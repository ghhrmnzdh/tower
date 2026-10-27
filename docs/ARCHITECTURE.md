# Tower — Architecture (shared by both front-ends)

Tower has **one brain and two faces**. A single background **daemon** holds
all logic and state; a **menubar app** (Swift) and a **terminal dashboard**
(Python/curses) are thin views over it. They never talk to each other — they
both read one state file and drop command files.

One frame carries the product: the **fence** keeps Claude inside your
country (geo guard), the **weather** explains why an agent stopped (network
health), the **agents** view is your running Claude agents (monitoring), and
**usage** is the plan/cost view.

```
              ┌───────────────────────── ~/.tower/ ──────────────────────────┐
              │  state.json   ← daemon writes ~1/s and instantly after a cmd  │
   reads ◀────┤  cmd/<id>.json → a front-end drops a command; daemon runs it  │
              │  config.json    persisted prefs (theme, country, plan budget) │
              │  daemon.lock    flock → only ONE daemon ever runs             │
              │  daemon.log                                                   │
              └───────────────────────────────────────────────────────────────┘
        ▲                              ▲                               ▲
   towerd.py                    src/*.swift                    tower-tui.py
   (the daemon)                 (menu bar app)                 (terminal dashboard)
```

(One-time migration: if a legacy state dir (`~/.corral` or `~/.geo-guard`)
exists and `~/.tower` doesn't, the daemon renames it on startup — config
carries over. It refuses while an old legacy daemon still holds its lock.)

## The daemon — `src/towerd.py` (stdlib only)
Runs these threads:
- **proxy** — a local HTTP/HTTPS proxy on a **sticky port** (prefers **:8888**,
  persisted as `cfg["proxy_port"]` and reused every run so a session pinned to it
  survives a daemon restart; `bind_proxy` retries the sticky port briefly before
  drifting). It CONNECT-tunnels HTTPS, so it sees each request's **hostname** but
  never decrypts traffic. Any host containing `anthropic`, `claude.ai`, or
  `claude.com` is treated as a Claude request. The upstream leg
  (`_upstream_connect`) sets a **long, bounded idle timeout** (`TUNNEL_IDLE_S`,
  not the connect timeout `create_connection` would otherwise strand on the
  socket) and `TCP_NODELAY`, so slow-first-byte and idle keep-alive tunnels aren't
  guillotined mid-session and streamed tokens aren't Nagle-batched. It also sets
  TCP keepalive (60s idle, 4×15s probes) and a 120s retransmission drop time, so a
  path that died silently — a VPN reconnect, a NAT dropping an idle flow — is cut
  and surfaces to Claude as a closed connection (normal retry budget) instead of
  a request that vanishes into a pooled tunnel.
- **geo** — checks the public IP's country every ~15s from **multiple
  independent sources** (`ip-api.com` → `ipwho.is` → `ipapi.co`, first hit
  wins; all proxy-bypassed so they read your real egress IP). Multi-source so
  one provider being down or wrong can't leave the guard "unconfirmed" — which,
  fail-closed, would block Claude. Caches the last known location for instant
  display on launch (display only — a cached reading never allows traffic).
- **usage** — reads Claude Code's own transcripts under
  `~/.claude/projects/**/*.jsonl` to compute **local** token/cost estimates.
  Offset-tailed (only appended lines are parsed), limited to files written inside
  the 7-day window, and counted once per message id — Claude writes a line per
  content block, each repeating the message's usage, with the final output count
  on the last one.
- **plan** — every **60s** runs `claude -p /usage` and parses it for the
  **real** plan limits (session / weekly / Fable %, reset times), the billing
  source (`billing`, e.g. "subscription"), and Claude's own "what's
  contributing to your limits" report per window (`windows["24h"|"7d"]` →
  requests, sessions, ranked `tips` {pct, text, hint}, and `top` skills /
  subagents / mcp_servers {name, pct}) — approximate, this machine only,
  shares overlap; parsed line by line and never allowed to fail `/usage`.
  Claude Code does its own auth; we never read a token. The probe runs with
  `--no-session-persistence` (it used to leave ~1,400 transcripts a day in
  `projects/<CONFIG_DIR encoded>`, which both indexes now skip). `find_claude`
  looks past the app's bare launchd PATH: `claude_path` in config.json, then
  PATH, then known install locations (`~/.local/bin`, Homebrew, npm prefixes,
  fnm / nvm / volta / bun / pnpm / asdf / mise), then any absolute path seen in
  the process table.
- **net** — passive network health. Every 10s (3s while unhealthy) it probes
  `1.1.1.1:443` + `8.8.8.8:53` (IP literals — no DNS dependence) and does a
  timed TCP+TLS handshake to `api.anthropic.com:443` (no HTTP request, no
  cost). Raw sockets only — **never through the proxy** and never urllib
  (macOS urllib silently picks up system proxies). Classifies
  `online / degraded / offline / api_issue / captive` with a 2-sample debounce
  and a captive-portal check, so the UI can answer *"is it my internet, or is
  it Anthropic?"* the moment Claude errors. A completed handshake proves the
  edge is reachable, not that the backend is healthy — if Anthropic itself is
  500ing, `online` is still the right verdict ("it's not you").
  On-demand **speed test** (`{"cmd":"speedtest"}`): downloads 25 MB from
  `speed.cloudflare.com` (OVH fallback), 15s cap, 60s cooldown, direct
  connection (`ProxyHandler({})`).
- **agents** — the control tower, fed by **Claude Code's own HTTP hooks**.
  `hooks_on` adds one observation-only entry per lifecycle event (`HOOK_EVENTS`:
  SessionStart/End, UserPromptSubmit, Pre/PostToolUse(+Failure),
  PermissionRequest, Notification, Stop/StopFailure, SubagentStart/Stop,
  Pre/PostCompact) to `~/.claude/settings.json` — `type: "http"` →
  `http://127.0.0.1:<proxy port>/__tower/hook`, 2s timeout — leaving the user's
  own hooks untouched; `hooks_off` removes exactly those on every clean exit,
  atexit, and Reset. Claude POSTs each event to the proxy listener
  (`_serve_hook`, origin- or absolute-form), which drains the body, answers an
  **empty 200** (no decision — a hook can never change what Claude does) and
  hands the event to `AgentMonitor.on_event`. Status is therefore the event,
  not an inference: `working` (prompt / tool), `pending_tool` (permission
  prompt), `asking` (AskUserQuestion / elicitation / "needs input:"), `done` /
  `failed` (Stop / StopFailure / "failed:"), `idle` (also an `idle_prompt`
  notification, which settles an Esc-interrupted turn), `paused`, `gone`
  (SessionEnd, or its own process exited — an ending, never a failure).
  **Needs-you must stand before it counts** (`_defer` / `_settle`): a
  permission request lands as `pending_tool` only if no progress from that same
  agent follows within `PERM_SETTLE_S` (allow rules / auto mode approve a beat
  later), and a Stop lands as `done` only after `DONE_SETTLE_S` with no new
  activity. A Stop while subagents are still out isn't a stop at all — the row
  stays `working` ("waiting on N subagents…"), and only if the parent doesn't
  resume within `DONE_AFTER_SUBS_S` of the last one reporting back does it
  become `done`. Events carrying `agent_id` drive per-session **subagent**
  rows: type, the brief the parent gave it (the matching `Task`/`Agent` call's
  `description`), live activity, tool count, run time, and its first result line. Each event republishes `state.json` within
  ~50ms. A 3s tick adds what events can't: the kernel process table
  (`_LibProc` — libproc + `KERN_PROCARGS2`, ~1ms, `ps` only as fallback) for
  liveness, pid/tty (focus) and SIGSTOP pauses, matched to sessions by
  session id in the args or by folder — and **sticky**: a session keeps the
  exact process (pid + start time) it was matched to while that process lives,
  however far its working folder wanders (`cd`). The row's project is the
  process's own folder, not the latest event's cwd. Live processes with no hook traffic yet
  get a placeholder row so counts stay truthful. The model/title come from one
  bounded tail read of the transcript per turn — never a full parse. Tower's own
  `claude -p /usage` runs with `disableAllHooks` (and its cwd is filtered) so it
  never shows up. Needs-you queue, collisions (shared `file_path`s from
  PostToolUse), momentum ticks, and transition events are as before. **Guard
  status** (`guarded`) comes from the routing timeline (`cfg["route_log"]`):
  "was routing installed when this process launched?" — a launch within ~5s of a
  flip, or before the timeline, is `null` and never counted. `agents.summary`
  publishes `unguarded` and `pinned` from it. Never injects input into a session.
- **state writer** — builds state every 1s but writes `state.json` only when
  it changed (plus a 2s heartbeat), immediately after any command, and within
  ~50ms of a hook event. The app watches `~/.tower` (DispatchSource) and the TUI
  re-parses only on a new mtime, so an agent row moves in milliseconds.
- **command watcher** — polls `cmd/` every ~60ms, runs the command, writes an
  optional `<id>.done` result.

## Key design decisions
- **Routing is via `~/.claude/settings.json` (`env.HTTPS_PROXY`), never the
  shell.** Editing the shell (aliases) is what used to break the `claude`
  command; settings.json is passive and reversible. Reset removes exactly those
  keys and backs the file up first. **On by default:** the daemon routes Claude
  the moment it starts (i.e. when you open the app) unless you've *explicitly*
  turned routing off (`cfg["routed"] == False`) — you never have to arm it.
- **Fail-CLOSED.** Claude is allowed **only** when the daemon has affirmatively
  confirmed BOTH that you're inside your target country AND that the network has
  a usable path to Anthropic (`State.claude_allowed()`). Anything uncertain —
  location checking/cached/errored, or the net offline/captive/edge-unreachable
  — is blocked. A blocked Claude request is made **PENDING, not FAILED**: the
  daemon **holds** it a few seconds (re-checking, so a sub-second blip clears
  with no visible retry), then replies **`503 Service Unavailable` +
  `Retry-After`** — never `403`. Claude Code retries 5xx into its native
  "Retrying · attempt x/y" spinner (403 it treats as broken auth → "Please run
  /login" → dead turn). Because the 503 answers the CONNECT, Claude Code labels
  it `Couldn't connect through your proxy (ERR_PROXY_TUNNEL)` in that spinner —
  it is still retried (only a 407 or a TLS cert error is fatal). Long-outage tolerance comes from the **retry budget**,
  not the hold: routing also writes `CLAUDE_CODE_RETRY_WATCHDOG` /
  `CLAUDE_CODE_MAX_RETRIES` (`RETRY_ENV`) into settings.json so the agent rides
  out a whole outage and resumes on its own (1500 attempts at ~40 s each ≈
  17 h, sized for 12 h+ unattended multi-agent runs; values older Tower
  versions installed are upgraded in place, a user-set value is never touched) — the hold stays short
  because it's *pre-CONNECT* and a long one risks the client's tunnel connect
  timeout. `RETRY_ENV` also raises `CLAUDE_STREAM_FIRST_BYTE_TIMEOUT_MS` to
  Claude's own 10-minute request ceiling: on a slow link a long chat's
  multi-megabyte upload plus prefill can outlast the default ~3-minute wait for
  response headers, and that path aborts the upload and fails the turn after a
  single retry. There is no allow-through fallback; the defense against false blocks
  is **durable, accurate detection**, so `geo_loop` queries
  multiple independent sources (ip-api → ipwho.is → ipapi.co, proxy-bypassed) and
  a merely-slow ("degraded") link still counts as reachable. `claude -p /usage`
  is gated the same way — it never runs off-country or on an unstable net.
- **Single instance + crash-resilient.** An `flock` on `daemon.lock` means a
  second launch just exits; front-ends can always safely try to start it. The app
  respawns a daemon that dies unexpectedly (its pollTimer notices `alive` gone for
  >10s, throttled to once/30s), and `route_off` runs on every clean exit and via
  `atexit`, so a stranded proxy env is rare and self-healing — the default-on
  startup rewrites `settings.json` for new sessions the moment the daemon is back.
- **"Off means off" for pinned sessions.** The proxy listener outlives routing, so
  a session started while routed keeps its `HTTPS_PROXY` env even after a
  double-confirmed route-off. `State.routed` mirrors that intent: while off,
  `should_block` is a pure pass-through for those pinned tunnels (same direct
  access new sessions get), never a stuck gate. `state.routed` is set only by the
  route command or persisted `cfg["routed"]`; it never fails open on its own.
- **Quit keeps the endpoint alive (relay).** A confirmed `quit` removes routing
  and releases `daemon.lock`, but if any claude process launched while routed is
  still alive, the daemon keeps only its proxy listener running as a pass-through
  (`_relay_for_pinned`, `~/.tower/relay.pid` held under flock) — without it, every
  open chat dies with ECONNREFUSED until restarted. It exits once those pids are
  gone (checked every `RELAY_POLL_S`) or when a new daemon starts: `_evict_relay`
  SIGTERMs it (only while its flock is held) and reclaims the same sticky port, so
  the pinned chats come back under the guard. A signal (SIGTERM/SIGINT) still
  means a full exit — no relay.
- **Transcript parsing is defensive** (usage estimate only). The session JSONL
  format is undocumented and drifts; the usage index wraps every line parse. The
  agent monitor no longer parses transcripts — status comes from hooks; a bad
  hook body counts into `agents.meta.parse_errors` and is dropped.
- **Keep-awake is a policy, not a switch** (`keepawake_loop`). Turning it on
  *arms* it; the Mac is held only while an agent is working (or a request is
  held on the guard), plus a 10-min grace between turns — otherwise it sleeps
  exactly as it would without Tower. The hold is a lone
  `PreventUserIdleSystemSleep` (`caffeinate -i -w <daemon pid>`): never a
  display assertion, so the screen still sleeps, and tied to the daemon so a
  crash can't orphan it. There are no thermal or battery cut-offs: a vigil keeps
  the Mac working (macOS's own critical-battery sleep still applies). The armed
  mode persists in `cfg["keepawake_mode"]`, so a respawned daemon resumes it.
- **Lid-closed needs no password.** Lid sleep is lifted through the
  `IOPMrootDomain` user client (`kPMSetClamshellSleepState`), callable by any
  user — no root, no sudoers rule, no prompt. It's a *kernel* flag that outlives
  the process, so three things release it: the daemon on startup (a crashed
  predecessor's hold), the app the moment the daemon is found dead
  (`LidSleep.restore`), and a reboot. While wanted, the daemon re-asserts it
  every tick, so it self-heals. Older versions used a NOPASSWD
  `pmset disablesleep` rule (`/etc/sudoers.d/geo-guard`); startup clears a
  lingering `disablesleep` from it and Reset still removes the rule.
- **Ports.** If :8888 is busy the proxy steps to the next free port.

## Claude Desktop + Claude on the web
Fenced **per app**, never system-wide: both are Chromium, which takes
`--proxy-server` at launch, so Tower opens them pointed at its own proxy and
their Claude traffic meets the same fail-closed gate as Claude Code. Nothing
else is touched — no system proxy settings, no PAC, no other browser.
- **Desktop** (`open_desktop`) — `open -a Claude.app --args
  --proxy-server=http://127.0.0.1:<port>`. If Desktop is already running
  *without* the flag, Tower only reports it (amber "running unguarded"); a
  relaunch happens on an explicit click: SIGTERM (a clean ⌘Q), wait, reopen.
- **Web** (`open_web`) — claude.ai as an app window (`--app=`) in the first
  installed Chrome-family browser, on a Tower-only profile
  (`~/.tower/web-profile`). **No front-end offers it any more:** a separate
  profile means signing in again, and a running Chrome ignores launch flags, so
  it can never be the user's own browser. The command stays for compatibility.
- **No activity feed.** Tower sees Desktop's traffic, not its chats, so the
  popover shows Desktop only while it runs unguarded (a gap to close; the
  section is off by default) and the dashboard carries the coverage line.
- **Truth from the process** — `_LibProc` already reads every process's args;
  it also notes Claude Desktop's main binary and the web profile's browser
  main process (`_guarded_app_kind`), and `apps_snapshot` publishes
  `apps.desktop {installed, running, guarded}` / `apps.web {available,
  browser, running}` — guarded means the live process carries the flag.
  Guarded app processes count as pinned for the post-quit relay, like a
  routed Claude Code session.

## Command protocol (`cmd/<id>.json`)
`{cmd: "route"|"reset"|"country"|"enforce"|"scope"|"keepawake"|"removekeepawake"
     |"recheck"|"refreshplan"|"planfetch"|"theme"|"speedtest"
     |"focus"|"dismiss"|"undismiss"|"desktop"|"web"|"quit", ...args, id?}` → daemon runs it and
writes `<id>.done` with the result. Fire-and-forget is fine; `state.json`
reflects the outcome within a tick.

- `focus {session_id}` raises that agent's terminal tab (Terminal.app by tty;
  tmux by pane; iTerm2 coded but untested here). Background agents have no
  tab — the reply carries a `claude --resume <id>` fallback the front-ends put
  on the clipboard.
- `desktop {relaunch?}` opens Claude Desktop through the guard; `relaunch`
  quits an unguarded Desktop first (front-ends confirm). `web` opens a guarded
  claude.ai window (kept, but no front-end sends it).
- `dismiss {session_id}` acknowledges a done/failed row (drops it from the
  needs-you queue until its next transition).
- `recheck` re-checks location **and** re-probes network health — one gesture,
  both signals.

## Background processes (seeable + killable)
`state.json.procs` reports the live PIDs (`daemon_pid`, `keepawake_pid`). Both
front-ends surface these and offer "stop the guard & everything", which sends
`quit` — the daemon then removes routing, kills the keep-awake holder
(`caffeinate` on macOS, `systemd-inhibit` on Linux), and exits.

`state.json.platform` says which OS wrote the state — `"macos"`, `"linux"` or
`"windows"` — so a front-end can adapt without guessing from its own platform.

See **[APP.md](APP.md)** and **[TUI.md](TUI.md)** for two of the three
front-ends, **[DESIGN.md](DESIGN.md)** for the design system,
**[LINUX.md](LINUX.md)** for the Debian/Ubuntu packages, the Linux top-bar
radar and the Linux edges, and
**[../windows_plan.md](../windows_plan.md)** for the Windows port plan.
