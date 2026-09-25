# review-craft.md — Apple-ad craft review of `out/tower-film.mp4`

**Lens:** minimal / premium / modern. Nothing else. Not honesty, not structure,
not audio — those get their own passes. This one asks: *does it look expensive?*

**Method.** All 1200 frames extracted from the encoded MP4 with
`ffmpeg -i out/tower-film.mp4 -vsync 0` into
`…/scratchpad/qa_craft/all_%04d.png` (so `all_0081.png` = film frame 80).
Every frame cited below was opened and looked at. Consecutive-frame strips were
built through every morph and every cut (`s_M1 s_M2 s_M3 s_M5 s_off s_cut s_D1
s_type_a2 s_url s_relay`). Numeric measurements are from `out/frames/*.png`
(pre-encode) so grain/vignette/ink figures are not confused by x264.

**Verdict: not there yet.** The type on the two hero cards is genuinely
beautiful, the safe-area discipline is flawless, and three motion ideas (the
ring breaking, the ring re-knitting, the `CA` that never moves) are better than
anything in the old film. But the mark — which is on screen for 810 of 1200
frames — currently renders as a *sunburst / gear / roulette wheel* in three of
its five states, every "kinetic" type reveal is a per-character typewriter, the
frame averages **1.6 % ink**, and 67.5 % of the film is one repeated
composition. Right now it reads as a well-made screensaver with a dev-tool icon
set, not as a product film.

---

## Ranked findings

---

### 1 · The dashed ring renders as a sunburst, not a broken ring — the film's three "serious" states all look like a gear

**Frames:** f536–f614 (`holdNet`, B3) · f621–f689 (`off`, B4) · f780–f869
(C2 left) · f735–f944 (the `holdGeo` fence) · f1044–f1073 (D1).
Look at `z_holdnet_ring.png` (f580, 3× zoom) and `z_off_ring.png` (f660).

**What is wrong.** The dash is specified in unit lengths as `(5, 6)` on a ring
whose stroke is `6.0` units (`scene_end.py:461`, `scene_end.py:491`,
`scene_wire.py:620`, and FILM §2.3/§3). **The dash is shorter than the stroke is
wide.** 21 px long × 25.2 px thick. Each "dash" is therefore a *square block*,
and 24 of them around a circle is a sunburst — a roulette wheel, a camera
aperture, a loading crown. Same failure on the `off` state at `(5, 7)` and, at
small scale, on the `holdGeo` fence at `(4, 5)` (`scene_hold.py:473`), so
`holdGeo` renders as a crown *inside* a ring: two concentric sunbursts.

Two consequences:

* It is the single loudest, cheapest-looking object in the film, and it is
  amber or red, so it is also the only saturated thing on screen.
* It destroys the film's thesis. C2 (f780–869) exists to let the viewer resolve
  "broken ring vs solid ring". As rendered, the left mark is not a broken ring —
  it is a completely different symbol. See f810 and f830: they read as two
  unrelated logos, not one object in two states.

The proof that this is a dash-*length* problem and not a dash problem is in the
morph itself: `s_M2.png`, frames **f528–f532**, where the interpolation passes
through long arcs with short gaps, is the most premium image in the entire film.
By f536 it has become a gear.

**Fix.** Lengthen every dash so `on ≫ stroke`, and quantise the period to an
integer number of dashes so the pattern closes without a seam (there is a
visible irregular gap at ~4:30 in f660 and ~2:00 in f740 today).
Ring circumference at `r = 33` is `207.345`; fence circumference at `r = 15` is
`94.248`.

| where | today | change to | dashes |
|---|---|---|---|
| `holdNet` ring — `scene_end.py:461`, and the same tuple in `scene_wire.py` | `(5.0, 6.0)` | `(13.8, 6.9)` | 10 |
| `off` ring — `scene_end.py:491`, `scene_wire.py:620` | `(5.0, 7.0)` | `(15.4, 7.7)` | 9 |
| `holdGeo` fence — `scene_end.py:477`, `scene_hold.py:473` | `(4.0, 5.0)` | `(7.85, 3.93)` | 8 |

Also give the dash ends **round caps** (`_ring` draws butt-capped quads in all
four copies: `scene_open.py:367`, `scene_wire.py:382`, `scene_hold.py`,
`scene_end.py:356`). A rounded terminal on a 25 px stroke is the difference
between "a guard ring that has opened" and "a warning sticker".

---

### 2 · The frame is empty in the wrong way: 1.6 % ink, and 810 of 1200 frames are the same composition

**Frames:** measured ink coverage (`L > 40`) — f80 **1.70 %**, f140 **0.88 %**,
f230 1.83 %, f300 1.90 %, f480 1.66 %, f580 1.14 %, f660 0.97 %, f760 1.66 %,
f830 1.48 %, f920 2.54 %, f1000 2.04 %, f1045 **1.08 %**, f1160 2.51 %.

craft §9.4 caps ink at 25 % (12 % on a hero). The film runs at **one twelfth of
the hero cap**. That is not restraint, that is an underfilled frame. Apple's
most minimal work sits at 5–15 %.

Two specific symptoms:

**(a) The Layout-M hole.** Look at f230, f300, f480, f580, f660, f760, f920,
f1000. The copy column ends at x ≈ 520–600. The mark starts at x = 1138. There
are **540–620 px of dead black through the exact centre of the frame**, in every
one of those shots, and content occupies only the y 390–740 band. The frame
reads as two small posters pinned to opposite corners. This composition runs
A3 + A4 + B2 + B3 + B4 + C1 + C3 + C4 = 660 frames, plus A1 (90) and D1 (60) as
the same layout with the copy deleted: **810 / 1200 = 67.5 % of the film, 27
seconds, one picture.**

**(b) The solo-mark shots are unbalanced, not confident.** f80 and f1045: a
302 px object at x = 1290 with 1130 px of nothing to its left and no second
element to hold the frame. A1 (90 f) and D1 (60 f) are five seconds of a frame
that looks like a caption failed to render.

**Fix, concrete.**

* **Grow the mark.** The canonical circle is a 420 px box drawing a 302 px
  object (measured: bbox 304 × 304 at f80, constant all film — see §"what is
  already excellent"). Take the box to **560 px** (visual Ø ≈ 403) and move
  the centre from `(1290, 540)` to `(1250, 540)`. Box becomes
  `(970, 260) → (1530, 820)`; still 290 px clear of the right safe edge.
* **Move the copy column right and widen it.** `x = 160` → `x = 260`. Combined
  with the bigger mark the centre gap drops from ~600 px to ~330 px and the two
  masses start reading as one composition.
* **A1 and D1 must not use the Layout-M position.** With no copy, put the mark
  on the frame's optical centre, `(960, 500)`, at the 560 px box. It is a
  different shot, so it may have a different placement; nothing rhymes with an
  empty half-frame.

---

### 3 · Every "kinetic" type reveal is a per-character typewriter with no rise

**Frames:** `s_type_a2.png`, f106–f127. Read them in order:
f111 `Wh` → f112 `Whe` → f113 `Wher` → f114 `Where` → f115 `Where y` →
f116 `Where yo` → f117 `Where you` → f118 `Where you a` → f119 `Where you ar` →
f120 `Where you are` → f121 `Where you are.`

That is one glyph per frame. It is the oldest cliché in motion graphics and it
is the fastest way to look like a template. The kicker `CHECK ONE` types on in
the same four frames (f108–f112), so there are two typewriters running at once.

Worse: **the 17 px rise specified in FILM §2.7 is not happening.** Compare the
baseline of `Wh` at f111 with `Where you are.` at f121 — identical. The reveal
is pure sequential per-char opacity. The "rise" channel that would have made it
feel authored is absent.

Same failure on the URL: `s_url.png`, f1119 `g` → f1120 `gh` → f1121 `ghhrm` →
… → f1128 complete. FILM §4.14 calls this a `clip_reveal` **wipe**; it renders
as a typewriter with a half-lit leading glyph (see f1123's ghost `h`, f1125's
ghost `o`), which at 1:1 looks like a rendering error.

**Fix.** Kill the per-character stagger everywhere. Replace `draw_kinetic` with
a **whole-line** reveal: opacity 0 → 1 over 13 f `EASE_ENTER`, plus a real
translate of `0.14 em` (17 px on the hero, 5 px on the caption, 3 px on the
label) on the same curve, drawn to a float offset. If a leading edge is wanted,
use a **soft-edged left→right mask over the whole line** (a 120 px feathered
wipe travelling 0 → width+120 over 13 f) — that is the Apple gesture and it
never exposes a partial glyph. Affected: A2 (f108/f111), B1 (f336/f339), A3
(f186/f198), A4 (f270/f273/f278), C2 (f791), C4 (f962/f972/f976), D2
(f1083/f1086/f1120).

---

### 4 · The `verify` sweep is drawn over the ring: the wedge eats the white band and the needle punches through it

**Frames:** f70–f261 and f966–f1019 — i.e. **~250 frames**. Best seen in
`z_wedge_ring.png` (f230, 4× zoom) and `z_a1_f80_mark.png`.

`scene_open.py:444` draws the ring at centreline `r = 33.0 u`, half-stroke
`3.0 u`, so the band spans `r = 30 … 36`. Then `scene_open.py:453–461` draws the
trail wedge to `wr` and `:462–472` draws the needle to `nlen`, both of which run
to **33 u** (FILM §4.1: "needle length 0 → 33 units"), *and both are drawn after
the ring so they paint on top of it*. Results visible at f230:

* The grey wedge covers the **inner half of the white ring** wherever it passes.
  The ring visibly narrows from 26 px to ~13 px along the wedge's arc, and there
  is a hard grey chord sitting inside the white band.
* The needle crosses the whole band and its round cap
  (`ellipse` at `nx, ny`, r = 2 u) lands at 35 u — 147 px, i.e. *inside* the
  ring band, 4 px from its outer edge. The needle and the ring fuse into a
  white blob with a spur at 1:30.
* The blip at `BLIPS[0] = (64, 41)` (`scene_open.py:364`) sits under the needle
  and reads as a **lump on the line** (clearly visible in the 4× crop).

**Fix.** Clamp everything inside the ring's inner edge:

* `nlen` and `wr` max: **33.0 → 29.0** units (ring inner edge is 30.0; the
  needle's 2 u cap then tops out at 31 — still touching, so also reduce the cap
  or use `28.0`).
* Draw the sweep **before** the ring (move the block at `scene_open.py:448–472`
  above `:440`), so if anything ever does overlap, the ring wins. Apply in all
  four `_ring`/radar copies.

**And replace the flat-alpha wedge with a gradient.** Measured luma of the wedge
is ~48 on a field of 13 — a hard-edged, uniform dark-grey pie slice with two
hard radial edges (`d.polygon(..., fill=_rgba(TEXT, wa))`). That is the single
cheapest-looking element in the mark; it reads as a loading-spinner asset. Draw
it as 12 stacked wedge slices with alpha ramping `0.16 → 0.00` from the needle
backwards, or as a radial-angular gradient mask. A radar trail *decays*; this
one is a triangle.

---

### 5 · C3's `503` lockup — the film's payload — is the worst-set type in it

**Frame:** f920. See `z_503.png` (2× zoom of x 150–860, y 570–760).

Five separate problems in one lockup:

1. **The `0` has a dot in it.** JetBrains Mono's programmer zero, at 160 px, in
   the middle of the most important string in the film. It reads as a defect —
   an eye, a bullet hole, a typo. Nothing else in the film has a dotted counter,
   so it looks like an accident.
2. **A code face at hero size.** The digits are 0.6 em advance — condensed,
   mechanical, tabular. Blown to 160 px this is literally "a terminal screenshot
   scaled up", the exact read the brief exists to prevent.
3. **The annotations align to nothing.** `· Retry-After` baseline y = 696 sits
   at the numeral's *mid-height*; `Retrying · attempt 3/8` baseline y = 732 sits
   **12 px below the numeral's baseline (720)**. Neither line touches the
   numeral's cap-line or baseline, so the pair floats.
4. **The two annotation lines are optically misaligned with each other.** Both
   start at x = 478, but line 1 begins with `· ` (a mid-dot with wide
   sidebearings) and line 2 with `R`. Line 1 reads as indented by ~14 px.
5. **The rule is shorter than the block it caps.** Rule runs x 160 → 760;
   `Retrying · attempt 3/8` runs to x ≈ 821. A rule that under-runs its own
   content by 61 px looks like a bug.

**Fix.**
* Set `503` in **SFNS at 176 px, weight 700, tracking −4 px** (or New York
  Bold), not JetBrains. If it must stay mono, JetBrains Mono has no dotless-zero
  variant here — so it can't stay mono.
* Align the annotation pair to the numeral: baselines **y = 684 and y = 720**,
  so line 2 shares the numeral's baseline exactly. That single change turns two
  stray lines into a lockup.
* Drop the leading `· ` from line 1 (make it `Retry-After`) so both lines start
  on the same optical edge at x = 478; move the separator dot into the gap as a
  drawn 4 px dot at x = 462 if it is load-bearing.
* Extend the rule to **x = 160 → 860**.

---

### 6 · The off-country contact breaks the mark's silhouette

**Frames:** f750–f944 (C1, C2-right, C3) and f1056–f1061 (D1). Clearest at
f760, f830, f920 and in `s_M3.png` f751–f755.

`off-country blip base (72, 32)` is at radius **28.4 units** from the hub; the
ring's inner edge is at **30.0**. The blip itself is r = 5 u, so it reaches
33.4 u — *the ring's centreline* — and the halo (`r = 5 + hp·9`, up to 14 u)
reaches **42.4 u**, i.e. 6.4 units (27 px) **outside the mark's outer edge**.

On screen the bright amber dot sits directly on the ring, obliterating a chunk
of it, and a dark halo bubble hangs off the ring's 1:30 like a magnifying-glass
handle. The mark stops being a circle. In C2 (f830) this is fatal: the two marks
are supposed to be the *same object*, and one of them has a lump on it.

**Fix.** Move the contact inboard and cap the halo so the whole state lives
inside the ring:
* contact base `(72, 32)` → **`(68, 35)`** (radius 23.4 u)
* halo `r = 5 + hp·9` → **`r = 4 + hp·2`** (max 6 u ⇒ outer extent 29.4 u, just
  inside the ring's 30.0 inner edge)
* keep `lunge = 6` — closest approach becomes 17.4 u against a fence at 15.0,
  so "it never gets in" is preserved with 2.4 u of margin.
* the ray endpoint follows: `(72,32)` → `(68,35)`.

---

### 7 · The grain is visible, it lifts the black, it loops every 12 frames, and it costs 160 MB

**Frames:** any. See `z_field_1to1.png` (a 1:1 800 × 400 crop of empty field
at f5) — the mottle is obvious without looking for it. FILM §2.9 says it "must
be invisible when you look for it".

Measured on the flat field: mean **13.6, 13.6, 15.5** against an `INK` of
`12, 12, 14`; std **3.0**; range **10 … 25**. On 8 × 8 block averages of an
entirely empty frame the low-frequency variation runs **12.0 … 19.2**. On a
near-black field a +13 excursion is enormous.

Root cause is in `draw.py:65–88`:
* `np.clip(np.abs(n) * amount * 5.0, 0, 14)` — **`abs()` makes the grain
  half-normal and strictly additive**, so it can only ever lift the field. The
  darkest pixel in the film is 10 and the *mean* field is 1.6 luma above
  `#0C0C0E`. craft §9.27 wants `#0C0C0E ± 2`; the film's blacks are grey.
* amplitude 5.0 with a clip at 14 is roughly 3× what banding suppression needs.
* the plate is generated at `(H//2, W//2)` and upscaled with `Image.NEAREST`, so
  the grain is **2 × 2 blocky** — it is chunky digital noise, not film grain.
* only **12 plates**, cycled by `i % 12` → the texture repeats every 0.4 s. The
  eye locks onto a 0.4 s loop; it reads as a dirty overlay.

It also dominates the encode: **160.8 MB for 40 s = 32 Mbit/s** on a film that
is 98 % flat black.

**Fix (`draw.py:65–88`):**
* drop `np.abs()` — use signed `n` so the grain is zero-mean and the field stays
  on `#0C0C0E`. That needs the plate composited as an add/subtract rather than
  an alpha-white overlay; the simplest correct version is a signed `int16` add
  on the numpy array before `Image.fromarray`.
* amplitude `5.0 → 1.8`, clip `14 → 4`.
* generate at full `(H, W)`, or keep half-res but resample `Image.BILINEAR`.
* plates `12 → 30` (a 1 s loop is below the perceptual lock threshold).

Expect the deliverable to drop to ~25–40 MB at the same CRF.

---

### 8 · The film's "structural match cut" (B2, f420) does not match

FILM §1 and §4.6 stake the whole B-act on this: *"the mark left frame at f329 in
`clear` at (1290,540)/420 px and returns at f420 in `clear` at (1290,540)/420 px
— bit-identical geometry across 90 frames of type."*

**It is not.** Measured pulse-ring radius (median radius of lit interior pixels,
excluding the outer ring):

| frame | pulse |
|---|---|
| f327 / f328 / f329 | **invisible** — only the three blips are lit (n = 2284 px) |
| f420 | **r = 59.5 px**, fully lit (n = 6317 px) |

Per-pixel diff of the 420 × 420 mark box between f329 and f420: **17 576 pixels
differ by more than 20** (grain-only baseline, measured on the static f1180 /
f1181 pair, is max 13). You leave the shot on a bare ring and cut back to a ring
with a large grey circle inside it. The device — the one thing that was supposed
to make the B act feel engineered — is simply absent.

**Fix.** Make the pulse phase-coincident across the gap. The gap is
**91 frames**; `91 = 7 × 13`, so set the `clear` pulse period to **91 frames
(3.033 s)** — currently 71.4 f, driven by `pr = ((f - PULSE_BORN)/30.0 * 0.42) %
1.0` at `scene_open.py:614`. Change the `0.42` rate to `30/91 = 0.32967`. f329
and f420 then land on identical phase and the cut becomes a real match cut.

Secondary but related: because the pulse is *invisible* for part of every cycle
(f327–f329 vs f300), the `clear` state has two different silhouettes over a
75–90 frame hold. Give the pulse a floor of α ≈ 0.12 at max radius so the mark
never changes identity while it is being held.

---

### 9 · The end card: the mark is exactly cap-height, so it reads as a button, and `TOWER` is unkerned

**Frames:** f1160, `out/tower-film-poster.jpg`, `z_tower.png`.

**(a) The mark reads as a shirt button / camera lens, not a radar.** Measured
bbox at f1160: **144 × 144 px**, centred (960, 340). New York's cap height at
200 px is ≈ 143 px. So the mark is **exactly the same height as the letters**,
which makes it read as a sixth character stacked above the word — and because
D2 uses the `clear` pose at frozen still values, there is no needle, no sweep,
no direction: just a thick white annulus, a grey inner ring (the frozen pulse at
r = 22 u) and three white dots. That is a button with three thread holes. On the
poster frame it is unmistakable.

Fix: take the box **200 → 280 px** (visual Ø ≈ 202, i.e. 1.4× cap height), and
either drop the frozen pulse ring (it is what creates the second concentric
circle that makes it a button) or use the **`verify` still pose** so the needle
gives the mark an axis.

**(b) `TOWER` is set on flat +12 px tracking with no optical correction.**
Measured inter-glyph gaps at f1160: **T|O 24, O|W 20, W|E 18, E|R 25** px. In a
high-contrast serif the optical requirement runs the other way — `O|W` (round
against diagonal) opens the biggest hole and `W|E` (diagonal terminal against a
flat stem) closes the tightest. The word currently reads "TO WER" with a lump at
`WE`. Apply per-pair deltas on top of the +12 track: **T|O −8, O|W −8, W|E +8,
E|R 0** (targets 16 / 12 / 26 / 25).

**(c) The vertical rhythm has no system.** mark bottom 411 → wordmark cap top
≈ 516 (105) → tagline baseline 744 (84 below the wordmark baseline) → url 852
(108). Three near-identical gaps for three different hierarchical distances.
Set them on a ratio: mark→wordmark **140**, wordmark→tagline **96**,
tagline→url **132** (i.e. baselines 660 / 756 / 888, all on the 12 grid), so the
mark+wordmark lock up and the url clearly detaches.

---

### 10 · The Layout-M type scale is one tier too small for a film

The state label is **mono_bold 24 px** (cap height ≈ 17 px = **1.6 % of frame
height**); the readout is **26 px mono** (x-height ≈ 13 px = 1.2 %); the caption
is 36 px SF. See f230, f300, f480, f580, f660, f760, f920, f1000.

That is UI-caption sizing dropped into a 1920 × 1080 film. On a phone or at
480p it is unreadable; on a TV it reads as fine print in the corner of a black
frame. It is also the direct cause of the 1.6 % ink figure in §2.

**Fix.** Take the whole Layout-M tier up one step and re-space on the 12 grid:

| role | today | change to |
|---|---|---|
| state label | mono_bold 24, track +3.4 | **mono_bold 34, track +4.8** |
| caption | ui 36 wght 400 | **ui 48 wght 400** |
| readout | mono 26 | **mono 34** |
| baselines | 444 / 516 / rule 576 / 612 / 648 | **432 / 528 / rule 600 / 648 / 696** |

This alone roughly doubles ink coverage in the eight Layout-M shots and closes
part of the centre hole from the left.

---

### 11 · D1's `holdGeo → off` is a cross-fade, and f1074–f1075 puts a red core inside a white ring

**Frames:** `s_D1.png`, f1062–f1067 and f1074–f1075.

* **f1062**: the red dashed ring is already drawn *while the amber fence, ray,
  contact and halo are still ghosting underneath at partial alpha*. Two finished
  pictures superimposed in one frame. FILM §1 asserts "There is not one
  cross-dissolve in this film"; this is one, and it is on the failure state,
  which is the one place the film promised a sober channel-by-channel morph
  (M4).
* **f1074 / f1075**: the ring has already recoloured to white/cream while the
  core is still saturated **red**. Two hues in one frame, against FILM §4.13's
  "One hue at a time, always" and §2.6's "distinct accent hues in any frame ≤ 1".
  It reads as a healthy ring with an error dot in it — semantically backwards.

**Fix.** In the D1 morph table (`scene_end.py`), interpolate the geo group's
*geometry* rather than its alpha: shrink the fence radius 15 → 0 and retract the
ray over the same 6 frames so nothing is ever double-exposed. And **lead the
core, don't trail it** — recolour core and ring on the same eased `k` (today the
core lags by ~2 frames), so f1074/f1075 are a single interpolated hue.

---

### 12 · The release (M5) does the right thing invisibly

**Frames:** `s_M5.png`, f960–f974.

FILM §M5's best sentence is "the fence expands r 15 → 33 and is absorbed into
the outer ring". Measured, it *does* travel — median radius of the fence pixels
goes 58.2 (f959) → 64.2 (f960) → 70.8 (f961) → 75.2 (f962) → 81.4 (f963). But
the alpha collapses faster than the radius grows: by f962 the fence is a grey
smudge and by f964 it is gone, having covered barely a third of its journey
while still legible. Watching it, you see a cross-fade, not an absorption.

**Fix.** Hold the fence at **α ≥ 0.75 until it reaches r = 28 u**, then dump
alpha to 0 over the last **3 frames** as it merges with the ring at r = 33.
Same total 15 f; the travel becomes the story instead of the fade.

---

### 13 · The 1 px hairline rule is below the noise floor

**Frames:** f230, f300, f480, f580, f760, f920, f1000. See `z_rule.png`.

`HAIRLINE = #242426` (`brand.py:56`) is luma 36 against a field whose grain
already peaks at 25. A 1 px line at Δ11 over a mottled background, then
chroma-subsampled by x264, is effectively invisible — at 1:1 it reads as a
compression artefact. It is the only element in Layout M with an edge, and it is
doing no work; the copy column has no floor.

**Fix.** `#242426 → #34343A` at 1 px (Δ ≈ 30 over field), *or* keep the colour
and go to 2 px. Do not do both. And extend it to x = 860 so it caps the widest
line in every Layout-M shot (see §5).

---

### 14 · Layout H sits high and does not rhyme with Layout M

**Frames:** f140 (A2), f380 (B1).

Kicker baseline 360, hero baseline 480. The type block's mass centre is at
y ≈ 420 against a frame centre of 540, and **everything below y = 500 — 54 % of
the frame height — is empty**, plus everything right of x ≈ 950. The block
floats in the upper-left with nothing anchoring it.

It also doesn't rhyme with anything: Layout M's label sits at 444 and its
caption at 516, so cutting A2 → A3 the eye jumps 84 px for no reason.

**Fix.** Move Layout H down onto Layout M's spine: kicker baseline **444**, hero
baseline **564** (both on the 12 grid, mass centre y ≈ 504 ≈ the optical
centre). Combined with the x = 260 column move from §2, A2 and A3 then share a
left edge and a first baseline, and the cut at f180 becomes a genuine rhyme.

---

### 15 · Smaller things, worth doing

* **f1000 — `allowed 124200`.** A bare six-digit counter with no unit and no
  context is debug output. It is the single most "dev tool screenshot" string in
  the film. Either give it a noun (`124,200 requests allowed`) or cut it and let
  `Toronto, CA — inside CA` stand alone; the shot does not need a second line.
* **f810 / f830 — the dimmed mark keeps a neutral core.** The frozen `holdGeo`
  side runs at α 0.45 but its core is neutral `#E7E6E2`, so at 45 % it is a cool
  grey dot inside a warm amber mark — the **brightest, coolest, most
  eye-catching thing on the side that is supposed to be quiet**. Tint the core
  toward the amber when the mark is dimmed (mix 40 % `AMBER` at α < 0.6), or
  drop the core's alpha to 0.30 while the rest sits at 0.45.
* **f533–f539 — a 7-frame hole in the `holdNet` arrival.** The blips have gone
  to 0 and ping #1 does not fade in until f540, so for seven frames the mark is
  a hollow crown with one dot in it. Bring ping #1's entrance forward to **f534**
  so the interior is never empty; the "sonar doubles up a beat later" idea
  survives at 0.13 s instead of 0.20 s.
* **f970–f971 — the needle emerges as a keyhole.** The round hub cap plus a 3 u
  stub reads as a keyhole / exclamation mark for two frames. Start the needle's
  draw-on from length 6 u at α 0 rather than length 0, so it is never shorter
  than its own cap.
* **f1044–f1073 — the D1 poses are 6 frames (0.2 s) each.** With three of the
  five states now rendering as crowns (§1), the recap reads as a UI test harness
  cycling states. Once §1 is fixed this mostly resolves; if it still strobes,
  take the poses to 8 f and the morphs to 4 f (same 60-frame budget).
* **Optical left alignment.** `x = 160` is used as the advance origin for mono,
  SF and New York alike. At f300 the `C` of `CLEARED` (mono), the `C` of
  `Confirmed` (SF) and the `T` of `Toronto` (mono) do not share an optical left
  edge. craft §9.15 asks for `font.getbbox()` correction; apply it — at these
  sizes it is 2–6 px, which is exactly the amount that reads as "sloppy" without
  the viewer knowing why.

---

## What is already excellent — do not break these

* **Safe-area discipline is perfect.** Max luma anywhere in the 96 px action-safe
  ring is **27** across every frame sampled (f80, f140, f230, f300, f480, f580,
  f660, f760, f830, f920, f1000, f1045, f1160) — that is grain, not ink. Zero
  clipping, zero bleed. This is the single biggest improvement over the old film
  and it is flawless.
* **The mark never scales.** Measured bbox is **304 × 304 px, constant**, at
  f80, 300, 420, 520, 524, 530, 536, 545, 580, 614, 660, 760, 920, 1000, 1045,
  1060 — across every state and every morph. No pop, no drift. Protect this when
  resizing per §2.
* **The C1 readout relay (f716–f741, `s_relay.png`) is the most expensive-looking
  thing in the film.** `Toronto, CA — inside` fades out f720–727, the slot sits
  empty with only ` CA` holding at full opacity f724–727, and
  `Tehran, IR — outside` fades in f729–735 — the trailing `CA` never moves, never
  dips, never shifts by a pixel. It is a real relay, uniformly faded, with no
  cross-dissolve. Do not touch it.
* **f528–f532, the ring breaking into long arcs.** Five frames of genuinely
  premium animation. §1's fix is really just "make the end state look like
  frame 531".
* **f1050–f1051, the ring re-knitting** (broken → solid, holdNet → holdGeo).
  The best two frames in D1 and the one place the film's thesis lands in motion.
* **The hero type (f140, f380).** New York 120 px at −1.2 px tracking on
  `#0C0C0E` is genuinely beautiful — weight, colour and measure are all right.
  The problem is *where* it sits (§14) and *how it arrives* (§3), never the
  setting itself.
* **The `off` gap (f615–f620).** Six frames of true empty field before the mark
  fades up. Clean, brave, and it works. Keep it exactly as it is.
* **The vignette.** Measured centre-to-corner falloff is 15.9 → 13.8 luma,
  ~13 %. Invisible, well under the 0.35 cap. `draw.py:51` is fine — do not
  touch it while fixing the grain above it.
* **Anti-aliasing on curves.** The ring at 4× zoom (`z_a1_f35_mark.png`) is
  clean, with correct radial butt caps on the draw-on arc and no stair-stepping.
  The supersample-and-LANCZOS pipeline is working.
