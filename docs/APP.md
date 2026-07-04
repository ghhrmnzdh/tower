# Corral — macOS Menubar App

A native (Swift + AppKit/SwiftUI, macOS 14+) menu-bar agent — no dock icon, no
browser. It reads `~/.corral/state.json` and drives the daemon via command
files, exactly like the terminal dashboard — see
**[ARCHITECTURE.md](ARCHITECTURE.md)**; the look and motion are specified in
**[DESIGN.md](DESIGN.md)**.

## Run
```bash
open "Corral.app"
```
or double-click **`Corral.app`** in Finder. A horse (or horseshoe) appears in
the menu bar; click it for the popover.

> **First launch:** it's ad-hoc signed (not notarized), so macOS may block it —
> **right-click → Open → Open** once, then normal launch works.

## Build from source
```bash
./build.sh        # compiles src/*.swift → Corral.app (~20s)
```
Requires Xcode Command Line Tools (`swiftc`) to build, and Python 3 at runtime.

## The menu-bar icon — a live signal, in strict priority order
| Icon | Meaning |
|---|---|
| red `wifi.slash` | **Your internet is offline** — Claude errors are local |
| `wifi.exclamationmark` | Captive portal (red-tinted) or slow connection (plain) |
| orange `exclamationmark.icloud` | **Anthropic API unreachable** — your internet is fine |
| orange `exclamationmark.shield.fill` | **Blocking Claude** — fail-closed: off-country, or still confirming your location |
| a horse (template) | Agents at work — the silhouette is the **highest-tier model running** (winged = Fable, badge-ring = Opus, gallop = Sonnet, doodle pony = Haiku); it takes a subtle canter step while a tool call is in flight |
| a horseshoe | The corral is quiet |

Badge text next to the icon: the **needs-you count** (red when something
failed, orange otherwise), then the usage % if that preference is on.

## The popover (the glance)
Flat rows, top to bottom: guard status + **route toggle** → net weather (one
quiet latency line when fine; a verdict banner when not — *"Anthropic API
unreachable — your internet is fine (23 ms)"*) → **Needs You** (failed >
blocked > asking > done; click a row to focus that terminal, or copy the
resume command for background agents; hover to dismiss) → collision banners →
**The Herd** (each working agent: breathing horse avatar, project, live
activity line, `n ✓` momentum counter) → Resting (collapsed) → location (+
re-check button) → plan meters → footer (Dashboard / Settings / Quit).

## The dashboard window
Five tabs: **Overview** (status + all guard controls + counters),
**Network** (dual-series latency chart, speed test, live traffic feed),
**Usage** (plan limits + refresh, local cost estimate, per-model breakdown,
7-day chart), **Corral** (every session in full detail, collisions, "while
you were away" event history), **Settings** (menu-bar mode, thresholds, live
plan toggle, country, reset).

## Notifications
Fired on agent transitions: →failed / →blocked / →asking always; →done only
when you haven't opened the popover in the last 60s. Clicking one focuses that
agent's terminal. If you deny notification permission, the menubar badge
carries the signal alone — Corral never nags.

## Quit
`Cmd-Q` (or the Quit button) **asks first**, then tells the daemon to quit so
routing is removed and Claude returns to a direct connection.

## Parity note
The app and the terminal dashboard are kept feature-matched (same daemon, same
commands); the TUI's agent view is a compact card for now. If you change a
setting in one, the other reflects it within ~1s.
