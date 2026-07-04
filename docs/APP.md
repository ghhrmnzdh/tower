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
Motion. Badge text next to it: the **needs-you count** (red when something
failed, orange otherwise), then the usage % if that preference is on.

## The popover (the glance)
Flat rows, top to bottom: guard status + **route toggle** → net weather (one
quiet latency line when fine; a verdict banner when not — *"Anthropic API
unreachable — your internet is fine (23 ms)"*) → **Needs You** (failed >
blocked > asking > done; click a row to focus that terminal, or copy the
resume command for background agents; hover to dismiss) → collision banners →
**Agents** (each working agent: its model mark, project, live
activity line, `n ✓` momentum counter) → Resting (collapsed) → location (+
re-check button) → plan meters → footer (Dashboard / Settings / Quit).

## The dashboard window
Five tabs: **Overview** (status + all guard controls + counters),
**Network** (dual-series latency chart, speed test, live traffic feed),
**Usage** (plan limits + refresh, local cost estimate, per-model breakdown,
7-day chart), **Tower** (every session in full detail, collisions, "while
you were away" event history), **Settings** (menu-bar mode, thresholds, live
plan toggle, country, reset).

## Notifications
Fired on agent transitions: →failed / →blocked / →asking always; →done only
when you haven't opened the popover in the last 60s. Clicking one focuses that
agent's terminal. If you deny notification permission, the menubar badge
carries the signal alone — Tower never nags.

## Quit
`Cmd-Q` (or the Quit button) **asks first**, then tells the daemon to quit so
routing is removed and Claude returns to a direct connection.

## Parity note
The app and the terminal dashboard are kept feature-matched (same daemon, same
commands); the TUI's agent view is a compact card for now. If you change a
setting in one, the other reflects it within ~1s.
