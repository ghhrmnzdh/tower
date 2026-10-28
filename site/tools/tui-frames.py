"""Re-render the terminal frames the site replays, from the REAL dashboard.

src/tower-tui.py is imported (never run) and its compose() is called against
the fictional working day in fixture.py, at each size class plus one held
screen. The frames are spliced into every page's
<script type="application/json" id="tuiData"> block, so the site shows exactly
what `tower` draws. No daemon is touched and nothing under your real HOME is
read: HOME points at an empty temp dir for the run.

    python3 site/tools/tui-frames.py              # both editions
    python3 site/tools/tui-frames.py --check      # exit 1 if a page is stale

Run it whenever the TUI's layout changes. Not published (deploy strips tools/).
"""
import copy, curses, importlib.util, json, os, re, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PAGES = [os.path.join(ROOT, "site", "index.html"),
         os.path.join(ROOT, "site", "fa", "index.html")]
SIZES = [("tiny", 11, 56), ("compact", 26, 84), ("regular", 36, 132),
         ("wide", 46, 196), ("xwide", 54, 246)]

os.environ["HOME"] = tempfile.mkdtemp(prefix="tower-site-")
sys.path.insert(0, HERE)
import fixture  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "tui", os.path.join(ROOT, "src", "tower-tui.py"))
tui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tui)
BOLD, DIM = curses.A_BOLD, curses.A_DIM
tui.cp = lambda n: (n << 8) | tui._PAIR_ATTR.get(n, 0)   # keep the pair number
tui.COLOR = True
tui.MOTION = True


def enc(fr):
    """A frame as [y, x, text, pair, style(1 bold | 2 dim), fx?] ops."""
    ops = []
    for y, x, t, attr, fx in fr.ops:
        op = [y, x, t, (attr >> 8) & 0xFF,
              (1 if attr & BOLD else 0) | (2 if attr & DIM else 0)]
        if fx:
            op.append(["spin", list(fx[1]), fx[2]] if fx[0] == "spin"
                      else ["shim", fx[1]])
        ops.append(op)
    return {"h": fr.h, "w": fr.w, "ops": ops}


def frames():
    # One fixed instant, so a re-run draws the same frames and --check is exact
    # (the charts bin by wall time and drifted minute to minute). The page swaps
    # the header clock for the visitor's own; nothing else reads as a date.
    now = 1793173260.0
    state = fixture.build(now)
    out = {}
    for name, h, w in SIZES:
        tui._GRID.clear()
        out[name] = enc(tui.compose(state, h, w, now))
    held = copy.deepcopy(state)          # the same screen during a net hold
    held["guard"].update(net_ok=False, claude_allowed=False, pending=True,
                         holding=3)
    held["net"].update(status="api_issue", raw_status="api_issue",
                       reason="Anthropic edge unreachable", api_ms=None,
                       api_error="timeout")
    held["plan"]["gate_reason"] = "net"
    tui._GRID.clear()
    out["hold"] = enc(tui.compose(held, 36, 132, now))
    return out


BLOCK = re.compile(r'(<script type="application/json" id="tuiData">)(.*?)(</script>)',
                   re.S)


def shape(js):
    """What --check compares: the frames minus the clocks and live times that
    move with every run."""
    t = re.sub(r'\d{1,2}:\d\d', 'T', js)
    return re.sub(r'\d+(\.\d+)?[smhd]\b|\d+m \d\ds|\d+h \d\dm', 'D', t)


def main():
    js = json.dumps(frames(), ensure_ascii=False, separators=(",", ":"))
    js = js.replace("</", "<\\/")
    check, stale = "--check" in sys.argv, []
    for page in PAGES:
        if not os.path.exists(page):
            continue
        html = open(page, encoding="utf-8").read()
        m = BLOCK.search(html)
        if not m:                        # a page that replays no terminal
            print("no frames in", os.path.relpath(page, ROOT), "- skipped")
            continue
        if check:
            if shape(m.group(2)) != shape(js):
                stale.append(page)
            continue
        html = html[:m.start(2)] + js + html[m.end(2):]
        open(page, "w", encoding="utf-8").write(html)
        print("frames →", os.path.relpath(page, ROOT))
    if stale:
        sys.exit("stale TUI frames: " + ", ".join(os.path.relpath(p, ROOT) for p in stale))


if __name__ == "__main__":
    main()
