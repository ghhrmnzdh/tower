#!/usr/bin/env python3
"""
towerd — Tower core daemon (no web server, no shell alias).

One background process that:
  * runs a local HTTPS/HTTP proxy (the "fence") pinning Claude Code to a country,
  * polls public-IP location,
  * reads Claude Code's local transcripts for real usage + pace,
  * routes Claude by editing ~/.claude/settings.json env (NEVER the shell),
  * talks to its front-ends (Swift menubar + Python TUI) through plain files
    in ~/.tower/ : state.json (out) and cmd/<id>.json (in).

stdlib only. Single instance (flock). Proxy fixed on :8888 so settings stay stable.
"""

import atexit
import errno
import json
import os
import re
import shlex
import shutil
import signal
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:                       # zoneinfo is stdlib on 3.9+
    ZoneInfo = None

# Platform split. Everything Unix-only (fcntl lock, caffeinate/pmset keep-awake,
# ps/lsof process scan, osascript focus, os.setsid) lives behind IS_WINDOWS; the
# Windows equivalents (named mutex, SetThreadExecutionState, toolhelp snapshot)
# live in _win.py, imported only here. macOS/Linux behavior is unchanged.
IS_WINDOWS = os.name == "nt"
if IS_WINDOWS:
    import _win
else:
    import fcntl

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(HOME, ".tower")
# Pre-rename state dirs, newest first (Corral, then Geo Guard). Config carries
# over from whichever still exists (see _migrate_legacy_state_dir).
LEGACY_CONFIG_DIRS = [os.path.join(HOME, ".corral"),
                      os.path.join(HOME, ".geo-guard")]
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")
LOCK_FILE = os.path.join(CONFIG_DIR, "daemon.lock")
CMD_DIR = os.path.join(CONFIG_DIR, "cmd")
LOG_FILE = os.path.join(CONFIG_DIR, "daemon.log")

CLAUDE_PROJECTS = os.path.join(HOME, ".claude", "projects")
CLAUDE_SETTINGS = os.path.join(HOME, ".claude", "settings.json")
SETTINGS_BAK = CLAUDE_SETTINGS + ".tower.bak"

# TCC-protected locations. Tower is a *monitor*, not a file manager: it must
# NEVER open or enumerate anything under these, because the first read triggers
# a macOS "Tower wants to access your Desktop/Photos/Music…" prompt — attributed
# to us, at an unpredictable moment, for data we never actually need. An agent
# whose cwd sits here still gets a row (project_name is derived from the path
# string, no I/O); we simply skip the git-root/branch/collision file reads for
# it. See the "Never trip a TCC prompt" invariant in CLAUDE.md. (/Volumes covers
# external/network disks, also gated by TCC on recent macOS.)
# Windows has no TCC prompt system, so nothing is "protected" there — the agent
# monitor can read git roots/branches freely. Empty tuple ⇒ _is_protected is a
# no-op (always False). The macOS list (and hardcoded /Volumes) stays as-is.
if IS_WINDOWS:
    _PROTECTED_ROOTS = ()
else:
    _PROTECTED_ROOTS = tuple(os.path.join(HOME, d) for d in (
        "Desktop", "Documents", "Downloads", "Pictures", "Movies", "Music",
        os.path.join("Library", "Mobile Documents"),   # iCloud Drive
        os.path.join("Library", "CloudStorage"),        # third-party cloud mounts
    )) + ("/Volumes",)


def _is_protected(path):
    """True if `path` is inside a TCC-gated folder — string-only, never stats
    (a stat/open here is itself what we're avoiding)."""
    if not path:
        return False
    p = os.path.normpath(os.path.abspath(path))
    return any(p == r or p.startswith(r + os.sep) for r in _PROTECTED_ROOTS)
LEGACY_SETTINGS_BAKS = [CLAUDE_SETTINGS + ".corral.bak",
                        CLAUDE_SETTINGS + ".geo-guard.bak"]

PROXY_PORT = int(os.environ.get("TOWER_PORT",
                                os.environ.get("CORRAL_PORT", "8888")))
CLAUDE_HOST_HINTS = ("anthropic", "claude.ai", "claude.com")

PMSET = "/usr/bin/pmset"
# Legacy path kept on purpose: the rule may already be installed on disk under
# this name and replacing it would cost the user another admin prompt.
SUDOERS_FILE = "/etc/sudoers.d/geo-guard"
USER = (os.environ.get("USER") or os.environ.get("LOGNAME")
        or os.environ.get("USERNAME") or "user")

# per-MTok USD (input, output, cache-write, cache-read); estimates, overridable.
PRICING = {
    "claude-opus-4-8":           (15.0, 75.0, 18.75, 1.50),
    "claude-sonnet-5":           (3.0, 15.0, 3.75, 0.30),
    "claude-haiku-4-5-20251001": (1.0, 5.0, 1.25, 0.10),
    "claude-fable-5":            (5.0, 25.0, 6.25, 0.50),
}
DEFAULT_PRICE = (15.0, 75.0, 18.75, 1.50)
DEFAULT_PLAN_WEEK_TOKENS = 400_000_000


def log(msg):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except OSError:
        pass


def load_config():
    cfg = {"theme": "Daybreak", "country": "CA",
           "plan_week_tokens": DEFAULT_PLAN_WEEK_TOKENS}
    try:
        with open(CONFIG_FILE) as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        _atomic_write(CONFIG_FILE, json.dumps(cfg, indent=2))
    except Exception:
        pass


def _atomic_write(path, text):
    d = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=d)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        _os_replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _os_replace(src, dst):
    """os.replace, but tolerant of Windows sharing violations. On POSIX a rename
    over a file another process holds open is fine; on Windows it can raise
    PermissionError for the brief instant a front-end has state.json open for
    reading, so retry a few times. macOS/Linux take the plain path."""
    if not IS_WINDOWS:
        os.replace(src, dst)
        return
    for i in range(20):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            time.sleep(0.01)
    os.replace(src, dst)   # last try — let it raise if still contended


def is_claude_host(host):
    h = (host or "").lower()
    return any(hint in h for hint in CLAUDE_HOST_HINTS)


def bind_free(preferred, host="127.0.0.1", span=20):
    last = None
    for p in list(range(preferred, preferred + span)) + [0]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, p))
            s.listen(128)
            return s, s.getsockname()[1]
        except OSError as e:
            last = e
            s.close()
    raise last or OSError("no free port")


STICKY_PORT_RETRY_S = 3.0   # wait this long for a dying predecessor to release the
                            # sticky port before drifting to a fresh one


def bind_proxy(cfg, host="127.0.0.1"):
    """Bind the proxy listener, preferring the SAME port as last run
    (cfg['proxy_port']) so a Claude session pinned to that port survives a daemon
    restart. A predecessor that's shutting down may hold the port for a moment
    (single-instance flock means it's the only other holder), so retry briefly
    before drifting via bind_free. The brief connect-refused gap during a restart
    is absorbed by Claude's native retries once the same port comes back. Persists
    the port whenever it changes."""
    sticky = cfg.get("proxy_port")
    if isinstance(sticky, int) and 0 < sticky < 65536:
        deadline = time.monotonic() + STICKY_PORT_RETRY_S
        while True:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((host, sticky))
                s.listen(128)
                return s, sticky
            except OSError:
                s.close()
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.2)
    sock, port = bind_free(PROXY_PORT, host=host)
    if port != cfg.get("proxy_port"):
        cfg["proxy_port"] = port
        save_config(cfg)
    return sock, port


# --------------------------------------------------------------------------- #
# State
# --------------------------------------------------------------------------- #
class State:
    def __init__(self, cfg):
        self.cfg = cfg
        self.target_cc = str(cfg.get("country", "CA")).upper()
        self.theme = cfg.get("theme", "Daybreak")
        self.plan_week_tokens = int(cfg.get("plan_week_tokens",
                                            DEFAULT_PLAN_WEEK_TOKENS))
        # When False the daemon NEVER runs `claude` → no /usage → no chance of
        # Photos/Music TCC prompts (claude's shell startup is what triggers them).
        self.plan_enabled = bool(cfg.get("plan_enabled", True))
        self.proxy_port = PROXY_PORT
        self.enforce = True
        self.block_all = False
        # The user's routing INTENT, mirrored from cfg so the proxy honors it live.
        # The listener outlives routing, so sessions started while routed keep their
        # HTTPS_PROXY env pointed here even after a double-confirmed route-off. When
        # routed is False we pass those pinned tunnels straight through UNGATED —
        # matching the direct connection new sessions get — instead of gating (or
        # breaking) them. Set ONLY by the double-confirmed route cmd or startup cfg;
        # never fail-open on its own. See should_block().
        self.routed = bool(cfg.get("routed", True))
        # Last-known settings.json file truth (is the proxy env installed?), kept
        # fresh by note_route_change each build_state cycle so the agent monitor can
        # classify per-session guard state without its own settings read.
        self.routing_now = None
        # Usable path to Anthropic, published by NetMonitor each sample.
        # None = not yet known (treated as unstable → fail-closed).
        self.net_ok = None

        self.status = "CHECKING"
        self.ip = self.city = self.region = self.isp = None
        self.country_name = self.country_cc = None
        self.last_error = None
        self._recheck = False
        # Egress IP the current reading was taken on, and the monotonic clock of
        # the last confirmed-OK reading. Together they let the gate notice a VPN
        # drop the instant it happens (egress changed) and refuse to trust a
        # reading that's gone stale (a hung geo thread) — both fail CLOSED.
        self._egress = None
        self._geo_ok_mono = None
        # Show the last known location instantly on launch (status CACHED means
        # "displaying last known, re-verifying"). CACHED is NOT "OK", so under
        # the fail-closed guard it does NOT allow Claude through — it is display
        # only. The live check overwrites it with a confirmed reading in ~1s.
        ll = cfg.get("last_location") or {}
        if ll.get("country_cc"):
            self.ip = ll.get("ip")
            self.city = ll.get("city")
            self.region = ll.get("region")
            self.isp = ll.get("isp")
            self.country_name = ll.get("country_name")
            self.country_cc = ll.get("country_cc")
            self.status = "CACHED"

        self.allowed = 0
        self.blocked = 0
        self.holding = 0             # Claude requests held (pending) in-proxy now
        self.last_claude_block = 0.0  # ts of the most recent blocked Claude request
        self.recent = deque(maxlen=50)

        self.keepawake_on = False
        self.keepawake_mode = "off"
        self._caffeinate = None

        # real plan usage, fetched by running `claude -p /usage` (no creds read)
        self.plan = None
        self._refreshplan = False

        self.stop = threading.Event()
        self.lock = threading.Lock()

        # Ground-truth path health: monotonic timestamps of recent Claude tunnels
        # the UPSTREAM reset mid-flight. The synthetic net probe (a tiny TLS
        # handshake) can't predict a large-body reset; real tunnel outcomes can.
        # A burst here flips the gate closed so the next reconnect is held as a
        # calm 503-pending instead of a raw ECONNRESET in Claude's escalating
        # backoff. Own lock so it never contends with self.lock.
        self._tfails = deque(maxlen=64)
        self._tfail_lock = threading.Lock()

    @property
    def in_target(self):
        return self.status == "OK" and self.country_cc == self.target_cc

    def claude_allowed(self):
        """Fail-CLOSED gate: a Claude request may proceed ONLY when we
        affirmatively confirm BOTH that you're inside the target country AND
        that the network has a usable path to Anthropic. Anything uncertain —
        location still checking / cached / errored, or the net offline /
        captive / edge-unreachable — is NOT allowed. There is no allow-through
        fallback: if we can't prove the request is safe, we don't make it.
        The cure for false blocks is durable, accurate detection (multi-source
        geo), not letting unconfirmed traffic through."""
        if not self.net_ok:
            return False
        # Real requests are the truest probe: if live Claude tunnels are being
        # reset upstream faster than chance, the path is not usable right now —
        # fail closed so the reconnect is held (calm 503) rather than admitted
        # into another raw ECONNRESET.
        if self.path_unstable():
            return False
        if not (self.status == "OK" and self.country_cc == self.target_cc):
            return False
        # Backstop: never keep the gate open on a confirmation we haven't
        # refreshed within GEO_MAX_AGE. A healthy geo loop refreshes every cycle
        # (or flips to ERROR, which the check above already blocks); only a hung
        # or dead loop lets an "OK" reading go stale — and then we fail closed
        # rather than trust a frozen "in-country" answer.
        m = self._geo_ok_mono
        return m is not None and (time.monotonic() - m) <= GEO_MAX_AGE

    def should_block(self, claude):
        # enforce off, or the user turned routing off: the proxy is a pass-through.
        # A pinned session (still holding our HTTPS_PROXY env) then behaves exactly
        # like a direct, unrouted connection — off means off, not stuck-gated.
        if not self.enforce or not self.routed:
            return False
        # Non-Claude traffic passes untouched unless block_all is set — we only
        # ever police Claude Code's own requests.
        if not claude and not self.block_all:
            return False
        # Fail-closed: block whenever a real Claude request wouldn't be allowed.
        return not self.claude_allowed()

    def record(self, host, claude, blocked):
        with self.lock:
            if blocked:
                self.blocked += 1
                if claude:
                    self.last_claude_block = time.time()
            else:
                self.allowed += 1
            self.recent.append({
                "t": datetime.now().strftime("%H:%M:%S"), "host": host,
                "kind": "claude" if claude else "other",
                "action": "blocked" if blocked else "allowed"})

    def record_tunnel_fail(self):
        """An established Claude tunnel was reset by the UPSTREAM side mid-flight
        — the ECONNRESET the client would otherwise surface. Timestamp it so
        path_unstable() can hold the next reconnect instead of re-admitting a
        doomed tunnel."""
        with self._tfail_lock:
            self._tfails.append(time.monotonic())

    def path_unstable(self):
        """True when real Claude tunnels are resetting upstream faster than
        chance — TUNNEL_FAIL_BURST resets within TUNNEL_FAIL_WINDOW_S. Self-
        clearing: once the gate holds, no new tunnels reach upstream, the window
        empties, and traffic is admitted again to re-test the path."""
        cutoff = time.monotonic() - TUNNEL_FAIL_WINDOW_S
        with self._tfail_lock:
            while self._tfails and self._tfails[0] < cutoff:
                self._tfails.popleft()
            return len(self._tfails) >= TUNNEL_FAIL_BURST

    def note_hold(self, delta):
        """Track Claude requests currently parked in the pre-CONNECT hold, so the
        front-ends can shimmer a 'reconnecting' indicator while any are waiting."""
        with self.lock:
            self.holding = max(0, self.holding + delta)

    def retry_pending(self):
        """True while a Claude request is actively waiting on the guard — held
        in-proxy right now, or blocked within the last few seconds while Claude
        Code retries. Flips False the instant the guard passes again, so the
        shimmer clears exactly when Claude is about to resume."""
        if not self.enforce or not self.routed or self.claude_allowed():
            return False
        if self.holding > 0:
            return True
        return (time.time() - self.last_claude_block) < RETRY_PENDING_WINDOW_S

    def location_dict(self):
        with self.lock:
            return {"status": self.status, "ip": self.ip, "city": self.city,
                    "region": self.region, "country_name": self.country_name,
                    "country_cc": self.country_cc, "in_target": self.in_target,
                    "isp": self.isp, "error": self.last_error}


# --------------------------------------------------------------------------- #
# Geolocation
# --------------------------------------------------------------------------- #
# Multiple independent geo sources so one provider being down, rate-limited,
# or wrong never leaves us "unconfirmed" (which, under fail-closed, blocks
# Claude). They're tried in order; the first that returns a country wins. All
# go through an opener with ProxyHandler({}) so the lookup measures your REAL
# egress IP and never travels through our own guard proxy — the same reason
# the net probes use raw sockets.
def _geo_opener():
    import urllib.request
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


# The gate must never keep trusting a confirmation it hasn't refreshed within
# this long: a geo thread that hangs or dies must fail CLOSED, not leave the
# door open on a frozen "in-country" reading. Comfortably larger than one full
# geo cycle (interval + worst-case lookup) so a healthy loop never trips it.
GEO_MAX_AGE = 60.0


def _egress_ip():
    """The local source IP the kernel would use to reach the public internet.
    On a VPN this is the tunnel's local address; the instant the VPN drops (or
    the primary interface changes) it flips to the real interface IP. A UDP
    'connect' only sets the socket's default peer — NO packet is sent — so this
    is a local, sub-millisecond call with no network dependency. Returns None
    when there's no route out at all (itself a change worth reacting to)."""
    for ref in ("1.1.1.1", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect((ref, 80))
                return s.getsockname()[0]
            finally:
                s.close()
        except OSError:
            continue
    return None


def _geo_ipapi(opener):
    fields = "status,country,countryCode,city,regionName,isp,query,message"
    with opener.open(f"http://ip-api.com/json/?fields={fields}", timeout=8) as r:
        d = json.loads(r.read().decode())
    if d.get("status") != "success":
        raise RuntimeError(d.get("message", "lookup failed"))
    return {"ip": d.get("query"), "city": d.get("city"),
            "region": d.get("regionName"), "isp": d.get("isp"),
            "country_name": d.get("country"),
            "country_cc": (d.get("countryCode") or "").upper()}


def _geo_ipwho(opener):
    with opener.open("https://ipwho.is/", timeout=8) as r:
        d = json.loads(r.read().decode())
    if not d.get("success", True) or not d.get("country_code"):
        raise RuntimeError(d.get("message", "lookup failed"))
    conn = d.get("connection") or {}
    return {"ip": d.get("ip"), "city": d.get("city"),
            "region": d.get("region"), "isp": conn.get("isp"),
            "country_name": d.get("country"),
            "country_cc": (d.get("country_code") or "").upper()}


def _geo_ipapico(opener):
    # Third independent IP-geo source (real client-IP geolocation, not a CDN
    # edge/colo reading — Cloudflare-fronted "loc" services can disagree with
    # the true egress country and would cause false blocks).
    with opener.open("https://ipapi.co/json/", timeout=8) as r:
        d = json.loads(r.read().decode())
    cc = (d.get("country_code") or d.get("country") or "").upper()
    if not cc or d.get("error"):
        raise RuntimeError(d.get("reason") or "no country in response")
    return {"ip": d.get("ip"), "city": d.get("city"),
            "region": d.get("region"), "isp": d.get("org"),
            "country_name": d.get("country_name") or cc, "country_cc": cc}


GEO_PROVIDERS = (("ip-api", _geo_ipapi), ("ipwho.is", _geo_ipwho),
                 ("ipapi.co", _geo_ipapico))


def geo_loop(state, interval=15):
    opener = _geo_opener()
    while not state.stop.is_set():
        egress = _egress_ip()          # the network this reading is taken on
        loc, err = None, None
        for name, fn in GEO_PROVIDERS:
            try:
                cand = fn(opener)
            except Exception as e:  # noqa: BLE001
                err = e
                continue
            if cand.get("country_cc"):
                loc = cand
                break
        if loc:
            with state.lock:
                state.status = "OK"
                state.ip = loc.get("ip")
                state.city = loc.get("city")
                state.region = loc.get("region")
                state.isp = loc.get("isp")
                state.country_name = loc.get("country_name")
                state.country_cc = loc.get("country_cc")
                state.last_error = None
                state._egress = egress
                state._geo_ok_mono = time.monotonic()
            state.cfg["last_location"] = {
                "ip": state.ip, "city": state.city, "region": state.region,
                "isp": state.isp, "country_name": state.country_name,
                "country_cc": state.country_cc}
            save_config(state.cfg)
        else:
            with state.lock:
                state.status = "ERROR"
                state.last_error = (_humanize(err) if err
                                    else "the location lookup failed")
                state._egress = egress
        # Wait out the interval — but the MOMENT the egress IP changes (VPN
        # dropped / reconnected / interface switched) we can no longer claim to
        # be in-country, so fail closed on the spot and re-verify immediately
        # instead of trusting the now-stale reading for up to a full interval.
        # _egress_ip() is a local, sub-ms call, so polling it every 0.25s is
        # free and bounds the off-country exposure window to ~a quarter second.
        waited = 0.0
        while waited < interval and not state.stop.is_set():
            if state._recheck:
                state._recheck = False
                break
            if _egress_ip() != state._egress:
                with state.lock:
                    if state.status == "OK":
                        state.status = "CHECKING"   # unconfirmed → gate closes
                break
            time.sleep(0.25)
            waited += 0.25


def _humanize(exc):
    reason = getattr(exc, "reason", exc)
    t = str(reason).lower()
    if "timed out" in t or "timeout" in t:
        return "the location service didn't respond in time"
    if "refused" in t:
        return "the location service refused the connection"
    if "unreachable" in t or "getaddrinfo" in t or "resolve" in t:
        return "no internet connection right now"
    return str(reason).split("] ", 1)[-1].strip() or "the location lookup failed"


# --------------------------------------------------------------------------- #
# Proxy
# --------------------------------------------------------------------------- #
TUNNEL_DRAIN_S = 5.0    # bound the wait for the second half to see EOF, no leak

def _pipe(src, dst):
    """Copy src→dst until src EOF, then half-close dst's WRITE side only, so the
    peer sees a graceful FIN — never a reset.

    A CONNECT tunnel is full-duplex: two _pipe threads run, one per direction.
    The old code's `finally` did shutdown(SHUT_RDWR) on BOTH sockets, so whichever
    direction finished first abortively tore down the other. shutdown(SHUT_RDWR)
    (and close) on a socket that still holds unread inbound data makes the kernel
    send a TCP RST, which Claude Code surfaces as `ECONNRESET`. A large request
    body keeps the UPLOAD half busy far longer, widening the window where the
    DOWNLOAD half returns first and RSTs a still-live upload — so big-payload
    turns died while tiny diffs sailed through. Half-closing WRITE-only lets each
    direction finish on its own; the caller closes both once both halves return.

    Returns True if this half died on a reset (RST/broken pipe) rather than a
    clean EOF — the caller uses that on the upstream-read half to tell a genuine
    mid-flight upstream drop from a normal close."""
    reset = False
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError as e:
        reset = e.errno in (errno.ECONNRESET, errno.EPIPE, errno.ETIMEDOUT)
    try:
        dst.shutdown(socket.SHUT_WR)   # propagate EOF as a FIN, not a RST
    except OSError:
        pass
    return reset


def _recv_headers(conn):
    data = b""
    while b"\r\n\r\n" not in data:
        try:
            chunk = conn.recv(4096)
        except OSError:
            break
        if not chunk:
            break
        data += chunk
        if len(data) > 65536:
            break
    return data


# A blocked Claude request is made PENDING, never FAILED. Two layers:
#   1. Short hold — while blocked we briefly withhold our answer (re-checking
#      every BLOCK_POLL_S) so a sub-second blip (geo re-confirming) clears and
#      the request succeeds on the FIRST try with no visible retry. This hold is
#      deliberately short: it happens BEFORE the CONNECT tunnel is established,
#      and Claude Code's TCP connect timeout for the proxy tunnel is undocumented
#      (~120s, possibly shorter) — a long pre-CONNECT hold risks tripping it and
#      making things worse. Keep it well under any plausible connect timeout.
#   2. 503 + retry — if still blocked, we answer 503 + Retry-After immediately.
#      Claude Code auto-retries 5xx with its native "Retrying in Ns · attempt
#      x/y" spinner. THAT is the durable "pending" UX: the agent waits and
#      resumes on its own when the guard clears. The retry budget is turned up
#      via settings.json env (see arm_retry_tolerance) so it rides out a whole
#      network switch instead of exhausting after the default 10 attempts.
# We reply 503, NEVER 403: Claude treats 403 as broken auth ("Please run
# /login") and kills the turn, but treats 503 as a transient, retry-able error.
# Still fail-closed: a request is let through ONLY if should_block() clears — we
# never pass unconfirmed traffic, we just make the block wait-able.
BLOCK_HOLD_S = 5.0          # short pre-CONNECT hold to absorb sub-second blips
BLOCK_POLL_S = 0.5          # re-check the block predicate this often while holding
TUNNEL_FAIL_WINDOW_S = 20.0  # window for counting upstream mid-tunnel resets
TUNNEL_FAIL_BURST = 2       # this many resets in-window → path unstable, hold next
BLOCK_RETRY_AFTER = 2       # Retry-After seconds — retry soon (Claude also backs off)
RETRY_PENDING_WINDOW_S = 20.0  # after a block, keep the 'pending' UI lit this long
UPSTREAM_CONNECT_S = 5.0    # TCP connect to upstream (the net probe proves TCP+TLS
                            # reachable in <=3s, so a slower connect means a bad path
                            # — fail fast to a retryable 502, don't hang the turn)
TUNNEL_IDLE_S = 600.0       # relay I/O timeout on an ESTABLISHED tunnel. create_
                            # connection's timeout stays ON the socket, so this was
                            # an accidental 10s that guillotined slow-first-byte turns
                            # and idle keep-alive sockets mid-session. Long-but-bounded:
                            # never kills a live turn, but a vanished peer (sleep/wake,
                            # NAT drop) can't leak the relay thread + fds forever.
HEADER_TIMEOUT_S = 10.0     # a client must present its request headers within this,
                            # else the accept thread + fd is pinned forever on a silent
                            # socket (accepted sockets don't inherit the listener timeout)
BLOCK_POLL_RAMP = (0.05, 0.1, 0.2, 0.4)  # first re-checks during a hold, then fall
                            # back to BLOCK_POLL_S — a sub-100ms blip clears almost
                            # instantly instead of rounding up to the 0.5s poll


def _decide_block(conn, state, host):
    claude = is_claude_host(host)
    if not state.should_block(claude):
        state.record(host, claude, blocked=False)
        return False

    # Blocked. Hold the connection open and keep re-checking so a short blip
    # (location re-confirming, net recovering) clears invisibly rather than
    # bubbling up as an error. Non-Claude blocked traffic (block_all) isn't
    # worth holding for — only give Claude the grace window.
    if claude:
        state.note_hold(1)          # light the 'reconnecting' shimmer in the UIs
        try:
            waited, ramp = 0.0, iter(BLOCK_POLL_RAMP)
            while waited < BLOCK_HOLD_S and not state.stop.is_set():
                step = next(ramp, BLOCK_POLL_S)
                state.stop.wait(step)
                waited += step
                if not state.should_block(claude):
                    state.record(host, claude, blocked=False)
                    return False
        finally:
            state.note_hold(-1)

    # Still blocked. Report it as a *retryable* condition, not a 403, so Claude
    # backs off and waits for a usable path instead of tearing down the session.
    state.record(host, claude, blocked=True)
    if state.path_unstable():
        reason = b"connection to Anthropic keeps dropping"
    elif not state.net_ok:
        reason = b"no stable connection to Anthropic"
    elif state.status != "OK":
        reason = b"location not confirmed"
    else:
        reason = b"outside target country"
    body = (b"tower: blocked (" + reason
            + b") - holding for a usable path, retry shortly\n")
    conn.sendall(b"HTTP/1.1 503 Service Unavailable\r\n"
                 b"Content-Type: text/plain\r\n"
                 b"Retry-After: " + str(BLOCK_RETRY_AFTER).encode() + b"\r\n"
                 b"Connection: close\r\nContent-Length: "
                 + str(len(body)).encode() + b"\r\n\r\n" + body)
    return True


def _upstream_connect(host, port):
    """Open the upstream leg of a tunnel. create_connection applies its timeout to
    the CONNECT only in spirit but leaves it ON the returned socket, so we reset it
    to a long-but-bounded idle timeout (TUNNEL_IDLE_S) — otherwise every relay recv
    inherits the short connect deadline and a slow-first-byte or idle keep-alive
    tunnel dies mid-session. TCP_NODELAY kills Nagle so streamed SSE token frames
    and small request bodies aren't batched behind delayed ACKs."""
    up = socket.create_connection((host, port), timeout=UPSTREAM_CONNECT_S)
    up.settimeout(TUNNEL_IDLE_S)
    try:
        up.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass
    return up


def _tunnel(conn, state, host, port):
    if _decide_block(conn, state, host):
        return
    try:
        up = _upstream_connect(host, port)
    except OSError:
        conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        # A burst of upstream connect failures on a Claude host means the path is
        # down right now — feed the gate so the next reconnect is held as a calm
        # 503-pending instead of serial 5s connect-hangs + raw 502s.
        if is_claude_host(host):
            state.record_tunnel_fail()
        return
    conn.settimeout(None)   # tunnel relay must block indefinitely, not carry the
                            # header-read deadline set on conn in _handle_proxy_client
    conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    t = threading.Thread(target=_pipe, args=(conn, up), daemon=True)
    t.start()
    # Main thread reads the UPSTREAM half: a reset here is a genuine mid-flight
    # drop from Anthropic/the VPN (not a client abort, which resets `conn` in the
    # upload thread). Both halves half-close on EOF; wait for the upload half to
    # drain rather than guillotining it, then close both.
    upstream_reset = _pipe(up, conn)
    t.join(TUNNEL_DRAIN_S)
    for s in (up, conn):
        try:
            s.close()
        except OSError:
            pass
    # Feed the real outcome back to the guard: a burst of upstream resets means
    # the path is unusable right now, so the next reconnect is held (calm 503)
    # instead of admitted into another raw ECONNRESET.
    if upstream_reset and is_claude_host(host):
        state.record_tunnel_fail()


def _plain(conn, state, method, target, raw):
    from urllib.parse import urlsplit
    p = urlsplit(target)
    host = p.hostname
    if not host:
        return
    port = p.port or 80
    if _decide_block(conn, state, host):
        return
    path = p.path or "/"
    if p.query:
        path += "?" + p.query
    try:
        blob = raw.split(b"\r\n", 1)[1]
    except IndexError:
        blob = b"\r\n"
    try:
        up = _upstream_connect(host, port)
    except OSError:
        conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
        return
    conn.settimeout(None)   # done reading headers; relay blocks indefinitely
    up.sendall(f"{method} {path} HTTP/1.1\r\n".encode() + blob)
    t = threading.Thread(target=_pipe, args=(conn, up), daemon=True)
    t.start()
    _pipe(up, conn)
    t.join(TUNNEL_DRAIN_S)
    for s in (up, conn):
        try:
            s.close()
        except OSError:
            pass


def _handle_proxy_client(conn, state):
    try:
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        conn.settimeout(HEADER_TIMEOUT_S)   # bound the header read; _tunnel/_plain
                                            # clear it (settimeout(None)) before relay
        raw = _recv_headers(conn)
        if not raw:
            return
        first = raw.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        parts = first.split(" ")
        if len(parts) < 3:
            return
        method, target = parts[0], parts[1]
        if method.upper() == "CONNECT":
            host, _, ps = target.partition(":")
            _tunnel(conn, state, host, int(ps or "443"))
        else:
            _plain(conn, state, method, target, raw)
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def proxy_loop(state, srv):
    srv.settimeout(0.5)
    while not state.stop.is_set():
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        threading.Thread(target=_handle_proxy_client, args=(conn, state),
                         daemon=True).start()
    srv.close()


def proxy_is_up(port):
    s = socket.socket()
    s.settimeout(0.3)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# Network health — "is it my internet, my link speed, or Anthropic?"
# Probes use RAW sockets only: on macOS urllib silently picks up system-wide
# proxies (getproxies_macosx_sysconf) even with a clean env, so it would
# measure the proxy instead of the network. The speed test builds an opener
# with ProxyHandler({}) for the same reason. Probes also deliberately bypass
# the guard proxy: net health measures the network, not geo policy, and must
# keep working while Claude is blocked.
# Known limitation: a completed TLS handshake proves Anthropic's EDGE is
# reachable, not that the backend is healthy — which is still the right
# message ("your internet is fine; the problem is on Anthropic's side").
# --------------------------------------------------------------------------- #
NET_TIMEOUT = 3.0
NET_INTERVAL_OK = 5.0
NET_INTERVAL_BAD = 3.0
DEGRADED_INTERNET_MS = 300
DEGRADED_API_MS = 1000            # TLS ≈ 2×RTT + crypto, hence the higher bar
NET_REFS = (("1.1.1.1", 443), ("8.8.8.8", 53))   # IP literals, two operators
API_PROBE_HOST = "api.anthropic.com"
SPEEDTEST_COOLDOWN = 60
SPEEDTEST_CAP_S = 15
SPEEDTEST_URLS = ("https://speed.cloudflare.com/__down?bytes=25000000",
                  "https://proof.ovh.net/files/10Mb.dat")


def _tcp_ms(host, port, timeout=NET_TIMEOUT):
    """TCP connect time in ms (≈ 1 RTT), or None. Raw socket, never urllib."""
    t0 = time.monotonic()
    try:
        s = socket.create_connection((host, port), timeout=timeout)
    except OSError:
        return None
    try:
        return (time.monotonic() - t0) * 1000.0
    finally:
        s.close()


def _api_probe(timeout=NET_TIMEOUT):
    """DNS + TCP + TLS handshake to api.anthropic.com — proves the layers
    that distinguish "my network can reach Anthropic" from "it can't" without
    spending an API request. getaddrinfo is timed separately first so a
    resolver fault is distinguishable from a connectivity fault.
    Returns (total_ms, None) or (None, kind) with kind in
    {"dns", "tcp", "tls", "timeout"}."""
    t0 = time.monotonic()
    try:
        infos = socket.getaddrinfo(API_PROBE_HOST, 443,
                                   proto=socket.IPPROTO_TCP)
        addr = infos[0][4][:2]
    except socket.gaierror:
        return None, "dns"
    except OSError:
        return None, "dns"
    try:
        sock = socket.create_connection(addr, timeout=timeout)
    except socket.timeout:
        return None, "timeout"
    except OSError:
        return None, "tcp"
    try:
        sock.settimeout(max(timeout - (time.monotonic() - t0), 0.1))
        ssl.create_default_context().wrap_socket(
            sock, server_hostname=API_PROBE_HOST).close()
        return (time.monotonic() - t0) * 1000.0, None
    except socket.timeout:
        return None, "timeout"
    except ssl.SSLError:
        return None, "tls"
    except OSError:
        return None, "tcp"
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _captive_check(timeout=NET_TIMEOUT):
    """True iff the network genuinely reaches the open internet: raw-socket
    HTTP GET to Apple's captive-portal endpoint must answer "Success". A
    portal intercepts this page with its login screen instead. Raw socket so
    macOS system proxies can't fake the answer."""
    try:
        s = socket.create_connection(("captive.apple.com", 80),
                                     timeout=timeout)
    except OSError:
        return False
    try:
        s.settimeout(timeout)
        s.sendall(b"GET /hotspot-detect.html HTTP/1.0\r\n"
                  b"Host: captive.apple.com\r\n\r\n")
        data = b""
        while len(data) < 8192:
            chunk = s.recv(2048)
            if not chunk:
                break
            data += chunk
        return b"Success" in data
    except OSError:
        return False
    finally:
        try:
            s.close()
        except OSError:
            pass


class NetMonitor:
    """Passive latency probes + on-demand bandwidth test (state.json "net").
    Same pattern as UsageIndex: own lock + loop() thread. Published `status`
    is debounced (2 consecutive samples must agree); `raw_status` is the
    latest sample. All timing time.monotonic(), timestamps time.time()."""

    def __init__(self, state):
        self.state = state
        self.lock = threading.Lock()
        self.history = deque(maxlen=60)
        self.status = "checking"
        self.raw_status = None
        self.reason = None                  # "dns" | "captive_portal" | None
        self.internet_ms = None
        self.api_ms = None
        self.api_error = None               # "dns"|"tcp"|"tls"|"timeout"|None
        self.last_change = time.time()
        self.checked = None
        self._pending = None                # (candidate status, streak)
        self._last_sample_mono = None
        self._probe_now = False             # set by "recheck" (like _recheck)
        self._st_thread = None
        self.speedtest = {"running": False, "progress": 0.0,
                          "mbps_down": None, "ms": None, "bytes": None,
                          "at": None, "error": None, "cooldown_until": 0.0}

    def loop(self):
        while not self.state.stop.is_set():
            try:
                mono = time.monotonic()
                internet_ms, api_ms, api_err = self._probe_once()
                raw, reason = self._classify(internet_ms, api_ms, api_err)
                now = time.time()
                with self.lock:
                    expected = (NET_INTERVAL_OK if self.status == "online"
                                else NET_INTERVAL_BAD)
                    if (self._last_sample_mono is not None
                            and mono - self._last_sample_mono > 3 * expected):
                        # Slept through samples (Device asleep): the first groggy
                        # post-wake sample must not count toward a flip.
                        self._pending = None
                    self._last_sample_mono = mono
                    self.raw_status = raw
                    self.internet_ms = internet_ms
                    self.api_ms = api_ms
                    self.api_error = api_err
                    self.checked = now
                    self.history.append({"t": now, "internet_ms": internet_ms,
                                         "api_ms": api_ms})
                    if self.status == "checking":
                        self.status, self.reason = raw, reason
                        self.last_change = now
                        self._pending = None
                    elif raw == self.status:
                        self.reason = reason
                        self._pending = None
                    else:
                        cand, n = self._pending or (None, 0)
                        n = n + 1 if cand == raw else 1
                        if n >= 2:          # 2 consecutive samples agree
                            self.status, self.reason = raw, reason
                            self.last_change = now
                            self._pending = None
                        else:
                            self._pending = (raw, n)
            except Exception as e:  # noqa: BLE001
                log(f"net probe error: {e}")
            with self.lock:
                interval = (NET_INTERVAL_OK if self.status == "online"
                            else NET_INTERVAL_BAD)
                # Publish a usable-path signal for the fail-closed guard.
                # "online"/"degraded" = reachable (degraded is merely slow, not
                # broken); "offline"/"captive"/"api_issue"/"checking" = no
                # trustworthy path to Anthropic → Claude requests are blocked.
                self.state.net_ok = self.status in ("online", "degraded")
            waited = 0.0
            while waited < interval and not self.state.stop.is_set():
                if self._probe_now:
                    self._probe_now = False
                    break
                time.sleep(0.25)
                waited += 0.25

    @staticmethod
    def _probe_once():
        refs = [m for m in (_tcp_ms(h, p) for h, p in NET_REFS)
                if m is not None]
        internet_ms = min(refs) if refs else None
        api_ms, api_err = _api_probe()
        return internet_ms, api_ms, api_err

    @staticmethod
    def _classify(internet_ms, api_ms, api_err):
        """Classification matrix → (raw_status, reason)."""
        if internet_ms is not None:
            if api_ms is not None:
                # internet_ms is a bare TCP connect to an IP literal — a VPN
                # gateway / transparent proxy / captive appliance can answer it
                # locally and read ~0ms while the real Anthropic path is slow.
                # api_ms (full TLS to a named host) can't be spoofed that way,
                # so when only it is slow, say so — don't blame "the internet".
                if internet_ms >= DEGRADED_INTERNET_MS:
                    return "degraded", "link_slow"     # local link genuinely slow
                if api_ms >= DEGRADED_API_MS:
                    return "degraded", "api_slow"      # link fine, path slow
                return "online", None
            if api_err == "dns":
                return "degraded", "dns"    # resolver broken, not Anthropic
            if api_err == "tls" and not _captive_check():
                # TCP to IP literals connectable but TLS to a real hostname
                # fails cert — the classic Wi-Fi login-page signature.
                return "captive", "captive_portal"
            return "api_issue", None        # internet fine, edge unreachable
        if api_ms is not None:
            # IPv6-only/NAT64: IPv4 literals fail, hostnames work — NOT
            # offline, because Anthropic is reachable.
            return "degraded", None
        return "offline", None

    def snapshot(self):
        with self.lock:
            return {"status": self.status,
                    "raw_status": self.raw_status,
                    "reason": self.reason,
                    "internet_ms": self.internet_ms,
                    "api_ms": self.api_ms,
                    "api_error": self.api_error,
                    "last_change": self.last_change,
                    "checked": self.checked,
                    "history": list(self.history),
                    "speedtest": dict(self.speedtest)}

    def start_speedtest(self):
        now = time.time()
        with self.lock:
            if self.speedtest["running"]:
                return {"error": "a speed test is already running"}
            cd = self.speedtest.get("cooldown_until") or 0.0
            if now < cd:
                return {"error": f"cooling down, retry in {int(cd - now) + 1}s"}
            self.speedtest["running"] = True
            self.speedtest["progress"] = 0.0
            self.speedtest["error"] = None
            self.speedtest["cooldown_until"] = now + SPEEDTEST_COOLDOWN
        self._st_thread = threading.Thread(target=self._run_speedtest,
                                           daemon=True)
        self._st_thread.start()
        return {"started": True}

    def _run_speedtest(self):
        import urllib.request
        # ProxyHandler({}) forces a DIRECT connection: bypasses macOS system
        # proxies AND the guard proxy — we measure the network, not policy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        err = None
        for url in SPEEDTEST_URLS:      # OVH fallback: independent of a CDN
            got = 0
            try:
                m = re.search(r"bytes=(\d+)", url)
                expected = int(m.group(1)) if m else 10_000_000
                t0 = time.monotonic()
                with opener.open(url, timeout=10) as r:
                    cl = r.headers.get("Content-Length")
                    if cl:
                        expected = max(int(cl), 1)
                    while True:
                        chunk = r.read(65536)
                        if not chunk:
                            break
                        got += len(chunk)
                        with self.lock:
                            self.speedtest["progress"] = min(
                                got / float(expected), 1.0)
                        if time.monotonic() - t0 >= SPEEDTEST_CAP_S:
                            break       # partial transfer is a valid sample
                elapsed = max(time.monotonic() - t0, 1e-6)
                if got <= 0:
                    raise OSError("no data received")
                with self.lock:
                    self.speedtest.update({
                        "running": False, "progress": 1.0,
                        "mbps_down": round(got * 8 / elapsed / 1e6, 1),
                        "ms": int(elapsed * 1000), "bytes": got,
                        "at": time.time(), "error": None})
                return
            except Exception as e:  # noqa: BLE001
                err = _humanize(e)
        with self.lock:
            self.speedtest.update({"running": False, "progress": 0.0,
                                   "error": err or "speed test failed",
                                   "at": time.time()})


# --------------------------------------------------------------------------- #
# Agent monitoring — the summary (state.json "agents")
# Merges the process table with offset-tailed transcript reads into one view:
# per-session status, the needs-you queue, and repo/file collisions.
# READ-ONLY toward ~/.claude: never writes there, never injects input.
# The snapshot's field names are a contract with the Swift app — don't rename.
# --------------------------------------------------------------------------- #
AGENT_INTERVAL = 1.0          # full merge + status engine cadence
AGENT_FAST_INTERVAL = 0.5     # between full refreshes: cheap activity-only tick
# The `ps` table scan is the one costly part of a full refresh (~60ms); the
# transcript tail + status engine are cheap (~20ms). So we run the whole refresh
# every 1s (halving the 2-cycle status-transition debounce from ~4s to ~2s so an
# agent flipping working↔idle/done surfaces fast) but reuse the last `ps` result
# for up to this long — process presence changes rarely, and a ~2s lag on
# detecting a *dead* process is fine. This keeps status near-realtime without
# doubling the `ps` cost.
PROC_RESCAN_S = 1.8
# How often to latch which agents have a live TCP connection to the proxy — proof
# they're actually routed. One lsof call (~50ms) on its own cadence, off the ps
# path; positive-proof only (an idle agent shows nothing between keep-alives), so
# the latch upgrades the routing-timeline presumption, never contradicts it.
PROXY_CLIENT_RESCAN_S = 5.0
# retail_known() (the 0.5s hot path) only re-tails transcripts touched within
# this window. An agent that's actually producing activity has a sub-second
# mtime, so bounding here keeps the hot path O(active-sessions) instead of
# O(every-transcript-ever-seen) — the full scan() still tails everything each
# cycle, so long-idle rows stay correct, just refreshed at 1s not 0.5s.
RETAIL_ACTIVE_S = 90.0
# Thresholds; each overridable via the same-named key in ~/.tower/config.json
AGENT_WORKING_S = 10.0        # agent_working_s: fresher mtime = working
AGENT_IDLE_S = 300.0          # agent_idle_s: staler (process alive) = idle
AGENT_GONE_KEEP_S = 60.0      # agent_gone_keep_s: keep gone rows, then drop
AGENT_TOOL_GRACE_S = 180.0    # agent_tool_grace_s: slow-tool grace period
AGENT_PENDING_WARN_S = 600.0  # agent_pending_warn_s: pending_tool → warn
AGENT_WORKING_WARN_S = 1200.0  # agent_working_warn_s: no completed turn → warn
# Mid-turn dead silence past this = the signature of an in-progress API error /
# retry storm. Claude Code writes NOTHING to the transcript while it retries an
# overloaded / 500 / connection error (only the final outcome — a real reply, or
# a terminal "API Error:" synthetic line — is written), so the turn just goes
# quiet and the status engine would otherwise keep reading it as "working". This
# is the only signal we have for a live API stall; kept well above a normal
# think/first-token gap so a healthy turn never trips it. (agent_api_stall_s)
AGENT_API_STALL_S = 90.0
AGENT_EDIT_WINDOW_S = 900.0   # recent-edit window for file-level collisions
GRACE_TOOLS = ("Bash", "Task", "Agent", "Workflow")    # legitimately slow
EDIT_TOOLS = ("Edit", "Write", "NotebookEdit", "MultiEdit")
MODEL_TIERS = ("haiku", "sonnet", "opus", "fable")     # ascending caliber
NEEDS_RANK = {"failed": 0, "pending_tool": 1, "asking": 2, "done": 3}

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_RE_SESSION_ID = re.compile(r"--session-id[= ](" + _UUID + r")")
_RE_RESUME_PATH = re.compile(r"--resume[= ](\S+\.jsonl)")
_RE_RESUME_ID = re.compile(r"--resume[= ](" + _UUID + r")(?:\s|$)")
# `/effort` echoes its result into the transcript as a user message, e.g.
# "<local-command-stdout>Set effort level to max (this session only): …". This
# is the ONLY per-session record of the live effort — settings.json holds only
# the startup default — so we parse it to show each agent's true value.
_RE_EFFORT_CMD = re.compile(
    r"[Ss]et effort level to (\w+)|[Rr]eset effort.*?to (default|\w+)")


def _model_family(model):
    m = (model or "").lower()
    for fam in ("fable", "opus", "sonnet", "haiku"):
        if fam in m:
            return fam
    return "other"


def _short_path(p):
    # Separator-agnostic: transcript paths recorded on Windows use "\", on Unix
    # "/". Normalize to "/" so the last-two-segments shortening works on both.
    parts = str(p).replace("\\", "/").rstrip("/").split("/")
    return "/".join(parts[-2:]) if len(parts) > 2 else str(p)


def _tool_detail(name, inp):
    p = (inp.get("file_path") or inp.get("notebook_path")
         or inp.get("path"))
    if p:
        return _short_path(p)
    c = inp.get("command")
    if c:
        return " ".join(str(c).split())[:80]
    q = (inp.get("pattern") or inp.get("query") or inp.get("prompt")
         or inp.get("url") or inp.get("description"))
    if q:
        return str(q)[:80]
    return None


def _activity_phrase(tool):
    """Human phrase from the latest tool_use ("editing src/Model.swift")."""
    if not tool:
        return None
    name = tool.get("name") or "?"
    detail = tool.get("detail")
    n = name.lower()
    if n in ("edit", "write", "notebookedit", "multiedit"):
        return f"editing {detail}" if detail else "editing files"
    if n == "read":
        return f"reading {detail}" if detail else "reading files"
    if n in ("grep", "glob", "websearch", "toolsearch"):
        return "searching"
    if n == "bash":
        c = detail or ""
        if re.search(r"(?:^|\s|/)(?:pytest|npm test|cargo test|swift test"
                     r"|go test|xcodebuild test|make test)\b", c):
            return "running tests"
        first = c.split()[0] if c.split() else ""
        return f"running {os.path.basename(first)}" if first else \
            "running a command"
    if n in ("task", "agent"):
        return "delegating to a subagent"
    if n == "webfetch":
        return "fetching a page"
    if n == "askuserquestion":
        return "asking a question"
    return f"using {name}"


def _stall_secs(rec, threshold):
    """Seconds a *working* turn has been silent MID-turn with nothing pending —
    or None if it isn't stalled. This is Tower's only handle on an in-progress
    API error / retry storm, which Claude Code doesn't record in the transcript
    (see AGENT_API_STALL_S). Mid-turn = the last stop wasn't an end_turn (the
    turn hasn't completed); nothing pending = no open tool (an open tool is the
    legitimate 'pending_tool' wait, not a stall). Anything past `threshold` of
    dead air here is abnormal — a healthy first-token / think gap is far shorter."""
    if rec.get("last_stop") == "end_turn":
        return None                     # turn completed — not mid-flight
    if rec.get("open_tools"):
        return None                     # a tool is genuinely pending, not a stall
    mtime = rec.get("mtime")
    if not mtime:
        return None
    age = time.time() - mtime
    return int(age) if age > threshold else None


def _activity_for(rec, status, stall_s=AGENT_API_STALL_S):
    """The live description line for a session: the API-error reason when the
    turn has failed, an honest 'no response — possible API error' when a working
    turn has gone silent mid-flight, otherwise the phrase for its latest
    tool_use. Shared by the full-refresh row builder and the between-refresh fast
    tick so both agree."""
    if status == "paused":
        return "paused — process suspended"
    if status == "failed" and rec.get("api_error_msg"):
        return rec.get("api_error_msg")
    if status == "working":
        stalled = _stall_secs(rec, stall_s)
        if stalled is not None:
            return (f"no response for {stalled}s — "
                    "possible API error or network stall")
    return _activity_phrase(rec.get("last_tool"))


def _norm_effort(v):
    """Normalise an effort value to Claude Code's own canonical name — low,
    medium, high, xhigh, max (NOT abbreviated). Aliases fold in; None for
    anything unrecognised so the UI can simply omit the chip."""
    s = str(v or "").strip().lower()
    return {"low": "low", "minimal": "low",
            "medium": "medium", "med": "medium", "normal": "medium",
            "high": "high",
            "xhigh": "xhigh", "x-high": "xhigh", "extra-high": "xhigh",
            "max": "max", "maximum": "max", "ultra": "max",
            "highest": "max"}.get(s)


def _git_branch_of(root):
    """Branch from .git/HEAD (worktree .git-file indirection handled)."""
    if not root or _is_protected(root):
        return None                 # never read files inside a TCC-gated folder
    gd = os.path.join(root, ".git")
    try:
        if os.path.isfile(gd):
            with open(gd) as f:
                line = f.read().strip()
            if line.startswith("gitdir:"):
                gd = line.split(":", 1)[1].strip()
        with open(os.path.join(gd, "HEAD")) as f:
            head = f.read().strip()
        if head.startswith("ref:"):
            return head.rsplit("/", 1)[-1]
        return head[:8]
    except Exception:  # noqa: BLE001
        return None


class ProcScanner:
    """Reads the process table for live claude processes. `lsof` (works
    without sudo) is used ONLY for pids whose args don't name a session, and
    is cached per pid — claude does not hold its .jsonl open, so cwd is the
    correlation key for bare interactive sessions."""

    def __init__(self):
        self.lsof_ok = True
        self._cwd_cache = {}

    def _scan_entries(self):
        """Normalized raw process rows — one dict per candidate claude process
        with keys pid, ppid, tty, stopped, lstart, args (full command line).
        POSIX reads the BSD `ps` table; Windows reads Win32_Process via _win.
        The shared parser in scan() turns these into the correlated row dicts."""
        if IS_WINDOWS:
            try:
                return _win.enum_claude_processes()
            except Exception as e:  # noqa: BLE001
                log(f"win proc scan error: {e}")
                return []
        try:
            r = subprocess.run(
                ["ps", "-axo", "pid=,ppid=,tty=,state=,lstart=,args="],
                capture_output=True, text=True, timeout=10)
            lines = r.stdout.splitlines()
        except Exception as e:  # noqa: BLE001
            log(f"ps scan error: {e}")
            return []
        entries = []
        for line in lines:
            parts = line.split(None, 9)
            if len(parts) < 10:
                continue
            args = parts[9]
            exe = args.split(None, 1)[0]
            if os.path.basename(exe) not in ("claude", "claude.exe"):
                continue
            try:
                pid, ppid = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            tty = parts[2] if parts[2] not in ("??", "-") else None
            # ps STAT: a leading 'T' (or 't', traced) is a SIGSTOP-suspended
            # process. It writes nothing while frozen, so the transcript goes
            # silent exactly like an API stall — distinguish the two here so a
            # deliberately-paused agent is reported as paused, not "erroring".
            stopped = parts[3][:1] in ("T", "t")
            try:
                lstart = time.mktime(time.strptime(
                    " ".join(parts[4:9]), "%a %b %d %H:%M:%S %Y"))
            except Exception:  # noqa: BLE001
                lstart = None
            entries.append({"pid": pid, "ppid": ppid, "tty": tty,
                            "stopped": stopped, "lstart": lstart, "args": args})
        return entries

    def scan(self):
        """{pid: {pid, ppid, tty, lstart, kind, session_id, transcript}} for
        claude processes; bg-pty-host parents are dropped (child kept)."""
        rows, hosts = {}, set()
        for e in self._scan_entries():
            pid, ppid = e["pid"], e["ppid"]
            args = e["args"]
            tty = e["tty"]
            stopped = e["stopped"]
            lstart = e["lstart"]
            if "--bg-pty-host" in args:
                hosts.add(pid)      # parent half of a bg pair — child wins
                continue
            toks = args.split(None, 2)
            sub = (toks[1] if len(toks) > 1
                   and not toks[1].startswith("-") else None)
            kind = "infra" if sub in ("daemon", "login") else None
            sid = None
            m = _RE_SESSION_ID.search(args)
            if m:
                sid = m.group(1).lower()
            transcript = None
            m = _RE_RESUME_PATH.search(args)
            if m:
                transcript = m.group(1)
            elif not sid:
                m = _RE_RESUME_ID.search(args)
                if m:
                    sid = m.group(1).lower()
            rows[pid] = {"pid": pid, "ppid": ppid, "tty": tty,
                         "lstart": lstart, "kind": kind, "session_id": sid,
                         "transcript": transcript, "stopped": stopped}
        for p in rows.values():
            if p["kind"]:
                continue
            if p["ppid"] in hosts:
                p["kind"] = "background"
            elif p["tty"]:
                p["kind"] = "interactive"
            elif p["session_id"] or p["transcript"]:
                p["kind"] = "background"
            else:
                p["kind"] = "infra"     # e.g. our own `claude -p /usage`
        for pid in list(self._cwd_cache):
            if pid not in rows:
                self._cwd_cache.pop(pid, None)
        return rows

    def cwd_of(self, pid):
        # No dependency-free way to read another process's cwd on Windows
        # (needs fragile PEB reads / admin). Return None: bare interactive
        # sessions simply won't be correlated by cwd there — background/scripted
        # agents (which carry --session-id/--resume in their args) still work.
        if IS_WINDOWS:
            return None
        if pid in self._cwd_cache:
            return self._cwd_cache[pid]
        cwd = None
        try:
            r = subprocess.run(
                ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                capture_output=True, text=True, timeout=10)
            for ln in r.stdout.splitlines():
                if ln.startswith("n"):
                    cwd = ln[1:].strip()
            if cwd:
                self.lsof_ok = True
        except Exception as e:  # noqa: BLE001
            self.lsof_ok = False
            log(f"lsof cwd error pid={pid}: {e}")
        self._cwd_cache[pid] = cwd
        return cwd


class TranscriptIndex:
    """Offset-tailing reader of ~/.claude/projects/<encoded>/*.jsonl (depth 1
    only — subagents/ etc. skipped). Per file keeps {mtime, size, offset,
    summary}; on growth parses only the new complete lines, on shrink resets.
    The dir encoding is lossy, so the literal per-line "cwd" field is truth.
    Every line parse is defensive; failures count into parse_errors."""

    def __init__(self):
        self.parse_errors = 0
        self._files = {}

    def scan(self):
        seen = set()
        try:
            dirs = os.listdir(CLAUDE_PROJECTS)
        except OSError:
            return
        for d in dirs:
            pdir = os.path.join(CLAUDE_PROJECTS, d)
            if not os.path.isdir(pdir):
                continue
            try:
                names = os.listdir(pdir)
            except OSError:
                continue
            for name in names:
                if not name.endswith(".jsonl"):
                    continue
                path = os.path.join(pdir, name)
                if not os.path.isfile(path):
                    continue
                try:
                    st = os.stat(path)
                except OSError:
                    continue
                seen.add(path)
                rec = self._files.get(path)
                if (rec and rec["mtime"] == st.st_mtime
                        and rec["size"] == st.st_size):
                    continue
                if rec is None or st.st_size < rec["size"]:
                    # new file, or shrunk/replaced (compaction): reparse
                    rec = {"mtime": 0.0, "size": 0, "offset": 0,
                           "summary": self._new_summary(path)}
                    self._files[path] = rec
                self._tail(path, rec)
                rec["mtime"] = st.st_mtime
                rec["size"] = st.st_size
                rec["summary"]["mtime"] = st.st_mtime
        for path in list(self._files):
            if path not in seen:
                self._files.pop(path, None)

    def retail_known(self):
        """Cheap re-tail of already-tracked files only — no directory walk.
        Stats each known transcript and parses any newly-appended lines. Skips
        discovery of new files and shrink/compaction resets (the full scan()
        handles those); this exists so the fast tick can refresh live activity
        every ~0.5s at a fraction of scan()'s cost. Only recently-touched files
        are re-tailed: a session producing activity has a sub-second mtime, so
        this bounds the hot path to O(active) even when tens of thousands of old
        transcripts have accumulated — full scan() still tails the rest at 1s."""
        cutoff = time.time() - RETAIL_ACTIVE_S
        for path, rec in list(self._files.items()):
            if rec["mtime"] < cutoff:
                continue
            try:
                st = os.stat(path)
            except OSError:
                continue
            if rec["mtime"] == st.st_mtime and rec["size"] == st.st_size:
                continue
            if st.st_size < rec["size"]:
                continue                # shrunk/replaced — defer to full scan()
            self._tail(path, rec)
            rec["mtime"] = st.st_mtime
            rec["size"] = st.st_size
            rec["summary"]["mtime"] = st.st_mtime

    def summaries(self):
        return {p: r["summary"] for p, r in self._files.items()}

    @staticmethod
    def _new_summary(path):
        return {"path": path,
                "session_id": os.path.basename(path)[:-len(".jsonl")],
                "cwd": None, "git_branch": None, "version": None,
                "session_kind": None, "model": None, "title": None,
                "agent_name": None, "last_prompt": None,
                "started": None, "last_ts": None, "last_user_ts": None,
                "last_stop": None, "last_text": None, "last_synth": False,
                "trailing_error": False, "turn_done_ts": None,
                "api_retrying": False, "api_error_msg": None,
                "effort_cmd": None,     # per-session /effort override (or None)
                "open_tools": {}, "last_tool": None,
                "err_ring": deque(maxlen=10), "tools_done": 0, "errors": 0,
                "subagents": 0, "files": set(),
                "recent_edits": deque(maxlen=100), "mtime": 0.0}

    def _tail(self, path, rec):
        try:
            with open(path, "rb") as f:
                f.seek(rec["offset"])
                data = f.read()
        except OSError:
            return
        if not data:
            return
        end = data.rfind(b"\n")
        if end < 0:
            return                      # no complete new line yet
        for line in data[:end].split(b"\n"):
            if line.strip():
                self._feed(rec["summary"], line)
        rec["offset"] += end + 1

    def _feed(self, s, line):
        try:
            o = json.loads(line)
        except Exception:  # noqa: BLE001
            self.parse_errors += 1
            return
        if not isinstance(o, dict):
            self.parse_errors += 1
            return
        try:
            self._apply(s, o)
        except Exception:  # noqa: BLE001
            self.parse_errors += 1

    def _apply(self, s, o):
        ts = _parse_ts(o.get("timestamp"))
        if ts is not None:
            if s["started"] is None or ts < s["started"]:
                s["started"] = ts
            if s["last_ts"] is None or ts > s["last_ts"]:
                s["last_ts"] = ts
        v = o.get("sessionId") or o.get("session_id")
        if v:
            s["session_id"] = v
        for src, dst in (("cwd", "cwd"), ("gitBranch", "git_branch"),
                         ("version", "version")):
            v = o.get(src)
            if v:
                s[dst] = v
        if o.get("sessionKind") == "bg":
            s["session_kind"] = "bg"
        if o.get("isSidechain"):
            return              # subagent chatter never drives main status
        t = o.get("type")
        if t == "ai-title":
            v = o.get("aiTitle")
            if v:
                s["title"] = str(v)[:160]
        elif t == "agent-name":
            v = o.get("agentName")
            if v:
                s["agent_name"] = str(v)[:160]
        elif t == "last-prompt":
            v = o.get("lastPrompt")
            if v:
                s["last_prompt"] = str(v)[:300]
        elif t == "system":
            sub = o.get("subtype")
            if sub == "turn_duration":
                s["turn_done_ts"] = ts or s["last_ts"]
            elif sub == "api_error":
                # Claude is retrying a failed API call (connection / overload /
                # rate-limit). These lines keep refreshing the transcript mtime,
                # so without an explicit flag the agent would look "working"
                # through the entire retry storm. Record it so the status engine
                # can surface the truth in real time.
                s["api_retrying"] = True
                err = o.get("error") if isinstance(o.get("error"), dict) else {}
                att, mx = o.get("retryAttempt"), o.get("maxRetries")
                if att and mx:
                    s["api_error_msg"] = f"API error — retrying {att}/{mx}"
                else:
                    s["api_error_msg"] = ("API error — " + str(
                        err.get("formatted") or err.get("message")
                        or "retrying"))[:160]
        elif t == "assistant":
            self._assistant(s, o, ts)
        elif t == "user":
            self._user(s, o, ts)

    def _assistant(self, s, o, ts):
        m = o.get("message")
        if not isinstance(m, dict):
            return
        model = m.get("model")
        if model == "<synthetic>":
            s["last_synth"] = True      # error notice — never a real model
        elif model:
            s["model"] = model
            s["last_synth"] = False
            s["api_retrying"] = False   # a real reply landed — recovered
            s["api_error_msg"] = None
        stop = m.get("stop_reason")
        if stop:                # multi-line msgs: last line carries the final
            s["last_stop"] = stop
            if stop == "end_turn":
                s["turn_done_ts"] = ts or s["last_ts"]
        s["trailing_error"] = False
        content = m.get("content")
        if not isinstance(content, list):
            return
        texts = []
        for b in content:
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "text":
                if b.get("text"):
                    texts.append(str(b.get("text")))
            elif bt == "tool_use":
                name = b.get("name") or "?"
                inp = b.get("input") if isinstance(b.get("input"), dict) \
                    else {}
                tool = {"name": name, "detail": _tool_detail(name, inp),
                        "since": ts or time.time()}
                tid = b.get("id")
                if tid:
                    s["open_tools"][tid] = tool
                    while len(s["open_tools"]) > 40:
                        s["open_tools"].pop(next(iter(s["open_tools"])))
                s["last_tool"] = tool
                fp = inp.get("file_path") or inp.get("notebook_path")
                if name in EDIT_TOOLS and fp:
                    s["files"].add(fp)
                    s["recent_edits"].append((ts or time.time(), fp))
                if name in ("Task", "Agent"):
                    s["subagents"] += 1
        if texts:
            s["last_text"] = "\n".join(texts)[-2000:]
        if model == "<synthetic>":
            # A <synthetic> assistant message is Claude's own error notice. Only
            # treat the API-error variety as a fault (a "[Request interrupted]"
            # is also synthetic but is not a failure) — key off the explicit
            # flag / top-level error, or the "API Error:" text Claude writes.
            first = texts[0].strip() if texts else ""
            if (o.get("isApiErrorMessage") or o.get("error")
                    or "api error" in first.lower()):
                s["api_retrying"] = False    # terminal error, not a retry line
                s["api_error_msg"] = first[:160] or "API error"

    def _user(self, s, o, ts):
        m = o.get("message")
        content = m.get("content") if isinstance(m, dict) else None
        # `/effort` result echo: capture the live per-session effort. This is a
        # command stdout, not a real turn — record it and return so it doesn't
        # reset turn state below.
        if isinstance(content, str) and "effort level to" in content.lower():
            mm = _RE_EFFORT_CMD.search(content)
            if mm:
                lvl = mm.group(1) or mm.group(2)
                # "reset to default" clears the override → fall back to settings
                s["effort_cmd"] = None if (lvl or "").lower() == "default" \
                    else _norm_effort(lvl)
            return
        handled = False
        if isinstance(content, list):
            for b in content:
                if not (isinstance(b, dict)
                        and b.get("type") == "tool_result"):
                    continue
                handled = True
                s["open_tools"].pop(b.get("tool_use_id"), None)
                err = bool(b.get("is_error"))
                s["err_ring"].append(err)
                s["tools_done"] += 1
                if err:
                    s["errors"] += 1
                s["trailing_error"] = err
        if not handled:
            # a real user prompt — a new turn begins
            s["last_user_ts"] = ts or s["last_ts"]
            s["last_stop"] = None
            s["last_text"] = None
            s["last_synth"] = False
            s["trailing_error"] = False
            s["api_retrying"] = False
            s["api_error_msg"] = None


class SettingsCache:
    """mtime-cached reader for Claude `settings.json` files (user + per-project).
    Resolves each session's effort level without re-parsing JSON every 2s cycle:
    a path is only re-read when its mtime changes. Strictly read-only."""

    def __init__(self):
        self._cache = {}        # path -> (mtime, dict|None)

    def get(self, path):
        try:
            mt = os.stat(path).st_mtime
        except OSError:
            self._cache.pop(path, None)
            return None
        hit = self._cache.get(path)
        if hit and hit[0] == mt:
            return hit[1]
        data = None
        try:
            with open(path) as f:
                d = json.load(f)
            if isinstance(d, dict):
                data = d
        except Exception:  # noqa: BLE001
            data = None
        self._cache[path] = (mt, data)
        return data


class AgentMonitor:
    """Owns ProcScanner + TranscriptIndex and merges them: status engine,
    2-cycle transition debounce, needs-you queue, collisions, summary counters,
    events ring, plus focus/dismiss services for dispatch()."""

    def __init__(self, state):
        self.state = state
        self.lock = threading.Lock()
        self.procs = ProcScanner()
        self._procs_cache = None     # last ps scan, reused between PROC_RESCAN_S
        self._procs_ts = 0.0
        self._proxy_seen = {}        # pid -> wall ts of last observed live proxy conn
        self._proxy_scan_ts = 0.0
        self.transcripts = TranscriptIndex()
        cfg = state.cfg
        self.working_s = float(cfg.get("agent_working_s", AGENT_WORKING_S))
        self.idle_s = float(cfg.get("agent_idle_s", AGENT_IDLE_S))
        self.gone_keep_s = float(cfg.get("agent_gone_keep_s",
                                         AGENT_GONE_KEEP_S))
        self.tool_grace_s = float(cfg.get("agent_tool_grace_s",
                                          AGENT_TOOL_GRACE_S))
        self.pending_warn_s = float(cfg.get("agent_pending_warn_s",
                                            AGENT_PENDING_WARN_S))
        self.working_warn_s = float(cfg.get("agent_working_warn_s",
                                            AGENT_WORKING_WARN_S))
        self.api_stall_s = float(cfg.get("agent_api_stall_s",
                                         AGENT_API_STALL_S))
        self._track = {}        # sid -> status/since/pending/gone_since/…
        self._settings = SettingsCache()
        self._dismissed = set()
        self._events = deque(maxlen=50)
        self._done_today = 0
        self._done_day = datetime.now().strftime("%Y-%m-%d")
        self._git_cache = {}
        self._snap = {"sessions": [], "needs_you": [], "collisions": [],
                      "summary": {"working": 0, "needs_you": 0,
                               "done_today": 0, "top_tier": None,
                               "unguarded": 0, "pinned": 0},
                      "events": [],
                      "meta": {"lsof_ok": True, "parse_errors": 0,
                               "claude_versions": []}}

    def loop(self, interval=AGENT_INTERVAL, fast=AGENT_FAST_INTERVAL):
        while not self.state.stop.is_set():
            try:
                self.refresh()
            except Exception as e:  # noqa: BLE001
                log(f"agents refresh error: {e}")
            waited = 0.0
            while waited < interval - 1e-6 and not self.state.stop.is_set():
                time.sleep(fast)
                waited += fast
                if waited < interval - 1e-6:    # the last tick == next refresh
                    try:
                        self._fast_tick()
                    except Exception as e:  # noqa: BLE001
                        log(f"agents fast tick error: {e}")

    def _fast_tick(self):
        """Between full refreshes, keep the live description honest without a
        full cycle. Re-tails only known transcripts (no `ps`/lsof, no status
        engine, no directory walk) and patches the transcript-derived fields —
        activity line, last-activity clock, tick counters — onto the existing
        snapshot. Status/pending/health stay as the last full refresh computed
        them; they get re-evaluated on the next 2s cycle. Rows are NOT re-sorted
        (reordering agents every 0.5s would be visually jarring)."""
        self.transcripts.retail_known()
        by_sid = {}
        for rec in self.transcripts.summaries().values():
            sid = rec.get("session_id")
            if sid:
                prev = by_sid.get(sid)
                if prev is None or rec["mtime"] > prev["mtime"]:
                    by_sid[sid] = rec
        with self.lock:
            for sess in self._snap["sessions"]:
                rec = by_sid.get(sess["session_id"])
                if rec is None:
                    continue
                sess["activity"] = _activity_for(rec, sess["status"],
                                                 self.api_stall_s)
                sess["last_activity"] = rec.get("mtime")
                # Live per-session effort: a `/effort` change lands in the
                # transcript and is picked up here within ~0.5s (settings default
                # otherwise), so the badge tracks the true value in near-realtime.
                sess["effort"] = (rec.get("effort_cmd")
                                  or self._effort_of(sess.get("cwd"),
                                                     sess.get("git_root")))
                sess["ticks"] = {"tools_done": rec.get("tools_done", 0),
                                 "files": len(rec.get("files") or ()),
                                 "errors": rec.get("errors", 0),
                                 "subagents": rec.get("subagents", 0)}

    # -- merge + status engine ------------------------------------------- #
    def refresh(self):
        now = time.time()
        day = datetime.now().strftime("%Y-%m-%d")
        if day != self._done_day:       # done_today counts since local midnight
            self._done_day = day
            self._done_today = 0
        # The `ps` scan is the costly part; reuse it across sub-PROC_RESCAN_S
        # refreshes so the 1s status cadence doesn't pay for a `ps` every cycle.
        if self._procs_cache is None or now - self._procs_ts >= PROC_RESCAN_S:
            self._procs_cache = self.procs.scan()
            self._procs_ts = now
        procs = self._procs_cache
        # Latch live proxy connections on their own (slower) cadence, then forget
        # pids that are no longer running so the guard-proof map can't go stale.
        if now - self._proxy_scan_ts >= PROXY_CLIENT_RESCAN_S:
            self._scan_proxy_clients(now)
            self._proxy_scan_ts = now
            self._proxy_seen = {pid: t for pid, t in self._proxy_seen.items()
                                if pid in procs}
        self.transcripts.scan()
        by_sid = {}
        for rec in self.transcripts.summaries().values():
            sid = rec.get("session_id")
            if sid:
                prev = by_sid.get(sid)
                if prev is None or rec["mtime"] > prev["mtime"]:
                    by_sid[sid] = rec

        proc_by_sid, loose = {}, []
        for p in procs.values():
            if p["kind"] == "infra":    # never listed
                continue
            sid = p.get("session_id")
            if not sid and p.get("transcript"):
                sid = os.path.basename(p["transcript"])[:-len(".jsonl")]
            if sid:
                sid = sid.lower()
                cur = proc_by_sid.get(sid)
                if cur is None or (p.get("lstart") or 0) > \
                        (cur.get("lstart") or 0):
                    proc_by_sid[sid] = p
            else:
                loose.append(p)

        # Bare interactive `claude`: lsof cwd + newest transcript, launch-time
        # tie-break (oldest process claims first so a transient newcomer
        # can't steal a long-lived session's transcript).
        claimed = set(proc_by_sid)
        loose.sort(key=lambda p: p.get("lstart") or 0)
        for p in loose:
            cwd = self.procs.cwd_of(p["pid"])
            if not cwd:
                continue
            cands = [r for r in by_sid.values()
                     if r.get("cwd") == cwd
                     and r["session_id"] not in claimed]
            if not cands:
                continue
            ls = p.get("lstart") or 0
            fresh = [r for r in cands if (r.get("started") or 0) >= ls - 120]
            if fresh:
                pick = min(fresh, key=lambda r: (r.get("started") or 0) - ls)
            else:
                pick = max(cands, key=lambda r: r["mtime"])
            proc_by_sid[pick["session_id"]] = p
            claimed.add(pick["session_id"])

        active = {sid for sid, r in by_sid.items()
                  if now - r["mtime"] <= self.gone_keep_s}
        rows = []
        for sid in set(proc_by_sid) | active | set(self._track):
            rec = by_sid.get(sid)
            p = proc_by_sid.get(sid)
            tr = self._track.get(sid)
            if tr is None:
                if rec is None and p is None:
                    continue
                tr = {"status": None, "since": now, "pending": None,
                      "gone_since": None, "had_pid": False}
                self._track[sid] = tr
            if p:
                tr["had_pid"] = True
                tr["gone_since"] = None
            elif tr["gone_since"] is None:
                tr["gone_since"] = now
            if p is None and sid not in active and \
                    now - (tr["gone_since"] or now) > self.gone_keep_s:
                self._track.pop(sid, None)      # gone: kept 60s, then dropped
                continue
            if rec is None and p is None:
                self._track.pop(sid, None)
                continue

            raw, pt = self._raw_status(rec, p, tr, now)
            status = self._debounce(sid, tr, raw, now)
            rows.append(self._row(sid, rec, p, tr, status, pt, now))

        rows.sort(key=lambda r: -(r["last_activity"] or 0))
        needs = [{"session_id": r["session_id"], "reason": r["status"],
                  "since": r["status_since"]}
                 for r in rows
                 if r["status"] in NEEDS_RANK and not r["dismissed"]]
        needs.sort(key=lambda n: (NEEDS_RANK[n["reason"]], n["since"] or 0))

        colls = self._collisions(rows, by_sid, now)

        working = [r for r in rows
                   if r["status"] in ("working", "pending_tool")]
        tiers = [MODEL_TIERS.index(r["model_family"]) for r in working
                 if r["model_family"] in MODEL_TIERS]
        # Guard-coverage counts. routed_now = the user wants routing AND it's
        # installed on disk this cycle. Only definite verdicts count (unknown never
        # does): unguarded = live agents started before the guard while routing is
        # on (restart them to protect them); pinned = live agents still guarded by a
        # proxy the user has since turned off (they stay protected until restarted).
        routed_now = bool(self.state.routed and self.state.routing_now)
        live = [r for r in rows if r.get("pid") and r.get("kind") != "infra"
                and r["status"] != "gone"]
        unguarded = sum(1 for r in live if r.get("guarded") is False) \
            if routed_now else 0
        pinned = sum(1 for r in live if r.get("guarded") is True) \
            if not routed_now else 0
        summary = {"working": len(working), "needs_you": len(needs),
                "done_today": self._done_today,
                "top_tier": MODEL_TIERS[max(tiers)] if tiers else None,
                "unguarded": unguarded, "pinned": pinned}

        versions = sorted({(by_sid.get(r["session_id"]) or {}).get("version")
                           for r in rows} - {None})
        snap = {"sessions": rows, "needs_you": needs, "collisions": colls,
                "summary": summary, "events": list(self._events),
                "meta": {"lsof_ok": self.procs.lsof_ok,
                         "parse_errors": self.transcripts.parse_errors,
                         "claude_versions": versions}}
        with self.lock:
            self._snap = snap

    def _raw_status(self, rec, p, tr, now):
        """Undebounced status + pending-tool info for this cycle."""
        prev = tr.get("status")
        if p is None:
            if prev in ("working", "pending_tool") and tr.get("had_pid"):
                return "failed", None   # process died mid-work
            if prev == "failed":
                return "failed", None   # stays failed for its keep window
            return "gone", None
        if p.get("stopped"):
            # SIGSTOP-suspended: the process is frozen, not working and not
            # erroring. Report it honestly as paused BEFORE the stall/api-error
            # inference below — a frozen turn writes nothing, which would
            # otherwise read as "no response — possible API error".
            return "paused", None
        if rec is None:
            return "working", None      # process up, transcript not seen yet
        # A trailing API error surfaces IMMEDIATELY — before the freshness gate
        # below — because an active retry storm keeps writing api_error lines
        # that refresh mtime, which would otherwise mask the fault as "working".
        # Cleared the moment a real reply lands (recovery) or a new turn starts.
        if rec.get("api_retrying") or rec.get("api_error_msg"):
            return "failed", None
        age = now - rec["mtime"]
        open_tools = rec.get("open_tools") or {}
        # A COMPLETED turn is terminal REGARDLESS of freshness — the same reason
        # the API-error check above pre-empts the gate. The final assistant
        # message refreshes the transcript mtime, so a turn that JUST ended still
        # reads as < working_s old; the freshness gate below would then keep
        # mislabelling it "working" for the first ~10s after it actually
        # finished — the "still shows running when it's already done" lag. An
        # end_turn with no tool left open IS the completion signal: classify it
        # now (done / failed / asking), only aging to "idle" once it has been
        # quiet past idle_s. The next real user prompt resets last_stop to None,
        # so a new turn correctly reads as working again.
        if rec.get("last_stop") == "end_turn" and not open_tools:
            return ("idle", None) if age > self.idle_s \
                else self._finished_status(rec)
        if age < self.working_s:
            return "working", None
        if age > self.idle_s:
            return "idle", None
        # stalled between working_s and idle_s. "pending_tool" means a tool call
        # is genuinely OPEN — a tool_use with no matching tool_result yet — i.e.
        # actually awaiting approval or a slow run. Do NOT infer it from
        # last_stop=="tool_use": that stays set through the think-gap AFTER a
        # tool's result comes back, so on auto-accept it produced a phantom
        # "waiting to edit X" from the stale last_tool. Require an open tool.
        if open_tools:
            tool = max(open_tools.values(),
                       key=lambda t: t.get("since") or 0)
            name = tool.get("name") or "?"
            pt = {"name": name, "detail": tool.get("detail"),
                  "since": tool.get("since") or rec["mtime"]}
            if name == "AskUserQuestion":
                return "asking", pt     # a question is waiting, not a tool
            if name in GRACE_TOOLS and \
                    now - (pt["since"] or now) < self.tool_grace_s:
                return "working", None  # slow tool, still within grace
            return "pending_tool", pt
        return "working", None          # prompt sent, reply not started

    def _finished_status(self, rec):
        """Classify a turn that has ENDED (stop_reason end_turn, no tool still
        open): "done" normally, or failed/asking when the final assistant text
        says so. Split out of _raw_status so the completion signal can pre-empt
        the freshness gate there instead of trailing it."""
        if rec.get("trailing_error") or rec.get("last_synth"):
            return "failed", None
        lines = [ln.strip().lower()
                 for ln in (rec.get("last_text") or "").splitlines()]
        if any(ln.startswith("failed:") for ln in lines):
            return "failed", None
        if any(ln.startswith("needs input:") for ln in lines):
            return "asking", None
        return "done", None             # "result:" and everything else

    def _debounce(self, sid, tr, raw, now):
        """Publish a transition only after 2 scan cycles agree."""
        prev = tr["status"]
        if prev is None:
            tr["status"], tr["since"], tr["pending"] = raw, now, None
            return raw
        if raw == prev:
            tr["pending"] = None
            return prev
        cand, n = tr["pending"] or (None, 0)
        n = n + 1 if cand == raw else 1
        if n < 2:
            tr["pending"] = (raw, n)
            return prev
        tr["status"], tr["since"], tr["pending"] = raw, now, None
        self._events.append({"t": now, "session_id": sid,
                             "from": prev, "to": raw})
        if raw == "done":
            self._done_today += 1
        self._dismissed.discard(sid)    # dismissal lasts until a transition
        return raw

    def _scan_proxy_clients(self, now):
        """Latch which pids currently hold an ESTABLISHED TCP connection to the
        proxy port — hard proof they're routed through the guard. One lsof over
        network fds (no TCC: these are sockets, not files). A client's `n` line
        ends `->127.0.0.1:<port>`; the daemon's own accept-side fds point the other
        way and are naturally excluded. Positive-proof only: absence never means
        unguarded (an idle agent has no live connection between keep-alives)."""
        port = self.state.proxy_port
        try:
            r = subprocess.run(
                ["lsof", "-nP", f"-iTCP@127.0.0.1:{port}",
                 "-sTCP:ESTABLISHED", "-Fpn"],
                capture_output=True, text=True, timeout=10)
        except Exception as e:  # noqa: BLE001
            log(f"lsof proxy-client scan error: {e}")
            return
        pid = None
        suffix = f"->127.0.0.1:{port}"
        for ln in r.stdout.splitlines():
            if ln.startswith("p"):
                try:
                    pid = int(ln[1:])
                except ValueError:
                    pid = None
            elif ln.startswith("n") and pid is not None and \
                    ln.rstrip().endswith(suffix):
                self._proxy_seen[pid] = now

    def _guarded_of(self, p):
        """Per-agent guard truth: True (proven or presumed routed), False (started
        before the guard), or None (unknown — no proc, or launch too close to a
        route flip to call). A live proxy connection is proof; otherwise fall back
        to whether routing was installed at the process's launch time."""
        if not p or not p.get("pid"):
            return None
        if p["pid"] in self._proxy_seen:
            return True
        return guarded_at(self.state.cfg, p.get("lstart"))

    def _row(self, sid, rec, p, tr, status, pt, now):
        rec = rec or {}
        cwd = rec.get("cwd")
        if not cwd and p and p["kind"] == "interactive":
            cwd = self.procs.cwd_of(p["pid"])
        model = rec.get("model")
        git_root = self._git_root_of(cwd)
        tty = p.get("tty") if p else None
        if p:
            kind = p["kind"]
        else:
            kind = ("background" if rec.get("session_kind") == "bg"
                    else "interactive")
        return {
            "session_id": sid,
            "pid": p["pid"] if p else None,
            "kind": kind,
            "model": model,
            "model_family": _model_family(model),
            "effort": rec.get("effort_cmd") or self._effort_of(cwd, git_root),
            "context": self._ctx_tag_of(cwd, git_root, _model_family(model)),
            "project_name": os.path.basename(cwd) if cwd else None,
            "cwd": cwd,
            "git_root": git_root,
            "git_branch": rec.get("git_branch") or _git_branch_of(git_root),
            "title": rec.get("title") or rec.get("agent_name"),
            "last_prompt": rec.get("last_prompt"),
            "status": status,
            "status_since": tr["since"],
            "activity": _activity_for(rec, status, self.api_stall_s),
            "pending_tool": pt if status in ("pending_tool", "asking")
            else None,
            "tty": tty,
            "focusable": bool(p and p["kind"] == "interactive" and tty),
            "guarded": self._guarded_of(p),
            "last_activity": rec.get("mtime"),
            "started": (p.get("lstart") if p else None) or rec.get("started"),
            "ticks": {"tools_done": rec.get("tools_done", 0),
                      "files": len(rec.get("files") or ()),
                      "errors": rec.get("errors", 0),
                      "subagents": rec.get("subagents", 0)},
            "health": self._health(rec, status, tr, now),
            "dismissed": sid in self._dismissed,
        }

    def _health(self, rec, status, tr, now):
        if status == "paused":
            return {"level": "ok", "reasons": []}   # user-suspended, not a fault
        reasons = []
        ring = list(rec.get("err_ring") or ())
        errs = sum(1 for e in ring if e)
        if errs >= 3:
            reasons.append(f"{errs} failed tool calls in last "
                           f"{len(ring)} results")
        if status == "pending_tool" and \
                now - (tr["since"] or now) > self.pending_warn_s:
            reasons.append(
                f"tool pending over {int(self.pending_warn_s // 60)} min")
        if status == "working":
            stalled = _stall_secs(rec, self.api_stall_s)
            if stalled is not None:
                reasons.append(f"no model response for {stalled}s — "
                               "possible API error or network stall")
            base = max(rec.get("turn_done_ts") or 0,
                       rec.get("last_user_ts") or 0,
                       rec.get("started") or 0) or tr["since"]
            if now - base > self.working_warn_s:
                reasons.append(f"no completed turn in over "
                               f"{int(self.working_warn_s // 60)} min")
        return {"level": "warn" if reasons else "ok", "reasons": reasons}

    def _collisions(self, rows, by_sid, now):
        groups = defaultdict(list)
        for r in rows:
            if r["git_root"] and r["status"] not in ("idle", "gone"):
                groups[r["git_root"]].append(r)
        out = []
        for root, grp in sorted(groups.items()):
            if len(grp) < 2:
                continue
            fcount = defaultdict(int)
            for r in grp:
                rec = by_sid.get(r["session_id"]) or {}
                files = {fp for t, fp in (rec.get("recent_edits") or ())
                         if now - t <= AGENT_EDIT_WINDOW_S}
                for fp in files:
                    fcount[fp] += 1
            shared = sorted(fp for fp, c in fcount.items() if c >= 2)
            out.append({"git_root": root,
                        "session_ids": [r["session_id"] for r in grp],
                        "level": "file" if shared else "repo",
                        "files": shared})
        return out

    def _effort_of(self, cwd, git_root):
        """A session's reasoning effort, resolved from the settings cascade
        rooted at its project: user < project < project-local (later wins),
        mirroring Claude Code's own precedence. Returns the compact badge label
        ("high", "xhigh", "ultra", …) or None. Read-only — never writes."""
        def _pick(d):
            if isinstance(d, dict):
                return d.get("effortLevel") or d.get("reasoningEffort")
            return None

        val = _pick(self._settings.get(CLAUDE_SETTINGS))
        base = git_root or cwd
        if base:
            for name in ("settings.json", "settings.local.json"):
                v = _pick(self._settings.get(os.path.join(base, ".claude", name)))
                if v:
                    val = v
        return _norm_effort(val)

    def _ctx_tag_of(self, cwd, git_root, family):
        """Context-window variant tag (e.g. "1M") for a session. The transcript's
        model id doesn't carry it — only the configured model does ("opus[1m]") —
        so read that from the same settings cascade. Applied only when the
        configured model's family matches the session's running family, so a
        haiku session is never mis-tagged with an opus default's window."""
        def _model(d):
            return d.get("model") if isinstance(d, dict) else None
        mid = _model(self._settings.get(CLAUDE_SETTINGS))
        base = git_root or cwd
        if base:
            for name in ("settings.json", "settings.local.json"):
                m = _model(self._settings.get(os.path.join(base, ".claude", name)))
                if m:
                    mid = m
        if not mid or "[" not in mid:
            return None
        fam, _, rest = str(mid).lower().partition("[")
        if not (family and family != "other" and family in fam):
            return None                 # unknown family or a different model
        tag = rest.split("]", 1)[0].strip()
        return tag.upper() or None      # "1m" -> "1M"

    def _git_root_of(self, cwd):
        if not cwd:
            return None
        if cwd in self._git_cache:
            return self._git_cache[cwd]
        # An agent working inside Desktop/Documents/Photos/Music/etc. still gets
        # a row, but we do NOT walk its tree looking for .git — the first stat
        # there fires a TCC prompt. Cache the skip so we only decide once.
        if _is_protected(cwd):
            self._git_cache[cwd] = None
            return None
        root, d = None, cwd
        while True:
            if _is_protected(d):
                break               # never cross into a gated folder mid-walk
            if os.path.exists(os.path.join(d, ".git")):
                root = d
                break
            nd = os.path.dirname(d)
            if nd == d:
                break
            d = nd
        self._git_cache[cwd] = root
        return root

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self._snap))

    # -- services for dispatch() ------------------------------------------ #
    def dismiss(self, session_id, on=True):
        with self.lock:
            if on:
                self._dismissed.add(session_id)
            else:
                self._dismissed.discard(session_id)
        return {"ok": True, "dismissed": bool(on)}

    def focus(self, session_id):
        """Bring the session's terminal tab frontmost. Never raises."""
        if IS_WINDOWS:
            # No osascript/tmux tab-raising analog on Windows (and no tty to
            # match a tab by). Offer the resume command as the fallback.
            return {"ok": False, "fallback": f"claude --resume {session_id}"}
        try:
            with self.lock:
                sess = next((s for s in self._snap["sessions"]
                             if s["session_id"] == session_id), None)
            if sess is None:
                return {"ok": False, "error": "unknown session",
                        "fallback": f"claude --resume {session_id}"}
            tty = sess.get("tty")
            if not sess.get("focusable") or not tty:
                return {"ok": False,
                        "fallback": f"claude --resume {session_id}"}
            dev = tty if tty.startswith("/dev/") else "/dev/" + tty
            script = (
                'tell application "Terminal"\n'
                '  repeat with w in windows\n'
                '    repeat with t in tabs of w\n'
                f'      if tty of t is "{dev}" then\n'
                '        set selected of t to true\n'
                '        set index of w to 1\n'
                '        activate\n'
                '        return "ok"\n'
                '      end if\n'
                '    end repeat\n'
                '  end repeat\n'
                'end tell\n'
                'return "notfound"')
            try:
                r = subprocess.run(["osascript", "-e", script],
                                   capture_output=True, text=True, timeout=15)
                if r.returncode == 0 and "ok" in (r.stdout or ""):
                    return {"ok": True, "via": "terminal"}
            except Exception:  # noqa: BLE001
                pass
            # tmux fallback: match the pane by its tty
            try:
                r = subprocess.run(
                    ["tmux", "list-panes", "-a", "-F",
                     "#{pane_tty} #{session_name}:#{window_index}"
                     ".#{pane_index}"],
                    capture_output=True, text=True, timeout=10)
                if r.returncode == 0:
                    for ln in r.stdout.splitlines():
                        ptty, _, target = ln.partition(" ")
                        if ptty.strip() == dev and target.strip():
                            subprocess.run(
                                ["tmux", "switch-client", "-t",
                                 target.strip()],
                                capture_output=True, timeout=10)
                            return {"ok": True, "via": "tmux"}
            except Exception:  # noqa: BLE001
                pass
            # iTerm2 branch — coded but untested (not installed here)
            if os.path.isdir("/Applications/iTerm.app"):
                it = (
                    'tell application "iTerm2"\n'
                    '  repeat with w in windows\n'
                    '    repeat with tb in tabs of w\n'
                    '      repeat with sn in sessions of tb\n'
                    f'        if tty of sn is "{dev}" then\n'
                    '          select tb\n'
                    '          select sn\n'
                    '          activate\n'
                    '          return "ok"\n'
                    '        end if\n'
                    '      end repeat\n'
                    '    end repeat\n'
                    '  end repeat\n'
                    'end tell\n'
                    'return "notfound"')
                try:
                    r = subprocess.run(["osascript", "-e", it],
                                       capture_output=True, text=True,
                                       timeout=15)
                    if r.returncode == 0 and "ok" in (r.stdout or ""):
                        return {"ok": True, "via": "iterm2"}
                except Exception:  # noqa: BLE001
                    pass
            return {"ok": False, "fallback": f"claude --resume {session_id}"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e),
                    "fallback": f"claude --resume {session_id}"}


# --------------------------------------------------------------------------- #
# Usage (reads Claude Code transcripts)
# --------------------------------------------------------------------------- #
class UsageIndex:
    def __init__(self, state):
        self.state = state
        self.lock = threading.Lock()
        self._mtime = {}
        self._rows = {}
        self.snapshot = self._empty()

    @staticmethod
    def _empty():
        return {"session": {"tokens": 0, "input": 0, "output": 0, "cache": 0,
                            "cost": 0.0, "msgs": 0, "since": None},
                "today": {"tokens": 0, "cost": 0.0},
                "week": {"tokens": 0, "cost": 0.0},
                "pace": {"tokens_per_active_hr": 0, "active_hrs": 0,
                         "projected_week_tokens": 0, "projected_week_cost": 0.0,
                         "live_tpm": 0},
                "headroom": {"used_week_tokens": 0, "plan_week_tokens": 0,
                             "pct": 0.0},
                "byModel": [], "series": []}

    def loop(self, interval=8):
        while not self.state.stop.is_set():
            try:
                self.refresh()
            except Exception as e:  # noqa: BLE001
                log(f"usage refresh error: {e}")
            waited = 0.0
            while waited < interval and not self.state.stop.is_set():
                time.sleep(0.5)
                waited += 0.5

    def _scan(self):
        rows = []
        if not os.path.isdir(CLAUDE_PROJECTS):
            return rows
        for root, _d, files in os.walk(CLAUDE_PROJECTS):
            for name in files:
                if not name.endswith(".jsonl"):
                    continue
                path = os.path.join(root, name)
                try:
                    mt = os.path.getmtime(path)
                except OSError:
                    continue
                if self._mtime.get(path) != mt:
                    self._mtime[path] = mt
                    self._rows[path] = self._parse(path)
                rows.extend(self._rows.get(path, ()))
        return rows

    @staticmethod
    def _parse(path):
        out = []
        try:
            with open(path, "r", errors="replace") as f:
                for line in f:
                    if '"usage"' not in line:
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(o, dict):
                        continue
                    msg = o.get("message")
                    if not isinstance(msg, dict):
                        continue
                    u = msg.get("usage")
                    if not isinstance(u, dict):
                        continue
                    epoch = _parse_ts(o.get("timestamp"))
                    if epoch is None:
                        continue
                    out.append((epoch, msg.get("model") or "unknown",
                                int(u.get("input_tokens", 0) or 0),
                                int(u.get("output_tokens", 0) or 0),
                                int(u.get("cache_creation_input_tokens", 0) or 0),
                                int(u.get("cache_read_input_tokens", 0) or 0),
                                o.get("sessionId") or ""))
        except OSError:
            pass
        return out

    def refresh(self):
        rows = self._scan()
        now = datetime.now().astimezone()
        now_e = now.timestamp()
        today_start = now.replace(hour=0, minute=0, second=0,
                                  microsecond=0).timestamp()
        week_start = (now - timedelta(days=now.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0).timestamp()
        elapsed_frac = max((now_e - week_start) / (7 * 86400.0), 1e-3)

        snap = self._empty()
        bm_tok = defaultdict(int)
        bm_cost = defaultdict(float)
        active = set()
        s_tok = defaultdict(int)
        s_cost = defaultdict(float)
        live = 0
        latest_sid, latest_e = None, -1.0
        for r in rows:
            if r[0] > latest_e:
                latest_e, latest_sid = r[0], r[6]

        for epoch, model, ti, to, cw, cr, sid in rows:
            if model.startswith("<"):
                continue
            total = ti + to + cw + cr
            cost = _cost(model, ti, to, cw, cr)
            if epoch >= week_start:
                snap["week"]["tokens"] += total
                snap["week"]["cost"] += cost
                active.add(int(epoch // 3600))
                bm_tok[model] += total
                bm_cost[model] += cost
            if epoch >= today_start:
                snap["today"]["tokens"] += total
                snap["today"]["cost"] += cost
            if epoch >= now_e - 60:
                live += total
            day = datetime.fromtimestamp(epoch).astimezone().strftime("%Y-%m-%d")
            s_tok[day] += total
            s_cost[day] += cost
            if sid == latest_sid:
                s = snap["session"]
                s["tokens"] += total
                s["input"] += ti
                s["output"] += to
                s["cache"] += cw + cr
                s["cost"] += cost
                s["msgs"] += 1
                if s["since"] is None or epoch < s["since"]:
                    s["since"] = epoch

        ahrs = len(active)
        snap["pace"] = {
            "tokens_per_active_hr": int(snap["week"]["tokens"] / ahrs) if ahrs else 0,
            "active_hrs": ahrs,
            "projected_week_tokens": int(snap["week"]["tokens"] / elapsed_frac),
            "projected_week_cost": round(snap["week"]["cost"] / elapsed_frac, 2),
            "live_tpm": live}
        plan = max(self.state.plan_week_tokens, 1)
        snap["headroom"] = {"used_week_tokens": snap["week"]["tokens"],
                            "plan_week_tokens": plan,
                            "pct": round(100.0 * snap["week"]["tokens"] / plan, 1)}
        tot = max(sum(bm_tok.values()), 1)
        snap["byModel"] = sorted(
            ({"model": m, "tokens": bm_tok[m], "cost": round(bm_cost[m], 2),
              "pct": round(100.0 * bm_tok[m] / tot, 1)} for m in bm_tok),
            key=lambda x: -x["tokens"])[:6]
        series = []
        for i in range(6, -1, -1):
            day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            series.append({"day": day, "tokens": s_tok.get(day, 0),
                           "cost": round(s_cost.get(day, 0.0), 2)})
        snap["series"] = series
        for k in ("today", "week"):
            snap[k]["cost"] = round(snap[k]["cost"], 2)
        snap["session"]["cost"] = round(snap["session"]["cost"], 2)
        with self.lock:
            self.snapshot = snap

    def get(self):
        with self.lock:
            return json.loads(json.dumps(self.snapshot))


def _parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _cost(model, ti, to, cw, cr):
    pin, pout, pcw, pcr = PRICING.get(model, DEFAULT_PRICE)
    return (ti * pin + to * pout + cw * pcw + cr * pcr) / 1_000_000.0


# --------------------------------------------------------------------------- #
# Real plan usage — driven via `claude -p /usage` (Claude Code does the auth;
# we never read the token). This mirrors the Settings → Usage page exactly.
# --------------------------------------------------------------------------- #
def find_claude():
    p = shutil.which("claude")
    if p:
        return p
    if IS_WINDOWS:
        for c in (os.path.join(HOME, ".claude", "local", "claude.exe"),
                  os.path.join(HOME, ".claude", "local", "claude.cmd")):
            if os.path.exists(c):
                return c
        return None
    for c in ("/opt/homebrew/bin/claude", "/usr/local/bin/claude",
              os.path.join(HOME, ".claude", "local", "claude"),
              "/usr/bin/claude"):
        if os.path.exists(c):
            return c
    return None


_RESET_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}


def _parse_reset_at(s):
    """Turn a /usage reset stamp — e.g. 'Jul 4 at 11:39pm (Asia/Tehran)' — into
    an epoch so the front-ends can render a live *relative* time. The year is
    omitted in the source, so we pick the nearest future one. Returns None if it
    doesn't parse; callers then fall back to the (timezone-stripped) text."""
    if not s:
        return None
    m = re.match(r"\s*([A-Za-z]{3})\s+(\d{1,2})\s+at\s+"
                 r"(\d{1,2}):(\d{2})\s*([ap]m)\s*(?:\(([^)]+)\))?", s, re.I)
    if not m:
        return None
    mon = _RESET_MONTHS.get(m.group(1).lower())
    if not mon:
        return None
    day, hour, minute = int(m.group(2)), int(m.group(3)), int(m.group(4))
    if m.group(5).lower() == "pm" and hour != 12:
        hour += 12
    elif m.group(5).lower() == "am" and hour == 12:
        hour = 0
    tz = None
    if m.group(6) and ZoneInfo is not None:
        try:
            tz = ZoneInfo(m.group(6).strip())
        except Exception:  # noqa: BLE001 — unknown tz → treat as local
            tz = None
    now = datetime.now(tz)
    try:
        dt = datetime(now.year, mon, day, hour, minute, tzinfo=tz)
    except ValueError:
        return None
    if (dt - now).total_seconds() < -86400:   # already well past → next year
        try:
            dt = dt.replace(year=now.year + 1)
        except ValueError:
            return None
    return dt.timestamp()


def parse_usage(out):
    def pct(label):
        m = re.search(label + r"\s*(\d+)%\s*used(?:\s*·\s*resets\s*([^\n]+))?",
                      out)
        if not m:
            return None, None
        return int(m.group(1)), (m.group(2).strip() if m.group(2) else None)
    sp, sr = pct(r"Current session:")
    wp, wr = pct(r"Current week \(all models\):")
    fp, fr = pct(r"Current week \(Fable\):")
    if sp is None and wp is None:
        return {"ok": False, "error": "could not parse /usage output"}
    res = {"ok": True, "updated": time.time(),
           "session": {"pct": sp, "resets": sr, "resets_at": _parse_reset_at(sr)},
           "week": {"pct": wp, "resets": wr, "resets_at": _parse_reset_at(wr)},
           "fable": {"pct": fp, "resets": fr, "resets_at": _parse_reset_at(fr)}}
    m = re.search(r"Last 24h\s*·\s*(\d+)\s*requests\s*·\s*(\d+)\s*sessions", out)
    if m:
        res["last24h"] = {"requests": int(m.group(1)),
                          "sessions": int(m.group(2))}
    return res


# A hermetic sandbox for every `claude -p /usage`. This is THE fix for the
# unpredictable macOS Photos / Apple Music / Contacts permission prompts: at
# startup claude captures a "shell snapshot" by sourcing the user's shell rc
# (~/.zshrc, ~/.zprofile, …), and that rc pulls in tools / shell integrations
# that touch those data stores — the TCC prompt is then attributed to Tower,
# because Tower spawned claude, every 60s, at no predictable moment. We remove
# BOTH trigger paths for /usage: point zsh/sh/bash at an EMPTY rc (so nothing is
# sourced) and load ZERO MCP servers (an MCP server can reach Contacts/Photos
# too). HOME is left intact so claude still finds its own auth under ~/.claude.
# Verified: /usage returns byte-identical output and the tell-tale rc-sourcing
# side effect ("Shell cwd was reset…") disappears.
USAGE_NORC_DIR = os.path.join(CONFIG_DIR, "norc")          # empty ZDOTDIR
USAGE_MCP_FILE = os.path.join(CONFIG_DIR, "empty-mcp.json")  # zero MCP servers


def _ensure_usage_sandbox():
    """Create the empty ZDOTDIR + empty MCP config once; keep the rc dir clean.
    Windows has no TCC and no shell-rc sourcing to neutralise, so only the empty
    MCP config (still passed to --mcp-config) is created there."""
    try:
        if not IS_WINDOWS:
            os.makedirs(USAGE_NORC_DIR, exist_ok=True)
            for n in (".zshrc", ".zshenv", ".zprofile", ".zlogin", ".profile"):
                p = os.path.join(USAGE_NORC_DIR, n)
                if os.path.lexists(p):
                    os.remove(p)                # never let an rc sneak back in
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if not os.path.exists(USAGE_MCP_FILE):
            with open(USAGE_MCP_FILE, "w") as f:
                f.write('{"mcpServers":{}}')
    except OSError as e:  # noqa: BLE001
        log(f"usage sandbox setup failed: {e}")


def _claude_env():
    """Env for a hermetic `claude -p /usage` (see USAGE_NORC_DIR above):
    - strip Claude-Code *nesting* vars (else a nested /usage prints run-stats
      instead of the usage report),
    - neutralise every shell's rc sourcing — the Photos/Music/Contacts TCC
      trigger — via an empty ZDOTDIR and blanked ENV/BASH_ENV,
    - keep a sane PATH (helpers) and HOME (claude's own auth in ~/.claude)."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("CLAUDE_CODE") and k != "CLAUDECODE"
           and k != "CLAUDE_EFFORT"}
    _ensure_usage_sandbox()
    if IS_WINDOWS:
        # No shell-rc sourcing on Windows, so nothing to neutralise; keep the
        # inherited PATH (it already resolves claude/node). Separator is ';'.
        return env
    env["ZDOTDIR"] = USAGE_NORC_DIR     # zsh sources $ZDOTDIR/.z* → none exist
    env["ENV"] = ""                     # sh: no startup file
    env["BASH_ENV"] = ""                # bash non-interactive: no startup file
    extra = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
    have = env.get("PATH", "").split(os.pathsep)
    env["PATH"] = os.pathsep.join([p for p in extra if p not in have] + have)
    return env


def fetch_plan():
    claude = find_claude()
    if not claude:
        return {"ok": False, "error": "claude CLI not found"}
    env = _claude_env()
    argv = [claude, "-p", "/usage",
            "--strict-mcp-config", "--mcp-config", USAGE_MCP_FILE]
    # A Windows `claude` on PATH is usually a `claude.cmd` npm shim; CreateProcess
    # can't exec a batch file directly (WinError 193), so run it through cmd /c.
    if IS_WINDOWS and claude.lower().endswith((".cmd", ".bat")):
        argv = ["cmd", "/c"] + argv
    last = {"ok": False, "error": "could not parse /usage output"}
    # `claude -p /usage` occasionally returns a run-stats blob instead of the
    # usage report; retry a few times so one bad response doesn't fail the cycle.
    for _ in range(3):
        try:
            r = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL, capture_output=True,
                text=True, timeout=90, env=env,
                cwd=CONFIG_DIR)     # neutral cwd: never let claude scan a
                                    # protected folder it happened to inherit

            res = parse_usage((r.stdout or "") + "\n" + (r.stderr or ""))
            if res.get("ok"):
                return res
            last = res
        except subprocess.TimeoutExpired:
            last = {"ok": False, "error": "claude /usage timed out"}
        except Exception as e:  # noqa: BLE001
            last = {"ok": False, "error": str(e)}
        time.sleep(0.6)
    return last


def plan_loop(state, interval=60):
    while not state.stop.is_set():
        if not state.plan_enabled:
            # Live plan-fetching off → never run claude (no Photos/Music prompts).
            with state.lock:
                state.plan = {"ok": False, "disabled": True}
            waited = 0.0
            while waited < 2.0 and not state.stop.is_set():
                if state._refreshplan:
                    state._refreshplan = False
                    break
                time.sleep(0.25)
                waited += 0.25
            continue
        if not state.claude_allowed():
            # Same fail-closed gate as the proxy: `claude -p /usage` IS a Claude
            # request, so we never run it while you're off-country or the net is
            # unstable. Keep showing the last good reading (flagged "gated") so
            # the UI stays honest instead of blanking.
            with state.lock:
                keep = state.plan if (state.plan and state.plan.get("ok")) else {}
                state.plan = {**keep, "ok": keep.get("ok", False),
                              "gated": True, "refreshing": False,
                              "gate_reason": "net" if not state.net_ok else "geo",
                              "checked": time.time()}
            waited = 0.0
            while waited < 2.0 and not state.stop.is_set():
                if state._refreshplan:
                    state._refreshplan = False
                    break
                time.sleep(0.25)
                waited += 0.25
            continue
        with state.lock:
            if state.plan and state.plan.get("ok"):
                state.plan = {**state.plan, "refreshing": True}
        res = fetch_plan()
        with state.lock:
            if res.get("ok"):
                state.plan = res                       # fresh; flags cleared
            elif state.plan and state.plan.get("ok"):
                state.plan = {**state.plan, "refreshing": False,
                              "error": res.get("error")}
            else:
                state.plan = {"ok": False, "refreshing": False,
                              "error": res.get("error"), "checked": time.time()}
        log(f"plan fetch: {'ok' if res.get('ok') else res.get('error')}")
        waited = 0.0
        while waited < interval and not state.stop.is_set():
            if state._refreshplan:
                state._refreshplan = False
                break
            time.sleep(0.5)
            waited += 0.5


# --------------------------------------------------------------------------- #
# Routing via settings.json (NEVER the shell) + reset + keep-awake
# --------------------------------------------------------------------------- #
def _read_settings():
    try:
        with open(CLAUDE_SETTINGS) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


# Retry-tolerance env we install alongside the proxy so a *blocked* request
# (503 from the guard) or a real outage keeps Claude Code in its native
# "Retrying in Ns · attempt x/y" spinner instead of erroring the turn. The
# watchdog unlocks up to ~300 attempts (~3h of backoff), so the agent stays
# PENDING across a whole network switch and resumes on its own when the guard
# clears. Installed non-destructively (setdefault) and removed on route_off only
# if the value is still ours — a user-set value is left untouched.
RETRY_ENV = {
    "CLAUDE_CODE_RETRY_WATCHDOG": "1",     # unlock the long retry budget
    "CLAUDE_CODE_MAX_RETRIES": "300",      # attempts before the turn finally errors
}


def routing_installed():
    env = _read_settings().get("env") or {}
    v = str(env.get("HTTPS_PROXY", "") or env.get("https_proxy", ""))
    return "127.0.0.1" in v


# Routing timeline: a small persisted history of on/off transitions (wall-clock),
# so we can later ask "was the guard installed when THIS Claude process launched?"
# and honestly badge sessions started before the guard as unguarded. ps `lstart`
# resolves to ~1s, so a launch within ROUTE_EDGE_TOLERANCE_S of a flip is 'unknown',
# never guessed.
ROUTE_LOG_MAX = 40
ROUTE_EDGE_TOLERANCE_S = 5.0


def note_route_change(state, installed, now=None):
    """Record a routing transition when the installed state actually changes.
    Called from the route command, startup, shutdown, and build_state — the
    build_state hook self-corrects the record after an external settings edit or a
    kill -9 (a stranded proxy env is honestly logged as still-installed, which is
    exactly what those sessions captured). Cheap in steady state: no change → no
    write. Also refreshes state.routing_now (the file-truth the agent monitor reads
    without its own settings read)."""
    installed = bool(installed)
    now = time.time() if now is None else now
    with state.lock:
        state.routing_now = installed
        rlog = state.cfg.setdefault("route_log", [])
        if rlog and bool(rlog[-1].get("installed")) == installed:
            return
        rlog.append({"t": now, "installed": installed})
        del rlog[:-ROUTE_LOG_MAX]
    save_config(state.cfg)


def guarded_at(cfg, ts):
    """Was routing installed at wall-clock time `ts` (a process launch)? Returns
    the last transition's state at or before ts; None when there's no covering
    record or ts lands within ROUTE_EDGE_TOLERANCE_S of a transition (lstart is too
    coarse to call it either way). None means 'unknown', never counted as un/guarded."""
    if ts is None:
        return None
    rlog = cfg.get("route_log") or []
    verdict = None
    for e in rlog:
        t = e.get("t")
        if t is None:
            continue
        if abs(t - ts) <= ROUTE_EDGE_TOLERANCE_S:
            return None
        if t <= ts:
            verdict = bool(e.get("installed"))
    return verdict


def route_on(proxy_port):
    # SAFETY: never point Claude Code at a proxy that isn't actually accepting
    # connections. Writing a dead proxy into settings.json silently kills every
    # Claude API request (this is the bug that froze the earlier session).
    if not proxy_is_up(proxy_port):
        log(f"route_on refused: nothing listening on 127.0.0.1:{proxy_port}")
        return False
    url = f"http://127.0.0.1:{proxy_port}"
    data = _read_settings()
    if os.path.exists(CLAUDE_SETTINGS) and not os.path.exists(SETTINGS_BAK):
        try:
            shutil.copyfile(CLAUDE_SETTINGS, SETTINGS_BAK)
        except OSError:
            pass
    env = data.get("env")
    if not isinstance(env, dict):
        env = {}
    env["HTTPS_PROXY"] = url
    env["HTTP_PROXY"] = url
    # Make the agent ride out blocks/outages via its native retry spinner rather
    # than failing the turn. Don't clobber a value the user set themselves.
    for k, v in RETRY_ENV.items():
        env.setdefault(k, v)
    data["env"] = env
    try:
        os.makedirs(os.path.dirname(CLAUDE_SETTINGS), exist_ok=True)
        _atomic_write(CLAUDE_SETTINGS, json.dumps(data, indent=2) + "\n")
        return True
    except OSError as e:
        log(f"route_on failed: {e}")
        return False


def route_off():
    if not os.path.isfile(CLAUDE_SETTINGS):
        return []
    data = _read_settings()
    env = data.get("env")
    removed = []
    if isinstance(env, dict):
        for k in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
            v = str(env.get(k, ""))
            if k in env and ("127.0.0.1" in v or "localhost" in v):
                env.pop(k)
                removed.append(k)
        # Remove the retry-tolerance env we installed — but only if it still
        # holds our value (leave a user-customised value in place).
        for k, val in RETRY_ENV.items():
            if env.get(k) == val:
                env.pop(k)
                removed.append(k)
        if not env:
            data.pop("env", None)
    if removed:
        if not os.path.exists(SETTINGS_BAK):
            try:
                shutil.copyfile(CLAUDE_SETTINGS, SETTINGS_BAK)
            except OSError:
                pass
        _atomic_write(CLAUDE_SETTINGS, json.dumps(data, indent=2) + "\n")
    return removed


def reset_to_default():
    removed, backups = [], []
    off = route_off()
    if off:
        removed.append("proxy from settings.json")
        if os.path.exists(SETTINGS_BAK):
            backups.append(SETTINGS_BAK)
    if IS_WINDOWS:
        _win.keepawake(False)       # no pmset/sudoers on Windows
    else:
        _pmset_nopasswd("0")
        if os.path.exists(SUDOERS_FILE):
            removed.append("keep-awake disabled (permission remains; use "
                           "'Remove keep-awake permission' to clear)")
    return {"done": True, "removed": removed, "backups": backups}


def _osascript_admin(sh):
    apple = sh.replace("\\", "\\\\").replace('"', '\\"')
    try:
        r = subprocess.run(
            ["osascript", "-e",
             f'do shell script "{apple}" with administrator privileges'],
            capture_output=True, timeout=180)
        return r.returncode == 0
    except Exception:
        return False


def _pmset_nopasswd(val):
    try:
        r = subprocess.run(["sudo", "-n", PMSET, "-a", "disablesleep", val],
                           capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def _install_clamshell_rule(val):
    rule = (f"{USER} ALL=(root) NOPASSWD: {PMSET} -a disablesleep 1, "
            f"{PMSET} -a disablesleep 0\n")
    tmp = tempfile.NamedTemporaryFile("w", delete=False, suffix="-tower")
    tmp.write(rule)
    tmp.close()
    os.chmod(tmp.name, 0o644)
    q = shlex.quote(tmp.name)
    ok = _osascript_admin(
        f"/usr/sbin/visudo -cf {q} && "
        f"/usr/bin/install -m 0440 -o root -g wheel {q} {SUDOERS_FILE} && "
        f"{PMSET} -a disablesleep {val}")
    try:
        os.remove(tmp.name)
    except OSError:
        pass
    return ok


def _clamshell(enable):
    val = "1" if enable else "0"
    if _pmset_nopasswd(val):
        return True
    if not enable:
        return True
    return _install_clamshell_rule(val)


def _remove_clamshell_rule():
    _pmset_nopasswd("0")
    if os.path.exists(SUDOERS_FILE):
        _osascript_admin(f"{PMSET} -a disablesleep 0; /bin/rm -f {SUDOERS_FILE}")


def set_keepawake(state, on, mode):
    if IS_WINDOWS:
        # SetThreadExecutionState replaces the whole caffeinate/pmset/sudoers
        # stack. No admin, no clamshell — modes collapse to off / idle.
        if not on:
            _win.keepawake(False)
            state.keepawake_on = False
            state.keepawake_mode = "off"
            return {"on": False, "mode": "off"}
        _win.keepawake(True)
        state.keepawake_on = True
        state.keepawake_mode = "idle"
        return {"on": True, "mode": "idle", "needs_admin": False}
    if state._caffeinate and state._caffeinate.poll() is None:
        try:
            state._caffeinate.terminate()
            state._caffeinate.wait(timeout=3)
        except Exception:
            pass
    state._caffeinate = None
    if not on:
        state.keepawake_on = False
        state.keepawake_mode = "off"
        _clamshell(False)
        return {"on": False, "mode": "off"}
    try:
        state._caffeinate = subprocess.Popen(
            ["caffeinate", "-dimsu"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    needs_admin = False
    if mode == "clamshell":
        needs_admin = not _clamshell(True)
    state.keepawake_on = True
    state.keepawake_mode = mode
    return {"on": True, "mode": mode, "needs_admin": needs_admin}


# --------------------------------------------------------------------------- #
# File IPC: state writer + command watcher
# --------------------------------------------------------------------------- #
def build_state(state, usage, net, agents):
    # Refresh the routing timeline from the on-disk truth every cycle: keeps
    # state.routing_now fresh for the agent monitor and self-corrects the record
    # after an external settings edit or a kill -9 (records a change only when the
    # installed state actually flips, so this is a no-op write in steady state).
    installed = routing_installed()
    note_route_change(state, installed)
    return {
        "ts": time.time(),
        "location": state.location_dict(),
        "guard": {"target_cc": state.target_cc, "enforce": state.enforce,
                  "block_all": state.block_all, "allowed": state.allowed,
                  "blocked": state.blocked, "proxy_port": state.proxy_port,
                  "proxy_up": proxy_is_up(state.proxy_port),
                  # Fail-closed gate state: is a Claude request permitted right
                  # now, and if not, is it geo or net that's holding it back?
                  "claude_allowed": state.claude_allowed(),
                  "net_ok": bool(state.net_ok),
                  # Pending/retry UI: a Claude request is waiting on the guard
                  # (held in-proxy or retrying) — front-ends shimmer while true.
                  "pending": state.retry_pending(),
                  "holding": state.holding},
        "routing": {"installed": installed,
                    "intended": state.routed},
        "keepawake": {"on": state.keepawake_on, "mode": state.keepawake_mode},
        "settings": {"theme": state.theme, "country": state.target_cc,
                     "plan_week_tokens": state.plan_week_tokens,
                     "plan_enabled": state.plan_enabled},
        "recent": list(state.recent),
        "usage": usage.get(),
        "plan": state.plan,
        "net": net.snapshot(),
        "agents": agents.snapshot(),
        "procs": {
            "daemon_pid": os.getpid(),
            "keepawake_pid": (state._caffeinate.pid
                              if state._caffeinate
                              and state._caffeinate.poll() is None else None),
        },
        "version": "3.0",
    }


def state_writer(state, usage, net, agents, interval=1.0):
    while not state.stop.is_set():
        try:
            _atomic_write(STATE_FILE,
                          json.dumps(build_state(state, usage, net, agents)))
        except Exception as e:  # noqa: BLE001
            log(f"state write error: {e}")
        time.sleep(interval)


def dispatch(state, usage, net, agents, req):
    cmd = req.get("cmd")
    if cmd == "route":
        if bool(req.get("on", True)):
            ok = route_on(state.proxy_port)
            state.routed = ok
            state.cfg["routed"] = ok
            save_config(state.cfg)
            note_route_change(state, ok)
            return {"installed": ok,
                    "error": None if ok else "guard proxy is not running yet"}
        route_off()
        state.routed = False
        state.cfg["routed"] = False
        save_config(state.cfg)
        note_route_change(state, False)
        return {"installed": False}
    if cmd == "reset":
        return reset_to_default()
    if cmd == "country":
        cc = str(req.get("cc", "")).upper()[:2]
        if cc:
            state.target_cc = cc
            state.cfg["country"] = cc
            save_config(state.cfg)
            state._recheck = True
        return {"ok": True, "target_cc": state.target_cc}
    if cmd == "recheck":
        state._recheck = True
        net._probe_now = True   # one user gesture refreshes both signals
        return {"ok": True}
    if cmd == "refreshplan":
        state._refreshplan = True
        return {"ok": True}
    if cmd == "speedtest":
        return net.start_speedtest()
    if cmd == "focus":
        return agents.focus(str(req.get("session_id") or ""))
    if cmd == "dismiss":
        return agents.dismiss(str(req.get("session_id") or ""), True)
    if cmd == "undismiss":
        return agents.dismiss(str(req.get("session_id") or ""), False)
    if cmd == "planfetch":
        state.plan_enabled = bool(req.get("on", True))
        state.cfg["plan_enabled"] = state.plan_enabled
        save_config(state.cfg)
        state._refreshplan = True
        return {"plan_enabled": state.plan_enabled}
    if cmd == "enforce":
        state.enforce = bool(req.get("on", True))
        return {"enforce": state.enforce}
    if cmd == "scope":
        state.block_all = bool(req.get("block_all", False))
        return {"block_all": state.block_all}
    if cmd == "keepawake":
        return set_keepawake(state, bool(req.get("on", False)),
                             str(req.get("mode", "idle")))
    if cmd == "removekeepawake":
        if IS_WINDOWS:
            _win.keepawake(False)   # no persistent permission to remove
        else:
            _remove_clamshell_rule()
        state.keepawake_on = False
        state.keepawake_mode = "off"
        return {"removed": IS_WINDOWS or not os.path.exists(SUDOERS_FILE)}
    if cmd == "theme":
        state.theme = str(req.get("theme", "Daybreak"))
        state.cfg["theme"] = state.theme
        save_config(state.cfg)
        return {"theme": state.theme}
    if cmd == "quit":
        state.stop.set()
        return {"bye": True}
    return {"error": f"unknown cmd {cmd!r}"}


def command_watcher(state, usage, net, agents):
    os.makedirs(CMD_DIR, exist_ok=True)
    while not state.stop.is_set():
        did = False
        try:
            for name in sorted(os.listdir(CMD_DIR)):
                if not name.endswith(".json"):
                    continue
                path = os.path.join(CMD_DIR, name)
                try:
                    with open(path) as f:
                        req = json.load(f)
                except Exception:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    continue
                try:
                    os.remove(path)
                except OSError:
                    pass
                try:
                    res = dispatch(state, usage, net, agents, req)
                except Exception as e:  # noqa: BLE001
                    res = {"error": str(e)}
                    log(f"cmd {req} error: {e}")
                did = True
                rid = req.get("id")
                if rid:
                    try:
                        _atomic_write(os.path.join(CMD_DIR, f"{rid}.done"),
                                      json.dumps(res))
                    except OSError:
                        pass
            # Write fresh state IMMEDIATELY after handling a command so the UI
            # reflects the change within ~1 tick instead of waiting for the 1s
            # state heartbeat.
            if did:
                try:
                    _atomic_write(STATE_FILE, json.dumps(
                        build_state(state, usage, net, agents)))
                except Exception:  # noqa: BLE001
                    pass
        except FileNotFoundError:
            os.makedirs(CMD_DIR, exist_ok=True)
        time.sleep(0.06 if not did else 0.0)   # poll fast; loop hot after a cmd


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def _migrate_legacy_state_dir():
    """One-time rename of a legacy state dir (Corral, then Geo Guard) to Tower;
    config carries over. Only when a legacy dir exists and the new one doesn't,
    and never while an old daemon still holds its lock — a live legacy daemon
    would keep writing into the moved directory."""
    if os.path.isdir(CONFIG_DIR):
        return
    # Corral/Geo Guard were macOS-only; no legacy dir can exist on Windows, and
    # fcntl isn't available there — skip the "is the old daemon still running?"
    # probe entirely.
    if IS_WINDOWS:
        return
    legacy = next((d for d in LEGACY_CONFIG_DIRS if os.path.isdir(d)), None)
    if not legacy:
        return
    old_lock = os.path.join(legacy, "daemon.lock")
    try:
        with open(old_lock) as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)  # free = no old daemon
    except FileNotFoundError:
        pass
    except OSError:
        print("towerd: quit the old daemon first "
              "(its state dir is still locked)", flush=True)
        raise SystemExit(1)
    try:
        os.rename(legacy, CONFIG_DIR)
        for bak in LEGACY_SETTINGS_BAKS:
            if os.path.exists(bak) and not os.path.exists(SETTINGS_BAK):
                os.rename(bak, SETTINGS_BAK)
                break
        log(f"migrated {legacy} -> {CONFIG_DIR}")
    except OSError as e:
        print(f"towerd: state-dir migration failed ({e})", flush=True)


_routed_off_once = False


def _route_off_idempotent(reason):
    """Restore settings.json (remove our proxy env) at most once, from whichever
    shutdown path fires first — the main finally, a signal, or atexit."""
    global _routed_off_once
    if _routed_off_once:
        return
    _routed_off_once = True
    try:
        removed = route_off()
        if removed:
            log(f"route_off on {reason}: {removed}")
    except Exception as e:  # noqa: BLE001
        log(f"route_off on {reason} failed: {e}")


def main():
    # Detach into our own session so we're an independent daemon, not a
    # responsibility-child of whatever launched us (the menu-bar app). This
    # keeps macOS from attributing a spawned `claude`'s unrelated prompts
    # (e.g. a shell/plugin touching Apple Music) to "Tower.app".
    # os.setsid doesn't exist on Windows (and raises AttributeError, not
    # OSError); the front-end spawns us DETACHED there instead.
    if hasattr(os, "setsid"):
        try:
            os.setsid()
        except OSError:
            pass
    _migrate_legacy_state_dir()
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(CMD_DIR, exist_ok=True)
    # single instance
    if IS_WINDOWS:
        # Named mutex — cleaner than a file lock on Windows. Keep the handle on
        # `state` (set below) so it lives as long as the process.
        _mutex = _win.single_instance()
        if _mutex is None:
            log("another daemon is already running; exiting")
            print("towerd: already running", flush=True)
            return
        lockf = None
    else:
        _mutex = None
        lockf = open(LOCK_FILE, "w")
        try:
            fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            log("another daemon is already running; exiting")
            print("towerd: already running", flush=True)
            return
        lockf.write(str(os.getpid()))
        lockf.flush()

    cfg = load_config()
    state = State(cfg)
    state._mutex = _mutex       # keep the single-instance mutex alive (Windows)
    usage = UsageIndex(state)
    net = NetMonitor(state)
    agents = AgentMonitor(state)

    try:
        proxy_sock, proxy_port = bind_proxy(cfg)
    except OSError as e:
        log(f"proxy bind failed: {e}")
        print(f"towerd: proxy bind failed ({e})", flush=True)
        return
    state.proxy_port = proxy_port

    threading.Thread(target=geo_loop, args=(state,), daemon=True).start()
    threading.Thread(target=proxy_loop, args=(state, proxy_sock),
                     daemon=True).start()
    threading.Thread(target=usage.loop, daemon=True).start()
    threading.Thread(target=plan_loop, args=(state,), daemon=True).start()
    threading.Thread(target=net.loop, daemon=True).start()
    threading.Thread(target=agents.loop, daemon=True).start()
    threading.Thread(target=state_writer, args=(state, usage, net, agents),
                     daemon=True).start()
    threading.Thread(target=command_watcher, args=(state, usage, net, agents),
                     daemon=True).start()

    # ON BY DEFAULT: unless you have EXPLICITLY turned routing off before
    # (cfg["routed"] == False), the guard routes Claude the moment the daemon
    # comes up — i.e. as soon as you open the app. The proxy socket is already
    # listening, so route_on's safety check passes and Claude is only ever
    # routed while the guard is genuinely up.
    if state.cfg.get("routed", True):
        if route_on(state.proxy_port):
            log("routing on at startup (default-on)")
    # Seed the routing timeline with the actual on-disk truth at boot: starts the
    # history and self-corrects a record left stranded by a previous kill -9.
    note_route_change(state, routing_installed())

    log(f"started pid={os.getpid()} proxy=:{proxy_port}")
    print(f"towerd: proxy :{proxy_port}", flush=True)

    # Belt-and-braces: also restore settings.json if the interpreter exits without
    # running the finally below (idempotent, so the finally path won't double-log).
    atexit.register(_route_off_idempotent, "atexit")

    def _sig(*_a):
        state.stop.set()
    # SIGINT (Ctrl-C) works everywhere. SIGTERM is POSIX; on Windows the
    # catchable console-close signal is SIGBREAK. The primary, cross-platform
    # shutdown is the {"cmd":"quit"} command file (dispatch sets state.stop),
    # which runs the finally: route_off() block below regardless of signals.
    signal.signal(signal.SIGINT, _sig)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _sig)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _sig)

    try:
        while not state.stop.is_set():
            time.sleep(0.2)
    finally:
        set_keepawake(state, False, "off")
        # SAFETY: never leave Claude Code pointed at a proxy that is stopping.
        # Routing is active ONLY while the guard is alive; always restore
        # settings.json on the way out.
        _route_off_idempotent("shutdown")
        try:
            os.remove(STATE_FILE)
        except OSError:
            pass
        log("stopped")


if __name__ == "__main__":
    main()
