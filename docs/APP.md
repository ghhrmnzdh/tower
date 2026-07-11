# Tower — macOS Menubar App

A native (Swift + AppKit/SwiftUI, macOS 14+) menu-bar agent — no dock icon, no
browser. It reads `~/.tower/state.json` and drives the daemon via command
files, exactly like the terminal dashboard — see
**[ARCHITECTURE.md](ARCHITECTURE.md)**; the look and motion are specified in
**[DESIGN.md](DESIGN.md)**.

## Run
```bash
open "Tower.app"
```
or double-click **`Tower.app`** in Finder. The tower radar appears in the menu
bar; click it for the popover.

> **First launch:** it's ad-hoc signed (not notarized), so macOS may block it —
> **right-click → Open → Open** once, then normal launch works.

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

It animates smoothly (~30fps) only while a state has motion to show — a hold, a
verify sweep, or a calm scan while agents are working — and freezes under Reduce
Motion.

When **keep-awake** is on, the radar's core lights — a soft, neutral **vigil
lamp** meaning "the tower is holding your Device awake." It's subliminal and never
amber/red, so a guard hold always outranks it: the two facts compose in one mark
instead of colliding. It's a still lit lamp while the lid may stay open, and
breathes slowly on a lid-closed vigil.

The bar **never counts running agents.** The only number it can show is the
**needs-you count** (red when something failed, orange otherwise) — and even
that is switchable off in Settings — then the usage % if that preference is on.

## The popover (the glance)
Flat rows, top to bottom: guard status + **route toggle** → net weather (one
quiet latency line when fine; a verdict banner when not — *"Anthropic API
unreachable — your internet is fine (23 ms)"*) → **Needs You** (failed >
blocked > asking > done; click a row to focus that terminal, or copy the
resume command for background agents; hover to dismiss) → collision banners →
**Agents** (each working agent: its model mark, project, live
activity line — the model's own step description, or "thinking…" between tools —
and its `n ✓` momentum counter; a done row shows the agent's result, not your
prompt) → Resting (collapsed) → location (+
re-check button) → **keep awake** (the beacon lamp + what it means in plain
words; tap to cycle Off / lid-open / lid-closed) → plan meters → footer
(Dashboard / Settings / Quit).

Which sections show, and how tight (Comfortable / Compact), is **yours to
compose** — Settings → Popover, with a live miniature that settles with the same
spring as you flip each switch. The order stays fixed (it encodes attention);
you choose *what shows*, not what outranks what.

## The dashboard window
Five tabs: **Overview** (status + all guard controls + a **keep-awake card** +
counters), **Network** (dual-series latency chart, speed test, live traffic
feed), **Usage** (plan limits + refresh, local cost estimate, per-model
breakdown, 7-day chart), **Tower** (every session in full detail, collisions,
"while you were away" event history), **Settings** (menu-bar mode + needs-you
badge, thresholds, **Popover composition with a live preview**, live plan
toggle, country, reset).

## Notifications
Fired on agent transitions: →failed / →blocked / →asking always; →done only
when you haven't opened the popover in the last 60s. A →done body carries the
agent's result. Transitions older than ~3 minutes are never toasted — a sleep or
App-Nap backlog resolves into the dashboard's "while you were away" list, not a
burst of late banners — except a still-open failed/blocked/asking, which stays
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
