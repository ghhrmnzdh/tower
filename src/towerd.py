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
import bisect
import errno
import json
import os
import re
import select
import shutil
import signal
import socket
import ssl
import subprocess
import sys
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
# live in _win.py, imported only here.
#
# Linux is POSIX like macOS — same fcntl lock, same `ps` table, same setsid —
# but it is not macOS: there is no caffeinate/IOKit, no osascript, no TCC, and
# /proc answers what macOS needs lsof/libproc for. Those edges live in
# _linux.py behind IS_LINUX. macOS behavior is unchanged everywhere.
IS_WINDOWS = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux")
if IS_WINDOWS:
    import _win
else:
    import fcntl
if IS_LINUX:
    import _linux

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
# Pid of a quit daemon still holding the proxy port open for pinned chats (see
# _relay_for_pinned). The next daemon evicts it and takes the port back.
RELAY_FILE = os.path.join(CONFIG_DIR, "relay.pid")
LOG_FILE = os.path.join(CONFIG_DIR, "daemon.log")

CLAUDE_PROJECTS = os.path.join(HOME, ".claude", "projects")
CLAUDE_SETTINGS = os.path.join(HOME, ".claude", "settings.json")
SETTINGS_BAK = CLAUDE_SETTINGS + ".tower.bak"
# Tower's own `claude -p /usage` probes run with cwd=CONFIG_DIR, so Claude Code
# files them under projects/<CONFIG_DIR with every non-alphanumeric char → "-">
# (e.g. -Users-me--tower). They are never agents and carry no model usage. Older
# probes also persisted a session per run — ~1,400 transcripts a day that every
# scan then had to stat forever, so the monitor grew its own workload without
# bound. Both transcript indexes skip this directory outright.
PROBE_PROJECT_DIR = re.sub(r"[^A-Za-z0-9]", "-", CONFIG_DIR)

# TCC-protected locations. Tower is a *monitor*, not a file manager: it must
# NEVER open or enumerate anything under these, because the first read triggers
# a macOS "Tower wants to access your Desktop/Photos/Music…" prompt — attributed
# to us, at an unpredictable moment, for data we never actually need. An agent
# whose cwd sits here still gets a row (project_name is derived from the path
# string, no I/O); we simply skip the git-root/branch/collision file reads for
# it. See the "Never trip a TCC prompt" invariant in CLAUDE.md. (/Volumes covers
# external/network disks, also gated by TCC on recent macOS.)
# Windows and Linux have no TCC prompt system, so nothing is "protected" there —
# the agent monitor can read git roots/branches freely. Empty tuple ⇒ _is_protected is a
# no-op (always False). The macOS list (and hardcoded /Volumes) stays as-is.
if IS_WINDOWS or IS_LINUX:
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
TASKPOLICY = "/usr/sbin/taskpolicy"
# Legacy: older versions held the lid with a NOPASSWD `pmset disablesleep` rule.
# Lid-closed no longer needs it; the path is kept so Reset can still remove it.
SUDOERS_FILE = "/etc/sudoers.d/geo-guard"

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

        # Keep-awake: the armed mode persists, so a respawned daemon resumes the
        # vigil; whether the Mac is actually held right now is keepawake_loop's.
        km = cfg.get("keepawake_mode")
        self.keepawake_mode = km if km in ("idle", "clamshell") else "off"
        self.keepawake_on = self.keepawake_mode != "off"
        self.keepawake_reason = "off"
        self.keepawake_grace_left = None
        self._awake_poke = threading.Event()
        self._awake_held = False
        self._lid_held = False
        self._inhibit_want = None   # Linux: the logind lock currently asked for
        self._inhibit_failed = False
        self._caffeinate = None

        # real plan usage, fetched by running `claude -p /usage` (no creds read)
        self.plan = None
        self._refreshplan = threading.Event()   # "refresh now" — wakes plan_loop

        self.stop = threading.Event()
        # Hook events land on proxy threads; the monitor's on_event is the sink.
        # _publish wakes the state writer so a change reaches the UI in ms.
        self.hook_sink = None
        self._publish = threading.Event()
        # The proxy listener has its own stop: after a confirmed quit it outlives
        # the rest of the daemon so pinned chats keep a live endpoint (relay mode).
        self.proxy_stop = threading.Event()
        self.relay_on_exit = False
        self.lock = threading.Lock()

        # Ground-truth path health: monotonic timestamps of recent Claude tunnels
        # the UPSTREAM reset mid-flight. The synthetic net probe (a tiny TLS
        # handshake) can't predict a large-body reset; real tunnel outcomes can.
        # A burst here flips the gate closed so the next reconnect is held as a
        # calm 503-pending instead of a raw ECONNRESET in Claude's escalating
        # backoff. Own lock so it never contends with self.lock.
        self._tfails = deque(maxlen=64)
        self._toks = deque(maxlen=256)   # fresh upstream connects, same window
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

    def record_tunnel_ok(self):
        """A Claude tunnel reached Anthropic (upstream connect succeeded) — the
        counterweight path_unstable() weighs resets against."""
        with self._tfail_lock:
            self._toks.append(time.monotonic())

    def path_unstable(self):
        """True when real Claude tunnels are resetting upstream faster than
        chance — at least TUNNEL_FAIL_BURST resets within TUNNEL_FAIL_WINDOW_S
        that are also TUNNEL_FAIL_SHARE of the window's outcomes. Self-clearing:
        once the gate holds, no new tunnels reach upstream, the window empties,
        and traffic is admitted again to re-test the path."""
        cutoff = time.monotonic() - TUNNEL_FAIL_WINDOW_S
        with self._tfail_lock:
            for q in (self._tfails, self._toks):
                while q and q[0] < cutoff:
                    q.popleft()
            fails, oks = len(self._tfails), len(self._toks)
            return (fails >= TUNNEL_FAIL_BURST
                    and fails >= TUNNEL_FAIL_SHARE * (fails + oks))

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
            last = {"ip": state.ip, "city": state.city, "region": state.region,
                    "isp": state.isp, "country_name": state.country_name,
                    "country_cc": state.country_cc}
            if state.cfg.get("last_location") != last:   # not every 15s
                state.cfg["last_location"] = last
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
TUNNEL_SILENT_LOG_S = 60.0  # ledger: log a Claude tunnel whose last request bytes
                            # got no reply for this long, or whose write blocked
                            # this long — evidence of WHO went silent (see _tunnel)

def _pipe(src, dst, st=None):
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
    mid-flight upstream drop from a normal close. Only a failed READ from src
    counts: a failed write to dst means the far side (on the upstream-read half,
    Claude itself closing or aborting a stream — routine with many parallel
    agents) went away, which says nothing about the path to Anthropic.

    `st` (optional dict) is the tunnel ledger for this direction: `last` =
    monotonic time the last chunk was fully handed on, `stall` = the longest a
    single write to dst blocked, `end` = why this half stopped. Cheap: one
    clock read per chunk."""
    reset = False
    how = "eof"
    try:
        while True:
            try:
                data = src.recv(65536)
            except OSError as e:
                reset = e.errno in (errno.ECONNRESET, errno.EPIPE,
                                    errno.ETIMEDOUT)
                how = "idle-timeout" if isinstance(e, socket.timeout) else (
                    f"read error ({e.__class__.__name__})")
                break
            if not data:
                break
            if st is None:
                dst.sendall(data)
                continue
            t0 = time.monotonic()
            dst.sendall(data)
            st["last"] = t1 = time.monotonic()
            st["stall"] = max(st.get("stall", 0.0), t1 - t0)
    except OSError as e:
        how = f"write error ({e.__class__.__name__})"
    if st is not None:
        st["end"] = how
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
TUNNEL_FAIL_BURST = 2       # at least this many resets in-window → path unstable,
TUNNEL_FAIL_SHARE = 0.5     # …AND at least this share of the window's tunnel outcomes
                            # (resets vs fresh upstream connects). A lone agent keeps
                            # the old 2-strike rule; with many parallel agents a couple
                            # of resets among dozens of good tunnels is a lossy link,
                            # not a dead one, and must not pause every agent at once.
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
# Dead-path detection on the UPSTREAM leg. Claude Code reuses pooled tunnels, and
# the localhost leg to us never breaks — so when the path beyond us dies silently
# (VPN reconnect, NAT/middlebox drops an idle flow; no FIN, no RST), nothing
# tells Claude. Its next request vanishes into the dead flow and it waits out the
# whole first-byte window ("No response from the API after …") before retrying.
# The kernel can notice instead, and each rule only fires on a path that is GONE,
# never on one that is merely slow:
#   · keepalive probes an idle tunnel (a server busy computing a reply still ACKs
#     them), cutting a dead one after IDLE + INTVL×CNT ≈ 2 min — macOS's own
#     default would wait 2 h;
#   · the retransmission drop time cuts a tunnel whose in-flight bytes get NO ACK
#     at all for this long (a slow but live upload keeps ACKing, so it's safe).
# A cut tunnel reaches Claude as a closed connection, which rides its normal
# retry budget (RETRY_ENV) instead of the one-retry first-byte path.
UPSTREAM_KEEPIDLE_S = 60
UPSTREAM_KEEPINTVL_S = 15
UPSTREAM_KEEPCNT = 4
UPSTREAM_RXT_DROP_S = 120
# Darwin <netinet/tcp.h> values, pinned: the socket module never exports
# TCP_RXT_CONNDROPTIME, and /usr/bin/python3 (3.9, the app's last-resort
# interpreter) lacks TCP_KEEPALIVE too — without it the idle probe would silently
# stay at the 2 h default.
_DARWIN_TCP_KEEPALIVE = 0x10
_DARWIN_TCP_RXT_CONNDROPTIME = 0x80
_DARWIN_TCP_KEEPINTVL = 0x101
_DARWIN_TCP_KEEPCNT = 0x102
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


def _upstream_sockopts():
    """(level, option, value) for the upstream leg, per platform: TCP_NODELAY plus
    the dead-path rules above. Options the platform lacks are simply absent."""
    tcp = socket.IPPROTO_TCP
    opts = [(tcp, socket.TCP_NODELAY, 1),
            (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)]
    if sys.platform == "darwin":
        return opts + [(tcp, _DARWIN_TCP_KEEPALIVE, UPSTREAM_KEEPIDLE_S),
                       (tcp, _DARWIN_TCP_KEEPINTVL, UPSTREAM_KEEPINTVL_S),
                       (tcp, _DARWIN_TCP_KEEPCNT, UPSTREAM_KEEPCNT),
                       (tcp, _DARWIN_TCP_RXT_CONNDROPTIME, UPSTREAM_RXT_DROP_S)]
    for name, val in (("TCP_KEEPIDLE", UPSTREAM_KEEPIDLE_S),
                      ("TCP_KEEPINTVL", UPSTREAM_KEEPINTVL_S),
                      ("TCP_KEEPCNT", UPSTREAM_KEEPCNT),
                      # Linux's analogue of the drop time, in milliseconds
                      ("TCP_USER_TIMEOUT", UPSTREAM_RXT_DROP_S * 1000)):
        if hasattr(socket, name):
            opts.append((tcp, getattr(socket, name), val))
    return opts


def _upstream_connect(host, port):
    """Open the upstream leg of a tunnel. create_connection applies its timeout to
    the CONNECT only in spirit but leaves it ON the returned socket, so we reset it
    to a long-but-bounded idle timeout (TUNNEL_IDLE_S) — otherwise every relay recv
    inherits the short connect deadline and a slow-first-byte or idle keep-alive
    tunnel dies mid-session. TCP_NODELAY kills Nagle so streamed SSE token frames
    and small request bodies aren't batched behind delayed ACKs; keepalive + the
    retransmission drop time cut a silently dead path (see UPSTREAM_KEEPIDLE_S)."""
    up = socket.create_connection((host, port), timeout=UPSTREAM_CONNECT_S)
    up.settimeout(TUNNEL_IDLE_S)
    for level, opt, val in _upstream_sockopts():
        try:
            up.setsockopt(level, opt, val)
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
    if is_claude_host(host):
        state.record_tunnel_ok()
    conn.settimeout(None)   # tunnel relay must block indefinitely, not carry the
                            # header-read deadline set on conn in _handle_proxy_client
    claude = is_claude_host(host)
    ust, dst_ = ({}, {}) if claude else (None, None)
    t = threading.Thread(target=_pipe, args=(conn, up, ust), daemon=True)
    try:
        conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        t.start()
    except (OSError, RuntimeError):   # client gone, or no thread to spare:
        for s in (up, conn):          # close both now (Claude retries at once)
            try:                      # instead of leaking a half-open tunnel
                s.close()
            except OSError:
                pass
        return
    # Main thread reads the UPSTREAM half: a reset here is a genuine mid-flight
    # drop from Anthropic/the VPN (not a client abort, which resets `conn` in the
    # upload thread). Both halves half-close on EOF; wait for the upload half to
    # drain rather than guillotining it, then close both.
    upstream_reset = _pipe(up, conn, dst_)
    t.join(TUNNEL_DRAIN_S)
    for s in (up, conn):
        try:
            s.close()
        except OSError:
            pass
    # Feed the real outcome back to the guard: a burst of upstream resets means
    # the path is unusable right now, so the next reconnect is held (calm 503)
    # instead of admitted into another raw ECONNRESET.
    if upstream_reset and claude:
        state.record_tunnel_fail()
    if claude:
        _ledger(host, ust, dst_)


def _ledger(host, up_st, down_st):
    """Attribute a silent Claude tunnel. Tower relays each chunk the moment it
    arrives, so if the request's bytes were all handed to the upstream socket
    and nothing came back, the silence is on the path (VPN) or Anthropic's side
    — and this line says so, with numbers. A long blocked write says the
    receiving side stopped taking bytes. Quiet for healthy tunnels."""
    now = time.monotonic()
    last_up, last_down = up_st.get("last"), down_st.get("last")
    notes = []
    if last_up and (last_down or 0) < last_up \
            and now - last_up >= TUNNEL_SILENT_LOG_S:
        notes.append(f"last request unanswered {now - last_up:.0f}s after Tower "
                     f"relayed it (path/Anthropic silent, not Tower)")
    if up_st.get("stall", 0) >= TUNNEL_SILENT_LOG_S:
        notes.append(f"upload write blocked {up_st['stall']:.0f}s "
                     f"(upstream stopped accepting bytes)")
    if down_st.get("stall", 0) >= TUNNEL_SILENT_LOG_S:
        notes.append(f"download write blocked {down_st['stall']:.0f}s "
                     f"(Claude stopped reading)")
    if notes:
        log(f"tunnel {host}: " + "; ".join(notes)
            + f" — ended: claude-side {up_st.get('end', '?')}, "
              f"upstream-side {down_st.get('end', '?')}")


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


def _is_hook_target(target):
    """Origin-form `/__tower/hook`, or absolute-form when Claude's HTTP client
    sends the hook via its proxy env (which is this same listener)."""
    if target.startswith("/"):
        return target.split("?", 1)[0] == HOOK_PATH
    from urllib.parse import urlsplit
    p = urlsplit(target)
    return p.hostname in ("127.0.0.1", "localhost") and p.path == HOOK_PATH


_RE_HOOK_FIELD = re.compile(
    rb'"(hook_event_name|session_id|cwd|transcript_path|agent_id|agent_type'
    rb'|tool_name)"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _hook_head(data):
    """The routing fields of an oversized hook body, without parsing it all."""
    out = {}
    for m in _RE_HOOK_FIELD.finditer(data[:65536]):
        k = m.group(1).decode()
        if k not in out:
            try:
                out[k] = json.loads(b'"' + m.group(2) + b'"')
            except Exception:  # noqa: BLE001
                pass
    return out


def _serve_hook(conn, state, raw):
    """Claude Code's HTTP hook. Read the whole body (a half-read body would turn
    into a client-side error), answer an empty 200 — "no decision", so the hook
    can never alter what Claude does — and only then hand the event over."""
    head, _, body = raw.partition(b"\r\n\r\n")
    hl = head.lower()
    chunks, got = [body], len(body)
    if b"transfer-encoding: chunked" in hl:
        buf = body
        while not buf.endswith(b"0\r\n\r\n"):
            c = conn.recv(65536)
            if not c:
                break
            buf += c if len(buf) < HOOK_BODY_MAX else b""
        data, rest = b"", buf
        while rest:
            size_line, _, rest = rest.partition(b"\r\n")
            try:
                n = int(size_line.split(b";")[0], 16)
            except ValueError:
                break
            if n == 0:
                break
            data += rest[:n]
            rest = rest[n + 2:]
    else:
        m = re.search(rb"content-length:\s*(\d+)", hl)
        n = int(m.group(1)) if m else 0
        while got < n:
            c = conn.recv(min(65536, n - got))
            if not c:
                break
            if got < HOOK_BODY_MAX:
                chunks.append(c)
            got += len(c)
        data = b"".join(chunks)
    conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n"
                 b"Connection: close\r\n\r\n")
    sink = state.hook_sink
    if sink is None:
        return                          # relay mode: acknowledge, nothing to do
    try:
        ev = json.loads(data) if len(data) < HOOK_BODY_MAX else _hook_head(data)
    except Exception:  # noqa: BLE001
        ev = _hook_head(data)
    if isinstance(ev, dict):
        sink(ev)


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
        if method.upper() == "POST" and _is_hook_target(target):
            _serve_hook(conn, state, raw)
        elif method.upper() == "CONNECT":
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


ACCEPT_BACKOFF_S = 0.2       # pause after a transient accept/thread failure


def proxy_loop(state, srv):
    """Accept forever. The listener must NEVER die while the daemon lives: a
    pinned session can't move to another endpoint, and a listener nobody
    accepts on leaves its CONNECTs queued unanswered until Claude's 10-minute
    first-byte watchdog fires. So a transient failure (out of fds under a big
    parallel run, a peer that aborted in the backlog, no thread to spare) is
    logged and survived; only proxy_stop — or our own socket being closed
    (EBADF) — ends the loop."""
    srv.settimeout(0.5)
    last_log = 0.0
    while not state.proxy_stop.is_set():
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        except OSError as e:
            if e.errno == errno.EBADF:
                break
            if time.monotonic() - last_log > 30:
                last_log = time.monotonic()
                log(f"proxy accept error (continuing): {e}")
            state.proxy_stop.wait(ACCEPT_BACKOFF_S)
            continue
        try:
            threading.Thread(target=_handle_proxy_client, args=(conn, state),
                             daemon=True).start()
        except RuntimeError as e:   # can't start new thread: fail THIS client
            try:                    # fast (closed → Claude retries at once)
                conn.close()        # rather than hang it, and keep accepting
            except OSError:
                pass
            if time.monotonic() - last_log > 30:
                last_log = time.monotonic()
                log(f"proxy thread start failed (continuing): {e}")
            state.proxy_stop.wait(ACCEPT_BACKOFF_S)
    srv.close()


def raise_fd_limit(want=8192):
    """launchd hands an app-spawned daemon a soft RLIMIT_NOFILE of 256. Every
    tunnel costs two fds, so a large parallel-agent run could exhaust it —
    and then every new tunnel fails. Lift the soft limit toward the hard one."""
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        target = want if hard == resource.RLIM_INFINITY else min(want, hard)
        if soft != resource.RLIM_INFINITY and soft < target:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
    except (ImportError, ValueError, OSError) as e:
        log(f"fd limit unchanged: {e}")


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
# The API probe's timeout scales with the link, so SLOW never reads as DEAD. On
# a far-hop VPN a healthy TLS handshake to Anthropic takes 2-3 s; a flat 3 s
# timeout turned those into "edge unreachable" samples, two in a row closed the
# gate, and every working agent sat in "Retrying … ERR_PROXY_TUNNEL" on a link
# that was carrying traffic fine. So: allow API_PROBE_RTT_MULT × the slowest
# recent good handshake, and after a timed-out sample give the next probe the
# full API_PROBE_TIMEOUT_MAX — the gate only closes on a path that misses a
# generous deadline too. A fast link keeps the snappy 3 s floor.
API_PROBE_RTT_MULT = 3.0
API_PROBE_TIMEOUT_MAX = 10.0
API_PROBE_RECENT = 12             # history samples the RTT scale looks back over
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
        self._probe_now = threading.Event()  # set by "recheck" — wakes loop()
        self._st_thread = None
        self.speedtest = {"running": False, "progress": 0.0,
                          "mbps_down": None, "ms": None, "bytes": None,
                          "at": None, "error": None, "cooldown_until": 0.0}

    def loop(self):
        while not self.state.stop.is_set():
            try:
                mono = time.monotonic()
                with self.lock:
                    api_timeout = self._api_timeout()
                internet_ms, api_ms, api_err = self._probe_once(api_timeout)
                raw, reason = self._classify(internet_ms, api_ms, api_err)
                now = time.time()
                with self.lock:
                    expected = (NET_INTERVAL_OK if self.status == "online"
                                else NET_INTERVAL_BAD)
                    # Gap is measured from the END of the previous probe, so a
                    # long (escalated) probe isn't mistaken for a sleep.
                    if (self._last_sample_mono is not None
                            and mono - self._last_sample_mono > 3 * expected):
                        # Slept through samples (Mac asleep): the first groggy
                        # post-wake sample must not count toward a flip.
                        self._pending = None
                    self._last_sample_mono = time.monotonic()
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
            if self._probe_now.wait(interval):  # sleep, unless asked to probe
                self._probe_now.clear()

    def _api_timeout(self):
        """Deadline for the next API probe (caller holds self.lock). See
        API_PROBE_RTT_MULT: scaled to the slowest recent good handshake, and
        escalated to the max right after a timeout so one slow sample is
        re-tested generously before it can count toward closing the gate."""
        if self.api_error == "timeout":
            return API_PROBE_TIMEOUT_MAX
        recent = [h["api_ms"] for h in list(self.history)[-API_PROBE_RECENT:]
                  if h["api_ms"] is not None]
        t = API_PROBE_RTT_MULT * max(recent) / 1000.0 if recent else 0.0
        return min(max(NET_TIMEOUT, t), API_PROBE_TIMEOUT_MAX)

    @staticmethod
    def _probe_once(api_timeout=NET_TIMEOUT):
        refs = [m for m in (_tcp_ms(h, p) for h, p in NET_REFS)
                if m is not None]
        internet_ms = min(refs) if refs else None
        api_ms, api_err = _api_probe(api_timeout)
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
# Fed by Claude Code's own HTTP hooks: every session POSTs its lifecycle events
# (prompt, tool start/end, permission prompt, subagent start/stop, turn end,
# session end) to the proxy port at HOOK_PATH, so status IS the event — not a
# guess from transcript mtimes — and lands the instant it happens, subagents
# included. The hooks are observation-only: the endpoint always answers an empty
# 200 (= no decision) and an unreachable Tower is a non-blocking failure Claude
# ignores. The kernel process table (libproc, ~1ms) adds only what events can't
# carry: is the process still alive, its pid/tty for focus, and paused (SIGSTOP).
# The snapshot's field names are a contract with the Swift app — don't rename.
# --------------------------------------------------------------------------- #
HOOK_PATH = "/__tower/hook"
HOOK_TIMEOUT_S = 2            # a stuck Tower must never hold a tool call up
HOOK_EVENTS = ("SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse",
               "PostToolUse", "PostToolUseFailure", "PermissionRequest",
               "Notification", "Stop", "StopFailure", "SubagentStart",
               "SubagentStop", "PreCompact", "PostCompact")
HOOK_BODY_MAX = 4 << 20       # parse at most this much (a huge Write still drains)
AGENT_TICK_S = 3.0            # liveness + aging cadence; events publish at once
PEEK_BYTES = 256 << 10        # transcript tail read for model/title, once a turn
# Thresholds; each overridable via the same-named key in ~/.tower/config.json
AGENT_IDLE_S = 300.0          # agent_idle_s: a finished turn ages to idle
AGENT_GONE_KEEP_S = 60.0      # agent_gone_keep_s: keep gone rows, then drop
AGENT_PENDING_WARN_S = 600.0  # agent_pending_warn_s: pending_tool → warn
AGENT_WORKING_WARN_S = 1200.0  # agent_working_warn_s: no completed turn → warn
# A working turn with no event at all for this long and no tool running: the
# signature of an API retry storm or a dead network path. (agent_api_stall_s)
AGENT_API_STALL_S = 90.0
AGENT_FORGET_S = 6 * 3600.0
LIVE_EVENT_S = 15.0           # a hook event this recent proves the session lives
# A needs-you state must stand this long before it counts. Permission requests
# that an allow rule / auto mode approves a beat later, and turns that resume on
# their own, would otherwise flash "needs you" mid-work.
PERM_SETTLE_S = 2.5
DONE_SETTLE_S = 3.0
DONE_AFTER_SUBS_S = 20.0      # parent stopped, last subagent back: resume window   # an idle session with no process and no event
AGENT_EDIT_WINDOW_S = 900.0   # recent-edit window for file-level collisions
EDIT_TOOLS = ("Edit", "Write", "NotebookEdit", "MultiEdit")
MODEL_TIERS = ("haiku", "sonnet", "opus", "fable")     # ascending caliber
NEEDS_RANK = {"failed": 0, "pending_tool": 1, "asking": 2, "done": 3}

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_RE_SESSION_ID = re.compile(r"--session-id[= ](" + _UUID + r")")
_RE_RESUME_PATH = re.compile(r"--resume[= ](\S+\.jsonl)")
_RE_RESUME_ID = re.compile(r"--resume[= ](" + _UUID + r")(?:\s|$)")
def _model_family(model):
    m = (model or "").lower()
    for fam in ("fable", "opus", "sonnet", "haiku"):
        if fam in m:
            return fam
    return "other"


def _short_path(p):
    # Separator-agnostic: transcript paths recorded on Windows use "\", on Unix
    # "/". Normalize to "/" on Windows only — a POSIX filename may legally
    # contain a backslash, so the macOS shortening stays byte-for-byte as before.
    s = str(p).replace("\\", "/") if IS_WINDOWS else str(p)
    parts = s.rstrip("/").split("/")
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


_CMD_WRAPPERS = frozenset(("sudo", "env", "time", "nohup", "nice",
                           "stdbuf", "command", "exec", "caffeinate"))
_RE_ENVVAR = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _cmd_summary(c):
    """The first meaningful program in a shell line: skip leading `cd …`
    segments, shed env-var / wrapper prefixes, then basename the first real
    token. `cd x && FOO=1 sudo pytest -q` → "pytest". None if nothing found."""
    for seg in re.split(r"&&|\|\||;", c):
        toks = seg.strip().split()
        if not toks or toks[0] == "cd":
            continue
        while toks and (_RE_ENVVAR.match(toks[0]) or toks[0] in _CMD_WRAPPERS):
            toks = toks[1:]
        if toks:
            return os.path.basename(toks[0])
    return None


def _decap(s):
    """Lowercase only a leading Capitalised word so a human description joins the
    lowercase phrase family ("Run the test suite" → "run the test suite"), while
    an all-caps / proper token ("NPM", "CMake") is left as written."""
    return s[0].lower() + s[1:] \
        if len(s) > 1 and s[0].isupper() and s[1].islower() else s


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
        # Prefer the model's own one-line description of the command — far more
        # informative than a token off the command line ("cd x && pytest" used
        # to read as "running cd"). Fall back to a smarter command summary.
        desc = tool.get("desc")
        if desc:
            return _decap(desc)
        c = detail or ""
        if re.search(r"(?:^|\s|/)(?:pytest|npm test|cargo test|swift test"
                     r"|go test|xcodebuild test|make test)\b", c):
            return "running tests"
        first = _cmd_summary(c)
        return f"running {first}" if first else "running a command"
    if n in ("task", "agent"):
        return "delegating to a subagent"
    if n == "webfetch":
        return "fetching a page"
    if n == "askuserquestion":
        return "asking a question"
    return f"using {name}"


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


# --------------------------------------------------------------------------- #
# Claude Desktop + Claude on the web — fenced per app, never system-wide.
# Both are Chromium, which takes `--proxy-server` at launch: Tower opens them
# pointed at its own proxy, so their Claude traffic meets the same fail-closed
# guard as Claude Code, and nothing else on the Mac (VPNs, other browsers, the
# system proxy settings) is touched. Desktop is the user's own app, relaunched
# through Tower on request; the web is claude.ai in a Chrome app window on a
# Tower-only profile (sign in once). Guarded = the running process carries the
# flag — read from its args, never assumed.
# --------------------------------------------------------------------------- #
DESKTOP_APPS = ("/Applications/Claude.app",
                os.path.join(HOME, "Applications", "Claude.app"))
DESKTOP_EXE = "/Contents/MacOS/Claude"
WEB_BROWSERS = (("/Applications/Google Chrome.app", "Google Chrome"),
                ("/Applications/Brave Browser.app", "Brave Browser"),
                ("/Applications/Microsoft Edge.app", "Microsoft Edge"),
                ("/Applications/Chromium.app", "Chromium"))
WEB_PROFILE = os.path.join(CONFIG_DIR, "web-profile")
WEB_URL = "https://claude.ai"
APP_QUIT_WAIT_S = 10.0


def _guarded_app_kind(args):
    """"desktop" for Claude Desktop's main process, "web" for the main process
    of Tower's own browser profile, else None. Exact executable prefix: the
    helper processes share the bundle but not the main binary's path."""
    if not args:
        return None
    for app in DESKTOP_APPS:
        exe = app + DESKTOP_EXE
        if args == exe or args.startswith(exe + " "):
            return "desktop"
    if f"--user-data-dir={WEB_PROFILE}" in args:
        for app, name in WEB_BROWSERS:
            exe = f"{app}/Contents/MacOS/{name}"
            if args == exe or args.startswith(exe + " "):
                return "web"
    return None


def _first_existing(paths):
    return next((p for p in paths if os.path.isdir(p)), None)


def _proxy_flag(port):
    return f"--proxy-server=http://127.0.0.1:{port}"


def apps_snapshot(state, agents):
    """state.json "apps": is each Claude surface installed, running, guarded."""
    lp = agents.procs._libproc
    found = lp.apps if lp is not None else {"desktop": [], "web": []}
    flag = _proxy_flag(state.proxy_port)
    desk = found["desktop"]
    browser = next(((a, n) for a, n in WEB_BROWSERS if os.path.isdir(a)), None)
    return {
        "desktop": {"installed": _first_existing(DESKTOP_APPS) is not None,
                    "running": bool(desk),
                    "guarded": (all(flag in d["args"] for d in desk)
                                if desk else None),
                    "pid": desk[0]["pid"] if desk else None},
        "web": {"available": browser is not None,
                "browser": browser[1] if browser else None,
                "running": bool(found["web"]),
                "guarded": True if found["web"] else None},
    }


def _app_pids(agents, kind):
    lp = agents.procs._libproc
    return [a["pid"] for a in (lp.apps.get(kind, []) if lp else [])]


def open_desktop(state, agents, relaunch=False):
    """Open Claude Desktop through the guard. Running unguarded → only on an
    explicit relaunch: SIGTERM (Electron quits cleanly, like ⌘Q), wait, reopen
    with the flag. Never quits it on its own, never asks for Automation."""
    app = _first_existing(DESKTOP_APPS)
    if not app:
        return {"ok": False, "error": "Claude Desktop isn't installed"}
    if not proxy_is_up(state.proxy_port):
        return {"ok": False, "error": "the guard isn't listening yet"}
    agents.procs.scan()
    running = _app_pids(agents, "desktop")
    guarded = apps_snapshot(state, agents)["desktop"]["guarded"]
    if running and not guarded:
        if not relaunch:
            return {"ok": False, "unguarded": True}
        for pid in running:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        t0 = time.monotonic()
        while any(_pid_alive(p) for p in running):
            if time.monotonic() - t0 > APP_QUIT_WAIT_S:
                return {"ok": False, "error": "Claude Desktop didn't quit"}
            time.sleep(0.2)
        running = []
    argv = ["open", "-a", app]
    if not running:                 # launch args only reach a fresh process
        argv += ["--args", _proxy_flag(state.proxy_port)]
    try:
        subprocess.run(argv, capture_output=True, timeout=15)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    log(f"claude desktop opened through the guard ({'relaunch' if relaunch else 'open'})")
    return {"ok": True}


def open_web(state):
    """claude.ai in a Chrome-family app window on Tower's own profile, through
    the guard. A second call just opens another window in the same instance."""
    browser = next(((a, n) for a, n in WEB_BROWSERS if os.path.isdir(a)), None)
    if not browser:
        return {"ok": False, "error": "needs Chrome, Brave, Edge or Chromium"}
    if not proxy_is_up(state.proxy_port):
        return {"ok": False, "error": "the guard isn't listening yet"}
    os.makedirs(WEB_PROFILE, exist_ok=True)
    argv = ["open", "-n", "-a", browser[0], "--args",
            f"--user-data-dir={WEB_PROFILE}", _proxy_flag(state.proxy_port),
            f"--app={WEB_URL}", "--no-first-run", "--no-default-browser-check"]
    try:
        subprocess.run(argv, capture_output=True, timeout=15)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    log(f"claude web opened through the guard in {browser[1]}")
    return {"ok": True}


class _LibProc:
    """The process table straight from the kernel (libproc + sysctl), instead of
    forking `ps` every 1.8s: ~1ms per scan vs ~35ms, and no child process. A
    process's argv never changes, so it's read once per (pid, start time) and
    cached; steady state is one proc_pidinfo per pid. macOS only — callers fall
    back to `ps` if anything here is unavailable."""
    PIDTBSDINFO, BSDINFO_SIZE = 3, 136          # struct proc_bsdinfo
    PIDVNODEPATHINFO, VNODEPATH_SIZE = 9, 2352  # struct proc_vnodepathinfo
    CDIR_PATH_OFF = 152                         # pvi_cdir.vip_path
    SSTOP = 4
    NODEV = 0xFFFFFFFF

    def __init__(self):
        import ctypes
        import ctypes.util
        self._c = ctypes
        lib = ctypes.CDLL(ctypes.util.find_library("System"))
        lib.proc_listallpids.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                     ctypes.c_void_p, ctypes.c_int]
        lib.sysctl.argtypes = [ctypes.POINTER(ctypes.c_int), ctypes.c_uint,
                               ctypes.c_void_p, ctypes.POINTER(ctypes.c_size_t),
                               ctypes.c_void_p, ctypes.c_size_t]
        self._lib = lib
        mib = (ctypes.c_int * 2)(1, 8)          # CTL_KERN, KERN_ARGMAX
        v, n = ctypes.c_int(), ctypes.c_size_t(4)
        lib.sysctl(mib, 2, ctypes.byref(v), ctypes.byref(n), None, 0)
        self._argmax = v.value or 1 << 20
        self._argbuf = ctypes.create_string_buffer(self._argmax)
        self._bsd = ctypes.create_string_buffer(self.BSDINFO_SIZE)
        self._args = {}         # (pid, start) -> (kind, argv), or None (not ours)
        self.apps = {"desktop": [], "web": []}   # Claude Desktop / web window
        self._ttys = {}         # st_rdev -> "ttys001"

    def _argv(self, pid):
        c = self._c
        mib = (c.c_int * 3)(1, 49, pid)         # CTL_KERN, KERN_PROCARGS2
        n = c.c_size_t(self._argmax)
        if self._lib.sysctl(mib, 3, self._argbuf, c.byref(n), None, 0) != 0:
            return None
        raw = self._argbuf.raw[:n.value]
        if len(raw) < 4:
            return None
        argc = int.from_bytes(raw[:4], "little")
        rest = raw[4:]
        rest = rest[rest.find(b"\0"):].lstrip(b"\0")   # skip exec path + pad
        return " ".join(a.decode("utf-8", "replace")
                        for a in rest.split(b"\0")[:argc])

    def _tty(self, dev):
        if dev == self.NODEV or dev == 0:
            return None
        if dev not in self._ttys:
            try:
                with os.scandir("/dev") as it:
                    for e in it:
                        if e.name.startswith("tty"):
                            try:
                                self._ttys[e.stat().st_rdev] = e.name
                            except OSError:
                                pass
            except OSError:
                pass
            self._ttys.setdefault(dev, None)
        return self._ttys[dev]

    def entries(self):
        c, lib, bsd = self._c, self._lib, self._bsd
        n = lib.proc_listallpids(None, 0)
        buf = (c.c_int * (n + 64))()
        n = lib.proc_listallpids(buf, c.sizeof(buf))
        if n <= 0:
            raise OSError("proc_listallpids failed")
        out, live = [], set()
        apps = {"desktop": [], "web": []}
        for pid in buf[:n]:
            if lib.proc_pidinfo(pid, self.PIDTBSDINFO, 0, bsd,
                                self.BSDINFO_SIZE) != self.BSDINFO_SIZE:
                continue
            raw = bsd.raw
            start = int.from_bytes(raw[120:128], "little")
            key = (pid, start)
            live.add(key)
            if key not in self._args:
                a = self._argv(pid)
                exe = a.split(None, 1)[0] if a else ""
                if os.path.basename(exe) in ("claude", "claude.exe"):
                    self._args[key] = ("cli", a)
                else:
                    kind = _guarded_app_kind(a)
                    self._args[key] = (kind, a) if kind else None
            hit = self._args[key]
            if not hit:
                continue
            kind, args = hit
            if kind != "cli":
                apps[kind].append({"pid": pid, "args": args,
                                   "lstart": float(start)})
                continue
            exe = args.split(None, 1)[0]
            _note_claude_exe(exe)
            out.append({
                "pid": pid,
                "ppid": int.from_bytes(raw[16:20], "little"),
                "tty": self._tty(int.from_bytes(raw[108:112], "little")),
                "stopped": int.from_bytes(raw[4:8], "little") == self.SSTOP,
                "lstart": float(start), "args": args})
        for k in [k for k in self._args if k not in live]:
            del self._args[k]
        self.apps = apps
        return out

    def cwd(self, pid):
        buf = self._c.create_string_buffer(self.VNODEPATH_SIZE)
        if self._lib.proc_pidinfo(pid, self.PIDVNODEPATHINFO, 0, buf,
                                  self.VNODEPATH_SIZE) != self.VNODEPATH_SIZE:
            return None
        path = buf.raw[self.CDIR_PATH_OFF:self.CDIR_PATH_OFF + 1024]
        return path.split(b"\0", 1)[0].decode("utf-8", "replace") or None


class ProcScanner:
    """Reads the process table for live claude processes. `lsof` (works
    without sudo) is used ONLY for pids whose args don't name a session, and
    is cached per pid — claude does not hold its .jsonl open, so cwd is the
    correlation key for bare interactive sessions."""

    def __init__(self):
        self.lsof_ok = True
        self._cwd_cache = {}
        self._libproc = None
        if sys.platform == "darwin":
            try:
                self._libproc = _LibProc()
            except Exception as e:  # noqa: BLE001
                log(f"libproc unavailable, using ps: {e}")

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
        if self._libproc is not None:
            try:
                return self._libproc.entries()
            except Exception as e:  # noqa: BLE001
                log(f"libproc scan failed, falling back to ps: {e}")
                self._libproc = None
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
            _note_claude_exe(exe)       # a full path here helps find_claude()
            try:
                pid, ppid = int(parts[0]), int(parts[1])
            except ValueError:
                continue
            # No controlling terminal: macOS `ps` prints "??", Linux "?".
            # Getting this wrong on Linux would type every headless agent as
            # "interactive" and make it focusable at a tty that isn't there.
            tty = parts[2] if parts[2] not in ("??", "?", "-") else None
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
        if IS_LINUX:
            # /proc/<pid>/cwd is the answer lsof would go looking for anyway,
            # minus the subprocess (and Ubuntu doesn't ship lsof by default).
            cwd = _linux.proc_cwd(pid)
            self._cwd_cache[pid] = cwd
            return cwd
        if self._libproc is not None:
            cwd = self._libproc.cwd(pid)
            if cwd:
                self._cwd_cache[pid] = cwd
                return cwd
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


def _is_dir_entry(entry, follow=True):
    try:
        return entry.is_dir(follow_symlinks=follow)
    except OSError:
        return False


def _project_dirs():
    """Every ~/.claude/projects/<encoded> directory except Tower's own probe
    directory (PROBE_PROJECT_DIR). Raises OSError when projects/ can't be listed,
    so callers can keep their last view instead of treating it as 'no files'."""
    with os.scandir(CLAUDE_PROJECTS) as it:
        return [e.path for e in it
                if e.name != PROBE_PROJECT_DIR and _is_dir_entry(e)]


def _iter_transcripts(dirs, nested=False):
    """Yield (path, stat) for each *.jsonl directly inside `dirs` — and, with
    nested=True, anywhere below them (subagent runs). One scandir per directory
    and one stat per file: the agent monitor walks this every second, and the old
    listdir + isfile + stat paid two syscalls per file. Symlinked subdirectories
    aren't descended, matching os.walk."""
    pending = list(dirs)
    while pending:
        d = pending.pop()
        try:
            with os.scandir(d) as it:
                entries = list(it)
        except OSError:
            continue
        for e in entries:
            if e.name.endswith(".jsonl"):
                try:
                    if not e.is_file():
                        continue
                    st = e.stat()
                except OSError:
                    continue
                yield e.path, st
            elif nested and _is_dir_entry(e, follow=False):
                pending.append(e.path)


def _read_new_lines(path, offset):
    """Yield (line, next_offset) for every complete line after byte `offset` (the
    line keeps its trailing newline, which JSON ignores). A trailing partial line
    is left for the next call; commit `next_offset` as each line is used.

    Reads line by line on purpose. Slurping the file — or even fixed 4 MB chunks —
    makes large, variously-sized transient buffers that macOS's allocator keeps
    after they're freed: a first pass over ~1 GB of transcripts left the daemon's
    memory footprint at ~230 MB (the old slurp: ~415 MB), versus ~50 MB this way,
    for the same CPU."""
    try:
        f = open(path, "rb")
    except OSError:
        return
    with f:
        try:
            f.seek(offset)
            for line in f:
                if not line.endswith(b"\n"):
                    return
                offset += len(line)
                yield line, offset
        except OSError:
            return


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


def _first_line(text, n=140):
    """First meaningful line of an assistant message — what a done row shows."""
    for raw in (text or "").splitlines():
        ln = " ".join(raw.split()).lstrip("#>*` ").rstrip("*` ")
        if ln:
            return ln[:n]
    return None


# Hook events that prove an agent is still moving (cancel a standing stop).
PROGRESS_EVENTS = frozenset(("UserPromptSubmit", "PreToolUse", "PostToolUse",
                             "PostToolUseFailure", "PreCompact", "SubagentStart"))


def _finished(text):
    """A turn's outcome from its final message: the "failed:" / "needs input:"
    convention, else done."""
    for ln in (text or "").splitlines():
        ln = ln.strip().lower()
        if ln.startswith("failed:"):
            return "failed"
        if ln.startswith("needs input:"):
            return "asking"
    return "done"


_RE_PEEK_MODEL = re.compile(rb'"model":"((?:claude-|<)[^"]{1,80})"')
_RE_PEEK_TITLE = re.compile(rb'"(?:aiTitle|agentName)":"((?:[^"\\]|\\.){1,160})"')


def _peek_transcript(path):
    """(model, title) from the tail of a transcript — one bounded read, done
    once per turn, never a parse of the whole file. Either may be None."""
    if not path or _is_protected(path):
        return None, None
    try:
        with open(path, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - PEEK_BYTES))
            tail = f.read()
    except OSError:
        return None, None
    model = title = None
    for m in _RE_PEEK_MODEL.finditer(tail):
        if not m.group(1).startswith(b"<"):     # <synthetic> error notices
            model = m.group(1).decode("utf-8", "replace")
    for m in _RE_PEEK_TITLE.finditer(tail):
        try:
            title = json.loads(b'"' + m.group(1) + b'"')[:160]
        except Exception:  # noqa: BLE001
            pass
    return model, title


class AgentMonitor:
    """Sessions as Claude Code reports them through its hooks (on_event, called
    from the proxy thread), plus a slow liveness tick. Publishes a snapshot with
    the same contract as before, now with live subagents per session."""

    def __init__(self, state):
        self.state = state
        self.lock = threading.Lock()
        self.procs = ProcScanner()
        self._procs_cache = {}
        self._proxy_seen = {}       # kept for _pinned_pids (no lsof latch now)
        cfg = state.cfg
        self.idle_s = float(cfg.get("agent_idle_s", AGENT_IDLE_S))
        self.gone_keep_s = float(cfg.get("agent_gone_keep_s", AGENT_GONE_KEEP_S))
        self.pending_warn_s = float(cfg.get("agent_pending_warn_s",
                                            AGENT_PENDING_WARN_S))
        self.working_warn_s = float(cfg.get("agent_working_warn_s",
                                            AGENT_WORKING_WARN_S))
        self.api_stall_s = float(cfg.get("agent_api_stall_s", AGENT_API_STALL_S))
        self._sess = {}             # session_id -> live record (see _new)
        self._pid_of = {}           # session_id -> pid, from the liveness tick
        self._settings = SettingsCache()
        self._dismissed = set()
        self._events = deque(maxlen=50)
        self._done_today = 0
        self._done_day = datetime.now().strftime("%Y-%m-%d")
        self._git_cache = {}
        self._branch_cache = {}     # git_root -> (branch, read at)
        self.hook_errors = 0
        self._snap = {"sessions": [], "needs_you": [], "collisions": [],
                      "summary": {"working": 0, "needs_you": 0,
                                  "done_today": 0, "top_tier": None,
                                  "unguarded": 0, "pinned": 0},
                      "events": [],
                      "meta": {"source": "hooks", "lsof_ok": True,
                               "parse_errors": 0, "claude_versions": []}}

    # -- events (proxy thread) -------------------------------------------- #
    def on_event(self, ev):
        name, sid = ev.get("hook_event_name"), ev.get("session_id")
        if not name or not sid:
            self.hook_errors += 1
            return
        cwd = ev.get("cwd")
        if cwd and os.path.realpath(cwd) == os.path.realpath(CONFIG_DIR):
            return                      # Tower's own `claude -p /usage` probe
        now = time.time()
        with self.lock:
            s = self._sess.get(sid)
            if s is None:
                s = self._sess[sid] = self._new(sid, now)
            self._apply(s, name, ev, now)
            self._rebuild(now)
        self.state._publish.set()       # front-ends see it within milliseconds

    @staticmethod
    def _new(sid, now):
        return {"sid": sid, "cwd": None, "transcript": None, "model": None,
                "title": None, "last_prompt": None, "status": "idle",
                "since": now, "activity": None, "result": None, "tool": None,
                "pending": None, "last": now, "started": now, "turn_at": None,
                "effort": None, "tools_done": 0, "errors": 0,
                "err_ring": deque(maxlen=10), "files": set(),
                "recent_edits": deque(maxlen=100), "subs": {},
                "subs_total": 0, "ended": False, "peeked": False,
                "task_q": deque(maxlen=16),     # Task/Agent briefs awaiting a start
                "settle": None,         # a needs-you transition still standing
                "awaiting_subs": False,  # turn ended with subagents running
                "cwd0": None,           # first folder seen (the session's home)
                "proc": None}           # (pid, lstart) once matched — sticky

    def _set(self, s, status, now):
        prev = s["status"]
        if status == prev:
            return
        s["status"], s["since"] = status, now
        if prev is not None:
            self._events.append({"t": now, "session_id": s["sid"],
                                 "from": prev, "to": status})
        if status == "done":
            self._done_today += 1
        self._dismissed.discard(s["sid"])   # dismissal lasts until a transition

    @staticmethod
    def _tool(ev, now):
        name = ev.get("tool_name") or "?"
        inp = ev.get("tool_input") if isinstance(ev.get("tool_input"), dict) else {}
        return {"name": name, "detail": _tool_detail(name, inp),
                "desc": inp.get("description") if name == "Bash" else None,
                "since": now}

    def _apply(self, s, name, ev, now):
        s["last"] = now
        for src, dst in (("cwd", "cwd"), ("transcript_path", "transcript"),
                         ("model", "model"), ("session_title", "title")):
            v = ev.get(src)
            if isinstance(v, str) and v:
                s[dst] = v
        if s["cwd0"] is None:
            s["cwd0"] = s["cwd"]
        eff = ev.get("effort")
        if isinstance(eff, dict) and eff.get("level"):
            s["effort"] = _norm_effort(eff.get("level"))
        if not s["peeked"]:
            s["peeked"] = True
            self._peek(s)
        aid = ev.get("agent_id")
        st = s["settle"]
        if st and name in PROGRESS_EVENTS and st["scope"] in ("turn", aid or ""):
            s["settle"] = None          # it moved on: that wasn't a real stop
        if name in PROGRESS_EVENTS and name != "SubagentStart" and not aid:
            s["awaiting_subs"] = False

        if name == "SubagentStart" and aid:
            typ = ev.get("agent_type")
            # The brief the parent wrote when it spawned this one: the oldest
            # queued Task/Agent call of the same type, else the oldest at all.
            q = s["task_q"]
            brief = next((b for b in q if b[0] == typ), None) or (q[0] if q else None)
            if brief:
                q.remove(brief)
            s["subs"][aid] = {"agent_id": aid, "type": typ, "status": "working",
                              "since": now, "started": now,
                              "desc": brief[1] if brief else None,
                              "activity": "starting…", "result": None,
                              "tools": 0}
            s["subs_total"] += 1
            return
        if name == "SubagentStop" and aid:
            sub = s["subs"].setdefault(aid, {"agent_id": aid,
                                             "type": ev.get("agent_type"),
                                             "since": now})
            sub.update(status="done", since=now, activity=None,
                       result=_first_line(ev.get("last_assistant_message")))
            sub.setdefault("started", sub["since"])
            if s["awaiting_subs"] and not any(
                    x.get("status") == "working" for x in s["subs"].values()):
                # The parent ended its turn waiting on these. It usually picks
                # straight back up; if it doesn't, the turn really is done.
                s["awaiting_subs"] = False
                s["activity"] = "reading subagent results…"
                self._defer(s, "done", DONE_AFTER_SUBS_S, "turn", activity=None)
            elif s["awaiting_subs"]:
                n = sum(x.get("status") == "working" for x in s["subs"].values())
                s["activity"] = f"waiting on {n} subagent{'s' if n != 1 else ''}…"
            return
        if name in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
            if name != "PreToolUse":
                self._tool_done(s, ev, now, failed=name == "PostToolUseFailure")
            if aid:                     # inside a subagent: its row, not ours
                sub = s["subs"].setdefault(aid, {
                    "agent_id": aid, "type": ev.get("agent_type"),
                    "status": "working", "since": now, "started": now,
                    "desc": None, "result": None, "tools": 0})
                if name != "PreToolUse":
                    sub["tools"] = sub.get("tools", 0) + 1
                sub["activity"] = (_activity_phrase(self._tool(ev, now))
                                   if name == "PreToolUse" else "thinking…")
                return
            if name == "PreToolUse":
                t = self._tool(ev, now)
                inp = ev.get("tool_input")
                if t["name"] in ("Task", "Agent") and isinstance(inp, dict):
                    s["task_q"].append((inp.get("subagent_type") or "general-purpose",
                                        _first_line(inp.get("description"))))
                s["tool"], s["activity"] = t, _activity_phrase(t)
                if t["name"] == "AskUserQuestion":
                    s["pending"] = t
                    self._set(s, "asking", now)
                else:
                    s["pending"] = None
                    self._set(s, "working", now)
            else:
                s["tool"], s["pending"] = None, None
                s["activity"] = "thinking…"
                self._set(s, "working", now)
            return

        if name == "UserPromptSubmit":
            p = ev.get("prompt")
            if isinstance(p, str) and p.strip():
                s["last_prompt"] = " ".join(p.split())[:300]
            s.update(activity="thinking…", result=None, tool=None, pending=None,
                     turn_at=now)
            s["subs"] = {k: v for k, v in s["subs"].items()
                         if v.get("status") == "working"}
            self._set(s, "working", now)
        elif name == "PermissionRequest":
            t = self._tool(ev, now)
            self._defer(s, "pending_tool", PERM_SETTLE_S, aid or "", pending=t,
                        activity=f"needs approval · {_activity_phrase(t)}")
        elif name == "Notification":
            kind = ev.get("notification_type")
            if kind == "permission_prompt" and s["status"] != "pending_tool" \
                    and not (s["settle"] and s["settle"]["status"] == "pending_tool"):
                self._defer(s, "pending_tool", PERM_SETTLE_S, aid or "",
                            pending=s["pending"] or s["tool"],
                            activity=ev.get("message") or "needs your approval")
            elif kind == "elicitation_dialog":
                s["activity"] = ev.get("message") or "asking you a question"
                self._set(s, "asking", now)
            elif kind == "idle_prompt" and s["status"] in ("working",
                                                           "pending_tool"):
                # Claude is sitting at its prompt. An interrupted turn (Esc)
                # fires no Stop, so this is what settles it — quietly.
                s.update(tool=None, pending=None, activity=None)
                self._set(s, "idle", now)
        elif name == "Stop":
            s["task_q"].clear()
            msg = ev.get("last_assistant_message")
            s.update(tool=None, pending=None, result=_first_line(msg))
            self._peek(s)
            running = sum(x.get("status") == "working" for x in s["subs"].values())
            if running:
                # Subagents still out: the turn resumes when they report back.
                s["awaiting_subs"] = True
                s["activity"] = f"waiting on {running} subagent{'s' if running != 1 else ''}…"
            else:
                outcome = _finished(msg)
                s["activity"] = "wrapping up…"
                if outcome == "failed":
                    s["activity"] = None
                    self._set(s, outcome, now)
                else:
                    self._defer(s, outcome, DONE_SETTLE_S, "turn", activity=None)
        elif name == "StopFailure":
            s.update(tool=None, pending=None,
                     activity=(_first_line(ev.get("last_assistant_message"))
                               or f"API error · {ev.get('error') or 'unknown'}"))
            self._set(s, "failed", now)
        elif name == "PreCompact":
            s["activity"] = "compacting context…"
            self._set(s, "working", now)
        elif name == "PostCompact":
            if s["status"] == "working":
                s["activity"] = "thinking…"
        elif name == "SessionStart":
            if ev.get("source") != "compact":
                s.update(ended=False, activity=None, tool=None, pending=None)
                self._set(s, "idle", now)
        elif name == "SessionEnd":
            s.update(ended=True, tool=None, pending=None, activity=None)
            self._set(s, "gone", now)

    def _defer(self, s, status, wait, scope, **fields):
        """Stage a needs-you transition; it lands only if nothing in `scope`
        ("turn" = anything, "" = the main agent, else a subagent id) moves on
        within `wait` seconds. Caller holds the lock."""
        tok = object()
        s["settle"] = {"tok": tok, "status": status, "scope": scope,
                       "fields": fields}
        t = threading.Timer(wait, self._settle, (s["sid"], tok))
        t.daemon = True
        t.start()

    def _settle(self, sid, tok):
        try:
            with self.lock:
                s = self._sess.get(sid)
                st = s and s["settle"]
                if not st or st["tok"] is not tok or s["status"] in ("gone",
                                                                      "failed"):
                    return
                now = time.time()
                s["settle"] = None
                s.update(st["fields"])
                self._set(s, st["status"], now)
                self._rebuild(now)
            self.state._publish.set()
        except Exception as e:  # noqa: BLE001
            log(f"agents settle error: {e}")

    def _tool_done(self, s, ev, now, failed):
        s["tools_done"] += 1
        interrupted = bool(ev.get("is_interrupt"))
        s["err_ring"].append(failed and not interrupted)
        if failed and not interrupted:
            s["errors"] += 1
        name = ev.get("tool_name")
        inp = ev.get("tool_input") if isinstance(ev.get("tool_input"), dict) else {}
        fp = inp.get("file_path") or inp.get("notebook_path")
        if name in EDIT_TOOLS and fp and not failed:
            s["files"].add(fp)
            s["recent_edits"].append((now, fp))

    def _peek(self, s):
        model, title = _peek_transcript(s.get("transcript"))
        if model:
            s["model"] = model
        if title:
            s["title"] = title

    # -- liveness tick (own thread) --------------------------------------- #
    def loop(self, interval=AGENT_TICK_S):
        while not self.state.stop.is_set():
            try:
                self.tick()
            except Exception as e:  # noqa: BLE001
                log(f"agents tick error: {e}")
            self.state.stop.wait(interval)

    def tick(self):
        now = time.time()
        day = datetime.now().strftime("%Y-%m-%d")
        procs = self.procs.scan()
        self._procs_cache = procs
        live = {pid: p for pid, p in procs.items() if p["kind"] != "infra"}
        with self.lock:
            if day != self._done_day:   # done_today counts since local midnight
                self._done_day, self._done_today = day, 0
            self._pid_of = self._match(live, now)
            for sid, s in list(self._sess.items()):
                pid = self._pid_of.get(sid)
                if pid:
                    paused = procs[pid].get("stopped")
                    if paused and s["status"] != "paused":
                        s["unpause_to"] = s["status"]
                        self._set(s, "paused", now)
                    elif not paused and s["status"] == "paused":
                        self._set(s, s.pop("unpause_to", None) or "working", now)
                elif s.get("proc_gone") and s["status"] != "gone":
                    # Its own process exited without a SessionEnd (terminal
                    # closed, Ctrl-C, kill). That's an ending, not a failure.
                    s.update(ended=True, tool=None, pending=None, activity=None)
                    self._set(s, "gone", now)
                if s["status"] == "done" and now - s["since"] > self.idle_s:
                    self._set(s, "idle", now)
                for aid, sub in list(s["subs"].items()):
                    if sub.get("status") != "working" and \
                            now - sub.get("since", now) > self.gone_keep_s:
                        del s["subs"][aid]
                if (s["status"] == "gone" and now - s["since"] > self.gone_keep_s) \
                        or (not pid and now - s["last"] > AGENT_FORGET_S):
                    del self._sess[sid]
            self._rebuild(now)
        self.state._publish.set()

    def _match(self, live, now):
        """session_id -> pid. Sticky: a session keeps the exact process it was
        matched to (same pid AND start time) for as long as that process lives —
        its folder may wander (`cd`), the process's never does. New matches: a
        process whose args name the session, else by folder — the process's cwd
        is the session's home or an ancestor of where it is now."""
        out, taken = {}, set()
        for sid, s in self._sess.items():
            pr = s.get("proc")
            if not pr:
                continue
            p = live.get(pr[0])
            if p and p.get("lstart") == pr[1]:
                out[sid] = pr[0]
                taken.add(pr[0])
            elif now - s["last"] > LIVE_EVENT_S:
                s["proc"], s["proc_gone"] = None, True   # its process exited
            else:
                s["proc"] = None        # events still flowing: just re-match
        for p in live.values():
            if p["pid"] in taken:
                continue
            sid = (p.get("session_id")
                   or (os.path.basename(p["transcript"])[:-len(".jsonl")]
                       if p.get("transcript") else None))
            if sid and sid.lower() in self._sess and sid.lower() not in out:
                out[sid.lower()] = p["pid"]
                taken.add(p["pid"])

        def _under(child, root):
            return bool(child and root) and (
                child == root or child.startswith(root.rstrip("/") + "/"))

        free = sorted((p for p in live.values() if p["pid"] not in taken),
                      key=lambda p: p.get("lstart") or 0)
        waiting = sorted((s for sid, s in self._sess.items()
                          if sid not in out and not s["ended"]),
                         key=lambda s: s["started"])
        for p in free:
            pcwd = self.procs.cwd_of(p["pid"])
            if not pcwd:
                continue
            # Prefer the session whose home IS this folder, then one below it.
            pick = (next((s for s in waiting if s["cwd0"] == pcwd), None)
                    or next((s for s in waiting
                             if _under(s["cwd0"], pcwd) or _under(s["cwd"], pcwd)),
                            None))
            if pick:
                out[pick["sid"]] = p["pid"]
                taken.add(p["pid"])
                waiting.remove(pick)
        for sid, pid in out.items():
            s = self._sess[sid]
            s["proc"] = (pid, live[pid].get("lstart"))
            s.pop("proc_gone", None)
        self._unmatched = [p for p in live.values() if p["pid"] not in taken]
        return out

    # -- snapshot --------------------------------------------------------- #
    def _rebuild(self, now):
        procs = self._procs_cache or {}
        rows = [self._row(s, procs.get(self._pid_of.get(sid)), now)
                for sid, s in self._sess.items()]
        # A live claude process with no hook traffic yet (opened before Tower,
        # or idle since): still a row, so counts and warnings stay truthful.
        for p in getattr(self, "_unmatched", []):
            rows.append(self._placeholder(p, now))
        rows.sort(key=lambda r: -(r["last_activity"] or 0))
        needs = [{"session_id": r["session_id"], "reason": r["status"],
                  "since": r["status_since"]}
                 for r in rows
                 if r["status"] in NEEDS_RANK and not r["dismissed"]]
        needs.sort(key=lambda n: (NEEDS_RANK[n["reason"]], n["since"] or 0))
        working = [r for r in rows if r["status"] in ("working", "pending_tool")]
        tiers = [MODEL_TIERS.index(r["model_family"]) for r in working
                 if r["model_family"] in MODEL_TIERS]
        # Guard-coverage counts: unguarded = live agents started before the guard
        # while routing is on; pinned = live agents still guarded by a proxy the
        # user has since turned off. Only definite verdicts count.
        routed_now = bool(self.state.routed and self.state.routing_now)
        live = [r for r in rows if r.get("pid") and r["status"] != "gone"]
        summary = {
            "working": len(working), "needs_you": len(needs),
            "done_today": self._done_today,
            "top_tier": MODEL_TIERS[max(tiers)] if tiers else None,
            "unguarded": sum(1 for r in live if r.get("guarded") is False)
            if routed_now else 0,
            "pinned": sum(1 for r in live if r.get("guarded") is True)
            if not routed_now else 0}
        self._snap = {"sessions": rows, "needs_you": needs,
                      "collisions": self._collisions(rows, now),
                      "summary": summary, "events": list(self._events),
                      "meta": {"source": "hooks", "lsof_ok": True,
                               "parse_errors": self.hook_errors,
                               "claude_versions": []}}

    def _row(self, s, p, now):
        # The session's home: its process's folder (fixed for life), else the
        # first folder it reported — not wherever a `cd` has taken it since.
        cwd = (self.procs.cwd_of(p["pid"]) if p else None) or s["cwd0"] or s["cwd"]
        git_root = self._git_root_of(cwd)
        model = s["model"] or self._configured_model(cwd, git_root)
        fam = _model_family(model)
        status = s["status"]
        tty = p.get("tty") if p else None
        subs = sorted(s["subs"].values(), key=lambda x: x.get("since") or 0)
        return {
            "session_id": s["sid"],
            "pid": p["pid"] if p else None,
            "kind": p["kind"] if p else "interactive",
            "model": model,
            "model_family": fam,
            "effort": s["effort"] or self._effort_of(cwd, git_root),
            "context": self._ctx_tag_of(cwd, git_root, fam),
            "project_name": os.path.basename(cwd) if cwd else None,
            "cwd": cwd,
            "git_root": git_root,
            "git_branch": self._branch_of(git_root, now),
            "title": s["title"],
            "last_prompt": s["last_prompt"],
            "status": status,
            "status_since": s["since"],
            "turn_at": s["turn_at"],
            "activity": s["activity"] if status not in ("done", "idle", "gone")
            else None,
            "result": s["result"],
            "pending_tool": ({k: s["pending"].get(k) for k in
                              ("name", "detail", "since")}
                             if s["pending"] and status in ("pending_tool", "asking")
                             else None),
            "tty": tty,
            "focusable": bool(p and p["kind"] == "interactive" and tty),
            "guarded": guarded_at(self.state.cfg, p.get("lstart")) if p else None,
            "last_activity": s["last"],
            "started": (p.get("lstart") if p else None) or s["started"],
            "ticks": {"tools_done": s["tools_done"], "files": len(s["files"]),
                      "errors": s["errors"], "subagents": s["subs_total"]},
            "subagents": [{k: x.get(k) for k in ("agent_id", "type", "status",
                                                  "activity", "result", "since",
                                                  "started", "desc", "tools")}
                          for x in subs],
            "health": self._health(s, status, now),
            "dismissed": s["sid"] in self._dismissed,
        }

    def _placeholder(self, p, now):
        cwd = self.procs.cwd_of(p["pid"])
        git_root = self._git_root_of(cwd)
        model = self._configured_model(cwd, git_root)
        sid = p.get("session_id") or f"pid-{p['pid']}"
        return {
            "session_id": sid, "pid": p["pid"], "kind": p["kind"],
            "model": model, "model_family": _model_family(model),
            "effort": self._effort_of(cwd, git_root), "context": None,
            "project_name": os.path.basename(cwd) if cwd else None,
            "cwd": cwd, "git_root": git_root,
            "git_branch": self._branch_of(git_root, now), "title": None,
            "last_prompt": None,
            "status": "paused" if p.get("stopped") else "idle",
            "status_since": p.get("lstart"), "activity": None, "result": None,
            "pending_tool": None, "tty": p.get("tty"),
            "focusable": bool(p["kind"] == "interactive" and p.get("tty")),
            "guarded": guarded_at(self.state.cfg, p.get("lstart")),
            "last_activity": p.get("lstart"), "started": p.get("lstart"),
            "ticks": {"tools_done": 0, "files": 0, "errors": 0, "subagents": 0},
            "subagents": [], "health": {"level": "ok", "reasons": []},
            "dismissed": sid in self._dismissed,
        }

    def _health(self, s, status, now):
        if status == "paused":
            return {"level": "ok", "reasons": []}   # user-suspended, not a fault
        reasons = []
        ring = list(s["err_ring"])
        errs = sum(1 for e in ring if e)
        if errs >= 3:
            reasons.append(f"{errs} failed tool calls in last {len(ring)} results")
        if status == "pending_tool" and now - s["since"] > self.pending_warn_s:
            reasons.append(
                f"waiting for approval over {int(self.pending_warn_s // 60)} min")
        if status == "working":
            quiet = now - s["last"]
            if not s["tool"] and quiet > self.api_stall_s:
                reasons.append(f"no activity for {int(quiet)}s — "
                               "possible API error or network stall")
            if now - (s["turn_at"] or s["since"]) > self.working_warn_s:
                reasons.append(f"no completed turn in over "
                               f"{int(self.working_warn_s // 60)} min")
        return {"level": "warn" if reasons else "ok", "reasons": reasons}

    def _collisions(self, rows, now):
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
                s = self._sess.get(r["session_id"]) or {}
                for fp in {fp for t, fp in (s.get("recent_edits") or ())
                           if now - t <= AGENT_EDIT_WINDOW_S}:
                    fcount[fp] += 1
            shared = sorted(fp for fp, c in fcount.items() if c >= 2)
            out.append({"git_root": root,
                        "session_ids": [r["session_id"] for r in grp],
                        "level": "file" if shared else "repo",
                        "files": shared})
        return out

    def _branch_of(self, git_root, now):
        if not git_root:
            return None
        hit = self._branch_cache.get(git_root)
        if hit and now - hit[1] < 10:
            return hit[0]
        b = _git_branch_of(git_root)
        self._branch_cache[git_root] = (b, now)
        return b

    def _configured_model(self, cwd, git_root):
        """The model the settings cascade selects — the fallback until a
        session's own transcript names its model."""
        def _m(d):
            return d.get("model") if isinstance(d, dict) else None
        mid = _m(self._settings.get(CLAUDE_SETTINGS))
        base = git_root or cwd
        if base and not _is_protected(base):
            for name in ("settings.json", "settings.local.json"):
                v = _m(self._settings.get(os.path.join(base, ".claude", name)))
                if v:
                    mid = v
        return mid

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

    def working_count(self):
        with self.lock:
            return self._snap["summary"]["working"]

    # -- services for dispatch() ------------------------------------------ #
    def dismiss(self, session_id, on=True):
        with self.lock:
            if on:
                self._dismissed.add(session_id)
            else:
                self._dismissed.discard(session_id)
            self._rebuild(time.time())
        self.state._publish.set()
        return {"ok": True, "dismissed": bool(on)}

    def focus(self, session_id):
        """Bring the session's terminal tab frontmost. Never raises.

        Linux has no osascript/Terminal.app to ask and no portable way to raise
        an arbitrary terminal emulator's tab, so tmux is the only real path
        there; anything else answers with the resume fallback."""
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
            if not IS_LINUX:
                try:
                    r = subprocess.run(["osascript", "-e", script],
                                       capture_output=True, text=True,
                                       timeout=15)
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
            if not IS_LINUX and os.path.isdir("/Applications/iTerm.app"):
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
USAGE_RECALC_S = 60.0   # rebuild an unchanged view at most this often (decay)
USAGE_SERIES_DAYS = 7   # the day series; the week (since Monday) always fits inside


class UsageIndex:
    """The local token / cost estimate, read from Claude Code's transcripts.

    Work is proportional to what CHANGED, never to history — this runs every 8s
    for weeks, over a corpus that only grows:
      · each transcript is offset-tailed: only newly appended lines are parsed
        (the old reader re-parsed a whole 50 MB live transcript on every append);
      · a file untouched since the reporting window opened can't move any number
        we report (its rows are all older), so it is never parsed or held;
      · rows are bucketed by comparing epochs against precomputed local-midnight
        boundaries — no datetime conversion per row.
    Claude Code writes one JSONL line per content block (thinking / text /
    tool_use), each repeating the message's usage — and output_tokens grows on
    later lines of the same message. So rows are keyed by message id, last line
    wins; summing every line counted a turn two to five times over."""

    def __init__(self, state):
        self.state = state
        self.lock = threading.Lock()
        # path -> {"mtime", "size", "ino", "offset", "rows": {key: row}}
        self._files = {}
        self.snapshot = self._empty()
        self._calc_key, self._calc_ts = None, 0.0

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
            self.state.stop.wait(interval)

    def _scan(self, window_start):
        """Bring every transcript written since `window_start` up to date and
        forget the rest (their rows all predate the window)."""
        try:
            dirs = _project_dirs()
        except OSError:
            return False                # keep the last view on a transient error
        changed = False
        seen = set()
        for path, st in _iter_transcripts(dirs, nested=True):
            if st.st_mtime < window_start:
                continue
            seen.add(path)
            rec = self._files.get(path)
            if (rec is not None and rec["mtime"] == st.st_mtime
                    and rec["size"] == st.st_size):
                continue
            if (rec is None or st.st_size < rec["offset"]
                    or st.st_ino != rec["ino"]):
                # new, shrunk, or replaced by another file: read from the top
                rec = {"mtime": 0.0, "size": 0, "ino": st.st_ino, "offset": 0,
                       "rows": {}}
                self._files[path] = rec
            self._tail(path, rec)
            rec["mtime"] = st.st_mtime
            rec["size"] = st.st_size
            changed = True
        for path in list(self._files):
            if path not in seen:
                del self._files[path]
                changed = True
        return changed

    def _tail(self, path, rec):
        rows = rec["rows"]
        for line, nxt in _read_new_lines(path, rec["offset"]):
            start, rec["offset"] = rec["offset"], nxt
            if b'"usage"' not in line:
                continue
            try:
                key, row = self._row(json.loads(line.decode("utf-8", "replace")))
            except Exception:  # noqa: BLE001 — drifting format: skip the line
                continue
            if row is not None:
                # later lines of a message carry its final usage → last wins
                rows[key if key is not None else ("@", start)] = row

    @staticmethod
    def _row(o):
        """(message id or None, row) for a line carrying real model usage, else
        (None, None). row = (epoch, model, total, cost, in, out, cache, sid)."""
        if not isinstance(o, dict):
            return None, None
        msg = o.get("message")
        if not isinstance(msg, dict):
            return None, None
        u = msg.get("usage")
        if not isinstance(u, dict):
            return None, None
        epoch = _parse_ts(o.get("timestamp"))
        model = msg.get("model") or "unknown"
        if epoch is None or model.startswith("<"):     # <synthetic> error notice
            return None, None
        ti = int(u.get("input_tokens", 0) or 0)
        to = int(u.get("output_tokens", 0) or 0)
        cw = int(u.get("cache_creation_input_tokens", 0) or 0)
        cr = int(u.get("cache_read_input_tokens", 0) or 0)
        mid = msg.get("id")
        return (mid if isinstance(mid, str) and mid else None,
                (epoch, model, ti + to + cw + cr, _cost(model, ti, to, cw, cr),
                 ti, to, cw + cr, o.get("sessionId") or ""))

    def refresh(self):
        # Local-midnight boundaries via mktime, so a DST change inside the window
        # still buckets every row on its true local day.
        today = datetime.now().date()
        days = [today - timedelta(days=i)
                for i in range(USAGE_SERIES_DAYS - 1, -1, -1)]
        day_starts = [time.mktime(d.timetuple()) for d in days]
        tomorrow = time.mktime((today + timedelta(days=1)).timetuple())
        today_start = day_starts[-1]
        week_start = time.mktime(
            (today - timedelta(days=today.weekday())).timetuple())
        changed = self._scan(min(day_starts[0], week_start))
        now_e = time.time()
        # Nothing appended and the day hasn't turned: every number is the same
        # except the time-decaying ones (live tokens/min, pace), which only need
        # a refresh once a minute. Skip the full re-merge until then.
        key = (today_start, self.state.plan_week_tokens)
        if (not changed and key == self._calc_key
                and now_e - self._calc_ts < USAGE_RECALC_S):
            return
        self._calc_key, self._calc_ts = key, now_e
        elapsed_frac = max((now_e - week_start) / (7 * 86400.0), 1e-3)

        # One row per message: a subagent transcript can repeat a message its
        # parent logged too — keep the most complete copy.
        merged = {}
        for path, rec in self._files.items():
            for key, row in rec["rows"].items():
                if isinstance(key, tuple):          # no message id: line-unique
                    key = (path, key[1])
                cur = merged.get(key)
                if cur is None or row[5] >= cur[5]:
                    merged[key] = row

        snap = self._empty()
        bm_tok = defaultdict(int)
        bm_cost = defaultdict(float)
        active = set()
        s_tok = [0] * len(days)
        s_cost = [0.0] * len(days)
        live = 0
        latest_sid, latest_e = None, -1.0
        for epoch, model, total, cost, _ti, _to, _cache, sid in merged.values():
            if epoch > latest_e:
                latest_e, latest_sid = epoch, sid
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
            if day_starts[0] <= epoch < tomorrow:
                i = bisect.bisect_right(day_starts, epoch) - 1
                s_tok[i] += total
                s_cost[i] += cost
        s = snap["session"]
        for epoch, _model, total, cost, ti, to, cache, sid in merged.values():
            if sid != latest_sid:
                continue
            s["tokens"] += total
            s["input"] += ti
            s["output"] += to
            s["cache"] += cache
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
        snap["series"] = [{"day": d.strftime("%Y-%m-%d"), "tokens": s_tok[i],
                           "cost": round(s_cost[i], 2)}
                          for i, d in enumerate(days)]
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
# Absolute claude executables seen in the process table — the Chrome native host,
# for one, is always launched by full path. The last-resort lookup hint below.
_SEEN_CLAUDE_EXES = deque(maxlen=8)
_seen_exes_lock = threading.Lock()


def _note_claude_exe(exe):
    if os.path.isabs(exe):
        with _seen_exes_lock:
            if exe not in _SEEN_CLAUDE_EXES:
                _SEEN_CLAUDE_EXES.append(exe)


def _version_dirs(parent):
    """Version-named subdirectories of `parent` (v24.18.1, 22.3.0 …), newest
    first; [] when `parent` doesn't exist."""
    try:
        names = [n for n in os.listdir(parent) if re.search(r"\d", n)]
    except OSError:
        return []
    names.sort(key=lambda n: tuple(int(x) for x in re.findall(r"\d+", n)),
               reverse=True)
    return [os.path.join(parent, n) for n in names]


def _claude_candidates():
    """Where Claude Code actually gets installed, most specific first. The menu-bar
    app launches the daemon with launchd's bare PATH (/usr/bin:/bin:/usr/sbin:
    /sbin), so shutil.which can't see a CLI in ~/.local/bin or a Node version
    manager — and asking a login shell is out: sourcing the user's rc is exactly
    what trips TCC prompts. So look where installers put it (plain stats only)."""
    h = HOME
    out = [os.path.join(h, ".local", "bin", "claude"),      # native installer
           os.path.join(h, ".claude", "local", "claude"),   # legacy local install
           "/opt/homebrew/bin/claude", "/usr/local/bin/claude", "/usr/bin/claude",
           os.path.join(h, ".npm-global", "bin", "claude"),
           "/snap/bin/claude",                              # Snap (Linux)
           os.path.join(h, ".volta", "bin", "claude"),
           os.path.join(h, ".bun", "bin", "claude"),
           os.path.join(h, "Library", "pnpm", "claude"),
           os.path.join(h, ".local", "share", "pnpm", "claude"),
           os.path.join(h, ".yarn", "bin", "claude")]
    # npm installs under a Node version manager: its default alias, then every
    # installed Node, newest first.
    fnm_roots = (os.environ.get("FNM_DIR"),
                 os.path.join(h, ".local", "share", "fnm"),
                 os.path.join(h, "Library", "Application Support", "fnm"),
                 os.path.join(h, ".fnm"))
    for root in dict.fromkeys(r for r in fnm_roots if r):
        out.append(os.path.join(root, "aliases", "default", "bin", "claude"))
        out += [os.path.join(v, "installation", "bin", "claude")
                for v in _version_dirs(os.path.join(root, "node-versions"))]
    nvm = os.environ.get("NVM_DIR") or os.path.join(h, ".nvm")
    out += [os.path.join(v, "bin", "claude")
            for v in _version_dirs(os.path.join(nvm, "versions", "node"))]
    out += [os.path.join(h, ".asdf", "shims", "claude"),
            os.path.join(h, ".local", "share", "mise", "shims", "claude")]
    with _seen_exes_lock:
        out += list(_SEEN_CLAUDE_EXES)
    return out


def _is_exe(p):
    return os.path.isfile(p) and os.access(p, os.X_OK)


def find_claude(cfg=None):
    """The claude CLI to run /usage with. Resolved fresh on every fetch (a few
    stats), so an upgrade, a Node version switch, or a PATH entry that only lived
    as long as its shell (fnm's per-shell links) never strands the plan meters.
    `claude_path` in ~/.tower/config.json overrides the search."""
    override = (cfg or {}).get("claude_path")
    if isinstance(override, str) and override:
        override = os.path.expanduser(override)
        if _is_exe(override):
            return override
    p = shutil.which("claude")
    if p:
        return p
    if IS_WINDOWS:
        for c in (os.path.join(HOME, ".claude", "local", "claude.exe"),
                  os.path.join(HOME, ".claude", "local", "claude.cmd")):
            if os.path.exists(c):
                return c
        return None
    for c in _claude_candidates():
        if _is_exe(c):
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
    m = re.search(r"currently using your (\w[\w ]*?) to power", out)
    if m:
        res["billing"] = m.group(1).strip()        # "subscription", "API key", …
    try:
        windows = _parse_usage_contrib(out)
        if windows:
            res["windows"] = windows
    except Exception:  # noqa: BLE001 — the report is undocumented; never fail /usage on it
        pass
    return res


def _parse_usage_contrib(out):
    """The "What's contributing to your limits usage?" report, per window:
        Last 7d · 29123 requests · 18 sessions
          99%  Give "y-builder" subagents a cheaper model
          Top subagents: y-builder 58%, y-risk 10%
    → {"7d": {"requests", "sessions", "tips": [{"pct", "text", "hint"}],
              "top": {"skills"|"subagents"|"mcp_servers"|…: [{"name", "pct"}]}}}.
    Approximate, this machine only, shares overlap (Claude's own caveat) — the
    front-ends say so. Line-by-line and forgiving: unknown lines are skipped."""
    windows, cur = {}, None
    for raw in out.splitlines():
        line = raw.strip()
        m = re.match(r"Last\s+(\w+)\s*·\s*(\d+)\s*requests\s*·\s*(\d+)\s*sessions", line)
        if m:
            cur = {"requests": int(m.group(2)), "sessions": int(m.group(3)),
                   "tips": [], "top": {}}
            windows[m.group(1)] = cur
            continue
        if cur is None or not line:
            continue
        m = re.match(r"(\d+)%\s+(.+)$", line)
        if m:
            text, _, hint = m.group(2).partition(" · ")
            cur["tips"].append({"pct": int(m.group(1)), "text": text.strip(),
                                "hint": hint.strip() or None})
            continue
        m = re.match(r"Top\s+([\w ]+?):\s*(.+)$", line)
        if m:
            key = re.sub(r"\W+", "_", m.group(1).strip().lower())
            items = []
            for part in m.group(2).split(","):
                pm = re.match(r"\s*(.+?)\s+(\d+)%\s*$", part)
                if pm:
                    items.append({"name": pm.group(1), "pct": int(pm.group(2))})
            if items:
                cur["top"][key] = items
    return windows


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


def _claude_env(claude=None):
    """Env for a hermetic `claude -p /usage` (see USAGE_NORC_DIR above):
    - strip Claude-Code *nesting* vars (else a nested /usage prints run-stats
      instead of the usage report),
    - neutralise every shell's rc sourcing — the Photos/Music/Contacts TCC
      trigger — via an empty ZDOTDIR and blanked ENV/BASH_ENV,
    - keep a sane PATH (helpers, plus the CLI's own directory: a JS-shim install
      under nvm/fnm/volta runs `#!/usr/bin/env node`, and that node lives beside
      it) and HOME (claude's own auth in ~/.claude)."""
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
    if IS_LINUX:
        # No Homebrew; do include ~/.local/bin and /snap/bin, which is where a
        # user-scoped node/claude lives and which a systemd unit's PATH omits.
        extra = [os.path.join(HOME, ".local", "bin"), "/usr/local/bin",
                 "/usr/bin", "/bin", "/snap/bin"]
    else:
        extra = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"]
    if claude:
        own = [os.path.dirname(claude), os.path.dirname(os.path.realpath(claude))]
        extra = list(dict.fromkeys(own + extra))
    have = env.get("PATH", "").split(os.pathsep)
    env["PATH"] = os.pathsep.join([p for p in extra if p not in have] + have)
    return env


# CLIs that rejected --no-session-persistence (older builds): probe those without
# it rather than failing /usage forever.
_NO_PERSIST_UNSUPPORTED = set()


def fetch_plan(cfg=None):
    claude = find_claude(cfg)
    if not claude:
        return {"ok": False, "error": "claude CLI not found"}
    env = _claude_env(claude)
    argv = [claude, "-p", "/usage",
            "--strict-mcp-config", "--mcp-config", USAGE_MCP_FILE,
            # No hooks for the probe: it must not appear as an agent, and it
            # doesn't need to POST a dozen lifecycle events every minute.
            "--settings", '{"disableAllHooks": true}']
    # Never save the probe as a session: persisted, each run left a transcript in
    # ~/.claude/projects (PROBE_PROJECT_DIR) — about 1,400 a day, forever.
    if claude not in _NO_PERSIST_UNSUPPORTED:
        argv.append("--no-session-persistence")
    # A Windows `claude` on PATH is usually a `claude.cmd` npm shim; CreateProcess
    # can't exec a batch file directly (WinError 193), so run it through cmd /c.
    if IS_WINDOWS and claude.lower().endswith((".cmd", ".bat")):
        argv = ["cmd", "/c"] + argv
    # Once a minute, all day: run it on the efficiency cores (background QoS
    # clamp) — it's a ~1s CLI boot nobody waits on — and skip the CLI's
    # auto-update check and telemetry, which /usage doesn't need.
    if os.path.exists(TASKPOLICY):
        argv = [TASKPOLICY, "-c", "background"] + argv
    env.update(DISABLE_AUTOUPDATER="1", DISABLE_TELEMETRY="1",
               DISABLE_ERROR_REPORTING="1")
    last = {"ok": False, "error": "could not parse /usage output"}
    # `claude -p /usage` occasionally returns a run-stats blob instead of the
    # usage report; retry a few times so one bad response doesn't fail the cycle.
    for _ in range(3):
        try:
            r = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL, capture_output=True,
                timeout=90, env=env, cwd=CONFIG_DIR,
                # neutral cwd above: never let claude scan a protected folder it
                # inherited. Windows: the console-less daemon would flash a
                # console window each poll — suppress it; and decode UTF-8 so
                # unicode / box glyphs in the report don't mojibake.
                **({"creationflags": subprocess.CREATE_NO_WINDOW,
                    "encoding": "utf-8", "errors": "replace"}
                   if IS_WINDOWS else {"text": True}))

            out = (r.stdout or "") + "\n" + (r.stderr or "")
            if ("--no-session-persistence" in argv
                    and "unknown option" in out.lower()
                    and "no-session-persistence" in out):
                _NO_PERSIST_UNSUPPORTED.add(claude)
                argv = [a for a in argv if a != "--no-session-persistence"]
                continue
            res = parse_usage(out)
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
    logged = None           # log a fetch outcome only when it changes, not 1,440×/day
    while not state.stop.is_set():
        if not state.plan_enabled:
            # Live plan-fetching off → never run claude (no Photos/Music prompts).
            with state.lock:
                state.plan = {"ok": False, "disabled": True}
            if state._refreshplan.wait(2.0):
                state._refreshplan.clear()
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
            if state._refreshplan.wait(2.0):
                state._refreshplan.clear()
            continue
        with state.lock:
            if state.plan and state.plan.get("ok"):
                state.plan = {**state.plan, "refreshing": True}
        res = fetch_plan(state.cfg)
        with state.lock:
            if res.get("ok"):
                state.plan = res                       # fresh; flags cleared
            elif state.plan and state.plan.get("ok"):
                state.plan = {**state.plan, "refreshing": False,
                              "error": res.get("error")}
            else:
                state.plan = {"ok": False, "refreshing": False,
                              "error": res.get("error"), "checked": time.time()}
        outcome = "ok" if res.get("ok") else res.get("error")
        if outcome != logged:
            log(f"plan fetch: {outcome}")
            logged = outcome
        if state._refreshplan.wait(interval):   # sleep, unless asked to refresh
            state._refreshplan.clear()


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
# "Retrying in Ns · attempt x/y" spinner instead of erroring the turn. (Claude
# Code words a 503 CONNECT reply as "Couldn't connect through your proxy
# (ERR_PROXY_TUNNEL) — the proxy refused the tunnel…" in that spinner; it is
# still retried — only a 407 or a TLS cert error is fatal.) The watchdog
# unlocks a long budget, so the agent stays PENDING across a whole outage and
# resumes on its own when the guard clears. Never overwrites a user-set value,
# and removed on route_off only if the value is still ours.
#
# The first-byte window is the same idea for slow paths. A long chat sends a
# multi-megabyte request; over a high-latency link (a far VPN exit) the upload
# plus prefill can outlast Claude Code's default wait for response headers
# (3 min + 1 s per 32 KB of body). It then ABORTS the attempt — discarding the
# upload — and allows only one retry before failing the turn: "No response from
# the API after … A proxy or gateway that buffers streaming responses can cause
# this". Tower's tunnel relays bytes as they arrive (it can't buffer TLS), so the
# honest fix is patience: wait up to Claude's own request ceiling (API_TIMEOUT_MS,
# 10 min by default, which caps this value). A tunnel that is actually dead is
# still cut within ~2 min at the TCP layer (UPSTREAM_KEEPIDLE_S), so the long
# wait only ever applies to a path that is slow, never to one that is gone.
#
# The budget is per request, and Claude Code backs off to ~32 s between attempts
# (plus our BLOCK_HOLD_S), so each attempt costs ~40 s of wall clock. 300 lasted
# ~3.5 h: an overnight outage exhausted it and failed a whole unattended
# multi-agent run at once. 1500 rides out ~17 h, so a 12 h+ session outlasts any
# outage it would plausibly see. The watchdog lifts the usual clamp of 15.
RETRY_ENV = {
    "CLAUDE_CODE_RETRY_WATCHDOG": "1",     # unlock the long retry budget
    "CLAUDE_CODE_MAX_RETRIES": "1500",     # attempts before the turn finally errors
    "CLAUDE_STREAM_FIRST_BYTE_TIMEOUT_MS": "600000",   # slow ≠ dead: see above
}
# Values earlier Tower versions installed. They are ours, not a user
# customisation, so route_on upgrades them in place and route_off removes them.
RETRY_ENV_PRIOR = {
    "CLAUDE_CODE_MAX_RETRIES": ("300",),
}


def _retry_env_ours(k, v):
    return v == RETRY_ENV.get(k) or v in RETRY_ENV_PRIOR.get(k, ())


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
        if k not in env or _retry_env_ours(k, env[k]):
            env[k] = v
    data["env"] = env
    try:
        os.makedirs(os.path.dirname(CLAUDE_SETTINGS), exist_ok=True)
        _atomic_write(CLAUDE_SETTINGS, json.dumps(data, indent=2) + "\n")
        return True
    except OSError as e:
        log(f"route_on failed: {e}")
        return False


def _is_our_hook(h):
    return (isinstance(h, dict) and h.get("type") == "http"
            and HOOK_PATH in str(h.get("url", "")))


def _strip_our_hooks(hooks):
    """hooks dict without Tower's entries (user hooks untouched). -> (new, n)"""
    out, n = {}, 0
    for ev, groups in hooks.items():
        if not isinstance(groups, list):
            out[ev] = groups
            continue
        kept = []
        for g in groups:
            hs = g.get("hooks") if isinstance(g, dict) else None
            if isinstance(hs, list) and any(_is_our_hook(h) for h in hs):
                rest = [h for h in hs if not _is_our_hook(h)]
                n += len(hs) - len(rest)
                if not rest:
                    continue
                g = {**g, "hooks": rest}
            kept.append(g)
        if kept:
            out[ev] = kept
    return out, n


def hooks_on(proxy_port):
    """Point Claude Code's lifecycle hooks at this daemon (observation only).
    Idempotent: rewrites only when an entry is missing or carries an old port.
    Claude's settings watcher picks the change up in running sessions too."""
    url = f"http://127.0.0.1:{proxy_port}{HOOK_PATH}"
    data = _read_settings()
    cur = data.get("hooks") if isinstance(data.get("hooks"), dict) else {}
    want = {"type": "http", "url": url, "timeout": HOOK_TIMEOUT_S}
    if all(any(isinstance(g, dict) and g.get("hooks") == [want]
               for g in (cur.get(ev) or []) if isinstance(cur.get(ev), list))
           for ev in HOOK_EVENTS):
        return True
    hooks, _ = _strip_our_hooks(cur)
    for ev in HOOK_EVENTS:
        groups = hooks.get(ev) if isinstance(hooks.get(ev), list) else []
        hooks[ev] = groups + [{"hooks": [dict(want)]}]
    data["hooks"] = hooks
    if os.path.exists(CLAUDE_SETTINGS) and not os.path.exists(SETTINGS_BAK):
        try:
            shutil.copyfile(CLAUDE_SETTINGS, SETTINGS_BAK)
        except OSError:
            pass
    try:
        os.makedirs(os.path.dirname(CLAUDE_SETTINGS), exist_ok=True)
        _atomic_write(CLAUDE_SETTINGS, json.dumps(data, indent=2) + "\n")
        return True
    except OSError as e:
        log(f"hooks_on failed: {e}")
        return False


def hooks_off():
    """Remove Tower's hook entries (and only those). -> number removed."""
    if not os.path.isfile(CLAUDE_SETTINGS):
        return 0
    data = _read_settings()
    cur = data.get("hooks")
    if not isinstance(cur, dict):
        return 0
    hooks, n = _strip_our_hooks(cur)
    if not n:
        return 0
    if hooks:
        data["hooks"] = hooks
    else:
        data.pop("hooks", None)
    _atomic_write(CLAUDE_SETTINGS, json.dumps(data, indent=2) + "\n")
    return n


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
        for k in RETRY_ENV:
            if k in env and _retry_env_ours(k, env[k]):
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
    if hooks_off():
        removed.append("agent hooks from settings.json")
        if os.path.exists(SETTINGS_BAK):
            backups.append(SETTINGS_BAK)
    if IS_WINDOWS:
        _win.keepawake(False)       # no pmset/sudoers on Windows
    elif IS_LINUX:
        pass                        # the inhibitor lock dies with its holder
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


def _remove_clamshell_rule():
    _pmset_nopasswd("0")
    if os.path.exists(SUDOERS_FILE):
        _osascript_admin(f"{PMSET} -a disablesleep 0; /bin/rm -f {SUDOERS_FILE}")


# Keep-awake is a *policy*, not a switch. Turning it on arms it; Tower then holds
# the Mac awake only while it has a job: an agent working (or a Claude request
# held on the guard), plus a grace window so the gap between two turns doesn't
# drop the Mac to sleep. Nothing working → no hold at all, and the Mac sleeps
# exactly as it would without Tower. The hold itself is the cheapest one macOS
# has: a single PreventUserIdleSystemSleep assertion (`caffeinate -i`) — no
# display assertion, so the screen still dims and sleeps on its own schedule.
# The assertion is tied to the daemon (`-w`), so a crash can't orphan it.
# Lid-closed needs no password: the lid's sleep is switched off through the
# IOPMrootDomain user client (kPMSetClamshellSleepState), which any user may call
# — the same mechanism no-admin keep-awake apps use. That flag lives in the
# kernel, not in this process, so a crash would leave the lid unable to sleep the
# Mac: the daemon clears it on startup, and the app clears it the moment the
# daemon is found dead (AppDelegate.superviseDaemon). A reboot clears it too.
AWAKE_TICK_S = 5.0            # policy cadence; a mode change pokes it at once
AWAKE_GRACE_S = 600.0         # keep holding this long after the last working agent
PM_SET_CLAMSHELL_SLEEP_STATE = 12   # kPMSetClamshellSleepState, IOPMLibDefs.h

_rootdomain = None     # (IOKit, connection) to IOPMrootDomain, opened once


def _lid_sleep_disabled(disable):
    """Stop (True) or restore (False) sleep-on-lid-close. No root, no prompt.
    Returns True when the kernel accepted it."""
    global _rootdomain
    if sys.platform != "darwin":
        return False                # IOKit is macOS-only (Linux: logind lock)
    try:
        import ctypes
        if _rootdomain is None:
            import ctypes.util
            iokit = ctypes.CDLL(ctypes.util.find_library("IOKit"))
            libc = ctypes.CDLL(ctypes.util.find_library("System"))
            iokit.IOServiceMatching.restype = ctypes.c_void_p
            iokit.IOServiceMatching.argtypes = [ctypes.c_char_p]
            iokit.IOServiceGetMatchingService.restype = ctypes.c_uint
            iokit.IOServiceGetMatchingService.argtypes = [ctypes.c_uint,
                                                          ctypes.c_void_p]
            iokit.IOServiceOpen.argtypes = [ctypes.c_uint, ctypes.c_uint,
                                            ctypes.c_uint,
                                            ctypes.POINTER(ctypes.c_uint)]
            iokit.IOConnectCallScalarMethod.argtypes = [
                ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_uint64),
                ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
            svc = iokit.IOServiceGetMatchingService(
                0, iokit.IOServiceMatching(b"IOPMrootDomain"))
            conn = ctypes.c_uint()
            task = ctypes.c_uint.in_dll(libc, "mach_task_self_").value
            if not svc or iokit.IOServiceOpen(svc, task, 0,
                                              ctypes.byref(conn)) != 0:
                return False
            _rootdomain = (iokit, conn.value)
        iokit, conn = _rootdomain
        arg = (ctypes.c_uint64 * 1)(1 if disable else 0)
        return iokit.IOConnectCallScalarMethod(
            conn, PM_SET_CLAMSHELL_SLEEP_STATE, arg, 1, None, None) == 0
    except Exception as e:  # noqa: BLE001
        log(f"lid sleep call failed: {e}")
        return False


def _sleep_disabled():
    """True when `pmset disablesleep 1` is in force system-wide."""
    try:
        out = subprocess.run([PMSET, "-g"], capture_output=True, text=True,
                             timeout=5).stdout
    except Exception:  # noqa: BLE001
        return False
    return bool(re.search(r"SleepDisabled\s+1", out))


def set_keepawake(state, on, mode):
    """Arm or disarm keep-awake (a user command). The hold itself is owned by
    keepawake_loop; this only records the choice and persists it, so a
    respawned daemon resumes the vigil. Every mode is one tap — no password."""
    mode = mode if (on and mode in ("idle", "clamshell")) else "off"
    if IS_WINDOWS and mode == "clamshell":
        mode = "idle"               # no clamshell concept there
    state.keepawake_on = mode != "off"
    state.keepawake_mode = mode
    state.cfg["keepawake_mode"] = mode
    save_config(state.cfg)
    state._awake_poke.set()
    return {"on": state.keepawake_on, "mode": mode}


def _awake_apply(state, hold, lid):
    """Make the OS match the decision. Only transitions cost anything."""
    if IS_WINDOWS:
        if hold != state._awake_held:
            _win.keepawake(hold)    # this thread owns the execution state
    elif IS_LINUX:
        # logind does idle, sleep AND the lid for any user — no admin. One
        # `systemd-inhibit` holder per decision, restarted only when the
        # decision changes (idle ↔ lid). The holder watches the daemon's pid,
        # so a kill -9 can't leave the machine unable to sleep. A holder that
        # dies on its own (polkit denial over SSH, no logind) is logged once,
        # not retried every tick, and `holding` reports what's really held.
        want = ("clamshell" if lid else "idle") if hold else None
        alive = state._caffeinate is not None and state._caffeinate.poll() is None
        if want != state._inhibit_want:
            if alive:
                try:
                    state._caffeinate.terminate()
                    state._caffeinate.wait(timeout=3)
                except Exception:  # noqa: BLE001
                    pass
            state._caffeinate, state._inhibit_want = None, want
            state._inhibit_failed = False
            argv = _linux.keepawake_argv(want, os.getpid()) if want else None
            if want and argv is None:
                log("keep-awake: systemd-inhibit not found")
                state._inhibit_failed = True
            elif argv:
                try:
                    state._caffeinate = subprocess.Popen(
                        argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception as e:  # noqa: BLE001
                    log(f"keep-awake: systemd-inhibit start failed: {e}")
                    state._inhibit_failed = True
        elif want and not alive and not state._inhibit_failed:
            log("keep-awake: the systemd-inhibit lock was refused or lost")
            state._inhibit_failed = True
        hold = state._caffeinate is not None and state._caffeinate.poll() is None
        state._lid_held = hold and lid
    else:
        alive = state._caffeinate is not None and state._caffeinate.poll() is None
        if hold and not alive:
            try:
                state._caffeinate = subprocess.Popen(
                    ["caffeinate", "-i", "-w", str(os.getpid())],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:  # noqa: BLE001
                log(f"caffeinate start failed: {e}")
        elif not hold and alive:
            try:
                state._caffeinate.terminate()
                state._caffeinate.wait(timeout=3)
            except Exception:  # noqa: BLE001
                pass
            state._caffeinate = None
        # Re-assert every tick while wanted (one IOKit call): the flag is global,
        # so if anything restored lid sleep behind our back, it heals in a tick.
        if lid or state._lid_held:
            if _lid_sleep_disabled(lid) or not lid:
                state._lid_held = lid
    state._awake_held = hold


def keepawake_release(state):
    """Drop every hold now (shutdown). The armed mode stays persisted."""
    _awake_apply(state, False, False)


def keepawake_loop(state, agents):
    last_work = None
    while not state.stop.is_set():
        try:
            now = time.monotonic()
            hold, lid, reason = False, False, "off"
            state.keepawake_grace_left = None
            if state.keepawake_on:
                if agents.working_count() > 0 or state.retry_pending():
                    last_work = now
                if last_work is None or now - last_work >= AWAKE_GRACE_S:
                    reason = "standby"
                else:
                    hold = True
                    reason = "working" if last_work == now else "grace"
                    lid = state.keepawake_mode == "clamshell"
                if reason == "grace":
                    state.keepawake_grace_left = int(
                        AWAKE_GRACE_S - (now - last_work))
            if state.keepawake_reason != reason:
                log(f"keep-awake: {reason}")
            state.keepawake_reason = reason
            _awake_apply(state, hold, lid)
        except Exception as e:  # noqa: BLE001
            log(f"keep-awake error: {e}")
        state._awake_poke.wait(AWAKE_TICK_S)
        state._awake_poke.clear()


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
        "keepawake": {"on": state.keepawake_on, "mode": state.keepawake_mode,
                      # holding = the Mac is held awake right now; reason says
                      # why (working/grace) or why not (standby/off).
                      "holding": state._awake_held,
                      "reason": state.keepawake_reason,
                      "grace_left": state.keepawake_grace_left},
        "settings": {"theme": state.theme, "country": state.target_cc,
                     "plan_week_tokens": state.plan_week_tokens,
                     "plan_enabled": state.plan_enabled},
        "recent": list(state.recent),
        "usage": usage.get(),
        "plan": state.plan,
        "net": net.snapshot(),
        "agents": agents.snapshot(),
        "apps": apps_snapshot(state, agents),
        "procs": {
            "daemon_pid": os.getpid(),
            "keepawake_pid": (state._caffeinate.pid
                              if state._caffeinate
                              and state._caffeinate.poll() is None else None),
        },
        # Which OS produced this state. Front-ends read it instead of guessing
        # from their own platform (lid mode, whether a tab can be focused).
        "platform": ("windows" if IS_WINDOWS
                     else "linux" if IS_LINUX else "macos"),
        "version": "3.0",
    }


def state_writer(state, usage, net, agents, interval=1.0):
    """Build state every second, but only write it when something other than the
    timestamp changed — or every STATE_HEARTBEAT_S, so front-ends still see a
    live daemon. An idle Tower then writes (and the app decodes) half as often."""
    last_body, last_t = None, 0.0
    while not state.stop.is_set():
        try:
            d = build_state(state, usage, net, agents)
            ts = d.pop("ts")
            body = json.dumps(d)
            if body != last_body or ts - last_t >= STATE_HEARTBEAT_S:
                d["ts"] = ts
                _atomic_write(STATE_FILE, json.dumps(d))
                last_body, last_t = body, ts
        except Exception as e:  # noqa: BLE001
            log(f"state write error: {e}")
        # Sleep until something publishes (a hook event) or the 1s beat; then
        # coalesce a burst of events into one write.
        if state._publish.wait(interval):
            state._publish.clear()
            time.sleep(STATE_COALESCE_S)


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
        net._probe_now.set()    # one user gesture refreshes both signals
        return {"ok": True}
    if cmd == "refreshplan":
        state._refreshplan.set()
        return {"ok": True}
    if cmd == "speedtest":
        return net.start_speedtest()
    if cmd == "focus":
        return agents.focus(str(req.get("session_id") or ""))
    if cmd == "desktop":
        return open_desktop(state, agents, relaunch=bool(req.get("relaunch")))
    if cmd == "web":
        return open_web(state)
    if cmd == "dismiss":
        return agents.dismiss(str(req.get("session_id") or ""), True)
    if cmd == "undismiss":
        return agents.dismiss(str(req.get("session_id") or ""), False)
    if cmd == "planfetch":
        state.plan_enabled = bool(req.get("on", True))
        state.cfg["plan_enabled"] = state.plan_enabled
        save_config(state.cfg)
        state._refreshplan.set()
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
        elif IS_LINUX:
            pass                    # nothing persistent: a logind lock, held by a child
        else:
            _remove_clamshell_rule()
            state._lid_held = False
        set_keepawake(state, False, "off")
        return {"removed": (IS_WINDOWS or IS_LINUX
                            or not os.path.exists(SUDOERS_FILE))}
    if cmd == "theme":
        state.theme = str(req.get("theme", "Daybreak"))
        state.cfg["theme"] = state.theme
        save_config(state.cfg)
        return {"theme": state.theme}
    if cmd == "quit":
        # A confirmed quit keeps the proxy port open for pinned chats until they
        # exit (POSIX; Windows has no safe pid-liveness probe here).
        state.relay_on_exit = not IS_WINDOWS
        state.stop.set()
        return {"bye": True}
    return {"error": f"unknown cmd {cmd!r}"}


CMD_IDLE_S = 5.0        # kqueue fallback wake (a missed event can't strand a cmd)
STATE_COALESCE_S = 0.05  # batch a burst of hook events into one state write
STATE_HEARTBEAT_S = 2.0  # rewrite an unchanged state.json this often (front-ends
                         # treat a state older than 5s as a dead daemon)


def _cmd_dir_watch():
    """A kqueue that fires when a file lands in CMD_DIR, or None (Windows, or
    any failure — the caller then polls). Lets the watcher sleep until a
    front-end actually writes a command instead of listing the dir 4×/s."""
    if not hasattr(select, "kqueue"):
        return None
    try:
        fd = os.open(CMD_DIR, getattr(os, "O_EVTONLY", 0x8000))
    except OSError:
        return None
    try:
        kq = select.kqueue()
        kq.control([select.kevent(
            fd, select.KQ_FILTER_VNODE,
            select.KQ_EV_ADD | select.KQ_EV_CLEAR, select.KQ_NOTE_WRITE)], 0)
        return kq, fd
    except OSError:
        os.close(fd)
        return None


def command_watcher(state, usage, net, agents):
    os.makedirs(CMD_DIR, exist_ok=True)
    watch = _cmd_dir_watch()
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
            if watch:                   # the watched dir was replaced: re-arm
                watch[0].close()
                os.close(watch[1])
            watch = _cmd_dir_watch()
        if did:
            continue                    # loop hot after a cmd
        if watch:
            try:
                watch[0].control(None, 1, CMD_IDLE_S)
            except OSError:
                time.sleep(0.25)
        else:
            time.sleep(0.25)


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
    try:                    # the agent hooks only point at a live daemon
        if hooks_off():
            log(f"hooks removed on {reason}")
    except Exception as e:  # noqa: BLE001
        log(f"hooks_off on {reason} failed: {e}")


RELAY_POLL_S = 5.0       # how often a relay checks whether its pinned chats exited
RELAY_EVICT_S = 3.0      # how long a starting daemon waits for a relay to let go


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _pinned_pids(agents):
    """Live Claude processes that may hold our HTTPS_PROXY env: every claude
    process (from the raw process table, not agent rows — a chat with no
    hook traffic yet has no row, and headless `-p` runs are pinned too) that was
    launched while routing was installed. An unknown launch verdict counts
    as pinned: keeping an idle listener a little longer is free, while dropping
    it strands a chat on ECONNREFUSED."""
    try:
        procs = agents.procs.scan()     # fresh: catch a chat launched just now
    except Exception:  # noqa: BLE001
        procs = None
    if not procs:
        procs = agents._procs_cache or {}
    pids = {pid for pid, p in procs.items()
            if guarded_at(agents.state.cfg, p.get("lstart")) is not False}
    # Desktop / web windows launched through Tower hold the proxy flag for life.
    lp = agents.procs._libproc
    flag = _proxy_flag(agents.state.proxy_port)
    for kind in ("desktop", "web"):
        for a in (lp.apps.get(kind, []) if lp else []):
            if flag in a["args"]:
                pids.add(a["pid"])
    pids.discard(os.getpid())
    return {p for p in pids if _pid_alive(p)}


def _relay_for_pinned(state, pids, proxy_thread):
    """After a confirmed quit: a Claude session captures HTTPS_PROXY once at
    launch, so closing the port strands every chat started while routed on
    ECONNREFUSED until it is restarted ("only a new chat works"). Instead the
    quit daemon — routing already removed, lock already released — keeps the
    listener as a pure pass-through (state.routed False: the same direct,
    unguarded connection new chats get; off means off) until the last pinned
    chat exits, or until the next daemon evicts it with SIGTERM to take the port
    back and guard those chats again. Everything else has already stopped."""
    state.routed = False
    # Hold an flock on the relay file for our whole life: a held lock is the
    # proof a starting daemon needs that the pid inside is a live relay.
    relayf = None
    try:
        relayf = open(RELAY_FILE, "w")
        fcntl.flock(relayf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        relayf.write(str(os.getpid()))
        relayf.flush()
    except OSError:
        pass
    log(f"relay: keeping :{state.proxy_port} open as a pass-through for "
        f"{len(pids)} pinned chat(s)")
    while not state.proxy_stop.wait(RELAY_POLL_S):
        pids = {p for p in pids if _pid_alive(p)}
        if not pids:
            break
    state.proxy_stop.set()
    proxy_thread.join(2.0)
    if relayf is not None:
        try:
            os.remove(RELAY_FILE)
        except OSError:
            pass
        relayf.close()
    log("relay: released")


def _evict_relay():
    """Take the proxy port back from a quit daemon still relaying for pinned
    chats (see _relay_for_pinned), so those chats come back under the guard.
    The relay holds an flock on RELAY_FILE while alive, so we signal the pid
    inside only when that lock is held — a stale file (relay killed -9) can
    never make us SIGTERM an unrelated process that reused the pid."""
    try:
        f = open(RELAY_FILE)
    except OSError:
        return
    with f:
        try:
            fcntl.flock(f, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            pass                        # held → a live relay
        else:
            try:
                os.remove(RELAY_FILE)   # free → stale file, nobody to evict
            except OSError:
                pass
            return
        try:
            pid = int(f.read().strip())
        except ValueError:
            return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + RELAY_EVICT_S
    while _pid_alive(pid) and time.monotonic() < deadline:
        time.sleep(0.1)
    log(f"evicted relay pid={pid}")


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
    if not IS_WINDOWS:
        raise_fd_limit()
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

    if not IS_WINDOWS:
        _evict_relay()      # a quit daemon may still hold the sticky port

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
    proxy_thread = threading.Thread(target=proxy_loop,
                                    args=(state, proxy_sock), daemon=True)
    proxy_thread.start()
    threading.Thread(target=usage.loop, daemon=True).start()
    threading.Thread(target=plan_loop, args=(state,), daemon=True).start()
    threading.Thread(target=net.loop, daemon=True).start()
    threading.Thread(target=agents.loop, daemon=True).start()
    threading.Thread(target=state_writer, args=(state, usage, net, agents),
                     daemon=True).start()
    threading.Thread(target=command_watcher, args=(state, usage, net, agents),
                     daemon=True).start()
    # A crash (or kill -9) can't run the release above, and `pmset disablesleep`
    # outlives the process — the Mac would then never sleep, lid closed, in a
    # bag. If Tower's rule is installed, assume a lingering disablesleep is ours
    # and clear it; keepawake_loop re-takes it only if the policy wants it.
    if sys.platform == "darwin":
        _lid_sleep_disabled(False)      # a crashed predecessor's lid hold
        # Older versions held the lid with `pmset disablesleep` (root).
        if os.path.exists(SUDOERS_FILE) and _sleep_disabled():
            if _pmset_nopasswd("0"):
                log("keep-awake: cleared a legacy pmset lid hold")
    threading.Thread(target=keepawake_loop, args=(state, agents),
                     daemon=True).start()

    # ON BY DEFAULT: unless you have EXPLICITLY turned routing off before
    # (cfg["routed"] == False), the guard routes Claude the moment the daemon
    # comes up — i.e. as soon as you open the app. The proxy socket is already
    # listening, so route_on's safety check passes and Claude is only ever
    # routed while the guard is genuinely up.
    if state.cfg.get("routed", True):
        if route_on(state.proxy_port):
            log("routing on at startup (default-on)")
    # Agent monitor: Claude Code reports its lifecycle to this daemon via HTTP
    # hooks. Independent of routing — it observes, it doesn't guard.
    state.hook_sink = agents.on_event
    if hooks_on(state.proxy_port):
        log("agent hooks installed")
    # Seed the routing timeline with the actual on-disk truth at boot: starts the
    # history and self-corrects a record left stranded by a previous kill -9.
    note_route_change(state, routing_installed())

    log(f"started pid={os.getpid()} proxy=:{proxy_port}")
    print(f"towerd: proxy :{proxy_port}", flush=True)

    # Belt-and-braces: also restore settings.json if the interpreter exits without
    # running the finally below (idempotent, so the finally path won't double-log).
    atexit.register(_route_off_idempotent, "atexit")

    def _sig(*_a):
        # A signal means exit for real — also ends relay mode (a new daemon
        # evicting us, or the user killing the pass-through).
        state.stop.set()
        state.proxy_stop.set()
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
        while not state.stop.wait(1.0):     # 1s cap so signal handlers still run
            pass
    finally:
        keepawake_release(state)
        # SAFETY: never leave Claude Code pointed at a proxy that is stopping.
        # Routing is active ONLY while the guard is alive; always restore
        # settings.json on the way out.
        _route_off_idempotent("shutdown")
        try:
            os.remove(STATE_FILE)
        except OSError:
            pass
        pids = _pinned_pids(agents) if state.relay_on_exit else set()
        if pids and not state.proxy_stop.is_set():
            # Free the single-instance lock first so reopening Tower can start a
            # fresh daemon, which then evicts us and takes the port back.
            if lockf is not None:
                lockf.close()
            _relay_for_pinned(state, pids, proxy_thread)
        state.proxy_stop.set()
        log("stopped")


if __name__ == "__main__":
    main()
