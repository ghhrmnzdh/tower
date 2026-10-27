#!/usr/bin/env python3
"""
tower-tui — terminal front-end for the Tower daemon.

A read-only-looking dashboard that is actually a full controller: it renders
~/.tower/state.json and drives the guard by dropping command files into
~/.tower/cmd/ (exactly like the menubar app). stdlib only (curses).

Small and medium screens show four things — GUARD, AGENTS, PLAN, NETWORK —
in a monochrome grammar with color only where it means something (green
protected / healthy dot, amber held / warn, red failed / unguarded, and each
model's mark in its tier color). Size classes are supersets: tiny (one status
card) → compact (one column) → regular (two columns) → tall / wide / xwide,
dense dashboards that use the room — latency charts, the request log, usage,
where the limit goes, system, timeline — balanced across 2–4 columns. Every
panel is sized to its content: rows go to panels by priority, a panel that
doesn't earn room collapses to a one-line summary, nothing stretches to fill.
The deeper usage numbers are also one key away (`u`).

If the daemon isn't running it starts it (single-instance, so this is safe),
then attaches. Quitting the TUI leaves the guard running; press Shift-Q to stop
the guard entirely (removes routing, restores Claude to a direct connection).

Run:  python3 tower-tui.py
"""

import functools
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
import types
import unicodedata
import uuid

# curses isn't in the Windows stdlib. _wincurses is a drop-in shim implementing
# the exact curses subset this TUI uses, over ANSI/VT + msvcrt (dep-free). On
# macOS/Linux the real curses is used, unchanged. Anything beyond that subset
# (has_colors, COLORS, …) is reached through getattr with a safe default.
if os.name == "nt":
    import _wincurses as curses
else:
    import curses

# Platform noun for user-facing copy — "Mac" on macOS (unchanged), "PC" on
# Windows, "machine" on Linux (it may be a laptop, a desktop or a server, and
# only "machine" reads right in all three: "Keep the machine awake", "Claude
# agents on this machine"). Keeps the macOS wording byte-identical.
DEVICE = ("PC" if os.name == "nt"
          else "Mac" if sys.platform == "darwin" else "machine")

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(HOME, ".tower")
STATE_FILE = os.path.join(CONFIG_DIR, "state.json")
CMD_DIR = os.path.join(CONFIG_DIR, "cmd")
SEEN_FLAG = os.path.join(CONFIG_DIR, ".tui_seen")
DAEMON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "towerd.py")
SELF = os.path.abspath(__file__)
TICK_MS = 80          # input/redraw tick — snappy without burning CPU
HOLD_S = 0.5          # after an action, trust the optimistic view this long

CNAME = {
    "US": "United States", "CA": "Canada", "GB": "United Kingdom",
    "DE": "Germany", "FR": "France", "AU": "Australia", "JP": "Japan",
    "IN": "India", "SG": "Singapore", "NL": "Netherlands", "IE": "Ireland",
    "ES": "Spain", "IT": "Italy", "SE": "Sweden", "CH": "Switzerland",
    "BR": "Brazil", "MX": "Mexico", "KR": "South Korea", "AE": "UAE",
    "NO": "Norway", "FI": "Finland", "DK": "Denmark", "BE": "Belgium",
    "AT": "Austria", "PL": "Poland", "PT": "Portugal", "CZ": "Czechia",
    "NZ": "New Zealand", "ZA": "South Africa", "TR": "Türkiye", "IL": "Israel",
    "AR": "Argentina", "CL": "Chile", "HK": "Hong Kong", "TW": "Taiwan",
    "TH": "Thailand", "MY": "Malaysia", "ID": "Indonesia", "PH": "Philippines",
    "SA": "Saudi Arabia", "EG": "Egypt", "NG": "Nigeria", "UA": "Ukraine",
}
# (cc, name) ordered by country name — used by the picker modal
COUNTRY_LIST = sorted(((cc, n) for cc, n in CNAME.items()), key=lambda x: x[1])


def cname(cc):
    cc = (cc or "").upper()
    return CNAME.get(cc, cc or "—")


# --------------------------------------------------------------------------- #
# Terminal capabilities — probed once. Everything degrades instead of breaking:
# no color → attributes only (NO_COLOR honored); no UTF-8 → an ASCII twin of
# every glyph at the same cell width, so layouts don't move (TOWER_ASCII=1
# forces it); TOWER_REDUCE_MOTION=1 → every animation holds a still frame and
# the screen stops repainting on the animation tick.
# --------------------------------------------------------------------------- #
def _probe_unicode():
    if os.environ.get("TOWER_ASCII"):
        return False
    enc = getattr(sys.stdout, "encoding", None) or ""
    if not enc:
        try:
            import locale
            enc = locale.getpreferredencoding(False) or ""
        except Exception:
            enc = ""
    return "utf" in enc.lower()


UNICODE = _probe_unicode()
MOTION = not os.environ.get("TOWER_REDUCE_MOTION")
ELL = "…" if UNICODE else "."

_ASCII = str.maketrans({
    "╭": "+", "╮": "+", "╰": "+", "╯": "+", "─": "-", "│": "|", "├": "+",
    "└": "`", "╶": "-", "╴": "-",
    "█": "#", "▉": "=", "▊": "=", "▋": "=", "▌": "=", "▍": "=", "▎": "=",
    "▏": "=", "▓": "%", "▒": "+", "░": ".",
    "▁": "_", "▂": "_", "▃": ".", "▄": "-", "▅": "-", "▆": "=", "▇": "#",
    "●": "*", "○": "o", "◐": "o", "◉": "@", "◌": "o", "◎": "O", "⊘": "x",
    "✓": "v", "✔": "v", "✗": "x", "⚠": "!", "▲": "^", "⏸": "=", "·": ".",
    "—": "-", "–": "-", "…": ".", "↓": "v", "↑": "^", "→": ">", "↻": "@",
    "✦": "*", "⏎": "<", "›": ">", "↳": ">", "◆": "*", "∙": ".", "∘": "o",
    "‘": "'", "’": "'", "“": '"', "”": '"', "×": "x", "≥": ">", "≤": "<",
    "━": "=", "╸": "=", "≈": "~", "◴": "|", "◷": "/", "◶": "-", "◵": "\\",
})


def U(uni, asc):
    """A glyph, or its ASCII twin when the terminal can't take UTF-8."""
    return uni if UNICODE else asc


# --------------------------------------------------------------------------- #
# IPC
# --------------------------------------------------------------------------- #
_state_cache = [None, None]     # [(mtime_ns, size), parsed state]


def read_state():
    """state.json, re-parsed only when the daemon has rewritten it — the 80ms
    tick then costs one stat, while a hook event still shows up next tick."""
    try:
        st = os.stat(STATE_FILE)
        key = (st.st_mtime_ns, st.st_size)
        if key != _state_cache[0]:
            with open(STATE_FILE) as f:
                _state_cache[1] = json.load(f)
            _state_cache[0] = key
        s = _state_cache[1]
        if s and time.time() - s.get("ts", 0) < 5:
            return s
    except Exception:
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
    if read_state():
        return
    if not os.path.exists(DAEMON):
        return
    py = sys.executable or ("python" if os.name == "nt" else "python3")
    try:
        if os.name == "nt":
            # No setsid on Windows; detach so the daemon outlives this TUI and
            # gets no console window of its own.
            flags = (subprocess.CREATE_NEW_PROCESS_GROUP
                     | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                     | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
            subprocess.Popen([py, DAEMON],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             creationflags=flags)
        else:
            subprocess.Popen([py, DAEMON],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             start_new_session=True)
    except OSError:
        pass


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
    return f"${c:.0f}" if c >= 100 else f"${c:.2f}"


def fmt_kcost(c):
    """A cost in ≤5 cells, for chart labels: $5.6K · $641 · $25 · $2.5."""
    c = c or 0
    if c >= 1000:
        return f"${c / 1000:.1f}K"
    if c >= 10:
        return f"${c:.0f}"
    return f"${c:.1f}"


def fmt_ms(v):
    return f"{v:.0f}ms" if isinstance(v, (int, float)) else "—"


def model_name(mid):
    s = (mid or "").lower()
    for key, name in (("opus", "Opus"), ("sonnet", "Sonnet"),
                      ("haiku", "Haiku"), ("fable", "Fable")):
        if key in s:
            return name
    return "Other" if mid in ("unknown", "", None) else mid


def model_label(sess):
    """Model + effort as the app shows it: "Opus 5.5 · High". Version is parsed
    from the model id (numeric runs, dropping a yyyymmdd date suffix); effort is
    the daemon's compact label. Effort omitted when unknown."""
    base = model_name(sess.get("model") or sess.get("model_family"))
    mid = (sess.get("model") or "").lower().split("[", 1)[0]   # drop "[1m]" etc.
    nums, cur = [], ""
    for ch in mid + " ":
        if ch.isdigit():
            cur += ch
        else:
            if cur and len(cur) < 6:     # skip 6+ digit runs (date suffixes)
                nums.append(cur)
            cur = ""
    label = f"{base} {'.'.join(nums)}" if nums else base
    ctx = sess.get("context")
    if ctx:
        label += f" · {ctx}"
    eff = sess.get("effort")
    return f"{label} · {str(eff).strip().capitalize()}" if eff else label


def ago(since):
    if not isinstance(since, (int, float)) or not since:
        return ""
    s = max(0, time.time() - since)
    if s < 90:
        return f"{int(s)}s"
    if s < 5400:
        return f"{int(s / 60)}m"
    if s < 129600:
        return f"{s / 3600:.1f}h"
    return f"{int(s / 86400)}d"


def until(at):
    """Seconds until `at`, in the unit a person would say it in — exactly the
    app's resetPhrase: never short by a unit. "now" · "in 42m" (minutes rounded
    UP) · "in 2h 14m" · "in 37h 5m" (under 48h: hours + minutes) · "in 3d 4h"."""
    if not isinstance(at, (int, float)) or not at:
        return ""
    secs = at - time.time()
    if secs <= 30:
        return "now"
    m = int(-(-secs // 60))              # whole minutes, never short
    if m < 60:
        return f"in {m}m"
    h = m // 60
    if h < 48:
        return f"in {h}h" if m % 60 == 0 else f"in {h}h {m % 60}m"
    d, rh = h // 24, h % 24
    return f"in {d}d" if rh == 0 else f"in {d}d {rh}h"


def reset_text(node):
    """A reset stamp shown relative, with no timezone. Falls back to the raw
    stamp minus its '(timezone)' tail if there's no parsed epoch."""
    rel = until(node.get("resets_at"))
    if rel:
        return rel
    raw = node.get("resets") or ""
    return raw.split("(", 1)[0].strip()




def meter(frac, width):
    """A slim meter split into (fill, track): a ━ fill, half-cell precise (╸),
    over a ─ track the caller draws in the structure color. Anything above
    zero shows at least a half cell, so 1% never reads as empty."""
    frac = max(0.0, min(1.0, frac or 0.0))
    width = max(0, int(width))
    total = frac * width
    full = int(total)
    s = "━" * full
    if full < width and (total - full >= 0.5 or (full == 0 and frac > 0)):
        s += "╸"
    s = s[:width]
    return s, "─" * (width - len(s))


AGENT_PHRASE = {
    "working": "working", "pending_tool": "waiting on a tool",
    "waiting_input": "waiting for you", "asking": "has a question",
    "done": "done", "failed": "failed", "idle": "idle", "gone": "gone",
    "paused": "paused",
}
# What actually needs the user (counted as "need you") vs. "your turn" — an
# agent that finished or is waiting for its next prompt: listed, but quieter,
# and never part of the needs-you number.
NEED = ("failed", "pending_tool", "asking")
TURN = ("done", "waiting_input")


def _dur(secs):
    s = int(max(0, secs))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m {s % 60:02d}s"
    return f"{s // 3600}h {(s % 3600) // 60:02d}m"


def subagent_lines(sess, limit=3):
    """The subagent tree under an agent row: running first (fan-out order), then
    the ones that came back, newest first. -> [(branch, node, text, right, live)]."""
    subs = [x for x in (sess.get("subagents") or []) if isinstance(x, dict)]
    run = sorted((x for x in subs if x.get("status") == "working"),
                 key=lambda x: x.get("started") or x.get("since") or 0)
    back = sorted((x for x in subs if x.get("status") != "working"),
                  key=lambda x: x.get("since") or 0, reverse=True)
    subs = run + back
    shown, rest = subs[:limit], subs[limit:]
    now = time.time()
    out = []
    for i, x in enumerate(shown):
        live = x.get("status") == "working"
        last = i == len(shown) - 1 and not rest
        what = x.get("desc") or (x.get("activity") if live else x.get("result")) \
            or ("working…" if live else "done")
        if live and x.get("desc") and x.get("activity"):
            what += f" · {x['activity']}"
        t0 = x.get("started") or x.get("since") or now
        t1 = now if live else (x.get("since") or t0)
        out.append(("└─" if last else "├─", "●" if live else "✓",
                    f"{x.get('type') or 'subagent'}  {what}",
                    _dur(t1 - t0) if live or t1 - t0 >= 1 else "", live))
    if rest:
        nrun = sum(1 for x in rest if x.get("status") == "working")
        out.append(("└─", " ", f"+{len(rest)} more"
                    + (f" · {nrun} running" if nrun else ""), "", False))
    return out


SPARK = "▁▂▃▄▅▆▇█"


def sparkline(vals):
    m = max(vals) if vals else 0
    if m <= 0:
        return "▁" * len(vals)
    return "".join(SPARK[min(len(SPARK) - 1, int((v / m) * (len(SPARK) - 1)))]
                   for v in vals)


# --------------------------------------------------------------------------- #
# Text — display width, clipping, sanitizing. Terminal cells, not code points:
# a CJK/emoji char takes two, a combining mark none, so a panel border never
# gets pushed out by an agent's activity line.
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=4096)
def _cw(c):
    if c < "̀":
        return 1
    if unicodedata.category(c) in ("Mn", "Me", "Cf"):
        return 0
    return 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1


def tw(t):
    """Display width of t in terminal cells."""
    return len(t) if t.isascii() else sum(_cw(c) for c in t)


def clean(t):
    """Text as it will hit the screen: one line, no control characters, and
    folded to ASCII when the terminal can't take UTF-8."""
    t = str(t)
    if not t.isprintable():
        t = "".join(c if c.isprintable() else " " for c in t)
    if not UNICODE and not t.isascii():
        t = t.translate(_ASCII).encode("ascii", "replace").decode("ascii")
    return t


def clip(t, n, ell=True):
    """t cut to n cells; a cut line ends in … so truncation never reads as data."""
    if n <= 0:
        return ""
    if tw(t) <= n:
        return t
    keep = n - 1 if ell else n
    out, used = [], 0
    for c in t:
        cw = _cw(c)
        if used + cw > keep:
            break
        out.append(c)
        used += cw
    return "".join(out) + (ELL if ell else "")


def pad(t, n):
    """t clipped and space-padded to exactly n cells."""
    t = clip(clean(t), n)
    return t + " " * max(0, n - tw(t))


# --------------------------------------------------------------------------- #
# Colors — monochrome. Text is the terminal's own foreground and three grays
# (labels/meta, charts, structure); bold carries emphasis. Color is reserved
# for meaning and nothing else: amber = held / warn, red = failed / unguarded,
# green = the small "on / healthy" dot. No accent hue anywhere. On 256-color
# terminals the tones are tuned to the app's (amber #E6A93C, red #E5484D) and
# read on light and dark backgrounds alike; 8/16-color terminals get the
# nearest basics (grays via A_DIM); no color at all falls back to bold/dim.
# --------------------------------------------------------------------------- #
C_TITLE = 1     # primary text — values (bold), names, row labels
C_GOOD = 2      # green — ONLY the small on/healthy ● dot
C_WARN = 3      # amber — held / warn
C_DIM = 4       # secondary text — meta, reasons, panel titles
C_MUTE = 5      # charts — sparklines
C_BAD = 6       # red — failure / unguarded / danger
C_LINE = 7      # structure — borders, meter tracks, tree branches
# The model tiers — "the mark is the model": only the glyph wears these, the
# name beside it stays white. Rosso, steel, crayon, gold (the app's tones).
C_OPUS, C_SONNET, C_HAIKU, C_FABLE = 8, 9, 10, 11
COLOR = True
_PAIR_ATTR = {}  # extra attributes folded into a pair (dim on 8-color, etc.)
B = curses.A_BOLD


def init_colors():
    global COLOR
    has = getattr(curses, "has_colors", None)
    if os.environ.get("NO_COLOR") or (has is not None and not has()):
        COLOR = False
    else:
        try:
            curses.start_color()
        except curses.error:
            COLOR = False
    if not COLOR:
        _PAIR_ATTR.update({C_DIM: curses.A_DIM, C_LINE: curses.A_DIM,
                           C_MUTE: curses.A_DIM, C_WARN: B, C_BAD: B})
        return
    fg = -1
    try:
        curses.use_default_colors()
    except curses.error:
        fg = curses.COLOR_WHITE
    bg = -1 if fg == -1 else curses.COLOR_BLACK
    n = getattr(curses, "COLORS", 8)
    if n >= 256:
        pal = {C_TITLE: fg, C_GOOD: 71, C_WARN: 179, C_DIM: 246,
               C_MUTE: 243, C_BAD: 167, C_LINE: 239,
               C_OPUS: 131, C_SONNET: 67, C_HAIKU: 172, C_FABLE: 136}
    elif n >= 16:
        pal = {C_TITLE: fg, C_GOOD: curses.COLOR_GREEN,
               C_WARN: curses.COLOR_YELLOW, C_DIM: 8, C_MUTE: 8,
               C_BAD: curses.COLOR_RED, C_LINE: 8}
    else:                                 # 8 colors: grays are dimmed white
        white = curses.COLOR_WHITE
        pal = {C_TITLE: fg, C_GOOD: curses.COLOR_GREEN,
               C_WARN: curses.COLOR_YELLOW, C_DIM: white, C_MUTE: white,
               C_BAD: curses.COLOR_RED, C_LINE: white}
        _PAIR_ATTR.update({C_DIM: curses.A_DIM, C_MUTE: curses.A_DIM,
                           C_LINE: curses.A_DIM})
    if n < 256:                           # tiers: the nearest basic hue
        pal.update({C_OPUS: curses.COLOR_RED, C_SONNET: curses.COLOR_BLUE,
                    C_HAIKU: curses.COLOR_YELLOW, C_FABLE: curses.COLOR_YELLOW})
    for pid, col in pal.items():
        try:
            curses.init_pair(pid, col, bg)
        except (curses.error, ValueError):
            curses.init_pair(pid, curses.COLOR_WHITE, bg)


def cp(n):
    if not COLOR:
        return _PAIR_ATTR.get(n, 0)
    return curses.color_pair(n) | _PAIR_ATTR.get(n, 0)


# --------------------------------------------------------------------------- #
# Mouse — a hitbox registry rebuilt on every composed frame. Each entry is
# (y, x1, x2, action); a click looks up its row, nothing tracks motion, so the
# idle loop stays as cheap as before. Actions are strings ("route", "menu", …)
# or ("focus", session_id) tuples, dispatched by do_click().
# --------------------------------------------------------------------------- #
MOUSE_B1 = curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED
MOUSE_WHEEL_UP = curses.BUTTON4_PRESSED
MOUSE_WHEEL_DOWN = getattr(curses, "BUTTON5_PRESSED", 0x200000)
# Dashboard single-key shortcuts that map straight onto a do_click() action —
# the toggles/pickers documented in HELP. ($/k/u/? run their own modal/cmd and
# are handled inline in run().)
KEY_ACTIONS = {ord("r"): "route", ord("e"): "enforce", ord("a"): "scope",
               ord("c"): "country", ord("p"): "country", ord("w"): "keepawake",
               ord("d"): "desktop"}
HITBOXES = []


def hit_at(my, mx):
    for y, x1, x2, action in HITBOXES:
        if my == y and x1 <= mx <= x2:
            return action
    return None


# --------------------------------------------------------------------------- #
# Guard verdict
# --------------------------------------------------------------------------- #
def status_of(s):
    """Return (label, color) for the overall guard status."""
    # Net faults outrank everything — a red verdict should mean "stop and
    # look", and `degraded` deliberately does NOT override (NETWORK shows it).
    net = (s.get("net") or {}).get("status")
    if net == "offline":
        return "Internet down", C_BAD
    if net == "captive":
        return "Wi-Fi login required", C_BAD
    if net == "api_issue":
        return "Anthropic API issue", C_BAD
    routed = (s.get("routing") or {}).get("installed")
    g = s.get("guard") or {}
    loc = s.get("location") or {}
    if not routed:
        return "Not routed", C_BAD           # direct, unguarded: danger
    if not g.get("enforce", True):
        return "Monitor only", C_WARN
    # Fail-closed: the daemon says whether a Claude request is allowed right now.
    if g.get("claude_allowed"):
        return "Protected", C_GOOD
    if g.get("net_ok") is False:
        return "Blocking — connection unstable", C_WARN
    if loc.get("status") != "OK":
        return "Blocking — confirming location…", C_WARN
    return "Blocking Claude", C_WARN


def radar_state(s):
    """The guard distilled to the app's five radar looks (Model.radarState)."""
    routed = (s.get("routing") or {}).get("installed")
    g = s.get("guard") or {}
    net = (s.get("net") or {}).get("status")
    if not routed:
        return "off"
    if not g.get("enforce", True) or g.get("claude_allowed"):
        return "holdNet" if net in ("offline", "captive", "api_issue") else "clear"
    if g.get("net_ok") is False:
        return "holdNet"
    if (s.get("location") or {}).get("status") != "OK":
        return "verify"
    return "holdGeo"


# The radar, in one cell: clear ◉ is still (the quiet state is completely
# still); verify sweeps; the holds are amber rings; off is a red slashed ring.
RADAR = {
    "clear": (U("◉", "@"), C_GOOD),
    "verify": (U("◴◷◶◵", "|/-\\"), C_TITLE),
    "holdNet": (U("◌", "o"), C_WARN),
    "holdGeo": (U("◎", "O"), C_WARN),
    "off": (U("⊘", "x"), C_BAD),
}
# The model marks, alive while their agent works — each in its own way.
MODEL_SPIN = {
    "opus": U("◐◓◑◒", "|/-\\"),          # orbiting
    "sonnet": U("◜◝◞◟", "|/-\\"),        # turning
    "haiku": U("∙∘○∘", ".oOo"),          # breathing
    "fable": U("⠁⠂⠄⡀⢀⠠⠐⠈", "|/-\\"),    # winding
}
SPIN_OTHER = U("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏", "|/-\\")


def explain(V):
    """One honest sentence under the verdict: what the guard is doing and why."""
    t, lab = V.target, V.label
    if V.stale:
        return ("No fresh state from the guard daemon for a few seconds — it "
                "may be restarting.")
    return {
        "Internet down": "No internet. Claude requests are held and resume on "
                         "their own once you're back online.",
        "Wi-Fi login required": "This network wants a captive-portal login — "
                                "open a browser. Claude is held until then.",
        "Anthropic API issue": "Internet is fine, but api.anthropic.com isn't "
                               "answering. Claude is held and retries on its own.",
        "Not routed": "Claude Code connects DIRECTLY — no country guard. "
                      "Press r to route it through Tower.",
        "Monitor only": "Routed through Tower, but off-country requests are "
                        "NOT blocked. Press e to enforce.",
        "Protected": f"Claude passes — confirmed in {t} on a stable path to "
                     "Anthropic.",
        "Blocking — connection unstable": "No trustworthy path to Anthropic — "
                                          "Claude is held (pending, not failed) "
                                          "and resumes on its own.",
        "Blocking — confirming location…": f"Holding Claude until your location "
                                           f"is confirmed in {t}.",
        "Blocking Claude": f"You appear to be outside {t} — Claude is held "
                           "until you're back (or your VPN is).",
    }.get(lab, "")


def usage_gate(s):
    """When the guard isn't passing Claude, `/usage` is withheld (running it
    would itself be an off-country / unstable request). Return a (headline,
    detail) explaining whether it's the connection or the location/VPN — or
    None when usage should render normally."""
    plan = s.get("plan") or {}
    if plan.get("disabled"):
        return None
    g = s.get("guard") or {}
    if not (plan.get("gated") or g.get("claude_allowed") is False):
        return None
    tc = g.get("target_cc")
    target = cname(tc) if tc else "your country"
    net_fault = plan.get("gate_reason") == "net" or g.get("net_ok") is False
    if net_fault:
        return ("Usage paused — connection unstable",
                "Can't reach Anthropic right now. Check your internet "
                "connection or VPN. Usage returns on its own once the link is "
                "stable.")
    return ("Usage paused — location not confirmed",
            f"You appear to be outside {target}. If you're on a VPN, set it to "
            f"{target}. Usage returns once your location is confirmed.")


def keepawake_line(kmode, ka):
    """The keep-awake consequence line, from the daemon's live policy — it holds
    only while agents work, so an armed mode says what it's doing right now."""
    if kmode == "off":
        return f"{DEVICE} may sleep — long agents can be interrupted"
    reason = ka.get("reason")
    if reason == "standby":
        return f"{DEVICE} sleeps normally until an agent works"
    if reason == "grace":
        m = max(1, ((ka.get("grace_left") or 0) + 59) // 60)
        return f"agents idle — letting the {DEVICE} sleep in {m} min"
    if kmode == "clamshell":
        return "long agents keep running with the lid closed"
    return "agents keep running; the screen still sleeps"


def open_desktop(win, s):
    d = (s.get("apps") or {}).get("desktop") or {}
    if not d.get("installed"):
        return
    if d.get("running") and not d.get("guarded"):
        if not confirm(win, "Quit Claude Desktop and reopen it through the guard?"):
            return
        send({"cmd": "desktop", "relaunch": True})
    else:
        send({"cmd": "desktop"})


# --------------------------------------------------------------------------- #
# View model — everything the panels need, derived once per composed frame.
# --------------------------------------------------------------------------- #
def agents_view(s):
    """Agents split by what they ask of you. None when the daemon predates
    the `agents` key (the panels are then omitted, as before)."""
    ag = s.get("agents")
    if not isinstance(ag, dict):
        return None
    sessions = [x for x in (ag.get("sessions") or []) if isinstance(x, dict)]
    by_id = {x.get("session_id"): x for x in sessions}
    A = types.SimpleNamespace(need=[], turn=[], working=[], paused=[], resting=[])
    listed = set()
    for nu in (ag.get("needs_you") or []):    # daemon order = rank order
        if not isinstance(nu, dict):
            continue
        sid = nu.get("session_id")
        sess = by_id.get(sid) or {}
        if sess.get("dismissed"):
            continue
        reason = nu.get("reason") or sess.get("status") or ""
        row = (reason, sess, nu.get("since"), sid)
        (A.need if reason in NEED else A.turn).append(row)   # only NEED counts
        listed.add(sid)
    for x in sessions:
        sid = x.get("session_id")
        if x.get("dismissed") or sid in listed:
            continue
        st = x.get("status")
        if st == "working":
            A.working.append(("working", x, None, sid))
        elif st == "paused":           # user-suspended: calm, no alarm
            A.paused.append(("paused", x, None, sid))
        elif st in ("idle", "gone", "done"):
            A.resting.append(x)
    summary = ag.get("summary") or {}
    A.working_n = summary.get("working", len(A.working)) or 0
    A.done_today = summary.get("done_today", 0) or 0
    A.coll = None
    for c in (ag.get("collisions") or []):
        if not isinstance(c, dict):
            continue
        n = len(c.get("session_ids") or []) or 2
        repo = os.path.basename(str(c.get("git_root") or "")) or "one repo"
        A.coll = f"⚠ {n} agents in {repo}"
        files = c.get("files") or []
        if c.get("level") == "file" and files:
            A.coll += f" — both touching {os.path.basename(str(files[0]))}"
        break
    routing = s.get("routing") or {}
    intended = routing.get("intended")
    if intended is None:                 # old daemon: fall back to file truth
        intended = routing.get("installed")
    n_ung = summary.get("unguarded", 0) or 0
    n_pin = summary.get("pinned", 0) or 0
    A.guard_line, A.guard_color = None, C_BAD
    if intended and n_ung:
        A.guard_line = (f"⚠ {n_ung} chat{'s' if n_ung != 1 else ''} started "
                        f"before the guard — restart to protect")
    elif not intended and n_pin:
        A.guard_line = (f"{n_pin} chat{'s' if n_pin != 1 else ''} still on the "
                        f"old proxy — safe until restart")
        A.guard_color = C_DIM
    return A


def view(s, now):
    V = types.SimpleNamespace()
    g = V.g = s.get("guard") or {}
    V.loc = s.get("location") or {}
    V.has_net = isinstance(s.get("net"), dict)
    V.net = s.get("net") or {}
    V.plan = s.get("plan") or {}
    V.u = s.get("usage") if isinstance(s.get("usage"), dict) else {}
    routing = s.get("routing") or {}
    V.routed = bool(routing.get("installed"))
    V.intended = routing.get("intended")
    if V.intended is None:
        V.intended = routing.get("installed")
    V.cc = g.get("target_cc") or (s.get("settings") or {}).get("country")
    V.target = cname(V.cc) if V.cc else "your country"
    V.recent = [r for r in (s.get("recent") or []) if isinstance(r, dict)]
    V.pending = bool(g.get("pending"))
    V.stale = now - (s.get("ts") or 0) >= 5
    if V.stale:
        V.label, V.color, rs = "Tower daemon not responding", C_WARN, "verify"
    else:
        (V.label, V.color), rs = status_of(s), radar_state(s)
    frames, V.rcolor = RADAR[rs]
    V.radar = frames[0]
    V.rfx = ("spin", frames, 0.25) if len(frames) > 1 else None
    V.explain = explain(V)
    ka = V.ka = s.get("keepawake") or {}
    V.kmode = ka.get("mode", "off")
    V.kon = bool(ka.get("on")) and V.kmode != "off"
    V.held = V.kon and ka.get("holding", True)   # armed ≠ held
    apps = s.get("apps") if isinstance(s.get("apps"), dict) else {}
    V.desk = apps.get("desktop") if isinstance(apps.get("desktop"), dict) else {}
    # Desktop earns a line only when there's a gap to act on.
    V.desk_gap = bool(V.desk.get("running")) and V.desk.get("guarded") is not True
    V.ag = agents_view(s)
    V.gate = usage_gate(s)
    V.raw = s
    V.req = req_view(s, now)
    V.dense = False                       # set by compose() on big screens
    return V


# --------------------------------------------------------------------------- #
# Frames — a composed screen is a list of draw ops + hitboxes, built from one
# state snapshot (and the size, and the second) and cached; animation ticks
# just replay it, re-timing only the shimmer/spin ops. So a 12fps shimmer costs
# a replay, never a re-layout.
# --------------------------------------------------------------------------- #
class Frame:
    __slots__ = ("h", "w", "ops", "hits", "live")

    def __init__(self, h, w):
        self.h, self.w = h, w
        self.ops = []
        self.hits = ([], [], [])     # segment > line > panel precedence
        self.live = False            # an op animates → repaint every tick

    def op(self, y, x, t, attr=0, fx=None):
        if not t or y < 0 or y >= self.h or x < 0 or x >= self.w:
            return
        room = self.w - x - (1 if y == self.h - 1 else 0)   # bottom-right is unwritable
        if tw(t) > room:
            t = clip(t, room, ell=False)
        self.ops.append((y, x, t, attr, fx))
        if fx and MOTION:
            self.live = True

    def hit(self, y, x1, x2, act, level=0):
        if act is not None and x2 >= x1:
            self.hits[level].append((y, x1, x2, act))


def _add(win, y, x, t, attr):
    try:
        win.addstr(y, x, t, attr)
    except curses.error:
        pass


def blit(win, fr):
    win.erase()
    now = time.time()
    for y, x, t, attr, fx in fr.ops:
        if fx is None:
            _add(win, y, x, t, attr)
        elif fx[0] == "spin":
            frames, per = fx[1], fx[2]
            _add(win, y, x, frames[int(now / per) % len(frames)] if MOTION
                 else frames[0], attr)
        elif not MOTION:
            _add(win, y, x, t, cp(fx[1]))
        else:
            # Shimmer for in-flight work: a bright band sweeps across the text
            # (~1.8s period, the app's shimmerPeriod). Bright core, normal
            # shoulders, dim elsewhere — attributes, since curses has no
            # gradients.
            color = fx[1]
            span = len(t) + 6
            pos = (now % 1.8) / 1.8 * span - 3
            for i, ch in enumerate(t):
                d = abs(i - pos)
                if d < 1.2:
                    a = cp(color) | B
                elif d < 2.6:
                    a = cp(color)
                else:
                    a = cp(color) | curses.A_DIM
                _add(win, y, x, ch, a)
                x += _cw(ch)
    HITBOXES[:] = fr.hits[0] + fr.hits[1] + fr.hits[2]
    win.noutrefresh()
    curses.doupdate()


# Lines are (segments, right_segments, priority, action); a segment is
# (text, attr, fx, action). Priority decides what survives a short panel:
# the lowest-priority lines drop first, the order of the rest never changes.
def sg(text, attr=0, fx=None, act=None):
    return (text, attr, fx, act)


def ln(*segs, right=(), prio=50, act=None):
    return (segs, tuple(right), prio, act)


BLANK = ((), (), 1, None)        # breathing room — the first thing to go


def _segw(segs):
    return sum(tw(clean(s[0])) for s in segs)


def put_segs(fr, y, x, room, segs):
    """Segments left→right within `room` cells; the cut one ends in …"""
    for text, attr, fx, act in segs:
        if room <= 0:
            break
        t = clean(text)
        n = tw(t)
        if n > room:
            t = clip(t, room)
            n = tw(t)
        if t:
            fr.op(y, x, t, attr, fx)
            fr.hit(y, x, x + n - 1, act, 0)
        x += n
        room -= n
    return x


def put_line(fr, y, x, iw, line):
    """A line in iw cells: content left, meta right-aligned. When both don't
    fit, the right side gives way first — leading segments drop (so an agent
    keeps its age, a verdict its country) — and the content clips with …"""
    segs, rsegs, _, act = line
    fr.hit(y, x, x + iw - 1, act, 1)
    lw = _segw(segs)
    rw = _segw(rsegs) if rsegs else 0
    if rw:
        keep = min(lw, max(10, iw * 3 // 5))
        if keep + 1 + rw > iw:
            rs = list(rsegs)
            while len(rs) > 1 and keep + 1 + _segw(rs) > iw:
                rs.pop(0)
            rw = _segw(rs)
            if keep + 1 + rw > iw:
                rw = iw - keep - 1
                if rw < 4:
                    rs, rw = [], 0
            rsegs = rs
    if rw:
        put_segs(fr, y, x + iw - rw, rw, rsegs)
        put_segs(fr, y, x, iw - rw - 1, segs)
    else:
        put_segs(fr, y, x, iw, segs)


def fit_lines(lines, k, more=None):
    """The k most important lines, in their original order. `more` =
    (floor, make): if lines at/above `floor` priority were hidden, the last
    kept line becomes make(n_hidden) — "+3 more agents"."""
    if len(lines) <= k:
        return lines
    if k <= 0:
        return []
    keep = sorted(sorted(range(len(lines)),
                         key=lambda i: (-lines[i][2], i))[:k])
    out = [lines[i] for i in keep]
    if more:
        floor, make = more
        kset = set(keep)
        hidden = sum(1 for i, l in enumerate(lines)
                     if l[2] >= floor and i not in kset)
        if hidden:
            if out[-1][2] >= floor:
                hidden += 1
            out[-1] = make(hidden)
    return out


class Panel:
    """A titled, rounded panel, sized to its content — never stretched.
    `variants` run richest → most condensed; it renders the richest that fits,
    and below the smallest it keeps the highest-priority lines. With one row
    it collapses to its `summary`."""
    __slots__ = ("title", "variants", "summary", "right", "act", "prio",
                 "least", "more", "foot")

    def __init__(self, title, variants, summary=(), right=(), act=None,
                 least=None, more=None, foot=()):
        vs, last = [], None
        for v in variants:                # keep strictly shrinking variants
            if v is not None and (last is None or len(v) < last):
                vs.append(list(v))
                last = len(v)
        self.variants = vs or [[]]
        self.title = title
        self.summary = summary
        self.right = right
        self.act = act
        self.prio = 50
        self.least = (len(self.variants[-1]) if least is None
                      else min(least, len(self.variants[0])))
        self.more = more
        self.foot = foot

    def full(self):
        return len(self.variants[0])

    def fit(self, k):
        for v in self.variants:
            if len(v) <= k:
                return v
        return fit_lines(self.variants[-1], k, self.more)

    def grow(self, cur, left):
        """The next box height from cur within `left` spare rows."""
        if len(self.variants) == 1:
            tgt = min(self.full() + 2, cur + left)
            return tgt if tgt >= 3 else cur
        opts = [len(v) + 2 for v in self.variants if cur < len(v) + 2 <= cur + left]
        return max(opts) if opts else cur


def draw_panel(fr, y, x, h, w, p):
    L = cp(C_LINE)
    title = p.title if isinstance(p.title, list) else [sg(p.title, cp(C_DIM))]
    for yy in range(y, y + h):
        fr.hit(yy, x, x + w - 1, p.act, 2)
    if h <= 1:
        # Collapsed: ╶─ TITLE  summary ──────╴
        fr.op(y, x, clean("╶─"), L)
        xx = put_segs(fr, y, x + 3, w - 5, title + [sg("   ")] + list(p.summary))
        n = (x + w - 1) - (xx + 1)
        if n >= 0:
            fr.op(y, xx + 1, clean("─" * n + "╴"), L)
        return
    fr.op(y, x, clean("╭" + "─" * (w - 2) + "╮"), L)
    tx = put_segs(fr, y, x + 2, max(0, w - 6), [sg(" ")] + title + [sg(" ")])
    if p.right:
        rw = min(_segw(p.right), x + w - 5 - tx)
        if rw >= 4:
            put_segs(fr, y, x + w - 4 - rw, rw + 2,
                     [sg(" ")] + list(p.right) + [sg(" ")])
    side = clean("│")
    for r in range(1, h - 1):
        fr.op(y + r, x, side, L)
        fr.op(y + r, x + w - 1, side, L)
    fr.op(y + h - 1, x, clean("╰" + "─" * (w - 2) + "╯"), L)
    if p.foot:
        put_segs(fr, y + h - 1, x + 2, w - 4, [sg(" ")] + list(p.foot) + [sg(" ")])
    for i, line in enumerate(p.fit(h - 2)):
        put_line(fr, y + 1 + i, x + 2, w - 4, line)


def allot(panels, H):
    """Rows per panel in one column of height H, by priority: everyone gets a
    one-line summary, then each (most important first) its useful minimum,
    then room to grow up to its content — never past it. Panels that can't get
    even a summary row drop, least important first.
    -> ([(panel, rows)] in visual order, spare rows)."""
    ps = [p for p in panels if p]
    while len(ps) > H:
        ps.remove(min(ps, key=lambda p: p.prio))
    ht = {id(p): 1 for p in ps}
    left = H - len(ps)
    rank = sorted(ps, key=lambda p: -p.prio)
    for p in rank:
        want = p.least + 2 if p.least > 0 else 1
        if 1 < want and want - 1 <= left:
            ht[id(p)] = want
            left -= want - 1
    for p in rank:
        if left > 0:
            cur = ht[id(p)]
            nxt = p.grow(cur, left)
            left -= nxt - cur
            ht[id(p)] = nxt
    return [(p, ht[id(p)]) for p in ps], left


def column(fr, panels, y, x, w, H, gap=None):
    """Stack a column's panels top-down, each sized to what it shows. One
    blank row between panels when every panel still gets all its rows; the
    column ends where its content ends — leftover rows stay calm, empty
    screen below, never padding inside a box."""
    n = len([p for p in panels if p])
    if gap is not None:                   # a fixed rhythm (big screens)
        plan, _ = allot(panels, H - gap * max(0, n - 1))
    else:
        plan, _ = allot(panels, H)
        gap = 0
        if n > 1:
            spaced, _ = allot(panels, H - (n - 1))
            if [r for _, r in spaced] == [r for _, r in plan]:
                gap = 1
    for p, rows in plan:
        if rows >= 3:                     # a box is exactly its lines + border
            rows = min(rows, len(p.fit(rows - 2)) + 2)
        draw_panel(fr, y, x, rows, w, p)
        y += rows + gap
    return y


# --------------------------------------------------------------------------- #
# Panels — four, sized to their content: GUARD, AGENTS, PLAN, NETWORK. Each
# builder gets the view and its inner width and returns a Panel (or None when
# the daemon has nothing for it). The deeper usage numbers live behind `u`.
#
# One grammar everywhere: a row label in normal weight in a fixed LABW column,
# the value bold, meta dim, meters white over a dim track. Color only means
# something: amber = held / warn, red = failed / unguarded, green = the small
# "on / healthy" dot and nothing else.
# --------------------------------------------------------------------------- #
LABW = 11            # the one label column every panel shares


def _dim(t, act=None):
    return sg(t, cp(C_DIM), act=act)


def _val(t, bold=True, act=None):
    return sg(t, cp(C_TITLE) | (B if bold else 0), act=act)


def _label(t):
    return sg(f"{t:<{LABW}}", cp(C_TITLE))


def _dot(color):
    return sg("●", cp(color) | B)


def _join(parts, gap="  "):
    """Segment groups joined by a plain gap — for right-aligned meta."""
    out = []
    for p in parts:
        if not p:
            continue
        if out:
            out.append(sg(gap))
        out += p
    return out


def _soft(segs, right, iw):
    """Optional right-hand meta: shown only when the row's content fits
    beside it whole — it never makes the content clip."""
    return right if right and _segw(segs) + 2 + _segw(right) <= iw else []


def pcolor(p):
    """A plan meter is white until it means something: amber ≥ 60%, red ≥ 85%."""
    return C_BAD if p >= 85 else (C_WARN if p >= 60 else C_TITLE)


# ---- GUARD ---------------------------------------------------------------- #
def location_line(V, iw):
    loc, st = V.loc, V.loc.get("status")
    place = ", ".join(str(x) for x in (loc.get("city"), loc.get("region")) if x)
    cc = loc.get("country_cc")
    tail = " · ".join(str(x) for x in (loc.get("ip"), loc.get("isp")) if x)
    right = []
    if V.net.get("status") == "offline":
        segs = [_dim("unknown — internet down")]
    elif st == "OK":
        if loc.get("in_target"):
            segs = [_val(place or cname(cc))]
        else:
            segs = [sg(f"outside {V.target}", cp(C_WARN) | B),
                    _dim("  " + ", ".join(x for x in (place, cname(cc)) if x))]
        right = [_dim(tail)] if tail else []
    elif st == "CACHED":
        segs = [_dim(f"last known {place + ' ' if place else ''}— re-checking…")]
    elif loc.get("error"):
        segs = [sg("unknown — Claude held until confirmed", cp(C_WARN) | B)]
    else:
        segs = [_dim("locating…")]
    segs = [_label("Location")] + segs
    return ln(*segs, right=_soft(segs, right, iw), act="recheck", prio=820)


def guard_line(V, iw):
    g = V.g
    segs = [_label("Guard")]
    if V.routed:
        segs += [_dot(C_GOOD), _val(" routed", act="route")]
    else:
        segs.append(sg("○ direct", cp(C_BAD) | B, act="route"))
    segs.append(_dim("  ·  "))
    if g.get("enforce", True):
        segs.append(_val("enforced", bold=False, act="enforce"))
    else:
        segs.append(sg("monitor only", cp(C_WARN) | B, act="enforce"))
    segs += [_dim("  ·  "),
             _dim("all traffic" if g.get("block_all") else "Claude only", act="scope")]
    port = g.get("proxy_port", "?")
    if g.get("proxy_up"):
        right = _soft(segs, [_dim(f"proxy :{port}")], iw)
    else:                                  # a down proxy is never optional
        right = [sg(f"proxy :{port} down", cp(C_BAD) | B)]
    return ln(*segs, right=right, prio=850)


def awake_line(V):
    desc = keepawake_line(V.kmode if V.kon else "off", V.ka)
    if V.held:
        segs = [_dot(C_GOOD), _val(" on"), _dim("  " + desc)]
    elif V.kon:
        segs = [_val("◐ armed"), _dim("  " + desc)]
    else:
        segs = [_dim("○ off  " + desc)]
    return ln(_label("Awake"), *segs, act="keepawake", prio=600)


def desk_line(V, prio=960):
    """Claude Desktop earns a line only when it's running unguarded."""
    if not V.desk_gap:
        return []
    return [ln(_label("Desktop"), sg("running unguarded", cp(C_WARN) | B),
               _dim("  its chats go direct"),
               right=[_dim("d relaunch")], act="desktop", prio=prio)]


def held_line(V, indent):
    held = V.g.get("holding")
    n = held if isinstance(held, int) and held > 0 else 0
    if not (V.pending or n):
        return []
    t = (f"↻ {n} Claude request{'s' if n != 1 else ''} held" if n
         else "↻ Claude request held")
    return [ln(sg(indent + t, cp(C_WARN) | B), _dim(" — pending, resumes on its own"),
               prio=950)]


def p_guard(V, iw):
    vc = V.color                        # green protected · amber held · red off
    verdict = ln(sg(V.radar, cp(V.rcolor) | B, V.rfx), sg("  "),
                 sg(V.label, cp(vc) | B),
                 right=[_dim("target "), _val(V.target, bold=False, act="country")],
                 prio=1000)
    ind = "   "                         # body text sits under the verdict text
    why = [ln(_dim(ind + t), prio=900 - j * 0.01)
           for j, t in enumerate(textwrap.wrap(V.explain, max(10, iw - len(ind))))]
    why1 = [ln(_dim(ind + V.explain), prio=900)] if V.explain else []
    hold = held_line(V, ind)
    rows = desk_line(V) + [location_line(V, iw), guard_line(V, iw), awake_line(V)]
    full = [verdict] + why + hold + [BLANK] + rows
    dense = [verdict] + why1 + hold + rows
    tight = [verdict] + hold + [r for r in rows if r[2] >= 820]
    return Panel("GUARD", [full, dense, tight], summary=list(verdict[0]))


# ---- AGENTS --------------------------------------------------------------- #
NEED_LOOK = {"failed": ("✗", C_BAD, "failed"),
             "pending_tool": ("!", C_WARN, "needs approval"),
             "asking": ("?", C_WARN, "has a question")}


def _name(sess):
    return str(sess.get("project_name")
               or os.path.basename(sess.get("cwd") or "") or "?")


def _mark_frames(sess):
    fam = str(sess.get("model_family") or model_name(sess.get("model"))).lower()
    return next((f for k, f in MODEL_SPIN.items() if k in fam), SPIN_OTHER)


TIER_COLOR = {"opus": C_OPUS, "sonnet": C_SONNET, "haiku": C_HAIKU,
              "fable": C_FABLE}


def tier_color(model):
    """The model's tier color, for its mark only (a model id or family)."""
    m = str(model or "").lower()
    return next((c for k, c in TIER_COLOR.items() if k in m), C_TITLE)


def _pending_detail(sess):
    pt = sess.get("pending_tool")
    if isinstance(pt, dict):
        return " ".join(str(x) for x in (pt.get("name"), pt.get("detail")) if x)
    return str(sess.get("activity") or "")


def _agent_line(V, row, kind, prio, nw, mw, narrow=False):
    """One agent: mark · project · model · activity, the turn clock right."""
    reason, sess, since, sid = row
    frames = _mark_frames(sess)
    now = time.time()
    act_txt = str(sess.get("activity") or "")
    fx, name_attr = None, cp(C_TITLE) | B
    right = []
    if kind == "need":
        mark, look, phrase = NEED_LOOK.get(
            reason, ("!", C_WARN, AGENT_PHRASE.get(reason, reason or "needs you")))
        mattr = cp(look) | B
        what = [sg(phrase, cp(look) | B)]
        det = _pending_detail(sess) if reason != "failed" else act_txt
        if det:
            what.append(_dim("  " + det))
        when = ago(since or sess.get("status_since"))
        if when:
            right = [sg(when, cp(look))]
    elif kind == "working":
        tc = tier_color(sess.get("model_family") or sess.get("model"))
        mark, mattr, fx = frames[0], cp(tc) | B, ("spin", frames, 0.2)
        # Thinking: the model mark is alive. A tool in flight: the activity
        # shimmers — unless the guard is reconnecting (one loudest thing).
        thinking = not act_txt or act_txt.startswith("thinking")
        wfx = ("shimmer", C_TITLE) if not thinking and not V.pending else None
        what = [sg(act_txt or "working…", cp(C_DIM if thinking else C_TITLE), wfx)]
        ticks = sess.get("ticks")
        done = ticks.get("tools_done") if isinstance(ticks, dict) else None
        t0 = sess.get("turn_at") or sess.get("status_since")
        right = _join([[_dim(f"{done} tools")] if done and not narrow else [],
                       [_val(f"{_dur(now - t0):>6}", bold=False)]
                       if isinstance(t0, (int, float)) and t0 else []])
    else:                                     # your turn / paused: listed, quiet
        tc = tier_color(sess.get("model_family") or sess.get("model"))
        mark, mattr, name_attr = frames[0], cp(tc), cp(C_TITLE)
        if kind == "turn" and reason == "done":
            mark, mattr = "✓", cp(C_GOOD) | B            # done reads done
        result = sess.get("result")
        if kind == "paused":
            what = [_dim("paused")]
        elif reason == "done":
            what = [_dim("done" + (f" — {result}" if result else ""))]
        else:
            what = [_dim("waiting for your next prompt")]
        when = ago(since or sess.get("status_since"))
        right = [_dim(when)] if when else []
    segs = [sg(mark, mattr, fx), sg("  "), sg(pad(_name(sess), nw), name_attr),
            sg("  ")]
    if mw:
        has_model = sess.get("model") or sess.get("model_family")
        segs.append(_dim(pad(model_label(sess) if has_model else "", mw) + "  "))
    if V.intended and sess.get("guarded") is False:
        segs.append(sg("unguarded  ", cp(C_BAD) | B))     # started before the guard
    segs += what
    return ln(*segs, right=right, act=("focus", sid) if sid else None, prio=prio)


def _tree_lines(sess, sid, prio, limit):
    """The subagent tree, dim, hung under the project name."""
    out = []
    for branch, node, stxt, right, live in subagent_lines(sess, limit):
        out.append(ln(sg("   " + branch + " ", cp(C_LINE)),
                      sg(node, cp(C_TITLE) | B if live else cp(C_GOOD)),
                      _dim(" " + stxt),
                      right=[_dim(f"{right:>6}")] if right else (),
                      act=("focus", sid) if sid else None, prio=prio))
    return out


def _detail_line(sess, sid, prio):
    """Big screens: the agent's last prompt, dim, and how long it has run."""
    ask = sess.get("title") or sess.get("last_prompt")
    up = ago(sess.get("started"))
    if not ask:
        return []
    return [ln(sg("   ↳ ", cp(C_LINE)), _dim("“" + " ".join(str(ask).split()) + "”"),
               right=[_dim(f"up {up}")] if up else (),
               act=("focus", sid) if sid else None, prio=prio)]


def _more(label):
    return lambda n: ln(_dim(f"   +{n} more {label}"), prio=0)


def p_agents(V, iw):
    A = V.ag
    if A is None:
        return None
    rows = ([("need", r) for r in A.need] + [("working", r) for r in A.working]
            + [("turn", r) for r in A.turn] + [("paused", r) for r in A.paused])
    narrow = iw < 60
    nw = min(18 if iw >= 72 else 12 if narrow else 14,
             max([tw(clean(_name(r[1]))) for _, r in rows] or [4]))
    ms = [tw(clean(model_label(r[1]))) for _, r in rows
          if r[1].get("model") or r[1].get("model_family")]
    mw = min(20, max(ms or [0]))
    if iw < 3 + nw + 2 + mw + 2 + 14 + 18:   # the activity keeps room to read
        mw = 0
    lim = 8 if V.dense else 4 if iw >= 70 else 2
    lines = []
    if A.coll:
        lines.append(ln(sg(A.coll, cp(C_WARN)), prio=980))
    if A.guard_line:
        lines.append(ln(sg(A.guard_line, cp(A.guard_color)), prio=970))
    base = {"need": 900, "working": 700, "turn": 600, "paused": 550}
    for i, (kind, r) in enumerate(rows):
        lines.append(_agent_line(V, r, kind, base[kind] - i * 0.01, nw, mw, narrow))
        if V.dense:                       # big screens: what it was asked
            lines += _detail_line(r[1], r[3], 250 - i * 0.01)
        if kind in ("need", "working"):
            # Details, then trees, fold away before any agent row does.
            lines += _tree_lines(r[1], r[3], 300 - i * 0.01, lim)
    if not rows:
        lines.append(ln(_dim("No agents running"), prio=650))
        lines.append(ln(_dim("start  claude  in any terminal — it shows up here"),
                        prio=2))
    if A.resting:
        names = ", ".join(str(x.get("project_name") or "?") for x in A.resting[:6])
        lines.append(ln(_dim(f"◌  {len(A.resting)} resting  ·  {names}"), prio=200))
    right = [_dim(f"{A.working_n} working  ·  {A.done_today} done today")]
    summary = ([sg(f"{len(A.need)} need you", cp(C_WARN) | B), _dim("  ·  ")]
               if A.need else []) + [_dim(f"{A.working_n} working")]
    nrows = sum(1 for l in lines if l[2] >= 550)
    return Panel("AGENTS", [lines], summary=summary, right=right,
                 least=max(1, min(6, nrows)), more=(550, _more("agents")))


# ---- PLAN ----------------------------------------------------------------- #
PLAN_ROWS = (("Session", "session"), ("Weekly", "week"), ("Fable", "fable"))


def reset_short(node):
    """'↻ 1h 48m' — the reset countdown under ↻, which already says 'resets'.
    The units are exactly until()'s; only its leading 'in ' is dropped."""
    rt = reset_text(node)
    if not rt:
        return ""
    return "↻ " + (rt[3:] if rt.startswith("in ") else rt)


def plan_meters(plan, iw, prio=900, cap=32):
    """Session / Weekly / Fable: label · bold % · a slim fixed meter · ↻ reset.
    Every column starts at the same cell, so the three rows read as a table."""
    nodes = []
    for label, key in PLAN_ROWS:
        node = plan.get(key)
        if isinstance(node, dict) and isinstance(node.get("pct"), (int, float)):
            nodes.append((label, int(node["pct"]), reset_short(node)))
    rw = max([tw(clean(r)) for _, _, r in nodes] or [0])
    mwid = min(cap, iw - LABW - 4 - 2 - (2 + rw if rw else 0))
    if mwid < 8 and rw:                  # no room: the countdown goes first
        rw = 0
        mwid = min(cap, iw - LABW - 4 - 2)
    out = []
    for i, (label, p, rt) in enumerate(nodes):
        segs = [_label(label), sg(f"{p:>3}%", cp(pcolor(p)) | B)]
        if mwid >= 4:
            fill, track = meter(p / 100.0, mwid)
            segs += [sg("  "), sg(fill, cp(pcolor(p)) | B), sg(track, cp(C_LINE))]
        if rw and rt:
            segs.append(_dim("  " + rt))
        out.append(ln(*segs, prio=prio - i * 50))
    return out


def cost_line(V, iw, prio=300):
    """The local estimate, down to one dim line."""
    u = V.u
    if not u:
        return []
    today, wk = u.get("today") or {}, u.get("week") or {}
    segs = [_dim(f"≈ {fmt_cost(today.get('cost'))} today  ·  "
                 f"{fmt_cost(wk.get('cost'))} week")]
    return [ln(*segs, right=_soft(segs, [_dim("local estimate")], iw),
               act="usage", prio=prio)]


def gate_lines(V, iw, spacious=True):
    head, detail = V.gate
    body = [ln(sg(head, cp(C_WARN) | B), prio=900)] + [
        ln(_dim(t), prio=800 - j * 0.01)
        for j, t in enumerate(textwrap.wrap(detail, max(16, min(iw, 64))))]
    return [BLANK] + body + [BLANK] if spacious else body


def p_plan(V, iw):
    """PLAN — the REAL limits, mirrored from `claude -p /usage`."""
    plan = V.plan
    if V.gate:
        # The guard isn't passing Claude → no usage to show: an honest message
        # (connection vs location), never stale numbers.
        return Panel("PLAN", [gate_lines(V, iw), gate_lines(V, iw, False)],
                     summary=[sg(V.gate[0], cp(C_WARN) | B)],
                     right=[sg("paused", cp(C_WARN))], act="planrefresh")
    if plan.get("disabled"):
        l0 = ln(_dim("Live limits are off — turn them on in the menu"), prio=900)
        return Panel("PLAN", [[l0] + cost_line(V, iw), [l0]], summary=l0[0],
                     right=[_dim("off")], act="planrefresh")
    if not plan.get("ok"):
        l0 = (ln(sg("unavailable — " + str(plan.get("error")), cp(C_WARN)), prio=900)
              if plan.get("error") else ln(_dim("fetching from Claude /usage…"), prio=900))
        return Panel("PLAN", [[l0] + cost_line(V, iw), [l0]], summary=l0[0],
                     act="planrefresh")
    right = [_dim("updating…" if plan.get("refreshing")
                  else f"updated {ago(plan.get('updated')) or 'just now'} ago"
                  if plan.get("updated") else "")]
    meters = plan_meters(plan, iw)
    cost = cost_line(V, iw)
    summ = []
    for label, key in PLAN_ROWS[:2]:
        node = plan.get(key)
        if isinstance(node, dict) and isinstance(node.get("pct"), (int, float)):
            p = int(node["pct"])
            summ += ([_dim("  ·  ")] if summ else []) + [
                _dim(label.lower() + " "), sg(f"{p}%", cp(pcolor(p)) | B)]
    variants = [meters + ([BLANK] + cost if cost else []), meters + cost, meters,
                meters[:2], meters[:1]]
    if not meters:
        variants = [[ln(_dim("no limits reported"), prio=900)] + cost]
    return Panel("PLAN", variants, summary=summ, right=right, act="planrefresh",
                 least=min(2, len(meters)) or 1)


# ---- NETWORK + REQUESTS --------------------------------------------------- #
_REQ_MIN = {}        # minute → Claude requests seen in it (max over reads)


def _req_epoch(t, now):
    """A `recent` stamp ("HH:MM:SS", local time) as epoch seconds, or None."""
    try:
        hh, mm, ss = (int(x) for x in str(t).split(":"))
        lt = time.localtime(now)
        e = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mm, ss, 0, 0, -1))
    except (ValueError, TypeError, OverflowError):
        return None
    return e - 86400 if e > now + 60 else e


def req_view(s, now):
    """Requests through the guard, distilled: Claude requests per minute, the
    current rate, the daemon's counters and the newest Claude request.
    `recent` is a short ring, so the TUI keeps its own per-minute history —
    each minute keeps the most it was ever seen holding (exact once the
    minute is inside the ring, never double-counted across reads)."""
    g = s.get("guard") or {}
    rows = [(_req_epoch(r.get("t"), now), r)
            for r in (s.get("recent") or []) if isinstance(r, dict)]
    per, last = {}, None
    for e, r in rows:
        if e is None or r.get("kind") != "claude":
            continue
        per[int(e // 60)] = per.get(int(e // 60), 0) + 1
        if last is None or e >= last[0]:
            last = (e, str(r.get("host") or "claude"))
    for k, v in per.items():
        if v > _REQ_MIN.get(k, 0):
            _REQ_MIN[k] = v
    cur = int(now // 60)
    for k in [k for k in _REQ_MIN if k < cur - 240]:
        del _REQ_MIN[k]
    R = types.SimpleNamespace(rows=rows, last=last)
    R.rate = sum(1 for e, r in rows if e is not None and e >= now - 60
                 and r.get("kind") == "claude")
    R.passed = g.get("allowed", 0) or 0
    R.held_total = g.get("blocked", 0) or 0
    h = g.get("holding")
    R.holding = h if isinstance(h, int) and h > 0 else 0
    R.series = lambda n: [_REQ_MIN.get(cur - n + 1 + i, 0) for i in range(max(0, n))]
    return R


def net_status(V, short=False):
    """The status as dot + word (+ the reason, dim). Healthy is a green dot."""
    net = V.net
    nst = net.get("status") or "checking"
    look = {
        "online": (C_GOOD, "Online", ""),
        "degraded": (C_WARN, "Degraded", {
            "dns": "DNS problem",
            "api_slow": "slow path to Anthropic"}.get(net.get("reason"), "slow link")),
        "offline": (C_BAD, "Offline", "Claude is held"),
        "captive": (C_BAD, "Wi-Fi login required", "open a browser"),
        "api_issue": (C_BAD, "Anthropic unreachable", "internet ok"
                      + ("" if short or not net.get("api_error")
                         else f" · {net.get('api_error')}")),
    }.get(nst, (C_DIM, "Checking…", ""))
    col, word, why = look
    segs = [_dot(col), sg(" " + word, cp(C_TITLE if col == C_GOOD else col) | B)]
    R = getattr(V, "req", None)
    if short and R and R.holding:         # a hold outranks the numbers
        segs.append(sg(f"  ↻ {R.holding} held", cp(C_WARN) | B))
    if why:
        segs.append(_dim("  " + why))
    if short and nst in ("online", "degraded"):
        segs += [_dim(f"  ·  internet {fmt_ms(net.get('internet_ms'))}"
                      f"  ·  api {fmt_ms(net.get('api_ms'))}")]
    if short and R and R.rate and not R.holding:   # requests fold in last
        segs.append(_dim(f"  ·  {R.rate} req/min"))
    return segs


def _lat_color(V, key):
    """Latency in white; amber when that path is degraded, red when failing."""
    net = V.net
    nst, why = net.get("status"), net.get("reason")
    if not isinstance(net.get(key), (int, float)):
        return C_BAD if nst in ("offline", "api_issue", "captive") else C_DIM
    if nst == "api_issue" and key == "api_ms":
        return C_BAD
    if nst == "degraded":
        return C_WARN if why != "api_slow" or key == "api_ms" else C_TITLE
    return C_TITLE


def _scale(ok, floor=True):
    hi, lo0 = max(ok), min(ok)
    if not floor:
        return 0.0, max(hi, 1)
    # Floored well under the fastest sample: jitter shows, but a steady link
    # reads as steady rather than as noise blown up to full height.
    return max(0.0, min(lo0 * 0.6, lo0 - (hi - lo0))), hi


def spark_segs(vals, width, floor=True):
    """A one-row sparkline, newest at the right: quiet gray, with the newest
    cell bright so it reads live. A failed probe is a red cell."""
    vals = vals[-width:] if width > 0 else []
    ok = [v for v in vals if v is not None]
    if not vals or not ok:
        return [sg(" " * max(0, width))] if width > 0 else []
    lo, hi = _scale(ok, floor)
    cells = []
    for v in vals:
        if v is None:
            cells.append((SPARK[-2], cp(C_BAD)))
        else:
            f01 = (v - lo) / (hi - lo) if hi > lo else 0.5
            cells.append((SPARK[max(0, min(7, int(round(f01 * 7))))], cp(C_MUTE)))
    if cells[-1][1] == cp(C_MUTE):
        cells[-1] = (cells[-1][0], cp(C_TITLE) | B)
    out = [sg(" " * (width - len(vals)))] if width > len(vals) else []
    for ch, a in cells:                   # runs of one attribute → one segment
        if out and out[-1][1] == a and out[-1][0].strip():
            out[-1] = sg(out[-1][0] + ch, a)
        else:
            out.append(sg(ch, a))
    return out


_DOTS = ((0x01, 0x02, 0x04, 0x40), (0x08, 0x10, 0x20, 0x80))   # braille L/R


def chart_rows(vals, cw, k):
    """A k-row braille line chart over cw cells (two points per cell), newest
    at the right, on the series' own floored scale. The samples are resampled
    to the chart's width and lightly smoothed (a 3-point mean), so it reads
    as a calm trend line rather than a comb; the exact current value sits
    beside it. Gray, the newest cell bright; a failed probe is a red
    full-height column. -> [segments] per row, top first (or None)."""
    if cw <= 0 or not any(v is not None for v in vals):
        return None
    n = min(cw * 2, len(vals))            # points, one per braille half-cell
    pts = []
    for i in range(n):                    # resample: the mean of each bucket
        run = vals[i * len(vals) // n:max(i * len(vals) // n + 1,
                                           (i + 1) * len(vals) // n)]
        ok = [v for v in run if v is not None]
        pts.append(None if len(ok) < len(run) else sum(ok) / len(ok))
    sm = []
    for i, v in enumerate(pts):
        if v is None:
            sm.append(None)
            continue
        win = [x for x in pts[max(0, i - 1):i + 2] if x is not None]
        sm.append(sum(win) / len(win))
    ok = [v for v in sm if v is not None]
    hi, lo0 = max(ok), min(ok)
    lo = max(0.0, lo0 - max((hi - lo0) * 0.15, lo0 * 0.02))
    H = 4 * k
    bits = [[0] * cw for _ in range(k)]
    bad = [False] * cw
    pad0 = cw * 2 - n
    prev = None
    for i, v in enumerate(sm):
        x = pad0 + i
        col, side = x // 2, x % 2
        if v is None:
            bad[col], prev = True, None
            for r in range(k):
                for d in range(4):
                    bits[r][col] |= _DOTS[side][d]
            continue
        lv = int(round((v - lo) / (hi - lo) * (H - 1))) if hi > lo else H // 2
        lv = max(0, min(H - 1, lv))
        a, b = (lv, lv) if prev is None else (min(prev, lv), max(prev, lv))
        for L in range(a, b + 1):         # join to the previous point: a line
            y = H - 1 - L
            bits[y // 4][col] |= _DOTS[side][y % 4]
        prev = lv
    newest = (pad0 + n - 1) // 2
    out = []
    for r in range(k):
        segs = []
        for c in range(cw):
            bv = bits[r][c]
            ch = (chr(0x2800 + bv) if UNICODE else "*") if bv else " "
            a = (cp(C_BAD) if bad[c] else cp(C_TITLE) | B if c == newest
                 else cp(C_MUTE))
            if segs and segs[-1][1] == a:
                segs[-1] = sg(segs[-1][0] + ch, a)
            else:
                segs.append(sg(ch, a))
        out.append(segs)
    return out


BLOCKS = " ▁▂▃▄▅▆▇█"     # 0…8 eighths of a cell, bottom-up (charts)


def requests_line(V, iw, prio=700):
    """ONE row for the requests through the guard: a per-minute sparkline of
    Claude requests, the rate, passed / held. While a request is held right
    now, that is all the row says."""
    R = V.req
    lab = _label("Requests")
    passed = [_dim(f"{R.passed:,} passed")]
    if R.holding:
        segs = [lab, sg(f"↻ {R.holding} held now", cp(C_WARN) | B),
                sg(" — pending", cp(C_WARN))]
        return ln(*segs, right=_soft(segs, passed, iw), prio=prio)
    segs = [lab, _val(f"{f'{R.rate}/min':>7}")]
    held = [sg(f"{R.held_total:,} held", cp(C_WARN))] if R.held_total else []
    meta = passed + ([_dim("  ·  ")] + held if held else [])
    if iw - LABW - 7 - 2 - _segw(meta) - 3 < 8:   # narrow: held outranks passed
        meta = held or passed
    sw = min(24, iw - LABW - 7 - 2 - _segw(meta) - 3)
    if sw >= 6:
        segs += [sg("  ")] + spark_segs(R.series(sw), sw, floor=False)
    segs += [sg("   ")] + meta
    hint = []
    if R.last:
        hint = [_dim(f"{R.last[1]} · {ago(R.last[0]) or '0s'} ago")]
    return ln(*segs, right=_soft(segs, hint, iw), prio=prio)


def p_net(V, iw):
    if not V.has_net:
        return None
    net = V.net
    status = ln(*net_status(V), prio=1000)
    hist = [x for x in (net.get("history") or []) if isinstance(x, dict)]

    def series(k):
        return [x.get(k) if isinstance(x.get(k), (int, float)) else None
                for x in hist]

    vw = 7
    sw = iw - LABW - vw - 2
    keys = (("Internet", "internet_ms"), ("API", "api_ms"))

    def head(label, key):
        return [_label(label),
                sg(f"{fmt_ms(net.get(key)):>{vw}}", cp(_lat_color(V, key)) | B)]

    calm = [ln(*head(l, k), *([sg("  ")] + spark_segs(series(k), sw)
                              if hist and sw >= 8 else []), prio=800 - j)
            for j, (l, k) in enumerate(keys)]
    req = [requests_line(V, iw)] if V.req else []
    if net.get("status") in ("offline", "captive"):
        calm = []                          # no numbers to plot — just the story
    variants = []
    if V.dense and calm and sw >= 16:
        # Room to breathe: a real chart per series, 2–6 rows, scale at right.
        cw = sw - 7
        for k in (5, 4, 3, 2):
            rows = []
            for j, (label, key) in enumerate(keys):
                vals = series(key)
                ch = chart_rows(vals, cw, k)
                if ch is None:
                    rows.append(calm[j])
                    continue
                ok = [v for v in vals if v is not None]
                if j and k >= 3:
                    rows.append(BLANK)
                for r, segs in enumerate(ch):
                    left = head(label, key) if r == 0 else [sg(" " * (LABW + vw))]
                    right = ([_dim(f"{fmt_ms(max(ok)):>6}")] if r == 0 else
                             [_dim(f"{fmt_ms(min(ok)):>6}")] if r == k - 1 else [])
                    rows.append(ln(*left, sg("  "), *segs, right=right,
                                   prio=800 - j - r * 0.01))
            variants.append([status] + rows + req)
    variants += [[status] + calm + req, [status] + calm,
                 [ln(*net_status(V, short=True), prio=1000)]]
    sp = net.get("speedtest") or {}
    right = []
    if sp.get("running"):
        prog = sp.get("progress") if isinstance(sp.get("progress"), (int, float)) else 0
        right = [_dim(f"speed test {int(prog * 100)}%…")]
    return Panel("NETWORK", variants, summary=net_status(V, short=True),
                 right=right, act="speedtest")


def p_requests(V, iw):
    """The request log (big screens): newest first, a run of identical
    requests folded into one row (×N); held rows amber."""
    R = V.req
    if R is None:
        return None
    runs = []
    for e, r in reversed(R.rows):
        key = (r.get("host"), r.get("kind"), r.get("action"))
        if runs and runs[-1][0] == key:
            runs[-1][2] += 1
        else:
            runs.append([key, r, 1])
    # time · host · kind · ×N, then passed / held right — fixed columns
    hw = max(8, min(30, iw - 8 - 2 - 2 - 6 - 5 - 8,
                    max([tw(clean(str(k[0] or "?"))) for k, _, _ in runs] or [8])))
    lines = []
    for i, (key, r, n) in enumerate(runs):
        host, kind, action = key
        held = action != "allowed"
        claude = kind == "claude"
        segs = [_dim(f"{str(r.get('t') or ''):<8}"), sg("  "),
                sg(pad(str(host or "?"), hw),
                   cp(C_WARN) | B if held else cp(C_TITLE if claude else C_DIM)),
                sg("  "), _dim("claude" if claude else "other "),
                _dim(f"{'×' + str(n) if n > 1 else '':>5}")]
        right = [sg("held", cp(C_WARN) | B)] if held else [_dim("passed")]
        lines.append(ln(*segs, right=right, prio=100 - i * 0.01))
    if not lines:
        lines = [ln(_dim("No requests yet — they show up as Claude runs"), prio=100)]
    right = [_dim(f"{R.passed:,} passed")] + (
        [_dim("  ·  "), sg(f"{R.held_total:,} held", cp(C_WARN))] if R.held_total else [])
    return Panel("REQUESTS", [lines], right=right, least=min(3, len(lines)),
                 summary=list(right), more=(0, lambda n: ln(_dim(f"+{n} more"), prio=0)))


# ---- big screens: USAGE · LIMITS · SYSTEM · TIMELINE ----------------------- #
def p_usage(V, iw):
    """The local estimate, measured on this machine at API list prices —
    never your plan %. Cost rows, seven days as thin bars (today bright), the
    model mix with each model's dot in its tier color."""
    u = V.u
    if not u:
        return None
    sess, today = u.get("session") or {}, u.get("today") or {}
    wk, pace = u.get("week") or {}, u.get("pace") or {}
    tiles = []
    for i, (lab, cost, sub) in enumerate((
            ("Today", fmt_cost(today.get("cost")), f"{fmt_tok(today.get('tokens'))} tokens"),
            ("Session", fmt_cost(sess.get("cost")),
             f"{fmt_tok(sess.get('tokens'))} tokens · {sess.get('msgs', 0) or 0} msgs"),
            ("Week", fmt_cost(wk.get("cost")), f"{fmt_tok(wk.get('tokens'))} tokens"),
            ("Projected", "~" + fmt_cost(pace.get("projected_week_cost")),
             "this week, at this pace"))):
        tiles.append(ln(_label(lab), _val(f"{cost:>7}"), _dim("   " + sub),
                        prio=900 - i))
    days = [d for d in (u.get("series") or []) if isinstance(d, dict)][-7:]
    costs = [float(d.get("cost") or 0) for d in days]
    bw = max(6, min(28, iw - LABW - 8))
    week = []
    vmax = max(costs or [0]) or 1.0
    for j, (d, c) in enumerate(zip(days, costs)):
        last = j == len(days) - 1
        fill, track = meter(c / vmax, bw)
        week.append(ln(sg(f"{'Today' if last else _weekday(d.get('day'), 4):<{LABW}}",
                          cp(C_TITLE if last else C_DIM)),
                       sg(fill, cp(C_TITLE) | B if last else cp(C_MUTE)),
                       sg(track, cp(C_LINE)),
                       sg(f"  {fmt_kcost(c):>6}", cp(C_TITLE) if last else cp(C_DIM)),
                       prio=500 - j * 0.01))
    ms = [m for m in (u.get("byModel") or []) if isinstance(m, dict)][:4]
    tot = sum((m.get("tokens") or 0) for m in ms) or 1
    mix = []
    mb = min(20, iw - LABW - 1 - 8 - 5 - 2 - 9)
    for j, m in enumerate(ms):
        p = m.get("pct")
        p = p if isinstance(p, (int, float)) else (m.get("tokens") or 0) / tot * 100
        fill, track = meter(p / 100.0, max(0, mb))
        bar = [sg("  "), sg(fill, cp(C_MUTE)), sg(track, cp(C_LINE))] if mb >= 4 else []
        mix.append(ln(_label("Models" if j == 0 else ""),
                      sg("●", cp(tier_color(m.get("model"))) | B),
                      _val(f" {model_name(m.get('model')):<7}", bold=False),
                      sg(f"{p:>4.0f}%", cp(C_TITLE) | B), *bar,
                      _dim(f"  {fmt_cost(m.get('cost')):>7}"), prio=600 - j * 0.01))
    full = tiles + ([BLANK] + mix if mix else []) + ([BLANK] + week if week else [])
    return Panel("USAGE", [full, tiles + mix, tiles + mix[:1], tiles, tiles[:1]],
                 summary=[_dim("today "), _val(fmt_cost(today.get("cost"))),
                          _dim("  ·  week "), _val(fmt_cost(wk.get("cost")))],
                 right=[_dim("local estimate · API prices")], act="usage", least=1)


def _weekday(day, n):
    try:
        wd = time.strptime(str(day), "%Y-%m-%d").tm_wday
    except (ValueError, TypeError):
        return "?"
    name = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")[wd]
    return name if n >= 4 else name[:2]


def p_limits(V, iw):
    """WHERE YOUR LIMIT GOES — Claude's own tips as ranked thin bars, then the
    top subagents / skills / MCP servers, with Claude's caveat."""
    plan = V.plan
    if V.gate or not plan.get("ok"):
        return None                        # never stale numbers
    wins = plan.get("windows") if isinstance(plan.get("windows"), dict) else {}
    wkey = "7d" if isinstance(wins.get("7d"), dict) and (
        wins["7d"].get("tips") or wins["7d"].get("top")) else "24h"
    wsel = wins.get(wkey) if isinstance(wins.get(wkey), dict) else {}
    tips = sorted((t for t in (wsel.get("tips") or [])
                   if isinstance(t, dict) and t.get("text")),
                  key=lambda t: -(t.get("pct") or 0))
    top = wsel.get("top") if isinstance(wsel.get("top"), dict) else {}
    lines = []
    for j, t in enumerate(tips[:6]):
        p = int(t.get("pct") or 0)
        fill, track = meter(p / 100.0, 10)
        segs = [sg(f"{p:>3}%", cp(C_TITLE) | B), sg("  "), sg(fill, cp(C_TITLE)),
                sg(track, cp(C_LINE)), sg("  " + str(t["text"]), cp(C_TITLE))]
        if t.get("hint"):
            segs.append(_dim("  · " + str(t["hint"])))
        lines.append(ln(*segs, prio=800 - j))
    nw = max(8, min(iw - LABW - 2 - 8 - 6, max(
        [tw(clean(str(x.get("name")))) for k in ("subagents", "skills", "mcp_servers")
         for x in (top.get(k) or []) if isinstance(x, dict)] or [8])))
    for c, (key, lab) in enumerate((("subagents", "Subagents"), ("skills", "Skills"),
                                    ("mcp_servers", "MCP"))):
        items = sorted((x for x in (top.get(key) or [])
                        if isinstance(x, dict) and x.get("name")),
                       key=lambda x: -(x.get("pct") or 0))[:5]
        if items and lines:
            lines.append(BLANK)
        for m, x in enumerate(items):
            p = int(x.get("pct") or 0)
            fill, track = meter(p / 100.0, 8)
            lines.append(ln(_label(lab if m == 0 else ""),
                            sg(pad(str(x["name"]), nw), cp(C_TITLE)), sg("  "),
                            sg(fill, cp(C_MUTE)), sg(track, cp(C_LINE)),
                            _dim(f"{p:>5}%"), prio=500 - c * 10 - m))
    if not lines:
        return None
    lines.append(ln(sg("approximate · this machine only · shares overlap",
                       cp(C_LINE)), prio=2))
    return Panel("WHERE YOUR LIMIT GOES", [lines],
                 right=[_dim("last 7 days" if wkey == "7d" else "last 24h")],
                 act="usage", least=min(3, len(lines)),
                 summary=[_dim(f"{len(tips)} tips")])


def p_system(V, iw):
    """The machine-side details GUARD sums up: where you are, the proxy, the
    keep-awake policy, Desktop, the daemon."""
    loc, g = V.loc, V.g
    rows = []

    def row(lab, segs, act=None, prio=500):
        rows.append(ln(_label(lab), *segs, act=act, prio=prio - len(rows)))

    cc = loc.get("country_cc")
    if loc.get("status") in ("OK", "CACHED"):
        it = loc.get("in_target")
        row("Country", [_val(f"{cname(cc)} ({cc or '—'})", bold=False), sg("  ")]
            + ([_dot(C_GOOD), _dim(" in target")] if it else
               [sg("outside target", cp(C_WARN) | B)]), "recheck")
        place = ", ".join(str(x) for x in (loc.get("city"), loc.get("region")) if x)
        if place:
            row("Place", [_val(place, bold=False)], "recheck")
        if loc.get("ip"):
            row("IP", [_val(str(loc["ip"]), bold=False)], "recheck")
        if loc.get("isp"):
            row("ISP", [_dim(str(loc["isp"]))], "recheck")
    port = g.get("proxy_port", "?")
    row("Proxy", [_val(f":{port}", bold=False),
                  sg("  up", cp(C_DIM)) if g.get("proxy_up") else
                  sg("  down", cp(C_BAD) | B)])
    row("Scope", [_dim("all traffic" if g.get("block_all") else "Claude only")], "scope")
    mode = {"idle": "lid open", "clamshell": "lid closed ok"}.get(V.kmode, "off")
    row("Awake", [_val(mode, bold=False), _dim("  " + keepawake_line(
        V.kmode if V.kon else "off", V.ka))], "keepawake")
    d = V.desk
    if d.get("installed"):
        row("Desktop", [sg("running unguarded", cp(C_WARN) | B) if V.desk_gap else
                        _val("guarded", bold=False) if d.get("running") else
                        _dim("not running")], "desktop")
    return Panel("SYSTEM", [rows], least=min(3, len(rows)),
                 summary=[_dim(f":{port}  ·  {mode}")])


TIMELINE_LOOK = {"working": ("●", C_TITLE, "working"), "done": ("✓", C_GOOD, "done"),
                 "failed": ("✗", C_BAD, "failed"),
                 "pending_tool": ("!", C_WARN, "needs approval"),
                 "asking": ("?", C_WARN, "has a question"),
                 "waiting_input": ("›", C_DIM, "waiting for you"),
                 "idle": ("◌", C_DIM, "idle"), "gone": ("◌", C_DIM, "gone"),
                 "paused": ("⏸", C_DIM, "paused")}


def p_timeline(V, iw):
    """Agent state changes, newest first — what happened while you looked away."""
    ag = V.raw.get("agents") if isinstance(V.raw.get("agents"), dict) else {}
    evs = [e for e in (ag.get("events") or []) if isinstance(e, dict)]
    if not evs:
        return None
    names = {x.get("session_id"): _name(x) for x in (ag.get("sessions") or [])
             if isinstance(x, dict)}
    nw = min(16, max(tw(clean(n)) for n in list(names.values()) + ["agent"]))
    lines = []
    for i, e in enumerate(sorted(evs, key=lambda e: -(e.get("t") or 0))):
        mark, col, word = TIMELINE_LOOK.get(e.get("to"), ("·", C_DIM, str(e.get("to"))))
        t = e.get("t")
        hhmm = time.strftime("%H:%M", time.localtime(t)) if isinstance(t, (int, float)) else "     "
        sid = e.get("session_id")
        lines.append(ln(_dim(hhmm + "  "), sg(mark, cp(col) | B), sg("  "),
                        sg(pad(names.get(sid) or str(sid or "?")[:8], nw), cp(C_TITLE)),
                        sg("  " + word, cp(col) if col in (C_WARN, C_BAD) else cp(C_DIM)),
                        right=[_dim(ago(t) + " ago")] if ago(t) else (),
                        act=("focus", sid) if sid in names else None,
                        prio=100 - i * 0.01))
    return Panel("TIMELINE", [lines], least=min(2, len(lines)),
                 summary=[_dim(f"{len(lines)} events")],
                 more=(0, lambda n: ln(_dim(f"+{n} earlier"), prio=0)))


# The layouts. Visual order is fixed per column (it encodes attention); the
# number is the priority that decides who gets rows when the screen is short.
# Small and medium screens stay calm (four panels); big ones add panels that
# genuinely get richer with room, each class a superset of the last.
LAYOUTS = {
    "compact": (((p_guard, 100), (p_agents, 95), (p_plan, 80), (p_net, 70)),),
    "regular": (((p_guard, 100), (p_agents, 95)),
                ((p_plan, 90), (p_net, 80))),
    "tall": (((p_guard, 100), (p_agents, 95), (p_timeline, 20)),
             ((p_plan, 90), (p_net, 80), (p_requests, 40))),
    # Big grids: the anchors stay put (attention order), and the extra panels
    # go, in order, to whichever flexible column is shortest — so the columns
    # come out balanced instead of one tall column beside empty ones.
    "wide": (((p_guard, 100), (p_agents, 95)),
             ((p_plan, 90),),
             ((p_net, 85), (p_requests, 40))),
    "xwide": (((p_guard, 100), (p_agents, 95)),
              ((p_plan, 90),),
              ((p_usage, 60),),
              ((p_net, 85), (p_requests, 40))),
}
EXTRAS = {"wide": (((p_usage, 60), (p_limits, 50), (p_timeline, 20)), (0, 1)),
          "xwide": (((p_limits, 50), (p_system, 45), (p_timeline, 20)), (0, 1, 2))}
SPLITS = {"wide": (0.44, 0.28, 0.28), "xwide": (0.31, 0.23, 0.22, 0.24)}
MAX_W = 260          # past this, the dashboard centers instead of sprawling

# Footer key hints: (key, label, priority) — shown in this order, as many as
# fit, most important first.
HINTS = (("⏎", "actions", 100), ("r", "route", 70), ("e", "enforce", 60),
         ("c", "country", 65), ("w", "awake", 45), ("u", "usage", 55),
         ("k", "re-check", 40), ("?", "help", 90), ("q", "quit", 95),
         ("Q", "stop guard", 20))


def size_class(h, w):
    """tiny · compact · regular (calm) → tall · wide · xwide (dense): each
    dense class keeps everything the calm one shows and adds what genuinely
    gets richer with room."""
    if w < 60 or h < 16:
        return "tiny"
    if w < 100:
        return "compact"
    if w < 180 or h < 30:
        return "tall" if w >= 140 and h >= 40 else "regular"
    return "wide" if w < 230 else "xwide"


def header(fr, V, x0, W):
    """Row 0: radar · TOWER · verdict on the left; the counts that ask for you
    and a clock on the right. Chips drop, least important first."""
    # A held request outranks a green verdict: amber, one loudest thing.
    lc = C_WARN if V.pending and V.color == C_GOOD else V.color
    left = [sg(V.radar, cp(V.rcolor) | B, V.rfx), sg("  "),
            sg("TOWER", cp(C_DIM) | B), _dim("   ")]
    # While a Claude request is held/retrying on the guard, the verdict
    # shimmers "Reconnecting Claude…" — clears the instant the guard passes.
    if V.pending:
        left.append(sg("Reconnecting Claude…", cp(lc) | B, ("shimmer", lc)))
    else:
        left.append(sg(V.label, cp(lc) | B))
    chips = []                           # (priority, segs), in display order
    A = V.ag
    if A:
        if A.need:
            chips.append((90, [sg(f"! {len(A.need)} need{'s' if len(A.need) == 1 else ''} you",
                                  cp(C_WARN) | B)]))
        if A.working_n:
            chips.append((60, [_dot(C_GOOD), _val(f" {A.working_n}", bold=True),
                               _dim(" working")]))
    if V.held:
        chips.append((30, [_dim("awake")]))
    chips.append((50, [_dim(time.strftime("%H:%M"))]))
    avail = W - 4

    def total():
        rw = sum(_segw(c[1]) for c in chips) + 4 * max(0, len(chips) - 1)
        return _segw(left) + (3 + rw if chips else 0)

    while total() > avail and chips:
        low = [c for c in chips if c[0] < 90]
        chips.remove(min(low, key=lambda c: c[0]) if low else chips[-1])
    x = put_segs(fr, 0, x0 + 2, avail, left)
    if chips:
        segs = []
        for c in chips:
            if segs:
                segs.append(sg("    "))
            segs += c[1]
        rw = _segw(segs)
        if x0 + W - 2 - rw > x:
            put_segs(fr, 0, x0 + W - 2 - rw, rw, segs)


def footer(fr, x0, W):
    y = fr.h - 1
    avail = W - 4
    items = [(U("⏎", "Enter") if k == "⏎" else k, lab, pr) for k, lab, pr in HINTS]
    chosen, used = set(), 0
    for i in sorted(range(len(items)), key=lambda i: -items[i][2]):
        k, lab, _ = items[i]
        cw = tw(k) + 1 + len(lab) + (3 if chosen else 0)
        if used + cw <= avail:
            chosen.add(i)
            used += cw
    segs = []
    for i in sorted(chosen):
        k, lab, _ = items[i]
        if segs:
            segs.append(sg("   "))
        segs += [_dim(k), sg(" " + lab, cp(C_LINE))]
    put_segs(fr, y, x0 + 2, avail, segs)
    fr.hit(y, 0, fr.w - 1, "menu", 2)    # click the footer → actions menu


def tiny_lines(V):
    """The status card, most important first by priority."""
    vc = C_WARN if V.pending and V.color == C_GOOD else V.color
    L = [ln(sg(V.radar, cp(V.rcolor) | B, V.rfx), sg("  "),
            sg("Reconnecting Claude…" if V.pending else V.label, cp(vc) | B,
               ("shimmer", vc) if V.pending else None),
            right=[_dim(V.target if len(V.target) <= 14 else (V.cc or ""),
                        act="country")], prio=1000)]
    if V.explain:
        L.append(ln(_dim(V.explain), prio=320))
    if V.desk_gap:
        L.append(ln(sg("Desktop running unguarded", cp(C_WARN) | B),
                    right=[_dim("d")], act="desktop", prio=960))
    A = V.ag
    if A:
        for i, row in enumerate(A.need[:2]):
            L.append(_agent_line(V, row, "need", 880 - i, min(14, tw(_name(row[1]))), 0))
        segs = ([sg(f"{len(A.need)} need you", cp(C_WARN) | B), _dim("  ·  ")]
                if A.need else [])
        segs += [_val(str(A.working_n)), _dim(" working")]
        if not A.need:
            segs.append(_dim("  ·  nothing needs you"))
        L.append(ln(*segs, prio=850))
    if V.gate:
        L.append(ln(sg(V.gate[0], cp(C_WARN) | B), prio=700))
    elif V.plan.get("ok"):
        segs = []
        for label, key in PLAN_ROWS[:2]:
            node = V.plan.get(key)
            if isinstance(node, dict) and isinstance(node.get("pct"), (int, float)):
                p = int(node["pct"])
                if segs:
                    segs.append(_dim("  ·  "))
                segs += [sg(label + " ", cp(C_TITLE)), sg(f"{p}%", cp(pcolor(p)) | B)]
                if key == "session" and reset_short(node):
                    segs.append(_dim(" " + reset_short(node)))
        if segs:
            L.append(ln(*segs, prio=700))
    if V.has_net:
        L.append(ln(*net_status(V, short=True), prio=650))
    if V.loc.get("status") == "OK":
        place = V.loc.get("city") or cname(V.loc.get("country_cc"))
        if V.loc.get("in_target"):
            L.append(ln(_dim(f"in {place}"), prio=400))
        else:
            L.append(ln(sg(f"outside {V.target}", cp(C_WARN) | B),
                        _dim(f"  {place}"), prio=750))
    return L


def layout_tiny(fr, V):
    h, w = fr.h, fr.w
    lines = tiny_lines(V)
    enter = U("⏎", "Enter")
    hints = [_dim(enter), sg(" menu   ", cp(C_LINE)), _dim("?"),
             sg(" help   ", cp(C_LINE)), _dim("q"), sg(" quit", cp(C_LINE))]
    if w >= 24 and h >= 5:
        cw = min(w - 2, 64)
        rows = min(h - 2, len(lines))
        p = Panel("TOWER", [lines], act="menu",
                  right=[_dim(time.strftime("%H:%M"))], foot=hints)
        draw_panel(fr, 0, 1, rows + 2, cw, p)
    else:
        n = h - 1 if h >= 3 else h
        for i, line in enumerate(fit_lines(lines, n)):
            put_line(fr, i, 0, w - 1, line)
        if h >= 3:
            put_segs(fr, h - 1, 0, w - 1, hints)
        for y in range(h):
            fr.hit(y, 0, w - 1, "menu", 2)


def compose(s, h, w, now):
    fr = Frame(h, w)
    V = view(s, now)
    cls = size_class(h, w)
    if cls == "tiny":
        layout_tiny(fr, V)
        return fr
    V.dense = cls in ("tall", "wide", "xwide")
    W = min(w - 2, MAX_W)
    x0 = (w - W) // 2
    header(fr, V, x0, W)
    footer(fr, x0, W)
    roomy = h >= 30                       # a breath under the header / over the footer
    top = 2 if roomy else 1
    H = h - top - (2 if roomy else 1)
    specs = LAYOUTS[cls]
    if cls == "compact":
        widths = [W]
    elif cls in ("regular", "tall"):
        rw = min(72, max(46, int(W * 0.40)))
        widths = [W - rw - 2, rw]
    else:
        avail = W - 2 * (len(specs) - 1)
        widths = [int(avail * f) for f in SPLITS[cls][:-1]]
        widths.append(avail - sum(widths))
    cols = []
    for cw, spec in zip(widths, specs):
        panels = []
        for fn, prio in spec:
            p = fn(V, cw - 4)
            if p:
                p.prio = prio
                panels.append(p)
        cols.append(panels)
    if cls in EXTRAS:
        extras, flex = EXTRAS[cls]

        def natural(ps):                  # a column's height at full content
            return sum(min(p.full() + 2, H) for p in ps) + max(0, len(ps) - 1)
        for fn, prio in extras:
            c = min(flex, key=lambda i: (natural(cols[i]), i))
            p = fn(V, widths[c] - 4)
            if p:
                p.prio = prio
                cols[c].append(p)
    x = x0
    for cw, panels in zip(widths, cols):
        column(fr, panels, top, x, cw, H, gap=1 if V.dense else None)
        x += cw + 2
    return fr


_frame = [None, None]     # [key, Frame] — one composed screen, replayed


def draw(win, s):
    h, w = win.getmaxyx()
    now = time.time()
    key = (id(s), s.get("ts"), h, w, int(now))
    if _frame[0] != key:
        try:
            fr = compose(s, h, w, now)
        except Exception as e:           # never let odd state take the TUI down
            fr = Frame(h, w)
            put_segs(fr, 0, 1, w - 2, [sg("TOWER", B), _dim("  render error — "),
                                       sg(f"{type(e).__name__}: {e}", cp(C_WARN))])
            put_segs(fr, max(0, h - 1), 1, w - 2,
                     [_dim("press Enter for the actions menu · q to quit")])
            fr.hit(max(0, h - 1), 0, w - 1, "menu", 2)
        _frame[0], _frame[1] = key, fr
    blit(win, _frame[1])


def frame_live():
    """Does the frame on screen animate (shimmer / spin)? Then repaint each tick."""
    return bool(MOTION and _frame[1] is not None and _frame[1].live)


# --------------------------------------------------------------------------- #
# Confirmations
# --------------------------------------------------------------------------- #
def safe_addstr(win, y, x, text, attr=0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x < 0 or x >= w:
        return
    text = clip(clean(text), w - x - 1, ell=False)
    if text:
        _add(win, y, x, text, attr)


def _restore_tick(win):
    """Back to the dashboard's input cadence. (nodelay(True) alone would leave
    getch non-blocking and spin the idle loop at full CPU.)"""
    win.nodelay(True)
    win.timeout(TICK_MS)


def _alert(win, title, body, prompt, color):
    """A centered alert: every word of the warning wrapped, never cut off; on a
    screen too small for a box, the same words bottom-anchored, prompt last."""
    h, w = win.getmaxyx()
    bw = min(72, w - 2)
    inner = bw - 6
    if inner >= 20:
        lines = []
        for j, para in enumerate(body):
            for t in textwrap.wrap(para, inner) or [""]:
                lines.append((t, j))
            if j < len(body) - 1:
                lines.append(("", j))
        bh = len(lines) + 5
        if bh <= h:
            by, bx = (h - bh) // 2, (w - bw) // 2
            draw_box(win, by, bx, bh, bw, title, color)
            for i, (t, j) in enumerate(lines):
                safe_addstr(win, by + 2 + i, bx + 3, t,
                            cp(color) | B if j == 0 else cp(C_TITLE))
            safe_addstr(win, by + bh - 2, bx + 3, prompt, cp(color) | B)
            win.noutrefresh()
            curses.doupdate()
            return
    if tw(prompt) > w - 2:
        prompt = "[y/N]"                  # the answer keys always stay visible
    lines = textwrap.wrap(" ".join(body), max(8, w - 2)) + [prompt]
    lines = lines[-h:]
    y0 = h - len(lines)
    for i, t in enumerate(lines):
        safe_addstr(win, y0 + i, 0, " " * w)
        safe_addstr(win, y0 + i, 1, t, cp(color) | B)
    win.noutrefresh()
    curses.doupdate()


def confirm(win, msg):
    win.nodelay(False)
    try:
        _alert(win, "CONFIRM", [msg], "y  yes      any other key  cancel", C_WARN)
        return win.getch() in (ord("y"), ord("Y"))
    finally:
        _restore_tick(win)


def _agents_working(s):
    sessions = ((s.get("agents") or {}).get("sessions")) or []
    return sum(1 for a in sessions
               if a.get("status") == "working" and not a.get("dismissed"))


def _pinned_note(s):
    """Extra warning for STOP/QUIT: live sessions reaching the API through the
    proxy (regardless of routing intent — matches the app's proxyPinnedCount).
    On stop the daemon keeps their port open as an unguarded pass-through until
    they exit, so they keep working, but with no guard."""
    n = sum(1 for r in (s.get("agents") or {}).get("sessions") or []
            if r.get("guarded") is True and r.get("pid")
            and r.get("kind") != "infra" and r.get("status") != "gone")
    if not n:
        return ""
    return (f" {n} open chat{'s' if n != 1 else ''} route through Tower — they "
            "keep working, but go DIRECT with no guard until you reopen it.")


def danger_confirm(win, s, headline, detail):
    """Two-step confirmation for anything that lets Claude reach the API
    WITHOUT the guard (route off, enforce off, stop+quit). Wording escalates
    when agents are working right now. Returns True ONLY if the user confirms
    BOTH steps — a single keypress can never disable protection."""
    n = _agents_working(s)
    warn = (f"⚠ {n} agent{'s' if n != 1 else ''} working NOW — "
            "they'll send UNGUARDED requests." if n else "")
    win.nodelay(False)
    try:
        _alert(win, "⚠ DANGER", ["⚠ " + headline] + ([warn] if warn else []),
               "y  continue      any other key  cancel", C_BAD)
        if win.getch() not in (ord("y"), ord("Y")):
            return False
        _alert(win, "⚠ ARE YOU SURE?", ["⚠ Are you SURE? " + detail]
               + ([warn] if warn else []),
               "press Y again to confirm · any other key cancels", C_BAD)
        return win.getch() in (ord("y"), ord("Y"))
    finally:
        _restore_tick(win)


def toggle_route(win, s):
    """Route on = safe (one keypress). Route OFF drops the guard entirely →
    double-confirm."""
    routed = bool((s.get("routing") or {}).get("installed"))
    if routed and not danger_confirm(
            win, s, "Turn OFF the guard? Claude connects DIRECTLY, unguarded.",
            "This removes routing from settings.json — no country guard at all."):
        return
    send({"cmd": "route", "on": not routed})


def toggle_enforce(win, s):
    """Enforce on = safe. Enforce OFF stops blocking off-country requests →
    double-confirm."""
    enforce = (s.get("guard") or {}).get("enforce", True)
    if enforce and not danger_confirm(
            win, s, "Stop ENFORCING? Off-country requests will NOT be blocked.",
            "Claude still routes through the guard but is no longer blocked."):
        return
    send({"cmd": "enforce", "on": not enforce})


# --------------------------------------------------------------------------- #
# Modal + onboarding
# --------------------------------------------------------------------------- #
def draw_box(win, y, x, h, w, title="", color=None):
    if h < 2 or w < 4:
        return
    line = cp(color) if color else cp(C_LINE)
    for r in range(h):
        safe_addstr(win, y + r, x, " " * w)
    safe_addstr(win, y, x, "╭" + "─" * (w - 2) + "╮", line)
    safe_addstr(win, y + h - 1, x, "╰" + "─" * (w - 2) + "╯", line)
    for r in range(1, h - 1):
        safe_addstr(win, y + r, x, "│", line)
        safe_addstr(win, y + r, x + w - 1, "│", line)
    if title:
        safe_addstr(win, y, x + 2, (" " + title + " ")[:max(0, w - 4)],
                    cp(color or C_TITLE) | B)


def country_modal(win, current_cc):
    """Centered, scrollable, type-to-filter country picker. Returns cc or None.
    Fits any window; scrolls when the list is taller than the terminal."""
    query = ""
    idx = next((i for i, (c, _) in enumerate(COUNTRY_LIST) if c == current_cc), 0)
    win.nodelay(False)
    win.timeout(-1)
    try:
        while True:
            h, w = win.getmaxyx()
            q = query.lower()
            fl = [t for t in COUNTRY_LIST
                  if not q or t[1].lower().startswith(q) or t[0].lower() == q]
            if not fl:
                fl = COUNTRY_LIST
            idx = max(0, min(idx, len(fl) - 1))
            bw = min(max(38, len(query) + 22), w - 2)
            rows = max(3, min(len(fl), h - 9))
            bh = rows + 6
            by = max(0, (h - bh) // 2)
            bx = max(0, (w - bw) // 2)
            draw_box(win, by, bx, bh, bw, "PIN A COUNTRY")
            prompt = ("filter: " + query) if query else "filter: (type a name)"
            safe_addstr(win, by + 1, bx + 2, prompt[:bw - 4], cp(C_DIM))
            top = max(0, min(idx - rows // 2, max(0, len(fl) - rows)))
            for r in range(rows):
                li = top + r
                yy = by + 3 + r
                if li >= len(fl):
                    safe_addstr(win, yy, bx + 2, " " * (bw - 4))
                    continue
                c, n = fl[li]
                label = f"{n} ({c})"
                if li == idx:
                    safe_addstr(win, yy, bx + 2,
                                ("› " + label).ljust(bw - 4)[:bw - 4],
                                cp(C_TITLE) | curses.A_REVERSE | B)
                else:
                    mark = "• " if c == current_cc else "  "
                    safe_addstr(win, yy, bx + 2, (mark + label)[:bw - 4],
                                cp(C_TITLE) | (B if c == current_cc else 0))
            safe_addstr(win, by + bh - 2, bx + 2,
                        "↑/↓ move · Enter pin · Esc cancel"[:bw - 4], cp(C_DIM))
            win.noutrefresh()
            curses.doupdate()
            ch = win.getch()
            if ch == 27:                                   # Esc
                return None
            if ch == curses.KEY_MOUSE:
                try:
                    _, mx, my, _, bs = curses.getmouse()
                except curses.error:
                    continue
                if bs & MOUSE_WHEEL_UP:
                    idx -= 1
                elif bs & MOUSE_WHEEL_DOWN:
                    idx += 1
                elif bs & MOUSE_B1:                        # click a row → pin
                    r = my - (by + 3)
                    if 0 <= r < rows and top + r < len(fl) \
                            and bx + 1 <= mx <= bx + bw - 2:
                        return fl[top + r][0]
            elif ch in (curses.KEY_UP, ord("k")):
                idx -= 1
            elif ch in (curses.KEY_DOWN, ord("j")):
                idx += 1
            elif ch in (curses.KEY_ENTER, 10, 13):
                return fl[idx][0] if fl else None
            elif ch in (curses.KEY_BACKSPACE, 127, 8):
                query = query[:-1]
                idx = 0
            elif 32 <= ch < 127:
                query += chr(ch)
                idx = 0
    finally:
        win.nodelay(True)
        win.timeout(TICK_MS)


# Accurate 5-row block letters, composed programmatically so they're legible.
_GLYPH = {
    "C": [" ████ ", "██    ", "██    ", "██    ", " ████ "],
    "L": ["██    ", "██    ", "██    ", "██    ", "██████"],
    "G": [" ████ ", "██    ", "██ ███", "██   █", " ████ "],
    "E": ["██████", "██    ", "█████ ", "██    ", "██████"],
    "O": [" ████ ", "██  ██", "██  ██", "██  ██", " ████ "],
    "U": ["██  ██", "██  ██", "██  ██", "██  ██", " ████ "],
    "A": [" ████ ", "██  ██", "██████", "██  ██", "██  ██"],
    "R": ["█████ ", "██  ██", "█████ ", "██ ██ ", "██  ██"],
    "D": ["█████ ", "██  ██", "██  ██", "██  ██", "█████ "],
    " ": ["   ", "   ", "   ", "   ", "   "],
}


def _make_banner(text):
    rows = ["", "", "", "", ""]
    for ch in text:
        g = _GLYPH.get(ch, _GLYPH[" "])
        for i in range(5):
            rows[i] += g[i] + " "
    return [r.rstrip() for r in rows]


BANNER = _make_banner("TOWER")


def onboarding(win):
    """First-run: ASCII banner, the command to reopen the TUI, and a country
    pin step. Responsive — degrades gracefully on small terminals."""
    st0 = read_state() or {}
    picked = (st0.get("guard") or {}).get("target_cc")   # remembered target
    bw = len(BANNER[0])
    while True:
        h, w = win.getmaxyx()
        win.erase()
        y = max(0, (h - 16) // 2)
        if w >= bw + 4:
            for i, line in enumerate(BANNER):
                safe_addstr(win, y + i, max(2, (w - bw) // 2),
                            line, cp(C_TITLE) | B)
            y += len(BANNER) + 1
        else:
            safe_addstr(win, y, max(2, (w - 6) // 2), "TOWER",
                        cp(C_TITLE) | B)
            y += 2

        def center(text, attr):
            safe_addstr(win, center.y, max(2, (w - len(text)) // 2), text, attr)
            center.y += 1
        center.y = y
        center("Pin Claude Code to a country · watch usage · keep long agents alive",
               cp(C_DIM))
        center.y += 1
        center("Open this dashboard anytime with:", cp(C_TITLE))
        # Prefer the one word when it really is on PATH — the .deb always
        # installs it. The python3 invocation stays as the fallback because it
        # always works.
        # Linux only: macOS keeps its exact wording, and an unrelated `tower`
        # on a Mac's PATH must never be advertised as this dashboard.
        cmd = ("tower" if sys.platform.startswith("linux") and shutil.which("tower")
               else f'python3 "{SELF}"')
        center(cmd if len(cmd) < w - 4 else "python3 …/tower-tui.py",
               cp(C_TITLE) | B)
        center.y += 1
        routed = bool(((read_state() or {}).get("routing") or {}).get("installed"))
        center(f"Target country:  {cname(picked) if picked else 'not set'}",
               cp(C_TITLE) | B if picked else cp(C_WARN))
        center(f"Route Claude through the guard:  {'yes' if routed else 'no'}",
               cp(C_TITLE) | B if routed else cp(C_DIM))
        center.y += 1
        center("When ON, every `claude` run goes through the guard automatically.",
               cp(C_DIM))
        center("When OFF, Claude connects directly. Change it anytime in the menu.",
               cp(C_DIM))
        center.y += 1
        center("[p] pick country    [r] routing on/off    [Enter] open dashboard",
               cp(C_TITLE))
        center("[q] quit", cp(C_DIM))
        win.noutrefresh()
        curses.doupdate()
        ch = win.getch()
        if ch in (ord("q"),):
            return "quit"
        if ch in (ord("p"), ord("c")):
            sel = country_modal(win, picked or "US")
            if sel:
                picked = sel
                send({"cmd": "country", "cc": sel})
                _mark_seen()          # remember: go straight to dashboard next time
        elif ch in (ord("r"),):
            if picked:
                send({"cmd": "country", "cc": picked})
            toggle_route(win, read_state() or {})   # guarded off-direction
            _mark_seen()
        elif ch in (curses.KEY_ENTER, 10, 13):
            return "done"


def _mark_seen():
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        open(SEEN_FLAG, "w").close()
    except OSError:
        pass


HELP = [
    ("r", "Route Claude through the guard — on / off"),
    ("e", "Enforce — block Claude when you're outside your country"),
    ("a", "Scope — block ALL traffic, or Claude only"),
    ("c / p", "Country — open the picker to choose & pin a country"),
    ("w", "Keep awake — cycle off → lid-open → lid-closed"),
    ("d", "Claude Desktop — open (or relaunch) through the guard"),
    ("u / $", "Usage — plan detail, where the limit goes, local cost"),
    ("k", "Re-check your location right now"),
    ("?", "Show this help"),
    ("q", "Quit the dashboard — the guard keeps running"),
    ("Q", "Stop the guard & restore Claude to a direct connection"),
    ("plan", "PLAN — click to refresh the real limits (runs Claude's /usage)"),
    ("net", "NETWORK — your internet vs Anthropic's API; click → speed test"),
    ("agents", f"AGENTS — Claude agents on this {DEVICE}; click → its terminal"),
    ("mouse", "Click rows/panels to act; wheel scrolls lists"),
]


def help_modal(win):
    """Centered, self-explaining key reference. Any key closes it."""
    win.nodelay(False)
    win.timeout(-1)
    try:
        h, w = win.getmaxyx()
        bw = min(80, w - 2)
        bh = min(len(HELP) + 5, h - 2)
        by = max(0, (h - bh) // 2)
        bx = max(0, (w - bw) // 2)
        draw_box(win, by, bx, bh, bw, "HELP · WHAT EACH KEY DOES")
        for r, (key, desc) in enumerate(HELP):
            yy = by + 2 + r
            if yy >= by + bh - 2:
                break
            safe_addstr(win, yy, bx + 3, f"{key:<7}", cp(C_TITLE) | B)
            safe_addstr(win, yy, bx + 11, desc[:bw - 13], cp(C_TITLE))
        safe_addstr(win, by + bh - 2, bx + 3, "press any key to close", cp(C_DIM))
        win.noutrefresh()
        curses.doupdate()
        win.getch()
    finally:
        win.nodelay(True)
        win.timeout(TICK_MS)


def _section(t, right=()):
    return ln(sg(t, cp(C_DIM)), right=right, prio=500)


def usage_lines(s, iw):
    """The Usage view (`u`): everything the main screen leaves out, in the
    same monochrome grammar — plan detail, where the limit goes, and the
    local estimate. Never your plan % in the estimate, never numbers while
    the guard isn't passing."""
    V = view(s, time.time())
    plan, u = V.plan, V.u
    out = []
    upd = ("updating…" if plan.get("refreshing") else
           f"updated {ago(plan.get('updated'))} ago" if plan.get("updated") else "")
    out.append(_section("PLAN LIMITS", right=[_dim(upd)] if upd else ()))
    wins = plan.get("windows") if isinstance(plan.get("windows"), dict) else {}
    if V.gate:
        out += gate_lines(V, iw, spacious=False)
    elif plan.get("disabled"):
        out.append(ln(_dim("Live limits are off — turn them on in the menu")))
    elif not plan.get("ok"):
        out.append(ln(sg("unavailable — " + str(plan.get("error")), cp(C_WARN))
                      if plan.get("error") else _dim("fetching from Claude /usage…")))
    else:
        out += plan_meters(plan, iw)
        parts = []
        for key, lab in (("24h", "last 24h"), ("7d", "last 7 days")):
            wd = wins.get(key)
            if isinstance(wd, dict) and wd.get("requests") is not None:
                parts.append((lab, wd.get("requests"), wd.get("sessions")))
        l24 = plan.get("last24h")
        if not parts and isinstance(l24, dict) and l24.get("requests") is not None:
            parts.append(("last 24h", l24.get("requests"), l24.get("sessions")))
        for j, (lab, req, ses) in enumerate(parts):
            out.append(ln(_label("Requests" if j == 0 else ""),
                          _val(f"{fmt_tok(req):>6}"), _dim(" requests  ·  "),
                          _val(str(ses if ses is not None else "—")),
                          _dim(f" sessions  ·  {lab}")))

    # ---- where the limit goes: Claude's own tips + top consumers ---- #
    if not V.gate and plan.get("ok"):
        wkey = "7d" if isinstance(wins.get("7d"), dict) and (
            wins["7d"].get("tips") or wins["7d"].get("top")) else "24h"
        wsel = wins.get(wkey) if isinstance(wins.get(wkey), dict) else {}
        tips = sorted((t for t in (wsel.get("tips") or [])
                       if isinstance(t, dict) and t.get("text")),
                      key=lambda t: -(t.get("pct") or 0))
        top = wsel.get("top") if isinstance(wsel.get("top"), dict) else {}
        cats = []
        for key, lab in (("subagents", "Subagents"), ("skills", "Skills"),
                         ("mcp_servers", "MCP")):
            items = [x for x in (top.get(key) or [])
                     if isinstance(x, dict) and x.get("name")]
            if items:
                cats.append((lab, sorted(items, key=lambda x: -(x.get("pct") or 0))))
        if tips or cats:
            out += [BLANK, _section(
                "WHERE YOUR LIMIT GOES · " + ("last 7 days" if wkey == "7d"
                                              else "last 24h"),
                right=[_dim("approximate · this machine · shares overlap")])]
            for t in tips[:5]:
                p = int(t.get("pct") or 0)
                fill, track = meter(p / 100.0, 12)
                segs = [sg(f"{p:>3}%", cp(C_TITLE) | B), sg("  "),
                        sg(fill, cp(C_TITLE)), sg(track, cp(C_LINE)),
                        sg("  " + str(t["text"]), cp(C_TITLE))]
                if t.get("hint"):
                    segs.append(_dim("  · " + str(t["hint"])))
                out.append(ln(*segs))
            for lab, items in cats:
                segs = [_label(lab)]
                for m, x in enumerate(items[:4]):
                    if m:
                        segs.append(_dim("  ·  "))
                    segs += [sg(str(x["name"]) + " ", cp(C_TITLE)),
                             _dim(f"{int(x.get('pct') or 0)}%")]
                out.append(ln(*segs))

    # ---- the local estimate ---- #
    if u:
        sess, today = u.get("session") or {}, u.get("today") or {}
        wk, pace = u.get("week") or {}, u.get("pace") or {}
        out += [BLANK, _section("LOCAL ESTIMATE",
                                right=[_dim("API list prices · not your plan")])]
        for lab, cost, sub in (
                ("Session", fmt_cost(sess.get("cost")),
                 f"{fmt_tok(sess.get('tokens'))} tokens · {sess.get('msgs', 0) or 0} msgs"),
                ("Today", fmt_cost(today.get("cost")),
                 f"{fmt_tok(today.get('tokens'))} tokens"),
                ("Week", fmt_cost(wk.get("cost")), f"{fmt_tok(wk.get('tokens'))} tokens"),
                ("Projected", "~" + fmt_cost(pace.get("projected_week_cost")),
                 f"~{fmt_tok(pace.get('projected_week_tokens'))} tokens / week")):
            out.append(ln(_label(lab), _val(f"{cost:>8}"), _dim("   " + sub)))
        ms = [m for m in (u.get("byModel") or []) if isinstance(m, dict)][:4]
        tot = sum((m.get("tokens") or 0) for m in ms) or 1
        for j, m in enumerate(ms):
            p = m.get("pct")
            p = p if isinstance(p, (int, float)) else (m.get("tokens") or 0) / tot * 100
            fill, track = meter(p / 100.0, 16)
            out.append(ln(_label("By model" if j == 0 else ""),
                          sg(f"{model_name(m.get('model')):<8}", cp(C_TITLE)),
                          sg(f"{p:>4.0f}%", cp(C_TITLE) | B), sg("  "),
                          sg(fill, cp(C_TITLE)), sg(track, cp(C_LINE)),
                          _dim(f"  {fmt_cost(m.get('cost')):>7}  ·  "
                               f"{fmt_tok(m.get('tokens'))} tokens")))
        days = [d for d in (u.get("series") or []) if isinstance(d, dict)][-7:]
        if days:
            costs = [float(d.get("cost") or 0) for d in days]
            out.append(ln(_label("7 days"),
                          sg(" ".join(sparkline(costs)), cp(C_MUTE)),
                          _dim(f"   {fmt_cost(costs[0])} → {fmt_cost(costs[-1])} today")))
        if pace.get("live_tpm") is not None:
            out.append(ln(_label("Pace"), _val(fmt_tok(pace.get("live_tpm"))),
                          _dim(" tok/min now  ·  "),
                          _val(fmt_tok(pace.get("tokens_per_active_hr"))),
                          _dim(" per active hour")))
    return out


def usage_modal(win):
    """The Usage view — a calm, scrollable sheet over the dashboard.
    ↑/↓ (or the wheel) scroll · r refreshes the real limits · any other key
    closes."""
    top = 0
    win.nodelay(False)
    win.timeout(1000)                     # live: re-read state once a second
    try:
        while True:
            s = read_state() or _state_cache[1] or {}
            h, w = win.getmaxyx()
            bw = min(92, w - 2)
            lines = usage_lines(s, bw - 4)
            rows = max(1, min(len(lines), h - 6))
            top = max(0, min(top, len(lines) - rows))
            more = top + rows < len(lines)
            bh = rows + 4                 # border + one row of air top/bottom
            by, bx = max(0, (h - bh) // 2), max(0, (w - bw) // 2)
            foot = [_dim("r refresh   " + ("↑↓ scroll   " if top or more else "")
                         + "any key closes")]
            p = Panel("USAGE", [[BLANK] + lines[top:top + rows] + [BLANK]],
                      foot=foot, right=[_dim(f"{top + 1}–{top + rows} of {len(lines)}")]
                      if top or more else ())
            fr = Frame(h, w)
            draw_panel(fr, by, bx, bh, bw, p)
            draw_box(win, by, bx, bh, bw)          # clears the sheet's area
            for y, x, t, attr, _ in fr.ops:
                _add(win, y, x, t, attr)
            win.noutrefresh()
            curses.doupdate()
            ch = win.getch()
            if ch == -1:
                continue
            if ch == curses.KEY_MOUSE:
                try:
                    _, _, _, _, bs = curses.getmouse()
                except curses.error:
                    continue
                if bs & MOUSE_WHEEL_UP:
                    top -= 1
                    continue
                if bs & MOUSE_WHEEL_DOWN:
                    top += 1
                    continue
                return
            if ch in (curses.KEY_UP, ord("k")):
                top -= 1
            elif ch in (curses.KEY_DOWN, ord("j")):
                top += 1
            elif ch == curses.KEY_PPAGE:
                top -= rows
            elif ch == curses.KEY_NPAGE:
                top += rows
            elif ch in (ord("r"), ord("R")):
                send({"cmd": "refreshplan"})
            elif ch == curses.KEY_RESIZE:
                win.erase()
            else:
                return
    finally:
        win.nodelay(True)
        win.timeout(TICK_MS)


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
KEEPAWAKE_CYCLE = ["off", "idle", "clamshell"]


def procs_modal(win, s):
    """See — and stop — the background processes this app started."""
    win.nodelay(False)
    win.timeout(400)
    try:
        while True:
            s = read_state() or {}
            procs = s.get("procs") or {}
            dpid = procs.get("daemon_pid")
            kpid = procs.get("keepawake_pid")
            h, w = win.getmaxyx()
            bw = min(58, w - 2)
            bh = min(9, h - 2)
            by = max(0, (h - bh) // 2)
            bx = max(0, (w - bw) // 2)
            draw_box(win, by, bx, bh, bw, "BACKGROUND PROCESSES")
            safe_addstr(win, by + 1, bx + 3,
                        "everything this app runs in the background:", cp(C_DIM))
            safe_addstr(win, by + 3, bx + 3, "guard daemon", cp(C_TITLE))
            safe_addstr(win, by + 3, bx + 22,
                        f"PID {dpid} · running" if dpid else "not running",
                        cp(C_TITLE if dpid else C_DIM))
            safe_addstr(win, by + 4, bx + 3, "keep-awake", cp(C_TITLE))
            safe_addstr(win, by + 4, bx + 22,
                        f"PID {kpid} · running" if kpid else "not running",
                        cp(C_TITLE if kpid else C_DIM))
            safe_addstr(win, by + bh - 3, bx + 3,
                        "[s] stop the guard & all of the above", cp(C_WARN))
            safe_addstr(win, by + bh - 2, bx + 3, "any other key — close",
                        cp(C_DIM))
            win.noutrefresh()
            curses.doupdate()
            ch = win.getch()
            if ch == -1:
                continue
            if ch in (ord("s"), ord("S")):
                if danger_confirm(
                        win, s,
                        "Stop the guard and all background processes? Claude "
                        "goes back to a DIRECT, unguarded connection.",
                        "This removes the guard entirely." + _pinned_note(s)):
                    send({"cmd": "quit"})
                    return "stopped"
            return None
    finally:
        win.nodelay(True)
        win.timeout(TICK_MS)


def _desk_val(s):
    d = (s.get("apps") or {}).get("desktop") or {}
    if not d.get("installed"):
        return "not installed"
    if not d.get("running"):
        return ""
    return "guarded" if d.get("guarded") else "UNGUARDED"


def actions_menu(win):
    """The one place actions live — so a stray keypress on the dashboard can't
    change anything. Doubles as the help/reference. Returns 'quit' or None."""
    idx = 0
    win.nodelay(False)
    win.timeout(300)
    try:
        while True:
            s = read_state() or {}
            g = s.get("guard") or {}
            routed = bool((s.get("routing") or {}).get("installed"))
            enforce = g.get("enforce", True)
            ka = s.get("keepawake") or {}
            sp = (s.get("net") or {}).get("speedtest") or {}
            cd = sp.get("cooldown_until")
            mbps = sp.get("mbps_down")
            if sp.get("running"):
                spval = "running…"
            elif isinstance(cd, (int, float)) and time.time() < cd:
                spval = "cooling down"
            elif isinstance(mbps, (int, float)) and mbps:
                spval = f"{mbps:.0f} Mbps"
            else:
                spval = ""
            items = [
                ("route", "Route Claude through the guard",
                 "ON" if routed else "off"),
                ("enforce", "Enforcement — block when outside",
                 "ON" if enforce else "off"),
                ("scope", "Block scope",
                 "ALL traffic" if g.get("block_all") else "Claude only"),
                ("country", "Pin a country…", cname(g.get("target_cc"))),
                ("keepawake", f"Keep the {DEVICE} awake",
                 {"idle": "lid open", "clamshell": "lid-closed ok"}.get(
                     ka.get("mode", "off"), "off")),
                ("desktop", "Open Claude Desktop through the guard",
                 _desk_val(s)),
                ("recheck", "Re-check location now", ""),
                ("speedtest", "Run internet speed test", spval),
                ("refresh", "Refresh usage now", ""),
                ("plan", "Live plan limits (runs Claude)",
                 "on" if (s.get("settings") or {}).get("plan_enabled", True) else "off"),
                ("cost", "Usage & cost details…", ""),
                ("procs", "Background processes…", ""),
                ("sep", "", ""),
                ("stop", "Stop guard & restore Claude, then quit", ""),
                ("quit", "Quit dashboard (guard keeps running)", ""),
            ]
            selectable = [i for i, it in enumerate(items) if it[0] != "sep"]
            if idx not in selectable:
                idx = selectable[0]
            h, w = win.getmaxyx()
            bw = min(64, w - 2)
            bh = min(len(items) + 4, h - 2)
            by = max(0, (h - bh) // 2)
            bx = max(0, (w - bw) // 2)
            draw_box(win, by, bx, bh, bw, "ACTIONS")
            for r, (key, label, val) in enumerate(items):
                yy = by + 2 + r
                if yy >= by + bh - 2:
                    break
                if key == "sep":
                    safe_addstr(win, yy, bx + 2, "─" * (bw - 4), cp(C_LINE))
                    continue
                sel = (r == idx)
                attr = (cp(C_TITLE) | curses.A_REVERSE | B) if sel \
                    else cp(C_TITLE)
                mark = "› " if sel else "  "
                safe_addstr(win, yy, bx + 3,
                            (mark + label).ljust(bw - 19)[:bw - 19], attr)
                if val:
                    va = (cp(C_BAD) | B if val == "UNGUARDED"
                          else cp(C_DIM) if val in ("off", "not installed")
                          else cp(C_TITLE) | (B if val == "ON" else 0))
                    safe_addstr(win, yy, bx + bw - 16, val[:13],
                                va | (curses.A_REVERSE if sel else 0))
            safe_addstr(win, by + bh - 2, bx + 3,
                        "↑/↓ move · Enter select · Esc close", cp(C_DIM))
            win.noutrefresh()
            curses.doupdate()
            ch = win.getch()
            if ch == -1:
                continue
            if ch == 27:
                return None
            activate = False
            if ch == curses.KEY_MOUSE:
                try:
                    _, mx, my, _, bs = curses.getmouse()
                except curses.error:
                    continue
                if bs & MOUSE_WHEEL_UP:
                    idx = selectable[(selectable.index(idx) - 1) % len(selectable)]
                elif bs & MOUSE_WHEEL_DOWN:
                    idx = selectable[(selectable.index(idx) + 1) % len(selectable)]
                elif bs & MOUSE_B1:                # click a row → select + run
                    r = my - (by + 2)
                    if 0 <= r < min(len(items), bh - 4) \
                            and items[r][0] != "sep" \
                            and bx + 1 <= mx <= bx + bw - 2:
                        idx = r
                        activate = True
            elif ch in (curses.KEY_UP, ord("k")):
                idx = selectable[(selectable.index(idx) - 1) % len(selectable)]
            elif ch in (curses.KEY_DOWN, ord("j")):
                idx = selectable[(selectable.index(idx) + 1) % len(selectable)]
            elif ch in (curses.KEY_ENTER, 10, 13):
                activate = True
            if activate:
                key = items[idx][0]
                if key == "route":
                    toggle_route(win, s)
                elif key == "enforce":
                    toggle_enforce(win, s)
                elif key == "scope":
                    send({"cmd": "scope", "block_all": not g.get("block_all", False)})
                elif key == "country":
                    sel = country_modal(win, g.get("target_cc", "US"))
                    if sel:
                        send({"cmd": "country", "cc": sel})
                elif key == "keepawake":
                    cur = ka.get("mode", "off")
                    nxt = KEEPAWAKE_CYCLE[(KEEPAWAKE_CYCLE.index(cur) + 1) % 3] \
                        if cur in KEEPAWAKE_CYCLE else "idle"
                    send({"cmd": "keepawake", "on": nxt != "off", "mode": nxt})
                elif key == "desktop":
                    open_desktop(win, s)
                elif key == "recheck":
                    send({"cmd": "recheck"})
                elif key == "speedtest":
                    send({"cmd": "speedtest"})
                elif key == "plan":
                    on = (s.get("settings") or {}).get("plan_enabled", True)
                    send({"cmd": "planfetch", "on": not on})
                elif key == "refresh":
                    send({"cmd": "refreshplan"})
                elif key == "cost":
                    usage_modal(win)
                elif key == "procs":
                    if procs_modal(win, s) == "stopped":
                        return "quit"
                elif key == "stop":
                    if danger_confirm(
                            win, s,
                            "Stop the guard and restore Claude to a DIRECT, "
                            "unguarded connection?",
                            "This turns the guard off entirely, then quits."
                            + _pinned_note(s)):
                        send({"cmd": "quit"})
                        return "quit"
                elif key == "quit":
                    return "quit"
                win.timeout(300)       # a confirm resets the tick; keep ours
    finally:
        win.nodelay(True)
        win.timeout(TICK_MS)


def do_click(win, act, s):
    """Dispatch a dashboard hitbox action. Returns 'quit' or None."""
    g = s.get("guard") or {}
    if isinstance(act, tuple) and act[0] == "focus":
        send({"cmd": "focus", "session_id": act[1]})
    elif act == "route":
        toggle_route(win, s)
    elif act == "enforce":
        toggle_enforce(win, s)
    elif act == "scope":
        send({"cmd": "scope", "block_all": not g.get("block_all", False)})
    elif act == "country":
        sel = country_modal(win, g.get("target_cc", "US"))
        if sel:
            send({"cmd": "country", "cc": sel})
    elif act == "keepawake":
        cur = (s.get("keepawake") or {}).get("mode", "off")
        nxt = KEEPAWAKE_CYCLE[(KEEPAWAKE_CYCLE.index(cur) + 1) % 3] \
            if cur in KEEPAWAKE_CYCLE else "idle"
        send({"cmd": "keepawake", "on": nxt != "off", "mode": nxt})
    elif act == "speedtest":
        send({"cmd": "speedtest"})
    elif act == "planrefresh":
        send({"cmd": "refreshplan"})
    elif act == "recheck":
        send({"cmd": "recheck"})
    elif act in ("cost", "usage"):
        usage_modal(win)
    elif act == "desktop":
        open_desktop(win, s)
    elif act == "menu":
        return actions_menu(win)
    return None


def _sig(d):
    """Cheap signature of the fields that affect the view — redraw only when it
    changes (plus a slow time-tick for clocks), so idle CPU stays near zero."""
    if not d:
        return None
    g = d.get("guard") or {}
    loc = d.get("location") or {}
    pl = d.get("plan") or {}
    ka = d.get("keepawake") or {}
    rec = d.get("recent") or []
    net = d.get("net") or {}
    st = net.get("speedtest") or {}
    prog = st.get("progress")
    prog = prog if isinstance(prog, (int, float)) else 0

    def _r(v):
        return round(v) if isinstance(v, (int, float)) else None

    ag = d.get("agents") or {}
    summary = ag.get("summary") or {}
    ag_sig = (tuple(sorted((str(x.get("session_id")), str(x.get("status")),
                            str(x.get("activity")), str(x.get("model")),
                            str(x.get("effort")), str(x.get("context")),
                            str(x.get("result")),
                            str((x.get("ticks") or {}).get("tools_done")
                                if isinstance(x.get("ticks"), dict) else None),
                            str([(y.get("agent_id"), y.get("status"),
                                  y.get("activity"))
                                 for y in (x.get("subagents") or [])
                                 if isinstance(y, dict)]))
                           for x in (ag.get("sessions") or [])
                           if isinstance(x, dict))),
              len(ag.get("needs_you") or []), len(ag.get("collisions") or []),
              summary.get("working"), summary.get("needs_you"),
              summary.get("done_today"))
    return (g.get("allowed"), g.get("blocked"), g.get("enforce"),
            g.get("block_all"), g.get("target_cc"), g.get("proxy_up"),
            g.get("pending"), g.get("holding"),
            (d.get("routing") or {}).get("installed"), ka.get("mode"), ka.get("holding"), ka.get("reason"),
            loc.get("status"), loc.get("in_target"), loc.get("city"),
            len(rec), rec[-1].get("t") if rec else None,
            pl.get("updated"), pl.get("refreshing"), pl.get("ok"),
            net.get("status"), net.get("raw_status"),
            _r(net.get("internet_ms")), _r(net.get("api_ms")),
            net.get("checked"), st.get("running"),
            round(prog * 50), st.get("at"),      # 2% steps → smooth, cheap
            ag_sig, json.dumps(d.get("apps"), sort_keys=True))


def run(win):
    curses.curs_set(0)
    init_colors()
    try:
        # Clicks + wheel only — no motion tracking, so no event floods and
        # the idle loop stays as cheap as before. mouseinterval(0) kills the
        # 200ms double-click wait so single clicks feel instant.
        curses.mousemask(MOUSE_B1 | MOUSE_WHEEL_UP | MOUSE_WHEEL_DOWN)
        curses.mouseinterval(0)
    except curses.error:
        pass
    try:
        curses.set_escdelay(25)           # Esc closes a modal now, not in 1s
    except (AttributeError, curses.error):
        pass
    win.nodelay(True)
    win.timeout(TICK_MS)
    last = None

    # First run: show onboarding (ASCII banner, launch command, country pin).
    if not os.path.exists(SEEN_FLAG):
        if onboarding(win) == "quit":
            return
        try:
            open(SEEN_FLAG, "w").close()
        except OSError:
            pass

    sig_prev = object()
    last_draw = 0.0

    def render():
        if last:
            draw(win, last)
        else:
            win.erase()
            safe_addstr(win, 1, 2, "starting guard daemon…", cp(C_DIM))
            win.noutrefresh(); curses.doupdate()

    while True:
        now = time.time()
        s = read_state()
        if s:
            last = s
        # Repaint only when something changed, or ~2×/s for clocks & live rows.
        # While the frame animates — the "Reconnecting Claude…" shimmer, a
        # working agent's model mark, the verify sweep — repaint every tick
        # (~12fps). That's a replay of the composed frame, not a re-layout.
        sig = _sig(last)
        if sig != sig_prev or now - last_draw > 0.5 or frame_live():
            render()
            sig_prev = sig
            last_draw = now

        try:
            ch = win.getch()
        except KeyboardInterrupt:
            return
        if ch == -1:                      # idle tick — nothing pressed
            continue
        # The dashboard is fully driveable three ways — single-key shortcuts
        # (the set documented in HELP / the help modal and hinted in the
        # footer and on the panels), the mouse, or the actions menu. `q` quits
        # and leaves the guard running; `Q` is the guarded off-switch (stop
        # guard + restore a direct Claude connection) and is double-confirmed.
        # A key that isn't a shortcut does nothing.
        st = last or {}
        if ch == curses.KEY_RESIZE:       # re-lay out for the new size class
            sig_prev = object()
        elif ch == ord("q"):
            return
        elif ch == ord("Q"):
            if danger_confirm(
                    win, st,
                    "Stop the guard and restore Claude to a DIRECT, "
                    "unguarded connection?",
                    "This turns the guard off entirely, then quits."
                    + _pinned_note(st)):
                send({"cmd": "quit"})
                return
            sig_prev = object()
        elif ch in (curses.KEY_ENTER, 10, 13, ord("m"), ord(" ")):
            if actions_menu(win) == "quit":
                return
            sig_prev = object()   # force a repaint after the menu closes
        elif ch in KEY_ACTIONS:
            if do_click(win, KEY_ACTIONS[ch], st) == "quit":
                return
            sig_prev = object()   # repaint after the shortcut acts
        elif ch in (ord("u"), ord("$")):
            usage_modal(win)
            sig_prev = object()
        elif ch == ord("k"):
            send({"cmd": "recheck"})
            sig_prev = object()
        elif ch == ord("?"):
            help_modal(win)
            sig_prev = object()
        elif ch == curses.KEY_MOUSE:
            try:
                _, mx, my, _, bs = curses.getmouse()
            except curses.error:
                continue
            if bs & MOUSE_B1:
                act = hit_at(my, mx)
                if act is not None:
                    if do_click(win, act, st) == "quit":
                        return
                    sig_prev = object()   # repaint after any click action


def main():
    if not sys.stdout.isatty():
        print("tower-tui needs an interactive terminal.", file=sys.stderr)
        sys.exit(1)
    ensure_daemon()
    # give the daemon a beat to write state.json
    for _ in range(20):
        if read_state():
            break
        time.sleep(0.2)
    curses.wrapper(run)


if __name__ == "__main__":
    main()
