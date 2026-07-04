# Corral — Terminal Dashboard

A zero-dependency (`curses`, stdlib only) terminal front-end for the guard. It
renders `~/.corral/state.json` and drives the daemon by dropping command
files — see **[ARCHITECTURE.md](ARCHITECTURE.md)**.

## Run
```bash
python3 "Corral.app/Contents/Resources/corral-tui.py"
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
dashboard**. (To see onboarding again, delete `~/.corral/.tui_seen`.)

## The dashboard is deliberately non-reactive — but clickable
A stray keypress does **nothing**, so you can't accidentally toggle routing by
fat-fingering a key. Deliberate gestures work:

| Gesture | Action |
|---|---|
| `Enter` (or `m` / `space`) | Open the **Actions menu** |
| `q` or `Q` | Quit the dashboard (**both** leave the guard running) |
| **Mouse click** | Act on what you clicked: guard rows toggle, the country name opens the picker, the NETWORK card runs a speed test, the plan section refreshes, a HERD row focuses that agent's terminal |
| **Scroll wheel** | Moves the selection in the menu and country picker |

## The Actions menu
Everything you can *do* lives here. Move with `↑/↓` (or the wheel), select
with `Enter` (or a click), close with `Esc`:

| Action | What it does |
|---|---|
| Route Claude through the guard | Turn routing on/off (edits `settings.json`, not your shell) |
| Enforcement | Fail-closed: allow Claude only when confirmed in-country on a stable connection; block otherwise |
| Block scope | Block ALL traffic, or Claude only |
| Pin a country… | Opens the searchable country picker |
| Keep the Mac awake | Cycle off → lid-open → lid-closed (lid-closed asks for your password once) |
| Re-check location now | Immediate location lookup **and** a fresh net probe |
| Refresh usage now | Re-run `claude -p /usage` immediately |
| **Run internet speed test** | 25 MB download, direct connection; shows running % / cooldown / last Mbps |
| View cost breakdown | Estimated $ at API prices (session/today/week/by-model) |
| Background processes… | See the daemon & keep-awake PIDs; **stop** them |
| Stop guard & restore Claude, then quit | Removes routing and exits everything |
| Quit dashboard | Exit; guard keeps running |

## What the dashboard shows
- **Header** — the guard status, except that net faults outrank it: a red
  **INTERNET DOWN / WI-FI LOGIN REQUIRED / ANTHROPIC API ISSUE** header means
  *stop and look here* (a slow link stays in the card, not the header).
- **Location** — status, IP, city, ISP, full country name. When the internet
  is down it says so instead of "Locating…" forever.
- **Guard** — route, enforce, scope, allowed/blocked counts, proxy status.
- **Keep awake** — whether long agents survive the lid closing.
- **NETWORK** — where a Claude error comes from: status dot
  (online/degraded/offline/api_issue/captive), `net` vs `api` latency, an
  API-latency sparkline (outages peg the top), and the last speed-test result.
- **THE HERD** — Claude agents on this Mac: `N at work · M done today · K need
  you`, then rows (needs-you first: ✗ failed / ⛔ waiting approval / ? asking /
  ✓ done, then the working herd) as
  `project — activity · model · age`. Collisions show as a ⚠ line when two
  agents share a repo (louder when they touch the same file). Click a row to
  focus that agent's terminal.
- **PLAN LIMITS** — the **real** numbers, mirrored from `claude -p /usage`
  (session / weekly / Fable, each `% used` + reset), refreshed every 60s.
- **local estimate** — a quiet, secondary block: absolute tokens, $, pace,
  by-model, 7-day trend. Computed locally; **not** your plan %.
- **LIVE TRAFFIC** — each request flowing through the guard, newest first.

## Performance
Input is instant (~80ms tick), the daemon confirms actions in ~60ms, and the
screen only repaints when something actually changes (mouse adds no idle cost —
no motion tracking, just a click-time hitbox lookup).

## Country picker
Type to filter, `↑/↓` or wheel to move, `Enter` or click to pin, `Esc` to
cancel. Scrolls and resizes to fit any window.
