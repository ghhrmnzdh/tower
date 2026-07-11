#!/usr/bin/env python3
"""
tower-tui — terminal front-end for the Tower daemon.

A read-only-looking dashboard that is actually a full controller: it renders
~/.tower/state.json and drives the guard by dropping command files into
~/.tower/cmd/ (exactly like the menubar app). stdlib only (curses).

If the daemon isn't running it starts it (single-instance, so this is safe),
then attaches. Quitting the TUI leaves the guard running; press Shift-Q to stop
the guard entirely (removes routing, restores Claude to a direct connection).

Run:  python3 tower-tui.py
"""

import json
import os
import subprocess
import sys
import textwrap
import time
import uuid

# curses isn't in the Windows stdlib. _wincurses is a drop-in shim implementing
# the exact curses subset this TUI uses, over ANSI/VT + msvcrt (dep-free). On
# macOS/Linux the real curses is used, unchanged.
if os.name == "nt":
    import _wincurses as curses
else:
    import curses

# Platform noun for user-facing copy — "Mac" on macOS (unchanged), "PC" on
# Windows. Keeps the macOS wording byte-identical while reading right on Windows.
DEVICE = "PC" if os.name == "nt" else "Mac"

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
# IPC
# --------------------------------------------------------------------------- #
def read_state():
    try:
        with open(STATE_FILE) as f:
            s = json.load(f)
        if time.time() - s.get("ts", 0) < 5:
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
    """Model + effort as the app shows it: "Opus 4.8 · HIGH". Version is parsed
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
    return f"{label} · {str(eff).upper()}" if eff else label


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
    """Live relative time in the future — 'in 3h', 'in 2d', 'now'."""
    if not isinstance(at, (int, float)) or not at:
        return ""
    s = at - time.time()
    if s <= 30:
        return "now"
    if s < 5400:
        return f"in {int(s / 60)}m"
    if s < 129600:
        return f"in {int(s / 3600)}h"
    return f"in {int(s / 86400)}d"


def reset_text(node):
    """A reset stamp shown relative, with no timezone. Falls back to the raw
    stamp minus its '(timezone)' tail if there's no parsed epoch."""
    rel = until(node.get("resets_at"))
    if rel:
        return rel
    raw = node.get("resets") or ""
    return raw.split("(", 1)[0].strip()


_EIGHTHS = " ▏▎▍▌▋▊▉"


def bar(frac, width):
    """Fixed-width bar with 1/8-cell precision (accurate) on a ░ track."""
    frac = max(0.0, min(1.0, frac))
    total = frac * width
    full = int(total)
    s = "█" * full
    if full < width:
        rem = int((total - full) * 8)
        if rem:
            s += _EIGHTHS[rem]
        s += "░" * (width - len(s))
    return s[:width]


AGENT_PHRASE = {
    "working": "working", "pending_tool": "waiting on a tool",
    "waiting_input": "waiting for you", "asking": "has a question",
    "done": "done", "failed": "failed", "idle": "idle", "gone": "gone",
    "paused": "paused",
}


def agent_row(sess, reason, since):
    """One agent row: <project> — <activity/result/phrase> · <family> [· N ✓] · <ago>."""
    name = (sess.get("project_name")
            or os.path.basename(sess.get("cwd") or "") or "?")
    st = reason or sess.get("status")
    result = sess.get("result")
    if st == "done" and result:
        what = f"done — {result}"       # what the agent produced, not the prompt
    else:
        what = (sess.get("activity")
                or AGENT_PHRASE.get(st, st or "…"))
    parts = [f"{name} — {what}"]
    if sess.get("model") or sess.get("model_family"):
        parts.append(model_label(sess))
    ticks = sess.get("ticks")
    done = ticks.get("tools_done") if isinstance(ticks, dict) else None
    if sess.get("status") == "working" and done:
        parts.append(f"{done} ✓")       # momentum, matched to the app row
    when = ago(since or sess.get("status_since") or sess.get("last_activity"))
    if when:
        parts.append(when)
    return " · ".join(parts)


SPARK = "▁▂▃▄▅▆▇█"


def sparkline(vals):
    m = max(vals) if vals else 0
    if m <= 0:
        return "▁" * len(vals)
    return "".join(SPARK[min(len(SPARK) - 1, int((v / m) * (len(SPARK) - 1)))]
                   for v in vals)


# --------------------------------------------------------------------------- #
# Colors
# --------------------------------------------------------------------------- #
C_TITLE = 1
C_GOOD = 2
C_WARN = 3
C_DIM = 4
C_ACCENT = 5
C_BAD = 6


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_TITLE, curses.COLOR_WHITE, -1)
    curses.init_pair(C_GOOD, curses.COLOR_GREEN, -1)
    curses.init_pair(C_WARN, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_DIM, curses.COLOR_CYAN, -1)
    curses.init_pair(C_ACCENT, curses.COLOR_MAGENTA, -1)
    curses.init_pair(C_BAD, curses.COLOR_RED, -1)


def cp(n):
    return curses.color_pair(n)


# --------------------------------------------------------------------------- #
# Mouse — a hitbox registry rebuilt on every draw pass. Each entry is
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
               ord("c"): "country", ord("p"): "country", ord("w"): "keepawake"}
HITBOXES = []


def hit_at(my, mx):
    for y, x1, x2, action in HITBOXES:
        if my == y and x1 <= mx <= x2:
            return action
    return None


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def status_of(s):
    """Return (label, color) for the overall guard status."""
    # Net faults outrank everything — a red header should mean "stop and
    # look", and `degraded` deliberately does NOT override (card shows it).
    net = (s.get("net") or {}).get("status")
    if net == "offline":
        return "INTERNET DOWN", C_BAD
    if net == "captive":
        return "WI-FI LOGIN REQUIRED", C_BAD
    if net == "api_issue":
        return "ANTHROPIC API ISSUE", C_BAD
    routed = (s.get("routing") or {}).get("installed")
    g = s.get("guard") or {}
    loc = s.get("location") or {}
    if not routed:
        return "Not routed", C_DIM
    if not g.get("enforce", True):
        return "Monitor only", C_DIM
    # Fail-closed: the daemon says whether a Claude request is allowed right now.
    if g.get("claude_allowed"):
        return "Protected", C_GOOD
    if g.get("net_ok") is False:
        return "Blocking — connection unstable", C_WARN
    if loc.get("status") != "OK":
        return "Blocking — confirming location…", C_WARN
    return "Blocking Claude", C_WARN


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


def safe_addstr(win, y, x, text, attr=0):
    h, w = win.getmaxyx()
    if y < 0 or y >= h or x >= w:
        return
    win.addstr(y, x, text[:max(0, w - x - 1)], attr)


def draw_shimmer(win, y, x, text, color):
    """Terminal 'shimmer' for the retry/pending state: a bright band sweeps
    across the text on every redraw tick (time-based, ~1.8s period, matching the
    app's shimmerPeriod). Bright core, normal shoulders, dim elsewhere — the
    agentic 'reconnecting' look, done with attributes since curses has no
    gradients."""
    span = len(text) + 6
    pos = (time.time() % 1.8) / 1.8 * span - 3
    for i, chx in enumerate(text):
        d = abs(i - pos)
        if d < 1.2:
            attr = cp(color) | curses.A_BOLD
        elif d < 2.6:
            attr = cp(color)
        else:
            attr = cp(color) | curses.A_DIM
        safe_addstr(win, y, x + i, chx, attr)


def draw(win, s):
    win.erase()
    HITBOXES.clear()
    h, w = win.getmaxyx()
    label, lc = status_of(s)
    g = s.get("guard") or {}
    loc = s.get("location") or {}
    net = s.get("net") or {}
    u = s.get("usage") or {}
    cc = g.get("target_cc", "—")

    # Header. While a Claude request is held/retrying on the guard, the status
    # word shimmers "Reconnecting Claude…" — an agentic pending state that
    # clears the instant the guard passes and Claude resumes on its own.
    safe_addstr(win, 0, 2, "TOWER", cp(C_TITLE) | curses.A_BOLD)
    pending = bool(g.get("pending"))
    head = "Reconnecting Claude…" if pending else label
    tail = f"  ·  target: {cname(cc)}"
    right = head + tail
    rx0 = max(2, w - len(right) - 2)
    if pending:
        draw_shimmer(win, 0, rx0, head, lc)
        safe_addstr(win, 0, rx0 + len(head), tail, cp(lc) | curses.A_BOLD)
    else:
        safe_addstr(win, 0, rx0, right, cp(lc) | curses.A_BOLD)
    tpos = right.find("target:")
    if tpos >= 0:                       # click the country name → picker
        HITBOXES.append((0, rx0 + tpos, rx0 + len(right) - 1, "country"))
    safe_addstr(win, 1, 2, "─" * (w - 4), cp(C_DIM))

    # ---- Left: location ---- #
    y = 2
    safe_addstr(win, y, 2, "NETWORK LOCATION", cp(C_DIM) | curses.A_BOLD); y += 1
    st = loc.get("status")
    if net.get("status") == "offline":
        # one story with the header: not "Locating…" forever, not blocking
        safe_addstr(win, y, 3, "internet down — location unknown, not blocking",
                    cp(C_BAD)); y += 1
    elif st in ("OK", "CACHED"):
        it = loc.get("in_target")
        if st == "OK":
            head = "✔ inside target" if it else "✗ outside target — Claude blocked"
            hc = C_GOOD if it else C_WARN
        else:
            head, hc = "· last known (re-checking…)", C_DIM
        safe_addstr(win, y, 3, head, cp(hc) | curses.A_BOLD); y += 1
        place = ", ".join(x for x in (loc.get("city"), loc.get("region")) if x)
        ccx = loc.get("country_cc")
        for k, v in (("IP", loc.get("ip")),
                     ("Country", f"{cname(ccx)} ({ccx or '—'})"),
                     ("Location", place),
                     ("ISP", loc.get("isp"))):
            if v:
                safe_addstr(win, y, 3, f"{k:<8}", cp(C_DIM))
                safe_addstr(win, y, 12, str(v))
                y += 1
    elif loc.get("error"):
        safe_addstr(win, y, 3, "location unknown — not blocking", cp(C_DIM)); y += 1
        safe_addstr(win, y, 3, "! " + loc["error"], cp(C_WARN)); y += 1
    else:
        safe_addstr(win, y, 3, "locating…", cp(C_DIM)); y += 1

    # ---- Guard block (right column) ---- #
    rx = min(w - 30, 40)
    gy = 2
    safe_addstr(win, gy, rx, "GUARD", cp(C_DIM) | curses.A_BOLD); gy += 1
    routed = (s.get("routing") or {}).get("installed")
    rows = [
        ("Route Claude", "on" if routed else "off", C_GOOD if routed else C_DIM),
        ("Enforce", "on" if g.get("enforce", True) else "off",
         C_GOOD if g.get("enforce", True) else C_DIM),
        ("Scope", "ALL traffic" if g.get("block_all") else "Claude only", C_TITLE),
        ("Allowed", str(g.get("allowed", 0)), C_GOOD),
        ("Blocked", str(g.get("blocked", 0)),
         C_WARN if g.get("blocked", 0) else C_DIM),
        ("Proxy", f":{g.get('proxy_port', '?')} {'up' if g.get('proxy_up') else 'down'}",
         C_GOOD if g.get("proxy_up") else C_BAD),
    ]
    row_acts = ("route", "enforce", "scope", None, None, None)
    for (k, v, c), act in zip(rows, row_acts):
        safe_addstr(win, gy, rx, f"{k:<13}", cp(C_DIM))
        safe_addstr(win, gy, rx + 13, v, cp(c))
        if act:                          # click a guard row → toggle it
            HITBOXES.append((gy, rx, w - 3, act))
        gy += 1

    # ---- KEEP AWAKE — its own card, set apart from the rest ---- #
    y = max(y, gy) + 1
    ka = s.get("keepawake") or {}
    kmode = ka.get("mode", "off")
    kon = bool(ka.get("on")) and kmode != "off"
    cardw = w - 4
    if y + 3 <= h - 4:
        draw_box(win, y, 2, 3, cardw, "KEEP AWAKE")
        dot = "●" if kon else "○"
        state_txt = {"idle": "on · lid open",
                     "clamshell": "on · survives lid close"}.get(kmode, "off")
        desc = {"idle": f"{DEVICE} stays awake while the lid is open",
                "clamshell": "long agents keep running with the lid closed"}.get(
                    kmode if kon else "off",
                    f"{DEVICE} may sleep — long agents can be interrupted")
        hint = "[w] change"
        safe_addstr(win, y + 1, 4, f"{dot} {state_txt}",
                    cp(C_GOOD if kon else C_DIM) | curses.A_BOLD)
        dx = 4 + len(f"{dot} {state_txt}") + 3
        hx = max(dx, w - 3 - len(hint) - 1)
        safe_addstr(win, y + 1, dx, desc[:max(0, hx - dx - 1)], cp(C_DIM))
        safe_addstr(win, y + 1, hx, hint, cp(C_ACCENT))
        for yy in range(y, y + 3):       # click the card → cycle keep-awake
            HITBOXES.append((yy, 2, w - 3, "keepawake"))
        y += 3

    # ---- NETWORK HEALTH — where a Claude error comes from. Omitted when the
    # daemon predates the `net` key so old daemons render exactly as before. --- #
    if "net" in s and y + 4 <= h - 4:
        draw_box(win, y, 2, 4, cardw, "NETWORK")
        nst = net.get("status") or "checking"
        ncol = {"online": C_GOOD, "degraded": C_WARN,
                "checking": C_DIM}.get(nst, C_BAD)
        if nst == "api_issue":
            line1 = ("● api issue · internet OK · api.anthropic.com "
                     f"unreachable ({net.get('api_error') or '?'})")
        elif nst == "captive":
            line1 = "● Wi-Fi login required — open a browser"
        elif nst == "offline":
            line1 = "● internet down"
        else:
            line1 = (f"● {nst} · net {fmt_ms(net.get('internet_ms'))}"
                     f" · api {fmt_ms(net.get('api_ms'))}")
            if nst == "degraded":
                line1 += {"dns": " · DNS problem",
                          "api_slow": " · slow path to Anthropic (link ok)",
                          }.get(net.get("reason"), " · slow link")
        safe_addstr(win, y + 1, 4, line1[:max(0, cardw - 4)],
                    cp(ncol) | curses.A_BOLD)
        # latency sparkline — failed samples peg at 3000 so outages read high
        spark_w = max(8, min(30, cardw - 44))
        vals = [hh.get("api_ms")
                if isinstance(hh.get("api_ms"), (int, float)) else 3000.0
                for hh in (net.get("history") or [])[-spark_w:]
                if isinstance(hh, dict)]
        left = "api " + (sparkline(vals) if vals else "—")
        sp = net.get("speedtest") or {}
        mbps = sp.get("mbps_down")
        prog = sp.get("progress")
        prog = prog if isinstance(prog, (int, float)) else 0
        if sp.get("running"):
            st_txt = f"speed test: {int(prog * 100)}% …"
        elif isinstance(mbps, (int, float)) and mbps:
            st_txt = f"↓ {mbps:.0f} Mbps ({ago(sp.get('at'))} ago)"
        elif sp.get("error"):
            st_txt = "speed test failed"
        else:
            st_txt = "speed test: never run"
        hint = "click → speed test"
        safe_addstr(win, y + 2, 4, left, cp(C_DIM))
        sx = 4 + len(left) + 3
        hx = max(sx, w - 3 - len(hint) - 1)
        safe_addstr(win, y + 2, sx, st_txt[:max(0, hx - sx - 1)], cp(C_DIM))
        safe_addstr(win, y + 2, hx, hint, cp(C_ACCENT))
        for yy in range(y, y + 4):       # click the card → run a speed test
            HITBOXES.append((yy, 2, w - 3, "speedtest"))
        y += 4

    # ---- AGENTS — Claude agents on this Mac. Omitted entirely when the
    # daemon predates the `agents` key. --- #
    ag = s.get("agents")
    if isinstance(ag, dict):
        by_id = {x.get("session_id"): x
                 for x in (ag.get("sessions") or []) if isinstance(x, dict)}
        arow = []                        # (marker, color, text, session_id)
        listed = set()
        for nu in (ag.get("needs_you") or []):
            if not isinstance(nu, dict):
                continue
            sid = nu.get("session_id")
            sess = by_id.get(sid) or {}
            if sess.get("dismissed"):
                continue
            reason = nu.get("reason") or sess.get("status") or ""
            mark, mc = {"failed": ("✗", C_BAD),
                        "pending_tool": ("⛔", C_WARN),
                        "asking": ("?", C_ACCENT),
                        "done": ("✓", C_GOOD)}.get(reason, ("•", C_WARN))
            arow.append((mark, mc, agent_row(sess, reason, nu.get("since")), sid,
                         sess.get("status") == "working"))
            listed.add(sid)
        for x in (ag.get("sessions") or []):
            if not isinstance(x, dict) or x.get("dismissed"):
                continue
            sid = x.get("session_id")
            if sid in listed:
                continue
            st = x.get("status")
            if st == "working":
                arow.append(("●", C_DIM, agent_row(x, "working", None),
                             sid, True))
            elif st == "paused":       # user-suspended: still on the board,
                arow.append(("⏸", C_DIM, agent_row(x, "paused", None),
                             sid, False))    # calm — no shimmer, no alarm
        coll = None
        for c in (ag.get("collisions") or []):
            if not isinstance(c, dict):
                continue
            n = len(c.get("session_ids") or []) or 2
            repo = os.path.basename(str(c.get("git_root") or "")) or "one repo"
            coll = f"⚠ {n} agents in {repo}"
            files = c.get("files") or []
            if c.get("level") == "file" and files:
                coll += f" — both touching {os.path.basename(str(files[0]))}"
            break
        summary = ag.get("summary") or {}
        counts = (f"{summary.get('working', 0)} at work · "
                  f"{summary.get('done_today', 0)} done today · "
                  f"{summary.get('needs_you', 0)} need you")
        routing = s.get("routing") or {}
        intended = routing.get("intended")
        if intended is None:                 # old daemon: fall back to file truth
            intended = routing.get("installed")
        n_ung = summary.get("unguarded", 0) or 0
        n_pin = summary.get("pinned", 0) or 0
        guard_line, guard_color = None, C_WARN
        if intended and n_ung:
            guard_line = (f"⚠ {n_ung} chat{'s' if n_ung != 1 else ''} started "
                          f"before the guard — restart to protect")
        elif not intended and n_pin:
            guard_line = (f"{n_pin} chat{'s' if n_pin != 1 else ''} still on the "
                          f"old proxy — safe until restart")
            guard_color = C_DIM
        nrows = min(6, len(arow))
        if arow:
            bh_a = 1 + nrows + (1 if coll else 0) + (1 if guard_line else 0) + 2
            while bh_a > (h - 4) - y and nrows > 1:   # shrink to fit
                nrows -= 1
                bh_a = 1 + nrows + (1 if coll else 0) + \
                    (1 if guard_line else 0) + 2
        else:
            bh_a = 3                     # just "no agents running"
        if y + bh_a <= h - 4:
            draw_box(win, y, 2, bh_a, cardw, "AGENTS")
            yy = y + 1
            if not arow:
                safe_addstr(win, yy, 4, "no agents running", cp(C_DIM))
            else:
                safe_addstr(win, yy, 4, counts[:max(0, cardw - 4)],
                            cp(C_TITLE) | curses.A_BOLD)
                yy += 1
                for mark, mc, txt, sid, live in arow[:nrows]:
                    safe_addstr(win, yy, 4, mark, cp(mc) | curses.A_BOLD)
                    if intended and by_id.get(sid, {}).get("guarded") is False:
                        txt = txt + "  ·unguarded"    # started before the guard
                    clipped = txt[:max(0, cardw - 7)]
                    if live:             # working agent: shimmer like the header
                        draw_shimmer(win, yy, 7, clipped, C_TITLE)
                    else:
                        safe_addstr(win, yy, 7, clipped, cp(C_TITLE))
                    if sid:              # click a row → focus that session
                        HITBOXES.append((yy, 4, w - 3, ("focus", sid)))
                    yy += 1
                if coll:
                    safe_addstr(win, yy, 4, coll[:max(0, cardw - 4)], cp(C_WARN))
                    yy += 1
                if guard_line:
                    safe_addstr(win, yy, 4, guard_line[:max(0, cardw - 4)],
                                cp(guard_color))
            y += bh_a

    # ---- PLAN LIMITS: the REAL numbers, mirrored from `claude -p /usage` ---- #
    safe_addstr(win, y, 2, "─" * (w - 4), cp(C_DIM)); y += 1
    plan = s.get("plan") or {}
    BX = 12
    BAR_W = max(12, min(w - BX - 48, 30))
    VX = BX + BAR_W + 2

    def bcolor(p):
        return C_BAD if p >= 90 else (C_WARN if p >= 75 else C_GOOD)

    gate = usage_gate(s)
    safe_addstr(win, y, 2, "PLAN LIMITS", cp(C_TITLE) | curses.A_BOLD)
    HITBOXES.append((y, 2, w - 3, "planrefresh"))   # click → refresh plan
    if gate:
        safe_addstr(win, y, 15, "paused — guard not passing", cp(C_WARN))
    elif plan.get("disabled"):
        safe_addstr(win, y, 15, "live limits off (no Claude runs)", cp(C_DIM))
    elif plan.get("ok"):
        if plan.get("refreshing"):
            note = "updating…"
        else:
            note = f"updated {ago(plan.get('updated'))} ago"
        safe_addstr(win, y, 15, note, cp(C_GOOD))
    elif plan.get("error"):
        safe_addstr(win, y, 15, "unavailable — " + str(plan.get("error"))[:44],
                    cp(C_WARN))
    else:
        safe_addstr(win, y, 15, "fetching from Claude /usage…", cp(C_DIM))
    y += 1

    if gate:
        # Guard isn't passing Claude → no usage to show. Give the message room
        # to breathe instead of cramming numbers that would be wrong anyway.
        head, detail = gate
        y += 1
        safe_addstr(win, y, 3, head, cp(C_WARN) | curses.A_BOLD); y += 2
        for line in textwrap.wrap(detail, max(20, w - 8)):
            safe_addstr(win, y, 3, line, cp(C_DIM)); y += 1
        y += 1
    elif plan.get("disabled"):
        safe_addstr(win, y, 3,
                    "turn on with the menu · uses the local estimate below",
                    cp(C_DIM)); y += 1
    elif plan.get("ok"):
        for label, node in (("Session", plan.get("session")),
                            ("Week all", plan.get("week")),
                            ("Fable", plan.get("fable"))):
            node = node or {}
            p = node.get("pct")
            if p is None:
                continue
            safe_addstr(win, y, 3, label, cp(C_TITLE) | curses.A_BOLD)
            safe_addstr(win, y, BX, bar(p / 100.0, BAR_W),
                        cp(bcolor(p)) | curses.A_BOLD)
            txt = f"{p:3d}% used"
            rt = reset_text(node)
            if rt:
                txt += f"   resets {rt}"
            safe_addstr(win, y, VX, txt, cp(C_DIM))
            HITBOXES.append((y, 2, w - 3, "planrefresh"))
            y += 1
        l24 = plan.get("last24h")
        if l24:
            safe_addstr(win, y, 3, f"last 24h · {l24.get('requests')} requests · "
                        f"{l24.get('sessions')} sessions", cp(C_DIM)); y += 1

    # ---- LOCAL ESTIMATE — quiet header, structured aligned rows ---- #
    y += 1
    sess = u.get("session") or {}
    wk = u.get("week") or {}
    pace = u.get("pace") or {}
    safe_addstr(win, y, 2, "local estimate", cp(C_DIM))
    safe_addstr(win, y, 17, "· measured on this machine, not your plan %",
                cp(C_DIM) | curses.A_DIM)
    y += 1

    def le(label, value):
        safe_addstr(win, y, 4, label, cp(C_DIM))
        safe_addstr(win, y, 14, value, cp(C_TITLE))

    le("Session", f"{fmt_tok(sess.get('tokens'))} tokens    "
       f"{fmt_cost(sess.get('cost'))}    {sess.get('msgs', 0)} msgs    "
       f"{ago(sess.get('since'))}"); y += 1
    le("Week", f"{fmt_tok(wk.get('tokens'))} tokens    "
       f"{fmt_cost(wk.get('cost'))}    "
       f"~{fmt_tok(pace.get('projected_week_tokens'))} projected"); y += 1
    bm = u.get("byModel") or []
    if bm:
        le("Models", " · ".join(f"{model_name(m['model'])} {fmt_tok(m['tokens'])}"
                                for m in bm[:4])); y += 1
    series = u.get("series") or []
    if series:
        le("Trend 7d", sparkline([d.get("tokens", 0) for d in series])
           + f"    {fmt_tok(pace.get('live_tpm'))}/min now"); y += 1

    # ---- Live traffic through the guard ---- #
    y += 1
    if y < h - 3:
        safe_addstr(win, y, 2, "─" * (w - 4), cp(C_DIM)); y += 1
        recent = s.get("recent") or []
        safe_addstr(win, y, 2,
                    f"LIVE TRAFFIC   {g.get('allowed', 0)} allowed · "
                    f"{g.get('blocked', 0)} blocked", cp(C_TITLE) | curses.A_BOLD)
        y += 1
        if not recent:
            safe_addstr(win, y, 3,
                        "waiting for requests — run  claude  in another terminal",
                        cp(C_DIM)); y += 1
        else:
            for r in reversed(recent):
                if y >= h - 2:
                    break
                good = r.get("action") == "allowed"
                claude = r.get("kind") == "claude"
                safe_addstr(win, y, 3, r.get("t", ""), cp(C_DIM))
                safe_addstr(win, y, 12, "✔ allowed" if good else "⛔ blocked",
                            cp(C_GOOD if good else C_BAD) | curses.A_BOLD)
                safe_addstr(win, y, 24, "Claude" if claude else "other",
                            cp(C_ACCENT if claude else C_DIM))
                safe_addstr(win, y, 32, str(r.get("host", ""))[:max(0, w - 34)],
                            cp(C_TITLE))
                y += 1

    # ---- Footer: minimal; full key reference lives in help ---- #
    foot = "press  Enter  or click here for the actions menu     ·     q  to quit"
    safe_addstr(win, h - 2, 2, "─" * (w - 4), cp(C_DIM))
    safe_addstr(win, h - 1, 2, foot[:w - 4], cp(C_DIM))
    HITBOXES.append((h - 1, 2, w - 3, "menu"))
    win.noutrefresh()
    curses.doupdate()


def confirm(win, msg):
    h, w = win.getmaxyx()
    safe_addstr(win, h - 1, 2, msg + " [y/N]" + " " * 10, cp(C_WARN) | curses.A_BOLD)
    win.nodelay(False)
    ch = win.getch()
    win.nodelay(True)
    return ch in (ord("y"), ord("Y"))


def _agents_working(s):
    sessions = ((s.get("agents") or {}).get("sessions")) or []
    return sum(1 for a in sessions
               if a.get("status") == "working" and not a.get("dismissed"))


def _pinned_note(s):
    """Extra warning for STOP/QUIT: sessions still pinned to the proxy keep working
    while the guard runs, but lose their connection the moment it stops."""
    n = ((s.get("agents") or {}).get("summary") or {}).get("pinned", 0) or 0
    if not n:
        return ""
    return (f" {n} chat{'s' if n != 1 else ''} still pinned to the proxy will "
            "lose their connection until restarted.")


def danger_confirm(win, s, headline, detail):
    """Two-step confirmation for anything that lets Claude reach the API
    WITHOUT the guard (route off, enforce off, stop+quit). Wording escalates
    when agents are working right now. Returns True ONLY if the user confirms
    BOTH steps — a single keypress can never disable protection."""
    h, w = win.getmaxyx()
    n = _agents_working(s)
    warn = (f"  ⚠ {n} agent{'s' if n != 1 else ''} working NOW — "
            "they'll send UNGUARDED requests." if n else "")
    win.nodelay(False)
    try:
        safe_addstr(win, h - 1, 2,
                    ("⚠ " + headline + warn + "   [y/N]" + " " * 20)[:w - 4],
                    cp(C_BAD) | curses.A_BOLD)
        if win.getch() not in (ord("y"), ord("Y")):
            return False
        safe_addstr(win, h - 1, 2,
                    ("⚠ Are you SURE? " + detail + "   press Y again to confirm"
                     + " " * 20)[:w - 4], cp(C_BAD) | curses.A_BOLD)
        return win.getch() in (ord("y"), ord("Y"))
    finally:
        win.nodelay(True)


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
def draw_box(win, y, x, h, w, title=""):
    for r in range(h):
        safe_addstr(win, y + r, x, " " * w)
    safe_addstr(win, y, x, "┌" + "─" * (w - 2) + "┐", cp(C_DIM))
    safe_addstr(win, y + h - 1, x, "└" + "─" * (w - 2) + "┘", cp(C_DIM))
    for r in range(1, h - 1):
        safe_addstr(win, y + r, x, "│", cp(C_DIM))
        safe_addstr(win, y + r, x + w - 1, "│", cp(C_DIM))
    if title:
        safe_addstr(win, y, x + 2, " " + title + " ", cp(C_TITLE) | curses.A_BOLD)


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
                                cp(C_ACCENT) | curses.A_REVERSE | curses.A_BOLD)
                else:
                    mark = "• " if c == current_cc else "  "
                    safe_addstr(win, yy, bx + 2, (mark + label)[:bw - 4],
                                cp(C_GOOD if c == current_cc else C_TITLE))
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
                            line, cp(C_ACCENT) | curses.A_BOLD)
            y += len(BANNER) + 1
        else:
            safe_addstr(win, y, max(2, (w - 6) // 2), "TOWER",
                        cp(C_ACCENT) | curses.A_BOLD)
            y += 2

        def center(text, attr):
            safe_addstr(win, center.y, max(2, (w - len(text)) // 2), text, attr)
            center.y += 1
        center.y = y
        center("Pin Claude Code to a country · watch usage · keep long agents alive",
               cp(C_DIM))
        center.y += 1
        center("Open this dashboard anytime with:", cp(C_TITLE))
        cmd = f'python3 "{SELF}"'
        center(cmd if len(cmd) < w - 4 else "python3 …/tower-tui.py",
               cp(C_GOOD) | curses.A_BOLD)
        center.y += 1
        routed = bool(((read_state() or {}).get("routing") or {}).get("installed"))
        center(f"Target country:  {cname(picked) if picked else 'not set'}",
               cp(C_GOOD) | curses.A_BOLD if picked else cp(C_WARN))
        center(f"Route Claude through the guard:  {'yes' if routed else 'no'}",
               cp(C_GOOD) | curses.A_BOLD if routed else cp(C_DIM))
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
    ("$", "Cost — estimated $ this usage would cost at API prices"),
    ("k", "Re-check your location right now"),
    ("u", "Refresh plan usage now (runs Claude's /usage)"),
    ("?", "Show this help"),
    ("q", "Quit the dashboard — the guard keeps running"),
    ("Q", "Stop the guard & restore Claude to a direct connection"),
    ("net", "NETWORK card — your internet vs Anthropic's API; click"),
    ("agents", f"AGENTS — Claude agents on this {DEVICE}; click to focus"),
    ("mouse", "Click rows to act; wheel scrolls lists"),
]


def help_modal(win):
    """Centered, self-explaining key reference. Any key closes it."""
    win.nodelay(False)
    win.timeout(-1)
    try:
        h, w = win.getmaxyx()
        bw = min(66, w - 2)
        bh = min(len(HELP) + 5, h - 2)
        by = max(0, (h - bh) // 2)
        bx = max(0, (w - bw) // 2)
        draw_box(win, by, bx, bh, bw, "HELP · WHAT EACH KEY DOES")
        for r, (key, desc) in enumerate(HELP):
            yy = by + 2 + r
            if yy >= by + bh - 2:
                break
            safe_addstr(win, yy, bx + 3, f"{key:<7}", cp(C_ACCENT) | curses.A_BOLD)
            safe_addstr(win, yy, bx + 11, desc[:bw - 13], cp(C_TITLE))
        safe_addstr(win, by + bh - 2, bx + 3, "press any key to close", cp(C_DIM))
        win.noutrefresh()
        curses.doupdate()
        win.getch()
    finally:
        win.nodelay(True)
        win.timeout(TICK_MS)


def cost_modal(win, s):
    """Beautiful $ breakdown at API list prices (independent of your plan)."""
    u = (s or {}).get("usage") or {}
    sess = u.get("session") or {}
    today = u.get("today") or {}
    wk = u.get("week") or {}
    pace = u.get("pace") or {}
    bm = u.get("byModel") or []
    win.nodelay(False)
    win.timeout(-1)
    try:
        h, w = win.getmaxyx()
        bw = min(60, w - 2)
        bh = min(11 + min(len(bm), 5), h - 2)
        by = max(0, (h - bh) // 2)
        bx = max(0, (w - bw) // 2)
        draw_box(win, by, bx, bh, bw, "ESTIMATED API COST")
        yy = by + 1
        safe_addstr(win, yy, bx + 3,
                    "what this usage would cost pay-as-you-go", cp(C_DIM)); yy += 1
        safe_addstr(win, yy, bx + 3,
                    "(API list prices — not your subscription)",
                    cp(C_DIM) | curses.A_DIM); yy += 2

        def line(label, val, sub="", lc=C_TITLE):
            nonlocal yy
            safe_addstr(win, yy, bx + 3, label, cp(C_DIM))
            safe_addstr(win, yy, bx + 15, val, cp(lc) | curses.A_BOLD)
            if sub:
                safe_addstr(win, yy, bx + 27, sub, cp(C_DIM))
            yy += 1

        line("Session", fmt_cost(sess.get("cost")),
             f"{fmt_tok(sess.get('tokens'))} tokens")
        line("Today", fmt_cost(today.get("cost")))
        line("This week", fmt_cost(wk.get("cost")),
             f"→ ~{fmt_cost(pace.get('projected_week_cost'))} projected", C_GOOD)
        yy += 1
        safe_addstr(win, yy, bx + 3, "By model", cp(C_DIM) | curses.A_BOLD); yy += 1
        for m in bm[:5]:
            if yy >= by + bh - 2:
                break
            safe_addstr(win, yy, bx + 5, f"{model_name(m['model']):<8}", cp(C_ACCENT))
            safe_addstr(win, yy, bx + 15, fmt_cost(m.get("cost")), cp(C_TITLE))
            safe_addstr(win, yy, bx + 27, f"{fmt_tok(m.get('tokens'))} tokens",
                        cp(C_DIM))
            yy += 1
        safe_addstr(win, by + bh - 2, bx + 3, "press any key to close", cp(C_DIM))
        win.noutrefresh()
        curses.doupdate()
        win.getch()
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
                        cp(C_GOOD if dpid else C_DIM))
            safe_addstr(win, by + 4, bx + 3, "keep-awake", cp(C_TITLE))
            safe_addstr(win, by + 4, bx + 22,
                        f"PID {kpid} · running" if kpid else "not running",
                        cp(C_GOOD if kpid else C_DIM))
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
                ("recheck", "Re-check location now", ""),
                ("speedtest", "Run internet speed test", spval),
                ("refresh", "Refresh usage now", ""),
                ("plan", "Live plan limits (runs Claude)",
                 "on" if (s.get("settings") or {}).get("plan_enabled", True) else "off"),
                ("cost", "View cost breakdown", ""),
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
                    safe_addstr(win, yy, bx + 2, "─" * (bw - 4), cp(C_DIM))
                    continue
                sel = (r == idx)
                attr = (cp(C_ACCENT) | curses.A_REVERSE | curses.A_BOLD) if sel \
                    else cp(C_TITLE)
                mark = "› " if sel else "  "
                safe_addstr(win, yy, bx + 3,
                            (mark + label).ljust(bw - 19)[:bw - 19], attr)
                if val:
                    vc = C_GOOD if val in ("ON", "lid open", "lid-closed ok") \
                        else (C_DIM if val == "off" else C_TITLE)
                    safe_addstr(win, yy, bx + bw - 16, val[:13],
                                cp(vc) | (curses.A_REVERSE if sel else 0))
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
                    cost_modal(win, s)
                elif key == "procs":
                    if procs_modal(win, s) == "stopped":
                        return "quit"
                elif key == "stop":
                    if danger_confirm(
                            win, s,
                            "Stop the guard and restore Claude to a DIRECT, "
                            "unguarded connection?",
                            "This turns the guard off entirely, then quits."):
                        send({"cmd": "quit"})
                        return "quit"
                elif key == "quit":
                    return "quit"
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
                                if isinstance(x.get("ticks"), dict) else None))
                           for x in (ag.get("sessions") or [])
                           if isinstance(x, dict))),
              len(ag.get("needs_you") or []), len(ag.get("collisions") or []),
              summary.get("working"), summary.get("needs_you"),
              summary.get("done_today"))
    return (g.get("allowed"), g.get("blocked"), g.get("enforce"),
            g.get("block_all"), g.get("target_cc"), g.get("proxy_up"),
            (d.get("routing") or {}).get("installed"), ka.get("mode"),
            loc.get("status"), loc.get("in_target"), loc.get("city"),
            len(rec), rec[-1].get("t") if rec else None,
            pl.get("updated"), pl.get("refreshing"), pl.get("ok"),
            net.get("status"), net.get("raw_status"),
            _r(net.get("internet_ms")), _r(net.get("api_ms")),
            net.get("checked"), st.get("running"),
            round(prog * 50), st.get("at"),      # 2% steps → smooth, cheap
            ag_sig)


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
        h, w = win.getmaxyx()
        if h < 12 or w < 46:
            win.erase()
            safe_addstr(win, 0, 0, "Terminal too small —", cp(C_WARN))
            safe_addstr(win, 1, 0, f"need ≥46×12 (now {w}×{h})", cp(C_DIM))
            win.noutrefresh(); curses.doupdate()
            win.getch()
            continue
        now = time.time()
        s = read_state()
        if s:
            last = s
        # Repaint only when something changed, or ~2×/s for clocks & live rows.
        # While a Claude request is pending on the guard, repaint every tick so
        # the "Reconnecting Claude…" shimmer animates smoothly (~12fps).
        sig = _sig(last)
        pending = bool((last or {}).get("guard", {}).get("pending"))
        # A working agent's row shimmers; keep repainting every tick so it
        # animates smoothly (same cadence as the "Reconnecting Claude…" header).
        working_live = any(
            isinstance(x, dict) and x.get("status") == "working"
            for x in ((last or {}).get("agents") or {}).get("sessions") or [])
        if sig != sig_prev or now - last_draw > 0.5 or pending or working_live:
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
        # (the set documented in HELP / the help modal and hinted on the cards,
        # e.g. "[w] change"), the mouse, or the actions menu. `q` quits and
        # leaves the guard running; `Q` is the guarded off-switch (stop guard +
        # restore a direct Claude connection) and is double-confirmed. A key
        # that isn't a shortcut does nothing.
        st = last or {}
        if ch == ord("q"):
            return
        if ch == ord("Q"):
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
        elif ch == ord("$"):
            cost_modal(win, st)
            sig_prev = object()
        elif ch == ord("k"):
            send({"cmd": "recheck"})
            sig_prev = object()
        elif ch == ord("u"):
            send({"cmd": "refreshplan"})
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
