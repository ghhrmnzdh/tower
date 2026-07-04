# Tower — Design System

> **Quiet tower, clear signal.** A well-run tower is calm. Motion is
> information: agents work in a steady rhythm, and exactly one thing at a
> time is allowed to call for you.

Premium means Apple-grade restraint — Dynamic-Island/watchOS-rings polish, not
fireworks. Three rules every component traces to:

1. **The mark is the state.** The radar *is* the guard; a model mark *is* the
   model. Nothing decorative signals status.
2. **Motion = state change.** Celebration is earned (done), never granted
   (failure is sober). Nothing loops at full attention when all is well; a mark
   is alive only while its state has something to say.
3. **One loudest thing.** A strict attention hierarchy; at most one element
   pulses at a time.

## The radar — Tower's mark

Tower's identity is a **radar on a control tower**: an outer ring, a center, and
the contacts and signals that move around it. Its state *is* the guard, distilled
to five looks (`RadarState`, `src/Glyph.swift`):

| State | Look | Means |
|---|---|---|
| **clear** | monochrome ring, calm outward pulse, live blips | guarding · in-country + path open |
| **verify** | a sweep rotates with a soft trail | confirming location; held until sure |
| **holdNet** | amber dashed ring, sonar pings, amber core | no usable path — held pending, self-clears |
| **holdGeo** | amber ring, rotating fence, a lunging off-country blip | wrong country / VPN — held, not failed |
| **off** | red dashed ring, hollow red core | routing off — direct requests. **Danger** |

The **menu bar is the radar**, rendered in **full color** so it reads exactly
like the popover header: the amber/red brand tones *are* the signal, with a
neutral resolved from the bar's own appearance for everything else (never a flat
template tint — that would throw away the amber-hold-vs-red-unguarded
distinction). It animates only when a state has motion worth spending frames on —
a hold, a verify sweep, or a calm scan while agents are working — and freezes
under Reduce Motion. The same radar anchors the popover header, the empty state,
and the app icon. Hold/danger tones: amber `#E6A93C`, red `#E5484D`.

## Model marks

One **monochrome** mark per Claude model tier — a center and the lines around
it. Deliberately colorless and minimal: still at rest, and while its agent
works each comes alive in its own way — haiku's ticks breathe outward, sonnet
turns, opus's rings orbit, fable's spiral winds. Motion is smooth (a 60fps
`Canvas` TimelineView, paused when idle / under Reduce Motion).

| Model | Mark |
|---|---|
| **Fable** | a spiral, a highlight winding up it |
| **Opus** | three orbiting rings + a pulsing core |
| **Sonnet** | a single S stroke, slowly turning |
| **Haiku** | three ticks breathing out + a core |

The tier accent (Fable gold `#C9A227`, Opus rosso `#B0343C`, Sonnet steel
`#3B6FB5`, Haiku crayon `#E8842C`) appears only in the row's small text label —
never on the mark itself.
All marks are drawn in a 0…100 box by `drawRadar` / `drawModelMark`
(`src/Glyph.swift`); one geometry backs both the live SwiftUI `Canvas` views and
the menu-bar templates baked by `ImageRenderer`.

## Status → attention semantics

Done-vs-failed is unmistakable **without color** — distinct symbol shapes,
fixed queue positions, distinct motion:

| State | Color | Symbol | Motion | Position |
|---|---|---|---|---|
| failed | systemRed | `xmark.octagon.fill` | sober fade — **never bounces** | Needs You, rank 1 |
| blocked (approval) | systemOrange | `hand.raised.fill` | one pulse on arrival | Needs You, rank 2 |
| asking | systemIndigo | `questionmark.bubble.fill` | one pulse on arrival | Needs You, rank 3 |
| done | systemGreen | checkmark **draws on** (trim 0→1) | payoff spring + 0.9s glow | Needs You, rank 4 |
| stall / loop | systemYellow | `exclamationmark.triangle.fill` | none | agent row, badged |
| working — thinking | monochrome | the model mark | alive — per-model motion (60fps) | Agents |
| working — tool in flight | secondary | activity line | shimmer sweep (1.8s) | Agents |
| guard pending — reconnecting | status warn | `arrow.triangle.2.circlepath` | "Reconnecting Claude…" shimmer sweep (1.8s) | header sub-line |
| collision | yellow (repo) / red (same file) | `arrow.triangle.merge` | slides in once | banner above agents |
| idle | tertiary | `zzz` | none | Resting, collapsed |

Attention hierarchy: menubar badge > Needs-You order > collision banner > the
radar's own motion. Notifications fire on →failed/→blocked/→asking always;
→done only if the popover hasn't been opened in 60s.

## Motion tokens (`src/DesignSystem.swift`)

| Token | Value | Used for |
|---|---|---|
| `settle` | spring(response 0.45, damping 0.85) | any state swap |
| `arrive` | spring(0.55, 0.72) | entrances (slight overshoot) |
| `payoff` | spring(0.35, 0.60) | the done pop |
| `sober` | easeOut 0.25s | failure — no bounce, ever |
| `reorder` | spring(0.50, 0.80) | queue re-ranking (matchedGeometry) |
| `shimmerPeriod` | 1.8s | in-flight activity lines |
| `stagger` | 0.04s/row | multi-row inserts |
| `glowHold` | 0.9s | done-glow before settling |

The **dopamine layer**: the summary line (`3 at work · 41 jobs done today · 1
needs you`) and per-row `n ✓` counters tick up with
`.contentTransition(.numericText())` as agents complete tools — visible
momentum. The done payoff is one composite ~0.6s gesture (check draws on, row
glows, counter ticks), then quiet. The radar animation is driven at ~30fps only
while the state warrants it, and paused otherwise.

**Restraint rules** (enforced in review): at most one glowing row at a time
(newest wins); the quiet state is completely still; **Reduce Motion** degrades
everything — loops stop, springs become 0.2s fades, counters set directly, and
each radar state freezes at a legible still frame.

## Layout

Popover: 360pt wide, flat rows + dividers (Wi-Fi-menu style, no card chrome).
Section order = attention order: header (radar + route toggle) → net weather →
Needs You → collisions → Agents → Resting → location → plan meters → footer.
Type scale: header 13 semibold · row title 13 · activity 11 secondary ·
counters 11 monospaced-digit · section headers 11 semibold secondary.
Empty state: a still radar and "No agents running." — calm, fully quiet.
