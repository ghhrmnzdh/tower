# 📡 Tower

**Tower — a control tower for your Claude agents.** When you're running many
agents across terminal tabs and projects, Tower brings them into one view:
what each is doing, which one needs you (blocked, asking, done), and which are
colliding on the same repo — so none run off unwatched.

## Install

One line — installs Tower to `/Applications`, puts the `tower` command on your
PATH, and starts it:

```sh
curl -fsSL https://ghhrmnzdh.github.io/tower/install.sh | sh
```

No password, no `sudo`, no Gatekeeper warning, nothing to drag or un-quarantine.
Run the same line again to upgrade. The radar then appears in your menu bar;
type `tower` for the terminal dashboard.

<details>
<summary>Why a <code>curl</code> line and not a download?</summary>

Tower isn't notarized (that needs a paid Apple Developer account), and macOS
quarantines anything downloaded *in a browser* — that's what triggers the
"unidentified developer" block. A file fetched with `curl` is never quarantined,
so macOS never runs that check. Same binary, fewer hoops.

The script is short and does nothing clever:
[read it first](https://ghhrmnzdh.github.io/tower/install.sh) if you'd rather not
pipe a stranger's shell script into `sh` — a reasonable instinct.

**Prefer to build it?** One command, ~20s. Needs Xcode Command Line Tools for
`swiftc` (`xcode-select --install`):

```bash
git clone https://github.com/ghhrmnzdh/tower && cd tower
./build.sh          # → creates Tower.app
```

**Just want the terminal dashboard?** It's pure Python, stdlib only — no build,
no app, no `swiftc`. From a checkout: `python3 src/tower-tui.py`.

</details>

Requires macOS 14+ on Apple Silicon, Python 3.8+, and Claude Code.
(Windows: the daemon and terminal dashboard run today, [experimentally](#windows-experimental).)

---

## What it does

One daemon, four jobs:

- **The agents** — every running Claude Code agent, live: status, activity,
  model, momentum. A ranked **needs-you queue** (failed > blocked > asking >
  done) with notifications, and click-to-focus that agent's terminal.
- **The weather** — when Claude errors mid-session, Tower instantly answers
  *"is it my internet, is it slow, or is it Anthropic?"* — passive latency
  probes + an on-demand speed test.
- **The fence** — pin Claude Code to one country. A tiny local proxy holds
  Claude's requests whenever you're not **confirmed** inside your target country
  (fail-closed: an unconfirmed location never gets through).
- **Usage** — your real plan usage (mirrored from `claude -p /usage`)
  plus a clearly-labeled local token/cost estimate.

Two front-ends, one daemon, one source of truth:

- **`Tower.app`** — a native menubar agent (Swift/AppKit + SwiftUI, macOS 14+).
  No dock icon, no browser, no terminal required.
- **Terminal dashboard** — a stdlib `curses` TUI (now with mouse support) for
  when you live in the shell.

Both read the same `~/.tower/state.json` and drive the daemon through the
same command files, so you can use either (or both) interchangeably. Either
front-end starts the background daemon automatically if it isn't running, and
from the popover, **Terminal Dashboard…** opens the TUI for you.

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
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The daemon, IPC, routing, the fail-closed gate, net probes, agent monitoring |
| [docs/DESIGN.md](docs/DESIGN.md) | The design system — the radar, model marks, attention semantics, motion tokens |
| [docs/APP.md](docs/APP.md) | The macOS menubar app — build, popover, dashboard, notifications |
| [docs/TUI.md](docs/TUI.md) | The terminal dashboard — cards, actions menu, mouse |
| [windows_plan.md](windows_plan.md) | The Windows port — what already runs, and the plan for the native tray |
| [CLAUDE.md](CLAUDE.md) | Quick orientation + invariants for contributors |

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
src/Model.swift`), status, a `n ✓` completed-tools momentum counter, age, and
whether that agent is actually **behind the guard** (a chat started before you
turned Tower on is still on a direct connection until you restart it).
Plus: same-repo collision banners (escalating when two agents edit the same
file), a "while you were away" event history in the dashboard, and macOS
notifications when an agent flips to blocked / asking / failed / done.

Statuses are derived read-only from Claude Code's own session transcripts —
Tower never writes into `~/.claude` and never injects input. The
"waiting for approval" state is an honest heuristic (a pending tool call with
a stalled transcript can also be a slow tool).

---

## How the guard works

The guard is **fail-closed**. A Claude request proceeds only when Tower can
*affirmatively confirm* two things at once: you are inside the target country,
**and** the network has a usable path to Anthropic. Anything uncertain — the
location still checking, cached, or errored; the net offline, captive, or unable
to reach Anthropic's edge — is held. There is no allow-through fallback.

**A held request is PENDING, not FAILED.** Tower holds it for a few seconds
(so a sub-second blip clears with no visible retry), then answers `503 +
Retry-After`. Claude Code turns a 503 into its own native *"Retrying · attempt
x/y"* spinner, so the turn survives and resumes by itself the moment the guard
clears. (Tower never returns 403 — Claude reads that as broken auth and kills
the turn.)

- The proxy tunnels HTTPS via `CONNECT`, so it sees each request's **hostname**
  (enough to allow or hold) but **never decrypts** your traffic.
- Any host containing `anthropic`, `claude.ai`, or `claude.com` is treated as a
  Claude Code request.
- Your country is confirmed every ~15 s against **three independent geo
  providers**, re-checked immediately whenever your public IP changes (a VPN
  drop is caught in about a quarter of a second), and a confirmation older than
  60 s is never trusted.

| Situation | Claude Code | Other traffic |
|---|---|---|
| Confirmed inside target country, path to Anthropic open | ✅ allowed | ✅ allowed |
| Confirmed outside target country | ⏸ held (503-pending) | ✅ allowed (⏸ with *Block ALL*) |
| Location unknown / unconfirmed / stale | ⏸ held (fail-closed) | ✅ allowed |
| No usable path (offline, captive portal, edge unreachable) | ⏸ held | ✅ allowed |
| Live Claude tunnels being reset upstream | ⏸ held | ✅ allowed |
| Slow but reachable connection | ✅ allowed | ✅ allowed |
| Routing or enforcement off | ✅ allowed (**unguarded**) | ✅ allowed |

> **Limitation:** this is a proxy, not an OS-level kill switch. It guards
> Claude Code because Claude Code obeys the proxy env. A program told to
> ignore the proxy could still reach the network.

---

## Safety model

Tower is careful never to leave Claude Code in a broken state:

1. **It never routes Claude at a dead proxy.** Routing is only written to
   `settings.json` when the proxy is actually accepting connections, and only
   ever as `env` keys — never a shell alias.
2. **It always un-routes on shutdown.** Quitting tells the daemon to remove
   the proxy from `settings.json` first, so Claude goes back to a direct
   connection.
3. **A crashed UI can't break Claude.** If a front-end dies, the daemon keeps
   the proxy up; if the daemon dies, it removes routing on the way out.
4. **Fail-closed.** An unconfirmed location never gets through. A false hold is
   a pending retry that clears itself; a false *allow* is an off-country request
   you can't take back.
5. **Turning the guard off is double-confirmed.** Anything that lets Claude
   reach the API unguarded — routing off, enforcement off, quitting — warns hard
   and asks a second time, telling you how many agents are working right now and
   how many chats are pinned to the proxy.
6. **It backs up `settings.json`** to `settings.json.tower.bak` before its
   first edit.
7. **Network probes never go through the proxy** and never touch your Claude
   credentials; the Anthropic probe is a TLS handshake, not an API request.
8. **It never trips a macOS permission prompt** — the daemon never reads inside
   Photos / Documents / Desktop / Downloads, and every `claude -p /usage` runs
   sandboxed.

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
├── release.sh                   # builds, packages and publishes a release
├── site/                        # the landing page + install.sh (→ gh-pages)
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
- **Remove the app:** delete `Tower.app` (and the `tower` symlink the installer
  put on your PATH). Nothing else is left behind.
- If you ever want to see the TUI onboarding again, delete `~/.tower/.tui_seen`.

---

## License

Open source. Use it, fork it, port it. The Windows daemon and terminal dashboard
already run ([experimental](#windows-experimental)) — `windows_plan.md` covers
what's left, chiefly the native tray.
