# 📡 Tower

**Tower — a control tower for your Claude agents.** When you're running many
agents across terminal tabs and projects, Tower brings them into one view:
what each is doing, which one needs you (blocked, asking, done), and which are
colliding on the same repo — so none run off unwatched.

One daemon, four jobs:

- **The agents** — every running Claude Code agent, live: status, activity,
  model, momentum. A ranked **needs-you queue** (failed > blocked > asking >
  done) with notifications, and click-to-focus that agent's terminal.
- **The weather** — when Claude errors mid-session, Tower instantly answers
  *"is it my internet, is it slow, or is it Anthropic?"* — passive latency
  probes + an on-demand speed test.
- **The fence** — pin Claude Code to one country. A tiny local proxy blocks
  Claude's requests when you're **confirmed outside** your target country
  (fail-closed: an unconfirmed location never gets through).
- **Usage** — your real plan usage (mirrored from `claude -p /usage`)
  plus a clearly-labeled local token/cost estimate.

Two front-ends, one daemon, one source of truth:

- **`Tower.app`** — a native menubar agent (Swift/AppKit + SwiftUI, macOS 14+).
  No dock icon, no browser, no terminal required.
- **Terminal dashboard** — a stdlib `curses` TUI (now with mouse support) for
  when you live in the shell.

Both read the same `~/.tower/state.json` and drive the daemon through the
same command files, so you can use either (or both) interchangeably.

> Tower is the app formerly known as **Geo Guard** (then Corral), grown up.
> Your `~/.corral` or `~/.geo-guard` state migrates automatically on first
> launch.

## The marks

Tower's identity is a **radar on a control tower** — its five states *are* the
guard (cleared, verifying, held on the connection, held off-country, or
unguarded). The menu bar is that radar; it animates only while a state has
something to say. Alongside it, one still mark per Claude model:

| Model | Mark |
|---|---|
| **Fable** | a gold spiral |
| **Opus** | three orbiting rings + core, rosso |
| **Sonnet** | a single steel S stroke |
| **Haiku** | three crayon ticks + core |

See [docs/DESIGN.md](docs/DESIGN.md) for the whole design system, or open
[Tower Identity Study.html](Tower%20Identity%20Study.html) to watch the marks
live.

## Documentation

| Doc | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The daemon, IPC, routing, fail-open, net probes, agent monitoring |
| [docs/DESIGN.md](docs/DESIGN.md) | The design system — the radar, model marks, attention semantics, motion tokens |
| [docs/APP.md](docs/APP.md) | The macOS menubar app — build, popover, dashboard, notifications |
| [docs/TUI.md](docs/TUI.md) | The terminal dashboard — cards, actions menu, mouse |
| [windows_plan.md](windows_plan.md) | The Windows port — what already runs, and the plan for the native tray |
| [CLAUDE.md](CLAUDE.md) | Quick orientation + invariants for contributors |

---

## Quick start

### Get it

**One line** — installs Tower to `/Applications` and starts it:

```sh
curl -fsSL https://ghhrmnzdh.github.io/tower/install.sh | sh
```

No Gatekeeper warning, nothing to drag, nothing to un-quarantine. (Tower is
ad-hoc signed, not notarized — notarizing needs a paid Apple Developer account.
A file fetched with `curl` isn't quarantined, so macOS never assesses it and the
app just opens. Same binary as the zip below, fewer hoops.) Run the same line
again to upgrade.

**Or download it by hand** — from [Releases](https://github.com/ghhrmnzdh/tower/releases/latest),
grab **`Tower.app.zip`** and unzip it. That is the built app.

> ⚠️ Don't grab **"Source code (zip)"** — GitHub lists that on every release, and
> it unpacks to a `tower-x.y.z/` folder with **no `Tower.app` inside it**. The
> bundle is a build product, not a checked-in file. If that's what you have,
> either download `Tower.app.zip` instead, or build it (below).

> A browser download **is** quarantined, so macOS will refuse to open it —
> *"Tower.app cannot be opened because it is from an unidentified developer."*
> On macOS 15+ right-click → Open no longer clears it. Either run
> `xattr -rd com.apple.quarantine /path/to/Tower.app`, or open it once and go to
> **System Settings → Privacy & Security → Open Anyway**. The one-liner above
> avoids all of this.

**Or build from source** — one command, ~20s. Needs Xcode Command Line Tools
(for `swiftc`); `xcode-select --install` if you don't have them:

```bash
./build.sh          # → creates Tower.app
```

### Run it

**Menubar app** — double-click **`Tower.app`**. The tower radar appears in your
menu bar; click it for the popover.

**Terminal** — one word:

```bash
tower
```

The installer symlinks that onto your PATH. Or, from the menu bar popover, click
**Terminal Dashboard…** — it opens in Terminal for you.

The terminal dashboard is pure Python, so it needs no build at all. Straight
from a source checkout, with no `swiftc` and no `Tower.app`, this just works:

```bash
python3 src/tower-tui.py
```

(Or double-click **`Tower (Terminal).command`** in a checkout.)

Either front-end starts the background daemon automatically if it isn't
already running.

> **First launch:** only an app you *downloaded in a browser* is quarantined, and
> macOS will call it unidentified. Installing with the `curl` one-liner above, or
> building from source, avoids that entirely — the app just opens. To rescue a
> browser-downloaded copy: `xattr -rd com.apple.quarantine /path/to/Tower.app`.

---

## The menu bar at a glance

The radar's state *is* the guard (full color — amber for a hold, red for unguarded):

| Radar | Meaning |
|---|---|
| **clear** — calm ring + blips | Guarding · in-country and a path to Anthropic is open |
| **verify** — a rotating sweep | Confirming your location; held until sure |
| 🟠 **holdNet** — amber dashed ring + pings | No usable path (offline / captive / API) — held pending |
| 🟠 **holdGeo** — amber ring + fence + off-country blip | Wrong country / VPN — held, not failed |
| 🔴 **off** — red dashed ring, hollow core | Routing off — Claude connects directly, **unguarded** |

Badge: needs-you count (red if something failed) · optional usage %.

---

## What the agents view shows

Per agent: project, model (its mark), live activity (`editing
src/Model.swift`), status, a `n ✓` completed-tools momentum counter, and age.
Plus: same-repo collision banners (escalating when two agents edit the same
file), a "while you were away" event history in the dashboard, and macOS
notifications when an agent flips to blocked / asking / failed / done.

Statuses are derived read-only from Claude Code's own session transcripts —
Tower never writes into `~/.claude` and never injects input. The
"waiting for approval" state is an honest heuristic (a pending tool call with
a stalled transcript can also be a slow tool).

---

## Safety model

Tower is careful never to leave Claude Code in a broken state:

1. **It never routes Claude at a dead proxy.** Routing is only written to
   `settings.json` when the proxy is actually accepting connections.
2. **It always un-routes on shutdown.** Quitting tells the daemon to remove
   the proxy from `settings.json` first, so Claude goes back to a direct
   connection.
3. **A crashed UI can't break Claude.** If a front-end dies, the daemon keeps
   the proxy up; if the daemon dies, it removes routing on the way out.
4. **Fail-open.** If your location can't be confirmed (offline, rate-limited),
   Claude is **not** blocked — a failed lookup must never knock Claude offline.
5. **It backs up `settings.json`** to `settings.json.tower.bak` before its
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
./build.sh          # compiles src/*.swift → Tower.app (~20s)
```

### Project layout

```
tower/
├── Tower.app/                  # built product (regenerate with build.sh)
├── Tower (Terminal).command    # double-click → terminal dashboard
├── Tower Identity Study.html   # the radar + model marks, live
├── build.sh                     # assembles the .app from src/
├── docs/                        # ARCHITECTURE, DESIGN, APP, TUI
├── windows_plan.md              # plan to port this to Windows
└── src/
    ├── towerd.py               # the daemon (proxy + geo + usage + net + agents + IPC)
    ├── *.swift                  # native menubar app (AppKit + SwiftUI); Glyph.swift = the marks
    ├── tower-tui.py            # terminal dashboard (curses)
    ├── Info.plist
    └── AppIcon.icns
```

### How the pieces talk

```
                ┌───────────────────────┐
   writes  ───▶ │  ~/.tower/state.json │  ◀── reads (menubar + TUI, 1×/s)
                └───────────────────────┘
   towerd.py                                 src/*.swift / tower-tui.py
                ┌───────────────────────┐
   reads  ◀──── │  ~/.tower/cmd/*.json │  ◀── writes commands (route, focus…)
                └───────────────────────┘
```

The daemon is stdlib-only and holds **all** logic and state. The front-ends
are thin: read one JSON file, write command files. That's what keeps the
codebase small and the [Windows port](windows_plan.md) straightforward.

---

## Requirements

- **macOS 14+**, Apple Silicon — for the full experience (menubar app + TUI).
- **Windows 10/11** — daemon + terminal dashboard only, and **experimental**;
  see [Windows](#windows-experimental) below.
- **Python 3.8+** on `PATH` (macOS ships one; Homebrew or python.org also fine).
- **Xcode Command Line Tools** — only to *build* the Mac app (`xcode-select --install`).
- **Claude Code** installed, so there are agents to tower.

No root, no daemons installed system-wide (except the optional keep-awake
"lid-closed" mode, which asks for admin once and can be fully removed).
Nothing leaves your machine but the public-IP country lookup and the network
probes.

---

## Windows (experimental)

The daemon and the terminal dashboard **run on Windows 10/11 today** — the same
guard, the same fail-closed proxy, the same live state, still dependency-free.
Routing ported for free: Claude Code reads the same `settings.json` on every
platform. What's missing is the native tray app (the menubar app is Swift,
macOS-only), so on Windows the TUI *is* the front-end.

There's no build step — grab the source and run:

```bat
python src\tower-tui.py
```

or double-click **`Tower (Terminal).cmd`**, which finds Python for you.

> ⚠️ **Experimental — please read.** The Windows port is written and reviewed,
> but it has **never been run on real Windows hardware**. Expect rough edges,
> and please [open an issue](https://github.com/ghhrmnzdh/tower/issues) with
> what you hit — that feedback is exactly what promotes it out of experimental.
> Nothing here weakens the guard: the fail-closed rule is in the shared daemon,
> and the Windows-only shims (single-instance mutex, process enumeration) are
> written to fail *closed* too.

Under the hood, only the OS-specific edges differ — [`src/_win.py`](src/_win.py)
(named-mutex single instance, `SetThreadExecutionState` keep-awake,
`Win32_Process` agent scan, console VT/UTF-8) and
[`src/_wincurses.py`](src/_wincurses.py) (a drop-in `curses` subset over ANSI +
`msvcrt`). `towerd.py` itself stays one portable file behind an `IS_WINDOWS`
flag. The plan for the native tray is [windows_plan.md](windows_plan.md).

---

## Reset / uninstall

- **Turn everything off:** quit the app (it removes routing) or press `Q` in
  the terminal.
- **Full manual reset:** delete `~/.tower/`, and if `env.HTTPS_PROXY` still
  points at `127.0.0.1` in `~/.claude/settings.json`, remove it (or restore
  `~/.claude/settings.json.tower.bak`).
- **Remove the app:** delete `Tower.app`. Nothing else is left behind.
- If you ever want to see the TUI onboarding again, delete `~/.tower/.tui_seen`.

---

## License

Open source. Use it, fork it, port it. The Windows daemon and terminal dashboard
already run ([experimental](#windows-experimental)) — `windows_plan.md` covers
what's left, chiefly the native tray.
