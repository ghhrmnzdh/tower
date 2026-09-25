# Tower — Design Authority for the Synthetic Film

**Status:** extracted spec. Everything below is transcribed or derived from
source, not invented. Where I derived a number (degrees from dash lengths,
spring settle times, film-scale type ramp) it is marked **[derived]** and the
derivation is shown.

**Authority precedence** — if two sources disagree, the higher one wins:

1. `src/Glyph.swift` — the *pixels*. Every mark geometry and every motion
   formula. This is the only source of truth for the marks.
2. `src/DesignSystem.swift` — the *tokens*. Motion springs, sizes, type scale,
   status semantics, tier accents.
3. `docs/DESIGN.md` — the *laws*. Three rules, attention hierarchy, restraint
   rules, Reduce Motion.
4. `Tower Identity Study.html` — the *register*. Neutral palette, card
   language, kicker/lede typographic feel. (Its SVG is a 1:1 mirror of
   `drawRadar`; verified line-by-line — no discrepancies.)
5. `promo/analysis/brand.json` — a correct digest of 1–4 plus the
   `do_not_claim` list. Use it for the honesty rules; use 1–4 for geometry.

---

## 0. One correction to the brief before anything else

> "…every arc, tick, sweep, ring, the pin/tower form."

**There is no pin/tower form.** `drawRadar` contains no tower silhouette, no
map pin, no mast, no antenna, no building. The "control tower" is the *concept*;
the *mark* is a radar scope seen from above:

```
outer ring  +  a filled core  +  three contacts (blips)  +  per-state motion
```

Do not draw a tower shape anywhere in the film as if it were the logo. If the
film needs a "tower", the radar mark **is** it. Inventing a mast would be
exactly the "invent a language the app does not use" failure the brief forbids.

Full inventory of the radar's drawable parts, and nothing else exists:

| part | present in states | source line |
|---|---|---|
| outer ring r=33 | **all five** | Glyph.swift:77 |
| verify sweep (needle + wedge trail) | verify | :81–95 |
| clear pulse ring | clear | :98–104 |
| holdNet sonar pings ×2 | holdNet | :107–115 |
| 3 blips | clear, verify, off (0 in holds) | :118–128 |
| holdGeo fence + ray + off-blip + halo | holdGeo | :131–153 |
| awake vigil (3 blooms + halo) | orthogonal overlay, any state | :159–172 |
| core (filled, or hollow-red when off) | all five | :174–180 |

---

## 1. Coordinate system and the rasterisation contract

From `Glyph.swift:57` (`g0.scaleBy(x: sc, y: sc)` where `sc = size/100`) and
`brand.json.radar_glyph.coordinate_system`:

- **Unit box:** `[0,0] … [100,100]`. Hub (centre) = `(50, 50)`.
- **Y axis points DOWN** (CoreGraphics/SwiftUI flipped context = SVG = Pillow).
  No axis flip is needed anywhere. Pillow matches natively.
- **Angles in degrees, 0° = +x (3 o'clock), increasing CLOCKWISE on screen**
  (a consequence of y-down). `ImageDraw.arc(bbox, start, end)` uses the exact
  same convention — start/end in degrees, 0° at 3 o'clock, sweeping clockwise.
  No conversion.
- **Scaling:** multiply every number below by `size/100`. Nothing is
  size-conditional; the mark is scale-invariant by construction (this is why
  the same code drives an 18pt menu-bar icon and a 120px study card).
- **Rotation** (`rotated(deg,…)`, Glyph.swift:62): translate `+ (50,50)`,
  rotate `deg` clockwise, translate `- (50,50)`. i.e. rotate about the hub.

### 1.1 Extents — nothing clips

Computed worst cases **[derived]**, so you know the safe crop:

| element | max distance from hub | box extent |
|---|---|---|
| ring r=33, stroke 6 | 36.0 | 14 … 86 |
| clear pulse max r=34, stroke 3 | 35.5 | 14.5 … 85.5 |
| holdGeo halo, centre (72,32) d=28.43, r→14, stroke 2.5 | — | x 56.75…87.25, y 16.75…47.25 |
| haiku tick tip 34+3.4, stroke 8 round cap | 41.4 | 8.6 … 91.4 |
| opus outer arc r=38, stroke 6.5 | 41.25 | 8.75 … 91.25 |
| fable spiral max r=35, stroke 8 | 39.0 | 11 … 89 |
| beacon bloom r=30 | 30 | 20 … 80 |

**Everything lives inside `0…100`.** Render the glyph into an RGBA tile of
exactly `S × S` px representing the 0…100 box; no bleed is required, but
allocate the tile with a 4-unit margin (`0.04·S`) if you plan to add any drop
shadow — the glyph itself never needs it.

### 1.2 Pillow rasterisation rules (non-negotiable for quality)

Pillow has **no antialiasing** on `ellipse`/`arc`/`line`. The old film's
mushiness partly came from this. Rules:

1. **Supersample ×4 minimum, ×6 preferred.** Draw the glyph at `S*6`, then
   `.resize((S,S), Image.LANCZOS)`. At the film's sizes (a hero radar is
   ~360–520 px) ×4 is enough and 2.25× cheaper; use ×4 for hero, ×6 for any
   mark under 80 px.
2. **One RGBA layer per translucent element,** composited in draw order with
   `Image.alpha_composite`. Do **not** accumulate alpha by drawing translucent
   shapes onto the same layer — overlapping strokes (the two holdNet pings,
   the three awake blooms) would double-darken and diverge from SwiftUI, which
   composites source-over per shape.
3. **Stroked circles:** `ImageDraw.ellipse` strokes *inward* from the bbox in
   Pillow 10.1. To get a stroke *centred* on radius `r` with width `w`, pass
   the bbox for radius `r + w/2` and `width=w`. Verify once, then bake it into
   a helper `ring(d, cx, cy, r, w, rgba)`.
4. **No dashes in Pillow.** Synthesise: see §2.2.
5. **Round line caps** don't exist either — draw the segment with
   `line(..., width=w)` and stamp an `ellipse` of radius `w/2` at each endpoint.
6. **Determinism:** all geometry is a pure function of `(state, P)`; `P =
   frame_index / 30.0`. No `time.time()`, no `random` without a fixed seed.
   Frame 471 must be byte-identical across runs.

---

## 2. THE RADAR MARK

`func drawRadar(ctx, size, state, phase P, color, awake, reduce)`
— Glyph.swift:53. `P` is **seconds** (in the app, `timeIntervalSinceReference
Date`; in the film, `frame/30`). `A = reduce ? 0 : 1` is the motion gate.
`color` is the **neutral** (`#E7E6E2` on the film's ink background).

### 2.1 Draw order (matters — later paints over earlier)

```
1. outer ring            (state colour + state dash)
2. verify sweep          (only .verify)
3. clear pulse           (only .clear)
4. holdNet pings ×2      (only .holdNet)
5. blips ×3              (opacity is state-dependent)
6. holdGeo group         (only .holdGeo: fence, ray, off-blip, halo)
7. awake vigil           (blooms + halo, under the core)
8. core                  (filled, or hollow red when .off)
```

### 2.2 Outer ring — the single most identifying element

```
circle(hub, r=33), stroke width 6
```

| state | stroke colour | dash pattern (unit lengths) |
|---|---|---|
| clear | neutral `#E7E6E2` | solid |
| verify | neutral `#E7E6E2` | solid |
| holdNet | amber `#E6A93C` | `[5, 6]` |
| holdGeo | amber `#E6A93C` | **solid** |
| off | red `#E5484D` | `[5, 7]` |

**Dash → degrees [derived].** Circumference at r=33 is `2π·33 = 207.345`.
`deg = 360·len / (2π·r)`:

| pattern | on° | off° | period° | periods per turn |
|---|---|---|---|---|
| off `[5,7]` @ r=33 | 8.6812 | 12.1537 | 20.8348 | 17.279 |
| holdNet `[5,6]` @ r=33 | 8.6812 | 10.4174 | 19.0986 | 18.850 |
| fence `[4,5]` @ r=15 | 15.2789 | 19.0986 | 34.3775 | 10.472 |

Implementation: start at **0° (3 o'clock)** with dash phase 0 and lay
alternating on/off arcs in increasing degrees until you pass 360°, clipping the
last dash. **Butt caps** (SwiftUI `StrokeStyle` default) — do *not* round the
ring's dash ends. The period does not divide 360 evenly, so a slightly short
final dash appears at the 0° seam. That is faithful; keep it. (The one dash
that *does* use round caps is the holdGeo ray — §2.7.)

`ImageDraw.arc(bbox_for_r33_plus_w2, start_deg, end_deg, fill=rgba, width=6)`.

### 2.3 The core

```
if state == .off:   stroke circle(hub, r=5.5), width 4, colour #E5484D   (HOLLOW)
else:               fill   circle(hub, r = 4.5)         (5.6 when awake != none)
                    colour = #E6A93C if state == .holdNet else neutral
```

The hollow red ring-core is the *only* structural difference in the off state
besides the ring colour/dash. It reads as "the centre is empty — nothing is
holding this." Do not fill it.

### 2.4 Blips (the contacts)

Fixed positions in the box: `(64,41)`, `(38,58)`, `(58,66)`; each `r = 3.6`,
**filled with the neutral** (never amber, never red — even in holdGeo/off).

Polar, for reference **[derived]**: `d=16.64 @ -32.74°`, `d=14.42 @ 146.31°`,
`d=17.89 @ 63.43°`. Deliberately irregular — they must not read as a symmetric
pattern.

Opacity per state (`i` = blip index 0,1,2):

| state | opacity |
|---|---|
| clear | `0.8 + 0.2·sin(P·1.6 + i·1.3)·A` |
| verify | `0.3 + 0.12·sin(P·2.2 + i)·A` |
| off | `0.22` (constant) |
| holdNet, holdGeo | `0` — **not drawn** |

`if op > 0.001` gate. Reduce Motion (`A=0`) → clear 0.8, verify 0.3.

Read this: **in a hold, the scope has no contacts.** Nothing is getting
through. That is the honest visual, and it is free.

### 2.5 `clear` — the calm outward pulse

```
pr = (P · 0.42) mod 1                # period = 1/0.42 = 2.381 s
r  = 8 + pr·26                       # 8 → 34
op = (1 - pr) · 0.5                  # 0.5 → 0
stroke circle(hub, r), width 3, neutral @ op
```
Reduce Motion still: `r = 22, op = 0.30`.

One ring, one expansion, fading out. It never loops "at full attention" — peak
alpha is 0.5 on a #E7E6E2 stroke over #0C0C0E. This is the *quiet* state.

### 2.6 `verify` — the rotating sweep

Whole group rotates about the hub by `(P · 150) mod 360` degrees → **2.400 s
per revolution**, clockwise on screen.

- **Needle:** line `(50,50) → (50,17)`, width 4, **round cap**, neutral, full
  opacity. (Length 33 — it reaches the ring.)
- **Trail wedge:** polygon `hub → 13 points on r=33 from 270° to 208.5°
  (inclusive, i/12 steps) → close`, filled **neutral @ 0.16**.
  - 270° = straight up = `(50,17)` (the needle).
  - 208.5° = `(20.999, 34.254)` **[derived]** — matches the study's SVG
    `A 33 33 0 0 0 21 34` exactly.
  - Span = **61.5°**, lying *counter-clockwise* of the needle → the trail
    **lags behind** the clockwise sweep. Get this backwards and it reads as a
    comet flying tail-first.
- Reduce Motion: rotation frozen at 0 (needle straight up).

The trail is a *straight-edged* wedge in the app (13 chords of a 61.5° arc, not
a smooth arc — chord error at r=33 over 5.125° steps is ~0.017 units, i.e.
invisible). Just sample 13 points and fill the polygon.

### 2.7 `holdNet` — amber sonar, no contacts

Two concentric pings, phase-offset 0.5, plus the amber ring and amber core.

```
for i in (0, 1):
    pr = ((P · 0.7) + i·0.5) mod 1        # period = 1/0.7 = 1.4286 s
    r  = 7 + pr·15                        # 7 → 22
    op = max(0, 1 - pr) · 0.7             # 0.7 → 0
    stroke circle(hub, r), width 3.5, #E6A93C @ op
```
Reduce Motion still: `r = 11 + i·7` → 11, 18; `op = 0.55 - i·0.25` → 0.55, 0.30.

Semantics for the film's copy: **held pending, self-clears.** Never "error",
never "failed", never red.

### 2.8 `holdGeo` — the fence and the off-country contact

Amber solid ring (§2.2), **neutral** core, no blips, plus:

1. **Fence:** `circle(hub, r=15)`, width 3, dash `[4,5]` (→ 15.279°/19.099°,
   10.47 periods **[derived]**), amber, rotating about the hub by
   `(P·45) mod 360` → **8.000 s per revolution**, clockwise. Butt caps.
2. **Ray:** line `(50,50) → (72,32)`, width 2.5, **round cap**, dash `[2,4]`,
   amber. Length = `hypot(22,18) = 28.425` **[derived]**. Static (does not
   rotate). Round caps on a dashed line mean each 2-unit dash renders as a
   4.5-unit capsule with a 1.75-unit visible gap — draw dash segments then
   stamp `r=1.25` dots at both ends of each.
3. **Off-country blip:** base centre `(72,32)` (d=28.425, −39.29° from hub),
   `r=5`, **filled amber**.
   ```
   dx, dy = -0.773, 0.634            # literal constants in Glyph.swift:139
   lunge  = 6 · (0.5 + 0.5·sin(P·2.2))      # 0 → 6,  period 2.856 s
   s      = 1 + 0.16·sin(P·3.0)             # scale about (72,32), period 2.094 s
   centre = (72 + dx·lunge, 32 + dy·lunge)
   ```
   **`(dx,dy)` is the unit vector from the blip toward the hub** — exact value
   `(-0.77396, +0.63324)` **[derived]**; the source rounds it. So the contact
   **lunges inward at the fence** and is pushed back, forever. Its distance
   from the hub goes 28.43 → 22.43; the fence sits at 15, so **it never gets
   in.** That single detail is the whole story of the fence — protect it.
   The scale `s` is applied about the *base* point `(72,32)`, not the lunged
   centre (`translate(mx,my) · scale(s) · translate(-72,-32)`, Glyph.swift:
   143–147), so the disc grows slightly asymmetrically as it lunges. Reproduce
   it: final centre = `(mx,my) + (1-s)·((72,32) - (72,32))` — which collapses
   to just `centre = (mx, my)` with radius `5·s`. (The translate pair cancels
   for a circle centred on the base point.) So in practice:
   **filled circle at `(mx,my)` with radius `5·s`.**
4. **Halo:** `circle(centre_of_lunged_blip, r = 5 + hp·9)`, width 2.5, amber @
   `(1 - hp)·0.8`, where `hp = (P·1.1) mod 1` → **period 0.909 s**. Note the
   halo tracks the *lunged* centre (Glyph.swift:151, HTML line 111 sets
   cx/cy to `72+dx·lunge`).

Reduce Motion still: fence rotation 0, `lunge = 0`, `s = 1`, halo `r = 10`,
halo `op = 0.5`.

### 2.9 `off` — unguarded. The only red in the system.

Red dashed ring `[5,7]`, hollow red core `r=5.5 / w=4`, blips at a flat 0.22,
and **no motion at all** (`P` does not appear in any off-state expression).
It is a completely still, hollow, dashed mark. Reduce Motion still = identical.

The stillness is the point: nothing is watching. In the film, the off state
must never gain a pulse, a shimmer, or a shake — it is the one state whose
loudness comes from being *dead*.

### 2.10 The awake vigil (keep-awake) — an overlay on any state

Drawn *under* the core. **Neutral only — never amber, never red** (a hold must
always outrank the lamp). Modes: `none | idle | clamshell`.

```
breathing = (mode == clamshell)
amp = 1.0 if breathing else 0.6
br  = (0.5 + 0.5·sin(P·2π/2.4)) if (breathing and not reduce) else 0.7   # 2.4 s
for (r, base) in [(15, 0.09), (11, 0.15), (7.5, 0.22)]:
    fill circle(hub, r), neutral @ base·(0.75 + 0.35·br·amp)
halo: stroke circle(hub, r = 9.5 + 1.7·br·amp), width 2.2,
      neutral @ 0.44 + 0.30·br·amp
core radius becomes 5.6 (from 4.5)
```
Only `clamshell` breathes; `idle` is a still lit lamp (`br = 0.7` constant).

**For the film: keep `awake = none` unless a beat is specifically about
keep-awake.** It adds a second glowing thing to the mark, and "one loudest
thing" forbids competing with a hold.

### 2.11 The standalone beacon (`drawBeacon`, Glyph.swift:284)

Same lamp, no ring, same 0…100 box. Only if a keep-awake beat exists.

```
ON:   blooms [(30,0.10),(21,0.17),(13,0.26)] @ op·(0.75+0.35·br·amp)
      ring  r = 17 + 2·br·amp, width 4.5, @ 0.30 + 0.25·br·amp
      core  fill r = 11
OFF:  ring  r = 15, width 4.5, @ 0.34
      core  fill r = 6, @ 0.30
```

### 2.12 The five states as one comparison table

| | clear | verify | holdNet | holdGeo | off |
|---|---|---|---|---|---|
| ring colour | neutral | neutral | **amber** | **amber** | **red** |
| ring dash | solid | solid | `5,6` | solid | `5,7` |
| core | filled neutral 4.5 | filled neutral 4.5 | filled **amber** 4.5 | filled neutral 4.5 | **hollow red** 5.5/w4 |
| blips | 0.8±0.2, alive | 0.3±0.12, faint | **none** | **none** | 0.22, dead |
| motion | 1 pulse ring, 2.38 s | sweep, 2.40 s/rev | 2 pings, 1.43 s | fence 8 s/rev + lunge 2.86 s + halo 0.91 s | **none** |
| busiest | quiet | steady | urgent-but-calm | busiest | dead still |
| means | guarding · path open | confirming location | no usable path — held | off-country — held | **UNGUARDED. danger** |
| caption (verbatim) | "Guarding · in-country and a path to Anthropic is open" | "Confirming your location; held until sure" | "No usable path (offline / captive / API) — held pending" | "Wrong country / VPN — held, not failed" | "Routing off — Claude connects directly, unguarded" |
| study label | Cleared | Verifying | Hold · connection | Hold · location | Unguarded |

**A state transition in the film must change the ring first** — colour and dash
are the fastest-read channel at any size. The core is the second read, the
motion the third.

---

## 3. THE PER-MODEL MARKS

`func drawModelMark(ctx, size, tier, color, phase P, energy E)` — Glyph.swift:188.
Same 0…100 box, same hub. `E = max(0, energy)`: **0 = still at rest, 1 = the
agent is working.** All strokes: `lineCap = .round`, `lineJoin = .round`.

**MONOCHROME. ALWAYS.** `do_not_claim`: "Do NOT tint the model marks with their
tier accent." The tier accent (§6) is allowed **only** in the small text label
next to the mark. Draw every model mark in the neutral `#E7E6E2` (or a
secondary neutral if it must recede).

`rotoscale(deg, k)` = translate `+(50,50)` · rotate `deg` clockwise · scale `k`
about the hub · translate `−(50,50)`.

### 3.1 Haiku — three ticks + a core

```
rotAll = E · 6 · sin(P · 0.7)                    # whole mark sways, period 8.976 s
for k in 0,1,2:
    a  = radians(-90 + k·120)                    # -90° (up), 30°, 150°
    dx, dy = cos(a), sin(a)
    osc = 0.5 + 0.5·sin(P·2.3 + k·2.094)         # per-tick beat, period 2.732 s,
                                                 # 120° apart in phase (2.094 = 2π/3)
    off = E · 3.4 · osc                          # 0 → 3.4
    line (50 + dx·(16+off), 50 + dy·(16+off)) → (50 + dx·(34+off), 50 + dy·(34+off))
    width 8, round caps, drawn inside rotoscale(rotAll, 1)
core: fill circle(hub, 7 · (1 + E·0.22·sin(P·3.0)))     # period 2.094 s
```
At rest (E=0): three radial ticks from r=16 to r=34 at −90°/30°/150°, width 8,
plus a filled r=7 core. Perfectly still.

### 3.2 Sonnet — one S stroke

```
rot = E·(P·16) + E·4·sin(P·1.3)     # continuous turn: 16 deg/s → 22.5 s/rev
                                    # + a ±4° wobble, period 4.833 s
s   = 1 + E·0.05·sin(P·1.3)
path: upper arc, centre (50, 37.5), r = 12.5, a from -90° to +90°  (25 samples)
      lower arc, centre (50, 62.5), r = 12.5, a from -90° to -270° (25 samples)
      (continuous — the two arcs meet at (50,50))
stroke width 8, round caps, inside rotoscale(rot, s)
```
Key points: starts `(50,25)`, bulges **right** to `(62.5,37.5)`, crosses
`(50,50)`, bulges **left** to `(37.5,62.5)`, ends `(50,75)`. Sample as
polylines (25 pts per arc) exactly as the source does — do not use a Bézier.

### 3.3 Opus — three orbiting rings + a pulsing core

```
radii = [16, 27, 38]; gaps = [90°, 210°, 330°]; rates = [14, -10, 8]   # deg/s
for i in 0,1,2:
    rr = E·(P·rates[i])                       # ring i rotation, degrees
    s  = 1 + E·0.06·sin(P·1.7 - i·0.8)        # breathe, period 3.696 s
    arc: 49 samples, a from gaps[i]+30 to gaps[i]+330   (a 300° arc)
    stroke width 6.5, round caps, inside rotoscale(rr, s)
core: fill circle(hub, 5 · (1 + E·0.18·sin(P·2.1)))     # period 2.992 s
```
Each ring has a **60° gap centred on `gaps[i]`** — i.e. gaps point down (90°),
lower-left (210°), upper-right (330°). Periods per revolution **[derived]**:
25.71 s, 36.00 s (counter-rotating), 45.00 s. Three different rates and one
reversal — that is what makes it read as an orbit rather than a spinner.

### 3.4 Fable — a spiral with a highlight winding up it

```
def spiral(f):                       # f in 0..1
    ang = f·2.35·2π − π/2            # 2.35 turns, starting straight up
    rr  = 2.5 + (35 − 2.5)·f         # 2.5 → 35
    return (50 + rr·cos(ang), 50 + rr·sin(ang))

base: polyline over 121 samples (i/120), stroke width 8, round caps/joins, neutral
core: fill circle(hub, 4)
if E > 0.01:
    head = (P · 0.22) mod 1          # period 4.545 s
    tail = max(0, head − 0.16)
    seg  = polyline spiral(f) for f = tail, tail+0.01, … ≤ head
    stroke seg width 8.6, neutral @ min(1,E)·0.95
    fill circle(spiral(head), 5) @ min(1,E)
```
The highlight is a slightly *fatter* stroke (8.6 vs 8) at 0.95 alpha over the
base — so it reads as a travelling brightening, not a separate line. The head
dot (r=5) is the leading light.

### 3.5 Model mark summary

| tier | at rest | while working (E→1) | display name | accent (TEXT ONLY) |
|---|---|---|---|---|
| haiku | 3 ticks r16→34 @ −90/30/150 + core r7 | ticks breathe out 3.4, mark sways ±6°, core ±22% | Haiku | `#E8842C` crayon |
| sonnet | one S, arcs r12.5 at y=37.5 / y=62.5 | turns 16°/s + ±4° wobble, ±5% scale | Sonnet | `#3B6FB5` steel |
| opus | 3 arcs (300°) r16/27/38, gaps 90/210/330 | rings orbit at 14 / −10 / 8 °/s, core ±18% | Opus | `#B0343C` rosso |
| fable / other | 2.35-turn spiral r2.5→35 + core r4 | a highlight winds up it, 4.55 s per pass | Fable | `#C9A227` gold |

`ModelTier` order (highest first): fable(4) > opus(3) > sonnet(2) > haiku(1) >
other(0). `other` falls through to the fable spiral geometry with a grey accent.

---

## 4. MOTION LAWS

### 4.1 The tokens (`TowerDesign.Motion`)

| token | definition | use | **[derived]** settle-to-0.5% | frames @30fps | peak overshoot |
|---|---|---|---|---|---|
| `settle` | spring(response 0.45, damping 0.85) | any state swap (colours, symbols, toggles) | 0.485 s | **15** | +0.63 % |
| `arrive` | spring(0.55, 0.72) | entrances, slight overshoot | 0.620 s | **19** | +3.84 % |
| `payoff` | spring(0.35, 0.60) | the done pop | 0.507 s | **16** | +9.48 % |
| `reorder` | spring(0.50, 0.80) | queue re-ranking | 0.575 s | **18** | +1.52 % |
| `sober` | **easeOut 0.25 s** | **failure — no bounce, ever** | 0.250 s | **8** | **0 %** |
| `shimmerPeriod` | 1.8 s | in-flight activity line sweep | — | **54** | — |
| `stagger` | 0.04 s per row | multi-row inserts | — | **1.2 → use 1** | — |
| `glowHold` | 0.9 s | done-glow before settling | — | **27** | — |
| done payoff total | ~0.6 s composite | check draws on + row glows + counter ticks | — | **18** | — |
| Reduce Motion swap | easeInOut 0.2 s | replaces every spring | — | **6** | — |

### 4.2 The easing functions, as Python

SwiftUI's `spring(response:dampingFraction:)` is a unit-mass second-order
system with `ω₀ = 2π/response` and `ζ = dampingFraction`. Exact closed form:

```python
import math

def spring(response, zeta):
    """SwiftUI .spring(response:dampingFraction:) -> f(t_seconds) in 0..~1.09"""
    w0 = 2.0 * math.pi / response
    if zeta < 1.0:                                    # underdamped
        wd = w0 * math.sqrt(1.0 - zeta * zeta)
        return lambda t: 0.0 if t <= 0 else 1.0 - math.exp(-zeta * w0 * t) * (
            math.cos(wd * t) + (zeta * w0 / wd) * math.sin(wd * t))
    return lambda t: 0.0 if t <= 0 else 1.0 - math.exp(-w0 * t) * (1.0 + w0 * t)

SETTLE  = spring(0.45, 0.85)   # 15 f — any state swap
ARRIVE  = spring(0.55, 0.72)   # 19 f — entrances
PAYOFF  = spring(0.35, 0.60)   # 16 f — the done pop
REORDER = spring(0.50, 0.80)   # 18 f — re-ranking
```

Cubic-Bézier easings (CoreAnimation / SwiftUI curve control points), solved by
Newton — this is what `.easeOut` / `.easeInOut` actually are:

```python
def cubic_bezier(x1, y1, x2, y2, eps=1e-6):
    """CSS/CoreAnimation cubic-bezier(x1,y1,x2,y2) -> f(progress 0..1)."""
    def bx(u): return 3*(1-u)**2*u*x1 + 3*(1-u)*u*u*x2 + u**3
    def by(u): return 3*(1-u)**2*u*y1 + 3*(1-u)*u*u*y2 + u**3
    def dbx(u): return 3*(1-u)**2*x1 + 6*(1-u)*u*(x2-x1) + 3*u*u*(1-x2)
    def f(x):
        x = 0.0 if x < 0 else (1.0 if x > 1 else x)
        u = x
        for _ in range(8):
            e = bx(u) - x
            if abs(e) < eps: break
            d = dbx(u)
            if abs(d) < 1e-9: break
            u -= e / d
        return by(u)
    return f

EASE_OUT    = cubic_bezier(0.00, 0.00, 0.58, 1.00)   # SOBER — failure
EASE_IN     = cubic_bezier(0.42, 0.00, 1.00, 1.00)
EASE_IN_OUT = cubic_bezier(0.42, 0.00, 0.58, 1.00)   # Reduce-Motion swap, 0.2 s
```

Two extra curves the film needs that the app does not name. Use these — and
*only* these — for camera/composition moves (title cards, panel entrances,
cross-scene wipes), so film motion sits in the same family as UI motion:

```python
# Apple-ad standard: slow-in/slow-out with a long tail. For any push/scale/slide.
FILM_EASE  = cubic_bezier(0.22, 0.61, 0.36, 1.00)     # "easeOutCubic"-ish, no overshoot
# For the one hero reveal per act. Mild overshoot, no bounce.
FILM_ENTER = cubic_bezier(0.16, 0.84, 0.44, 1.00)

# Generic helpers
def clamp01(x): return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)
def seg(f, a, b): return clamp01((f - a) / (b - a))          # frame window -> 0..1
def lerp(a, b, k): return a + (b - a) * k
def smoothstep(x): x = clamp01(x); return x * x * (3.0 - 2.0 * x)
```

**Never** use a bounce, elastic, back-out, overshoot >10 %, shake, wobble, or
`easeInBack` anywhere in this film. Nothing in Tower's system does that, and the
largest legal overshoot in the whole product is `payoff`'s **+9.5 %**.

### 4.3 "Failure never bounces" — the hard rule

From `DesignSystem.swift:23` and `DESIGN.md:85` and `brand.json.must_never[0]`:

> Failure must NEVER bounce — failed uses easeOut 0.25 s, a sober fade. No
> spring, no overshoot, no shake.

Concretely, for the film:

- Anything representing **failure or danger** (the `off` radar, a failed agent,
  a destructive confirm) animates with `EASE_OUT` over **8 frames** and then
  stops. No scale-up-and-settle. No entrance overshoot. No pulse.
- Anything representing **success/done** may use `PAYOFF` (16 f) plus a 27-frame
  glow hold, then quiet.
- Everything else that is a *state swap* uses `SETTLE` (15 f).
- Entrances use `ARRIVE` (19 f) — but only for things that are neutral or good.
- **A hold (amber) is neither.** It is pending, not failed. Animate a hold in
  with `SETTLE` (15 f) — calm, no celebration, no funeral.

### 4.4 The three laws, as film constraints

**1. The mark is the state.** `DESIGN.md:10`. The radar *is* the guard.
   - Never draw a separate badge/pill/light that duplicates what the radar is
     already saying. If a caption says "held", the radar in frame must be in a
     hold state at that instant, and vice versa.
   - Never use the radar decoratively. It must never be a logo bug in the
     corner in a state that contradicts the scene.
   - Never invent a sixth radar state.

**2. Motion = state change.** `DESIGN.md:12`.
   - Motion in this film has to *mean* a transition. A thing that has nothing
     to say holds a still frame.
   - Celebration is earned (done), never granted (failure is sober).
   - "Nothing loops at full attention when all is well." The `clear` pulse at
     alpha ≤0.5 is the maximum idle loop the system permits. Do not add ambient
     particles, drifting grain, breathing gradients, or a slow zoom on a
     "quiet" beat — that is exactly the "messy, can't focus" failure.
   - Corollary: **cross-dissolving two dense layers is banned.** The old film's
     ghosting is a direct violation — a dissolve is motion that means nothing.
     Cut, or move one element with `FILM_EASE`, or wipe with a hard edge.

**3. One loudest thing at a time.** `DESIGN.md:15`, `must_never[1]`.
   - At most **one** element in frame is animating at full attention at any
     frame. Everything else is still or ≤0.3 alpha.
   - Attention hierarchy, verbatim: `menubar badge > Needs-You order >
     collision banner > the radar's own motion`. In film terms: if a
     needs-you event is on screen, the radar must be quiet, and vice versa.
   - Enforce it mechanically: build a per-frame "attention budget" of 1.0 and
     assert in the renderer that the sum of active-animation weights ≤ 1.0.

**4. Reduce Motion is always honored.** `DESIGN.md:122`, `brand.json.
   reduce_motion`. Every radar state has a *legible still frame* — never a
   blank (§2.5–2.9 list them). For the film this means two things:
   - Build a `REDUCE=1` render path that produces a valid, legible 1200-frame
     output where every glyph uses its still values and all transitions become
     6-frame `EASE_IN_OUT` fades. Even if it never ships, having it forces
     every composition to be legible in a single frozen frame — which is
     exactly the discipline the old film lacked.
   - **Test:** pause on any frame. If you cannot tell what the guard state is
     from that one frame, the composition is wrong.

### 4.5 Frame budget arithmetic for 1200 frames

At 30 fps, 40.000 s = **1200 frames** exactly. Useful quanta:

| beat | frames | seconds |
|---|---|---|
| a state swap (`settle`) | 15 | 0.500 |
| an entrance (`arrive`) | 19 | 0.633 |
| a sober failure fade | 8 | 0.267 |
| the done payoff + glow | 18 + 27 = 45 | 1.500 |
| one shimmer sweep | 54 | 1.800 |
| one radar `clear` pulse | 71.4 | 2.381 |
| one radar `verify` revolution | 72 | 2.400 |
| one holdNet ping cycle | 42.9 | 1.429 |
| one holdGeo fence revolution | 240 | 8.000 |
| one fable highlight pass | 136.4 | 4.545 |
| a legible line of copy on screen | ≥ 60 | ≥ 2.0 |

**Loop-friendly beat lengths:** 72 f (one verify turn), 144 f, 240 f (one fence
turn). If a shot must loop seamlessly, size it to a whole number of the active
mark's period; otherwise start the shot at `P = 0` for that mark by offsetting
its phase (`P_local = (frame - shot_start) / 30`), which is legal because every
formula is a pure function of `P`.

---

## 5. TYPE

### 5.1 The three faces and their roles

| role | face | path | how to instantiate |
|---|---|---|---|
| display / headline | **New York** (serif) | `/System/Library/Fonts/NewYork.ttf` | variable: axes `[Optical Size 12…256 (def 256), Weight 400…1000 (def 400), GRAD 0…1]` |
| UI / body / lede | **SF (SFNS)** | `/System/Library/Fonts/SFNS.ttf` | variable: axes `[Width 30…150 (def 100), Optical Size 17…96 (def 28), GRAD 400…1000 (def 400), Weight 1…1000 (def 400)]` |
| mono / kicker / data / code | **JetBrains Mono** | `src/Fonts/JetBrainsMono-Medium.ttf`, `-Bold.ttf` | static; OFL, redistributable |

Verified on this machine (Pillow 10.1.0, numpy 1.26.4, ffmpeg 7.0.1). The axis
lists above are the real `get_variation_axes()` output — **note the order**:
New York is `[opsz, wght, GRAD]`, SF is `[wdth, opsz, GRAD, wght]`. Getting the
order wrong silently produces a wrong weight.

The technique, matching `promo/overlays.py:91`:

```python
from PIL import ImageFont
_CACHE = {}

SERIF = "/System/Library/Fonts/NewYork.ttf"
UI    = "/System/Library/Fonts/SFNS.ttf"
MONO  = "/Users/omega/room/mainprojects/tower/src/Fonts/JetBrainsMono-Medium.ttf"
MONO_B= "/Users/omega/room/mainprojects/tower/src/Fonts/JetBrainsMono-Bold.ttf"

def font(kind, size, weight=None):
    size = int(round(size)); key = (kind, size, weight)
    if key in _CACHE: return _CACHE[key]
    if kind == "serif":
        f = ImageFont.truetype(SERIF, size)
        try: f.set_variation_by_axes([max(12, min(256, size * 2)), weight or 520, 0])
        except Exception: pass
    elif kind == "ui":
        f = ImageFont.truetype(UI, size)
        try: f.set_variation_by_axes([100, max(17, min(96, size)), 400, weight or 400])
        except Exception: pass
    elif kind == "mono":      f = ImageFont.truetype(MONO, size)
    elif kind == "mono_bold": f = ImageFont.truetype(MONO_B, size)
    else: raise ValueError(kind)
    _CACHE[key] = f
    return f
```

**SF weight axis values** (Apple's named instances): Regular **400**, Medium
**510**, Semibold **590**, Bold **700**, Heavy **810**, Black **900**. The app's
`.semibold` = **590**. New York's weight axis floor is **400** — there is no
light New York; do not request below 400.

**Optical size matters.** For SF, `opsz` clamped to the point size is right
(the app's `Font.system` does this automatically). For New York at display
sizes, push `opsz` high (`size*2`, capped 256) — that is what gives the
headline its tighter, sharper display cut instead of a text-cut serif.

### 5.2 The product's own scale (use verbatim when drawing a Tower surface)

`DesignSystem.swift:44–52`, popover width 360 pt:

| element | pt | weight |
|---|---|---|
| header | 13 | semibold (590) |
| row title | 13 | regular (400) |
| activity line | 11 | regular, secondary colour |
| counters / times | 11 | regular, **monospacedDigit** |
| section header | 11 | semibold (590), secondary colour |
| caption | 9 | regular |
| model/effort tokens | — | **JetBrains Mono** Medium/Bold |

Sizes: `popoverWidth 360 · menubarPt 18 · rowGlyph 28 · radiusCard 10 ·
radiusBadge 6 · padH 14 · rowVPad 7`.

**Film upscale [derived].** Draw any Tower surface at an integer-ish factor and
scale *everything* including radii and paddings. Never render the popover
smaller than 2×:

| | 2× (720 px wide) | **2.5× (900 px wide) — preferred when the UI is the subject** |
|---|---|---|
| header 13 | 26 | 33 |
| row title 13 | 26 | 33 |
| activity 11 | 22 | 28 |
| counter 11 mono | 22 | 28 |
| section 11 | 22 | 28 |
| caption 9 | 18 | 23 |
| rowGlyph 28 | 56 | 70 |
| menubar radar 18 | 36 | 45 |
| padH 14 | 28 | 35 |
| rowVPad 7 | 14 | 18 |
| radiusCard 10 | 20 | 25 |
| radiusBadge 6 | 12 | 15 |

At 2.5× a 900 px popover leaves 510 px of margin each side on a 1920 frame —
that is the composition. **Never crop a Tower surface.** The old film's cropped,
bleeding text is the single loudest thing the user hated. If it does not fit,
show *less UI*, not a cropped view.

### 5.3 The film's own type ramp [derived]

Derived from the identity study's ratios (`h1 42 / lede 17 / h2 22 / kicker 11
/ name 18 / desc 11` on a 1100 px column) scaled to a 1920 frame, then rounded
to a clean ramp. Use these numbers.

| role | face / weight | px | tracking | line-height | colour |
|---|---|---|---|---|---|
| **kicker / eyebrow** | JetBrains Mono Medium, UPPERCASE | 20 | **+0.24 em = +4.8 px** | — | `#6E6E6A` |
| **hero headline** | New York, wght **560**, opsz 256 | **112** | **−0.01 em = −1.12 px** | 1.06 (119 px) | `#E7E6E2` |
| **act headline** | New York, wght 520, opsz 160 | 76 | −0.01 em | 1.10 | `#E7E6E2` |
| **section title** | New York, wght 500 | 46 | 0 | 1.20 | `#E7E6E2` |
| **lede / body** | SF, wght 400 | 34 | 0 | **1.6 (54 px)** | `#9A9A95` |
| **sub-caption** | SF, wght 400 | 26 | 0 | 1.5 | `#8B8B86` |
| **state label** (under a mark) | JetBrains Mono Medium, UPPERCASE | 22 | **+0.14 em = +3.1 px** | — | `#7C7C77` |
| **big number / meter** | JetBrains Mono **Bold** | 64 | 0 | — | `#E7E6E2` |
| **terminal / code** | JetBrains Mono Medium | 26 | 0 | 1.55 (40 px) | `#E7E6E2` on `#141416` |
| **install command** | JetBrains Mono Medium | 30 | 0 | — | `#E7E6E2` |

**Measure:** body copy max **62 ch** (the study's `max-width:62ch`) ≈ **1080 px**
at 34 px SF. Never exceed 1100 px of text width on a 1920 frame. One idea per
card; two lines maximum for a headline.

**Tracking in Pillow** (no native support) — draw per character:

```python
def draw_tracked(d, xy, text, f, fill, track=0.0):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + track
    return x - track    # advance of the run

def tracked_width(text, f, track=0.0):
    return sum(f.getlength(c) for c in text) + track * max(0, len(text) - 1)
```
Positive tracking on the kicker and the state labels is **load-bearing** — it is
what makes the mono read as a label rather than as code. Negative tracking on
New York at 112 px is what keeps the headline from looking loose.

**Vertical rhythm:** an 8 px baseline grid, 24 px module. Kicker sits **32 px**
above the headline cap-height; lede sits **40 px** below the headline baseline.

**Numbers:** JetBrains Mono is tabular by construction, so counters never
reflow (this is the film's stand-in for `.monospacedDigit()` +
`.contentTransition(.numericText())`). If a counter ticks up on screen, tick
it **digit-in-place** — no slide, no odometer roll; the app just swaps the
glyph.

---

## 6. COLOUR — the resolved token table

Every hex below is read from source. `[study]` = `Tower Identity Study.html`
`:root`/CSS; `[glyph]` = hard-coded in `src/Glyph.swift`; `[ds]` =
`src/DesignSystem.swift`; `[resolved]` = the literal sRGB value macOS resolves
the named `NSColor` to in Dark appearance (captured in `brand.json`).

### 6.1 Surface & text

| token | hex | RGB | role | source |
|---|---|---|---|---|
| `ink` | `#0C0C0E` | 12,12,14 | the film's background. Every frame. | [study] `--ink` |
| `surface` | `#141416` | 20,20,22 | card / panel / terminal fill | [study] `.card` |
| `hairline` | `rgba(255,255,255,.08)` ≈ `#242426` on ink | — | 1 px border on any surface | [study] `.card` border |
| `text` | `#E7E6E2` | 231,230,226 | primary text **and the glyphs' `currentColor`** | [study] `--paper` |
| `text_2` | `#9A9A95` | 154,154,149 | lede / body | [study] `p.lede` |
| `muted` | `#8B8B86` | 139,139,134 | sub-headline / caption | [study] `--mut` |
| `dim` | `#7C7C77` | 124,124,119 | uppercase state labels | [study] `.desc` |
| `kicker` | `#6E6E6A` | 110,110,106 | eyebrow — lowest legible tier | [study] `.kicker` |

Contrast on `#0C0C0E`: `text` 15.6:1, `text_2` 8.0:1, `muted` 6.5:1, `dim`
4.9:1, `kicker` 3.9:1. **`kicker` is legal only at ≥20 px and only for short
uppercase eyebrows** (its 3.9:1 is below AA for body text). Never set body copy
below `text_2`.

### 6.2 Signal — load-bearing, never decorative

| token | hex | RGB | means | source |
|---|---|---|---|---|
| `amber` | `#E6A93C` | 230,169,60 | **HELD / PENDING / WARN.** holdNet + holdGeo ring, holdNet core, the whole geo group. TUI `C_WARN`. | [glyph] `towerAmber` |
| `red` | `#E5484D` | 229,72,77 | **DANGER / UNGUARDED.** The `off` radar only, and destructive confirms. | [glyph] `towerRed` |
| `green` | `#30D158` | 48,209,88 | pass / done / ok | [resolved] `systemGreen` dark |

> **The rule, verbatim from `brand.json`:** *"amber and red are load-bearing
> (hold vs unguarded) — never use them decoratively."*

That means: no amber underline flourishes, no red for emphasis, no green
gradient washes, no coloured backgrounds, no accent-coloured typography except
where the app itself does it. The film's palette is **ink + paper + one signal
colour at a time.** If more than one of {amber, red, green} is in frame, you
have already broken "one loudest thing".

### 6.3 Status semantics (`AgentStatus`, only if the film shows the agent list)

| status | token | hex (dark) | symbol | motion | needs-you rank |
|---|---|---|---|---|---|
| failed | systemRed | `#FF4245` | `xmark.octagon.fill` | **sober fade, never bounces** | 1 |
| blocked (approval) | systemOrange | `#FF9230` | `hand.raised.fill` | one pulse on arrival | 2 |
| asking | systemIndigo | `#6D7CFF` | `questionmark.bubble.fill` | one pulse on arrival | 3 |
| done / waiting input | systemGreen | `#30D158` | checkmark **draws on** (trim 0→1) | payoff + 0.9 s glow | 4 |
| stall / loop | systemYellow | `#FFD600` | `exclamationmark.triangle.fill` | none | — |
| working | primary | `#E7E6E2` | **the model mark** | per-model motion | — |
| paused / idle / gone | tertiary | `#FFFFFF` @25 % | `zzz` / `pause.circle` | none | — |

Note these are macOS *system* colours and are **not** the brand amber/red.
`systemRed #FF4245` ≠ `towerRed #E5484D`; `systemOrange #FF9230` ≠ `towerAmber
#E6A93C`. Keep them straight: brand tones on the **radar**, system tones on
**agent rows**. If the film only ever shows the radar + a couple of rows,
prefer standardising the row tones to the brand set (`amber`/`red`/`green`) for
palette coherence — that is a defensible simplification because the *semantics*
are identical, and it keeps the film to three signal hues. Decide once; do not
mix.

SF Symbols are not available to Pillow. Draw the four needed symbols as
primitives, keeping the **shape** distinction (that's what makes done-vs-failed
readable without colour):

| symbol | draw as |
|---|---|
| `xmark.octagon.fill` | regular octagon (r=50, vertices at 22.5°+k·45°) filled, with an X (two strokes from ±(0.32r) corners, width 0.16r) knocked out in `ink` |
| `hand.raised.fill` | a rounded 4-finger palm — or substitute a filled rounded square with a horizontal bar; keep it **blocky** |
| `questionmark.bubble.fill` | filled rounded rect + tail, with a `?` in SF at 0.62× the bubble height knocked out |
| `checkmark` | a 2-segment polyline `(0.24,0.53) → (0.44,0.72) → (0.78,0.30)` in unit space, width 0.10, round caps, **animated by trimming 0→1** |

### 6.4 Model tier accents — TEXT LABELS ONLY

| tier | hex | name |
|---|---|---|
| fable | `#C9A227` | gold |
| opus | `#B0343C` | rosso |
| sonnet | `#3B6FB5` | steel |
| haiku | `#E8842C` | crayon |
| other | systemGray | — |

`DESIGN.md:71`: *"appears only in the row's small text label — never on the mark
itself."* If the film shows model names, the name may take its accent at the
small label size; the mark stays `#E7E6E2`.

### 6.5 TUI palette (only if a terminal is shown)

`src/tower-tui.py` uses 8-colour curses on the terminal's own background
(`use_default_colors`, bg = −1). Roles, not hexes: `C_TITLE` white/bold,
`C_GOOD` green, `C_WARN` yellow, `C_DIM` cyan (section headers), `C_ACCENT`
magenta (selection, often reversed), `C_BAD` red. Verbatim section headers:
`TOWER · NETWORK LOCATION · GUARD · KEEP AWAKE · NETWORK · AGENTS · PLAN LIMITS
· LIVE TRAFFIC · ACTIONS · PIN A COUNTRY · ESTIMATED API COST · BACKGROUND
PROCESSES · INTERNET DOWN · ANTHROPIC API ISSUE`. Render a synthetic terminal on
`#141416`, not pure black, and map green/yellow/red to the brand `green/amber/
red` so it stays inside the film's palette.

### 6.6 Surface construction

From the study's card: `background #141416`, `border 1px rgba(255,255,255,.08)`,
`border-radius 20px`, `padding 24/18/18`, internal `gap 14`, glyph box `120px`.
Scaled to the film (×1.75 for a 1920 frame), a "state card" is:

```
size        280 × 340 px          (or 320 × 380 for a hero card)
radius      35 px
fill        #141416
border      1.75 px @ #FFFFFF 8%  (draw as a rounded-rect outline)
glyph       210 px, centred, 42 px from the top
name        New York 32 px wght 500, #E7E6E2, 24 px below the glyph
desc        JetBrains Mono 19 px UPPERCASE, +0.14 em, #7C7C77, 12 px below name
```
Five such cards on a 1920 frame: `5 × 280 + 4 × 28 gap = 1512`, centred → 204 px
side margins. That is the "all five states at once" composition, straight from
the identity study.

---

## 7. THE PRINCIPLES, AS A FILM CHECKLIST

Print this next to the shot list. Every shot must pass all nine.

1. **The mark is the state.** Is there exactly one radar in frame, and is its
   state the literal truth of what the copy says at that instant? No decorative
   marks, no contradicting logo bug, no sixth state.
2. **Motion = state change.** Does every moving pixel in this shot correspond
   to a state changing? If something moves "for atmosphere", delete it.
3. **One loudest thing.** Count the elements animating at >0.3 alpha amplitude.
   Is it exactly one? Is everything else still?
4. **Failure never bounces.** Any red/failed/off beat: `EASE_OUT`, 8 frames,
   then dead still. No spring, no overshoot, no shake, no zoom.
5. **Legible in one frozen frame.** Pause anywhere. Can you name the guard
   state and read every word? (This is Reduce Motion discipline applied to
   composition. It is the direct fix for "too messy and people can not focus".)
6. **Nothing is cropped.** No Tower surface bleeds off frame. No text is cut.
   If it doesn't fit, show less, don't crop.
7. **No cross-dissolve of two dense layers.** Cut, or move one thing. The old
   film's ghosting is the specific failure being corrected.
8. **The quiet state is quiet.** If the beat is "all clear", the only loop
   allowed is the radar's own 2.381 s pulse at ≤0.5 alpha. No drifting
   backgrounds, no ambient particles, no slow push-in.
9. **Honest.** See §8.

Composition defaults that follow from the above:
- Background is `#0C0C0E`, flat, always. No gradient, no vignette, no grain.
  (A gradient is a second thing competing for attention and it bands at 8-bit.)
- One idea per card. Copy on the left third or centred; the mark on the right
  third or centred — never overlapping. **Subtitles never sit on top of live
  UI**: reserve a dedicated 180 px band at the bottom (`y 860…1040`) and keep
  every UI surface out of it.
- Safe margins: 120 px all round for anything important; 96 px hard minimum.
- Cuts land on beat boundaries that are whole frames (§4.5), never mid-spring.

---

## 8. THE HONESTY GUARDRAILS THAT TOUCH DESIGN

The full list is `brand.json.do_not_claim` (23 items) — read it before writing
a single line of copy. The ones that are *visual* decisions, and therefore mine
to enforce here:

| # | rule | the visual consequence |
|---|---|---|
| 1 | Off-country is **AMBER**, not red | `holdGeo` ring is `#E6A93C`, core stays **neutral**, blips are off. Red appears **only** in the `off` state. |
| 2 | A hold is **PENDING**, not failed | Never pair a hold with a ✕, a "failed", an error tone, or a sober fade. A hold arrives on `SETTLE` and *self-clears*. Show it clearing. |
| 3 | A block is **503 + Retry-After**, never 403 | If the film shows a status code, it is `503`. Claude Code's own retry spinner reads "Retrying · attempt x/y". Never "403", never "Error", never "Failed". |
| 4 | **Degraded ≠ blocked** | A slow-but-reachable link still gets through. Do not show a slow connection turning the radar amber. Only offline / captive / edge-unreachable holds. |
| 5 | Fail-**closed**, never fail-open | Never depict traffic "getting through anyway" while unconfirmed. Uncertain = held. |
| 6 | Marks stay **monochrome** | Model marks are `#E7E6E2`. Tier accent lives in the text label only. |
| 7 | The menu-bar radar is **full colour**, not a flat template | The amber/red *are* the information. Never render the film's menu-bar radar as a single flat tint. |
| 8 | Not a VPN, not a firewall, not a kill switch | No shield icons, no padlocks, no globe-with-a-tunnel, no "IP changed" imagery. Tower **confirms** where you are; it never moves you. |
| 9 | Read-only toward `~/.claude` | No imagery of Tower writing into, steering, or injecting into a session. |
| 10 | No usage numbers while gated | If the film shows the plan meters and the guard is holding in the same shot, that is a lie. Show the honest gated message instead, or don't show meters in that shot. |
| 11 | Menu bar never counts running agents | Any badge shown is the **needs-you** count (or usage %), never "3 agents running". |
| 12 | Never two things pulsing | Enforced by §7.3. |

**Copy is pre-cleared** in `brand.json.voice.lines` (each marked `verbatim:
true/false` with its source) and `brand.json.voice.state_captions_verbatim`.
Prefer a verbatim line over a new one. Register: *calm, factual, understated;
short declaratives; never hypes.* "Quiet tower, clear signal."

---

## 9. QUICK-REFERENCE CONSTANTS (paste into the renderer)

```python
# ---- colour ---------------------------------------------------------------
INK      = (0x0C, 0x0C, 0x0E)   # background — every frame
SURFACE  = (0x14, 0x14, 0x16)   # cards, panels, terminal
HAIRLINE = (0xFF, 0xFF, 0xFF, 20)   # 8% white
TEXT     = (0xE7, 0xE6, 0xE2)   # primary + glyph currentColor
TEXT2    = (0x9A, 0x9A, 0x95)   # lede
MUTED    = (0x8B, 0x8B, 0x86)   # caption
DIM      = (0x7C, 0x7C, 0x77)   # uppercase state label
KICKER   = (0x6E, 0x6E, 0x6A)   # eyebrow (>=20px, uppercase only)
AMBER    = (0xE6, 0xA9, 0x3C)   # HELD / PENDING  — load-bearing
RED      = (0xE5, 0x48, 0x4D)   # UNGUARDED       — load-bearing
GREEN    = (0x30, 0xD1, 0x58)   # pass / done
TIER     = {"fable": (0xC9,0xA2,0x27), "opus": (0xB0,0x34,0x3C),
            "sonnet": (0x3B,0x6F,0xB5), "haiku": (0xE8,0x84,0x2C)}

# ---- radar (0..100 box, hub (50,50), y down, 0deg = +x, CW) ---------------
HUB          = (50.0, 50.0)
RING_R,  RING_W  = 33.0, 6.0
RING_DASH    = {"clear": None, "verify": None,
                "holdNet": (5, 6), "holdGeo": None, "off": (5, 7)}
RING_COLOR   = {"clear": TEXT, "verify": TEXT,
                "holdNet": AMBER, "holdGeo": AMBER, "off": RED}
CORE_R, CORE_R_AWAKE, CORE_OFF_R, CORE_OFF_W = 4.5, 5.6, 5.5, 4.0
BLIPS        = [(64.0, 41.0), (38.0, 58.0), (58.0, 66.0)]
BLIP_R       = 3.6
# clear
PULSE_RATE, PULSE_R0, PULSE_DR, PULSE_W = 0.42, 8.0, 26.0, 3.0   # op=(1-pr)*0.5
PULSE_STILL  = (22.0, 0.30)
# verify
SWEEP_DPS, SWEEP_NEEDLE_W = 150.0, 4.0            # 2.400 s / rev, round cap
SWEEP_A0, SWEEP_A1, SWEEP_N, SWEEP_ALPHA = 270.0, 208.5, 12, 0.16
# holdNet
PING_RATE, PING_R0, PING_DR, PING_W = 0.7, 7.0, 15.0, 3.5        # op=max(0,1-pr)*0.7
PING_STILL   = [(11.0, 0.55), (18.0, 0.30)]
# holdGeo
FENCE_R, FENCE_W, FENCE_DASH, FENCE_DPS = 15.0, 3.0, (4, 5), 45.0   # 8.000 s / rev
RAY_A, RAY_B, RAY_W, RAY_DASH = (50.0, 50.0), (72.0, 32.0), 2.5, (2, 4)  # round cap
OFF_BLIP, OFF_BLIP_R = (72.0, 32.0), 5.0
LUNGE_DIR, LUNGE_MAX, LUNGE_W = (-0.773, 0.634), 6.0, 2.2   # 6*(0.5+0.5*sin(P*2.2))
OFF_SCALE_W  = 3.0                                          # 1 + 0.16*sin(P*3.0)
HALO_RATE, HALO_R0, HALO_DR, HALO_W = 1.1, 5.0, 9.0, 2.5    # op=(1-hp)*0.8
HALO_STILL   = (10.0, 0.50)
# awake vigil (neutral only)
VIGIL_BLOOM  = [(15.0, 0.09), (11.0, 0.15), (7.5, 0.22)]    # op*(0.75+0.35*br*amp)
VIGIL_HALO_W, VIGIL_PERIOD = 2.2, 2.4    # r=9.5+1.7*br*amp, op=0.44+0.30*br*amp
# beacon (standalone)
BEACON_BLOOM = [(30.0, 0.10), (21.0, 0.17), (13.0, 0.26)]
BEACON_ON    = dict(ring_r0=17.0, ring_dr=2.0, ring_w=4.5, core_r=11.0)
BEACON_OFF   = dict(ring_r=15.0, ring_w=4.5, ring_op=0.34, core_r=6.0, core_op=0.30)

# ---- model marks ----------------------------------------------------------
HAIKU  = dict(angles=(-90, 30, 150), r0=16.0, r1=34.0, w=8.0, core=7.0,
              breathe=3.4, beat=2.3, phase_step=2.094, sway=6.0, sway_rate=0.7,
              core_amp=0.22, core_rate=3.0)
SONNET = dict(r=12.5, cy_top=37.5, cy_bot=62.5, w=8.0, samples=25,
              spin_dps=16.0, wobble=4.0, wobble_rate=1.3, scale_amp=0.05)
OPUS   = dict(radii=(16.0, 27.0, 38.0), gaps=(90.0, 210.0, 330.0),
              rates=(14.0, -10.0, 8.0), arc=300.0, w=6.5, samples=49,
              core=5.0, core_amp=0.18, core_rate=2.1,
              ring_amp=0.06, ring_rate=1.7, ring_phase=0.8)
FABLE  = dict(turns=2.35, r0=2.5, r1=35.0, steps=120, w=8.0, core=4.0,
              head_rate=0.22, tail_len=0.16, hl_w=8.6, hl_alpha=0.95, head_r=5.0)

# ---- motion (frames @ 30 fps) --------------------------------------------
FPS, TOTAL_FRAMES = 30, 1200
F_SETTLE, F_ARRIVE, F_PAYOFF, F_REORDER, F_SOBER = 15, 19, 16, 18, 8
F_GLOW_HOLD, F_SHIMMER, F_STAGGER, F_REDUCE = 27, 54, 1, 6

# ---- type -----------------------------------------------------------------
SF_W = dict(regular=400, medium=510, semibold=590, bold=700, heavy=810)
TYPE = {   # (kind, px, weight, tracking_px)
  "kicker":   ("mono",  20, None, +4.8),   # UPPERCASE
  "hero":     ("serif", 112, 560, -1.12),
  "act":      ("serif",  76, 520, -0.76),
  "section":  ("serif",  46, 500,  0.0),
  "lede":     ("ui",     34, 400,  0.0),   # line-height 54
  "caption":  ("ui",     26, 400,  0.0),
  "state":    ("mono",   22, None, +3.1),  # UPPERCASE
  "number":   ("mono_bold", 64, None, 0.0),
  "code":     ("mono",   26, None, 0.0),   # line-height 40
  "install":  ("mono",   30, None, 0.0),
}
```

---

## 10. Verification note

I diffed `src/Glyph.swift` against the SVG + `updateRadar()` in
`Tower Identity Study.html` line by line: every radius, stroke width, dash
pattern, rate constant, opacity formula, and the still-frame fallbacks are
**identical**. `brand.json.radar_glyph` is likewise an accurate transcription.
The only values I computed rather than read are marked **[derived]**: the
dash-length→degree conversions (§2.2), the polar positions of the blips (§2.4),
the exact lunge unit vector (§2.8), the glyph extents (§1.1), the spring
settle-times/overshoots/frame counts (§4.1), the motion periods quoted
throughout, and the film-scale type ramp (§5.3).
