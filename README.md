# 🐎 Corral

**Corral — a control tower for your Claude agents.** When you're running many
agents across terminal tabs and projects, Corral rounds them all into one
view: what each is doing, which one needs you (blocked, asking, done), and
which are colliding on the same repo. Herd the loose ones into the pen so none
wander off unwatched.

One little ranch, four jobs:

- **The herd** — every running Claude Code agent, live: status, activity,
  model, momentum. A ranked **needs-you queue** (failed > blocked > asking >
  done) with notifications, and click-to-focus that agent's terminal.
- **The weather** — when Claude errors mid-session, Corral instantly answers
  *"is it my internet, is it slow, or is it Anthropic?"* — passive latency
  probes + an on-demand speed test.
- **The fence** — pin Claude Code to one country. A tiny local proxy blocks
  Claude's requests when you're **confirmed outside** your target country
  (fail-open: an unconfirmed location never blocks).
- **The feed bill** — your real plan usage (mirrored from `claude -p /usage`)
  plus a clearly-labeled local token/cost estimate.

Two front-ends, one daemon, one source of truth:

- **`Corral.app`** — a native menubar agent (Swift/AppKit + SwiftUI, macOS 14+).
  No dock icon, no browser, no terminal required.
- **Terminal dashboard** — a stdlib `curses` TUI (now with mouse support) for
  when you live in the shell.

Both read the same `~/.corral/state.json` and drive the daemon through the
same command files, so you can use either (or both) interchangeably.

> Corral is the app formerly known as **Geo Guard**, grown up. Your
> `~/.geo-guard` state migrates automatically on first launch.

## The horses

One horse per Claude model — **the craft scales with the caliber**
(crayon → flat vector → sculpted badge → gilded myth):

| Model | Horse |
|---|---|
| **Fable** | Mythic winged stallion, gold-leaf heraldry |
| **Opus** | Prancing stallion emblem — sculpted, glossy, premium badge |
| **Sonnet** | Clean galloping horse — flat vector, confident lines |
| **Haiku** | Little pony — a child's crayon doodle |

The **menu bar shows the highest-tier horse currently at work** (it takes a
subtle canter step while a tool call runs), a horseshoe when the corral is
quiet, and a needs-you count. See [docs/DESIGN.md](docs/DESIGN.md) for the
whole design system.

## Documentation

| Doc | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The daemon, IPC, routing, fail-open, net probes, agent monitoring |
| [docs/DESIGN.md](docs/DESIGN.md) | The design system — horses, attention semantics, motion tokens |
| [docs/APP.md](docs/APP.md) | The macOS menubar app — build, popover, dashboard, notifications |
| [docs/TUI.md](docs/TUI.md) | The terminal dashboard — cards, actions menu, mouse |
| [windows_plan.md](windows_plan.md) | Plan to port this to Windows |
| [CLAUDE.md](CLAUDE.md) | Quick orientation + invariants for contributors |

---

## Quick start

**Menubar app** — double-click **`Corral.app`**. A horse(shoe) appears in your
menu bar; click it for the popover.

**Terminal** — double-click **`Corral (Terminal).command`**, or run:

```bash
python3 "Corral.app/Contents/Resources/corral-tui.py"
```

Either front-end starts the background daemon automatically if it isn't
already running.

> **First launch:** because the app is ad-hoc signed (not notarized), macOS may
> say it's from an unidentified developer. Right-click **Corral.app → Open →
> Open** once; normal double-clicks work after that.

---

## The menu bar at a glance

Strict priority — the loudest true thing wins:

| Icon | Meaning |
|---|---|
| 🔴 `wifi.slash` | **Your internet is offline** — Claude errors are local, not Anthropic |
| 🟠 `exclamationmark.icloud` | **Anthropic API unreachable** — your internet is fine |
| `wifi.exclamationmark` | Captive portal (tinted) or slow connection (plain) |
| 🟠 `exclamationmark.shield.fill` | **Blocking Claude** — confirmed outside your target country |
| 🐎 a horse | Agents at work — the silhouette is the highest-tier model running |
| a horseshoe | The corral is quiet |

Badge: needs-you count (red if something failed) · optional usage %.

---

## What the herd view shows

Per agent: project, model (its horse), live activity (`editing
src/Model.swift`), status, a `n ✓` completed-tools momentum counter, and age.
Plus: same-repo collision banners (escalating when two agents edit the same
file), a "while you were away" event history in the dashboard, and macOS
notifications when an agent flips to blocked / asking / failed / done.

Statuses are derived read-only from Claude Code's own session transcripts —
Corral never writes into `~/.claude` and never injects input. The
"waiting for approval" state is an honest heuristic (a pending tool call with
a stalled transcript can also be a slow tool).

---

## Safety model

Corral is careful never to leave Claude Code in a broken state:

1. **It never routes Claude at a dead proxy.** Routing is only written to
   `settings.json` when the proxy is actually accepting connections.
2. **It always un-routes on shutdown.** Quitting tells the daemon to remove
   the proxy from `settings.json` first, so Claude goes back to a direct
   connection.
3. **A crashed UI can't break Claude.** If a front-end dies, the daemon keeps
   the proxy up; if the daemon dies, it removes routing on the way out.
4. **Fail-open.** If your location can't be confirmed (offline, rate-limited),
   Claude is **not** blocked — a failed lookup must never knock Claude offline.
5. **It backs up `settings.json`** to `settings.json.corral.bak` before its
   first edit.
6. **Network probes never go through the proxy** and never touch your Claude
   credentials; the Anthropic probe is a TLS handshake, not an API request.

**Quitting the menubar app asks first** and tells you it will turn the guard
off.

---

## How blocking works

- The proxy tunnels HTTPS via `CONNECT`, so it sees each request's **hostname**
  (enough to allow/deny) but **never decrypts** your traffic.
- Any host containing `anthropic`, `claude.ai`, or `claude.com` is treated as a
  Claude Code request.
- Country is checked every ~15 s via `ip-api.com`.

| Situation | Claude Code | Other traffic |
|---|---|---|
| Inside target country | ✅ allowed | ✅ allowed |
| Confirmed outside target | ⛔ blocked | ✅ allowed (⛔ with *Block ALL*) |
| Location unknown | ✅ allowed (fail-open) | ✅ allowed |
| Enforcement off | ✅ allowed | ✅ allowed |

> **Limitation:** this is a proxy, not an OS-level kill switch. It blocks
> Claude Code because Claude Code obeys the proxy env. A program told to
> ignore the proxy could still reach the network.

---

## Building from source

Requires **Xcode Command Line Tools** (`swiftc`) to build the app, and
**Python 3.8+** at runtime.

```bash
./build.sh          # compiles src/*.swift → Corral.app (~20s)
```

### Project layout

```
corral/
├── Corral.app/                  # built product (regenerate with build.sh)
├── Corral (Terminal).command    # double-click → terminal dashboard
├── build.sh                     # assembles the .app from src/
├── assets/horses/               # the design-system SVGs
├── docs/                        # ARCHITECTURE, DESIGN, APP, TUI
├── windows_plan.md              # plan to port this to Windows
└── src/
    ├── corrald.py               # the daemon (proxy + geo + usage + net + agents + IPC)
    ├── *.swift                  # native menubar app (AppKit + SwiftUI)
    ├── corral-tui.py            # terminal dashboard (curses)
    ├── Info.plist
    └── AppIcon.icns / AppIcon.svg
```

### How the pieces talk

```
                ┌───────────────────────┐
   writes  ───▶ │  ~/.corral/state.json │  ◀── reads (menubar + TUI, 1×/s)
                └───────────────────────┘
   corrald.py                                 src/*.swift / corral-tui.py
                ┌───────────────────────┐
   reads  ◀──── │  ~/.corral/cmd/*.json │  ◀── writes commands (route, focus…)
                └───────────────────────┘
```

The daemon is stdlib-only and holds **all** logic and state. The front-ends
are thin: read one JSON file, write command files. That's what keeps the
codebase small and the [Windows port](windows_plan.md) straightforward.

---

## Requirements

- **macOS 14+**, Apple Silicon.
- **Python 3.8+** on `PATH` (macOS ships one; Homebrew or python.org also fine).
- **Xcode Command Line Tools** — only to *build* (`xcode-select --install`).
- **Claude Code** installed, so there are agents to corral.

No root, no daemons installed system-wide (except the optional keep-awake
"lid-closed" mode, which asks for admin once and can be fully removed).
Nothing leaves your machine but the public-IP country lookup and the network
probes.

---

## Reset / uninstall

- **Turn everything off:** quit the app (it removes routing) or press `Q` in
  the terminal.
- **Full manual reset:** delete `~/.corral/`, and if `env.HTTPS_PROXY` still
  points at `127.0.0.1` in `~/.claude/settings.json`, remove it (or restore
  `~/.claude/settings.json.corral.bak`).
- **Remove the app:** delete `Corral.app`. Nothing else is left behind.
- If you ever want to see the TUI onboarding again, delete `~/.corral/.tui_seen`.

---

## License

Open source. Use it, fork it, port it. See `windows_plan.md` if you want to
bring the same experience to Windows.
