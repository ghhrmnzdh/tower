# Corral — Architecture (shared by both front-ends)

Corral has **one brain and two faces**. A single background **daemon** holds
all logic and state; a **menubar app** (Swift) and a **terminal dashboard**
(Python/curses) are thin views over it. They never talk to each other — they
both read one state file and drop command files.

The metaphor carries the product: the **fence** keeps Claude inside your
country (geo guard), the **weather** explains why a horse stopped (network
health), the **herd** is your running Claude agents (monitoring), and the
**feed bill** is usage.

```
              ┌───────────────────────── ~/.corral/ ──────────────────────────┐
              │  state.json   ← daemon writes ~1/s and instantly after a cmd  │
   reads ◀────┤  cmd/<id>.json → a front-end drops a command; daemon runs it  │
              │  config.json    persisted prefs (theme, country, plan budget) │
              │  daemon.lock    flock → only ONE daemon ever runs             │
              │  daemon.log                                                   │
              └───────────────────────────────────────────────────────────────┘
        ▲                              ▲                               ▲
   corrald.py                    src/*.swift                    corral-tui.py
   (the daemon)                 (menu bar app)                 (terminal dashboard)
```

(One-time migration: if `~/.geo-guard` exists from the Geo Guard era and
`~/.corral` doesn't, the daemon renames it on startup — config carries over.
It refuses while an old geoguardd still holds its lock.)

## The daemon — `src/corrald.py` (stdlib only)
Runs these threads:
- **proxy** — a local HTTP/HTTPS proxy on **:8888** (fixed, so routing stays
  stable). It CONNECT-tunnels HTTPS, so it sees each request's **hostname** but
  never decrypts traffic. Any host containing `anthropic`, `claude.ai`, or
  `claude.com` is treated as a Claude request.
- **geo** — checks the public IP's country every ~15s from **multiple
  independent sources** (`ip-api.com` → `ipwho.is` → `ipapi.co`, first hit
  wins; all proxy-bypassed so they read your real egress IP). Multi-source so
  one provider being down or wrong can't leave the guard "unconfirmed" — which,
  fail-closed, would block Claude. Caches the last known location for instant
  display on launch (display only — a cached reading never allows traffic).
- **usage** — reads Claude Code's own transcripts under
  `~/.claude/projects/**/*.jsonl` to compute **local** token/cost estimates.
- **plan** — every **60s** runs `claude -p /usage` and parses it for the
  **real** plan limits (session / weekly / Fable %, reset times). Claude Code
  does its own auth; we never read a token.
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
- **agents** — the control tower. Every ~2s it enumerates `claude` processes
  (`ps`), maps them to sessions (session id / transcript path straight from
  the args; `lsof` cwd as fallback), and offset-tails each live session's
  transcript to derive per-agent status: `working`, `pending_tool` (waiting
  for approval — or a slow tool; honest heuristic), `asking`, `done`,
  `failed`, `idle`, `gone`. It ranks a **needs-you queue**
  (failed > blocked > asking > done), detects **same-repo collisions**
  (escalating when two agents touch the same file), tracks momentum ticks
  (tools done / files touched / errors), and publishes state transitions as
  events the app turns into notifications. **Read-only toward Claude Code**:
  it never writes into `~/.claude` and never injects input.
- **state writer** — writes `state.json` atomically ~1/s (and immediately after
  any command, so the UI reflects changes in ~60ms).
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
  /login" → dead turn). Long-outage tolerance comes from the **retry budget**,
  not the hold: routing also writes `CLAUDE_CODE_RETRY_WATCHDOG` /
  `CLAUDE_CODE_MAX_RETRIES` (`RETRY_ENV`) into settings.json so the agent rides
  out a whole network switch and resumes on its own — the hold stays short
  because it's *pre-CONNECT* and a long one risks the client's tunnel connect
  timeout. There is no allow-through fallback; the defense against false blocks
  is **durable, accurate detection**, so `geo_loop` queries
  multiple independent sources (ip-api → ipwho.is → ipapi.co, proxy-bypassed) and
  a merely-slow ("degraded") link still counts as reachable. `claude -p /usage`
  rides the same gate — it never runs off-country or on an unstable net.
- **Single instance.** An `flock` on `daemon.lock` means a second launch just
  exits; front-ends can always safely try to start it.
- **Transcript parsing is defensive.** The session JSONL format is
  undocumented and drifts between Claude Code versions (observed mid-file).
  Every line parse is wrapped; unknown types are skipped;
  `agents.meta.parse_errors` surfaces drift instead of crashing. Worst case a
  session shows an unknown status — guard features are never affected.
- **Keep-awake.** `caffeinate` covers lid-open. Lid-closed needs root
  (`pmset disablesleep`); we ask for the password **once** and install a
  tightly-scoped, `visudo`-validated NOPASSWD rule for just those two commands,
  so it never nags again. Reset removes it. (The sudoers file keeps its legacy
  `geo-guard` name so existing installs don't re-prompt.)
- **Ports.** If :8888 is busy the proxy steps to the next free port.

## Command protocol (`cmd/<id>.json`)
`{cmd: "route"|"reset"|"country"|"enforce"|"scope"|"keepawake"|"removekeepawake"
     |"recheck"|"refreshplan"|"planfetch"|"theme"|"speedtest"
     |"focus"|"dismiss"|"undismiss"|"quit", ...args, id?}` → daemon runs it and
writes `<id>.done` with the result. Fire-and-forget is fine; `state.json`
reflects the outcome within a tick.

- `focus {session_id}` raises that agent's terminal tab (Terminal.app by tty;
  tmux by pane; iTerm2 coded but untested here). Background agents have no
  tab — the reply carries a `claude --resume <id>` fallback the front-ends put
  on the clipboard.
- `dismiss {session_id}` acknowledges a done/failed row (drops it from the
  needs-you queue until its next transition).
- `recheck` re-checks location **and** re-probes network health — one gesture,
  both signals.

## Background processes (seeable + killable)
`state.json.procs` reports the live PIDs (`daemon_pid`, `keepawake_pid`). Both
front-ends surface these and offer "stop the guard & everything", which sends
`quit` — the daemon then removes routing, kills `caffeinate`, and exits.

See **[APP.md](APP.md)** and **[TUI.md](TUI.md)** for the two front-ends,
**[DESIGN.md](DESIGN.md)** for the design system, and
**[../windows_plan.md](../windows_plan.md)** for the Windows port plan.
