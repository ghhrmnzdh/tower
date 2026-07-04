# Corral — Design System

> **Fine tack, calm hands.** A well-run stable is quiet. Motion is
> information: the herd works in a calm rhythm, and exactly one thing at a
> time is allowed to call for the rancher.

Premium means Apple-grade restraint — Dynamic-Island/watchOS-rings polish, not
fireworks. Three rules every component traces to:

1. **Craft = caliber.** The finer the model, the finer the art. Nothing else
   signals tier.
2. **Motion = state change.** Celebration is earned (done), never granted
   (failure is sober). Nothing loops at full attention when all is well.
3. **One loudest thing.** A strict attention hierarchy; at most one element
   pulses at a time.

## The horse design language

One horse per Claude model tier. Same silhouette family — left-facing, same
pose skeleton, consistent baseline — only the *craftsmanship* changes.
Rule of thumb: **crayon → flat vector → sculpted badge → gilded myth.**

| Model | Horse | Art style | Feel |
|---|---|---|---|
| **Fable** | Mythic winged stallion | Illuminated-manuscript, gold-leaf heraldry, fine linework | storyteller, ornate & legendary |
| **Opus** | Prancing stallion emblem | Ferrari-grade: sculpted, glossy, premium badge | flagship, top-shelf |
| **Sonnet** | Clean galloping horse | Modern flat vector, confident lines | balanced, everyday workhorse |
| **Haiku** | Little pony | Child's crayon doodle, wobbly outline | fast, playful, light |

The **menu bar is the live signal of which caliber of model is working right
now**: the highest-tier horse among running agents (template monochrome — tier
reads from silhouette detail alone), the horseshoe when the corral is quiet.
Full color lives in the popover, dashboard, notifications, and the app icon
(a gilded stallion inside a corral-fence ring).

Tier accents (popover only, never the sole signal): Fable gold `#C9A227`,
Opus rosso `#B0343C`, Sonnet steel `#3B6FB5`, Haiku crayon `#E8842C`.

Assets are hand-authored SVGs in `assets/horses/` (CoreSVG subset: paths +
gradients only), loaded straight into `NSImage` at runtime; the loader falls
back `.svg → .pdf → SF symbol` so a missing asset never blanks the menu bar.

## Status → attention semantics

Done-vs-failed is unmistakable **without color** — distinct symbol shapes,
fixed queue positions, distinct motion:

| State | Color | Symbol | Motion | Position |
|---|---|---|---|---|
| failed | systemRed | `xmark.octagon.fill` | sober fade — **never bounces** | Needs You, rank 1 |
| blocked (approval) | systemOrange | `hand.raised.fill` | one pulse on arrival | Needs You, rank 2 |
| asking | systemIndigo | `questionmark.bubble.fill` | one pulse on arrival | Needs You, rank 3 |
| done | systemGreen | checkmark **draws on** (trim 0→1) | payoff spring + 0.9s glow | Needs You, rank 4 |
| stall / loop | systemYellow | `exclamationmark.triangle.fill` | none | herd row, badged |
| working — thinking | tier accent | the horse itself | breathe loop (2.4s) | The Herd |
| working — tool in flight | secondary | activity line | shimmer sweep (1.8s) | The Herd |
| guard pending — reconnecting | status warn | `arrow.triangle.2.circlepath` | "Reconnecting Claude…" shimmer sweep (1.8s) | header sub-line |
| collision | yellow (repo) / red (same file) | `arrow.triangle.merge` | slides in once | banner above herd |
| idle | tertiary | `zzz` | none | Resting, collapsed |

Attention hierarchy: menubar badge > Needs-You order > collision banner > herd
breathing. Notifications fire on →failed/→blocked/→asking always; →done only
if the popover hasn't been opened in 60s.

## Motion tokens (`src/DesignSystem.swift`)

| Token | Value | Used for |
|---|---|---|
| `settle` | spring(response 0.45, damping 0.85) | any state swap |
| `arrive` | spring(0.55, 0.72) | entrances (slight overshoot) |
| `payoff` | spring(0.35, 0.60) | the done pop |
| `sober` | easeOut 0.25s | failure — no bounce, ever |
| `reorder` | spring(0.50, 0.80) | queue re-ranking (matchedGeometry) |
| `breathe` | easeInOut 2.4s, autoreverses | the working horse |
| `shimmerPeriod` | 1.8s | in-flight activity lines |
| `stagger` | 0.04s/row | multi-row inserts |
| `glowHold` | 0.9s | done-glow before settling |

The **dopamine layer**: the herd summary line (`3 at work · 41 jobs done
today · 1 needs you`) and per-row `n ✓` counters tick up with
`.contentTransition(.numericText())` as agents complete tools — visible
momentum. The done payoff is one composite ~0.6s gesture (check draws on, row
glows, counter ticks), then quiet. The menu bar horse takes a subtle 2-frame
canter step every 1.2s only while a tool call is in flight.

**Restraint rules** (enforced in review): at most one glowing row at a time
(newest wins); no loop faster than 1.2s; the quiet state is completely still;
**Reduce Motion** degrades everything — loops stop, springs become 0.2s
fades, counters set directly, the canter freezes.

## Layout

Popover: 360pt wide, flat rows + dividers (Wi-Fi-menu style, no card chrome).
Section order = attention order: header (guard + route toggle) → net weather →
Needs You → collisions → The Herd → Resting → location → plan meters → footer.
Type scale: header 13 semibold · row title 13 · activity 11 secondary ·
counters 11 monospaced-digit · section headers 11 semibold secondary.
Empty state: a horseshoe and "The corral is empty." — charming, fully still.
