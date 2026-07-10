"""
_wincurses — a tiny curses-compatible shim for tower-tui.py on Windows.

curses is not in the Windows stdlib. Rather than rewrite the 1500-line TUI, this
module emulates *exactly* the curses subset the TUI touches, over ANSI/VT escape
sequences (output) and msvcrt (input). tower-tui.py does:

    if os.name == "nt":
        import _wincurses as curses
    else:
        import curses

and needs no other change — every `curses.*` call and window method it uses is
implemented here. Mouse is intentionally a no-op: mousemask() raises `error`, so
the TUI's existing `try/except curses.error` disables mouse and the keyboard
(which drives every action) carries the UI.

Pure stdlib: msvcrt + a little ctypes (via _win) for VT/UTF-8 enablement.

Only meaningful on Windows.
"""

import shutil
import sys
import time

import msvcrt

import _win


# --------------------------------------------------------------------------- #
# Constants (values chosen to match ncurses so any stray comparison still works)
# --------------------------------------------------------------------------- #
class error(Exception):
    """Raised where ncurses would raise curses.error (e.g. mouse unavailable)."""


A_NORMAL = 0
A_BOLD = 0x10000
A_DIM = 0x20000
A_REVERSE = 0x40000

COLOR_BLACK = 0
COLOR_RED = 1
COLOR_GREEN = 2
COLOR_YELLOW = 3
COLOR_BLUE = 4
COLOR_MAGENTA = 5
COLOR_CYAN = 6
COLOR_WHITE = 7

KEY_DOWN = 258
KEY_UP = 259
KEY_LEFT = 260
KEY_RIGHT = 261
KEY_BACKSPACE = 263
KEY_ENTER = 343
KEY_MOUSE = 409
KEY_RESIZE = 410

# Mouse bitmasks — defined only so the TUI's module-level `MOUSE_B1 = ...`
# expression evaluates at import time. Mouse events are never actually produced.
BUTTON1_PRESSED = 0x0002
BUTTON1_CLICKED = 0x0004
BUTTON4_PRESSED = 0x080000
BUTTON5_PRESSED = 0x200000

_SGR_FG = {-1: 39, 0: 30, 1: 31, 2: 32, 3: 33, 4: 34, 5: 35, 6: 36, 7: 37}

# Special-key scancodes following an msvcrt 0x00 / 0xE0 prefix byte.
_SPECIAL = {"H": KEY_UP, "P": KEY_DOWN, "K": KEY_LEFT, "M": KEY_RIGHT}

_pairs = {0: (-1, -1)}       # pair id -> (fg, bg); pair 0 is default-on-default


# --------------------------------------------------------------------------- #
# Module-level curses functions
# --------------------------------------------------------------------------- #
def start_color():
    pass


def use_default_colors():
    pass


def init_pair(pair_id, fg, bg):
    _pairs[pair_id] = (fg, bg)


def color_pair(pair_id):
    return (pair_id & 0xFF) << 8


def curs_set(visibility):
    sys.stdout.write("\x1b[?25l" if not visibility else "\x1b[?25h")
    sys.stdout.flush()


def mousemask(*_a):
    # No mouse support — signal "unavailable" exactly as ncurses would when the
    # terminal can't do mouse, so the TUI's try/except curses.error path fires.
    raise error("mouse not supported")


def mouseinterval(*_a):
    return 0


def getmouse():
    return (0, 0, 0, 0, 0)


def doupdate():
    if _Window.current is not None:
        _Window.current._flush()


def wrapper(func, *args, **kwargs):
    """Set up the console (VT + UTF-8, alternate screen, hidden cursor), run
    func(stdscr, *args), and always restore the console on the way out."""
    _win.enable_vt_and_utf8()
    out = sys.stdout
    out.write("\x1b[?1049h")     # alternate screen buffer
    out.write("\x1b[?25l")       # hide cursor
    out.write("\x1b[2J\x1b[H")   # clear
    out.flush()
    win = _Window()
    _Window.current = win
    try:
        return func(win, *args, **kwargs)
    finally:
        out.write("\x1b[0m")
        out.write("\x1b[?25h")   # show cursor
        out.write("\x1b[?1049l")  # leave alternate screen
        out.flush()
        _Window.current = None


# --------------------------------------------------------------------------- #
# The one window (stdscr)
# --------------------------------------------------------------------------- #
class _Window:
    current = None

    def __init__(self):
        self._timeout = -1       # <0 blocking, 0 non-blocking, >0 ms
        self._h, self._w = 0, 0
        self._pending = []       # rows of (char, attr) — the frame being built
        self._shown = []         # rows currently on the physical screen
        self._resize()

    # -- geometry ------------------------------------------------------------ #
    def _resize(self):
        cols, lines = shutil.get_terminal_size(fallback=(80, 24))
        if lines == self._h and cols == self._w and self._pending:
            return False
        self._h, self._w = lines, cols
        self._pending = [[(" ", 0)] * cols for _ in range(lines)]
        self._shown = [None] * lines            # force a full repaint
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()
        return True

    def getmaxyx(self):
        self._resize()
        return self._h, self._w

    # -- drawing ------------------------------------------------------------- #
    def erase(self):
        self._pending = [[(" ", 0)] * self._w for _ in range(self._h)]

    def addstr(self, y, x, text, attr=0):
        if y < 0 or y >= self._h or x < 0 or x >= self._w:
            return
        row = self._pending[y]
        for ch in text:
            if x >= self._w:
                break
            if ch == "\n" or ch == "\r":
                break
            row[x] = (ch, attr)
            x += 1

    def noutrefresh(self):
        # In ncurses this copies the window to the virtual screen; here the
        # pending buffer already IS that virtual screen, so doupdate does it all.
        pass

    def _sgr(self, attr):
        pair = (attr >> 8) & 0xFF
        fg, _bg = _pairs.get(pair, (-1, -1))
        codes = ["0"]
        if attr & A_BOLD:
            codes.append("1")
        if attr & A_DIM:
            codes.append("2")
        if attr & A_REVERSE:
            codes.append("7")
        codes.append(str(_SGR_FG.get(fg, 39)))
        return "\x1b[" + ";".join(codes) + "m"

    def _flush(self):
        out = []
        for y in range(self._h):
            row = self._pending[y]
            if self._shown[y] == row:
                continue
            out.append(f"\x1b[{y + 1};1H")
            cur_attr = None
            buf = []
            for ch, attr in row:
                if attr != cur_attr:
                    buf.append(self._sgr(attr))
                    cur_attr = attr
                buf.append(ch)
            buf.append("\x1b[0m\x1b[K")      # reset + clear to end of line
            out.append("".join(buf))
            self._shown[y] = list(row)
        if out:
            sys.stdout.write("".join(out))
            sys.stdout.flush()

    # -- input --------------------------------------------------------------- #
    def nodelay(self, flag):
        self._timeout = 0 if flag else -1

    def timeout(self, ms):
        self._timeout = ms

    def _read_key(self):
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):           # special-key prefix
            ch2 = msvcrt.getwch()
            return _SPECIAL.get(ch2, -1)
        if ch == "\x03":                     # Ctrl-C — match curses/KeyboardInterrupt
            raise KeyboardInterrupt
        if ch == "\x7f":                     # some terminals send DEL for backspace
            return KEY_BACKSPACE
        return ord(ch) if ch else -1

    def getch(self):
        t = self._timeout
        if t is None or t < 0:               # blocking
            while not msvcrt.kbhit():
                time.sleep(0.005)
            return self._read_key()
        if t == 0:                           # non-blocking
            return self._read_key() if msvcrt.kbhit() else -1
        deadline = time.time() + t / 1000.0  # wait up to t ms
        while time.time() < deadline:
            if msvcrt.kbhit():
                return self._read_key()
            time.sleep(0.005)
        return -1
