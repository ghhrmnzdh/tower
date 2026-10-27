#!/usr/bin/env python3
"""
tower-tray.py — Tower's Linux menu-bar front-end.

The macOS app puts the radar in the menu bar; this puts the same radar in the
GNOME/KDE/XFCE top bar, over the same contract every Tower front-end uses:

    read  ~/.tower/state.json      (the daemon's whole world, 1×/s)
    write ~/.tower/cmd/*.json      (fire-and-forget commands)

No logic lives here. What *does* live here is presentation — the same
derivations the Swift `TowerModel` and the curses TUI each make from that one
JSON file (guard status, the radar look, the needs-you queue, the counts a
danger warning has to quote). They are gathered in one marked section below so
a change can be mirrored in one reading.

Toolkit: GTK3 + AyatanaAppIndicator3, through the distro's own `python3-gi`.
That is the Linux reading of Tower's "no third-party deps" rule — AppKit is
macOS's platform toolkit, GTK is Ubuntu's, and neither arrives through pip.
AppIndicator (a StatusNotifierItem host) is what GNOME's shipped
`ubuntu-appindicators` extension renders in the top bar, and it is also what
KDE, XFCE, Cinnamon and Budgie read natively; GTK's own StatusIcon has been
deprecated for a decade and does not appear on Wayland GNOME at all.

The radar is drawn with Cairo from the geometry in src/Glyph.swift — one 0…100
box, five states, the keep-awake lamp layered under the core — so the mark is
the same mark, not a lookalike. Reduce Motion (the desktop's own
gtk-enable-animations) freezes each state at a legible still frame.

Run:  tower-tray        (or: python3 src/tower-tray.py)
"""

import json
import math
import os
import signal
import subprocess
import sys
import time
import uuid

# The toolkit is a *Recommends* of the tower package, not a Depends — that is
# what lets one .deb install on a headless box with --no-install-recommends and
# still arm the guard there. So every piece of it can legitimately be missing,
# and each way of missing it has to end in the same sentence naming what to
# install, never in a traceback: `import gi` fails when python3-gi is absent,
# `import cairo` when python3-gi-cairo is, and the indicator typelib is a third
# thing again. Ayatana is the maintained fork and what Ubuntu 22.04+ ships; the
# older AppIndicator3 name survives on some spins, so accept either.
_HOWTO = """  The top bar needs GTK and the Ayatana indicator bindings:

    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 \\
                     gir1.2-ayatanaappindicator3-0.1

  On GNOME the top bar also needs the shipped extension:

    sudo apt install gnome-shell-extension-appindicator

  Meanwhile the terminal dashboard has every feature, and needs none of it:

    tower
"""


def _no_toolkit(what):
    sys.stderr.write(f"tower-tray: no AppIndicator support found ({what}).\n")
    sys.stderr.write(_HOWTO)
    raise SystemExit(1)


try:
    import cairo                                    # noqa: F401  (python3-gi-cairo)
    import gi
except ImportError as e:                            # noqa: BLE001
    _no_toolkit(e.name or "missing module")

try:
    gi.require_version("Gtk", "3.0")
except ValueError:
    _no_toolkit("no GTK 3 typelib")

_IND = None
for _name in ("AyatanaAppIndicator3", "AppIndicator3"):
    try:
        gi.require_version(_name, "0.1")
        _IND = getattr(__import__("gi.repository", fromlist=[_name]), _name)
        break
    except (ValueError, ImportError):
        continue
if _IND is None:
    _no_toolkit("no indicator typelib")

try:
    from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402
except ImportError as e:                            # noqa: BLE001
    _no_toolkit(f"GTK bindings failed to load: {e}")

APP_ID = "com.tower.guard"

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(HOME, ".tower")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")
CMD_DIR = os.path.join(CONFIG_DIR, "cmd")
ICON_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME") or os.path.join(HOME, ".cache"),
    "tower", "icons")
DAEMON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "towerd.py")
if not os.path.exists(DAEMON):
    DAEMON = "/usr/lib/tower/towerd.py"

POLL_MS = 1000        # state.json is rewritten once a second
STATE_FRESH_S = 5.0   # an older state.json means the daemon is not answering
# Supervision, as the macOS app does it (AppDelegate.superviseDaemon): a daemon
# counts as dead only after this long without fresh state, and is respawned at
# most once per RESPAWN_EVERY_S — never after a confirmed quit.
DEAD_AFTER_S = 10.0
RESPAWN_EVERY_S = 30.0
# The radar's own tempo: the verify sweep takes 2.4s for a full turn, the clear
# pulse 2.38s, the lid-closed lamp 2.4s (src/Glyph.swift). So one 2.4s loop of
# 12 frames plays every one of them at its true speed.
LOOP_S = 2.4
FRAMES = 12
FRAME_MS = int(LOOP_S * 1000 / FRAMES)
HOLD_S = 0.6          # trust an optimistic toggle this long after a click

# Brand tones — docs/DESIGN.md. The ink is monochrome (the theme's own
# foreground); amber = held (pending, self-clearing), red = unguarded/failed
# (danger), and green only for an "on" switch or a small healthy/done dot.
AMBER = (0xE6 / 255, 0xA9 / 255, 0x3C / 255)
RED = (0xE5 / 255, 0x48 / 255, 0x4D / 255)
INK = None            # "no tint": the theme's foreground
DIM = (0.55, 0.55, 0.58)
GREEN_HEX = "#30a14e"
AMBER_HEX = "#e6a93c"

# Model tiers. The accent is text only, never on the mark itself (DESIGN.md).
TIERS = ("haiku", "sonnet", "opus", "fable")
TIER_RANK = {t: i for i, t in enumerate(TIERS)}

CNAME = {
    "US": "United States", "CA": "Canada", "GB": "United Kingdom",
    "DE": "Germany", "FR": "France", "AU": "Australia", "JP": "Japan",
    "IN": "India", "SG": "Singapore", "NL": "Netherlands", "IE": "Ireland",
    "ES": "Spain", "IT": "Italy", "SE": "Sweden", "CH": "Switzerland",
    "BR": "Brazil", "MX": "Mexico", "AE": "United Arab Emirates",
    "TR": "Türkiye", "PL": "Poland", "NO": "Norway", "DK": "Denmark",
    "FI": "Finland", "BE": "Belgium", "AT": "Austria", "PT": "Portugal",
    "NZ": "New Zealand", "KR": "South Korea", "IL": "Israel", "ZA": "South Africa",
    "AR": "Argentina", "CL": "Chile", "CO": "Colombia", "CZ": "Czechia",
    "RO": "Romania", "HU": "Hungary", "GR": "Greece", "HK": "Hong Kong",
    "TW": "Taiwan", "TH": "Thailand", "MY": "Malaysia", "ID": "Indonesia",
    "PH": "Philippines", "SA": "Saudi Arabia", "EG": "Egypt", "NG": "Nigeria",
    "UA": "Ukraine",
}
COUNTRY_LIST = sorted(CNAME.items(), key=lambda kv: kv[1])


def cname(cc):
    cc = (cc or "").upper()
    return CNAME.get(cc, cc or "—")


# --------------------------------------------------------------------------- #
# IPC — identical protocol to the app and the TUI: read one file, write command
# files atomically so the daemon's watcher never sees a half-written one.
# --------------------------------------------------------------------------- #
_state_cache = [None, None]     # (mtime_ns, size), parsed dict


def load_state():
    """The last state.json, parsed only when the file actually changed (the
    daemon rewrites it on change or every 2s), or None if there is none.
    May be stale — `fresh()` says whether the daemon is still answering."""
    try:
        st = os.stat(STATE_FILE)
    except OSError:
        _state_cache[0] = _state_cache[1] = None
        return None
    key = (st.st_mtime_ns, st.st_size)
    if key != _state_cache[0]:
        try:
            with open(STATE_FILE) as f:
                s = json.load(f)
        except (OSError, ValueError):
            return _state_cache[1]      # mid-replace: keep the last good one
        _state_cache[0] = key
        _state_cache[1] = s if isinstance(s, dict) else None
    return _state_cache[1]


def fresh(s, now=None):
    return bool(s) and ((now or time.time()) - (s.get("ts") or 0)) < STATE_FRESH_S


def send(cmd):
    os.makedirs(CMD_DIR, exist_ok=True)
    name = uuid.uuid4().hex
    tmp = os.path.join(CMD_DIR, "." + name + ".tmp")
    dst = os.path.join(CMD_DIR, name + ".json")
    try:
        with open(tmp, "w") as f:
            json.dump(cmd, f)
        os.replace(tmp, dst)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def spawn_daemon():
    """Start a daemon. It is single-instance (flock), so a redundant spawn
    simply exits; the supervisor still throttles them."""
    if not os.path.exists(DAEMON):
        return
    try:
        subprocess.Popen([sys.executable or "python3", DAEMON],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


class Supervisor:
    """Keeps the guard up — the macOS app's superviseDaemon, line for line.

    Opening Tower arms the guard (a daemon is started at once if none answers),
    and one that dies unexpectedly (kill -9) is respawned — but only after
    DEAD_AFTER_S without fresh state, at most once per RESPAWN_EVERY_S, and
    never once a quit has been confirmed: after a double-confirmed Quit the
    daemon deletes state.json on its way out, and respawning then would put
    the guard straight back and re-route Claude behind the user's back."""

    def __init__(self, spawn=spawn_daemon, clock=time.monotonic):
        self.confirmed_quit = False
        self.dead_since = None
        self.last_spawn = None
        self._spawn = spawn
        self._clock = clock

    def start(self, alive):
        if not alive and not self.confirmed_quit:
            self.last_spawn = self._clock()
            self._spawn()

    def tick(self, alive):
        if self.confirmed_quit:
            return False
        if alive:
            self.dead_since = None
            return False
        now = self._clock()
        if self.dead_since is None:
            self.dead_since = now
        if now - self.dead_since <= DEAD_AFTER_S:
            return False
        if self.last_spawn is not None and now - self.last_spawn < RESPAWN_EVERY_S:
            return False
        self.last_spawn = now
        self._spawn()
        return True


# --------------------------------------------------------------------------- #
# Derivations — mirrors of TowerModel (src/Model.swift) and the TUI's
# status_of()/agents_view()/usage_gate(). Presentation only; the daemon owns
# the truth.
# --------------------------------------------------------------------------- #
def guard_status(s):
    """(title, tone) for the overall guard — the TUI's status_of(). Net faults
    outrank everything, and `degraded` deliberately does not, since a
    slow-but-reachable link still passes traffic. A protected guard is plain
    ink: only holds (amber) and danger (red) are tinted."""
    net = (s.get("net") or {}).get("status")
    if net == "offline":
        return "Internet down", RED
    if net == "captive":
        return "Wi-Fi login required", RED
    if net == "api_issue":
        return "Anthropic API issue", RED
    g = s.get("guard") or {}
    loc = s.get("location") or {}
    if not (s.get("routing") or {}).get("installed"):
        return "Not routed — Claude is unguarded", RED
    if not g.get("enforce", True):
        return "Monitor only", AMBER
    if g.get("claude_allowed"):
        return "Protected", INK
    if g.get("net_ok") is False:
        return "Blocking — connection unstable", AMBER
    if loc.get("status") != "OK":
        return "Blocking — confirming location…", AMBER
    return "Blocking Claude", AMBER


def radar_state(s):
    """The guard distilled to one of the radar's five looks (Model.radarState).
    A live net fault reads as a held connection even while "protected"."""
    if s is None:
        return "verify"
    g = s.get("guard") or {}
    loc = s.get("location") or {}
    if not (s.get("routing") or {}).get("installed"):
        return "off"
    net = (s.get("net") or {}).get("status")
    if net in ("offline", "captive", "api_issue") or g.get("net_ok") is False:
        return "holdNet"
    if not g.get("enforce", True):
        return "clear"
    if g.get("claude_allowed"):
        return "clear"
    if loc.get("status") != "OK":
        return "verify"
    return "holdGeo"


def awake_glow(s):
    """The keep-awake lamp (Model.awakeGlow): lit only while the machine is
    actually *held* — armed with nothing to do is a dark core."""
    ka = (s or {}).get("keepawake") or {}
    if not ka.get("on") or ka.get("mode") == "off" \
            or ka.get("holding", True) is False:
        return "none"
    return "clamshell" if ka.get("mode") == "clamshell" else "idle"


def keepawake_mode(s):
    ka = (s or {}).get("keepawake") or {}
    return (ka.get("mode") if ka.get("on") else None) or "off"


def keepawake_title(s):
    """Model.keepAwakeTitle: holding right now, armed and waiting, or off."""
    mode = keepawake_mode(s)
    if mode == "off":
        return "Sleep allowed"
    lid = "lid closed" if mode == "clamshell" else "lid open"
    ka = (s or {}).get("keepawake") or {}
    return (f"Armed · {lid}" if ka.get("holding") is False
            else f"Holding awake · {lid}")


def keepawake_line(s):
    """KeepAwakeCopy.line, from the daemon's live policy: keep-awake holds only
    while agents work, so an armed mode says what it is doing right now."""
    mode = keepawake_mode(s)
    ka = (s or {}).get("keepawake") or {}
    if mode == "off":
        return "This machine may sleep on its own — a long agent can be cut off."
    reason = ka.get("reason")
    if reason == "standby":
        return "Armed — sleeps normally until an agent works."
    if reason == "grace":
        m = max(1, ((ka.get("grace_left") or 0) + 59) // 60)
        return f"Agents idle — letting this machine sleep in {m} min."
    if mode == "clamshell":
        return "Agents keep running even after you close the lid."
    return "Agents keep running; the screen still sleeps."


# What actually needs the user (counted — the macOS menu-bar badge, the TUI's
# NEED set) vs. "your turn" — a finished turn waiting on the next prompt:
# listed, quieter, and never part of the needs-you number.
NEED = ("failed", "pending_tool", "asking")
TURN = ("done", "waiting_input")
NEEDS_RANK = {"failed": 0, "pending_tool": 1, "asking": 2, "done": 3,
              "waiting_input": 3}
NEED_PHRASE = {"failed": "failed", "pending_tool": "needs approval",
               "asking": "has a question"}
AGENT_PHRASE = {
    "working": "working", "pending_tool": "needs approval",
    "waiting_input": "waiting for your next prompt", "asking": "has a question",
    "done": "done", "failed": "failed", "idle": "idle", "gone": "gone",
    "paused": "paused",
}


def sessions(s):
    return [x for x in (((s or {}).get("agents") or {}).get("sessions") or [])
            if isinstance(x, dict)]


class AgentsView:
    """Agents split by what they ask of you — the TUI's agents_view().

    need:    failed > approval > asking (counted, notified)
    turn:    done / waiting for the next prompt (listed, never counted)
    working: at work, highest tier first
    Rows are (reason, session, since)."""

    def __init__(self, s):
        ag = (s or {}).get("agents")
        ag = ag if isinstance(ag, dict) else {}
        rows = sessions(s)
        by_id = {x.get("session_id"): x for x in rows}
        self.need, self.turn, self.working, self.paused = [], [], [], []
        self.resting = 0
        listed = set()
        queue = ag.get("needs_you")
        if not isinstance(queue, list):
            # A daemon without the ranked queue: derive it the same way.
            queue = sorted(
                ({"session_id": x.get("session_id"), "reason": x.get("status"),
                  "since": x.get("status_since")}
                 for x in rows if x.get("status") in NEEDS_RANK),
                key=lambda n: (NEEDS_RANK[n["reason"]], n["since"] or 0))
        for nu in queue:                        # daemon order = rank order
            if not isinstance(nu, dict):
                continue
            sid = nu.get("session_id")
            sess = by_id.get(sid) or {"session_id": sid}
            if sess.get("dismissed"):
                continue
            reason = nu.get("reason") or sess.get("status") or ""
            row = (reason, sess, nu.get("since") or sess.get("status_since"))
            (self.need if reason in NEED else self.turn).append(row)
            listed.add(sid)
        for x in rows:
            sid = x.get("session_id")
            if x.get("dismissed") or sid in listed:
                continue
            st = x.get("status")
            if st == "working":
                self.working.append(("working", x, x.get("status_since")))
            elif st == "paused":
                self.paused.append(("paused", x, x.get("status_since")))
            elif st in ("idle", "gone", "done", "waiting_input"):
                self.resting += 1
        self.working.sort(key=lambda r: -TIER_RANK.get(
            (r[1].get("model_family") or "").lower(), -1))
        summary = ag.get("summary") if isinstance(ag.get("summary"), dict) else {}
        self.working_n = working_now(s)
        self.done_today = summary.get("done_today") or 0
        self.need_n = len(self.need)            # only NEED counts
        self.collisions = [c for c in (ag.get("collisions") or [])
                           if isinstance(c, dict)]

    @property
    def listed(self):
        return self.need + self.turn + self.working + self.paused


def _live(x):
    return bool(x.get("pid") and x.get("kind") != "infra"
                and x.get("status") != "gone")


def working_now(s):
    """Agents at work right now — the daemon's own summary count (working +
    awaiting an approval), re-derived only for a daemon that lacks it. This is
    the number every danger warning quotes: they would send unguarded
    requests the moment the guard goes."""
    summary = (((s or {}).get("agents") or {}).get("summary")) or {}
    n = summary.get("working") if isinstance(summary, dict) else None
    if isinstance(n, int):
        return n
    return sum(1 for x in sessions(s)
               if x.get("status") in ("working", "pending_tool") and _live(x))


def proxy_pinned_count(s):
    """Live chats reaching the API *through* Tower's proxy right now, whatever
    the routing intent (the app's proxyPinnedCount, the TUI's _pinned_note).
    On quit the daemon keeps their port open as an unguarded pass-through
    relay until they exit — so they keep working, but with no guard."""
    return sum(1 for x in sessions(s) if _live(x) and x.get("guarded") is True)


def working_clause(n):
    """The danger warning's agent clause (DangerAlerts.dangerAgentClause)."""
    if not n:
        return ""
    return (f"⚠ {n} Claude agent{' is' if n == 1 else 's are'} working right "
            f"now and will immediately send unguarded requests.")


def pinned_clause(n):
    """The quit warning's pinned clause — the same words as the app's
    quit alert and the TUI's _pinned_note."""
    if not n:
        return ""
    return (f"⚠ {n} open chat{'' if n == 1 else 's'} route through Tower now. "
            f"They keep working, but go DIRECT with no guard until you reopen "
            f"Tower.")


def usage_gate(s):
    """When the guard isn't passing Claude, `/usage` is withheld — running it
    would itself be the off-country or unstable request. Returns the honest
    (headline, one-line reason) saying whether it waits on the connection or
    the location — from the daemon's plan.gate_reason, else guard.net_ok —
    or None when usage should render normally. Never stale numbers."""
    plan = (s or {}).get("plan") or {}
    if plan.get("disabled"):
        return None
    g = (s or {}).get("guard") or {}
    if not (plan.get("gated") or g.get("claude_allowed") is False):
        return None
    target = cname(g.get("target_cc")) if g.get("target_cc") else "your country"
    if plan.get("gate_reason") == "net" or g.get("net_ok") is False:
        return ("Usage paused — connection unstable",
                "Can't reach Anthropic right now; usage returns on its own "
                "once the link is stable.")
    return ("Usage paused — location not confirmed",
            f"You appear to be outside {target} (check your VPN); usage "
            f"returns once your location is confirmed.")


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #
def fmt_tok(n):
    n = n or 0
    if n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.1f}K"
    return str(int(n))


def fmt_cost(c):
    c = c or 0
    return f"${c:,.2f}" if c < 100 else f"${c:,.0f}"


def ago(ts):
    if not ts:
        return ""
    d = max(0, time.time() - ts)
    if d < 45:
        return "just now"
    if d < 5400:
        return f"{int(d / 60)}m ago"
    if d < 129600:
        return f"{int(d / 3600)}h ago"
    return f"{int(d / 86400)}d ago"


def dur(secs):
    """A turn clock at minute grain ("<1m", "12m", "2h 05m")."""
    m = int(max(0, secs) // 60)
    if m < 1:
        return "<1m"
    if m < 60:
        return f"{m}m"
    return f"{m // 60}h {m % 60:02d}m"


def until(ts):
    """Exact reset countdowns, as the app shows them: minutes, then hours and
    minutes under 48h, then days and hours."""
    if not ts:
        return ""
    m = int((ts - time.time()) // 60)
    if m <= 0:
        return "now"
    if m < 60:
        return f"in {m}m"
    if m < 48 * 60:
        return f"in {m // 60}h {m % 60}m"
    return f"in {m // 1440}d {(m % 1440) // 60}h"


def reset_text(node):
    rel = until(node.get("resets_at"))
    if rel:
        return rel
    return (node.get("resets") or "").split("(", 1)[0].strip()


def _model_short(model):
    """"claude-sonnet-5" → "sonnet". The tier, not the release."""
    parts = (model or "").split("-")
    return parts[1] if len(parts) > 1 else (model or "?")


def model_label(sess):
    fam = sess.get("model_family") or ""
    return fam.capitalize() if fam else (sess.get("model") or "")


def agent_name(sess):
    return str(sess.get("project_name")
               or os.path.basename(sess.get("cwd") or "") or "?")


def _pending_detail(sess):
    pt = sess.get("pending_tool")
    if isinstance(pt, dict):
        return " ".join(str(x) for x in (pt.get("name"), pt.get("detail")) if x)
    return str(sess.get("activity") or "")


def agent_what(reason, sess):
    """(phrase, detail) for an agent row — the TUI's _agent_line wording."""
    if reason in NEED:
        det = (str(sess.get("activity") or "") if reason == "failed"
               else _pending_detail(sess))
        if det.startswith("needs approval · "):    # the daemon's own prefix
            det = det[len("needs approval · "):]
        return NEED_PHRASE[reason], det
    if reason == "done":
        return "done", str(sess.get("result") or "")
    if reason == "waiting_input":
        return "waiting for your next prompt", ""
    if reason == "paused":
        return "paused", ""
    return "", str(sess.get("activity") or "working…")


def _clip(text, n=72):
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


# --------------------------------------------------------------------------- #
# The radar — a Cairo port of drawRadar() in src/Glyph.swift.
#
# Same 0…100 box, same five states, same lamp layered under the core, so the
# top-bar mark is the mark, not a lookalike. Both toolkits put y downward and
# measure angles the same way, so the geometry transfers literally: keep it
# that way, and port changes rather than reinventing them.
# --------------------------------------------------------------------------- #
HUB = (50.0, 50.0)


def _circle(cr, c, r):
    cr.new_path()
    cr.arc(c[0], c[1], r, 0, 2 * math.pi)


def _stroke(cr, rgb, width, alpha=1.0, dash=()):
    cr.set_source_rgba(rgb[0], rgb[1], rgb[2], alpha)
    cr.set_line_width(width)
    cr.set_dash(list(dash))
    cr.stroke()
    cr.set_dash([])


def _fill(cr, rgb, alpha=1.0):
    cr.set_source_rgba(rgb[0], rgb[1], rgb[2], alpha)
    cr.fill()


def draw_radar(cr, size, state, phase, color, awake="none", reduce=False):
    """Draw the radar into `cr`, filling a `size`×`size` square."""
    cr.save()
    cr.scale(size / 100.0, size / 100.0)
    P = float(phase)
    A = 0.0 if reduce else 1.0

    def rotated(deg, draw):
        cr.save()
        cr.translate(50, 50)
        cr.rotate(math.radians(deg))
        cr.translate(-50, -50)
        draw()
        cr.restore()

    # ---- outer ring: color + dash encode the state ------------------------ #
    ring, dash = color, ()
    if state == "off":
        ring, dash = RED, (5, 7)
    elif state == "holdNet":
        ring, dash = AMBER, (5, 6)
    elif state == "holdGeo":
        ring = AMBER
    _circle(cr, HUB, 33)
    _stroke(cr, ring, 6, 1.0, dash)

    # ---- verify: a rotating sweep with a soft trail ----------------------- #
    if state == "verify":
        def sweep():
            cr.new_path()
            cr.move_to(*HUB)
            a0, a1 = 270.0, 208.5
            for i in range(13):
                a = math.radians(a0 + (a1 - a0) * i / 12.0)
                cr.line_to(50 + 33 * math.cos(a), 50 + 33 * math.sin(a))
            cr.close_path()
            _fill(cr, color, 0.16)
            cr.new_path()
            cr.move_to(*HUB)
            cr.line_to(50, 17)
            cr.set_line_cap(1)          # round
            _stroke(cr, color, 4)
            cr.set_line_cap(0)
        rotated((P * 150) % 360, sweep)

    # ---- clear: a slow radar pulse ---------------------------------------- #
    if state == "clear":
        pr = (P * 0.42) % 1 if A else 0
        r = 8 + pr * 26 if A else 22
        op = (1 - pr) * 0.5 if A else 0.3
        _circle(cr, HUB, r)
        _stroke(cr, color, 3, op)

    # ---- holdNet: amber sonar pings --------------------------------------- #
    if state == "holdNet":
        for i in range(2):
            pr = ((P * 0.7) + i * 0.5) % 1 if A else 0
            r = 7 + pr * 15 if A else 11 + i * 7
            op = max(0.0, 1 - pr) * 0.7 if A else 0.55 - i * 0.25
            _circle(cr, HUB, r)
            _stroke(cr, AMBER, 3.5, op)

    # ---- blips: contacts on the scope ------------------------------------- #
    for i, b in enumerate(((64, 41), (38, 58), (58, 66))):
        if state == "clear":
            op = 0.8 + 0.2 * math.sin(P * 1.6 + i * 1.3) * A
        elif state == "verify":
            op = 0.3 + 0.12 * math.sin(P * 2.2 + i) * A
        elif state == "off":
            op = 0.22
        else:
            op = 0.0
        if op > 0.001:
            _circle(cr, b, 3.6)
            _fill(cr, color, op)

    # ---- holdGeo: a rotating fence + a lunging off-country blip ------------ #
    if state == "holdGeo":
        def fence():
            _circle(cr, HUB, 15)
            _stroke(cr, AMBER, 3, 1.0, (4, 5))
        rotated((P * 45) % 360, fence)
        cr.new_path()
        cr.move_to(*HUB)
        cr.line_to(72, 32)
        cr.set_line_cap(1)
        _stroke(cr, AMBER, 2.5, 1.0, (2, 4))
        cr.set_line_cap(0)
        dx, dy = -0.773, 0.634
        lunge = 6 * (0.5 + 0.5 * math.sin(P * 2.2)) if A else 0
        s = 1 + (0.16 * math.sin(P * 3.0) if A else 0)
        mx, my = 72 + dx * lunge, 32 + dy * lunge
        cr.save()
        cr.translate(mx, my)
        cr.scale(s, s)
        cr.translate(-72, -32)
        _circle(cr, (72, 32), 5)
        _fill(cr, AMBER)
        cr.restore()
        hp = (P * 1.1) % 1 if A else 0
        hr = 5 + hp * 9 if A else 10
        hop = (1 - hp) * 0.8 if A else 0.5
        _circle(cr, (mx, my), hr)
        _stroke(cr, AMBER, 2.5, hop)

    # ---- the keep-awake vigil: a neutral lamp under the core -------------- #
    # Never amber/red, so a guard hold always outranks it and the two facts
    # compose in one mark. Only the lid-closed vigil breathes.
    if awake != "none":
        breathing = awake == "clamshell"
        amp = 1.0 if breathing else 0.6
        br = (0.5 + 0.5 * math.sin(P * 2 * math.pi / 2.4)) \
            if (breathing and A) else 0.7
        for r, op in ((15, 0.09), (11, 0.15), (7.5, 0.22)):
            _circle(cr, HUB, r)
            _fill(cr, color, op * (0.75 + 0.35 * br * amp))
        _circle(cr, HUB, 9.5 + 1.7 * br * amp)
        _stroke(cr, color, 2.2, 0.44 + 0.30 * br * amp)

    # ---- the core --------------------------------------------------------- #
    if state == "off":
        _circle(cr, HUB, 5.5)
        _stroke(cr, RED, 4)
    else:
        _circle(cr, HUB, 4.5 if awake == "none" else 5.6)
        _fill(cr, AMBER if state == "holdNet" else color)
    cr.restore()


# --------------------------------------------------------------------------- #
# Top-bar icon: pre-rendered frames on disk.
#
# StatusNotifierItem carries an icon *name*, not a surface, so every frame has
# to be a file — and the host only reloads when the name changes, which is
# exactly why each frame gets its own name. Frames are rendered once per
# (state, awake) and then cycled by name, so animating costs a D-Bus property
# set and no drawing at all.
# --------------------------------------------------------------------------- #
ICON_PX = 44          # 2× a 22px panel slot, so HiDPI stays crisp


class IconCache:
    """Renders a (state, awake) frame set on demand into ICON_DIR.

    Each set is the 12 animation frames plus one "still" — drawn with
    reduce=True, which is the design system's *legible frozen frame* for that
    state, never a blank one. Reduce Motion shows the still and nothing moves.
    """

    def __init__(self):
        os.makedirs(ICON_DIR, exist_ok=True)
        self._done = set()
        # The mark's neutral. Top bars are dark on Ubuntu's default theme and
        # light on others; a near-white neutral reads on both once the shell
        # composites it, and amber/red stay untouched because they *are* the
        # signal (docs/DESIGN.md — never a flat template tint).
        self.neutral = (0.93, 0.93, 0.95)

    def name(self, state, awake, frame):
        tag = frame if isinstance(frame, str) else f"{frame:02d}"
        return f"tower-{state}-{awake}-{tag}"

    def ensure(self, state, awake):
        key = (state, awake)
        if key in self._done:
            return
        import cairo

        def render(frame, phase, reduce):
            surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, ICON_PX, ICON_PX)
            draw_radar(cairo.Context(surf), ICON_PX, state, phase,
                       self.neutral, awake, reduce)
            surf.write_to_png(os.path.join(
                ICON_DIR, self.name(state, awake, frame) + ".png"))

        for i in range(FRAMES):
            render(i, i * LOOP_S / FRAMES, False)
        render("still", 0.0, True)
        self._done.add(key)


# --------------------------------------------------------------------------- #
# Look — the design system, in CSS.
#
# docs/DESIGN.md's type scale: header 13 semibold · row title 13 · activity 11
# secondary · counters 11 monospaced-digit · section headers 11 semibold
# secondary. Flat rows and separators, no card chrome — the Wi-Fi-menu shape
# the popover uses. The ink is the desktop theme's own foreground, so Tower
# reads right in light and dark and never borrows the theme's accent (blue on
# some, orange on Yaru): meters and the sparkline are ink, switches are green
# when on, and only holds (amber) and danger (red) are tinted.
# --------------------------------------------------------------------------- #
CSS = b"""
.tower-title      { font-size: 13px; font-weight: 600; }
.tower-row        { font-size: 13px; }
.tower-sub        { font-size: 11px; opacity: 0.65; }
.tower-section    { font-size: 11px; font-weight: 600; opacity: 0.6;
                    letter-spacing: 0.06em; }
.tower-count      { font-size: 11px; font-family: monospace; opacity: 0.75; }
.tower-warn       { color: #e6a93c; }
.tower-bad        { color: #e5484d; }
.tower-dim        { opacity: 0.6; }
.tower-pad        { padding: 12px 16px; }
.tower-tier-fable  { color: #c9a227; font-size: 11px; font-weight: 600; }
.tower-tier-opus   { color: #b0343c; font-size: 11px; font-weight: 600; }
.tower-tier-sonnet { color: #3b6fb5; font-size: 11px; font-weight: 600; }
.tower-tier-haiku  { color: #e8842c; font-size: 11px; font-weight: 600; }
button.tower-agent { padding: 2px 4px; }
button.tower-x     { padding: 0 6px; min-height: 0; min-width: 0; }
switch.tower-switch:checked { background-color: #30a14e;
                              background-image: none; border-color: #2a8a43; }
progressbar.tower-meter trough { min-height: 6px; }
progressbar.tower-meter progress { min-height: 6px; background-image: none;
                                   background-color: currentColor;
                                   border-color: transparent; }
progressbar.tower-meter.tower-warn progress { background-color: #e6a93c; }
progressbar.tower-meter.tower-bad progress  { background-color: #e5484d; }
"""

TONE_CLASS = {AMBER: "tower-warn", RED: "tower-bad", DIM: "tower-dim"}
_TONES = ("tower-warn", "tower-bad", "tower-dim")


def _tone(widget, cls):
    ctx = widget.get_style_context()
    for c in _TONES:
        if c != cls:
            ctx.remove_class(c)
    if cls:
        ctx.add_class(cls)


def _esc(text):
    """Escape text for Pango markup (stdlib, no binding quirks)."""
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def _dot(hex_color, text):
    """Pango markup: a small coloured dot, then the text in plain ink."""
    return (f'<span foreground="{hex_color}">●</span> '
            f'{_esc(text)}')


def _label(text, css=None, align=0.0, wrap=False, selectable=False):
    lb = Gtk.Label(label=text)
    lb.set_xalign(align)
    if wrap:
        lb.set_line_wrap(True)
        lb.set_max_width_chars(44)
    lb.set_selectable(selectable)
    if css:
        for c in css.split():
            lb.get_style_context().add_class(c)
    return lb


def _section(title):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.get_style_context().add_class("tower-pad")
    if title:
        box.pack_start(_label(title, "tower-section"), False, False, 0)
    return box


def _ink(widget, fallback=(0.2, 0.2, 0.22)):
    ok, col = widget.get_style_context().lookup_color("theme_fg_color")
    return (col.red, col.green, col.blue) if ok else fallback


class RadarArea(Gtk.DrawingArea):
    """The mark, live. Repainted only while its state has something to say."""

    def __init__(self, size=34):
        super().__init__()
        self.size = size
        self.set_size_request(size, size)
        self.state = "verify"
        self.awake = "none"
        self.reduce = False
        self.phase = 0.0
        self.connect("draw", self._on_draw)

    def _on_draw(self, _w, cr):
        draw_radar(cr, self.size, self.state, self.phase, _ink(self),
                   self.awake, self.reduce)
        return False


class Spark(Gtk.DrawingArea):
    """7-day token sparkline — the same series the popover and TUI show, in
    the theme's ink (never the accent colour)."""

    def __init__(self, height=26):
        super().__init__()
        self.vals = []
        self.set_size_request(-1, height)
        self.connect("draw", self._on_draw)

    def _on_draw(self, _w, cr):
        w = self.get_allocated_width()
        h = self.get_allocated_height()
        vals = self.vals or [0]
        top = max(vals) or 1
        n = len(vals)
        bw = max(2.0, w / max(1, n) - 2)
        rgb = _ink(self, DIM)
        for i, v in enumerate(vals):
            bh = max(1.0, (v / top) * (h - 2))
            x = i * (w / max(1, n)) + 1
            cr.rectangle(x, h - bh, bw, bh)
            cr.set_source_rgba(rgb[0], rgb[1], rgb[2],
                               0.25 + 0.55 * (v / top))
            cr.fill()
        return False


def _reveal(w, on=True):
    """Show or hide a subtree whose root is marked no-show-all.

    Those widgets exist so a blanket show_all() cannot reveal both the "usage
    is paused" message and a set of usage meters at the same time — but
    no-show-all also makes show_all() a no-op on the subtree, so revealing one
    has to walk it. This is that walk.
    """
    if not on:
        w.hide()
        return
    if isinstance(w, Gtk.Container):
        for child in w.get_children():
            _reveal(child, True)
    w.show()


def _meter(frac, tone=None):
    pb = Gtk.ProgressBar()
    pb.set_fraction(max(0.0, min(1.0, frac or 0.0)))
    pb.get_style_context().add_class("tower-meter")
    if tone:
        pb.get_style_context().add_class(tone)
    return pb


# --------------------------------------------------------------------------- #
# Notifications — src/Notifier.swift's policy.
#
# Driven by the daemon's own transition log (agents.events), behind a
# watermark so each transition is judged once:
#   → failed / → pending_tool / → asking: always while fresh; a stale one (a
#     suspend backlog) only if the agent is STILL in that state — still on you.
#   → done: only while fresh AND nobody has had the panel open in the last
#     minute (the person watching just saw it happen).
# "Fresh" = younger than MAX_EVENT_AGE_S; older transitions are history, never
# a burst of late popups. Never on entering "working" — an agent doing its job
# is not news. Clicking one shows that agent's terminal, when it has one.
#
# Spoken straight to org.freedesktop.Notifications over GIO's D-Bus, so this
# adds no dependency: libnotify would be a package, and the bus is already
# there. One notification per session, replaced on each new transition, so a
# flapping agent cannot stack up a wall of popups.
# --------------------------------------------------------------------------- #
MAX_EVENT_AGE_S = 180
DONE_QUIET_S = 60


def notification_text(status, sess):
    """(summary, body) — the app's wording for each transition."""
    project = sess.get("project_name") or "an agent"
    title = sess.get("title")
    if status == "failed":
        return (f"{project} hit an error",
                title or sess.get("activity") or "The agent failed — it needs a look.")
    if status == "pending_tool":
        pt = sess.get("pending_tool") if isinstance(sess.get("pending_tool"), dict) else {}
        return (f"{project} is waiting for approval",
                f"Tool: {pt['name']}" if pt.get("name") else "A tool call needs your OK.")
    if status == "asking":
        return (f"{project} asked you a question",
                title or "It's blocked on your answer.")
    return (f"{project} finished its turn",
            sess.get("result") or title or "The result is ready.")


def notifications_due(s, watermark, panel_seen_at, now=None):
    """The transitions worth a popup since `watermark` -> (due, new_watermark).
    Pure, so the policy can be checked without a bus. `due` is a list of
    (status, session)."""
    now = now or time.time()
    ag = (s or {}).get("agents") or {}
    events = [e for e in (ag.get("events") or []) if isinstance(e, dict)
              and isinstance(e.get("t"), (int, float)) and e["t"] > watermark]
    if not events:
        return [], watermark
    # Advance over the whole batch BEFORE deciding: a transition we choose to
    # drop (stale, or panel-suppressed) is dropped for good.
    new_mark = max(e["t"] for e in events)
    by_id = {x.get("session_id"): x for x in sessions(s)}
    due = []
    for e in sorted(events, key=lambda e: e["t"]):
        to = e.get("to")
        sess = by_id.get(e.get("session_id")) or {"session_id": e.get("session_id")}
        age = now - e["t"]
        if to in NEED:
            if age <= MAX_EVENT_AGE_S or sess.get("status") == to:
                due.append((to, sess))
        elif to in TURN:
            if age <= MAX_EVENT_AGE_S and now - panel_seen_at > DONE_QUIET_S:
                due.append((to, sess))
    return due, new_mark


class Notifier:
    def __init__(self):
        self.watermark = time.time()    # the backlog at launch is not news
        self._ids = {}                  # session_id -> notification id to replace
        self._by_id = {}                # notification id -> (session_id, focusable)
        self._bus = None
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            self._bus.signal_subscribe(
                None, "org.freedesktop.Notifications", "ActionInvoked",
                "/org/freedesktop/Notifications", None,
                Gio.DBusSignalFlags.NONE, self._on_action)
        except GLib.Error:
            self._bus = None            # no bus: run silent, never crash

    def sync(self, s, panel_seen_at):
        due, self.watermark = notifications_due(s, self.watermark, panel_seen_at)
        for status, sess in due:
            self._fire(sess, status)

    def _fire(self, sess, st):
        sid = sess.get("session_id")
        if self._bus is None or not sid:
            return
        summary, body = notification_text(st, sess)
        # urgency 2 = critical, for a failure only — it is rank 1.
        hints = {
            "urgency": GLib.Variant("y", 2 if st == "failed" else 1),
            # Lets the shell attribute (and collapse) these as Tower's.
            "desktop-entry": GLib.Variant("s", "tower-tray"),
        }
        # "default" is the click on the bubble itself; offered only when there
        # is a terminal to show (tmux on Linux).
        actions = ["default", "Show terminal"] if sess.get("focusable") else []
        args = GLib.Variant("(susssasa{sv}i)", (
            "Tower", self._ids.get(sid, 0), "tower",
            _clip(summary, 90), _clip(body, 200), actions, hints, -1))
        try:
            self._bus.call(
                "org.freedesktop.Notifications",
                "/org/freedesktop/Notifications",
                "org.freedesktop.Notifications", "Notify",
                args, GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, 5000,
                None, self._got_id, (sid, bool(actions)))
        except GLib.Error:
            pass

    def _got_id(self, bus, res, ctx):
        sid, focusable = ctx
        try:
            nid = bus.call_finish(res).unpack()[0]
        except GLib.Error:
            return                      # no notification daemon; stay quiet
        old = self._ids.get(sid)
        if old is not None:
            self._by_id.pop(old, None)
        self._ids[sid] = nid
        self._by_id[nid] = (sid, focusable)

    def _on_action(self, _conn, _sender, _path, _iface, _sig, params):
        try:
            nid, key = params.unpack()
        except (TypeError, ValueError):
            return
        hit = self._by_id.get(nid)
        if hit and hit[1] and key == "default":
            send({"cmd": "focus", "session_id": hit[0]})


# --------------------------------------------------------------------------- #
# The panel — the popover, as a window.
#
# Section ORDER is fixed because it encodes attention (docs/DESIGN.md):
# header → net weather → agents (needs-you first) → location → keep-awake →
# plan. Widgets are built once and updated in place; rebuilding the tree every
# second would flicker and steal focus mid-click. Only the agent list is
# rebuilt, and only when its rows actually change.
#
# It is a plain decorated window, not a popover: Wayland gives a client no way
# to place a surface under a top-bar item, so pretending to be attached would
# mean a panel that lands in the wrong place. A titled window is the honest
# shape, and it is what every Linux indicator app of this kind does.
# --------------------------------------------------------------------------- #
class Panel(Gtk.Window):
    def __init__(self, tray):
        super().__init__(title="Tower")
        self.tray = tray
        self.set_default_size(392, 640)
        self.set_resizable(True)
        self.set_skip_taskbar_hint(False)
        self.set_icon_name("tower")
        self.connect("delete-event", self._on_close)
        self._agent_sig = None
        self._hold_until = 0.0
        self._syncing = False

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(outer)

        outer.pack_start(self._build_header(), False, False, 0)
        outer.pack_start(Gtk.Separator(), False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for build in (self._build_net, self._build_agents, self._build_location,
                      self._build_keepawake, self._build_plan):
            if col.get_children():
                col.pack_start(Gtk.Separator(), False, False, 0)
            col.pack_start(build(), False, False, 0)
        scroll.add(col)
        outer.pack_start(scroll, True, True, 0)

        outer.pack_start(Gtk.Separator(), False, False, 0)
        outer.pack_start(self._build_footer(), False, False, 0)

    def _on_close(self, *_a):
        self.hide()
        return True     # closing the panel never quits the guard

    # ---- header ---------------------------------------------------------- #
    def _build_header(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.get_style_context().add_class("tower-pad")
        self.radar = RadarArea(34)
        box.pack_start(self.radar, False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        self.h_title = _label("Starting…", "tower-title")
        self.h_sub = _label("", "tower-sub")
        self.h_pending = _label("", "tower-sub tower-warn")
        self.h_pending.set_no_show_all(True)
        texts.pack_start(self.h_title, False, False, 0)
        texts.pack_start(self.h_sub, False, False, 0)
        texts.pack_start(self.h_pending, False, False, 0)
        box.pack_start(texts, True, True, 0)
        self.route_switch = Gtk.Switch()
        self.route_switch.set_valign(Gtk.Align.CENTER)
        self.route_switch.get_style_context().add_class("tower-switch")
        self.route_switch.set_tooltip_text(
            "Route Claude Code through the guard")
        self.route_switch.connect("notify::active", self._on_route)
        box.pack_start(self.route_switch, False, False, 0)
        return box

    def _on_route(self, sw, _p):
        if self._syncing:
            return
        if sw.get_active():
            self._hold_until = time.time() + HOLD_S
            send({"cmd": "route", "on": True})
            return
        # Turning the guard OFF is destructive: snap back to ON at once — it
        # only goes off once both confirmations are given.
        self._syncing = True
        sw.set_active(True)
        self._syncing = False
        GLib.idle_add(self.tray.confirm_route_off)

    # ---- net ------------------------------------------------------------- #
    def _build_net(self):
        box = _section("NETWORK")
        self.net_status = _label("—", "tower-row")
        box.pack_start(self.net_status, False, False, 0)
        self.net_detail = _label("", "tower-sub")
        box.pack_start(self.net_detail, False, False, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.speed_btn = Gtk.Button(label="Speed test")
        self.speed_btn.connect("clicked", lambda _b: send({"cmd": "speedtest"}))
        row.pack_start(self.speed_btn, False, False, 0)
        self.speed_label = _label("", "tower-sub")
        self.speed_label.set_valign(Gtk.Align.CENTER)
        row.pack_start(self.speed_label, True, True, 0)
        box.pack_start(row, False, False, 0)
        return box

    # ---- agents ---------------------------------------------------------- #
    def _build_agents(self):
        box = _section("AGENTS")
        self.agents_head = box.get_children()[0]
        self.agents_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,
                                   spacing=8)
        box.pack_start(self.agents_list, False, False, 0)
        return box

    def _agent_row(self, row, kind):
        """One agent. Clicking it shows its terminal (when it has one — tmux on
        Linux); what is listed in Needs You can also be dismissed."""
        reason, sess, since = row
        sid = sess.get("session_id")
        phrase, detail = agent_what(reason, sess)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        top.pack_start(_label(agent_name(sess), "tower-row"), True, True, 0)
        fam = (sess.get("model_family") or "").lower()
        if fam in TIER_RANK:
            top.pack_start(_label(model_label(sess), "tower-tier-" + fam),
                           False, False, 0)
        body.pack_start(top, False, False, 0)

        sub = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        if kind == "need":
            tone = "tower-bad" if reason == "failed" else "tower-warn"
            what = _label("", "tower-sub", wrap=True)
            what.set_markup(
                f'<span weight="bold">{_esc(phrase)}</span>'
                + (f"  {_esc(_clip(detail, 120))}"
                   if detail else ""))
            what.get_style_context().add_class(tone)
            when = ago(since)
        elif kind == "turn":
            what = _label("", "tower-sub", wrap=True)
            text = phrase + (f" — {_clip(detail, 120)}" if detail else "")
            what.set_markup(_dot(GREEN_HEX, text) if reason == "done"
                            else _esc(text))
            when = ago(since)
        elif kind == "paused":
            what = _label("paused", "tower-sub")
            when = ""
        else:
            what = _label(_clip(detail, 120), "tower-sub", wrap=True)
            t0 = sess.get("turn_at") or sess.get("status_since")
            when = dur(time.time() - t0) if isinstance(t0, (int, float)) else ""
        sub.pack_start(what, True, True, 0)
        if when:
            sub.pack_start(_label(when, "tower-count"), False, False, 0)
        body.pack_start(sub, False, False, 0)

        line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        if sess.get("focusable") and sid:
            btn = Gtk.Button()
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.get_style_context().add_class("tower-agent")
            btn.set_tooltip_text("Show this agent's terminal (tmux)")
            btn.add(body)
            btn.connect("clicked", lambda _b, i=sid: send(
                {"cmd": "focus", "session_id": i}))
            line.pack_start(btn, True, True, 0)
        else:
            line.pack_start(body, True, True, 0)
        if kind in ("need", "turn") and sid:
            x = Gtk.Button(label="✕")
            x.set_relief(Gtk.ReliefStyle.NONE)
            x.set_valign(Gtk.Align.START)
            x.get_style_context().add_class("tower-x")
            x.set_tooltip_text("Dismiss — until its next change")
            x.connect("clicked", lambda _b, i=sid: send(
                {"cmd": "dismiss", "session_id": i}))
            line.pack_start(x, False, False, 0)
        return line

    # ---- location -------------------------------------------------------- #
    def _build_location(self):
        box = _section("LOCATION")
        self.loc_where = _label("—", "tower-row")
        box.pack_start(self.loc_where, False, False, 0)
        self.loc_detail = _label("", "tower-sub", wrap=True, selectable=True)
        box.pack_start(self.loc_detail, False, False, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.country = Gtk.ComboBoxText()
        for cc, name in COUNTRY_LIST:
            self.country.append(cc, name)
        self.country.connect("changed", self._on_country)
        row.pack_start(self.country, True, True, 0)
        rc = Gtk.Button(label="Re-check")
        rc.connect("clicked", lambda _b: send({"cmd": "recheck"}))
        row.pack_start(rc, False, False, 0)
        box.pack_start(row, False, False, 0)
        return box

    def _on_country(self, combo):
        if self._syncing:
            return
        cc = combo.get_active_id()
        if cc:
            self._hold_until = time.time() + HOLD_S
            send({"cmd": "country", "cc": cc})

    # ---- keep-awake ------------------------------------------------------ #
    def _build_keepawake(self):
        box = _section("KEEP AWAKE")
        self.ka_title = _label("", "tower-row")
        box.pack_start(self.ka_title, False, False, 0)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        row.get_style_context().add_class("linked")
        self.ka_buttons = {}
        first = None
        for mode, text in (("off", "Off"), ("idle", "Keep awake"),
                           ("clamshell", "Lid closed")):
            btn = Gtk.RadioButton.new_with_label_from_widget(first, text)
            if first is None:
                first = btn
            btn.set_mode(False)         # draw as a toggle, not a radio dot
            btn.connect("toggled", self._on_keepawake, mode)
            self.ka_buttons[mode] = btn
            row.pack_start(btn, True, True, 0)
        box.pack_start(row, False, False, 0)
        self.ka_detail = _label("", "tower-sub", wrap=True)
        box.pack_start(self.ka_detail, False, False, 0)
        return box

    def _on_keepawake(self, btn, mode):
        if self._syncing or not btn.get_active():
            return
        self._hold_until = time.time() + HOLD_S
        send({"cmd": "keepawake", "on": mode != "off", "mode": mode})

    # ---- plan ------------------------------------------------------------ #
    def _build_plan(self):
        box = _section("PLAN LIMITS")
        self.plan_note = _label("", "tower-sub")
        box.pack_start(self.plan_note, False, False, 0)

        # Two mutually exclusive children: the honest gate message, or meters.
        # Never both, and never stale numbers behind a gate.
        self.gate_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.gate_head = _label("", "tower-row", wrap=True)
        self.gate_detail = _label("", "tower-sub", wrap=True)
        self.gate_box.pack_start(self.gate_head, False, False, 0)
        self.gate_box.pack_start(self.gate_detail, False, False, 0)
        self.gate_box.set_no_show_all(True)
        box.pack_start(self.gate_box, False, False, 0)

        self.meter_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.meters = {}
        for key, text in (("session", "Session"), ("week", "Week all"),
                          ("fable", "Fable")):
            line = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            name = _label(text, "tower-row")
            pct = _label("", "tower-count")
            pct.set_xalign(1.0)
            head.pack_start(name, True, True, 0)
            head.pack_start(pct, False, False, 0)
            meter = _meter(0)
            line.pack_start(head, False, False, 0)
            line.pack_start(meter, False, False, 0)
            line.set_no_show_all(True)
            self.meters[key] = (line, pct, meter)
            self.meter_box.pack_start(line, False, False, 0)
        self.meter_box.set_no_show_all(True)
        box.pack_start(self.meter_box, False, False, 0)

        est = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        est.pack_start(_label("local estimate · measured on this machine, "
                              "not your plan %", "tower-sub"), False, False, 0)
        self.est_session = _label("", "tower-sub")
        self.est_week = _label("", "tower-sub")
        self.est_models = _label("", "tower-sub")
        for w in (self.est_session, self.est_week, self.est_models):
            est.pack_start(w, False, False, 0)
        self.est_models.set_no_show_all(True)
        self.spark = Spark()
        self.spark.set_no_show_all(True)
        est.pack_start(self.spark, False, False, 0)
        box.pack_start(est, False, False, 0)
        return box

    # ---- footer ---------------------------------------------------------- #
    def _build_footer(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.get_style_context().add_class("tower-pad")
        term = Gtk.Button(label="Terminal dashboard")
        term.connect("clicked", lambda _b: self.tray.open_terminal())
        box.pack_start(term, False, False, 0)
        self.traffic = _label("", "tower-count")
        self.traffic.set_valign(Gtk.Align.CENTER)
        box.pack_start(self.traffic, True, True, 0)
        quit_btn = Gtk.Button(label="Quit Tower")
        quit_btn.get_style_context().add_class("destructive-action")
        quit_btn.connect("clicked", lambda _b: self.tray.request_quit())
        box.pack_start(quit_btn, False, False, 0)
        return box

    # ---- ticks ----------------------------------------------------------- #
    def tick_radar(self, phase, reduce_motion):
        """Animation only. Called at the frame rate, so it must stay this
        small — re-running the whole panel five times a second to move one
        mark is how a status app ends up costing a CPU core."""
        self.radar.phase = phase
        self.radar.reduce = reduce_motion
        self.radar.queue_draw()

    def update(self, s, av, phase, reduce_motion):
        self.radar.state = radar_state(s)
        self.radar.awake = awake_glow(s)
        self.tick_radar(phase, reduce_motion)
        if s is None:
            self.h_title.set_text("Starting…")
            _tone(self.h_title, "tower-dim")
            self.h_sub.set_text("waiting for the guard daemon")
            self.h_pending.hide()
            return

        g = s.get("guard") or {}
        title, tone = guard_status(s)
        self.h_title.set_text(title)
        _tone(self.h_title, TONE_CLASS.get(tone))

        bits = [f"fenced to {cname(g.get('target_cc'))}"]
        if av.working_n:
            bits.append(f"{av.working_n} at work")
        if av.need_n:
            bits.append(f"{av.need_n} need{'s' if av.need_n == 1 else ''} you")
        self.h_sub.set_text(" · ".join(bits))
        # The guard is holding a Claude request (it retries on its own): the
        # app's "Reconnecting Claude…" line.
        held = g.get("holding") if isinstance(g.get("holding"), int) else 0
        if g.get("pending") or held:
            self.h_pending.set_text("Reconnecting Claude…"
                                    + (f" · {held} held" if held else ""))
            self.h_pending.show()
        else:
            self.h_pending.hide()

        self._syncing = True
        if time.time() > self._hold_until:
            self.route_switch.set_active(
                bool((s.get("routing") or {}).get("intended")))
        self._syncing = False

        self._update_net(s)
        self._update_agents(s, av)
        self._update_location(s, g)
        self._update_keepawake(s)
        self._update_plan(s)
        self.traffic.set_text(f"{g.get('allowed', 0)} allowed · "
                              f"{g.get('blocked', 0)} blocked")

    def _update_net(self, s):
        net = s.get("net") or {}
        st = net.get("status") or "—"
        words = {"online": "Online", "degraded": "Online — slow",
                 "offline": "Internet down",
                 "captive": "Wi-Fi login required",
                 "api_issue": "Anthropic API unreachable",
                 "checking": "Measuring the connection…"}
        text = words.get(st, st)
        if st == "online":
            self.net_status.set_markup(_dot(GREEN_HEX, text))
            _tone(self.net_status, None)
        else:
            self.net_status.set_text(text)
            _tone(self.net_status,
                  "tower-dim" if st in ("checking", "—")
                  else "tower-warn" if st == "degraded" else "tower-bad")
        parts = []
        if net.get("internet_ms"):
            parts.append(f"internet {net['internet_ms']:.0f} ms")
        if net.get("api_ms"):
            parts.append(f"Anthropic {net['api_ms']:.0f} ms")
        if net.get("api_error"):
            parts.append(str(net["api_error"]))
        self.net_detail.set_text(" · ".join(parts))
        sp = net.get("speedtest") or {}
        if sp.get("running"):
            self.speed_btn.set_sensitive(False)
            self.speed_label.set_text(f"measuring… {sp.get('progress', 0):.0%}")
        else:
            self.speed_btn.set_sensitive(True)
            if sp.get("error"):
                self.speed_label.set_text(str(sp["error"]))
            elif sp.get("mbps_down"):
                self.speed_label.set_text(
                    f"{sp['mbps_down']:.1f} Mbps down · {ago(sp.get('at'))}")
            else:
                self.speed_label.set_text("")

    def _update_agents(self, s, av):
        counts = []
        if av.working_n:
            counts.append(f"{av.working_n} at work")
        if av.done_today:
            counts.append(f"{av.done_today} done today")
        if av.need_n:
            counts.append(f"{av.need_n} need{'s' if av.need_n == 1 else ''} you")
        self.agents_head.set_text(" · ".join(["AGENTS"] + counts))

        # Rebuild only on a real change (or once a minute, for the clocks):
        # every second would flicker and could yank a button out from under a
        # click.
        sig = (tuple((r[0], r[1].get("session_id"), r[1].get("activity"),
                      r[1].get("result"), r[1].get("model_family"),
                      bool(r[1].get("focusable")), r[2])
                     for r in av.listed),
               tuple((c.get("git_root"), c.get("level"),
                      tuple(c.get("files") or ())) for c in av.collisions),
               av.resting, int(time.time() // 60))
        if sig == self._agent_sig:
            return
        self._agent_sig = sig
        for child in self.agents_list.get_children():
            self.agents_list.remove(child)
        for c in av.collisions[:3]:
            n = len(c.get("session_ids") or []) or 2
            repo = os.path.basename(str(c.get("git_root") or "")) or "one repo"
            files = c.get("files") or []
            same_file = c.get("level") == "file" and files
            text = f"{n} agents in {repo}" + (
                f" — both touching {os.path.basename(str(files[0]))}"
                if same_file else "")
            self.agents_list.pack_start(
                _label(text, "tower-row " + ("tower-bad" if same_file
                                             else "tower-warn"), wrap=True),
                False, False, 0)
        if av.need or av.turn:
            self.agents_list.pack_start(_label("NEEDS YOU", "tower-section"),
                                        False, False, 0)
            for r in av.need:
                self.agents_list.pack_start(self._agent_row(r, "need"),
                                            False, False, 0)
            for r in av.turn:
                self.agents_list.pack_start(self._agent_row(r, "turn"),
                                            False, False, 0)
        for r in av.working:
            self.agents_list.pack_start(self._agent_row(r, "working"),
                                        False, False, 0)
        for r in av.paused:
            self.agents_list.pack_start(self._agent_row(r, "paused"),
                                        False, False, 0)
        if av.resting:
            self.agents_list.pack_start(
                _label(f"{av.resting} resting", "tower-sub"), False, False, 0)
        if not (av.listed or av.resting):
            self.agents_list.pack_start(
                _label("No agents running.", "tower-sub"), False, False, 0)
        self.agents_list.show_all()

    def _update_location(self, s, g):
        loc = s.get("location") or {}
        st = loc.get("status")
        where = ", ".join(x for x in (loc.get("city"), loc.get("region"),
                                      loc.get("country_name")) if x)
        if st == "OK":
            self.loc_where.set_text(where or cname(loc.get("country_cc")))
        elif st == "CHECKING":
            self.loc_where.set_text("Checking…")
        else:
            self.loc_where.set_text(where or "Location unknown")
        out = st == "OK" and not loc.get("in_target")
        _tone(self.loc_where, "tower-warn" if out
              else "tower-dim" if st != "OK" else None)
        target = cname(g.get("target_cc"))
        detail = [_esc(x)
                  for x in (loc.get("ip"), loc.get("isp")) if x]
        if loc.get("error"):
            detail.append(_esc(str(loc["error"])))
        if st == "OK" and loc.get("in_target"):
            detail.insert(0, _dot(GREEN_HEX, f"in {target}"))
        elif out:
            detail.insert(0, f'<span foreground="{AMBER_HEX}">'
                             f'{_esc(f"outside {target} — Claude is held")}'
                             f'</span>')
        self.loc_detail.set_markup(" · ".join(detail))
        self._syncing = True
        if time.time() > self._hold_until:
            cc = (g.get("target_cc") or "").upper()
            if cc and self.country.get_active_id() != cc:
                self.country.set_active_id(cc)
        self._syncing = False

    def _update_keepawake(self, s):
        mode = keepawake_mode(s)
        self._syncing = True
        btn = self.ka_buttons.get(mode)
        if btn is not None and not btn.get_active() \
                and time.time() > self._hold_until:
            btn.set_active(True)
        self._syncing = False
        self.ka_title.set_text(keepawake_title(s))
        self.ka_detail.set_text(keepawake_line(s))

    def _update_plan(self, s):
        plan = s.get("plan") or {}
        u = s.get("usage") or {}
        gate = usage_gate(s)
        if gate:
            self.plan_note.set_text("")
        elif plan.get("disabled"):
            self.plan_note.set_text("live limits off (no Claude runs)")
        elif plan.get("ok"):
            self.plan_note.set_text(
                "updating…" if plan.get("refreshing")
                else f"updated {ago(plan.get('updated'))}")
        elif plan.get("error"):
            self.plan_note.set_text(f"unavailable — {plan['error']}")
        else:
            self.plan_note.set_text("fetching from Claude /usage…")

        if gate:
            head, detail = gate
            self.gate_head.set_text(head)
            self.gate_detail.set_text(detail)
            _reveal(self.gate_box, True)
            self.meter_box.hide()
        else:
            self.gate_box.hide()
            self.meter_box.show()
            for key, (line, pct_lb, meter) in self.meters.items():
                node = plan.get(key) or {}
                p = node.get("pct")
                if p is None or not plan.get("ok"):
                    line.hide()
                    continue
                _reveal(line, True)
                txt = f"{p}%"
                rt = reset_text(node)
                if rt:
                    txt += f" · resets {rt}"
                pct_lb.set_text(txt)
                meter.set_fraction(max(0.0, min(1.0, p / 100.0)))
                # Ink until the warn line; amber, then red, only past it.
                _tone(meter, "tower-bad" if p >= 90
                      else "tower-warn" if p >= 75 else None)

        sess = u.get("session") or {}
        wk = u.get("week") or {}
        pace = u.get("pace") or {}
        self.est_session.set_text(
            f"session  {fmt_tok(sess.get('tokens'))} tokens · "
            f"{fmt_cost(sess.get('cost'))} · {sess.get('msgs', 0)} msgs")
        proj = pace.get("projected_week_tokens")    # None the first day after a reset
        self.est_week.set_text(
            f"week  {fmt_tok(wk.get('tokens'))} tokens · "
            f"{fmt_cost(wk.get('cost'))}"
            + (f" · ~{fmt_tok(proj)} projected" if proj is not None else ""))
        bm = u.get("byModel") or []
        models = " · ".join(f"{_model_short(m.get('model'))} "
                            f"{fmt_tok(m.get('tokens'))}" for m in bm[:4])
        self.est_models.set_text(models)
        _reveal(self.est_models, bool(models))
        vals = [d.get("tokens", 0) for d in (u.get("series") or [])]
        # An all-zero week is not a trend — a flat line of 1px bars would read
        # as data. Show nothing until there is something.
        vals = vals if any(vals) else []
        if vals != self.spark.vals:
            self.spark.vals = vals
            self.spark.queue_draw()
        _reveal(self.spark, bool(vals))


# --------------------------------------------------------------------------- #
# The tray — the top-bar item, its menu, and the one-second heartbeat.
#
# The menu carries the live status and the everyday controls, because on a
# StatusNotifierItem host a left-click *is* the menu: there is no separate
# "activate" a client can rely on, so the menu is the front door and the panel
# opens from it.
# --------------------------------------------------------------------------- #
def _set_label(item, text):
    """Set a menu item's label only when it changed — each set is a D-Bus
    property update to the shell, and the heartbeat runs every second."""
    if item.get_label() != text:
        item.set_label(text)


class TowerTray:
    def __init__(self, app):
        self.app = app
        self.icons = IconCache()
        self.notifier = Notifier()
        self.sup = Supervisor()
        self.panel_seen_at = 0.0
        self.t0 = time.monotonic()
        self.frame = 0
        self.state = None
        self.av = AgentsView(None)
        self.icon_key = None
        self.agent_sig = None
        self.hold_until = 0.0
        self._syncing = False
        self._reduce = False
        self._icon_anim = False
        self._panel_anim = False
        self._frame_src = None
        self._badge = None
        self._dialog_open = False

        provider = Gtk.CssProvider()
        try:
            provider.load_from_data(CSS)
        except GLib.Error:
            pass                        # an odd theme parser: plain look, no crash
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.panel = Panel(self)
        self.panel.set_application(app)
        self.panel.connect("show", lambda _w: self._refresh_clock())
        self.panel.connect("hide", lambda _w: self._refresh_clock())
        self.menu = self._build_menu()

        self.icons.ensure("verify", "none")
        self.ind = _IND.Indicator.new(
            APP_ID, self.icons.name("verify", "none", "still"),
            _IND.IndicatorCategory.APPLICATION_STATUS)
        self.ind.set_icon_theme_path(ICON_DIR)
        self.ind.set_status(_IND.IndicatorStatus.ACTIVE)
        self.ind.set_title("Tower")
        self.ind.set_menu(self.menu)
        # Middle-click is the one gesture a host reliably forwards past the
        # menu; make it the shortcut to the panel.
        self.ind.set_secondary_activate_target(self.open_item)

        # Opening Tower arms the guard: start a daemon now if none answers.
        self.sup.start(fresh(load_state()))
        GLib.timeout_add(POLL_MS, self._tick_state)
        self._tick_state()

    # ---- menu ------------------------------------------------------------ #
    def _build_menu(self):
        menu = Gtk.Menu()

        self.status_item = Gtk.MenuItem(label="Starting…")
        self.status_item.set_sensitive(False)
        menu.append(self.status_item)
        self.detail_item = Gtk.MenuItem(label="")
        self.detail_item.set_sensitive(False)
        menu.append(self.detail_item)

        menu.append(Gtk.SeparatorMenuItem())

        self.open_item = Gtk.MenuItem(label="Open Tower…")
        self.open_item.connect("activate", lambda _i: self.show_panel())
        menu.append(self.open_item)

        self.route_item = Gtk.CheckMenuItem(
            label="Route Claude through the guard")
        self.route_item.connect("toggled", self._on_route_item)
        menu.append(self.route_item)

        recheck = Gtk.MenuItem(label="Re-check location & network")
        recheck.connect("activate", lambda _i: send({"cmd": "recheck"}))
        menu.append(recheck)

        # keep-awake submenu
        ka_item = Gtk.MenuItem(label="Keep awake")
        ka_menu = Gtk.Menu()
        self.ka_items = {}
        first = None
        for mode, text in (("off", "Off"), ("idle", "Keep awake"),
                           ("clamshell", "Lid closed")):
            it = Gtk.RadioMenuItem.new_with_label_from_widget(first, text)
            if first is None:
                first = it
            it.connect("toggled", self._on_ka_item, mode)
            self.ka_items[mode] = it
            ka_menu.append(it)
        ka_item.set_submenu(ka_menu)
        menu.append(ka_item)

        # country submenu
        cc_item = Gtk.MenuItem(label="Country")
        cc_menu = Gtk.Menu()
        self.cc_items = {}
        first = None
        for cc, name in COUNTRY_LIST:
            it = Gtk.RadioMenuItem.new_with_label_from_widget(first, name)
            if first is None:
                first = it
            it.connect("toggled", self._on_cc_item, cc)
            self.cc_items[cc] = it
            cc_menu.append(it)
        cc_item.set_submenu(cc_menu)
        menu.append(cc_item)

        menu.append(Gtk.SeparatorMenuItem())

        self.agents_item = Gtk.MenuItem(label="No agents running")
        self.agents_menu = Gtk.Menu()
        self.agents_item.set_submenu(self.agents_menu)
        menu.append(self.agents_item)

        menu.append(Gtk.SeparatorMenuItem())

        term = Gtk.MenuItem(label="Terminal dashboard")
        term.connect("activate", lambda _i: self.open_terminal())
        menu.append(term)

        quit_item = Gtk.MenuItem(label="Quit Tower…")
        quit_item.connect("activate", lambda _i: self.request_quit())
        menu.append(quit_item)

        menu.show_all()
        return menu

    def _on_route_item(self, item):
        if self._syncing:
            return
        if item.get_active():
            self.hold_until = time.time() + HOLD_S
            send({"cmd": "route", "on": True})
            return
        self._syncing = True
        item.set_active(True)          # only a confirmed off actually turns off
        self._syncing = False
        GLib.idle_add(self.confirm_route_off)

    def _on_ka_item(self, item, mode):
        if self._syncing or not item.get_active():
            return
        self.hold_until = time.time() + HOLD_S
        send({"cmd": "keepawake", "on": mode != "off", "mode": mode})

    def _on_cc_item(self, item, cc):
        if self._syncing or not item.get_active():
            return
        self.hold_until = time.time() + HOLD_S
        send({"cmd": "country", "cc": cc})

    # ---- actions --------------------------------------------------------- #
    def show_panel(self):
        self.panel_seen_at = time.time()
        # Catch the panel up before it is shown, so it never opens stale.
        self.panel.update(self.state, self.av, self._phase(), self._reduce)
        self.panel.show_all()
        self.panel.present()

    def open_terminal(self):
        """Open the curses dashboard in whatever terminal this desktop has."""
        tui = "/usr/lib/tower/tower-tui.py"
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "tower-tui.py")
        if os.path.exists(local):
            tui = local
        cmd = ["tower"] if _which("tower") else [sys.executable or "python3", tui]
        for term, arg in (("x-terminal-emulator", "-e"),
                          ("gnome-terminal", "--"), ("ptyxis", "--"),
                          ("kgx", "--"), ("konsole", "-e"),
                          ("xfce4-terminal", "-x"), ("tilix", "-e"),
                          ("alacritty", "-e"), ("kitty", ""), ("xterm", "-e")):
            if not _which(term):
                continue
            argv = [term] + ([arg] if arg else []) + cmd
            try:
                subprocess.Popen(argv, start_new_session=True)
                return
            except OSError:
                continue
        self.message("No terminal emulator found",
                     "Install one, or run the dashboard yourself:\n\n  tower")

    def confirm_route_off(self):
        """Route off is the double-confirmed danger path (the app's
        setRouting(false)). Returns False so it can run from idle_add."""
        self.danger(
            "Turn off the guard?",
            "This removes routing from settings.json and Claude Code connects "
            "DIRECTLY to the API — with no country guard at all.",
            "Turn off guard",
            "This lets Claude Code reach the API with NO location guard — "
            "requests can go out from the wrong country.",
            "Yes, disable protection",
            lambda: send({"cmd": "route", "on": False}))
        return False

    def request_quit(self):
        """Quitting is destructive twice over: it removes the guard, and every
        chat pinned to the proxy keeps working through the daemon's relay but
        with no guard until Tower is reopened. Both numbers go in the warning
        — the app's quit alert, word for word."""
        self.danger(
            "Quit Tower and turn off the guard?",
            "Quitting removes routing from settings.json — Claude Code goes "
            "back to a DIRECT connection with no country guard at all.",
            "Continue…",
            "This disables Claude Code's location protection entirely until "
            "you reopen Tower.",
            "Quit & Disable Guard",
            self._do_quit, pinned=True)

    def _do_quit(self):
        # Confirmed: stop supervising FIRST. The daemon deletes state.json on
        # its way out, and the very next tick would otherwise read that as a
        # crash and start a fresh daemon that re-routes Claude.
        self.sup.confirmed_quit = True
        send({"cmd": "quit"})
        # Give the daemon its moment to un-route settings.json before we go.
        GLib.timeout_add(1200, self._finish_quit)

    def _finish_quit(self):
        self.app.quit()
        return False

    # ---- the two-stage danger gate --------------------------------------- #
    def danger(self, title, message, confirm, final_message, final_confirm,
               perform, pinned=False):
        """Anything that lets Claude reach the API without the guard is warned
        hard and confirmed twice, and both steps say how many agents are
        working right now — they would start sending unguarded requests the
        moment this takes effect (and, for a quit, how many chats are pinned
        to the proxy). The counts are re-read at each step."""
        if self._dialog_open or self.sup.confirmed_quit:
            return
        self._dialog_open = True
        try:
            if not self._ask(title, message + self._clauses(pinned),
                             "Cancel", confirm):
                return
            if not self._ask("Are you absolutely sure?",
                             final_message + self._clauses(pinned, True),
                             "Keep the guard on", final_confirm):
                return
            perform()
        finally:
            self._dialog_open = False

    def _clauses(self, pinned, always=False):
        s = self.state or {}
        parts = [working_clause(working_now(s))]
        if pinned:
            parts.append(pinned_clause(proxy_pinned_count(s)))
        parts = [p for p in parts if p]
        if not parts and always:
            parts = ["No agents are working right now."]
        return "".join("\n\n" + p for p in parts)

    def _ask(self, title, message, cancel, confirm):
        dlg = Gtk.MessageDialog(
            transient_for=self.panel if self.panel.get_visible() else None,
            modal=True, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE, text=title)
        dlg.format_secondary_text(message)
        dlg.add_button(cancel, Gtk.ResponseType.CANCEL)
        btn = dlg.add_button(confirm, Gtk.ResponseType.OK)
        btn.get_style_context().add_class("destructive-action")
        dlg.set_default_response(Gtk.ResponseType.CANCEL)
        dlg.set_keep_above(True)
        resp = dlg.run()
        dlg.destroy()
        return resp == Gtk.ResponseType.OK

    def message(self, title, body):
        dlg = Gtk.MessageDialog(
            transient_for=self.panel if self.panel.get_visible() else None,
            modal=True, message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.CLOSE, text=title)
        dlg.format_secondary_text(body)
        dlg.run()
        dlg.destroy()

    # ---- heartbeat ------------------------------------------------------- #
    def _phase(self):
        return time.monotonic() - self.t0

    @staticmethod
    def _reduce_motion():
        settings = Gtk.Settings.get_default()
        if settings is None:
            return False
        return not settings.get_property("gtk-enable-animations")

    def _icon_animates(self, s):
        """Motion = state change (docs/DESIGN.md, AppDelegate.radarShouldAnimate):
        a hold, a verify sweep, or a calm scan while agents work. Keep-awake
        never starts the clock — a vigil lasts hours, so in the bar the lamp
        is always still — and Reduce Motion is always still."""
        if self._reduce or s is None:
            return False
        st = radar_state(s)
        if st in ("verify", "holdNet", "holdGeo"):
            return True
        return st == "clear" and working_now(s) > 0

    def _refresh_clock(self):
        """Run the frame timer only while something on screen moves: the bar
        icon's state animates, or the panel is open and its radar does (the
        lid-closed vigil breathes there, and only there)."""
        s = self.state
        self._icon_anim = self._icon_animates(s)
        self._panel_anim = bool(
            self.panel.get_visible() and not self._reduce and s is not None
            and (self._icon_anim or awake_glow(s) == "clamshell"))
        want = self._icon_anim or self._panel_anim
        if want and self._frame_src is None:
            self._frame_src = GLib.timeout_add(FRAME_MS, self._tick_frame)
        elif not want and self._frame_src is not None:
            GLib.source_remove(self._frame_src)
            self._frame_src = None

    def _tick_state(self):
        raw = load_state()              # the one parse this tick
        alive = fresh(raw)
        if self.sup.confirmed_quit:
            # Quitting: show the truth, never resurrect the guard.
            s = None
        else:
            self.sup.tick(alive)
            s = raw if alive else None
        self.state = s
        self.av = av = AgentsView(s)
        self._reduce = self._reduce_motion()

        title = (guard_status(s)[0] if s
                 else "Quitting…" if self.sup.confirmed_quit else "Starting…")
        _set_label(self.status_item, "Tower — " + title)

        g = (s or {}).get("guard") or {}
        loc = (s or {}).get("location") or {}
        detail = []
        if s:
            where = loc.get("country_name") or cname(loc.get("country_cc"))
            if where and where != "—":
                detail.append(where)
            detail.append(f"fenced to {cname(g.get('target_cc'))}")
            if av.need_n:
                detail.append(f"{av.need_n} need{'s' if av.need_n == 1 else ''} you")
        _set_label(self.detail_item,
                   " · ".join(detail) or "waiting for the guard daemon")

        self._syncing = True
        if s and time.time() > self.hold_until:
            self.route_item.set_active(
                bool((s.get("routing") or {}).get("intended")))
            it = self.ka_items.get(keepawake_mode(s))
            if it is not None and not it.get_active():
                it.set_active(True)
            cc = (g.get("target_cc") or "").upper()
            it = self.cc_items.get(cc)
            if it is not None and not it.get_active():
                it.set_active(True)
        self._syncing = False

        self._sync_agents_menu(av)
        self._sync_badge(av)
        if self.panel.get_visible():
            # An open panel counts as looking: a "done" popup while you are
            # watching the row say done is noise.
            self.panel_seen_at = time.time()
            self.panel.update(s, av, self._phase(), self._reduce)
        if s is not None:
            self.notifier.sync(s, self.panel_seen_at)
        self._refresh_clock()
        self._apply_icon()
        return True

    def _sync_badge(self, av):
        """The needs-you count beside the radar — the app's needs-you pill. It
        counts only what actually needs you (failed / approval / asking),
        never a finished turn, and the bar never counts running agents."""
        text = str(av.need_n) if av.need_n else ""
        if text != self._badge:
            self._badge = text
            self.ind.set_label(text, "99")

    def _sync_agents_menu(self, av):
        rows = ([("need", r) for r in av.need] + [("turn", r) for r in av.turn]
                + [("working", r) for r in av.working])
        label = "No agents running"
        if rows:
            bits = []
            if av.working_n:
                bits.append(f"{av.working_n} at work")
            if av.need_n:
                bits.append(f"{av.need_n} need{'s' if av.need_n == 1 else ''} you")
            if av.turn:
                bits.append(f"{len(av.turn)} your turn")
            label = "Agents — " + (" · ".join(bits) or f"{len(rows)} listed")
        _set_label(self.agents_item, label)
        self.agents_item.set_sensitive(bool(rows))
        sig = tuple((k, r[0], r[1].get("session_id"), r[1].get("activity"),
                     r[1].get("result"), bool(r[1].get("focusable")))
                    for k, r in rows)
        if sig == self.agent_sig:
            return
        self.agent_sig = sig
        for child in self.agents_menu.get_children():
            self.agents_menu.remove(child)
        for kind, (reason, sess, _since) in rows:
            phrase, detail = agent_what(reason, sess)
            if kind == "need":
                what = phrase.upper() + (f" · {detail}" if detail else "")
            elif kind == "turn":
                what = phrase + (f" — {detail}" if detail else "")
            else:
                what = detail
            it = Gtk.MenuItem(label=_clip(f"{agent_name(sess)} — {what}", 80))
            sid = sess.get("session_id")
            # A row only does something when there is a terminal to show
            # (tmux on Linux); otherwise it is information, not a button.
            if sess.get("focusable") and sid:
                it.connect("activate", lambda _i, i=sid: send(
                    {"cmd": "focus", "session_id": i}))
            else:
                it.set_sensitive(False)
            self.agents_menu.append(it)
        self.agents_menu.show_all()

    def _tick_frame(self):
        if not (self._icon_anim or self._panel_anim):
            self._frame_src = None
            return False                # nothing moves: stop the clock
        if self._icon_anim:
            self.frame = (self.frame + 1) % FRAMES
            self._apply_icon()
        if self._panel_anim:
            self.panel.tick_radar(self._phase(), self._reduce)
        return True

    def _apply_icon(self):
        s = self.state
        st = radar_state(s)
        # In the bar the lamp never breathes (AppDelegate.radarShouldAnimate):
        # both keep-awake modes are a still lit lamp there.
        aw = "none" if awake_glow(s) == "none" else "idle"
        frame = self.frame if self._icon_anim else "still"
        key = (st, aw, frame)
        if key == self.icon_key:
            return              # nothing new to say; don't touch the bus
        self.icon_key = key
        self.icons.ensure(st, aw)
        what = (guard_status(s)[0] if s
                else "quitting" if self.sup.confirmed_quit else "starting")
        self.ind.set_icon_full(self.icons.name(st, aw, frame), f"Tower — {what}")


def _which(exe):
    for d in (os.environ.get("PATH") or "").split(os.pathsep):
        p = os.path.join(d, exe)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


class TrayApp(Gtk.Application):
    """One tray per session. Gtk.Application makes a second launch (the app
    grid, autostart *and* the systemd unit) hand over to the running one —
    which opens its panel — instead of adding a second radar, a second set of
    notifications and a second supervisor."""

    def __init__(self):
        flags = getattr(Gio.ApplicationFlags, "DEFAULT_FLAGS", None) \
            or Gio.ApplicationFlags.FLAGS_NONE    # GLib < 2.74 has only FLAGS_NONE
        super().__init__(application_id=APP_ID, flags=flags)
        self.tray = None
        self._activations = 0

    def do_startup(self):
        Gtk.Application.do_startup(self)
        self.hold()                     # live in the top bar with no window
        self.tray = TowerTray(self)

    def do_activate(self):
        self._activations += 1
        if self._activations > 1 and self.tray is not None:
            self.tray.show_panel()


def main():
    # No session, no top bar. Say so in one line — the alternative is a GTK
    # "cannot open display" traceback, which tells a user nothing about what to
    # do instead (and there is something to do: the dashboard needs no session).
    if not Gtk.init_check()[0]:
        sys.stderr.write(
            "tower-tray: no graphical session — there is no top bar to put "
            "the radar in.\n"
            "  Every feature is in the terminal dashboard:  tower\n")
        raise SystemExit(1)
    app = TrayApp()
    # Ctrl-C / SIGTERM end the main loop cleanly instead of being swallowed
    # by it. The daemon is not ours to stop: it runs in its own session.
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, app.quit)
        except (AttributeError, TypeError):
            pass
    raise SystemExit(app.run([sys.argv[0]]))


if __name__ == "__main__":
    main()
