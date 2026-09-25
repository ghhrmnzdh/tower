# review-motion.md — ANIMATION & THE ICON STATES

Review lens: the user's two most emphatic requirements —
**"the different icons of the app showing different stages is very important"**
and **"the whole transition and everything should have very premium animation."**

Method: all 1200 frames extracted from `out/tower-film.mp4` with ffmpeg
(`/private/tmp/.../scratchpad/qa_motion/full/`); consecutive-frame contact
strips of the mark at native 420 px through every morph; per-frame radial
profiles of the mark (ring radius, ring dash coverage, ring hue R−B / R−G, core
fill, fence coverage, ornament coverage) computed off the lossless masters in
`out/frames/`; a whole-film grain-suppressed motion profile (box-blur σ3,
per-frame Δ). Every claim below is a measurement plus frames I looked at.

**Verdict: FAIL on both requirements, with three genuinely excellent
sequences that must survive the fix.**

The five states *are* all present and individually labelled at hero scale
(f180–254 `VERIFYING`, f255–329 `CLEARED`, f510–614 `HOLD · CONNECTION`,
f615–689 `UNGUARDED`, f690–779 `HOLD · LOCATION`) and holdNet *is* directly
contrasted against holdGeo (C2, f780–869). That structure is right. But the
identity ring is visibly broken in `holdGeo` for 3 seconds straight, the
five-state recap that is supposed to *prove* the icon system is a slideshow of
1-frame pops, and 28 % of the film has literally zero motion.

---

## RANKED FINDINGS

### 1. `holdGeo`'s outer ring is visibly broken by the off-country contact — for 189 frames, including all 91 frames of the film's payload shot. **This destroys the film's thesis.**

**Frames:** f727–779 (C1), **f870–960 (C3, the `503` / PENDING shot — 3.03 s
unbroken)**, f1050–1062 (D1). Look at `zoom_900.png`: at f900 the amber contact
blob is *fused into* the outer ring at 1–2 o'clock and its halo cuts a dark
crescent bite out of the ring's inner edge. Measured: minimum luminance inside
the ring stroke band (r 128–148 px, intact = 229) drops below 160 on all 189
frames; at f770 the least-squares circle fit residual rises from 0.08 px
(clean) to 1.28 px.

**Why it is fatal, not cosmetic.** FILM.md §3/M3 states the thesis in one line:
*"ring dash: solid — **it does NOT break**. holdNet breaks the ring; holdGeo
does not."* On screen, holdGeo's ring **does** break — visibly, in the same
amber, at hero scale, for three seconds, on the one shot the film calls its
honesty payload. C2 then spends 90 frames teaching a difference that C3
immediately contradicts. The single most important icon distinction in the film
is unreadable.

**Geometry, exactly.** `scene_hold.py:243` `_RAY_END = (72.0, 32.0)` → 28.4
units from the hub. The ring spans r 30.0…36.0 units. The contact is
`5.0 * s`, `s = 1 + 0.16·sin(P·3)` → up to 5.8 units, so its outer edge reaches
**34.2** — 4.2 units *inside* the ring stroke. The halo is
`hr = 5 + hp·9` → 14 units, reaching **42.4**, right through and past the ring.
There is no frame on which they do not collide.

**Fix.** Move the contact inboard and cap the halo, in both copies:
* `scene_hold.py:243` — `_RAY_END = (66.5, 37.5)` (offset (16.5, −12.5),
  d = 20.7; contact edge 26.5 = 3.5 units clear of the ring).
* `scene_hold.py:488` — halo `hr = _lerp(8.0, 5.0 + hp * 4.0, amp)` (max 9 →
  reach 29.7, just inside the ring's inner edge at 30.0).
* `scene_hold.py:487` — `lunge = 4.0 * (...)` so closest approach is
  20.7 − 4.0 = 16.7 against a fence at 15 — still "it never gets in", and
  §M3's `d = 22.43` claim in FILM.md must be re-stated as 16.7.
* `scene_end.py:442, 481, 482, 774` — the same `72.0, 32.0` literals are
  duplicated four times in the D1 run; change all four or D1 and C1 will
  disagree.

---

### 2. D1's five-state run (f1020–1079) is not animated. Every "morph" is a 1-frame pop.

This is the shot that exists solely to satisfy *"the different icons showing
different stages"*, and it is a slideshow.

`EASE_SNAP = bezier(0.22, 1.00, 0.36, 1.00)` has `y1 = y2 = 1.0`, so it reduces
to `1 − (1−u)³` — an extreme ease-out. Sampled at `BEAT = 6` frames
(`scene_end.py:840`, five intervals) it yields
**k = 0, 0.676, 0.918, 0.983, 0.999, 1.000.**
68 % of every state change happens on the first frame; frames 3, 4 and 5 of
each six carry 1.7 % between them and are visually dead. `EASE_SOBER` at the
same beat gives 0, 0.488, 0.784, 0.929, 0.988, 1.0 — barely better.

Measured, from the mark's channels (see `s_D1a/b/c.png`, every frame f1024–1083
looked at):

| f | what should happen over 6 f | what actually happens |
|---|---|---|
| **1038** | verify → holdNet: the ring breaks | ring hue R−B goes 0.9 → **133.6 in one frame** (83 % of the 161.5 travel); dash coverage 1.000 → 0.738 in one frame. Whole-frame p999 Δ = **214** — larger than every scripted cut in the film except f90/f180/f1080. It is a cut in the middle of a shot. |
| **1050** | holdNet → holdGeo: **"the one to get right… the only place the ring re-knits"** | coverage 0.479 → **0.795** on f1050, 0.939 on f1051, solid by f1052. Three frames, and because `lerp(on)` grows hyperbolically the 24 dashes collapse straight into 4 giant arcs (f1050) then 2 (f1051) — it reads as a glitch, not a knit. FILM.md: *"If the viewer's eye catches it, the film has landed."* It cannot. |
| **1062** | holdGeo → off | R−G 57.2 → **134.2 in one frame** (85 %); fence/ray/contact vanish entirely between f1062 and f1063; core hollows in 2 frames (core0 229 → 20 → 16). |
| **1074** | off → clear | p999 Δ = 208 on f1074 and 213 on f1075. |

**Fix (two parts, both small).**
1. `scene_end.py` — stop using a pure ease-out at 6 frames. `brand.py:240`
   already defines `EASE_IN_OUT = bezier(0.42, 0.00, 0.58, 1.00)`, which at
   BEAT = 6 gives 0, 0.16, 0.50, 0.84, 0.97, 1.0 — a real S-curve with no
   overshoot, therefore still legal on `off`/hold entries. Swap `EASE_SNAP` and
   `EASE_SOBER` for it in the beat table at `scene_end.py:830–838`.
2. Rebalance the beats. 6 f morph / 6 f pose is backwards: the *change* is the
   subject, the pose is not. Make it **9 f morph / 3 f pose**, which needs 60 f
   for five morphs + five poses only if D1 grows to 60 → keep 60 f by using
   9/3 for the four interior beats and 6/6 for the bookends, or take 30 frames
   from D2's dead tail (finding 4) and run D1 at 90 f with 12 f morphs. The
   second is strongly preferred: it is free, and it is the shot the user asked
   for.

---

### 3. Semi-transparent ornaments punch holes through the ring — a Pillow compositing bug, 4 places.

`_ring()` draws with `d.ellipse(box, outline=_rgba(colour, alpha), width=w)` on
a draw context created as `ImageDraw.Draw(im)` (`scene_open.py:436`,
`scene_wire.py:460`, `scene_end.py:725`). On an RGBA image that **replaces**
the destination pixel instead of blending it. So an ornament at alpha ≈ 0.03
crossing the opaque outer ring sets those pixels to alpha 8/255 — it *erases* a
band out of the ring.

**Frames:** f28–31, **f320–329**, **f463–475**, f530–533. See `zoom_470.png`
(f470, 4× zoom): a hard-edged dark hairline runs around the inside of the ring,
splitting it into two contours. Radial profile at f474: r 126–133 = 229,
**r 134–144 = 20**, r 145–150 = 229 — an 11 px hole travelling outward through
the stroke and popping out at f476. In `clear`, the film's baseline state, the
mark grows a doubled/lumpy edge once every 0.7 s.

`scene_hold.py` composites each element into its own layer (`:266`) and is
clean — 0 punctures in f690–1019. That is the correct pattern.

**Fix.** One character, three files: `ImageDraw.Draw(im, 'RGBA')` at
`scene_open.py:436`, `scene_wire.py:460`, `scene_end.py:725`. Then re-run the
puncture check (min luminance in r 128–148 must stay ≥ 200 on every frame where
a ring exists).

---

### 4. 335 of 1200 frames — **27.9 % of the film — contain zero motion.** Plus 1.4 s of pure black.

Grain-suppressed frame-to-frame delta, dead runs:

| frames | dur | what is on screen |
|---|---|---|
| f0–11 | 0.40 s | **black** |
| f90–107 | 0.60 s | **black** |
| **f122–179** | **1.93 s** | "Where you are." — completely frozen |
| f330–335 | 0.20 s | **black** |
| **f350–419** | **2.33 s** | "How the wire is." — completely frozen |
| f615–620 | 0.20 s | **black** (spec'd gap — legal) |
| f631–689 | 1.97 s | `off` pose (spec'd still — correct) |
| f1067–1073 | 0.23 s | `off` pose (correct) |
| **f1096–1122** | **0.90 s** | end card frozen |
| **f1133–1199** | **2.23 s** | end card frozen |

Two 2-second dead type cards in the first half and a 3.1-second dead end card
is a screensaver, not "completely exciting". D2 alone is dead for 94 of its 120
frames; FILM.md §4.14 asked for 24 static frames at the end and got 67.

**Fix.** Steal from the dead and give it to the states:
* trim A2 to f90–149 (60 f) and B1 to f330–389 (60 f) — the reading floor is
  satisfied at ~40 f full-opacity and both currently hold ~58 and ~70;
* trim D2's tail to f1080–1169 (90 f, still 24 static frames at the end);
* spend the recovered 90 frames on D1 (finding 2) and on real motion inside
  C2 (finding 5). No new shots, no new copy.

---

### 5. C2 (f780–869) never shows holdNet and holdGeo at equal weight, and the swap between them is a literal two-way cross-dissolve.

Measured peak amber R inside each mark (full amber = 230):

```
f788–f834   left(holdNet) = 249   right(holdGeo) = 122     (49 %)
f836        207 / 163
f838        153 / 216
f840–f869   128 / 241  →  123 / 248                        (49 %)
```

So the shot that exists to let the viewer *compare* the two states dims one of
them to half for its entire length, and the A→B handover at **f836–840** is
two elements moving in opposite directions simultaneously over 5 frames —
which is a cross-fade, the one device FILM.md §1 swears the film contains none
of ("There is not one cross-dissolve in this film"). It is also un-staggered
(two ideas animating in the same frame, §2.8) and lands at f836/f838, not on a
multiple of 15.

Consequence for the user's requirement: at no instant in the film are the
broken ring and the solid ring legible side by side at the same weight. The
comparison is asserted, never made.

**Fix.** Hold both marks at full weight for the whole shot and animate the
*labels* instead — the label under the focused mark goes `#E6A93C`, the other
`#6E6E6A`, relayed one at a time (out 8 f `EASE_EXIT`, then in 8 f
`EASE_SOBER`, first-in ≥ last-out + 1) at f810 and f840. That satisfies
Amendment B's RELAY rule, removes the cross-fade, and keeps both geometries
readable throughout. Also raise the two marks from 216 px to ~260 px (the hero
mark is 304 px) — the ring/dash difference is the payload and it is currently
carried at 71 % of hero size.

---

### 6. M1 `verify → clear` (f262–276) is spec'd at 15 frames and is over in 4 — and the needle reads as a broken stub while it happens.

Measured ornament coverage inside the mark: f261 = 0.2361, f262 = 0.2237,
f263 = 0.2319, f264 = 0.1701, f265 = 0.1345, f266 = 0.1331, then flat. The
retraction is 3 frames wide and finished 10 frames before the morph's nominal
end; frames 267–276 are dead.

Worse, look at `s_M1.png` f262–264: the newborn `clear` pulse ring is drawn at
r ≈ 8 units directly on top of the needle's hub disc and two blips, and the
needle — which is supposed to *retract into the hub* — instead shortens from
the hub end, leaving a fat white lollipop stub pointing down-left with a
leftover dark wedge behind it. Three frames of visual mud on the film's first
state change.

**Fix.** In `scene_open.py`, drive the needle length by the *same* 15-frame
`SETTLE` progress the ring uses (`_m1k`), retracting **tip → hub** (scale the
end point toward the hub, not the start point away from it), and delay the
pulse birth to k ≥ 0.35 (≈ f267) so it is not born inside the needle head.
Fade the wedge on the same 15 f rather than 3.

---

### 7. The `clear` pulse and the `holdNet` pings are born at full opacity — a hard pop every 0.7 s, six times, uncut.

`scene_open.py:614` `pr = ((f − PULSE_BORN)/30 · 0.42) % 1.0`;
`alpha = max(0, 1 − pr) · 0.5`. At `pr = 0` alpha is **0.5 instantly**. Measured
births (>60 luminance appearing in the r 8–12 unit band in one frame):
**f477, f540, f561, f583, f604, f715, f1076** (f420 is masked by a cut).
At f477 a ring at lum 123 appears where the previous frame had 16.

f540/561/583/604 are all inside B3 — i.e. the film pops four times during the
`HOLD · CONNECTION` beat, which is exactly where nothing may bounce or flash.

**Fix.** Gate the birth: `a = 0.5 * (1.0 - pr) * _clamp01(pr / 0.15)` — a
4.5-frame fade-in, still a pure function of `f`, still deterministic. Apply in
`scene_open.py:615`, `scene_wire.py` `_spec_clear_to_holdnet` (`a0`, and `a1`
for ping #1), `scene_hold.py` `_pulse_clear`, `scene_end.py` pulse.

---

### 8. The hero type reveal is a 1-frame flash followed by a 10-frame staircase, not a 13-frame eased envelope.

Ink in the hero line, per frame:

```
A2  f110:  15 → f111: 730  (+715 — 22 % of the final 3302 in ONE frame)
    then  +442 +263 +245 +138 +308 +370 +191 +278 +250 +80, done at f121
B1  f338:  16 → f339: 680  (+663)
    then  +454 +193 +443 +304 +305 +364 +293 +164 +258 +88, done at f349
```

Two defects. (a) There is **no ease-in at all** — the leading characters arrive
at near-full weight on a single frame. (b) The velocity is non-monotonic
(+193 then +443 then +304 in B1; +138 then +308 then +370 in A2) — a 2.3×
swing between adjacent frames. That is judder; a per-char stagger of 0.78 f
under a 13 f `EASE_ENTER` envelope produces a smooth bell, and the total span
would be ~23 f, not 11.

**Fix.** The per-character envelope is collapsing to ~1 frame. In the
`draw_kinetic` path used by A2/B1, make each character's alpha
`EASE_ENTER(clamp01((f − start_i) / 13.0))` with `start_i = f0 + i·0.78`
(float, no rounding — rounding the per-char start to integers is what produces
the staircase), and rise `0.14 em` on the same curve.

---

### 9. f1026 — a one-frame empty pose in the middle of the five-state run.

Ornament coverage: f1025 = 0.1503 → **f1026 = 0.0532** → f1027 = 0.2204. On
f1026 the `clear` pulse has already been culled and the `verify` needle and
wedge have not yet appeared; the mark is a bare ring with three blips — a state
that does not exist in the product. The next frame the needle and wedge appear
at 92 % of final size (p999 Δ = 165). FILM.md §4.3: *"Nothing is ever
half-there."* This is worse — it is nothing-there, then everything-there.

**Fix.** Falls out of finding 2 (S-curve + longer morph) plus: cross the two
channels — the pulse's alpha must reach 0 on the same frame the needle's length
leaves 0, not two frames earlier. `scene_end.py`, the `clear`→`verify` beat at
`:830`.

---

### 10. The grain is animated hard enough to be the busiest motion in the frame.

Empty field (300×500 px sample, f600/f601): mean 15.97, σ 3.07, **mean
frame-to-frame |Δ| = 3.22/255, 38.8 % of pixels change by >3 levels every
frame.** Over a #0C0C0E field that is visible crawl, and it is why the master is
160 MB for 40 s. FILM.md §2.9 requires the grain to be "invisible when you look
for it". It is not — on a dark, near-empty, mostly-still film it is the only
thing moving for 335 frames.

It also has a **12-frame loop** (the residual sum repeats exactly with period
12: 1843.3 / 1840.1 / 1840.4 / 1840.7 / 1835.6 / 1831.1 / 1847.9 / 1846.2 /
1843.1 / 1838.8 / 1837.2 / 1836.1), so it reads as a 2.5 Hz shimmer rather than
random noise.

**Fix.** In `make.py`'s `grain_layer`, drop the amplitude from ≤14 to ≤5 and
hold each grain field for **3 frames** (`i // 3`) instead of one — dithering
needs spatial noise, not temporal. Lengthen the loop to a prime (e.g. 37) so no
beat is audible to the eye.

---

### 11. f1062 puts two hues on screen at once, which D1's own spec forbids.

`s_D1b.png` f1062: the outer ring is already red (`R−G = 134`) while the fence,
ray and contact are still amber at reduced alpha, rendering as dark maroon-brown
inside it. FILM.md §4.13: *"One hue at a time, always… The amber→red morph
passes through a single interpolated orange — one hue, never two."*

**Fix.** In the `holdGeo → off` beat (`scene_end.py:836`), take the geo group's
alpha to 0 over frames 1–2 of the morph (8 f `EASE_SOBER` scaled to the beat)
*before* the ring's hue starts moving, i.e. stagger the ring hue to start at
k ≥ 0.3. Same idea as the correct stagger already used at f1074.

---

### 12. Minor / verify

* **f1041 dash coverage reversal.** holdNet ring coverage runs 0.523, 0.459,
  **0.450, 0.479**, 0.479 — a 5.6 %-of-travel excursion past the target and
  back, on an amber hold. `EASE_SNAP` cannot overshoot, so this is most likely
  dash-phase aliasing at the 6-frame beat, but it looks like a bounce and
  bounce on a hold is a hard violation. Re-measure after finding 2 lands.
* **f1064 hue overshoot on `off`.** R−G reaches 151.1 then settles to 149.7
  (1.5 % of travel). Under the 4 % cap, but it is on the strictest element in
  the film. Re-measure after finding 2.
* **C3's cut is blunted.** The film's biggest scale jump lands at f870, but the
  first copy (`PENDING`) does not appear until f877 and `503` not until f893 —
  7 and 23 frames of a bare mark after the cut. Pull `PENDING` to f872.
* **Scale.** Hero mark ring Ø = 304 px (28 % of frame height); C2 = 216 px;
  D2 = 144 px (13 %). The recap (D1) is at hero size but carries no label, and
  the two smallest presentations are the comparison shot and the sign-off. If
  "the icons showing different stages" is the point, C2 should be ≥ 260 px.

---

## DO NOT BREAK — these four are genuinely excellent

1. **A1's ring draw-on, f11–47.** Arc coverage velocity ramps
   +0.001 → +0.079 (peak at f30, exactly mid-span) → +0.002, perfectly
   symmetric, zero judder. A textbook `EASE_MOVE`. Leave it alone.
2. **M2 `clear → holdNet`, f525–539.** Ring hue R−B runs
   4.9 → 18.6 → 46.2 → 77.8 → 103.0 → 124.7 → 141.2 → 151.5 → 157.8 → 161.1 →
   161.6 → 161.5: a clean accelerate-then-decelerate bell with 0.06 %
   overshoot. The ring genuinely *breaks into segments* over 11 visible frames.
   This is what every other morph should be measured against.
3. **M3 `clear → holdGeo`, f720–750** (`s_M3a.png`, `s_M3b.png`). The best
   sequence in the film: the ring's hue lerps over 7 visible frames, the
   `clear` pulse *contracts* inward and locks at r = 15 while its dash breaks
   progressively (solid arc f723 → 2 arcs f726 → 4 arcs f727 → 8 f728 →
   14 f731), and the ray then draws outward from the hub over ~9 frames. One
   ring genuinely becoming another. Real geometry interpolation, not a
   cross-fade. Protect this exactly as-is (only the contact position in
   finding 1 changes).
4. **M5 `holdGeo → verify`, f960–979** (`s_M5a.png`). The fence expands
   r 15 → 33 and is absorbed into the outer ring while its colour lerps
   amber → neutral, then the needle draws back out of the hub and the blips
   arrive staggered 3 f apart at f972–975. It reverses M3 exactly, and it
   reads as automatic recovery, which is the honest semantic.

Also correct and worth keeping: **B4's `off`** — 6 empty frames (f615–620),
then an 8-frame `EASE_SOBER` opacity-only fade-up (f621–628: 30 %, 45 %, 65 %,
80 %, 90 %, 95 %, 98 %, 100 %), then **dead still from f631 to f689** (verified:
zero change beyond grain). Failure does not bounce. The same is true of D1's
`off` pose f1068–1073. And the mark's core geometry is sub-pixel exact
everywhere — least-squares circle fit gives r₀ = 138.62 px with centre offset
0.00 px and residual σ = 0.08 px on every clean frame.

---

## ONE-LINE SUMMARY FOR THE FIXER

Fix 1 (contact/ring collision) and 3 (RGBA compositing) first — they are small,
mechanical, and together they repair the icon system's legibility. Then 2 and 4
together: take the dead frames out of A2/B1/D2 and spend them on D1's morphs
with a symmetric ease. Those four changes turn a slideshow into the film it is
already 60 % of the way to being.
