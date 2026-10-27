# Tower — macOS Menubar App

A native (Swift + AppKit/SwiftUI, macOS 14+) menu-bar agent — no dock icon, no
browser. It reads `~/.tower/state.json` and drives the daemon via command
files, exactly like the terminal dashboard — see
**[ARCHITECTURE.md](ARCHITECTURE.md)**; the look and motion are specified in
**[DESIGN.md](DESIGN.md)**.

## Install
```sh
curl -fsSL https://ghhrmnzdh.github.io/tower/install.sh | sh
```
Installs to `/Applications` and launches. The app is ad-hoc signed, not notarized,
so a *browser* download gets quarantined and blocked as "unidentified developer" —
but a `curl` download never carries the quarantine flag, so Gatekeeper never
assesses it and the app just opens. `site/install.sh` is the script; `release.sh`
publishes the release it pulls from. To rescue a hand-downloaded copy:
`xattr -rd com.apple.quarantine /path/to/Tower.app`.

## Run
```bash
open "Tower.app"
```
or double-click **`Tower.app`** in Finder. The tower radar appears in the menu
bar; click it for the popover.

## Build from source
```bash
./build.sh        # compiles src/*.swift → Tower.app (~20s)
```
Requires Xcode Command Line Tools (`swiftc`) to build, and Python 3 at runtime.

## The menu-bar icon — the tower radar
The menu bar is a single mark, the **radar**, whose state *is* the guard
(full color — the amber/red brand tones are the signal, matching the popover):

| Radar | Meaning |
|---|---|
| **clear** — calm ring + blips | Guarding · in-country and a path to Anthropic is open |
| **verify** — a rotating sweep | Confirming your location; held until sure |
| **holdNet** — amber dashed ring + sonar pings | No usable path (offline / captive / API) — held pending, self-clears |
| **holdGeo** — amber ring + rotating fence + off-country blip | Wrong country / VPN — held, not failed |
| **off** — red dashed ring, hollow core | Routing off — Claude connects directly, **unguarded** |

In the menu bar it animates (~15fps) only while a state has motion to show — a hold, a
verify sweep, or a calm scan while agents are working — and freezes under Reduce
Motion. It also skips frames while the menu bar itself is hidden (a full-screen
app, a sleeping or locked display).

The popover and dashboard stay mounted when closed, so they are kept idle off
screen: `TowerModel` publishes its once-a-second snapshot to SwiftUI only while
one of them is visible (`popoverVisible` / `dashboardVisible`), and every
continuous animation — model marks, radar, beacon, shimmer, spinners — pauses on
`\.surfaceVisible`. Opening a surface catches it up, without animation, before it
is shown.

When **keep-awake** is holding the Mac, the radar's core lights — a soft, neutral **vigil
lamp** meaning "the tower is holding your Device awake." It's subliminal and never
amber/red, so a guard hold always outranks it: the two facts compose in one mark
instead of colliding. It's a still lit lamp while the lid may stay open, and
breathes slowly on a lid-closed vigil — in the popover and dashboard only. In the
menu bar both are a still lit lamp: keep-awake runs for hours, and must never keep
the bar's render clock going on its own. Keep-awake
holds only while agents work: armed with nothing to do, the core stays dark and
the row reads "Armed — the Mac sleeps normally until an agent works."

The bar **never counts running agents.** The only number it can show is the
**needs-you pill** — a filled badge (red when something failed, orange
otherwise) counting only what actually needs you: a failure, an approval, a
question. A finished turn never counts. It's switchable off in Settings. Then the
plan % beside a tiny ring that fills with it — Session, Week, or "Closest limit"
(whichever tracked limit is nearest) — never shown while the guard withholds
`/usage`, so it's never a stale number. Reset countdowns are exact: minutes, then
hours and minutes under 48h ("2h 14m", "37h 5m"), then "3d 4h".

## The popover (the glance)
Top to bottom (the middle is yours to reorder): a **status card** — the radar,
the verdict, where you're fenced, and the **route toggle** (tinted only on a hold
or danger; "Reconnecting Claude…" shimmers while a request is held) → **net
weather** (a reading strip — Internet · API; a verdict
banner when not fine — *"Anthropic API unreachable — your internet is fine
(23 ms)"*) → **Agents** (Needs You first: failed > approval > asking > your turn;
click a row to show that agent's terminal; hover to dismiss → collision banners → each working agent: its model
mark, project, live activity line, its `n ✓` counter, and its **subagents as a
tree** → Resting, collapsed) → **location** (a flag tile with an in/out badge,
city, ISP, IP, an animated re-check) → **Claude apps** (off by default; add
it in Settings): Claude Desktop — *Open*, or the amber *Relaunch guarded* while
it runs unguarded — and Claude on the web, claude.ai in a guarded Chrome-family
window on Tower's own profile (sign in once there); a hover ✕ hides the section
→ **keep awake** (the beacon and the
three-way switch) → **plan rings** (or, while the guard holds Claude, one calm *Usage paused* row
saying whether it waits on the connection or your location) (Session · Weekly · Fable, each with an exact
countdown — or slim bars, your pick; white until your warn line; hover for the
reset clock time; today's estimated cost rides the header) → a slim **footer** (Open Dashboard ⌘D, Settings ⌘,,
Terminal ⌘T, Quit ⌘Q — which still asks twice).

It's **yours to compose** — Settings → Popover: drag rows to reorder (the held
row lifts and follows the pointer; the rest glide aside on a spring), switch
each on or off (or right-click any section in the popover → Hide), pick rings or
bars and Comfortable / Compact, and toggle subagent trees, resting agents and
the IP. Settings → Plan limits chooses which limits you track (drop Fable if you
never use it).

## The dashboard window
A native macOS window: a source-list sidebar (Agents carries the needs-you
badge; the guard rides at its foot; collapsing it folds it to an icon rail), a
unified toolbar with each page's title, a live subtitle and its actions
(Re-check location, Run speed test, Refresh plan, **Open Claude** — Desktop or
the web through the guard, amber while Desktop runs unguarded — and Terminal
dashboard), and pages built from one panel vocabulary. It adapts
to its width — single column when narrow, panels paired two-up from ~640 pt of
content, columns past ~820 pt, three columns past ~1240 pt — and caps content
width so a huge window stays legible. Its size and place are remembered.

Five pages: **Overview** (a glance sized to the window, never a page you
scroll, that grows with it: the guard with its switch, the live agents — click
one to show its terminal; the list scrolls inside its panel — and plan rings +
network beside it; a taller window adds **Requests** (Claude's per-minute
pulse, passed / held counts, the newest requests, holds in amber); a wide one
adds a third column with the cost estimate and, given height, the week —
whichever panel can use height absorbs the rest, so the columns end together), **Agents** (Mail-style master–detail that stacks the list above the
inspector in a narrow window: grouped list — Needs you / Working / Resting —
with right-click Show Terminal / Dismiss, and an inspector laid out by its own
width: status and how long, branch, what it's doing, tools / files /
subagents / errors, every subagent, what it was asked, health, details, its own
timeline), **Network** (verdict hero, hover-able dual-series latency chart,
speed test, live traffic), **Usage** (two even rows: plan limits as slim bars with exact countdowns beside
the cost estimate — today, session, this week (since Monday), its pace, and the
mix by model; then the last 7 days in dollars beside **Where your limits go** —
Claude's top `/usage` suggestions by share and its top subagent / skill / MCP
server, 24 h or 7 d. Monochrome; yellow/red only past your lines), **Settings** (one short grouped form: guard; menu bar — what it shows, the
needs-you badge, the yellow/red lines; popover — its sections in drag-to-reorder
rows, rings or bars, density, a few details; plan limits to track and live
reads; version + reset).

## Notifications
Fired on agent transitions: →failed / →blocked / →asking always; →done only
when you haven't opened the popover in the last 60s. A →done body carries the
agent's result. Transitions older than ~3 minutes are never toasted — a sleep or
App-Nap backlog resolves into each agent's timeline, not a burst of late
banners — except a still-open failed/blocked/asking, which stays
worth showing because it's still awaiting you. (To keep those timers honest while
the menubar app is inactive, Tower holds an App-Nap exemption that still allows
idle system sleep.) Clicking one focuses that agent's terminal. If you deny
notification permission, the menubar badge carries the signal alone — Tower never
nags.

## Quit
`Cmd-Q` (or the Quit button) **asks first**, then tells the daemon to quit so
routing is removed and Claude returns to a direct connection.

## Parity note
The app and the terminal dashboard are kept feature-matched (same daemon, same
commands); the TUI's agent view is a compact card for now. If you change a
setting in one, the other reflects it within ~1s.
