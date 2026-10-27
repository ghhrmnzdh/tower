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
| Single keys | `r` route · `e` enforce · `a` scope · `c`/`p` country · `w` keep awake · `d` Desktop · `W` Claude on the web · `k` re-check · `u` (or `$`) usage view · `?` help (the footer hints the ones that fit) |
| **Mouse click** | Act on what you clicked: in GUARD the `routed` / `enforced` / `Claude only` words toggle, the target country opens the picker, the Location row re-checks, the Awake row cycles keep-awake, the Desktop line relaunches it guarded; PLAN refreshes the real limits (its `≈ $` line opens the usage view); NETWORK runs a speed test; an agent row shows that agent's terminal; the footer opens the menu |
| **Scroll wheel** | Moves the selection in the menu and country picker; scrolls the usage view |

## The Actions menu
Everything you can *do* lives here. Move with `↑/↓` (or the wheel), select
with `Enter` (or a click), close with `Esc`. The bottom line says the one thing
worth knowing about the selected action where there is one (the web window's
own profile, why it's unavailable, that a Desktop relaunch quits it first):

| Action | What it does |
|---|---|
| Route Claude through the guard | Turn routing on/off (edits `settings.json`, not your shell) |
| Enforcement | Fail-closed: allow Claude only when confirmed in-country on a stable connection; block otherwise |
| Block scope | Block ALL traffic, or Claude only |
| Pin a country… | Opens the searchable country picker |
| Keep the Device awake | Cycle off → lid-open → lid-closed (no password) |
| Open Claude Desktop through the guard | Opens it with Tower's proxy; an unguarded Desktop is relaunched after a `y` confirm (`d`) — the item then reads *Relaunch…* and its value is an amber `UNGUARDED` |
| Open Claude on the web through the guard | claude.ai in a Chrome-family app window on **Tower's own profile** — guarded, but a separate sign-in (once), never your own browser profile; one key, no confirm (`W`). Shows `window open` while one is; `unavailable` with *needs Chrome, Brave, Edge or Chromium* when no such browser is installed |
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
  never padded to fill. Each panel has a **minimum**, a **calm** size (what an
  ordinary terminal shows) and a **maximum** (its richest variant); height
  goes to things that genuinely get richer (more agents and their details,
  full subagent trees, taller charts, the extra panels), and every column
  ends on the same row.

## Layout — size classes
Width picks the grid; height decides how much each panel holds. Within a
column rows go to panels **by priority**: every panel first gets a one-line
summary (`╶─ NETWORK   ● Online · internet 187ms · api 402ms ──╴`), then — most
important first — its useful minimum, then growth in phases:

1. every panel to its **calm** size — exactly what a small terminal has always
   shown (80×24 is unchanged);
2. the charts (NETWORK, USAGE's day chart) to a comfortable 3 rows;
3. every list and detail to its **maximum**, AGENTS first (whole subagent
   trees, then each live agent's last prompt `↳ "…"  up 3.5h`, then where it
   works `~/repo · ⎇ branch   5 files edited · 2 tool errors`, then resting
   agents by name), then GUARD, PLAN and the extras;
4. the charts to theirs (NETWORK up to 14 + 14 + 8 rows, the 7-day chart up to
   16).

Below its calm size a panel renders the richest variant that fits and then
keeps its highest-priority lines (subagent trees fold before any agent row,
hidden agents become `+N more agents`); above it, any height works (the next
richer variant, trimmed by priority — never a torn chart or tree). A cut line
ends in `…`. Resizing (`KEY_RESIZE`) re-lays out on the spot.

| Class | Size | Grid |
|---|---|---|
| **tiny** | < 60 cols or < 16 rows | One rounded status card: verdict + target, the verdict's reason, a Desktop gap if any, the top needs-you rows, `need you · working`, Session/Weekly %, net (with `N req/min` / `↻ N held` folded in), location. Under 24×5 the same lines without the box. |
| **compact** | 60–99 cols | One column: GUARD → AGENTS → PLAN → NETWORK, then the extras below as height allows. |
| **regular** | 100–179 cols (or < 30 rows) | Two columns. Left: GUARD, AGENTS. Right (≈ 40%, 46–72 cols): PLAN, NETWORK. |
| **wide** | 180–229 cols, ≥ 30 rows | Three: GUARD + AGENTS · PLAN · NETWORK. |
| **xwide** | ≥ 230 cols, ≥ 30 rows | Four: GUARD + AGENTS · PLAN · USAGE · NETWORK. Past 260 cols it caps and centers. |

**Extras.** After the anchors, USAGE, TIMELINE, WHERE YOUR LIMIT GOES and
REQUESTS are placed in that order (TIMELINE first on xwide, where USAGE is an
anchor), each in the column that could stand the least tall at full content —
a chart panel preferring a column that has none — and only where it fits with
at least four real lines without squeezing an anchor below its comfortable
size. So 80×24 stays the calm four; a tall or wide screen fills.

**Fill, then cap.** All columns of a grid end on the same row: the screen's,
or — when even the fullest column can't reach it — the height at which every
column is complete, with the whole dashboard (header, grid, footer) centered
on the screen. A wide screen with little to show fills better with fewer,
taller columns, so wide / xwide also weigh the narrower grids (and regular
weighs one column, for tall-narrow terminals like 100×120), keeping whichever
covers ≥ 20% more of the screen unless the class's own grid already reaches
within 6 rows of full. The choice is made on a resize and re-weighed every 30 s,
never per frame — the layout doesn't flip as agents come and go. On a quiet
machine (one agent, little history) a very large terminal (250×85, 300×100)
holds ~60 rows of real information per column: the dashboard stops there and
centers rather than padding.

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
  now). An unguarded running Claude Desktop is always an amber **Desktop
  running unguarded** row (`d relaunch`); with room GUARD adds the calm app
  rows below.
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
  `└─ ✓` once back). With room each agent also shows its last prompt
  dim (`↳ "…"  up 3.5h`) and the full tree. Click / select a row to bring that
  agent's terminal forward — that's the only agent action.
- **PLAN** — the **real** limits, mirrored from `claude -p /usage`: Session /
  Weekly / Fable as `Label  NN%  ━━━━╸────  ↻ 1h 48m` — the % bold right next
  to the label, a slim fixed-width meter (≤ 32 cells), the reset countdown dim
  after it, all three rows in the same columns; meter and % white below 60%,
  amber ≥ 60%, red ≥ 85%. The countdown is `until()`'s exact units (`now`,
  `42m`, `2h 14m`, `37h 5m` under 48h, `3d 4h`) under `↻`. Freshness sits in
  the title. With room: the reset's wall clock (`↻ 2h 14m  23:44`,
  `Sat 01:30`) where the meter keeps 12 cells, and `Last 24h` / `Last 7d`
  request and session counts from `/usage`. Under the meters, at most one dim
  line of the local estimate — `≈ $191 today · $301 week   local estimate` —
  only while USAGE isn't on screen (never the same number twice). When `/usage` is withheld (the
  guard isn't passing) the panel instead gives a spacious, honest message —
  *connection unstable* or *location not confirmed*, from `plan.gate_reason` /
  `guard.net_ok` — never stale numbers.
- **NETWORK** — a status dot + word (green `● Online`; amber *Degraded · slow
  path to Anthropic*; red *Offline* / *Wi-Fi login required* / *Anthropic
  unreachable*), then `Internet` and `API` rows: the current ms, bold and
  right-aligned (white; amber on a degraded path, red when failing), and ONE
  slim one-row gray sparkline per series (`▁▂▃▄▅▆▇█`, newest cell bright, each
  series on its own floored scale; a failed probe is a red cell). With room
  each series becomes a **solid bar chart** (`▁…█`, one bar per sample —
  bucket means when there are more samples than cells — every bar at least an
  eighth tall so the series reads as one silhouette; gray, newest bright, a
  failed probe a red full-height bar; peak top-right, floor bottom-right),
  growing with the column: Internet / API first, then Requests per minute as
  its own chart with `passed · held` and the newest request under it. The
  status line says how long the link has been in that state (`for 12m`), and a
  finished speed test adds a `Speed` row. Otherwise, ONE **Requests** row: `Requests   12/min  ▁▂▅▃▇▂  1,020 passed · 7 held` — Claude
  requests per minute as a gray sparkline (a history the TUI builds from
  `recent` while it runs), the current rate bold, the daemon's passed count and
  — only when > 0 — its held count (gray: it's history), plus the newest Claude request
  (`api.anthropic.com · 3s ago`) when it fits. While `guard.holding > 0` the
  row says only `↻ 2 held now — pending`, in amber. The title shows a speed
  test only while one runs; click runs one.

### Room-only panels (the extras)
- **USAGE** — the local estimate at API list prices (never your plan %):
  today / session / week / projected cost rows — the week runs from the
  plan's weekly reset (`since Tue 10:30 reset`; `since Monday` until `/usage`
  has been read; on a narrow panel that replaces the token count), and
  *Projected* is left out for the first day after a reset, when the daemon
  withholds it rather than extrapolate from a few hours — and the model mix (a
  tier-colored `●`, share bar in gray, cost); with room, `Pace` (tokens per
  active hour · hours active · per-minute now), the session's `Tokens` split
  (input · output · cache) and the week against your `Budget`; then seven days
  of spend — thin rows when short, a column chart with each day's cost under
  its bar (today bright) when tall. Replaces PLAN's one-line estimate while
  shown. Click → the usage view.
- **TIMELINE** — what happened while you looked away, as *moments*, not raw
  status flips: `turn done · 4m 12s`, `asked, then needed approval · waited
  4m 31s`, `failed`, `started` (with the session title) / `back to work`,
  `ended`. A done followed by more work within 90 s is one stretch;
  consecutive needs-you states are one wait. One time column — the relative
  age, right, dim. Color only for a moment that is still the session's state
  now (amber needs approval / has a question, red failed, green ✓ done); the
  history is gray. The project name only when more than one session is in
  view, once per group (one group per session, latest first). Shown only with
  two or more moments. Click → that agent.
- **WHERE YOUR LIMIT GOES** — Claude's own tips as ranked thin bars with their
  hint (wrapped in full when there's room), the top subagents / skills / MCP
  servers as ranked mini-bars, and Claude's caveat. Hidden (never stale) while
  the guard isn't passing.
- **REQUESTS** — who the guard talked to over the recent window, one row per
  host: Claude hosts first (white), other traffic dim, the count, held count
  (amber only while a Claude request is held right now), how long since the
  last one. Title: `50 in the last 4m`.

GUARD also grows with room: an `IP` row (when the address didn't fit beside
the place), `Desktop` guarded / not running (`d opens it guarded`) when it's
installed and fine — an unguarded Desktop is always the amber row above —
`Web` (`● Chrome window open`, or `claude.ai in a guarded Chrome window · W
opens it`; hidden when no Chrome-family browser is available), and
`Chats  N through the guard · M unguarded` (red) while routing is on. Both apps
are launchers, not monitors: Tower sees no activity from either.

## The usage view (`u`)
Everything the main screen leaves out, in the same monochrome grammar, as a
scrollable sheet (`↑/↓` or the wheel scroll, `r` refreshes the real limits, any
other key closes): **plan limits** with request / session counts for the last
24h and 7 days; **where your limit goes** — Claude's own tips as ranked %
bars with their hint (`· run /clear`), the top subagents / skills / MCP
servers, and Claude's caveat *approximate · this machine · shares overlap*;
and the **local estimate** at API list prices (never your plan %): session /
today / week (with the reset it runs from) / projected cost (`—` for the first
day after a reset), per-model share, seven days of spend as a
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
- **Unicode** — box drawing, slim `━` meters, sparklines, block-bar charts and marks on UTF-8 terminals;
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
it, re-timing just the shimmer/spin cells (~3–6 ms to compose, ~15 ms the
moment a resize re-weighs the grids; ~2% CPU while an agent animates). Each
chart series is drawn once per height per compose, and never taller than the
grid. state.json is re-parsed only when its mtime changes.

## Country picker
Type to filter, `↑/↓` or wheel to move, `Enter` or click to pin, `Esc` to
cancel. Scrolls and resizes to fit any window.
