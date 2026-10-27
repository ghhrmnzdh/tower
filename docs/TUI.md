# Tower — Terminal Dashboard

A zero-dependency (`curses`, stdlib only) terminal front-end for the guard. It
renders `~/.tower/state.json` and drives the daemon by dropping command
files — see **[ARCHITECTURE.md](ARCHITECTURE.md)**.

## Run
```bash
tower
```
That's `src/tower` — a tiny `sh` shim that ships in the bundle at
`Contents/Resources/tower`, which `site/install.sh` symlinks onto your PATH. It
resolves its own symlink to find the bundle it lives in, so it works from
anywhere; failing that it looks in `/Applications` and `~/Applications`. From the
menu-bar popover, **Terminal Dashboard…** runs the same thing: the app hands
`Contents/Resources/Tower Terminal.command` to LaunchServices and Terminal
executes it (deliberately not an AppleScript `tell application "Terminal"` —
that's an Apple Event, and would trigger an Automation permission prompt).

The TUI is pure stdlib Python, so it needs no build at all — from a bare source
checkout, run it directly:
```bash
python3 src/tower-tui.py
```
If the daemon isn't running it starts it (single-instance, so this is safe).

## First run — onboarding
On first launch you get a short setup screen (with the exact command above so
you can reopen it later):
- **[p] pick country** — choose & pin the country to enforce.
- **[r] routing on/off** — whether `claude` runs go through the guard
  automatically. ON = every `claude` is routed; OFF = Claude connects directly.
- **[Enter] open dashboard.**

Your choices are remembered — subsequent launches go **straight to the
dashboard**. (To see onboarding again, delete `~/.tower/.tui_seen`.)

## The dashboard is deliberately non-reactive — but clickable
A stray keypress does **nothing**, so you can't accidentally toggle routing by
fat-fingering a key. Deliberate gestures work:

| Gesture | Action |
|---|---|
| `Enter` (or `m` / `space`) | Open the **Actions menu** |
| `q` | Quit the dashboard (the guard keeps running) |
| `Q` | Stop the guard and restore a direct connection — double-confirmed |
| Single keys | `r` route · `e` enforce · `a` scope · `c`/`p` country · `w` keep awake · `d` Desktop · `k` re-check · `u` (or `$`) usage view · `?` help (the footer hints the ones that fit) |
| **Mouse click** | Act on what you clicked: in GUARD the `routed` / `enforced` / `Claude only` words toggle, the target country opens the picker, the Location row re-checks, the Awake row cycles keep-awake, the Desktop line relaunches it guarded; PLAN refreshes the real limits (its `≈ $` line opens the usage view); NETWORK runs a speed test; an agent row shows that agent's terminal; the footer opens the menu |
| **Scroll wheel** | Moves the selection in the menu and country picker; scrolls the usage view |

## The Actions menu
Everything you can *do* lives here. Move with `↑/↓` (or the wheel), select
with `Enter` (or a click), close with `Esc`:

| Action | What it does |
|---|---|
| Route Claude through the guard | Turn routing on/off (edits `settings.json`, not your shell) |
| Enforcement | Fail-closed: allow Claude only when confirmed in-country on a stable connection; block otherwise |
| Block scope | Block ALL traffic, or Claude only |
| Pin a country… | Opens the searchable country picker |
| Keep the Device awake | Cycle off → lid-open → lid-closed (no password) |
| Open Claude Desktop through the guard | Opens it with Tower's proxy; an unguarded Desktop is relaunched after a `y` confirm (`d`) |
| Re-check location now | Immediate location lookup **and** a fresh net probe |
| Run internet speed test | 25 MB download, direct connection; shows running % / cooldown / last Mbps |
| Refresh usage now | Re-run `claude -p /usage` immediately |
| Live plan limits | Turn the `/usage` fetch on/off |
| Usage & cost details… | The usage view (same as `u`) |
| Background processes… | See the daemon & keep-awake PIDs; **stop** them |
| Stop guard & restore Claude, then quit | Removes routing and exits everything |
| Quit dashboard | Exit; guard keeps running |

Anything that lets Claude reach the API without the guard — route off, enforce
off, stop guard (`Q`, the menu, or Background processes → `s`) — opens a red
alert **twice**: `y` to continue, then `Y` again; any other key cancels. The
alert names how many agents are working right now and, for stop/quit, how many
open chats are pinned to the proxy. Its text wraps in full (on a screen too
small for the box, it's bottom-anchored with the `[y/N]` keys always visible).
Turning the guard *on* is one key.

## Design — monochrome, color where it matters
The TUI follows the app's direction (docs/DESIGN.md). On small and medium
screens it shows only what you glance at — **guard, agents, plan, network** —
and everything else sits one key away. On big screens it uses the room: a
dense, terminal-native dashboard in the same language (see the size classes).

- **Color is meaning, never decoration.** Text is the terminal's own
  foreground plus three grays (meta, charts, structure); bold carries the
  values. Color appears only where it says something:
  - the **verdict + radar**: green when Protected, amber when held /
    verifying, red when off / unguarded (a held request turns a green
    header amber — one loudest thing);
  - **amber** = held / warn (a plan meter and its % at ≥ 60%, needs-approval
    and asking marks, held requests, a degraded path's latency), **red** =
    failed / unguarded / danger (≥ 85%, a failed agent, a failing path's
    latency, a failed probe's chart cell), **green** = the small `●` "on /
    healthy" dot and a done `✓`;
  - **the mark is the model**: an agent's model mark — and the small `●` by a
    model in USAGE — wears its tier color (Opus rosso, Sonnet steel, Haiku
    crayon, Fable gold; nearest basic hue on 8/16-color terminals). Only the
    glyph; the name beside it stays white.
  - **live**: every sparkline and chart is gray with its newest cell bright.
  No accent hue anywhere — meters, bars, numbers and selections are white/gray.
- **One grammar.** Every row is `Label` (normal weight, one shared 11-cell
  column) → **value** (bold) → meta (dim), with numbers right-aligned. Meters
  are a slim `━` (half-cell `╸` precise) over a dim `─` track. Panel borders
  are rounded and dim; panel titles are small dim caps.
- **Panels are sized to content.** A box is exactly its lines plus border —
  never padded to fill. Extra rows go to things that genuinely get richer with
  height (more agents, full subagent trees, a taller latency chart, a longer
  request log, the timeline); when the content runs out the rest stays as
  calm empty screen below the panels, never blank rows inside a box.

## Layout — size classes
Within a column rows go to panels **by priority**: every panel first gets a
one-line summary (`╶─ NETWORK   ● Online · internet 187ms · api 402ms ──╴`),
then — most important first — its useful minimum, then room to grow up to its
content. Each panel renders the richest variant that fits, and below its
smallest variant keeps its highest-priority lines — so subagent trees fold
away before any agent row, and hidden agents become `+N more agents`. A cut
line ends in `…`. Resizing (`KEY_RESIZE`) re-lays out on the spot. Each class
is a superset of the one before it.

| Class | Size | Layout |
|---|---|---|
| **tiny** | < 60 cols or < 16 rows | One rounded status card: verdict + target, the verdict's reason, a Desktop gap if any, the top needs-you rows, `need you · working`, Session/Weekly %, net (with `N req/min` / `↻ N held` folded in), location. Under 24×5 the same lines without the box. |
| **compact** | 60–99 cols | One column, calm: GUARD → AGENTS → PLAN → NETWORK. |
| **regular** | 100–179 cols | Two columns, calm. Left: GUARD, AGENTS. Right (≈ 40%): PLAN, NETWORK. One blank row between panels when it fits. |
| **tall** | 140–179 cols and ≥ 40 rows | The regular columns, dense: NETWORK's latency becomes a real chart, AGENTS adds each agent's last prompt and full trees, and TIMELINE (left) and REQUESTS (right) take the height below. |
| **wide** | 180–229 cols, ≥ 30 rows | Three dense columns. Anchors: GUARD + AGENTS · PLAN · NETWORK + REQUESTS. USAGE, WHERE YOUR LIMIT GOES and TIMELINE then go, in that order, to whichever of the first two columns is shorter. |
| **xwide** | ≥ 230 cols, ≥ 30 rows | Four dense columns. Anchors: GUARD + AGENTS · PLAN · USAGE · NETWORK + REQUESTS; WHERE YOUR LIMIT GOES, SYSTEM and TIMELINE go to the shortest of the first three. Past 260 cols the grid caps and centers. |

The balancing keeps the columns close in height; they end together only when
there is content to fill them (a quiet machine has little to show, and the
grid never pads).

Every class shares a quiet **header** — the radar glyph, `TOWER`, the verdict
(shimmering amber *Reconnecting Claude…* while a request is held), then
`! N need you` (amber), `● N working`, `awake`, and a clock, dropping the
least important chips first — and a dim **footer** of key hints (as many as
fit; click → menu). On a tall screen (≥ 30 rows) a blank row frames the
panels top and bottom.

## What the dashboard shows
- **Header verdict** — the guard status, except that net faults outrank it: a
  red *Internet down / Wi-Fi login required / Anthropic API issue* means *stop
  and look* (a merely slow link stays in NETWORK). The radar glyph is the app's
  five looks: green `◉` clear (still), a sweeping `◴◷◶◵` verify, amber `◌` net
  hold / `◎` geo hold, red `⊘` off. A daemon that stops writing state reads
  *Tower daemon not responding*.
- **GUARD** — one strong status line (radar + verdict, `target <country>`
  right), one honest sentence on why, `↻ N Claude requests held — pending`
  while any are, then three rows: **Location** (place, with IP · ISP right when
  it fits; amber *outside Canada* when off-country; uncertain is held, never
  "not blocking"), **Guard** (`● routed · enforced · Claude only`, proxy port
  right; red `○ direct` / amber `monitor only` / red `proxy down` when they
  mean something) and **Awake** (`● on` / `◐ armed` / `○ off` + what it's doing
  now). Claude Desktop appears only as an amber **Desktop running unguarded**
  row (`d relaunch`); nothing else about it is on screen.
- **AGENTS** — the collision banner (⚠ two agents in one repo / same file) and
  any unguarded-chats line first; then **needs you** (red ✗ failed · amber !
  needs approval · amber ? has a question — the only rows counted as "need
  you"), then working agents, then quieter *your turn* rows (green ✓ done —
  with the result — or waiting for the next prompt) and paused ones, then
  `◌ N resting · names`. Each row is
  `mark  project  Opus 5.5 · High  activity … N tools  4m 12s` in aligned
  columns: the model mark, in its tier color, is alive while it works (Opus
  orbits, Sonnet turns, Haiku breathes, Fable winds), the activity shimmers
  only while a tool is in flight (not while thinking, not while the header
  reconnects), and the right side is the turn clock (tools count when there's
  room). The model column drops on a narrow panel. Subagents hang under the
  project as a dim tree (`├─ ● Explore  <brief> · <activity>   42s`, a green
  `└─ ✓` once back). On dense screens each agent also shows its last prompt
  dim (`↳ "…"  up 3.5h`) and the full tree. Click / select a row to bring that
  agent's terminal forward — that's the only agent action.
- **PLAN** — the **real** limits, mirrored from `claude -p /usage`: Session /
  Weekly / Fable as `Label  NN%  ━━━━╸────  ↻ 1h 48m` — the % bold right next
  to the label, a slim fixed-width meter (≤ 32 cells), the reset countdown dim
  after it, all three rows in the same columns; meter and % white below 60%,
  amber ≥ 60%, red ≥ 85%. The countdown is `until()`'s exact units (`now`,
  `42m`, `2h 14m`, `37h 5m` under 48h, `3d 4h`) under `↻`. Freshness sits in
  the title. Under the meters, at most one dim line of the local estimate:
  `≈ $191 today · $301 week   local estimate`. When `/usage` is withheld (the
  guard isn't passing) the panel instead gives a spacious, honest message —
  *connection unstable* or *location not confirmed*, from `plan.gate_reason` /
  `guard.net_ok` — never stale numbers.
- **NETWORK** — a status dot + word (green `● Online`; amber *Degraded · slow
  path to Anthropic*; red *Offline* / *Wi-Fi login required* / *Anthropic
  unreachable*), then `Internet` and `API` rows: the current ms, bold and
  right-aligned (white; amber on a degraded path, red when failing), and ONE
  slim one-row gray sparkline per series (`▁▂▃▄▅▆▇█`, newest cell bright, each
  series on its own floored scale; a failed probe is a red cell). On dense
  screens each series becomes a 2–5 row braille line chart (resampled to the
  width and lightly smoothed so it reads as a trend, newest cell bright, peak
  top-right and fastest bottom-right, a failed probe a red column). Last, ONE
  **Requests** row: `Requests   12/min  ▁▂▅▃▇▂  1,020 passed · 7 held` — Claude
  requests per minute as a gray sparkline (a history the TUI builds from
  `recent` while it runs), the current rate bold, the daemon's passed count and
  — only when > 0 — its held count in amber, plus the newest Claude request
  (`api.anthropic.com · 3s ago`) when it fits. While `guard.holding > 0` the
  row says only `↻ 2 held now — pending`, in amber. The title shows a speed
  test only while one runs; click runs one.

### Dense-only panels
- **REQUESTS** — the request log from `recent`, newest first:
  `time  host  claude/other  ×N   passed|held` in fixed columns (a run of
  identical requests folds into one `×N` row); Claude hosts white, other
  traffic dim, held rows amber. Title: passed · held counters.
- **USAGE** — the local estimate at API list prices (never your plan %):
  today / session / week / projected cost rows, the model mix (a tier-colored
  `●`, share bar in gray, cost), and seven days of spend as thin bars with
  today bright. Click → the usage view.
- **WHERE YOUR LIMIT GOES** — Claude's own tips as ranked thin bars with their
  hint, the top subagents / skills / MCP servers as ranked mini-bars, and
  Claude's caveat. Hidden (never stale) while the guard isn't passing.
- **SYSTEM** (xwide) — country (green dot when in target, amber when not),
  place, IP, ISP, proxy port, scope, keep-awake policy, Desktop.
- **TIMELINE** — agent state changes newest first (`20:52  !  tower  needs
  approval   2m ago`), marks colored by what they mean; click → that agent.

## The usage view (`u`)
Everything the main screen leaves out, in the same monochrome grammar, as a
scrollable sheet (`↑/↓` or the wheel scroll, `r` refreshes the real limits, any
other key closes): **plan limits** with request / session counts for the last
24h and 7 days; **where your limit goes** — Claude's own tips as ranked %
bars with their hint (`· run /clear`), the top subagents / skills / MCP
servers, and Claude's caveat *approximate · this machine · shares overlap*;
and the **local estimate** at API list prices (never your plan %): session /
today / week / projected cost, per-model share, seven days of spend as a
sparkline, and pace. While the guard isn't passing it shows the same honest
gate message as PLAN.

Every field is optional: an older daemon without `net` / `agents` / `apps` /
`plan.windows` simply gets fewer panels or lines.

## Terminal support
- **Color** — monochrome: the terminal's foreground plus tuned 256-color grays,
  with amber / red / green and the four model tiers reserved for meaning; on
  8/16-color terminals the grays become bright-black or dimmed white and the
  tiers the nearest basic hue; bold/dim only when there's no color or
  `NO_COLOR` is set.
- **Unicode** — box drawing, slim `━` meters, sparklines, braille charts and marks on UTF-8 terminals;
  an ASCII twin of every glyph at the same width otherwise (or with
  `TOWER_ASCII=1`). Widths are measured in terminal cells, so CJK/emoji in an
  agent's activity never pushes a border out.
- **Motion** — `TOWER_REDUCE_MOTION=1` freezes every shimmer and mark at a
  still frame and stops the per-tick repaint.
- **Windows** — runs on the `_wincurses` shim (no mouse; the keyboard drives
  everything).

## Performance
Input is instant (~80ms tick), the daemon confirms actions in ~60ms, and the
screen only repaints when something actually changes (mouse adds no idle cost —
no motion tracking, just a click-time hitbox lookup). A screen is composed at
most once per second (or when state.json / the size changes) into a list of
draw ops; animation ticks — only while something on screen animates — replay
it, re-timing just the shimmer/spin cells (~2 ms to compose even 300×90, ~2% CPU
while an agent animates). state.json is re-parsed only when its mtime changes.

## Country picker
Type to filter, `↑/↓` or wheel to move, `Enter` or click to pin, `Esc` to
cancel. Scrolls and resizes to fit any window.
