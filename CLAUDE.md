# CLAUDE.md

Tower: a control tower for your Claude agents — pin Claude Code to a country
(the fence), isolate network faults (the weather), watch usage, and monitor
every running Claude agent. One daemon, two front-ends (menubar app + terminal
dashboard). Formerly Geo Guard, then Corral.

It is Claude-Code-only, and it is an **honest status layer** — a little helper
so Claude is never confused by a shifting location. If something looks wrong
(off-country, unstable net, a blocked request), that is the app *doing its job*
and reporting the truth, not the app being broken. There is no need to quit it
when you see a fault — quitting only removes the guard and routes Claude back to
a direct connection. Leave it running; it will clear itself when the underlying
condition (your location or your connection) recovers.

## Layout
- `src/towerd.py` — the daemon (proxy + geo + usage + plan + net health +
  agent monitor + file IPC). stdlib only.
- `src/*.swift` — native menu-bar app (main / AppDelegate / Model /
  DesignSystem / Glyph / StatusIcon / Popover / Dashboard / Notifier /
  Components).
- `src/Glyph.swift` — the identity marks: the tower **radar** (guard status,
  five animated states) and the still per-model marks. One geometry backs both
  the live SwiftUI `Canvas` views and the menu-bar `ImageRenderer` templates.
- `src/tower-tui.py` — terminal dashboard (curses, stdlib only).
- `Tower Identity Study.html` — the radar + model marks, live (design reference).
- `build.sh` — compiles the app bundle from `src/` (`-target arm64-apple-macos14.0`).
- `docs/` — ARCHITECTURE.md, DESIGN.md, APP.md, TUI.md.

## Build / run
- `./build.sh` then `open "Tower.app"`.
- TUI: `python3 "Tower.app/Contents/Resources/tower-tui.py"`.

## Invariants — don't break these
- **Never route Claude via the shell.** Routing edits `~/.claude/settings.json`
  `env` only (`HTTPS_PROXY`/`HTTP_PROXY`, plus `CLAUDE_CODE_RETRY_WATCHDOG` /
  `CLAUDE_CODE_MAX_RETRIES` so a blocked/outaged request stays PENDING in
  Claude's native retry spinner instead of erroring). Shell aliases broke the
  `claude` command before. `route_off` removes those keys, but leaves a
  retry value the user customised themselves (`RETRY_ENV`).
- **Fail-closed:** a Claude request is allowed ONLY when *confirmed* inside the
  target country AND the network has a usable path to Anthropic. Anything
  uncertain — location checking/cached/errored, or the net offline/captive/
  edge-unreachable — is blocked. There is no allow-through fallback; the cure
  for false blocks is durable, accurate detection (multi-source geo in
  `geo_loop`), not letting unconfirmed traffic through. `claude -p /usage` is
  itself a Claude request: it is gated on the *same* predicate
  (`State.claude_allowed()`) and never runs off-country or on an unstable net.
  The one intentional pass-through: while routing is ON the gate is fully
  fail-closed, but a double-confirmed route-OFF sets `State.routed = False`, which
  makes `should_block` a pass-through for sessions still pinned to the proxy —
  the same direct, unguarded connection new sessions get. "Off means off," not
  "stuck-gated." `state.routed` may only be flipped by the double-confirmed route
  command or the persisted `cfg["routed"]`; it never fails open on its own.
- **Block with 503, never 403 — the block is PENDING, not FAILED.** A blocked
  Claude request is *held* a few seconds (re-checking so a sub-second blip
  clears with no visible retry), then answered `503 + Retry-After`. Claude Code
  retries 5xx into its native "Retrying · attempt x/y" spinner — the durable
  "pending" UX that resumes on its own when the guard clears — but treats 403 as
  broken auth and kills the turn. The long-outage tolerance comes from the retry
  budget (`RETRY_ENV`), NOT from a long hold: the hold is pre-CONNECT and a long
  one risks tripping the client's tunnel connect timeout. Don't "fix" the block
  by returning 403, and don't stretch `BLOCK_HOLD_S` to cover outages.
- **Usage can't be shown when the guard isn't passing.** When `/usage` is
  gated, front-ends show a *spacious, honest message* (not stale numbers) that
  says whether it's the **connection** (net) or the **location/VPN** (geo) —
  driven by `plan.gate_reason` / `guard.net_ok`, never guessed.
- **No Claude request on an unstable connection.** "Unstable" = no trustworthy
  path to Anthropic (offline / captive portal / edge unreachable), NOT merely
  slow — a "degraded" (high-latency but reachable) link still allows traffic.
  `NetMonitor` publishes `state.net_ok`; it *does* feed `should_block()`.
- **On by default.** Opening the app starts the daemon, and the daemon routes
  Claude on startup unless you've *explicitly* turned routing off
  (`cfg["routed"] == False`). You never have to arm it by hand.
- **The proxy endpoint is durable.** A Claude session captures `HTTPS_PROXY` once
  at launch and can never change it, so the proxy address must not move under it.
  `bind_proxy` prefers the *same* port every run (persisted `cfg["proxy_port"]`,
  retrying briefly for a dying predecessor) so a pinned session survives a daemon
  restart; the app's pollTimer respawns a daemon that dies unexpectedly (kill -9);
  and `route_off` runs on every clean exit *and* via `atexit`. Don't reintroduce
  port drift or an endpoint that vanishes mid-session — that is the "only a new
  chat works" bug.
- **Never let a live tunnel carry a short timeout.** `socket.create_connection`
  leaves its connect timeout ON the socket, so the relay must reset it
  (`_upstream_connect` → `settimeout(TUNNEL_IDLE_S)`); a short idle timeout
  silently guillotines slow-first-byte and idle keep-alive tunnels mid-session.
  Sockets on the hot path also set `TCP_NODELAY` (Nagle batches streamed tokens).
- **Dangerous switch-offs are double-confirmed.** Anything that lets Claude
  reach the API *without* the guard — turning routing off, disabling
  enforcement, quitting/stopping the guard — is a destructive action. Both
  front-ends must **warn hard and require a second, explicit confirmation**
  before it takes effect, and the warning must call out how many agents are
  *working right now* (they'd immediately send unguarded requests), and quit/stop
  additionally calls out how many chats are *pinned to the proxy* (they lose their
  connection until restarted). Turning the guard *on* stays one tap; only the
  off-direction is gated. App: `TowerModel.requestDanger` + `DangerAlerts` +
  `proxyPinnedCount`; TUI: `danger_confirm` + `_pinned_note`.
- **Never trip a macOS permission prompt.** Tower must never make macOS ask for
  Photos / Music / Contacts / Desktop / Documents / Downloads. Two rules keep it
  hermetic: (1) the daemon NEVER opens or enumerates anything under a
  TCC-protected folder — guard every filesystem read with `_is_protected()`
  (`_PROTECTED_ROOTS`); an agent working there still gets a row, but derive its
  fields from the path string, not I/O (no git-root/branch/collision reads).
  (2) Every `claude -p /usage` runs sandboxed — empty `ZDOTDIR` (no shell rc is
  sourced), `--strict-mcp-config` + empty `--mcp-config` (no MCP servers spawn),
  and a neutral `cwd=CONFIG_DIR`. The only prompts Tower may ever cause are
  Notifications (lazy, first real alert), Terminal/iTerm control (only on a
  user-initiated focus), and the keep-awake admin password (opt-in, pre-explained).
- **Read-only toward Claude Code sessions:** the agent monitor never writes
  into `~/.claude` and never injects input into a session.
- **Daemon is single-instance** (`flock` on `~/.tower/daemon.lock`).
- **Front-ends are thin:** read `~/.tower/state.json`, write `cmd/*.json`.
  All logic lives in the daemon. Keep the app and TUI feature-matched
  (exception: the TUI's agent view is a compact card for now).
- **No third-party deps:** Python stdlib + AppKit/SwiftUI only. Net probes are
  raw sockets (macOS urllib silently picks up system proxies).
- **Real plan usage** comes from `claude -p /usage` (Claude does the auth — never
  read the token). Local token/cost is a separate, clearly-labeled estimate.
- **Transcript parsing is defensive:** the JSONL format is undocumented and
  drifts; per-line try/except, surface `meta.parse_errors`, never crash.
- **The design system is law:** docs/DESIGN.md — the mark is the state (radar =
  guard, model mark = model), motion = state change (failure never bounces),
  one loudest thing at a time, Reduce Motion always honored.
