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

from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

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
# The radar's own tempo: the verify sweep takes 2.4s for a full turn, the clear
# pulse 2.38s, the lid-closed lamp 2.4s (src/Glyph.swift). So one 2.4s loop of
# 12 frames plays every one of them at its true speed.
LOOP_S = 2.4
FRAMES = 12
FRAME_MS = int(LOOP_S * 1000 / FRAMES)
HOLD_S = 0.6          # trust an optimistic toggle this long after a click

# Brand tones — docs/DESIGN.md. Amber = held (pending, self-clearing),
# red = unguarded (danger). Everything else takes the neutral, which is
# resolved from the panel's own theme so the mark reads on light and dark.
AMBER = (0xE6 / 255, 0xA9 / 255, 0x3C / 255)
RED = (0xE5 / 255, 0x48 / 255, 0x4D / 255)
GREEN = (0x30 / 255, 0xA1 / 255, 0x4E / 255)
BLUE = (0x3B / 255, 0x6F / 255, 0xB5 / 255)
DIM = (0.55, 0.55, 0.58)

# Model tier accents. Text only, never on the mark itself (DESIGN.md).
TIER_ACCENT = {"fable": (0xC9 / 255, 0xA2 / 255, 0x27 / 255),
               "opus": (0xB0 / 255, 0x34 / 255, 0x3C / 255),
               "sonnet": (0x3B / 255, 0x6F / 255, 0xB5 / 255),
               "haiku": (0xE8 / 255, 0x84 / 255, 0x2C / 255)}
TIER_RANK = {"haiku": 0, "sonnet": 1, "opus": 2, "fable": 3}

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
def read_state():
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
        if time.time() - s.get("ts", 0) < 5:
            return s
    except Exception:  # noqa: BLE001
        pass
    return None


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


def ensure_daemon():
    """Start the daemon if nothing fresh is on disk. Opening Tower arms the
    guard — the same promise the macOS app keeps by launching it."""
    if read_state() or not os.path.exists(DAEMON):
        return
    try:
        subprocess.Popen([sys.executable or "python3", DAEMON],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Derivations — mirrors of TowerModel (src/Model.swift) and the TUI's
# status_of()/usage_gate(). Presentation only; the daemon owns the truth.
# --------------------------------------------------------------------------- #
def guard_status(s):
    """(title, tone) for the overall guard. Net faults outrank everything —
    a red header must mean "stop and look" — and `degraded` deliberately does
    not, since a slow-but-reachable link still passes traffic."""
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
        return "Not routed", DIM
    if not g.get("enforce", True):
        return "Monitor only", BLUE
    if g.get("claude_allowed"):
        return "Protected", GREEN
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
    ka = (s or {}).get("keepawake") or {}
    if not ka.get("on"):
        return "none"
    return "clamshell" if ka.get("mode") == "clamshell" else "idle"


NEEDS_YOU_RANK = {"failed": 1, "waiting_input": 2, "asking": 3, "done": 4}
AGENT_PHRASE = {
    "working": "working", "pending_tool": "waiting on a tool",
    "waiting_input": "waiting for you", "asking": "has a question",
    "done": "done", "failed": "failed", "idle": "idle", "gone": "gone",
    "paused": "paused",
}


def sessions(s):
    return ((s or {}).get("agents") or {}).get("sessions") or []


def needs_you(s):
    """failed > waiting_input > asking > done, oldest first inside a rank."""
    rows = [x for x in sessions(s)
            if NEEDS_YOU_RANK.get(x.get("status")) and not x.get("dismissed")]
    return sorted(rows, key=lambda x: (NEEDS_YOU_RANK.get(x.get("status"), 9),
                                       x.get("status_since") or 0))


def working(s):
    rows = [x for x in sessions(s) if x.get("status") == "working"]
    return sorted(rows,
                  key=lambda x: -TIER_RANK.get(x.get("model_family") or "", -1))


def resting(s):
    return [x for x in sessions(s) if x.get("status") in ("idle", "gone")]


def _live(x):
    return (x.get("pid") and x.get("kind") != "infra"
            and x.get("status") != "gone")


def proxy_pinned_count(s):
    """Agents reaching the API *through* Tower's proxy right now, whatever the
    routing intent — they lose their connection until restarted if the guard
    stops. This is the number a quit warning has to quote."""
    return sum(1 for x in sessions(s) if _live(x) and x.get("guarded") is True)


def working_count(s):
    return sum(1 for x in sessions(s)
               if x.get("status") in ("working", "pending_tool") and _live(x))


def usage_gate(s):
    """When the guard isn't passing Claude, `/usage` is withheld — running it
    would itself be the off-country or unstable request. Returns the honest
    (headline, detail) saying whether it's the connection or the location, or
    None when usage should render normally. Never stale numbers."""
    plan = (s or {}).get("plan") or {}
    if plan.get("disabled"):
        return None
    g = (s or {}).get("guard") or {}
    if not (plan.get("gated") or g.get("claude_allowed") is False):
        return None
    target = cname(g.get("target_cc")) if g.get("target_cc") else "your country"
    if plan.get("gate_reason") == "net" or g.get("net_ok") is False:
        return ("Usage paused — connection unstable",
                "Can't reach Anthropic right now. Check your internet "
                "connection or VPN. Usage returns on its own once the link "
                "is stable.")
    return ("Usage paused — location not confirmed",
            f"You appear to be outside {target}. If you're on a VPN, set it "
            f"to {target}. Usage returns once your location is confirmed.")


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


def until(ts):
    if not ts:
        return ""
    s = ts - time.time()
    if s <= 30:
        return "now"
    if s < 5400:
        return f"in {int(s / 60)}m"
    if s < 129600:
        return f"in {int(s / 3600)}h"
    return f"in {int(s / 86400)}d"


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


def agent_line(sess):
    """<project> — <activity/result/phrase>, matched to the TUI's agent_row."""
    name = (sess.get("project_name")
            or os.path.basename(sess.get("cwd") or "") or "?")
    st = sess.get("status")
    result = sess.get("result")
    if st == "done" and result:
        what = f"done — {result}"
    else:
        what = sess.get("activity") or AGENT_PHRASE.get(st, st or "…")
    return name, what


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
# the popover uses. Colours come from the desktop theme so Tower reads right in
# light and dark; only amber/red/green are ours, because they *are* the signal.
# --------------------------------------------------------------------------- #
CSS = b"""
.tower-title      { font-size: 13px; font-weight: 600; }
.tower-row        { font-size: 13px; }
.tower-sub        { font-size: 11px; opacity: 0.65; }
.tower-section    { font-size: 11px; font-weight: 600; opacity: 0.6;
                    letter-spacing: 0.06em; }
.tower-count      { font-size: 11px; font-family: monospace; opacity: 0.75; }
.tower-good       { color: #30a14e; }
.tower-warn       { color: #e6a93c; }
.tower-bad        { color: #e5484d; }
.tower-dim        { opacity: 0.6; }
.tower-gate       { font-size: 12px; }
.tower-pad        { padding: 12px 16px; }
.tower-tier-fable  { color: #c9a227; font-size: 11px; font-weight: 600; }
.tower-tier-opus   { color: #b0343c; font-size: 11px; font-weight: 600; }
.tower-tier-sonnet { color: #3b6fb5; font-size: 11px; font-weight: 600; }
.tower-tier-haiku  { color: #e8842c; font-size: 11px; font-weight: 600; }
progressbar.tower-meter trough { min-height: 6px; }
progressbar.tower-meter progress { min-height: 6px; }
"""

TONE_CLASS = {GREEN: "tower-good", AMBER: "tower-warn", RED: "tower-bad",
              DIM: "tower-dim", BLUE: "tower-dim"}


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
        ctx = self.get_style_context()
        ok, col = ctx.lookup_color("theme_fg_color")
        color = (col.red, col.green, col.blue) if ok else (0.2, 0.2, 0.22)
        draw_radar(cr, self.size, self.state, self.phase, color,
                   self.awake, self.reduce)
        return False


class Spark(Gtk.DrawingArea):
    """7-day token sparkline — the same series the popover and TUI show."""

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
        ctx = self.get_style_context()
        ok, col = ctx.lookup_color("theme_selected_bg_color")
        rgb = (col.red, col.green, col.blue) if ok else BLUE
        for i, v in enumerate(vals):
            bh = max(1.0, (v / top) * (h - 2))
            x = i * (w / max(1, n)) + 1
            cr.rectangle(x, h - bh, bw, bh)
            cr.set_source_rgba(rgb[0], rgb[1], rgb[2],
                               0.35 + 0.55 * (v / top))
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
# Notifications — the one thing the macOS app has that no other front-end did.
#
# Same policy as src/Notifier.swift: fire on a transition INTO failed /
# waiting-for-you / asking, always; on "done" only if nobody has looked at the
# panel in the last minute (otherwise the person watching just saw it happen).
# Never on entering "working" — an agent doing its job is not news.
#
# Spoken straight to org.freedesktop.Notifications over GIO's D-Bus, so this
# adds no dependency: libnotify would be a package, and the bus is already
# there. One notification per session, replaced on each new transition, so a
# flapping agent cannot stack up a wall of popups.
# --------------------------------------------------------------------------- #
NOTIFY_STATUSES = {
    "failed": ("failed", 2),            # urgency 2 = critical: rank 1, and it
    "waiting_input": ("needs your approval", 1),   # is the only one that gets it
    "asking": ("has a question", 1),
    "done": ("is done", 1),
}
DONE_QUIET_S = 60


class Notifier:
    def __init__(self):
        self._last = {}                 # session_id -> status we announced
        self._ids = {}                  # session_id -> notification id to replace
        self._bus = None
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error:
            pass                        # no bus: run silent, never crash

    def sync(self, s, panel_seen_at):
        rows = sessions(s)
        live = set()
        for sess in rows:
            sid = sess.get("session_id")
            if not sid:
                continue
            live.add(sid)
            st = sess.get("status")
            if self._last.get(sid) == st:
                continue
            was_known = sid in self._last
            self._last[sid] = st
            if not was_known:
                # First sight of a session is not a transition. Announcing the
                # backlog on launch would be a wall of popups about nothing new.
                continue
            if st not in NOTIFY_STATUSES:
                continue
            if st == "done" and time.time() - panel_seen_at < DONE_QUIET_S:
                continue
            self._fire(sess, st)
        for sid in list(self._last):
            if sid not in live:
                self._last.pop(sid, None)
                self._ids.pop(sid, None)

    def _fire(self, sess, st):
        if self._bus is None:
            return
        phrase, urgency = NOTIFY_STATUSES[st]
        name, what = agent_line(sess)
        sid = sess.get("session_id")
        body = what if st != "done" else (sess.get("result") or "done")
        # A plain dict of variants: the format string below builds the a{sv},
        # and handing it a pre-built Variant makes GLib try to iterate it.
        hints = {
            "urgency": GLib.Variant("y", urgency),
            "category": GLib.Variant("s", "device"),
            # Lets the shell attribute (and collapse) these as Tower's.
            "desktop-entry": GLib.Variant("s", "tower-tray"),
        }
        args = GLib.Variant("(susssasa{sv}i)", (
            "Tower", self._ids.get(sid, 0), "tower",
            f"{name} {phrase}", body, [], hints, -1))
        self._bus.call(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications", "Notify",
            args, GLib.VariantType("(u)"), Gio.DBusCallFlags.NONE, 5000, None,
            self._got_id, sid)

    def _got_id(self, bus, res, sid):
        try:
            self._ids[sid] = bus.call_finish(res).unpack()[0]
        except GLib.Error:
            pass                        # no notification daemon; stay quiet


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
    def __init__(self, app):
        super().__init__(title="Tower")
        self.app = app
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
        texts.pack_start(self.h_title, False, False, 0)
        texts.pack_start(self.h_sub, False, False, 0)
        box.pack_start(texts, True, True, 0)
        self.route_switch = Gtk.Switch()
        self.route_switch.set_valign(Gtk.Align.CENTER)
        self.route_switch.set_tooltip_text(
            "Route Claude Code through the guard")
        self.route_switch.connect("notify::active", self._on_route)
        box.pack_start(self.route_switch, False, False, 0)
        return box

    def _on_route(self, sw, _p):
        if self._syncing:
            return
        want = sw.get_active()
        if want:
            self._hold_until = time.time() + HOLD_S
            send({"cmd": "route", "on": True})
            return
        # Turning the guard OFF is destructive: Claude goes back to a direct,
        # unguarded connection. Two confirmations, and the warning has to say
        # how many agents would immediately send unguarded requests.
        self._syncing = True
        sw.set_active(True)             # stay on until it's actually confirmed
        self._syncing = False
        self.app.danger(
            "Turn the guard off?",
            "Claude goes back to a DIRECT, unguarded connection.",
            "Turn it off",
            lambda: send({"cmd": "route", "on": False}))

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

    def _agent_row(self, sess, needs):
        name, what = agent_line(sess)
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        tone = ""
        st = sess.get("status")
        if st == "failed":
            tone = "tower-bad"
        elif st in ("waiting_input", "asking"):
            tone = "tower-warn"
        elif st == "done":
            tone = "tower-good"
        top.pack_start(_label(name, "tower-row " + tone), True, True, 0)
        fam = (sess.get("model_family") or "").lower()
        if fam in TIER_ACCENT:
            top.pack_start(_label(model_label(sess), "tower-tier-" + fam),
                           False, False, 0)
        row.pack_start(top, False, False, 0)
        sub = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sub.pack_start(_label(what, "tower-sub", wrap=True), True, True, 0)
        when = ago(sess.get("status_since") or sess.get("last_activity"))
        if when:
            sub.pack_start(_label(when, "tower-count"), False, False, 0)
        row.pack_start(sub, False, False, 0)
        if needs:
            sid = sess.get("session_id")
            acts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            focus = Gtk.Button(label="Focus")
            focus.set_tooltip_text(
                "Raise this agent's terminal tab (tmux only on Linux)")
            focus.connect("clicked",
                          lambda _b, i=sid: send({"cmd": "focus",
                                                  "session_id": i}))
            acts.pack_start(focus, False, False, 0)
            copy = Gtk.Button(label="Copy resume")
            copy.set_tooltip_text("Copy  claude --resume <id>  to the clipboard")
            copy.connect("clicked", lambda _b, i=sid: self._copy(
                f"claude --resume {i}"))
            acts.pack_start(copy, False, False, 0)
            dis = Gtk.Button(label="Dismiss")
            dis.connect("clicked",
                        lambda _b, i=sid: send({"cmd": "dismiss",
                                                "session_id": i}))
            acts.pack_start(dis, False, False, 0)
            row.pack_start(acts, False, False, 0)
        return row

    def _copy(self, text):
        cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        cb.set_text(text, -1)
        cb.store()

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
        self.ka_detail = _label("", "tower-sub", wrap=True)
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
        self.gate_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.gate_head = _label("", "tower-row tower-warn", wrap=True)
        self.gate_detail = _label("", "tower-gate tower-dim", wrap=True)
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
        term.connect("clicked", lambda _b: self.app.open_terminal())
        box.pack_start(term, False, False, 0)
        self.traffic = _label("", "tower-count")
        self.traffic.set_valign(Gtk.Align.CENTER)
        box.pack_start(self.traffic, True, True, 0)
        quit_btn = Gtk.Button(label="Quit Tower")
        quit_btn.get_style_context().add_class("destructive-action")
        quit_btn.connect("clicked", lambda _b: self.app.request_quit())
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

    def update(self, s, phase, reduce_motion):
        self.radar.state = radar_state(s)
        self.radar.awake = awake_glow(s)
        self.tick_radar(phase, reduce_motion)
        if s is None:
            self.h_title.set_text("Starting…")
            self.h_sub.set_text("waiting for the guard daemon")
            return

        g = s.get("guard") or {}
        title, tone = guard_status(s)
        self.h_title.set_text(title)
        ctx = self.h_title.get_style_context()
        for c in ("tower-good", "tower-warn", "tower-bad", "tower-dim"):
            ctx.remove_class(c)
        ctx.add_class(TONE_CLASS.get(tone, "tower-dim"))

        nwork, nneed = working_count(s), len(needs_you(s))
        bits = [f"target {cname(g.get('target_cc'))}"]
        if nwork:
            bits.append(f"{nwork} at work")
        if nneed:
            bits.append(f"{nneed} needs you")
        if g.get("pending"):
            bits.append("retrying — the guard is holding")
        self.h_sub.set_text(" · ".join(b for b in bits if b))

        self._syncing = True
        if time.time() > self._hold_until:
            self.route_switch.set_active(
                bool((s.get("routing") or {}).get("intended")))
        self._syncing = False

        self._update_net(s)
        self._update_agents(s)
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
                 "api_issue": "Anthropic API issue",
                 "checking": "Checking…"}
        self.net_status.set_text(words.get(st, st))
        ctx = self.net_status.get_style_context()
        for c in ("tower-good", "tower-warn", "tower-bad", "tower-dim"):
            ctx.remove_class(c)
        ctx.add_class("tower-good" if st == "online"
                      else "tower-dim" if st == "checking"
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

    def _update_agents(self, s):
        need = needs_you(s)
        work = working(s)
        rest = resting(s)
        summ = ((s.get("agents") or {}).get("summary") or {})
        head = "AGENTS"
        counts = []
        if work:
            counts.append(f"{len(work)} at work")
        if summ.get("done_today"):
            counts.append(f"{summ['done_today']} done today")
        if need:
            counts.append(f"{len(need)} needs you")
        if counts:
            head += " · " + " · ".join(counts)
        self.agents_head.set_text(head)

        # Rebuild only on a real change: every second would flicker and could
        # yank a button out from under a click.
        sig = tuple((x.get("session_id"), x.get("status"), x.get("activity"),
                     x.get("result"), x.get("model_family"))
                    for x in need + work) + (len(rest),)
        if sig == self._agent_sig:
            return
        self._agent_sig = sig
        for child in self.agents_list.get_children():
            self.agents_list.remove(child)
        for coll in ((s.get("agents") or {}).get("collisions") or [])[:3]:
            where = coll.get("path") or coll.get("git_root") or "the same repo"
            same_file = coll.get("kind") == "file"
            self.agents_list.pack_start(
                _label(("Two agents are editing the same file — " if same_file
                        else "Two agents share ") + os.path.basename(where),
                       "tower-row " + ("tower-bad" if same_file
                                       else "tower-warn"), wrap=True),
                False, False, 0)
        if need:
            self.agents_list.pack_start(_label("NEEDS YOU", "tower-section"),
                                        False, False, 0)
            for sess in need:
                self.agents_list.pack_start(self._agent_row(sess, True),
                                            False, False, 0)
        for sess in work:
            self.agents_list.pack_start(self._agent_row(sess, False),
                                        False, False, 0)
        if rest:
            self.agents_list.pack_start(
                _label(f"{len(rest)} resting", "tower-sub"), False, False, 0)
        if not (need or work or rest):
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
        ctx = self.loc_where.get_style_context()
        for c in ("tower-good", "tower-warn", "tower-bad", "tower-dim"):
            ctx.remove_class(c)
        ctx.add_class("tower-good" if loc.get("in_target")
                      else "tower-dim" if st == "CHECKING" else "tower-warn")
        detail = [x for x in (loc.get("ip"), loc.get("isp")) if x]
        if loc.get("error"):
            detail.append(str(loc["error"]))
        if st == "OK" and not loc.get("in_target"):
            detail.append(f"outside {cname(g.get('target_cc'))} — Claude is held")
        self.loc_detail.set_text(" · ".join(detail))
        self._syncing = True
        if time.time() > self._hold_until:
            cc = (g.get("target_cc") or "").upper()
            if cc and self.country.get_active_id() != cc:
                self.country.set_active_id(cc)
        self._syncing = False

    def _update_keepawake(self, s):
        ka = s.get("keepawake") or {}
        mode = (ka.get("mode") if ka.get("on") else "off") or "off"
        self._syncing = True
        btn = self.ka_buttons.get(mode)
        if btn is not None and not btn.get_active() \
                and time.time() > self._hold_until:
            btn.set_active(True)
        self._syncing = False
        self.ka_detail.set_text({
            "idle": "This machine stays awake while agents work.",
            "clamshell": "Long agents keep running with the lid closed "
                         "(a logind inhibitor — no password needed).",
        }.get(mode, "This machine may sleep — long agents can be interrupted."))

    def _update_plan(self, s):
        plan = s.get("plan") or {}
        u = s.get("usage") or {}
        gate = usage_gate(s)
        if gate:
            self.plan_note.set_text("paused — guard not passing")
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
            _reveal(self.meter_box, False)
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
                meter.set_fraction(p / 100.0)
                mctx = meter.get_style_context()
                for c in ("tower-good", "tower-warn", "tower-bad"):
                    mctx.remove_class(c)
                mctx.add_class("tower-bad" if p >= 90
                               else "tower-warn" if p >= 75 else "tower-good")

        sess = u.get("session") or {}
        wk = u.get("week") or {}
        pace = u.get("pace") or {}
        self.est_session.set_text(
            f"session  {fmt_tok(sess.get('tokens'))} tokens · "
            f"{fmt_cost(sess.get('cost'))} · {sess.get('msgs', 0)} msgs")
        self.est_week.set_text(
            f"week  {fmt_tok(wk.get('tokens'))} tokens · "
            f"{fmt_cost(wk.get('cost'))} · "
            f"~{fmt_tok(pace.get('projected_week_tokens'))} projected")
        bm = u.get("byModel") or []
        models = " · ".join(f"{_model_short(m.get('model'))} "
                            f"{fmt_tok(m.get('tokens'))}" for m in bm[:4])
        self.est_models.set_text(models)
        _reveal(self.est_models, bool(models))
        vals = [d.get("tokens", 0) for d in (u.get("series") or [])]
        # An all-zero week is not a trend — a flat line of 1px bars would read
        # as data. Show nothing until there is something.
        self.spark.vals = vals if any(vals) else []
        _reveal(self.spark, bool(self.spark.vals))
        self.spark.queue_draw()


# --------------------------------------------------------------------------- #
# The tray — the top-bar item, its menu, and the one-second heartbeat.
#
# The menu carries the live status and every control the popover has, because
# on a StatusNotifierItem host a left-click *is* the menu: there is no separate
# "activate" a client can rely on, so the menu is the front door and the panel
# opens from it.
# --------------------------------------------------------------------------- #
class TowerTray:
    def __init__(self):
        self.icons = IconCache()
        self.notifier = Notifier()
        self.panel_seen_at = 0.0
        self.t0 = time.time()
        self.frame = 0
        self.state = None
        self.icon_key = None
        self.agent_sig = None
        self.hold_until = 0.0
        self._syncing = False

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.panel = Panel(self)
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

        GLib.timeout_add(POLL_MS, self._tick_state)
        GLib.timeout_add(FRAME_MS, self._tick_frame)
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

        quit_item = Gtk.MenuItem(label="Quit Tower")
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
        self.danger("Turn the guard off?",
                    "Claude goes back to a DIRECT, unguarded connection.",
                    "Turn it off",
                    lambda: send({"cmd": "route", "on": False}))

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
        self.panel.show_all()
        self.panel.present()
        self.panel.update(self.state, time.time() - self.t0,
                          self.reduce_motion())

    def open_terminal(self):
        """Open the curses dashboard in whatever terminal this desktop has."""
        tui = "/usr/lib/tower/tower-tui.py"
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "tower-tui.py")
        if os.path.exists(local):
            tui = local
        cmd = ["tower"] if _which("tower") else [sys.executable or "python3", tui]
        for term, arg in (("gnome-terminal", "--"), ("kgx", "--"),
                          ("konsole", "-e"), ("xfce4-terminal", "-x"),
                          ("tilix", "-e"), ("alacritty", "-e"),
                          ("kitty", ""), ("xterm", "-e")):
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

    def request_quit(self):
        """Quitting is destructive twice over: it removes the guard, and every
        chat pinned to the proxy loses its connection until restarted. Both
        numbers go in the warning."""
        s = self.state or {}
        pinned = proxy_pinned_count(s)
        extra = ""
        if pinned:
            extra = (f"\n\n{pinned} chat{'s' if pinned != 1 else ''} "
                     f"{'are' if pinned != 1 else 'is'} pinned to the guard's "
                     f"proxy and will lose the connection until restarted.")
        self.danger(
            "Quit Tower?",
            "This stops the guard. Claude goes back to a DIRECT, unguarded "
            "connection." + extra,
            "Quit Tower", self._do_quit)

    def _do_quit(self):
        send({"cmd": "quit"})
        # Give the daemon its moment to un-route settings.json before we go.
        GLib.timeout_add(1200, Gtk.main_quit)

    # ---- the two-stage danger gate --------------------------------------- #
    def danger(self, title, message, confirm, perform):
        """Anything that lets Claude reach the API without the guard is warned
        hard and confirmed twice, and the warning always says how many agents
        are working right now — they would start sending unguarded requests the
        moment this takes effect."""
        n = working_count(self.state or {})
        if n:
            message += (f"\n\n{n} agent{'s' if n != 1 else ''} "
                        f"{'are' if n != 1 else 'is'} working right now.")
        if not self._ask(title, message, confirm):
            return
        if not self._ask("Are you sure?",
                         "Last check — this takes effect immediately and the "
                         "guard stops protecting anything.",
                         confirm):
            return
        perform()

    def _ask(self, title, message, confirm):
        dlg = Gtk.MessageDialog(
            transient_for=self.panel if self.panel.get_visible() else None,
            modal=True, message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE, text=title)
        dlg.format_secondary_text(message)
        dlg.add_button("Keep the guard on", Gtk.ResponseType.CANCEL)
        btn = dlg.add_button(confirm, Gtk.ResponseType.OK)
        btn.get_style_context().add_class("destructive-action")
        dlg.set_default_response(Gtk.ResponseType.CANCEL)
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
    def reduce_motion(self):
        settings = Gtk.Settings.get_default()
        if settings is None:
            return False
        return not settings.get_property("gtk-enable-animations")

    def animating(self, s):
        """Motion = state change (docs/DESIGN.md). A hold or a verify sweep has
        something to say; a clear guard with nothing running is completely
        still, and Reduce Motion is always still."""
        if self.reduce_motion() or s is None:
            return False
        st = radar_state(s)
        if st in ("verify", "holdNet", "holdGeo"):
            return True
        if awake_glow(s) == "clamshell":
            return True
        return st == "clear" and working_count(s) > 0

    def _tick_state(self):
        ensure_daemon()
        self.state = read_state()
        s = self.state
        title, tone = (guard_status(s) if s else ("Starting…", DIM))
        self.status_item.set_label("Tower — " + title)

        g = (s or {}).get("guard") or {}
        loc = (s or {}).get("location") or {}
        detail = []
        if s:
            where = loc.get("country_name") or cname(loc.get("country_cc"))
            if where and where != "—":
                detail.append(where)
            detail.append(f"target {cname(g.get('target_cc'))}")
            n = working_count(s)
            if n:
                detail.append(f"{n} at work")
            nn = len(needs_you(s))
            if nn:
                detail.append(f"{nn} needs you")
        self.detail_item.set_label(" · ".join(detail) or "waiting for the daemon")

        self._syncing = True
        if time.time() > self.hold_until:
            self.route_item.set_active(
                bool(((s or {}).get("routing") or {}).get("intended")))
            mode = awake_glow(s)
            mode = "off" if mode == "none" else mode
            it = self.ka_items.get(mode)
            if it is not None and not it.get_active():
                it.set_active(True)
            cc = (g.get("target_cc") or "").upper()
            it = self.cc_items.get(cc)
            if it is not None and not it.get_active():
                it.set_active(True)
        self._syncing = False

        self._sync_agents_menu(s)
        if self.panel.get_visible():
            # An open panel counts as looking: a "done" popup while you are
            # watching the row say done is noise.
            self.panel_seen_at = time.time()
            self.panel.update(s, time.time() - self.t0, self.reduce_motion())
        self.notifier.sync(s, self.panel_seen_at)
        self._apply_icon()
        return True

    def _sync_agents_menu(self, s):
        rows = needs_you(s) + working(s)
        sig = tuple((x.get("session_id"), x.get("status"), x.get("activity"))
                    for x in rows)
        n = working_count(s or {})
        nn = len(needs_you(s or {}))
        label = "No agents running"
        if rows:
            label = f"{n} at work" + (f" · {nn} needs you" if nn else "")
        self.agents_item.set_label(label)
        self.agents_item.set_sensitive(bool(rows))
        if sig == self.agent_sig:
            return
        self.agent_sig = sig
        for child in self.agents_menu.get_children():
            self.agents_menu.remove(child)
        for sess in rows:
            name, what = agent_line(sess)
            it = Gtk.MenuItem(label=f"{name} — {what}")
            sid = sess.get("session_id")
            it.connect("activate",
                       lambda _i, i=sid: send({"cmd": "focus",
                                               "session_id": i}))
            self.agents_menu.append(it)
        self.agents_menu.show_all()

    def _tick_frame(self):
        if self.animating(self.state):
            self.frame = (self.frame + 1) % FRAMES
            self._apply_icon()
        if self.panel.get_visible():
            self.panel.tick_radar(time.time() - self.t0, self.reduce_motion())
        return True

    def _apply_icon(self):
        s = self.state
        st = radar_state(s)
        aw = awake_glow(s)
        frame = self.frame if self.animating(s) else "still"
        key = (st, aw, frame)
        if key == self.icon_key:
            return              # nothing new to say; don't touch the bus
        self.icon_key = key
        self.icons.ensure(st, aw)
        self.ind.set_icon_full(self.icons.name(st, aw, frame),
                               f"Tower — {guard_status(s)[0] if s else 'starting'}")


def _which(exe):
    for d in (os.environ.get("PATH") or "").split(os.pathsep):
        p = os.path.join(d, exe)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


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
    # A GTK app with no window open at start still needs the main loop; the
    # indicator lives in the top bar until someone opens the panel.
    TowerTray()
    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
