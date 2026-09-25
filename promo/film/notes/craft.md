# craft.md — the rules the new Tower film is built to

Scope: `promo/film/` only. 1920×1080, 30 fps, **exactly 1200 frames = 40.000 s**.
100% synthetic — every pixel drawn in Pillow/numpy, encoded by ffmpeg. No footage,
no photos, no stock, no external image assets.

Toolchain on this machine (verified): numpy **1.26.4**, Pillow **10.1.0**,
ffmpeg **7.0.1**. Nothing else. Python stdlib otherwise.

Determinism is a hard requirement: no `time.time()`, no `random` without a fixed
seed, no dict-iteration-order dependence, no environment reads. Frame *N* must
hash identically on every run and on every worker count. The old pipeline proves
this is achievable — `render_overlays(..., jobs=N)` forks over interleaved frame
slices and is byte-identical to the serial path because nothing depends on the
clock or on neighbouring frames. Keep that property.

This document is the acceptance spec. If a shot violates a numbered rule, the
shot is wrong — not the rule.

---

## 0. Inventory — what to steal from `promo/overlays.py`

These are proven, deterministic, stdlib+numpy+Pillow. The new toolkit
(`promo/film/`) should **lift them wholesale** rather than reinvent. Signatures
are exact. Line numbers are from `promo/overlays.py` at the time of writing.

### 0.1 Colour (L52–79)
```
rgb(h) -> (r,g,b)                         # '#RRGGBB' or passthrough
rgba(h, a=1.0) -> (r,g,b,a255)
mix(c1, c2, k) -> (r,g,b)                 # k=0 -> c1, linear in sRGB
```
Constants live in `storyboard.py` (L200–209) and are the authority:
`C_AMBER #E6A93C · C_RED #E5484D · C_GREEN #30D158 · C_INK #0C0C0E ·
C_SURFACE #141416 · C_BORDER #242426 · C_TEXT #E7E6E2 · C_MUTED #8B8B86 ·
C_DIM #7C7C77 · C_KICKER #6E6E6A`. Plus `TEXT2 = '#9A9A95'` (overlays L76).

### 0.2 Fonts — including the SFNS variable-weight trick (L83–119)
```
font(kind, size, weight=None)             # kind: 'serif'|'ui'|'mono'|'mono_bold'
```
Cached on `(kind, size, weight)`. The whole trick is `set_variation_by_axes`,
and **the axis order differs per face**:

* `serif` — `/System/Library/Fonts/NewYork.ttf`, axes `[Optical Size, Weight, GRAD]`
  → `f.set_variation_by_axes([clamp(size*2, 12, 256), weight or 520, 0])`
* `ui` — `/System/Library/Fonts/SFNS.ttf`, axes `[Width, Optical Size, GRAD, Weight]`
  → `f.set_variation_by_axes([100, clamp(size, 17, 96), 400, weight or 400])`
  (SFNS's default named instance is Regular; you *must* set `wght` explicitly to
  get semibold ≈ 590. The optical-size axis is clamped to 17–96 — feeding it the
  raw display size silently fails on huge type.)
* `mono` / `mono_bold` — JetBrains Mono Medium/Bold, **static**, no axes. OFL,
  redistributable.

Wrap every `set_variation_by_axes` in `try/except` (the old code does) — a
Pillow build without FreeType variation support must degrade, not crash.

### 0.3 Easing / animation toolkit (L126–201)
```
clamp(x, lo=0.0, hi=1.0)      lerp(a, b, k)          linear(x)
ease_out_expo(x)              # 1 - 2^(-10x)
ease_out_cubic(x)             # 1 - (1-x)^3
ease_in_out_cubic(x)
ease_out_back(x, s=1.70158)   # OVERSHOOT — entrances only, see §4.6
ease_sober(x)                 # == ease_out_cubic; the only easing a failure may use
smoothstep(a, b, x)
t01(t, ev)                    # local 0..1 through an event
env(local, dur, rise=0.25, fall=0.25, ease_in=..., ease_out=...)  # opacity envelope
hash01(i, salt=0)             # pure seeded 0..1 hash of an int
vnoise(x, salt=0)             # smooth value noise over a float coord
```
`env()` auto-clamps rise/fall to `dur*0.45` so short events can't invert. Steal it.

### 0.4 Compositing (L206–268, L598–616)
```
class Layer(x, y, w, h)                  # RGBA scratch buffer
    .im  .d                              # Image, ImageDraw
    .fade(alpha)                         # multiply the alpha channel
    .paste(dst, alpha=1.0, dx=0, dy=0)   # alpha_composite at (x+dx, y+dy)
blend_rect(dst, box, colour, alpha=1.0, radius=0)
bfill(im, box, colour, alpha=1.0, radius=0, outline=None, width=1, oalpha=1.0)
clip_reveal(layer, frac, direction='x', soft=0.10, invert=False)   # soft-edge wipe
```
**The trap `bfill` exists to solve** (L600–602): `ImageDraw` *replaces* pixels, it
does not source-over. Any translucent shape drawn straight onto a painted RGBA
surface punches a hole in the alpha. Every translucent fill goes through a
`Layer` + `alpha_composite`. This bites once per project; it is already solved.

`clip_reveal` is the primitive behind every wipe: it builds a numpy ramp of width
`soft*n` and multiplies it into the layer's alpha. Use it for hairline draw-ons
and panel reveals instead of animating geometry.

### 0.5 Text (L273–343)
```
text_w(s, f, tracking=0.0)                              # sum of advances + tracking
draw_text(d, x, y, s, f, fill, tracking=0.0, anchor='ls')   # 'ls'|'ms'|'rs', BASELINE
draw_kinetic(d, x, y, s, f, colour, alpha=1.0, tracking=0.0, p=1.0,
             stagger=0.055, rise=16.0, ease=ease_out_expo, anchor='ls')
wrap(s, f, max_w, tracking=0.0) -> [lines]
```
`draw_kinetic` is the kinetic-type reveal: per-character alpha + a `rise` px
upward settle, staggered by `stagger` (in units of `p`), with the stagger span
auto-compressed to ≤ 0.72 so long strings still finish inside the window. This
is the only type-reveal mechanism the new film needs (see §4.1 for the constants
to feed it — the defaults are too fast/too loud for the new register).

Note: all tracked text is drawn glyph-by-glyph, so `draw_text` with `tracking != 0`
costs one `d.text()` per character. Fine at our volumes; don't put it in a
per-pixel loop.

### 0.6 Shapes (L348–392)
```
stroke_rect(d, box, colour, width=1, alpha=1.0)
stroke_rrect(d, box, r, colour, width=1, alpha=1.0)
dashed_line(d, p0, p1, colour, width=2, dash=(6,6), alpha=1.0, phase=0.0)
dash_arc(d, cx, cy, r, colour, width=2, dash=(5,6), alpha=1.0, phase_deg=0.0)
```
Pillow has no dash support; these two synthesise it. `dash_arc` converts a pixel
dash length to degrees via the circumference — reuse the maths, don't redo it.

### 0.7 The radar mark (L402–509)
```
render_radar(size, state='clear', p=0.0, still=True, draw_on=1.0, neutral=TEXT)
```
States: `clear · verify · holdGeo · holdNet · off`. Geometry is verbatim
`brand.json.radar_glyph` on a 0..100 box; hub at (50,50), ring R=33, ring width 6,
blips at (64,41) (38,58) (58,66). **Drawn at 4× and LANCZOS-downsampled** because
`ImageDraw` has no antialiasing on arcs or diagonals — adopt this SS≥3 rule for
every curved/diagonal element in the new film. Result cached on the full
parameter tuple (cap 400 entries).

Colour law encoded there and not to be broken: `holdNet`/`holdGeo` → amber,
`off` → red, `clear`/`verify` → **neutral `#E7E6E2`, not green**. The passing
radar is not a green light; it is simply calm.

### 0.8 Grade (L519–569)
```
grade_static(vig=0.55, pitch=3, scan_a=0.06) -> RGBA vignette+scanline plate (cached)
grain_layer(i, amount=2) -> one of 12 pre-rolled plates, cycled by frame index
draw_grade(im, ev, t, f, opts)
```
`grain_layer` seeds `np.random.RandomState(1917)` once and pre-rolls 12 half-res
luma plates upscaled NEAREST — deterministic and cheap. Keep the mechanism;
**retune the amplitude** (§5.7). `grade_static`'s vignette is a radial
`((r-0.52)/0.48)^1.7 * vig*0.62` ramp — keep it, at lower strength.
**Scanlines are banned in the new film** (§6.10): call `grade_static(vig, pitch=0, scan_a=0.0)`.

### 0.9 The waveform trace (L686–723)
```
_wave_points(x, y, w, h, t, state, amp_k=1.0)   # pure f(px, t); scrolls 60 px/s R→L
_draw_wave(dst, box, t, state, colour, amp_k=1.0, alpha=1.0)
```
Two octaves of `vnoise` (÷26 and ÷9) plus a `hash01` jitter term when
`state=='degraded'`; flat line when `offline`. `_draw_wave` adds a baseline
hairline at 0.14 alpha, a left-to-right alpha ramp (`linspace(0.18,1)**0.85`) so it
reads as a live trace, and a filled head dot + ring. Amplitudes: online 0.18,
degraded 0.55, offline 0.0. This is the single best-looking primitive in the old
file. Take it verbatim; only restyle the colour and the box.

### 0.10 Numbers (L1551–1564)
```
_digit_cell(im, x, ybase, digit_f, f, colour, alpha, cw, size)
```
A true odometer: each digit lives in a clipped `Layer`, and rolls only in the last
14% before its own carry (`smoothstep(0.86, 1.0, frac)`), so high places don't
wobble while the units spin. Mono font ⇒ tabular by construction. This is the
"precision" device in §4.7 — reuse it exactly.

### 0.11 Type-reveal recipes worth reading, not copying (L1650–1740)
`draw_super` (styles `kinetic` / `stamp` / `whisper`) and `draw_title` show the
weights and tracking that read at scale: stamp = ui@700 tracking 0.005em with a
1.05→1.00 `ease_out_expo` snap (a snap, not a spring); whisper = ui@340 tracking
0.045em; title = serif@560 tracking 0.06em with a rule that draws on. Steal the
*parameters*. Do **not** steal `super_scrim()` (L1636) or the 0.94-alpha plate
under `draw_stat` (L1588) — those are legibility patches for type sitting on
captured UI, and in a synthetic film that situation must never arise (§6.5).

### 0.12 Render harness (L1913–2013)
```
_frame_buckets(evs)                       # per-frame event lists, sorted by (z, t)
render_overlays(out_dir, progress=None, frames=None, grade=True,
                grain=False, compress=3, jobs=1)
main(argv)                                # CLI: out_dir, --range A:B, -j, --compress
```
Event → frame bucketing, z-sorted draw, `mp.Pool` over interleaved slices,
`--range A:B` for spot checks. Copy this shape; it makes iteration bearable.

---

## 1. Canvas, grid, safe areas

| Constant | Value |
|---|---|
| Frame | 1920 × 1080, sRGB, opaque RGB on export |
| Field (background) | `#0C0C0E` — never `#000000` |
| Margin (hard) | **160 px** left/right, **120 px** top/bottom |
| Action-safe ring | outer **96 px** on all sides: **must contain zero drawn content** |
| Columns | 8 cols × 165 px, gutter 40 px (160 + 8·165 + 7·40 + 160 = 1920) |
| Baseline grid | 12 px; all text baselines are `120 + 12k` |
| Optical centre | single hero line sits at **y = 0.44 H = 475 px** baseline, not 540 |
| Corner radius | 12 px on any panel; 999 on a pill; nothing in between |
| Hairline | 1 px `#242426`; subject stroke 2 px; nothing ≥ 3 px except the radar ring |

Every element's bounding box, including its glow/soft edge, lies inside
`(160, 120) → (1760, 960)`. Nothing is cropped by the frame edge, ever. If it
doesn't fit, it gets smaller or gets its own shot.

---

## 2. Negative space

1. **≥ 62 % of every frame is untouched field** — pixels within ±10/255 luma of
   `#0C0C0E` after grading. On a statement/hero shot: **≥ 78 %**.
2. **Ink coverage ≤ 25 %** of frame pixels in any frame; **≤ 12 %** on a hero
   shot. ("Ink" = |luma − field luma| > 10.)
3. **Accent coverage ≤ 3 %** of frame pixels carry a saturated brand hue
   (amber/red/green, S > 0.35). A single accented hero word may reach 6 %.
   In ≥ 70 % of the film's 1200 frames the accent coverage is **0 %**.
4. **Gutter between unrelated elements ≥ 64 px.** A label bound to its own
   subject may come to 24 px; nothing else.
5. **One idea per shot.** Every shot in the manifest declares
   `idea: "<≤ 8 words>"`. If you cannot write it in eight words, it is two shots.
   Enforcement is a build-time assertion, not a hope.
6. **One subject per shot.** Exactly one element is the largest/highest-contrast
   thing on screen, plus at most: one caption, one kicker. Three text objects is
   the ceiling; two is the target.
7. **Max two overlay families per frame**, where a family is one of
   {hero type, one synthetic UI surface, one label/chip, one data mark}.
   The old film routinely stacked five. See §6.7.
8. **No full-width bands.** No element spans more than 6 of 8 columns
   (≤ 1190 px) except a deliberate 1 px rule, which may span 4–8 columns.
9. Vertical: content occupies at most **two horizontal bands** per frame, and the
   bands are separated by ≥ 120 px of empty field. Type band and UI band are
   always disjoint — they never overlap on the y axis, so type can never sit on
   live UI text (§6.4).

---

## 3. Type

### 3.1 Scale (px em at 1080p)

| Role | Face / weight | Size | Tracking | Colour |
|---|---|---|---|---|
| Wordmark | serif (NewYork) 560 | 200 | +0.06 em (+12 px) | `#E7E6E2` |
| **Hero line** | serif 520 **or** ui 590 | **120** (range 108–132) | −0.01 em (−1.2 px) | `#E7E6E2` |
| Secondary statement | ui 520 | 72 | −0.005 em | `#E7E6E2` |
| Lede / caption | ui 400 | 36 (34–40) | +0.01 em | `#9A9A95` |
| Kicker / eyebrow | mono_bold, UPPERCASE | 20 | **+0.24 em (+4.8 px)** | `#6E6E6A` |
| State label | mono_bold, UPPERCASE | 24 | +0.14 em (+3.4 px) | state colour |
| Big number | mono_bold, tabular | 160 | 0 | `#E7E6E2` |
| Unit / suffix | ui 420 | 36 | +0.02 em | `#9A9A95` |

Hero cap-height ≈ 0.72 × 120 = **86 px = 8.0 % of frame height**. That is
Apple-ad scale. Below 96 px em a "hero" line reads as a subtitle; above 140 px it
reads as a title card. Anything under **20 px em is banned anywhere in the film**,
and no text is drawn below **55 % alpha** against the field.

### 3.2 Quantity

* Hero line: **≤ 6 words**, always **one line**. No wrapped hero lines.
* Total words visible in any single frame, all tiers summed: **≤ 11**.
* Measure (line length): **≤ 46 characters and ≤ 1190 px**, whichever binds first.
* **≤ 3 type tiers per shot** (e.g. kicker + hero + caption). Never four.
* Whole film: **≤ 60 words of on-screen copy** across all 40 s.

### 3.3 Reading time (the floor — nothing flashes past)

For a text block of `n` words, minimum **full-opacity hold**:

```
hold_s  = 0.60 + 0.38 * n           # lead-in + 0.38 s per word
hold_s >= 1.40                      # absolute floor for any word
kicker  >= 1.00                     # even a 2-word eyebrow
```
Reveal and exit time do **not** count toward `hold_s`. So a 5-word hero needs
`0.60 + 1.90 = 2.50 s` at full opacity, plus ~0.42 s reveal and ~0.26 s exit
≈ **3.2 s of screen time (96 frames)**. Budget the 1200 frames accordingly — this
is why the word ceiling is 60. Build-time assertion:
`assert shot.dur_f >= fps * (0.60 + 0.38*n + 0.42 + 0.26)`.

### 3.4 Optical alignment

* Left-align on the **flat left edge of the first glyph** via `font.getbbox()`,
  not the advance origin. `T`, `V`, `W`, `O` and quotes need hanging correction
  of 2–8 px at hero scale; do it, or the column looks broken.
* Centred type is centred on `text_w(s, f, tracking)` **minus the trailing
  tracking unit** — `draw_text` adds `tracking*(len-1)`, which is already correct;
  don't add a trailing space.
* Baselines snap to the 12 px grid **after** optical correction, not before.
* Mixed-face lines are aligned on the baseline, never on cap-height.
* A number and its unit sit on a shared baseline with a 10 px optical gap, not a
  space character.

---

## 4. Motion

Apple motion is: **slow-in/slow-out, short travel, no linear moves, no bounce on
anything serious.** All of the below.

### 4.1 The easing tokens (cubic-bezier, exact)

Implement a real `bezier(x1, y1, x2, y2)` solver (Newton, 8 iterations, seeded
from `t = x`; fully deterministic) and expose these as named constants. The
closed-form approximation already in `overlays.py` is listed as a fallback.

| Token | cubic-bezier | ≈ closed form | Use |
|---|---|---|---|
| `EASE_ENTER` | `(0.16, 1.00, 0.30, 1.00)` | `ease_out_expo` | element enter, type reveal, opacity in |
| `EASE_MOVE` | `(0.65, 0.00, 0.35, 1.00)` | `ease_in_out_cubic` | camera push, anything that travels |
| `EASE_SOBER` | `(0.33, 1.00, 0.68, 1.00)` | `ease_out_cubic` | **every** hold/block/off/failure change |
| `EASE_SNAP` | `(0.22, 1.00, 0.36, 1.00)` | `ease_out_expo` | a confirm, a number landing |
| `EASE_EXIT` | `(0.32, 0.00, 0.67, 0.00)` | `1-(1-x)^3` inverted | leaving frame / opacity out |
| `EASE_ARRIVE` | `(0.34, 1.28, 0.64, 1.00)` | `ease_out_back(s=1.2)` | **only** a neutral entrance, max 4 % overshoot |

`linear` is banned for anything visible. The only linear functions in the film are
the waveform scroll (60 px/s — a real signal, not a move) and the radar sweep
rotation (the mark's own geometry).

### 4.2 Durations (ms)

| Move | Duration | Easing |
|---|---|---|
| Type reveal (per line envelope) | **420** | `EASE_ENTER` |
| Type reveal per-char stagger | **26 ms/char**, total stagger span capped at **320** | — |
| Type reveal rise | **0.14 em** (17 px at hero) | `EASE_ENTER` |
| Element enter (panel, card, mark) | **340** | `EASE_ENTER` |
| Hairline draw-on (`clip_reveal`) | **520** | `EASE_MOVE` |
| State change (colour/label swap) | **250** | `EASE_SOBER` |
| Number roll to landing | **900** | `EASE_SNAP` |
| Camera push | **1200–2000** (never < 900) | `EASE_MOVE` |
| Exit / fade out | **260** | `EASE_EXIT` |
| Cross-dissolve (rare, §4.5) | **320** max | `EASE_MOVE` both sides |
| Cut | **1 frame** | — |
| Held silence before a reveal | **400–700** | — |

### 4.3 Travel budget (short travel)

* Max translation of any element: **115 px horizontal (6 % W), 65 px vertical
  (6 % H)**. Type reveal rise is 17 px. Nothing flies in from off-frame.
* Camera push: scale **1.000 → 1.045** maximum, ≥ 1.2 s, `EASE_MOVE`, and the
  push is toward the subject's optical centre. **Never a zoom-out on a reveal.**
* **No rotation** of any element, ever, except the radar's own sweep.
* **No motion blur.** Author things slow enough not to need it.
* **One moving element per frame.** The camera counts as the one. If the camera
  pushes, nothing else animates; if type reveals, the camera is locked.

### 4.4 Cuts land on a beat

The film has a 0.5 s pulse. **Every cut lands on a frame index divisible by 15.**
Major reveals land on multiples of **60** (2.0 s). Shot lengths: min **36 frames
(1.2 s)**, max **165 frames (5.5 s)**, target 45–150. Expect **12–16 shots** in
1200 frames. Cut points are declared in the manifest and asserted at build time
(`assert f0 % 15 == 0`).

### 4.5 Cut vs dissolve

**Default is a hard cut.** A cross-dissolve is permitted only when *both* the
outgoing and incoming frames have ink coverage **< 12 %**, and lasts ≤ 320 ms.
Dissolving two dense layers is the single ugliest thing the old film did (§6.6).
A dip-to-field (out to `#0C0C0E`, 200 ms, hold 2–4 frames, in 200 ms) is always
allowed and is the preferred way to change chapter.

### 4.6 Bounce law (honesty, not taste)

`EASE_ARRIVE` / `ease_out_back` may touch **only** neutral entrances. It is
**forbidden** on any element whose state is amber (hold), red (off/danger), or on
any block/pending/failure moment. Those use `EASE_SOBER`, 250 ms, no overshoot,
no shake. This is `brand.json.motion_laws.must_never`: *"Failure must NEVER
bounce."* It is also why it looks expensive: the serious moments are still.

### 4.7 Stillness

* The passing/quiet state is **completely still**. Nothing loops when all is well.
* At most **one** pulsing/glowing element at a time, ever.
* A shot may be entirely static for its whole duration. At least **3 shots** in
  the film should be.

---

## 5. What makes it premium

1. **Deep true black.** Field `#0C0C0E`. Panels `#141416`. Nothing between them.
   Never `#000000` (kills depth, bands on encode), never a lifted grey.
2. **One accent at a time.** A frame carries at most one saturated hue. Amber and
   green never coexist. Red appears in at most one shot in the whole film.
3. **Hairlines.** 1 px `#242426` for all structure. Curves and diagonals are
   supersampled ≥ 3× and LANCZOS-downsampled (`render_radar`'s technique) —
   a jaggy 1 px arc is the single clearest "made in Pillow" tell.
4. **Generous tracking on small caps.** Kicker +0.24 em, state labels +0.14 em.
   Small uppercase without tracking looks cheap; this one change does more for
   the register than any effect.
5. **Gradients: essentially none.** Permitted: the radial vignette at strength
   ≤ **0.35** (old film used 0.55), and linear luminance ramps with a total delta
   ≤ **6 %** used only as an alpha falloff. **No hue-shifting gradient anywhere.**
6. **Shadows: none.** No drop shadows. The only depth cue is a hairline border.
   If ambient lift is unavoidable: radial, ≤ **4 % alpha**, radius ≥ 2.5× the
   element, and never offset (a shadow with an offset is banned outright).
7. **Grain exists only to kill banding.** `grain_layer(i, amount=1)` — half the
   old amplitude, clipped ≤ 14/255. It must be invisible when you look for it and
   the flat field must be free of 8-bit banding. **Scanlines: off** (`scan_a=0.0`).
8. **Perfect optical alignment** (§3.4) and a single 12 px baseline rhythm.
9. **Restraint in count.** Two objects beat five. The whole film should feel like
   it could have been printed.
10. **Encode clean.** PNG intermediates, `libx264 -crf 16 -preset slow -pix_fmt
    yuv420p`, `-x264-params "aq-mode=3"` for the flat blacks, `-movflags
    +faststart`. No visible blocking in the field on a large display.

---

## 6. What makes it exciting rather than sleepy

Minimal ≠ slow. The energy comes from control, not decoration. Devices we use,
by name — the manifest should tag which shot uses which:

1. **Anticipation.** 6–10 frames of dead stillness (or a 2 % counter-move away
   from the direction of travel) immediately before every major move.
2. **Held silence before a reveal.** 12–20 frames of near-empty frame (ink < 4 %)
   before the biggest beat. Nothing is on screen. Then the thing arrives.
3. **The hard cut on the beat.** §4.4. Cuts on the 0.5 s pulse make a film feel
   scored even without music, and let a 40 s piece carry 14 ideas.
4. **One accent arriving in a field of neutral.** Amber appears **suddenly, once**,
   after ≥ 8 s of pure neutral. That single arrival is the emotional peak. It is
   why §2.3 caps accent coverage at 3 %: scarcity is the effect.
5. **Scale contrast across a cut.** Adjacent shots differ in subject scale by
   **≥ 3×** (a 1 px hairline / a 24 px chip, then a 120 px hero, then a 160 px
   number). At least 4 such jumps in the film.
6. **Speed contrast.** A 2.0 s slow push immediately followed by a 0.4 s snap.
   Never two shots at the same tempo back to back.
7. **Precision.** Odometer digits (`_digit_cell`) that land *exactly* on a cut
   frame. A hairline that draws to exactly the column edge. Numbers that are real.
8. **The match cut on the radar ring.** The ring occupies the identical screen
   circle across a cut; only its *state* changes (`clear` → `holdGeo`). Nothing
   moves, everything changes. Cheapest, strongest device we have.
9. **Draw-on rather than fade-in.** `clip_reveal` a rule or an arc into existence
   (520 ms, `EASE_MOVE`) instead of fading it. Fades are sleepy; draw-ons are alive.
10. **Asymmetric composition.** Hero type on columns 1–5, subject on 6–8. Dead
    centre only for the wordmark and the final card.
11. **The live trace.** `_draw_wave` running behind a still frame is the one
    permitted continuous motion — it reads as *the machine is on*, and it costs no
    attention because it never changes size or position.
12. **End on a hold.** The last 24 frames are completely static: mark, wordmark,
    one line. No animation into the freeze.

---

## 7. Honesty constraints on the visuals

Because we are *drawing* the UI rather than capturing it, every synthetic surface
must be faithful to the real design system and real semantics. Non-negotiable:

| Situation | Colour | Word |
|---|---|---|
| Confirmed inside target | neutral `#E7E6E2` (radar `clear`) | `INSIDE TARGET` |
| Checking / verifying | neutral (radar `verify`) | `CHECKING` |
| **Outside target** | **AMBER `#E6A93C`** — never red | `OUTSIDE TARGET` |
| Net offline / captive / edge unreachable | **AMBER** (radar `holdNet`) | `HOLDING` |
| Degraded / slow but reachable | amber label, **and traffic is ALLOWED** | `SLOW LINK · STILL ALLOWED` |
| Routing off / unguarded | RED `#E5484D` (radar `off`) | `UNGUARDED` |
| An agent finished | green `#30D158` — **status text only** | `done` |

* The passing radar is **neutral, not green**. Green is `AgentStatus.done`, never
  the guard ring.
* A blocked request is **held → 503 + Retry-After → PENDING**. On screen it may
  say `HELD`, `PENDING`, `503 · Retry-After`, `Retrying · attempt 2/8`.
  It may **never** say `403`, `FAILED`, `ERROR`, `DROPPED`, `DENIED`.
* **Degraded is not blocked.** If a shot shows a slow link, it must also show that
  traffic still passes.
* Nothing from `brand.json.do_not_claim` may appear: not a VPN, not a firewall,
  not a kill switch, not OS-level, not notarized, no telemetry, no traffic
  inspection, no token reading, no Windows/Intel/Linux, no writing into sessions,
  no running-agent count in the menu bar.
* Numbers on screen must be plausible and internally consistent across shots
  (one canonical fixture in the manifest; no shot invents its own).

---

## 8. THE BAN LIST

Every item below is something the old film at `promo/` actually did. Verified
against `promo/out/stills/s_4.0.jpg`, `s_13.0.jpg`, `s_20.9.jpg`, `s_27.0.jpg`.

1. **No captured pixels.** Not one frame, not one crop, not a texture.
2. **No content touching or crossing a frame edge.** `s_13.0` shows `TOW…` clipped
   at x=0 and `…da` clipped at x=1919; `s_4.0` shows a macOS title bar sliced by
   the top edge. Everything lives inside the safe box (§1) or it doesn't exist.
3. **No mid-word clipping.** `s_20.9`: *"A control tower for your Claude ag"*.
   `s_27.0`: *"owhere in the tree"*. `s_13.0`: *"Fabl"*. If it doesn't fit,
   shorten the copy — never crop the line.
4. **No type over live UI text.** `s_27.0` puts *"The wire was fine."* directly on
   *"Usage paused — location not confirmed"*. Type band and UI band are disjoint
   on the y axis (§2.9).
5. **No scrim as a fix.** `super_scrim()` and the 0.94-alpha plate under
   `draw_stat` exist only because type was placed on busy pixels. In a synthetic
   film that is a layout bug. **Banned:** any darkening plate whose purpose is to
   make text readable over other content.
6. **No cross-dissolve between dense layers.** `s_20.9` ghosts a 200 px `TOWER`
   serif wordmark over a fully populated terminal — two legible layers, neither
   readable. See §4.5.
7. **No overlay pile-up.** `s_13.0` has, simultaneously: a full-width dual-lane
   HUD, a caption strip, a whole TUI, a ghosted super, a privacy-mask plate and a
   live-traffic log. Max two families (§2.7).
8. **No always-on chrome.** No persistent full-width HUD bar, no permanent corner
   badges, no watermark. Chrome that is always there is chrome nobody sees.
9. **No corner brackets, crosshairs, reticles or targeting language**
   (`_corner_bracket`). Tower is an honest status layer, not a weapons HUD.
10. **No CRT/retro effects.** No scanlines, no chromatic aberration, no RGB split,
    no glitch, no VHS, no lens flare, no light leak, no film burn.
11. **No speed ramps.** The old film ramped a recording to make it feel urgent.
    If a thing should be fast, author it fast at 30 fps.
12. **No heavy vignette.** ≤ 0.35 (old: 0.55). A vignette you can see is a filter.
13. **No fake window chrome or third-party UI.** No traffic-light buttons, no
    macOS title bar, no terminal tab strip, no other app's text
    (`s_4.0`/`s_20.9` show a real Terminal title bar and a real menu). Synthetic
    surfaces are Tower's own visual language, abstracted.
14. **No redaction.** No `PRIVACY MASK` plates, no blur bars, no `***.**` IPs.
    Nothing is captured, so there is nothing to hide; a redaction bar just tells
    the viewer we were hiding something.
15. **No text below 20 px em and none below 55 % alpha.** The old film's 16 px
    footnotes at `DIM` are unreadable at any bitrate and just add grey noise.
16. **No bounce/overshoot on a hold, block, off or failure state.** §4.6.
17. **Never red for "outside target".** Amber. §7.
18. **Never "degraded ⇒ blocked"**, never `403`, never "failed"/"error" for a
    held request. §7.
19. **No two things moving at once**, and never a push + a dissolve simultaneously.
20. **No decorative loops when the state is fine.** Nothing spins/pulses to look
    busy. The one exception is `_draw_wave` (§6.11).
21. **No copy over 6 words in a hero line, no wrapped hero lines, no more than 3
    type tiers, no more than 11 words on screen.** §3.2.
22. **No unseeded randomness, no clock reads, no frame-order dependence.**
23. **No new dependencies.** numpy 1.26 + Pillow 10.1 + stdlib + ffmpeg 7.0.1.
24. **No touching `promo/*.py`.** The old pipeline is frozen; the new film lives
    entirely under `promo/film/`.

---

## 9. Per-shot checklist

Run against a rendered still from the shot's midpoint, plus its first and last
frame, plus the manifest entry. Every line is pass/fail — no "mostly".

**Composition**
- [ ] 1. The 96 px action-safe ring contains **zero** ink (max |Δluma| ≤ 10).
- [ ] 2. Every element bbox is inside `(160,120)–(1760,960)`.
- [ ] 3. Field fraction ≥ 62 % (hero shot: ≥ 78 %).
- [ ] 4. Ink coverage ≤ 25 % (hero: ≤ 12 %).
- [ ] 5. Accent coverage ≤ 3 % (single accented hero word: ≤ 6 %), and **one hue only**.
- [ ] 6. ≤ 2 overlay families; ≤ 3 text objects; exactly 1 subject.
- [ ] 7. The shot's `idea:` string is ≤ 8 words and the frame demonstrates it alone.
- [ ] 8. Gutter between unrelated elements ≥ 64 px.
- [ ] 9. Type band and UI band do not overlap on y.
- [ ] 10. Nothing is centred that isn't the wordmark or the end card.

**Type**
- [ ] 11. Hero em is 108–132 px; no hero line wraps; ≤ 6 words.
- [ ] 12. ≤ 11 words total on screen; ≤ 3 tiers.
- [ ] 13. No glyph below 20 px em; no text below 55 % alpha.
- [ ] 14. Kicker tracking +0.24 em, state labels +0.14 em, both UPPERCASE.
- [ ] 15. Left edges optically aligned (first-glyph bbox, not advance origin).
- [ ] 16. Every baseline is `120 + 12k`.
- [ ] 17. Full-opacity hold ≥ `0.60 + 0.38·words`, and ≥ 1.40 s for any word.
- [ ] 18. No word is clipped, hyphenated or truncated.

**Motion (check across the shot's frames)**
- [ ] 19. No `linear` on anything visible.
- [ ] 20. Exactly one element moves at a time (camera counts).
- [ ] 21. Max travel 115 px x / 65 px y; camera scale ≤ 1.045 over ≥ 1.2 s.
- [ ] 22. Any amber/red/hold/block/off transition uses `EASE_SOBER`, 250 ms,
      zero overshoot. Nothing bounces.
- [ ] 23. Shot starts on a frame index divisible by 15; a major reveal on 60.
- [ ] 24. Shot length 36–165 frames.
- [ ] 25. Transition in is a cut or a dip-to-field; any dissolve is ≤ 320 ms and
      both sides are < 12 % ink.
- [ ] 26. No rotation, no motion blur, no speed ramp.

**Premium finish**
- [ ] 27. Darkest field pixel is `#0C0C0E` ±2, not `#000000`.
- [ ] 28. Hairlines are 1 px `#242426`; nothing ≥ 3 px except the radar ring.
- [ ] 29. Curves/diagonals supersampled ≥ 3× (no visible stair-stepping at 100 %).
- [ ] 30. Vignette ≤ 0.35; scanlines absent; grain invisible but banding absent.
- [ ] 31. No drop shadow; no offset shadow of any kind.
- [ ] 32. No hue-shifting gradient; any luminance ramp ≤ 6 % delta.

**Honesty**
- [ ] 33. "Outside target" is amber, never red.
- [ ] 34. Passing radar is neutral `#E7E6E2`, not green.
- [ ] 35. Any block reads HELD/PENDING/503 · Retry-After — never 403/failed/error.
- [ ] 36. If a slow link is shown, it is also shown as still allowed.
- [ ] 37. No claim from `brand.json.do_not_claim` appears in copy or imagery.
- [ ] 38. Numbers match the single canonical fixture across all shots.

**Ban sweep**
- [ ] 39. No captured/derived-from-capture pixels; no fake window chrome; no
      third-party UI text; no redaction bar; no corner bracket/reticle; no CRT
      artefact; no scrim-for-legibility plate.

**Build integrity**
- [ ] 40. Rendering the shot twice yields identical SHA-256 per frame, and
      `-j 1` matches `-j 8`.

---

## 10. Automatable checks (write these as `promo/film/check.py`)

```
field_frac(img)        # frac of px with |luma - luma('#0C0C0E')| <= 10     >= 0.62
ink_frac(img)          # 1 - field_frac                                      <= 0.25
accent_frac(img)       # HSV: S > 0.35 and V > 0.25                          <= 0.03
safe_ring_clean(img)   # 96 px border ring: max |Δluma| <= 10                == True
black_point(img)       # img.min() over RGB                                  in 10..14
hue_count(img)         # distinct accent hues present (12° buckets, >0.2% px) <= 1
banding(img)           # max run-length of identical luma along a row in the
                       # field region                                        <= 40 px
determinism(shot)      # sha256 of every frame, two runs, jobs=1 vs jobs=8   equal
manifest_lint()        # words<=6/line, tiers<=3, hold>=0.60+0.38n,
                       # f0 % 15 == 0, 36 <= dur_f <= 165, idea <= 8 words,
                       # sum(words) <= 60, one accent key per shot
contact_sheet()        # 1 still per 15 frames -> 10x8 grid PNG for eyeball review
```

A shot that fails `manifest_lint()` must not render. A frame that fails
`safe_ring_clean` must fail the build, not the review.
