# UI TRUTH — ground truth for the synthetic film

Everything below is read out of the shipping source, not remembered. Authorities:

| Thing | Authority |
|---|---|
| popover layout / copy | `src/Popover.swift` |
| type + motion + size tokens | `src/DesignSystem.swift` |
| status titles, colours, model badge text | `src/Model.swift` |
| radar + model-mark + beacon geometry | `src/Glyph.swift` |
| terminal dashboard (every card, column-exact) | `src/tower-tui.py` (`draw()` @ L406) |
| app dashboard window | `src/Dashboard.swift` |
| traffic-log record shape | `src/towerd.py` `record()` @ L355 |
| real on-screen values | `promo/analysis/footage.json` |
| colour hexes | `promo/analysis/brand.json` |
| prose rules | `docs/DESIGN.md`, `docs/APP.md`, `docs/TUI.md`, `CLAUDE.md` |

There are **two** distinct real surfaces, and they are NOT the same design.
Do not blend them:

- **A. the menu-bar popover** — SwiftUI, 360 pt wide, flat rows + dividers,
  SF text, colour = macOS system colours.
- **B. the terminal dashboard (`tower`)** — curses, monospace, boxed cards,
  8-colour ANSI palette. This is what fills most of the old recording.
- (C. the app's Dashboard *window* — five tabs; only its Network→Live traffic
  block matters here, and it has a **different column order** from B. See §7.)

---

## 0. Global tokens

### Colour (authority: brand.json + Glyph.swift + DesignSystem.swift)

Brand / identity-study palette (use this for the film's own chrome):

```
ink        #0C0C0E   background
surface    #141416   card / panel
hairline   rgba(255,255,255,0.08)  ≈ #242426
text       #E7E6E2   primary
secondary  #9A9A95
muted      #8B8B86
dim        #7C7C77
kicker     #6E6E6A
amber      #E6A93C   HOLD / warn      (Glyph.swift towerAmber)
red        #E5484D   DANGER/unguarded (Glyph.swift towerRed)
```

macOS system colours actually resolved inside the app in **Dark** mode
(these are what the popover really shows):

```
systemGreen  #30D158   protected / allowed / done
systemOrange #FF9230   blocking, outside-target, waiting-approval, unguarded chip
systemRed    #FF4245   failed, offline, captive
systemIndigo #6D7CFF   asking
systemYellow #FFD600   stall / repo collision
label        #FFFFFF @85%   primary text
label 2nd    #FFFFFF @55%
label 3rd    #FFFFFF @25%
window bg    #1E1E1E
```

> Note the split: the **brand** amber/red (#E6A93C / #E5484D) are used by the
> **radar mark**; the **UI rows** use systemOrange/systemRed. For a synthetic
> redraw, prefer the brand pair everywhere for coherence — but keep the
> *semantic assignment* exactly as below. That's the part that must not drift.

Model tier accents (**text label only — never on the mark**):
`Fable #C9A227 · Opus #B0343C · Sonnet #3B6FB5 · Haiku #E8842C`.

TUI palette is `curses` 8-colour on the terminal's own default background
(`use_default_colors()`, bg = −1), from `init_colors()`:

```
C_TITLE  = WHITE    body text, section titles (bold), hostnames
C_GOOD   = GREEN    ok / allowed / inside target
C_WARN   = YELLOW   held / outside target / blocked-counter
C_DIM    = CYAN     dim labels & section headers (NETWORK LOCATION, GUARD, timestamps)
C_ACCENT = MAGENTA  accent — the "Claude" tag in the traffic log, hints
C_BAD    = RED      danger — blocked rows, INTERNET DOWN header
```

⚠ **C_DIM is literally CYAN, not grey.** In the real recording the section
headers and log timestamps are cyan/teal. For the synthetic version, render
those as brand `muted #8B8B86` (cleaner, still honest — it's the *dim* role);
just never repaint a semantic colour (green/amber/red) into a different meaning.

### Type

Real app: SF (`/System/Library/Fonts/SFNS.ttf`).
`header 13 semibold · rowTitle 13 · activity 11 · counter 11 monospacedDigit ·
section 11 semibold · caption 9`. Technical tokens (model/effort chip) are
**JetBrains Mono** 9.5 / 8.5 bold, the app's bundled face.
TUI: whatever monospace the terminal has; headers are UPPERCASE + A_BOLD.

### Sizes (popover)

`popoverWidth 360 · padH 14 · rowVPad 7 · radiusCard 10 · radiusBadge 6 ·
menubarPt 18 · rowGlyph 28`. Popover scroll body is capped at `maxHeight 460`.

### Motion

`settle spring(0.45, 0.85) · arrive spring(0.55, 0.72) · payoff spring(0.35,
0.60) · sober easeOut 0.25 (failure NEVER bounces) · reorder spring(0.50, 0.80)
· shimmerPeriod 1.8 s · stagger 0.04 s/row · glowHold 0.9 s`.
One loudest thing at a time. The all-clear state has **no looping motion**.

---

## 1. (a) The menu-bar popover

360 pt wide. Wi-Fi-menu idiom: flat rows, hairline `Divider()`s **between**
visible sections only, no card chrome. Order is fixed (it encodes attention):

```
┌─ 360 pt ───────────────────────────────────┐
│ HEADER    radar 30 · Tower / <status> · [◉] │  padH14 / padV10
├─────────────────────────────────────────────┤
│ NET       ● Internet · API      102 ms · 309 ms
├─────────────────────────────────────────────┤
│ AGENTS    AGENTS            55 jobs done today · 1 needs you
│           <needs-you rows>
│           <guard-gap banner>
│           <collision banners>
│           <working agent rows>
│           Resting · 8            (disclosure, collapsed)
├─────────────────────────────────────────────┤
│ LOCATION  🇨🇦 Toronto, CA — inside 🇨🇦 CA        ↻
├─────────────────────────────────────────────┤
│ KEEPAWAKE (beacon) Sleep allowed
│                    The Mac may sleep on its own — a long agent can be cut off.   ⌃⌄
├─────────────────────────────────────────────┤
│ PLAN      PLAN USAGE             updated 24s ago
│           Session  10%  resets in 5h   ▁▁▁▁▁▁▁▁
│           Weekly   53%  resets in 1d   ████▁▁▁▁
│           Fable    33%  resets in 1d   ██▁▁▁▁▁▁
├─────────────────────────────────────────────┤
│ FOOTER    ⌗ Open Dashboard…
│           > Terminal Dashboard…
│           ⚙ Settings…
│           ⏻ Quit & Stop Guard…
└─────────────────────────────────────────────┘
```

### Header row (`PopHeader`)

`HStack(spacing: 10)`, padH 14 / padV 10:

1. **Radar**, 30×30, `color: .primary`, wearing the keep-awake glow.
2. `VStack(spacing: 1)`: `Tower` (13 semibold, primary) over the status line
   (11) tinted by the status colour.
3. `Spacer()`
4. macOS **switch** toggle, `.controlSize(.small)`, help "Route Claude through
   the guard". ON = blue. Turning it OFF fires the two-stage danger alert.

Status line strings — the **only** legal ones (`GuardStatus.title`):

| state | title | tint | radar |
|---|---|---|---|
| starting | `Starting…` | secondary | verify |
| protected | `Protected` | systemGreen | clear |
| blocking | `Blocking Claude` | systemOrange | holdGeo |
| unstable | `Blocking — connection unstable` | systemOrange | holdNet |
| locating | `Blocking — confirming location…` | systemOrange | verify |
| unrouted | `Not routed` | secondary | **off** (red) |
| monitor | `Monitor only` | systemBlue | clear |

Plus one override: while a Claude request is held/retrying, the sub-line is
replaced by **`Reconnecting Claude…`** in the status colour with a
left-to-right **shimmer** (1.8 s sweep). This is the pending state, and it is
the single most important string in the film.

### The radar mark (`drawRadar`, 0…100 box, hub = (50,50))

Redraw spec — all numbers are in the 0…100 box:

- outer ring: `circle(r=33)`, stroke width **6**.
  - `clear`/`verify`: currentColor, solid
  - `holdGeo`: amber, solid
  - `holdNet`: amber, dash `[5,6]`
  - `off`: red, dash `[5,7]`
- **clear**: one expanding pulse ring, r 8→34, opacity 0.5→0, lw 3, period
  ≈ 1/0.42 of the phase unit. Plus 3 blips at (64,41),(38,58),(58,66), r 3.6,
  opacity 0.8±0.2 breathing.
- **verify**: a sweep — filled wedge from hub spanning 270°→208.5° at r 33,
  fill `color@0.16`, plus a 4 pt round-cap line hub→(50,17); whole thing
  rotates at 150°/phase-unit. Blips dim to ~0.3.
- **holdNet**: two amber sonar rings, r 7→22, lw 3.5, opacity →0, offset by
  half a period. No blips. Core is **amber**.
- **holdGeo**: an amber dashed "fence" `circle(r=15)`, lw 3, dash `[4,5]`,
  rotating 45°/unit; a dashed amber ray hub→(72,32), lw 2.5, dash `[2,4]`;
  an amber contact dot r 5 at (72,32) that **lunges outward** ~6 units along
  (−0.773, 0.634) and scales ±16 %; plus a halo ring r 5→14 fading out.
- **off**: red ring `circle(r=5.5)` stroked lw 4 (hollow core), blips at 0.22.
- core: filled `circle(r=4.5)` (5.6 when the vigil lamp is on), amber in
  holdNet, otherwise currentColor.
- keep-awake vigil (any state): 3 stacked soft discs r 15/11/7.5 at
  opacity 0.09/0.15/0.22 + a halo ring r ≈ 9.5–11.2, lw 2.2, opacity 0.44–0.74.
  **Neutral (currentColor) — never amber/red.**

Model marks, same 0…100 box, **monochrome**, `drawModelMark`:
`haiku` 3 ticks at −90/30/150° from r16→r34, lw 8, + core r 7 ·
`sonnet` one S: upper semicircle centred (50,37.5) r 12.5 + lower centred
(50,62.5) r 12.5, lw 8 · `opus` three 300° arcs at r 16/27/38 (gaps at
90/210/330°), lw 6.5, + core r 5 · `fable` an Archimedean spiral 2.35 turns,
r 2.5→35, lw 8, + core r 4.

### Net weather row (`NetRow`)

**online** (the quiet case) — `HStack(spacing: 6)`, padH 14 / padV 6:
`Circle 6×6 systemGreen` · `Internet · API` (12) · `Spacer` ·
`102 ms · 309 ms` (11 monospacedDigit, secondary).
Format is `fmtMs` = `"\(Int(v)) ms"` → **with a space**, em-dash `—` when nil.

Anything else is a **banner**: `HStack(spacing: 8)` = SF Symbol (13 semibold,
tinted) + `VStack(spacing:1)` title (12 semibold, primary) over sub (10,
secondary); background `color.opacity(0.14)` in a 8 pt continuous rounded rect;
inner padding 8, outer padH 10 / padV 5.

| netStatus / reason | icon | colour | title | sub |
|---|---|---|---|---|
| degraded / `dns` | wifi.exclamationmark | orange | `DNS problem` | `Your resolver is failing — not Anthropic` |
| degraded / `api_slow` | clock.badge.exclamationmark | orange | `Slow path to Anthropic` | `handshake 273 ms — link is fine, replies may lag` |
| degraded / `link_slow` (default) | wifi.exclamationmark | orange | `Internet is slow` | `ping 70 ms — expect Claude timeouts` |
| offline | wifi.slash | **red** | `Your internet is offline` | `Claude errors are local — not Anthropic` |
| api_issue | exclamationmark.icloud | orange | `Anthropic API unreachable` | `Your internet is fine (23 ms)` |
| captive | wifi.exclamationmark | **red** | `Wi-Fi login required` | `Open a browser to sign in to this network` |
| checking / unknown | — | — | *renders nothing* | |

**Honesty:** degraded is ORANGE and **still allows traffic**. Only
offline / captive / api_issue is a hold. Never draw a degraded banner next to a
blocked log and imply causation — in the real footage the net was `degraded`
and `online` while traffic flowed fine, and the block came purely from geo.

### Agents section (`AgentsSection`)

Header line: `AGENTS` (caption 9, **heavy**, tracking 0.7, secondary) ·
`Spacer` · summary (11 monospacedDigit, secondary, `.numericText()` tick).
padH 14, top 8, bottom 4.

Popover summary **omits zero parts**, joined ` · `:
`"N at work"`, `"N jobs done today"`, `"N needs you"` (`"needs"`/`"need"`
pluralises). Empty → `quiet`.
(The TUI always prints all three — see §2.)

Needs-you row (`NeedsYouRow`), `HStack(spacing: 9)`, padH 14 / padV 7:
- 22 pt-wide symbol slot. `done`/`waiting_input` get the **DoneCheck**: a 16×16
  systemGreen circle (lw 1.5) with a checkmark path
  `(0.26,0.54) → (0.44,0.72) → (0.76,0.32)` of the box, lw 2 round, that
  **trims 0→1** on arrival (payoff spring, 0.05 s delay), then a 0.9 s
  `st.color@0.12` row glow that fades over 0.4 s.
- otherwise an SF Symbol, 14 semibold, tinted:
  `failed → xmark.octagon.fill` systemRed ·
  `pending_tool → hand.raised.fill` systemOrange ·
  `asking → questionmark.bubble.fill` systemIndigo.
  Failure arrives via `.opacity` transition only — **no bounce, ever**.
- `VStack(spacing: 1)`: line 1 = `HStack(spacing: 6)` project name (13 medium,
  **primary**, 1 line) + **ModelBadge** + optional **unguarded** chip;
  line 2 = subtitle (11, secondary, 1 line).
- `Spacer`, a `Dismiss` borderless button that appears **only on hover**, then
  the age (11 monospacedDigit, tertiary).

Subtitle rules: failed → the `activity` string verbatim (the *reason*, e.g.
`API error — retrying 3/10`); done → `done — your turn · <result first line>`;
otherwise `<phrase> · <title|last_prompt>`.
Phrases: `working · waiting for approval · asked you a question ·
done — your turn · failed · paused · resting · gone`.

Working row (`AgentRow`), same metrics: the living **model mark** (28 pt slot)
instead of a symbol; line 2 is the activity (11, secondary), preceded by a mini
`ProgressView` and **shimmering** only while a tool call is in flight
(`pending_tool != nil`), else the literal string `thinking…`; right side is
`N ✓` (11 monospacedDigit, tertiary, numericText tick) then the age.

**ModelBadge** — a single neutral capsule, colourless by design:
`JetBrainsMono-Medium 9.5` for `Opus 5 · 1M` (leading pad 6, trailing 5),
then a 0.6 pt divider and `JetBrainsMono-Bold 8.5` tracking 0.4 for `HIGH` on
`primary@0.07`. Whole capsule: fill `primary@0.05`, stroke `primary@0.12`
0.6 pt, `foregroundStyle(.secondary)`. Effort compartment omitted when unknown.
`modelDisplay` = tier name + numeric runs from the model id (6+ digit date
suffixes and `[1m]` brackets dropped) + ` · <context>`.

**unguarded chip**: `JetBrainsMono-Bold 8.5`, tracking 0.3, systemOrange on
`orange@0.12`, capsule. Shown only when routing is on AND `guarded == false`.

Guard-gap banner (orange, `shield.slash`, 11 medium + 10 tertiary):
`N chats started before the guard — restart to protect` /
`click a chat to jump to its terminal`. Static — it never pulses.

Collision banner: `arrow.triangle.merge`, systemYellow (repo) or systemRed
(same file), 11 medium: `2 agents in tower` / `2 agents editing Popover.swift
in tower`. Slides in from the top once.

Empty state: a **still** radar (`.clear`, 30 pt, secondary, opacity 0.6),
`No agents running.` (11, secondary), `Run \`claude\` in any terminal and it'll
show up here.` (9, tertiary), centred, padV 14.

Resting: a `DisclosureGroup` labelled `Resting · 8` (11, tertiary), collapsed
by default; expanded rows are `zzz` (10, tertiary, 22 pt slot) + name + age.

### (c) Location row (`LocationRow`)

`HStack(spacing: 7)`, padH 14, padV 6 (4 in compact):

```
🇨🇦  Toronto, CA   — inside 🇨🇦 CA                                  ↻
```

- flag emoji (13) of the **current** cc when located, else of the target cc
- `"\(city), \(country_cc)"` at 12 pt primary — note this is the **cc**, not the
  region: `Toronto, CA`, not `Toronto, Ontario` (that's the TUI's format)
- then `— inside 🇨🇦 CA` (secondary) **or** `— outside 🇨🇦 CA` in
  **Color.orange** — off-country is AMBER, never red
- offline override: `internet down — location unknown, not blocking` in
  systemRed, replacing the whole line
- not-OK: `Locating… (allowing)` secondary
- trailing borderless `arrow.clockwise` (10 medium), help "Re-check location now"

### Keep-awake row (`KeepAwakeRow`)

`HStack(spacing: 11)`, padH 14 / padV 8 (5 compact): **beacon** 26×26, then
title (13 medium) over line (11 secondary, hidden in compact), `Spacer`,
`chevron.up.chevron.down` (10, tertiary). It's a `Menu` styled borderless.

| mode | rowTitle | line |
|---|---|---|
| off | `Sleep allowed` | `The Mac may sleep on its own — a long agent can be cut off.` |
| idle | `Staying awake · lid open` | `Long agents keep running while the lid is open.` |
| clamshell | `Staying awake · lid closed` | `Agents keep running even after you close the lid.` |

Beacon geometry (`drawBeacon`, 0…100): ON = discs r 30/21/13 at
opacity 0.10/0.17/0.26, halo ring r ≈17–19 lw 4.5, solid core r 11.
OFF = ring r 15 lw 4.5 at 0.34 + core r 6 at 0.30. Neutral colour only.

### (f) Plan / usage card (`PlanSection`)

padH 14 / padV 8, `VStack(spacing: 7)`.
Header: `PLAN USAGE` (caption 9 heavy, tracking 0.7, secondary) · `Spacer` ·
`updated 24s ago` or `updating…` (caption 9, tertiary).

Three meters, labels **`Session` / `Weekly` / `Fable`** (the TUI says
`Week all`, the dashboard window says `Weekly (all models)`):

```
Session                         10%   resets in 5h
▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔   ← 4 pt capsule track
```

Row = `HStack(firstTextBaseline)`: label (12 medium) · Spacer · `10%` (13 bold,
monospacedDigit, `.numericText()`) tinted by level · `resets in 5h` (caption 9,
tertiary). Under it a `Meter` 4 pt high: track `secondary@0.16` capsule, fill a
left→right gradient `color@0.85 → color`, min width 3 pt.

Level colour (identical in both front-ends): `< 75 % green · 75–89 % amber ·
≥ 90 % red`.

**The gated state — this is a headline moment, get it exact.** When the guard
isn't passing Claude, `/usage` cannot run, so the card shows a *spacious honest
message instead of numbers*: a centred SF Symbol (20 pt, orange) —
`location.slash` for a geo hold, `wifi.exclamationmark` when `net_ok == false` —
then headline (12 semibold) then detail (caption 9, secondary, centred,
wrapping), padV 16. The two legal texts (`usage_gate()` / `model.usageGate`):

- net: **`Usage paused — connection unstable`** /
  `Can't reach Anthropic right now. Check your internet connection or VPN.
  Usage returns on its own once the link is stable.`
- geo: **`Usage paused — location not confirmed`** /
  `You appear to be outside Canada. If you're on a VPN, set it to Canada.
  Usage returns once your location is confirmed.`

Other states: `Live limits are off — no Claude runs, no permission prompts.` ·
`unavailable — <error>` (orange) · a small spinner + `reading /usage…`.

### Footer

Four borderless menu-item rows, `HStack(spacing: 8)` = SF Symbol (11, 16 pt
slot) + title (13), padH 14 / padV 5:
`gauge.with.dots.needle.67percent  Open Dashboard…` ·
`terminal  Terminal Dashboard…` · `gearshape  Settings…` ·
`power  Quit & Stop Guard…`.

---

## 2. The terminal dashboard — column-exact

Everything is drawn at fixed columns by `draw(win, s)`. `w` = terminal width,
`cardw = w − 4`. Cards are `draw_box(y, x=2, h, w=cardw, title)` — a single-line
box whose UPPERCASE title sits in the top rule.

### Header (row 0–1)

```
col2                                                     right-aligned, 2 from edge
TOWER                              Protected  ·  target: Canada
────────────────────────────────────────────────────────────────  (row 1, C_DIM)
```

`TOWER` = C_TITLE bold at col 2. Right side = `<status><"  ·  target: "><country>`
in the status colour, **bold**, right-aligned to `w − len − 2`. Note the real
separator is **two spaces on each side of the ·**.

TUI status labels (`status_of()`) — net faults outrank the guard:

```
INTERNET DOWN                       C_BAD    (net offline)
WI-FI LOGIN REQUIRED                C_BAD    (captive)
ANTHROPIC API ISSUE                 C_BAD    (api_issue)
Not routed                          C_DIM
Monitor only                        C_DIM
Protected                           C_GOOD
Blocking — connection unstable      C_WARN
Blocking — confirming location…     C_WARN
Blocking Claude                     C_WARN
```

`degraded` deliberately does **not** reach the header — it stays in the NETWORK
card. When `guard.pending` is true the status word is replaced by
`Reconnecting Claude…` drawn with `draw_shimmer()`: a bright band sweeps
per-character on a **1.8 s** period (bold within 1.2 chars of the head, normal
to 2.6, `A_DIM` beyond) — attribute-based, since curses has no gradients.

### (c) NETWORK LOCATION card (left column, rows 2…)

```
row2  col2  NETWORK LOCATION                    C_DIM bold
row3  col3  ✔ inside target                     C_GOOD bold
row4  col3  IP        col12 104.234.138.96
row5  col3  Country   col12 Canada (CA)
row6  col3  Location  col12 Toronto, Ontario
row7  col3  ISP       col12 WorldStream B.V.
```

Labels are `f"{k:<8}"` at **col 3** in C_DIM; values at **col 12** in C_TITLE.
Only four labels, in this order: `IP`, `Country`, `Location`, `ISP`.
Values: `ip` · `f"{cname(cc)} ({cc})"` · `", ".join(city, region)` · `isp`.

Head-line variants — **memorise these**:

| condition | line | colour |
|---|---|---|
| status OK, in target | `✔ inside target` | **C_GOOD** |
| status OK, outside | `✗ outside target — Claude blocked` | **C_WARN (amber/yellow) — NOT red** |
| status CACHED | `· last known (re-checking…)` | C_DIM |
| net offline | `internet down — location unknown, not blocking` | C_BAD |
| error | `location unknown — not blocking` + `! <error>` | C_DIM / C_WARN |
| else | `locating…` | C_DIM |

Glyphs are `✔` (U+2714) and `✗` (U+2717). (footage.json transcribes them as
`✓`/`×`; the source is authoritative.)

`cname()` only knows 44 countries — **`IR` is not in the table**, so the real
render is literally `IR (IR)`, not `Iran (IR)`. That's why footage shows
`Country  IR (IR)`. Reproduce it or pick a country that *is* in the table; do
not "fix" it into `Iran (IR)` and call it real.

### GUARD card (right column, starts at col `rx = min(w−30, 40)`)

```
GUARD                       (C_DIM bold)
Route Claude  on            label f"{k:<13}" at rx (C_DIM), value at rx+13
Enforce       on            on = C_GOOD, off = C_DIM
Scope         Claude only   C_TITLE   (or "ALL traffic")
Allowed       124147        C_GOOD
Blocked       21917         C_WARN when nonzero, else C_DIM
Proxy         :8888 up      C_GOOD when up, C_BAD when down
```

Default port is **8888** (`towerd.PROXY_PORT`). `Scope: Claude only` is the
line that kills the "it kills your whole internet" objection — pair it with an
interleaved allowed/blocked log.

### KEEP AWAKE card

Boxed, 3 rows tall, full width:
`● on · lid open` (C_GOOD bold) or `○ off` (C_DIM bold) at col 4, then the
description in C_DIM, then the right-aligned hint `[w] change` in C_ACCENT.
Descriptions: `Mac stays awake while the lid is open` /
`long agents keep running with the lid closed` /
`Mac may sleep — long agents can be interrupted`.

### (d) NETWORK card — the weather

Boxed, 4 rows tall, title `NETWORK`. Line 1 at col 4, bold, tinted
`online→C_GOOD · degraded→C_WARN · checking→C_DIM · everything else→C_BAD`:

```
● online · net 102ms · api 310ms
● degraded · net 70ms · api 355ms · slow link
● degraded · net — · api 214ms · slow link
● degraded · net 88ms · api 900ms · slow path to Anthropic (link ok)
● degraded · net 61ms · api 240ms · DNS problem
● api issue · internet OK · api.anthropic.com unreachable (<err>)
● Wi-Fi login required — open a browser
● internet down
```

`fmt_ms` here is `f"{v:.0f}ms"` — **no space** (`102ms`). The popover uses
`102 ms` **with** a space. Both are real; pick per surface, don't cross them.
The degraded suffix is chosen by `net.reason`:
`dns → " · DNS problem"`, `api_slow → " · slow path to Anthropic (link ok)"`,
anything else → `" · slow link"`.

Line 2 at col 4: `api ▁▂▃▅▇█▅▃` — a `SPARK = "▁▂▃▄▅▆▇█"` sparkline over the last
`min(30, cardw−44)` `api_ms` history samples, normalised to the max, with
**failed samples pegged at 3000** so an outage reads as a full-height spike.
Then the speed-test slot (`↓ 214 Mbps (3m ago)` / `speed test: 42% …` /
`speed test: never run`) and the right-aligned `click → speed test` in C_ACCENT.

**online vs degraded, precisely:** `degraded` is amber, keeps its `net`/`api`
numbers, adds a reason suffix, stays in the card, and **does not block**.
`online` is green with just the two numbers. Neither one ever produces a
blocked row on its own.

### (e) AGENTS card

Boxed, title `AGENTS`. Line 1, C_TITLE bold at col 4 — the TUI always prints
all three parts, zeros included:

```
0 at work · 55 done today · 1 need you
```

(Compare the popover, which drops zero parts and says `jobs done today`.)

Then up to 6 rows, needs-you first (from `needs_you`), then `working`, then
`paused`. Each row: a marker at **col 4** (bold) and the text at **col 7**.

| reason | marker | colour |
|---|---|---|
| failed | `✗` | C_BAD |
| pending_tool | `⛔` | C_WARN |
| asking | `?` | C_ACCENT |
| done | `✓` | C_GOOD |
| working | `●` | C_DIM (text is drawn with `draw_shimmer`) |
| paused | `⏸` | C_DIM (no shimmer — calm) |

Row text (`agent_row`), parts joined ` · `:

```
<project> — <activity | "done — <result>" | phrase> · <Model V · CTX · EFFORT> [· N ✓] · <age>
```

Real example straight off the recording:

```
✓ nocturne_project — done — owhere in the tree. · Opus 5 · 1M · HIGH · 2m
```

`model_label()` builds `Opus 5 · 1M · HIGH`: tier name, then the numeric runs
from the model id (`[1m]` bracket stripped, 6+ digit date runs dropped), then
` · <context>`, then ` · <EFFORT>` upper-cased. Working rows append `N ✓`.
`ago()` renders `47s` / `2m` / `1.4h` / `3d`.
A session that started before the guard gets `  ·unguarded` appended.
Below the rows: an optional `⚠ 2 agents in tower — both touching Model.swift`
(C_WARN) and an optional guard-gap line.
No agents at all → the card is 3 rows with `no agents running` in C_DIM.

### PLAN LIMITS (not boxed — a rule + a title)

```
────────────────────────────────────────────
PLAN LIMITS    updated 24s ago             ← title col2 C_TITLE bold; note col15
Session     ████░░░░░░░░░░░░░░░░░░░░░░░░░░   10% used   resets in 5h
Week all    ███████████████░░░░░░░░░░░░░░░   53% used   resets in 1d
Fable       █████████░░░░░░░░░░░░░░░░░░░░░   33% used   resets in 1d
last 24h · 128 requests · 6 sessions
```

Bars start at `BX = 12`, width `BAR_W = clamp(w−60, 12, 30)`, values at
`VX = BX + BAR_W + 2`. `bar()` uses full blocks `█`, an eighths remainder from
`" ▏▎▍▌▋▊▉"`, and `░` for the track. Bar colour: `<75 C_GOOD · 75–89 C_WARN ·
≥90 C_BAD`, bold. Value text `f"{p:3d}% used"` + `   resets <rel>` in C_DIM,
where the reset is rendered **relative and timezone-free** (`in 5h`, `in 1d`,
`now`).

Note-at-col-15 variants: `updated 24s ago` (C_GOOD) · `updating…` ·
`paused — guard not passing` (C_WARN) · `live limits off (no Claude runs)` ·
`unavailable — <err>` · `fetching from Claude /usage…`.

When gated the bars are **replaced** (never shown stale) by the same two-line
message as the popover, wrapped to `w−8` at col 3: headline in C_WARN bold, a
blank line, then the detail in C_DIM.

### local estimate (deliberately quiet, clearly separated)

```
local estimate   · measured on this machine, not your plan %
    Session   1.2M tokens    $255.00    148 msgs    47m
    Week      18.4M tokens   $7307      ~2.96B projected
    Models    Opus 12.1M · Sonnet 4.2M · Haiku 1.1M
    Trend 7d  ▃▅▂▇█▄▆    1.4K/min now
```

Labels at col 4 (C_DIM), values at col 14 (C_TITLE). `fmt_tok` → `1.2K/1.2M/
1.20B`; `fmt_cost` → `$255` when ≥100 else `$7.31`.
This block must always read as **an estimate, not your plan %**.

### (b) LIVE TRAFFIC — the money block

```
────────────────────────────────────────────────────────────────
LIVE TRAFFIC   124147 allowed · 21917 blocked          C_TITLE bold, col 2
col3      col12        col24    col32
17:43:18  ✔ allowed    Claude   api.anthropic.com
17:43:18  ✔ allowed    Claude   api.anthropic.com
17:43:16  ⛔ blocked    Claude   api.anthropic.com
17:43:14  ✔ allowed    other    bridge.claudeusercontent.com
17:43:11  ⛔ blocked    Claude   api.anthropic.com
```

Exact truth, from `draw()` L782-794 and `towerd.record()`:

| column | x | content | attr |
|---|---|---|---|
| timestamp | **3** | `%H:%M:%S`, 8 chars | `C_DIM` |
| verdict | **12** | `✔ allowed` / `⛔ blocked` | `C_GOOD` / `C_BAD`, **bold** |
| kind | **24** | `Claude` / `other` | `C_ACCENT` / `C_DIM` |
| host | **32** | hostname, clipped to `w−34` | `C_TITLE` |

- Order is **timestamp → verdict → kind → host**. Newest **first**
  (`for r in reversed(recent)`), so new rows push in at the **top** and older
  ones fall off the bottom. The ring buffer is `deque(maxlen=50)`.
- Glyphs: `✔` U+2714 and `⛔` U+26D4. footage.json writes `✓`/`⛔`; the source
  wins. The **only red in the entire 87 s recording is this `blocked` column** —
  verified by a per-frame red-pixel scan.
- Header counters are `guard.allowed` / `guard.blocked`, whole numbers, no
  thousands separators.
- Empty: `waiting for requests — run  claude  in another terminal` (C_DIM).
- The block is drawn last and simply fills to `h − 2`, so the visible row count
  is whatever fits.

Footer, always: a rule at `h−2` and
`press  Enter  or click here for the actions menu     ·     q  to quit` (C_DIM).

---

## 3. REAL VALUES — the only numbers/strings we may put on screen

All from `promo/analysis/footage.json`, which is a frame-accurate transcription
of the actual 87.4 s recording. Prefer these over anything invented.

### Location (real, observed)

| field | inside-target reading | outside-target reading |
|---|---|---|
| head | `✔ inside target` (green) | `✗ outside target — Claude blocked` (**amber**) |
| IP | `104.234.138.96` → **REDACT to `***.***.***.***`** | `5.201.242.113` → **REDACT** |
| Country | `Canada (CA)` | `IR (IR)` |
| Location | `Toronto, Ontario` | `Tehran, Tehran` |
| ISP | `WorldStream B.V.` | `MCI` |
| target | `target: Canada` (cc `CA`) | same |

Popover form of the same fact: `🇨🇦 Toronto, CA — inside 🇨🇦 CA` /
`🇮🇷 Tehran, IR — outside 🇨🇦 CA` (the trailing clause is orange).

### Guard counters (real timeline)

| t (s) | allowed | blocked |
|---|---|---|
| 0.0 | 124147 | 21917 |
| 8.0 | 124147 | 21927 |
| 8.9 | 124153 | 21927 |
| 35.0 | 124168 | 21927 |
| 44.1 | 124168 | 21928 |
| 56.0 | — | 21936 |
| 67.3 | — | 21947 |
| 70.0 | 124173 | — |
| 81.4 | 124178 | **21968 (final)** |
| 83.0 | 124188 | 21968 |
| 86.0 | **124200** | 21968 |

Safe pattern for a synthetic counter: start `124147 / 21917`, end
`124200 / 21968`. Both are real endpoints of the real recording.

### Network readings (real samples)

```
degraded · net —     · api 214ms · slow link      (t=0)
degraded · net —     · api 475ms · slow link      (t=12)
degraded · net 70ms  · api 355ms · slow link      (t=20)
online   · net 102ms · api 310ms                  (t=24)
online   · net 85ms  · api 270ms                  (t=30)
online   · net 82ms  · api 273ms                  (t=40)
online   · net 140ms · api 262ms                  (t=50)
online   · net 107ms · api 1040ms                 (t=60)
online   · net 69ms  · api 612ms                  (t=70)
online   · net 86ms  · api 457ms                  (t=80)
online   · net 71ms  · api 408ms                  (t=86)
```

Popover-format pairs actually observed (with the space):
`102 ms · 309 ms` · `81 ms · 273 ms` · `140 ms · 261 ms` · `64 ms · 898 ms`.

**The load-bearing fact:** the network **never** went offline/captive during the
whole clip. It stayed `online` right through the off-country block. Geo and net
are visibly independent axes. Do not let the film imply the block came from the
network.

### Agents (real, static for all 87 s)

```
TUI:      0 at work · 55 done today · 1 need you
row:      ✓ nocturne_project — done — owhere in the tree. · Opus 5 · 1M · HIGH · 2m
          (age ticks 2m → 3m at t≈57)
popover:  55 jobs done today · 1 needs you
          nocturne_project · [Opus 5 · 1M][HIGH] · done — your turn · 2m
resting:  Resting · 8 (t=0) → Resting · 7 (t=37) → Resting · 6 (t=50)
```

`nocturne_project` is the only real agent name in the footage. If the film needs
more rows (and it should — the recording's "0 at work" is the #1 off-pitch flag),
invent **plausible project-directory names only** — they're just folder names,
not claims — and keep every other field within the real ranges above. Never
invent a *status* the app can't produce; the legal set is
`working · pending_tool · waiting_input · asking · done · failed · idle · gone ·
paused`.

### Plan usage (real, the only frame in the whole reel with live bars, t≈25.0)

```
Session  10%   resets Jul 26 at 9pm   → renders as "resets in 5h"
Weekly   53%   resets in 1d
Fable    33%   resets in 1d
```

All three are green under the 75 % threshold. Also observed:
`PLAN USAGE  updated 24s ago` / `updated 59s ago` / `updated 73s ago` /
`updated 80s ago`.

### Keep-awake

`Sleep allowed` for the whole clip (mode `off`, hollow beacon).

### Header / status strings actually observed

```
0.0 – 8.9   Reconnecting Claude…                    (dim, shimmering)
8.9 – 35.1  Protected  ·  target: Canada            (green, steady)
35.1– 39.2  Blocking Claude  ·  target: Canada      (amber, steady)
39.2– 81.4  Reconnecting Claude…  ·  target: Canada (dim, shimmering)
81.4– 87.4  Protected  ·  target: Canada            (green, steady)
```

Popover status strings observed: `Reconnecting Claude…`, `Protected`,
`Blocking Claude`. Popover gate message observed every time usage was gated:
`Usage paused — location not confirmed` + `You appear to be outside CA. If
you're on a VPN, set it to CA…`.

### Traffic hosts actually seen

```
api.anthropic.com                       kind = Claude   (allowed AND blocked)
bridge.claudeusercontent.com            kind = other    (always allowed)
http-intake.logs.us5.datadoghq.com      kind = other    (always allowed)
registry.npmjs.org                      kind = other    (always allowed)
```

Real timestamps ran `17:43:07` → `17:44:31`. A synthetic log can walk that same
clock. The interleave of green `other` rows through a run of red `Claude` rows
is real and is the strongest single frame for "Claude only, not your internet".

---

## 4. REDACT / never show

1. **Public IPs.** `104.234.138.96` and `5.201.242.113` are real, live,
   attributable addresses. Render as `***.***.***.***` (what the old film did),
   or `104.234.***.***`. City / region / ISP / country may stay — those are the
   product's point.
2. **VPN client internals** from the left half of the old frame: config names
   `WS-Mohammad_Sina-CDN`, `HTTP-Mohammad_Sina-CDN-137.35GB`, partial servers
   `185.****:443`, `37.3****:443`, quota `362.65 GB / 500 GB`. The new film has
   no VPN window at all — keep it that way.
3. **Spend figures** `Session $255`, `Week $7307`, `~2.96B projected`. If a
   local-estimate block appears, scale to something modest (e.g. `$4.10` /
   `$63` / `~410M projected`) and keep the "estimate, not your plan %" label.
4. Anything dating the shoot: the desktop screenshot thumbnail
   `Screenshot 2026-0…3PM`, the macOS menu-bar clock.
5. Real person's name anywhere in a path or window title.

---

## 5. Semantic traps — the things a synthetic redraw will get wrong

1. **Outside-target is AMBER, not red.** Both surfaces. Verified by a red-pixel
   scan of all 874 frames: the only red anywhere was the `blocked` column of the
   traffic log. A "red = wrong country" motion-graphics language would be a lie.
2. **A block is PENDING, not FAILED.** Never draw `ERROR`, `FAILED`, `403`, a
   red X on a request, or a broken-connection metaphor for a blocked request.
   The truthful vocabulary is: held → `503 + Retry-After` → Claude's own retry
   → resumes by itself. Tower's own word for it is `Reconnecting Claude…`.
3. **Degraded/slow still ALLOWS.** Amber net banner + green traffic is a valid,
   real frame. Only offline / captive / edge-unreachable holds.
4. **`Scope: Claude only`.** Non-Claude hosts stay green even while
   `api.anthropic.com` is red. Show it.
5. **Never show plan numbers while gated.** The gated card is a *message*, and
   it names the cause (connection vs location). Stale bars would break the
   product's core promise.
6. **The menu bar never counts running agents.** Only the needs-you count
   (optional) and optionally usage %.
7. **Failure never bounces.** `sober` = easeOut 0.25 s, opacity only.
   Done is the only thing that gets a spring, and only once.
8. **One loudest thing.** Never two pulsing elements in one frame. In the
   all-clear state, nothing loops at all.
9. **Model marks are monochrome.** The tier accent appears only in small text.
10. **The radar carries the guard state; the lamp carries keep-awake.** The lamp
    is always neutral so a hold outranks it. They compose, never collide.
11. Tower is **not** a VPN / firewall / kill switch, doesn't read traffic,
    prompts, or tokens, and guards **Claude Code only**. Full list:
    `promo/analysis/brand.json → do_not_claim` (23 entries) — read it before
    writing any on-screen copy.

---

## 6. Composition notes for a redraw

- Popover is **360 pt** wide. At 1920×1080 a 2× render (720 px) sits nicely as a
  hero card; 2.5× (900 px) if it's alone on screen. Its scroll body caps at
  460 pt, so a full popover is roughly 360 × 560 pt including header+footer.
- The TUI is monospace: pick a cell grid and honour the literal column indices
  (3 / 12 / 24 / 32 for traffic; 3 / 12 for the location card; `rx=40` for the
  GUARD column) — that's what makes it read as the real thing rather than a
  mock. A 96-column × ~34-row terminal reproduces the recording's proportions.
- Section headers are UPPERCASE + bold + the dim role colour; there is **no**
  letter-spacing in the TUI (curses can't), but the popover's `AGENTS` /
  `PLAN USAGE` do carry `tracking 0.7` at 9 pt heavy.
- The recording's single best structural beat, and the one to rebuild
  synthetically: **one frame** where the location card flips green→amber, the
  header flips `Protected`→`Blocking Claude`, and the plan card swaps to
  `Usage paused — location not confirmed` — all simultaneously — followed by the
  traffic log turning over one row at a time, and finally the recovery burst
  where held requests all land on the **same second** (real: six rows all
  stamped `17:43:18`). That burst is the literal on-screen proof of
  "pending, not failed", and it is the only proof we have — no Claude Code
  terminal was ever in frame.

---

## 7. Difference table — the same fact, three surfaces

| fact | popover | TUI | dashboard window |
|---|---|---|---|
| latency | `● Internet · API   102 ms · 309 ms` | `● online · net 102ms · api 310ms` | same NetRow as popover + a 2-series line chart |
| traffic row order | — | `time · verdict · kind · host` | `time · host · [kind pill] · [verdict pill]` |
| verdict marks | — | `✔ allowed` / `⛔ blocked` | capsule pills: `claude`(blue)/`other`(gray), `allowed`(green)/`blocked`(red), 9 pt semibold on `color@0.15` |
| newest row | — | **top** | **top** (`.suffix(12).reversed()`) |
| weekly meter label | `Weekly` | `Week all` | `Weekly (all models)` |
| agents summary | zero parts dropped, `jobs done today` | always all three, `done today` | full table |
| location line | `Toronto, CA — inside 🇨🇦 CA` | 4 labelled rows incl. `Ontario` | `Toronto, Ontario · WorldStream B.V. · 104.234.138.96` under the status title |
| off-country tint | `Color.orange` | `C_WARN` | `systemOrange` status tint |

Pick **one** traffic-row layout for the film and stay with it. The TUI's
`time · verdict · kind · host` is the more legible of the two at distance and is
what the recording shows, so it is the recommended one.
