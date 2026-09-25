# FILM.md — Tower, 40 s, fully synthetic

**This document is the authority.** Four engineers build four scene modules in
parallel without talking. Everything they need to agree on is fixed here: the
frame budget, the grid, the type scale, the mark's screen circle, the easing
tokens, the copy, and the audio hit list. If an implementation detail is not in
this file, it is not in the film.

| | |
|---|---|
| Master | 1920 × 1080, sRGB, opaque RGB, 30 fps |
| Length | **exactly 1200 frames = 40.000 s** |
| Source material | **none.** Every pixel is drawn in Pillow 10.1 + numpy 1.26 |
| Encode | ffmpeg 7.0.1, `libx264 -crf 16 -preset slow -pix_fmt yuv420p -x264-params aq-mode=3 -movflags +faststart` |
| Determinism | frame *N* is byte-identical every run and at every `-j`. No clock reads, no unseeded RNG, no neighbour-frame state |
| Ground notes | `notes/design.md` (the marks), `notes/ui-truth.md` (the product), `notes/craft.md` (the acceptance spec) |

The film has one argument, stated three ways:

> **Two independent things can go wrong — where you are, and how the wire is.
> Tower tells you which. Your turn goes PENDING, not FAILED, and it resumes on
> its own. Nobody restarts anything.**

And one identity device: **the radar mark is the state.** Ten of the fourteen
shots hold the mark on the *identical screen circle*, so every cut is a match
cut and the only thing that ever changes is the state. By the end the viewer
reads the icon alone.

---

## 1. THE FRAME BUDGET

14 shots. Four contiguous module ranges tiling 0…1199 with no gap and no
overlap. Every `in` point is divisible by 15 (craft §4.4). Every duration is
inside 36…165.

| # | id | module | in | out | dur | cut in | why that cut |
|---|---|---|---|---|---|---|---|
| A1 | `open.mark` | `scene_open.py` | 0 | 89 | 90 | open on field | The film starts on `#0C0C0E` and the ring draws itself onto it. No fade-up — a fade-up is a filter, a draw-on is an event. |
| A2 | `open.where` | `scene_open.py` | 90 | 179 | 90 | **hard cut** | Scale contrast ≥3× (a 420 px mark → a 120 px hero line). Both sides are <12 % ink so a dissolve would be *legal*; a cut is stronger and costs nothing. |
| A3 | `open.verify` | `scene_open.py` | 180 | 254 | 75 | **hard cut** | The mark returns to its canonical screen circle. The type disappears in one frame; the mark reappears in the same frame. Nothing is ever half-there. |
| A4 | `open.clear` | `scene_open.py` | 255 | 329 | 75 | **no cut — continuous morph** | A state change must be *seen changing*. Cutting between two finished pictures would be exactly the "cross-fade reads as slides" failure. §4 specifies the morph channel by channel. |
| B1 | `wire.how` | `scene_wire.py` | 330 | 419 | 90 | **hard cut** | Chapter break. Same device as A2, deliberately rhymed — but tighter (6 f of silence instead of 18): speed contrast, craft §6.6. |
| B2 | `wire.slow` | `scene_wire.py` | 420 | 509 | 90 | **hard cut** | **The film's structural match cut.** The mark left frame at f329 in `clear` at (1290,540)/420 px and returns at f420 in `clear` at (1290,540)/420 px — bit-identical geometry across 90 frames of type. |
| B3 | `wire.hold` | `scene_wire.py` | 510 | 614 | 105 | **no cut — continuous morph** | The first hold. It has to arrive *on the mark we have been watching*, or "the mark is the state" is a claim instead of a demonstration. |
| B4 | `wire.off` | `scene_wire.py` | 615 | 689 | 75 | **hard cut + 6 empty frames** | `off` is an absence. The only honest transition into an absence is a gap: 6 frames of empty field and the audio bed cut to true silence. A dip-to-field's payload without the fades. |
| C1 | `hold.geo` | `scene_hold.py` | 690 | 779 | 90 | **hard cut** | Back to the canonical circle in `clear`. The viewer must see the guard restored before it is taken away by *location* — otherwise `off` and `holdGeo` blur. |
| C2 | `hold.which` | `scene_hold.py` | 780 | 869 | 90 | **hard cut** | Layout change (one mark → two). A move or a dissolve would imply one mark split in two; a cut states "here are two things". |
| C3 | `hold.pending` | `scene_hold.py` | 870 | 944 | 75 | **hard cut — the film's biggest scale jump** | Return to the canonical circle, state unchanged (`holdGeo`, phase continuous). The cut carries no *state* information at all — it carries **scale**: 24 px labels become a 160 px `503`, 6.7×. It is the one cut in the film that changes the size of the world, and it lands on the honesty payload. |
| C4 | `hold.clear` | `scene_hold.py` | 945 | 1019 | 75 | **no cut — continuous morph** | The recovery must be visibly automatic. A cut here would let a viewer think someone intervened. Nothing may cut between the hold and its release. |
| D1 | `end.set` | `scene_end.py` | 1020 | 1079 | 60 | **hard cut (pure match cut)** | Every element except the mark vanishes on one frame; the mark is *bit-identical* across f1019/f1020. The cheapest, strongest device we own (craft §6.8). |
| D2 | `end.card` | `scene_end.py` | 1080 | 1199 | 120 | **hard cut** | The mark relocates and rescales. Only a cut may move it — craft §4.3 caps travel at 115 px and this is 330 px. |

**Module ranges (contiguous, tiling, no overlap):**

| module | frames | count | seconds | owns |
|---|---|---|---|---|
| `scene_open.py` | **0 … 329** | 330 | 0.000 – 11.000 | cold open + the fence lane (`verify`, `clear`) |
| `scene_wire.py` | **330 … 689** | 360 | 11.000 – 23.000 | the wire lane (`clear` held, `holdNet`) + `off` |
| `scene_hold.py` | **690 … 1019** | 330 | 23.000 – 34.000 | off-country → `holdGeo` → the contrast → PENDING → recovery |
| `scene_end.py` | **1020 … 1199** | 180 | 34.000 – 40.000 | the five-state run + the card |

`330 + 360 + 330 + 180 = 1200` ✓  ·  `90+90+75+75 = 330` ✓ · `90+90+105+75 = 360` ✓ · `90+90+75+75 = 330` ✓ · `60+120 = 180` ✓

**Major reveals land on multiples of 60** (craft §4.4): f720 (**the amber
HOLD · LOCATION arrival**), f960 (**the recovery**), f1020 (the five-state run).

*Do not claim more than that.* A2's and B1's hero lines reveal at f111 and f339 —
they are type entrances inside a shot, not structural reveals, and the reading
floor pins them where they are. Earlier drafts of this table asserted "f120 and
f360" as major reveals; nothing in §4 ever landed there and the assertion in §9
was passing on a tautology. The three landmarks above are the only ones the film
actually has, and all three are *state* events, which is the correct definition
of a major reveal in a film whose subject is a state.

**Scale contrast across a cut** (craft §6.5 wants ≥4 jumps of ≥3×). The film has
exactly four, and they are the film's tempo skeleton:

| cut | from | to | ratio |
|---|---|---|---|
| f90 | the 420 px mark | a 120 px hero line | 3.5× |
| f180 | a 120 px hero line | the 420 px mark | 3.5× |
| f420 | a 120 px hero line | the 420 px mark | 3.5× |
| **f870** | C2's 24 px labels | **C3's 160 px `503`** | **6.7×** |

f870 is the largest jump in the film and it lands on the honesty payload. See
§4.11 — that shot was a fourth consecutive 24 px-label composition in an earlier
draft, and it is why the middle of the film read as a screensaver.

**There is not one cross-dissolve in this film.** Amendment B forbids the lazy
default and every candidate here is better served by a morph (A4, B3, C4), a
match cut (B2, D1) or a gap (B4). Nothing dissolves. Nothing dips. State that in
the build assertion.

---

## 2. THE SHARED VISUAL SYSTEM

Everything in this section is imported, not re-implemented. It lives in
`promo/film/core.py`, which all four scene modules import and none of them
modify.

### 2.1 The module contract

```python
# promo/film/core.py — the only shared surface. Four modules import it.
FPS, W, H, TOTAL = 30, 1920, 1080, 1200

# each scene module exposes exactly this, and nothing else:
RANGE: tuple[int, int]                    # (first_frame, last_frame) inclusive
def render(f: int, im: Image.Image) -> None:
    """Draw frame f (RANGE[0] <= f <= RANGE[1]) onto an already-filled INK
    canvas. Must not read the clock, must not mutate module globals, must be
    a pure function of f."""
```

The driver fills every frame with `INK`, dispatches by range, applies the grade,
and writes the PNG. A module that draws outside its range is a build error. A
module that produces a different image for the same `f` on two calls is a build
error.

### 2.2 Canvas, grid, safe areas

| | |
|---|---|
| Field | `#0C0C0E` — every frame, flat. Never `#000000`, no gradient, no vignette beyond §2.9 |
| Hard margin | **160 px** left/right, **120 px** top/bottom |
| Action-safe ring | outer **96 px** on all sides — **zero drawn content**, asserted per frame |
| Content box | `(160, 120) → (1760, 960)`. Every bbox including soft edges lives inside it |
| Columns | 8 × 165 px, gutter 40 px. `160 + 8·165 + 7·40 + 160 = 1920` |
| Column left edges | c1 160 · c2 365 · c3 570 · c4 775 · c5 980 · c6 1185 · c7 1390 · c8 1595 |
| Baseline grid | 12 px. **Every text baseline is `120 + 12k`** |
| Corner radius | 12 px on a panel, 999 on a pill. Nothing between |
| Hairline | 1 px `#242426`. Subject stroke 2 px. Nothing ≥3 px except the radar ring |

### 2.3 The mark's screen circle — the spine of the film

**The radar lives at centre `(1290, 540)` in a `420 × 420` box** for A1, A3, A4,
B2, B3, B4, C1, C3, C4 and D1 — ten of fourteen shots. Only C2 (the pair) and D2
(the card) move it.

```
box origin      (1080, 330)         box            (1080,330) → (1500,750)
unit scale      s = 4.2 px / unit   (420 / 100)
hub             (1290, 540)
outer ring      r = 138.6 px, stroke 25.2 px
core            r = 18.9 px  (off-state hollow: r 23.1, stroke 16.8)
blips r=15.1    (1348.8, 502.2) · (1239.6, 573.6) · (1323.6, 607.2)
clear pulse     r 33.6 → 142.8 px, stroke 12.6
holdNet pings   r 29.4 → 92.4 px, stroke 14.7
holdGeo fence   r = 63.0 px, stroke 12.6, dash [16.8, 21.0] px
holdGeo ray     (1290,540) → (1382.4, 464.4), stroke 10.5, dash [8.4, 16.8] px
off-country blip base (1382.4, 464.4), r = 21.0 px
```

Left edge 1080, right edge 1500 — 260 px of clearance to the safe box. Nothing
about the mark ever clips.

Other placements:

| shot | centre | box | scale |
|---|---|---|---|
| C2 left (`holdNet`) | (700, 500) | 300 px, `(550,350)→(850,650)` | s = 3.0 |
| C2 right (`holdGeo`) | (1220, 500) | 300 px, `(1070,350)→(1370,650)` | s = 3.0 |
| D2 card | (960, 340) | 200 px, `(860,240)→(1060,440)` | s = 2.0 |

### 2.4 The two layouts, and why copy can never touch UI

**Layout H — hero type card** (A2, B1). Type only. No mark, no readout.

```
kicker   mono_bold 20 UPPER, +4.8 px track, #6E6E6A, left x=160, baseline y=360
hero     serif 120 wght 520,  -1.2 px track, #E7E6E2, left x=160, baseline y=480
```
Hero cap-height ≈ 86 px → cap top y = 394; the kicker baseline sits 34 px above
it (design.md §5.3 asks for 32; 360 is the nearest 12-grid line). Everything
else in frame is empty field. Field fraction ≥ 78 %.

**Layout M — mark + label + caption + readout** (A3, A4, B2, B3, B4, C1, C3, C4).
Copy occupies **columns 1–4** (`x 160 … 940`). The mark occupies **columns 6–8**
(`x 1080 … 1500`). They are disjoint on **x**, with a **140 px gutter**. Copy can
never overlap UI because they cannot reach each other.

```
state label   mono_bold 24 UPPER, +3.4 px track, state colour, x=160, baseline y=444
caption       ui 36 wght 400,     +0.36 px,      #9A9A95,      x=160, baseline y=516
rule          1 px #242426, x 160→760, y=576                  (draws on, never fades on)
readout ln 1  mono 26,            0 track,       see §2.6,     x=160, baseline y=612
readout ln 2  mono 26,            0 track,       see §2.6,     x=160, baseline y=648
```
Longest string in the copy column is `SLOW LINK · STILL ALLOWED` at 24 px mono
bold = 24 chars · 14.4 + 23 · 3.4 = **424 px** → right edge 584. Longest readout
is 23 chars · 15.6 = **359 px** → right edge 519. The gutter is never less than
496 px in practice. There is no possible collision.

*Sanctioned exception to craft §2.9 ("type band and UI band are disjoint on the
y axis").* In Layout M they are **not** disjoint on y — the copy occupies
y 420…660 and the mark's box is y 330…750, so they overlap vertically by 240 px.
They are disjoint on **x**, by 496 px, which is 4× the separation craft §2.9 was
trying to buy. craft §2.9 exists to make "subtitles landing on top of live UI
text" structurally impossible; x-disjointness achieves that more strongly than
y-disjointness, and it buys the composition an asymmetric left-heavy column
against a right-heavy mark instead of two stacked bands. Declared here so it is a
decision and not a drift. **No other rule in craft §2 is relaxed anywhere in this
film.**

**Layout M′ — the pending variant** (C3 only). Layout M with the two 26 px
readout lines replaced by the film's one big number. Same label slot, same
caption slot, same rule, same mark, same x-disjointness.

```
state label   mono_bold 24 UPPER, +3.4 px track, state colour, x=160, baseline y=444
caption       ui 36 wght 400,     +0.36 px,      #9A9A95,      x=160, baseline y=516
rule          1 px #242426, x 160→760, y=576
big number    mono_bold 160,      0 track,       #E7E6E2,      x=160, baseline y=720
annotation 1  mono 26,            0 track,       #8B8B86,      x=478, baseline y=696
annotation 2  mono 26,            0 track,       #8B8B86,      x=478, baseline y=732
```
`503` at mono_bold 160 is 3 × 96 = **288 px** wide → x 160…448; cap top
720 − 115 = 605, which clears the rule at y=576 by 29 px. The annotations start
at x=478 (a 30 px optical gap, not a space character — craft §3.4), and the
longest, `Retrying · attempt 3/8`, is 22 ch · 15.6 = **343 px** → right edge 821.
Gutter to the mark box at x=1080: **259 px**. Lowest descender y≈739, clear of
the 960 content floor by 221 px. The number and its two annotations are **one
text object** — a big-number lockup, exactly as craft §3.4 defines it — so the
shot still carries three text objects, not four.

**Layout C — the contrast pair** (C2 only). Symmetric, centred.

```
left mark  (700,500) 300 px      right mark (1220,500) 300 px     gutter 220 px
left label   centred x=700,  baseline y=720   mono_bold 24 UPPER +3.4, amber
right label  centred x=1220, baseline y=720   mono_bold 24 UPPER +3.4, amber
caption      centred x=960,  baseline y=828   ui 36, #9A9A95
```
*Sanctioned exception to craft §2 rule 10 ("nothing centred but the wordmark and
the end card"):* this shot's entire idea is that two things are equal and
independent. Symmetry **is** the idea. Any asymmetry here would rank one lane
above the other and state something false.

**Layout E — the end card** (D2 only). Centred, sanctioned.

```
mark      (960, 340), 200 px, clear, at REDUCE-MOTION STILL VALUES (dead static)
wordmark  serif 200 wght 560, +12 px track, #E7E6E2, centred x=960, baseline y=660
tagline   ui 36 wght 400, #9A9A95,                    centred x=960, baseline y=744
url       mono 30, #8B8B86 with "tower" in #E7E6E2,   centred x=960, baseline y=852
```
Mark bottom edge 440; wordmark cap top ≈ 516 → 76 px of clearance.

### 2.5 Type scale — the whole film, no other sizes exist

| role | face | px | weight | tracking | colour | used by |
|---|---|---|---|---|---|---|
| wordmark | serif (New York) | 200 | 560 | **+12.0 px** | `#E7E6E2` | D2 |
| hero | serif | 120 | 520 | **−1.2 px** | `#E7E6E2` | A2, B1 |
| kicker | mono_bold, UPPER | 20 | — | **+4.8 px** | `#6E6E6A` | A2, B1 |
| state label | mono_bold, UPPER | 24 | — | **+3.4 px** | state colour | A3 A4 B2 B3 B4 C1 C2 C3 C4 |
| caption / lede | ui (SF) | 36 | 400 | +0.36 px | `#9A9A95` | A4 B3 B4 C2 C3 |
| **big number** | **mono_bold** | **160** | — | **0** | `#E7E6E2` | **C3 only** |
| readout | mono | 26 | — | 0 | `#8B8B86` / values `#E7E6E2` | A3 A4 B2 B3 C1 C3 C4 |
| url | mono | 30 | — | 0 | `#8B8B86` / `#E7E6E2` | D2 |

The **big number** tier is used exactly once, on exactly one string (`503`), in
exactly one shot. That is the point: a size that appears once is an event, and
craft §6.5 names "a 160 px number" as one of the four scale jumps a 40 s film
needs. Using it twice would spend it.

Instantiation is `promo/overlays.py:font()` verbatim — the axis order differs per
face and getting it wrong silently produces the wrong weight:

* serif → `set_variation_by_axes([clamp(size*2, 12, 256), weight or 520, 0])`
* ui → `set_variation_by_axes([100, clamp(size, 17, 96), 400, weight or 400])`
* mono / mono_bold → static JetBrains Mono, no axes

Every `set_variation_by_axes` is wrapped in `try/except`. JetBrains Mono advance
is **0.6 em** — 20 px → 12.0, 24 px → 14.4, 26 px → 15.6, 30 px → 18.0. Use that
for width maths; it is tabular by construction so no counter ever reflows.

Nothing below **20 px em**. Nothing below **55 % alpha**. Ever.

### 2.6 Colour — the resolved table, and the law

```python
INK      = (0x0C, 0x0C, 0x0E)   # field, every frame
SURFACE  = (0x14, 0x14, 0x16)   # unused in this film — no panels are drawn
HAIRLINE = (0x24, 0x24, 0x26)   # 1 px structure
TEXT     = (0xE7, 0xE6, 0xE2)   # primary + the marks' currentColor
TEXT2    = (0x9A, 0x9A, 0x95)   # captions
MUTED    = (0x8B, 0x8B, 0x86)   # readout labels
KICKER   = (0x6E, 0x6E, 0x6A)   # eyebrow, >=20 px UPPER only
AMBER    = (0xE6, 0xA9, 0x3C)   # HELD / PENDING / WARN  — load-bearing
RED      = (0xE5, 0x48, 0x4D)   # UNGUARDED              — load-bearing
```

`GREEN #30D158` is defined and **never used**. There is no "done" agent in this
film, and the passing radar is **neutral, not green**. If green appears in a
render, the render is wrong.

**The law:** one saturated hue per frame, maximum. Amber and red never coexist in
a frame. Readouts colour only the *fault clause* — e.g. in
`Tehran, IR — outside CA` **only the word `outside` is amber** — not the target
`CA`, which is the reference and not the fault — and everything else is
`#8B8B86`; in `SLOW LINK · STILL ALLOWED` the words `SLOW LINK` are amber and
`· STILL ALLOWED` is `#E7E6E2`. That split is not decoration; it is the honest
typography of "the fault is amber, the verdict is not".

**Accent budget, restated for this film.** craft §2.3 asks for zero accent in
≥70 % of frames. Amendment A makes the amber hold states the film's headline
subject, so that number cannot survive and is replaced here by an explicit,
measured target:

Counted from the frame each accent pixel first appears, not from the shot
boundary — an earlier draft counted whole shots and was wrong in six of eight
rows (it charged B2 for 90 amber frames when the amber label enters at f430; it
charged B4 for 75 red frames when the field is empty until f621; it charged D1
red from f1056 when the pose there is still `holdGeo`; and it omitted C4's amber
entirely). The real numbers:

| run | frames | why it starts there |
|---|---|---|
| amber B2 430–509 | 80 | the `SLOW LINK` label enters f430. The mark is neutral all shot |
| amber B3 510–614 | 105 | the label carries over, then the mark goes amber at f525 |
| red B4 621–689 | 69 | f615–620 is empty field. The `off` mark fades up at f621 |
| amber C1 720–779 | 60 | neutral until the flip at f720 |
| amber C2 780–869 | 90 | both marks fade up already amber |
| amber C3 870–944 | 75 | continuous `holdGeo` |
| amber C4 945–974 | 30 | the ring reaches neutral on f974 |
| amber D1 1038–1061 | 24 | morph→`holdNet` through the `holdGeo` pose |
| red D1 1062–1079 | 18 | the amber→red morph and the `off` pose |

| | |
|---|---|
| frames carrying amber | 80 + 105 + 60 + 90 + 75 + 30 + 24 = **464** |
| frames carrying red | 69 + 18 = **87** |
| **frames with zero accent** | 1200 − 551 = **649 / 1200 = 54.1 %** |
| longest unbroken neutral run | **f0 – f429 = 430 frames = 14.3 s** |
| accent pixel coverage, any frame | **≤ 3 %** — unchanged, and this is the rule that actually protects the look |
| distinct accent hues in any frame | **≤ 1** — unchanged |

The number that matters is not 54.1 % — it is the 430-frame neutral run. Amber
arrives once, 14.3 seconds in, on two words of 24 px type covering 0.09 % of the
frame. Everything after that is paid for by that fast.

*Sanctioned exception to craft §5.2 ("red appears in at most one shot"):* red
appears in two — B4 (75 f, its dedicated beat) and D1 (24 f inside a labelless
recap of the mark's own five states). It is the same red on the same mark in the
same geometry; no new language is introduced. Amendment A requires all five
states to be featured, and this is the cheapest way to honour it.

### 2.7 Easing tokens — nothing is linear, ever

```python
EASE_ENTER = bezier(0.16, 1.00, 0.30, 1.00)   # element enter, type reveal
EASE_MOVE  = bezier(0.65, 0.00, 0.35, 1.00)   # draw-ons, anything that travels
EASE_SOBER = bezier(0.33, 1.00, 0.68, 1.00)   # EVERY hold / off / failure change
EASE_SNAP  = bezier(0.22, 1.00, 0.36, 1.00)   # a confirm, a digit landing
EASE_EXIT  = bezier(0.32, 0.00, 0.67, 0.00)   # opacity out
SETTLE     = spring(0.45, 0.85)               # 15 f — any radar state swap
ARRIVE     = spring(0.55, 0.72)               # 19 f — neutral entrance only
```

Standard durations, in frames, used throughout:

| move | frames | curve |
|---|---|---|
| radar state morph | **15** | `SETTLE` |
| type reveal envelope | **13** | `EASE_ENTER` |
| type reveal per-char stagger | **0.78 f/char**, span capped at **10 f** | — |
| type reveal rise | **0.14 em** (17 px hero, 5 px caption, 3 px label) | `EASE_ENTER` |
| sober opacity in/out (any hold/off element) | **8** | `EASE_SOBER` |
| hairline / clip_reveal draw-on | **16** | `EASE_MOVE` |
| opacity exit | **8** | `EASE_EXIT` |
| digit swap in place | **4** | `EASE_SNAP` |

`bezier()` is a real Newton solver, 8 iterations, seeded from `t = x` — fully
deterministic. `spring()` is the closed form in design.md §4.2.

**Banned outright:** linear on anything visible, bounce, elastic, back-out,
overshoot >4 %, shake, wobble, rotation of any element (the radar's own sweep and
fence are geometry, not element rotation), motion blur, speed ramps.

**`EASE_ARRIVE` / any overshoot is forbidden on anything amber, red, held,
blocked, pending or off.** Those get `EASE_SOBER`, 8 frames, and then they are
still. This is `brand.json.motion_laws.must_never` and it is the single reason
the serious moments look expensive.

### 2.8 Amendment B, formalised — overlapping choreography

Amendment B ("Stagger entrances 2-4 frames apart so motion has a leading edge")
overrides craft §4.3's "one moving element per frame" in one specific way, and
only this way:

> **A choreographed entrance group counts as ONE moving element.** Members of a
> group must (a) enter within a 12-frame window of each other, (b) be staggered
> **3 or 4 frames** apart, (c) move only in opacity and a ≤17 px rise, and
> (d) belong to the same idea. Two *different* ideas may never animate in the
> same frame, and the camera never moves at all in this film (there is no camera
> push anywhere — every shot is locked).

**There are exactly two entrance patterns in this film, and every shot declares
which one it is using.** An earlier draft had A4 and B3 citing the rule above
while staggering their copy 8 and 6 frames apart across a 30- and 36-frame span —
which the rule above forbids. The rule was not wrong; those shots were doing
something else and calling it by the wrong name.

| pattern | when | timing | counts as |
|---|---|---|---|
| **GROUP** — several elements arrive together | nothing is on screen in those slots yet | stagger **3 or 4 f**, all members inside a **12 f** window | one moving element |
| **RELAY** — a slot's occupant is replaced | a string already occupies that slot | outgoing exits fully (8 f `EASE_EXIT` or `EASE_SOBER`), **then** the incoming enters, first-in-frame ≥ last-out-frame + 1. Never overlapping | one moving element, for the whole relay |

A relay is the *only* legal way to change the text in an occupied slot. Two
strings at partial opacity in the same slot on the same frame is a cross-fade,
and this film contains none — §4.4 says so about the label slot and then §4.9's
earlier draft did it anyway in the readout slot with a +4 f offset. Fixed there.

Relays may be chained across slots (A4 relays the label, then the readout 8 f
later); a chain of relays is still one moving element because it is one idea —
"the state changed, so everything that reports it changes."

Shot-by-shot: **GROUP** — A1, A2, B1, B4, C2, D2. **RELAY** — A4, B3, C1, C4.
**GROUP then RELAY** — A3 (group in) and C3 (group in).

Sub-pixel smoothness is mandatory: every animated value is a float, and every
curved or diagonal element is drawn at **≥4× and LANCZOS-downsampled** (×6 for
anything under 80 px). Integer-snapped movement judders and reads cheap
instantly. The radar tile is drawn at 1680 px and resampled to 420.

### 2.9 Grade

`grade_static(vig=0.32, pitch=0, scan_a=0.0)` — vignette at **0.32** (old film:
0.55), **scanlines off**, no chromatic anything. `grain_layer(i, amount=1)`,
clipped ≤14/255, exists only to kill 8-bit banding in the flat field and must be
invisible when you look for it. No drop shadows anywhere, offset or otherwise.
No hue-shifting gradient anywhere.

### 2.10 The mark's phase is global and never resets

```python
P = f / 30.0          # seconds, global frame index, for EVERY mark formula
```

The sweep, the pulse, the pings, the fence, the lunge and the halo are all pure
functions of `P`. Because `P` is global the mark is *one continuous machine* for
the whole 40 s — it keeps turning across cuts and across the 90-frame type cards.
Never offset `P` per shot; never reset it at a cut. That continuity is free and
it is a large part of why the film feels like one object.

The only exceptions are elements *born* during a morph (the `clear` pulse born at
f262, f1005; the holdNet ping born at f525), which run on
`P_local = (f - birth) / 30.0` so they start at their cycle origin rather than
popping in mid-radius. Each birth frame is named in §4.

### 2.11 Deliberate emptiness, as a system

* Every shot names what is deliberately empty in §4. That is a spec line, not a
  note.
* ≥62 % of every frame is untouched field; ≥78 % on A2, B1, D1, D2.
* Ink coverage ≤25 % anywhere, ≤12 % on a hero shot.
* Maximum **three** text objects in a frame; the target is two.
* Maximum **two** overlay families, where a family is one of {hero type, the
  mark, a label/caption pair, a readout}.
* Maximum **11 words** visible in any single frame, counting readout tokens.
* **No panels, no cards, no window chrome, no terminal frame, no corner badge, no
  persistent HUD, no watermark, no logo bug.** The film contains exactly **three**
  kinds of drawn object: the mark, type, and a 1 px rule. Nothing else is ever
  drawn — if a shot seems to need a fourth kind, the shot is wrong.

---

## 3. THE STATE MORPH LIBRARY

Amendment B: *"State changes MORPH where the geometry allows it — interpolate the
actual shape rather than cross-fading between two finished pictures."* Every
transition in the film is one of the six below. They live in `core.py` as
`radar_morph(a, b, k, P)` where `k` is the eased 0…1 progress. **No radar state
change anywhere in this film is a cross-fade.**

The ring is always morphed first — colour and dash are the fastest-read channel
at any size (design.md §2.12). The core is the second read, the motion ornament
the third.

**Dash morphing.** A solid ring is represented as dash `(207.345, 0)` in unit
lengths (207.345 = the full circumference at r=33), so solid → `[5,6]`
interpolates as `on = lerp(207.345, 5, k)`, `off = lerp(0, 6, k)`, laid from the
0° seam with phase 0. The ring visibly **breaks into segments**, marching outward
from 3 o'clock. That single animation is worth more than any effect in the film.

### M1 · `verify → clear` — used at f262 (A4) and f1005 (C4)

15 f, `SETTLE`, all channels simultaneous.

| channel | from | to |
|---|---|---|
| ring | neutral solid | neutral solid — **unchanged**, and that is the point |
| needle | line hub→(50,17), length 33 | length 0 (retracts into the hub) |
| trail wedge | alpha 0.16 | alpha 0.00 |
| blips | base opacity 0.30 | base opacity 0.80 |
| new element | — | the `clear` pulse ring is **born at the hub**: `P_local` starts at the morph's first frame, so it emerges at r=8 and expands |
| core | filled neutral 4.5 | unchanged |

The read: the sweep stops looking and the scope starts breathing. Nothing
flashes, nothing bounces, nothing turns green.

### M2 · `clear → holdNet` — used at f525 (B3)

15 f, `SETTLE`. A hold is *pending*, not failed: it arrives calm — no
celebration, no funeral, and **no overshoot**.

| channel | from | to |
|---|---|---|
| ring colour | `#E7E6E2` | `#E6A93C`, mixed linearly in sRGB |
| ring dash | `(207.345, 0)` | `(5, 6)` — **the ring breaks** |
| core | filled neutral r 4.5 | filled **amber** r 4.5 |
| blips | 0.80 breathing | **0.00 — the scope loses its contacts** |
| pulse → ping #0 | r-range 8→34, w 3.0, α≤0.5, neutral | r-range 7→22, w 3.5, α≤0.7, amber. **The same ring, re-tuned** |
| ping #1 | — | fades in separately over 15 f `EASE_ENTER` starting **f540**, a beat *after* the state lands, so the sonar audibly and visibly doubles up |

### M3 · `clear → holdGeo` — used at f720 (C1). **The film's biggest moment.**

15 f `SETTLE` for the ring group, then a 30 f staged build for the geo group.
Read M3 against M2: this is where holdNet and holdGeo separate.

| channel | from | to | note |
|---|---|---|---|
| ring colour | `#E7E6E2` | `#E6A93C` | same as M2 |
| ring dash | solid | **solid — it does NOT break** | **the thesis, made geometric.** holdNet breaks the ring; holdGeo does not |
| core | filled neutral | **filled neutral — unchanged** | holdNet turns the core amber; holdGeo leaves it alone |
| blips | 0.80 | 0.00 | same as M2 |
| pulse → fence | expanding neutral ring, r 8→34 | **contracts and locks to r = 15**, colour → amber, dash solid → `(4,5)` | one ring *becomes* another. From f735 it rotates at 45 °/s |
| ray | — | dashed line hub→(72,32), draws **outward from the hub** via `clip_reveal` along its axis, 16 f `EASE_MOVE`, **f735–f750** | |
| off-country blip | — | appears at (72,32), r 5, amber, opacity 0→1 over 8 f `EASE_SOBER` at **f750** | sober: it is part of a hold |
| lunge + halo | — | begin at **f758**: `lunge = 6·(0.5 + 0.5·sin(P·2.2))` along `(−0.773, +0.634)`, halo `r = 5 + hp·9`, `hp = (P·1.1) mod 1` | the contact lunges toward the fence and is pushed back, forever. Its closest approach is d=22.43; the fence is at 15. **It never gets in.** Protect this |

Only two of the five ring/core channels differ between M2 and M3, and both are
*absences* — the ring that doesn't break, the core that doesn't change. That is
why C2 exists: at a glance those differences are subtle, and C2 puts them side by
side and lets the viewer resolve them at leisure.

### M4 · `clear → off` — used at f621 (B4), f1056 (D1)

**8 f, `EASE_SOBER`, opacity only, and then dead still.** Failure never bounces.
There is no draw-on, no scale, no settle. The mark simply *is* there.

| channel | value |
|---|---|
| ring | `#E5484D`, dash `(5, 7)` |
| core | **hollow**: stroke circle r 5.5, width 4, red. Never filled |
| blips | flat **0.22**, no breathing |
| motion | **none.** `P` does not appear in any off-state expression |

In B4 the state does not morph *from* anything — the frame is empty for 6 frames
first and the `off` mark fades up from nothing. In D1 it is a true 6 f morph from
`holdGeo` (dash `(4,5)`→`(5,7)`, amber→red, filled core → hollow core by
interpolating an inner hole radius 0→3.5 while the outer goes 4.5→5.5). Both use
`EASE_SOBER`.

### M5 · `holdGeo → verify` — used at f960 (C4). The release.

15 f `SETTLE` for the ring, staged teardown for the geo group.

| channel | from | to | frames |
|---|---|---|---|
| off-country blip + halo | live | alpha 0 | f960–f968, 8 f `EASE_SOBER` |
| ray | full | retracts **into the hub** (`clip_reveal` reversed) | f960–f972, 12 f `EASE_MOVE` |
| fence | r 15, amber, dash (4,5) | **expands r 15 → 33 and is absorbed into the outer ring**, alpha → 0 as it arrives | f960–f974, 15 f `SETTLE` |
| ring colour | `#E6A93C` | `#E7E6E2` | f960–f974, 15 f `SETTLE` |
| needle + wedge | — | draw on from the hub outward, wedge alpha 0→0.16 | f966–f979, 13 f `EASE_MOVE` |
| blips | 0.00 | 0.30 (verify level), staggered 3 f apart | from f972 |

The fence *becoming* the ring is the visual sentence "the fence is no longer
needed". It reverses M3's "the ring becomes the fence" exactly.

### M6 · the fast run — used only in D1

Six 6-frame morphs at `EASE_SNAP` (`EASE_SOBER` for anything entering or leaving
`off`), each running the same channel maths as M1–M5 but compressed. Poses are
6 frames. This is a *recap*, so speed is the point — the viewer has already been
taught each state individually at hero scale with its own label. See §4.13.


---

## 4. THE SHOTS

Every shot below gives: the single idea, exact layout, verbatim copy with its
on-screen frame range, the motion channel by channel, the colour state, and what
is deliberately empty. Frame numbers are absolute and integer. All type reveals
are `draw_kinetic` (per-char alpha + rise) unless the shot says
**opacity-only** — which it does for every hold, off and failure element,
because kinetic reveal is celebratory and a hold is not celebrated.

---

### 4.1 · A1 `open.mark` — f0 … f89 (90 f) — `scene_open.py`

**Idea:** *The mark draws itself onto nothing.*

**Layout.** The mark alone at the canonical circle: centre `(1290, 540)`,
420 px box, `(1080,330) → (1500,750)`. Columns 1–5 are empty field. No type of
any kind.

**Copy.** None. Zero words. The film's first three seconds contain no language
at all — that is the held silence craft §6.2 asks for, stretched to a whole shot
because the thing being introduced is a *mark*, not a sentence.

**Motion.**

| f | what | from → to | curve |
|---|---|---|---|
| 0–11 | **nothing.** Pure `#0C0C0E`. 12 frames of empty frame | — | — |
| 12–47 | **the outer ring draws on** — an arc sweep from −90° (12 o'clock) clockwise through 360° | angular reveal 0° → 360° | `EASE_MOVE`, 36 f |
| 12–21 | the ring's stroke width opens as it draws | 0 → 25.2 px | `EASE_ENTER`, 10 f |
| 48–66 | **the core seats** — filled disc | r 0 → 18.9 px | `ARRIVE` (19 f). The only overshoot in the film: +3.8 %, on a neutral entrance, which is the one place it is legal |
| 60 / 63 / 66 | **three blips fade up**, staggered 3 f | α 0 → verify level (0.30 base) | `EASE_ENTER`, 13 f each |
| 70–82 | **the state resolves to `verify`** — the trail wedge fades in and the needle draws outward from the hub | wedge α 0 → 0.16 · needle length 0 → 33 units (138.6 px) | wedge `EASE_ENTER` 13 f · needle `EASE_MOVE` 13 f |
| 70–89 | the sweep rotates on global `P` at 150 °/s | — | the mark's own geometry (the one sanctioned constant-rate motion) |

The ring draws from 12 o'clock so the seam of the draw-on is *not* the 0° dash
seam — when the ring later breaks into dashes at f525 the break starts at
3 o'clock, somewhere the eye has never been anchored. Small thing; it stops the
two events from rhyming into a single remembered gesture.

**Colour.** Fully neutral. `#E7E6E2` on `#0C0C0E`. **Zero accent.** The film
spends its first 14 seconds establishing that neutral is the normal, so that the
first amber at f420 is an event.

**Deliberately empty.** Columns 1–5 — the entire left 56 % of the frame. Frames
0–11 — the entire frame. There is no logo, no wordmark, no kicker, no product
name, and no explanation. The mark arrives before its name does.

---

### 4.2 · A2 `open.where` — f90 … f179 (90 f) — `scene_open.py`

**Idea:** *The first of two independent checks.*

**Layout H.** Type only, columns 1–5.

```
kicker  CHECK ONE        mono_bold 20 UPPER, +4.8, #6E6E6A, x=160, baseline y=360
hero    Where you are.   serif 120 wght 520, -1.2, #E7E6E2, x=160, baseline y=480
```
Hero measured width ≈ 840 px → right edge ≈ 1000. Measure 14 characters, well
inside the 46 ch / 1190 px cap. Left edge optically aligned on the flat left of
`W` via `font.getbbox()`, not the advance origin — at 120 px `W` needs ≈6 px of
hanging correction or the column looks broken against A3's label.

**Copy.**

| text | words | on screen | reveal |
|---|---|---|---|
| `CHECK ONE` | 2 | **f108 … f179** (full opacity f121 → f179 = 59 f ≥ 42 f floor) | kinetic, 0.78 f/char, envelope 13 f `EASE_ENTER`, rise 3 px |
| `Where you are.` | 3 | **f111 … f179** (full opacity f124 → f179 = **56 f** ≥ 53 f floor, margin 3) | kinetic, span capped 10 f, envelope 13 f `EASE_ENTER`, rise 17 px |

No exit animation — the shot ends on a hard cut, so the exit budget is not spent.

**Motion.** f90–f107: **18 frames of completely empty frame.** Then the kicker,
then the hero **3 frames** behind it — a GROUP (§2.8), inside the 12 f window,
one leading edge. (An earlier draft had the hero 6 f behind, which both broke
§2.8's stagger rule and left the hero exactly at its reading floor with zero
margin. 3 f fixes both.) Nothing else moves for the remaining 56 frames. This
shot is static for 62 % of its length.

**Colour.** Neutral only. Zero accent.

**Deliberately empty.** Columns 6–8 — where the mark was one frame ago and will
be again in 75 frames. Leaving the mark's seat visibly vacant for 90 frames is
what makes its return at f180 read as a return.

---

### 4.3 · A3 `open.verify` — f180 … f254 (75 f) — `scene_open.py`

**Idea:** *Tower holds the request while it confirms where you are.*

**Layout M.** Mark at the canonical circle in `verify`, phase continuous from A1
(global `P`, so the needle is wherever it should be — do not reset it).

```
label    VERIFYING              mono_bold 24 UPPER, +3.4, #E7E6E2, x=160, y=444
rule     1 px #242426           x 160 → 760, y=576
readout  Confirming location…   mono 26, #8B8B86,               x=160, y=612
```
No caption. The state label and the product's own words are enough.

**Copy.**

| text | words | on screen | reveal |
|---|---|---|---|
| `VERIFYING` | 1 | **f186 … f254** (full f199 → f254 = 55 f ≥ 42 f floor) | kinetic, 13 f `EASE_ENTER`, rise 3 px |
| `Confirming location…` *(readout, not copy)* | — | **f198 … f254** (full f211) | kinetic, 13 f, rise 3 px |

**Motion.**

| f | what | curve |
|---|---|---|
| 180–185 | mark alone, 6 f | — |
| 186 | label enters | `EASE_ENTER` 13 f |
| 192 | **the rule draws on** left→right, `clip_reveal(frac, 'x', soft=0.10)` | `EASE_MOVE` 16 f |
| 198 | readout enters | `EASE_ENTER` 13 f |
| 211–254 | **44 frames completely static** except the mark's own 2.400 s sweep | — |

Draw-on, not fade-in (craft §6.9). The rule is 600 px of 1 px hairline arriving
in 0.53 s; it is the only thing in the shot with an edge, and it gives the copy
column a floor.

**Colour.** Neutral. `verify` is a neutral state — Tower is *not* amber while it
checks; it simply hasn't answered yet, and it is holding the request until it
has. Zero accent.

**Deliberately empty.** The caption slot (baseline 516) stays empty in this shot
and fills in A4. That empty line is a promise that something is coming.

---

### 4.4 · A4 `open.clear` — f255 … f329 (75 f) — `scene_open.py`

**Idea:** *Confirmed in-country — the request passes.*

**No cut.** Continuous from A3. Same layout, same mark, same rule.

**Copy.**

| text | words | on screen | reveal |
|---|---|---|---|
| `VERIFYING` | — | exits **f262 … f269** | opacity-only, 8 f `EASE_EXIT` |
| `CLEARED` | 1 | enters **f270**, full f283 → f329 = **47 f** ≥ 42 f floor, margin 5 | kinetic, 13 f `EASE_ENTER` |
| `Confirmed in-country.` | 2 | enters **f273**, full f286 → f329 = **44 f** ≥ 42 f floor, margin 2 | kinetic, 13 f `EASE_ENTER`, rise 5 px |
| `Confirming location…` *(readout)* | — | exits **f270 … f277** | opacity-only, 8 f `EASE_EXIT` |
| `Toronto, CA — inside CA` *(readout)* | — | enters **f278**, full f291 → f329 | kinetic, 13 f |

**The caption moved from f276 to f273 and this is not cosmetic.** At f276 it held
full opacity for f289…f329 — which is **41 frames**, not the 42 the earlier draft
claimed, because a line shown on frames *a* through *b* inclusive is on screen for
`b − a + 1` frames. It was the only line in the film actually *below* its reading
floor, and it was below it by one frame, hidden by an off-by-one. Entering at f273
puts the caption 3 f behind `CLEARED` — a legal GROUP stagger (§2.8) instead of
the earlier 6 — and buys 3 frames of margin.

The label and readout swap as **RELAYs** (§2.8) — old out fully, then new in.
Two strings cross-fading in the same slot is the one thing that always reads
cheap. `VERIFYING` clears at f269 and `CLEARED` starts at f270; the readout
clears at f277 and the new one starts at f278. Never a frame of overlap.

**Motion.**

| f | what |
|---|---|
| 255–261 | **7 frames of dead stillness.** Anticipation (craft §6.1) — the sweep keeps turning, nothing else exists |
| **262–276** | **MORPH M1 · `verify → clear`**, 15 f `SETTLE`. Needle retracts 33→0, wedge α 0.16→0, blips 0.30→0.80, and the `clear` pulse ring is **born at the hub** with `P_local = (f−262)/30` so it emerges at r=8 |
| 262–291 | the copy RELAY chain (§2.8): label out 262–269, label in 270, caption in 273, readout out 270–277, readout in 278 |
| 292–329 | **38 frames static** except the pulse's own 2.381 s cycle at α ≤ 0.5 |

**Colour.** Neutral throughout. **The passing radar is not green.** It is calm.
Zero accent. This is the film's baseline, and it is deliberately unexciting — an
all-clear that celebrated itself would make every later hold read as an alarm.

**Deliberately empty.** Everything except one label, one caption, one rule, one
readout and one mark. Field fraction ≈ 84 %.

---

### 4.5 · B1 `wire.how` — f330 … f419 (90 f) — `scene_wire.py`

**Idea:** *The second of two independent checks.*

**Layout H**, identical metrics to A2 — same x, same baselines, same faces. The
rhyme is the point: two checks, two identical cards.

**Copy.**

| text | words | on screen | reveal |
|---|---|---|---|
| `CHECK TWO` | 2 | **f336 … f419** (full f349 → f419 = 71 f) | kinetic, 13 f `EASE_ENTER`, rise 3 px |
| `How the wire is.` | 4 | **f339 … f419** (full f352 → f419 = **68 f** ≥ 64 f floor, margin 4) | kinetic, span capped 10 f, 13 f, rise 17 px |

Hero measured width ≈ 928 px → right edge ≈ 1088. 16 characters.

**Motion.** f330–f335: **6 frames of empty frame** — one third of A2's 18.
Deliberate speed contrast (craft §6.6): the second card arrives faster than the
first because the viewer already knows the form. Then the same GROUP, hero **3 f**
behind the kicker exactly as in A2 (an earlier draft said 6 f here too, which put
the hero 1 frame above its floor). Static from f352.

**Colour.** Neutral. Zero accent. This is the last neutral-only shot before the
first amber, 65 frames later.

**Deliberately empty.** Columns 6–8 again. Same vacancy, same return.

---

### 4.6 · B2 `wire.slow` — f420 … f509 (90 f) — `scene_wire.py`

**Idea:** *A slow link is not a blocked link.*

**The film's structural match cut.** The mark returns at f420 to the exact
geometry it left at f329, in the exact state (`clear`), with `P` never having
reset. 90 frames of type sat between two frames of the same picture.

**Layout M.**

```
label    SLOW LINK · STILL ALLOWED   mono_bold 24 UPPER, +3.4, x=160, y=444
         "SLOW LINK"    -> #E6A93C   (the fault is amber)
         "· STILL ALLOWED" -> #E7E6E2 (the verdict is not)
rule     1 px #242426, x 160 → 760, y=576
readout  net 82 ms · api 273 ms      mono 26, x=160, y=612
         "net" / "api" / "ms"  -> #8B8B86      numbers -> #E7E6E2
```
Label width = 24 ch · 14.4 + 23 · 3.4 = 424 px → right edge 584. Readout width
= 22 ch · 15.6 = 343 px. Gutter to the mark: 496 px.

**Copy.**

| text | words | on screen | reveal |
|---|---|---|---|
| `SLOW LINK · STILL ALLOWED` | 4 | **f430 … f509** (full f443 → f509 = **67 f** ≥ 64 f floor, margin 3) | kinetic, 13 f `EASE_ENTER`, rise 3 px |
| `net 82 ms · api 273 ms` *(readout)* | — | **f450 … f509** (full f463) | kinetic, 13 f |

Both numbers are real observed samples from `analysis/footage.json`
(`online · net 82ms · api 273ms`, t = 40 s). Rendered in the **popover's**
format — `82 ms` with a space — because this is Tower's own voice, not a terminal
transcript. Do not cross the two formats.

**Motion.** f420–f425 mark alone (6 f). f426 rule draws on (16 f `EASE_MOVE`).
f430 label (a GROUP with the rule, 4 f behind it). f450 readout. Static from
f463 for 47 frames except the `clear` pulse. **No number rolls.** A rolling
counter here would be a second moving element and would also imply the link is
degrading, which it isn't.

**Colour.** **First amber of the film**, at f430 — 14.3 seconds in, after 430
frames of pure neutral. It is 2 words of 24 px type: accent coverage ≈ 0.09 % of
the frame. Scarcity is the effect (craft §6.4).

**And the mark stays neutral.** That is the entire shot. A degraded link is
high-latency but reachable, and `should_block()` does not fire on it. If the
radar went amber here the film would be lying, and it would also spend the
holdNet arrival 78 frames early.

**Deliberately empty.** The caption slot. There is nothing to add — the label
already contains the whole argument in four words.

---

### 4.7 · B3 `wire.hold` — f510 … f614 (105 f) — `scene_wire.py`

**Idea:** *No usable path to Anthropic — the request is held.*

**No cut.** Continuous from B2.

**Layout M**, same slots. Label, caption and readout all change.

**Copy.**

| text | words | on screen | reveal |
|---|---|---|---|
| `SLOW LINK · STILL ALLOWED` | — | exits **f525 … f532** | opacity-only, 8 f `EASE_EXIT` |
| `net 82 ms · api 273 ms` *(readout)* | — | exits **f528 … f535** | opacity-only, 8 f `EASE_EXIT` |
| `HOLD · CONNECTION` | 2 | enters **f540**, full f548 → f614 = 66 f ≥ 42 f | **opacity-only, 8 f `EASE_SOBER`** — a hold is not revealed kinetically |
| `No usable path.` | 3 | enters **f546**, full f554 → f614 = **60 f** ≥ 53 f floor | **opacity-only, 8 f `EASE_SOBER`** |
| `internet down` *(readout)* | — | enters **f552**, full f560 | **opacity-only, 8 f `EASE_SOBER`** |

`HOLD · CONNECTION` is `#E6A93C`. `No usable path.` is `#9A9A95`.
`internet down` is `#E6A93C` — this is the TUI's own line for the offline case
and it names the cause, which is the whole product.

**Be precise about why it is amber, because the product is not.** In the shipping
app the offline *banner* is red (`ui-truth.md` §1: `Your internet is offline` in
systemRed; the TUI header `INTERNET DOWN` in `C_BAD`). The **radar**, which is the
authority on the guard's verdict, is `holdNet` **amber**. This film unifies on the
brand pair and shows one hue per frame (§2.6), so a red readout beside an amber
mark is not available to it — and of the two, the *verdict* is what the film is
about. So: amber, matching the mark, and the word `red` is reserved in this film
for the one state where Tower is not guarding at all. This is a **declared
palette simplification, not a claim about the product's chrome.** The semantics
are untouched: offline holds, a hold is pending, and nothing here says "failed".

**Motion.**

| f | what |
|---|---|
| 510–524 | **15 frames of dead stillness.** The longest anticipation in the film, because the biggest change so far is coming |
| **525–539** | **MORPH M2 · `clear → holdNet`**, 15 f `SETTLE`. Ring `#E7E6E2`→`#E6A93C`; ring dash solid → `(5,6)` — **the ring breaks into segments from the 3 o'clock seam**; core → amber; blips 0.80 → **0.00**; the `clear` pulse ring re-tunes into ping #0 (r-range 8→34 becomes 7→22, w 3.0→3.5, α 0.5→0.7) |
| 540–554 | **ping #1 fades in**, 15 f `EASE_ENTER`, half a period out of phase. The sonar doubles up one beat *after* the state lands — an engineered flourish, not a state change |
| 525–560 | the copy RELAY chain (§2.8): label out 525–532, readout out 528–535, label in 540, caption in 546, readout in 552. Every slot is fully vacated before it is refilled |
| 561–614 | **54 frames static** except the two amber pings on their 1.4286 s cycle |

**Colour.** Amber. One hue. The ring, the core, the pings, the label and the
readout cause — all `#E6A93C`. Accent coverage ≈ 1.8 % of the frame, under the
3 % cap. Nothing is red. Nothing has failed.

**Deliberately empty.** The scope has **no contacts** — the three blips are gone,
and that is free, honest storytelling: nothing is getting through. Do not
substitute a symbol, a slash, a cross or a spinner for the missing blips.

---

### 4.8 · B4 `wire.off` — f615 … f689 (75 f) — `scene_wire.py`

**Idea:** *Without the guard there is no verdict at all.*

**This shot is the argument's control case, not a feature tour.** It was the
weakest shot in an earlier draft for a structural reason worth naming: it sits at
the film's midpoint, between the two holds, and it introduces a third idea
(routing) that the argument never returns to. Amendment A requires all five states
to be featured *and individually labelled*, D1's 6-frame poses are far too short
to carry a label, and so `off` needs exactly one labelled beat — this one. Its
75 frames are also close to irreducible: 6 empty + 8 sober fade + the 53-frame
floor on a 3-word caption = 71 frames minimum from the cut.

So it earns its place by being reframed rather than moved. A1–B3 have taught the
viewer that the mark always has an answer. B4 removes the answer. The three
preceding shots each show Tower *deciding* something; this one shows the frame
where nothing is being decided, which is what makes the two holds read as service
rather than obstruction. It is the film's only argument from absence.

**Cut in: hard cut to 6 frames of empty field, and the audio bed cuts to true
silence on f615.** This is the only gap in the film.

**Layout M**, mark at the canonical circle in `off`.

**Copy.**

| text | words | on screen | reveal |
|---|---|---|---|
| `UNGUARDED` | 1 | **f624 … f689** (full f632 → f689 = 58 f ≥ 42 f, margin 16) | **opacity-only, 8 f `EASE_SOBER`** |
| `Claude connects directly.` | 3 | **f627 … f689** (full f635 → f689 = **55 f** ≥ 53 f floor, margin 2) | **opacity-only, 8 f `EASE_SOBER`** |

`UNGUARDED` is `#E5484D`. The caption is `#9A9A95`.

**Motion.** There is almost none, and that is the design.

| f | what |
|---|---|
| 615–620 | **6 frames of completely empty frame.** No mark, no type, no sound |
| 621–628 | **MORPH M4 · `→ off`** — the mark fades up, **opacity only**, 8 f `EASE_SOBER`. No draw-on. No scale. No settle. It simply is there |
| 624 / 627 | label, then caption, 3 f behind — the same sober fade. A GROUP (§2.8): mark 621, label 624, caption 627, all inside a 7-frame window on 3-frame staggers |
| **635–689** | **55 frames of absolutely nothing moving.** `P` does not appear in any `off`-state expression. The ring does not pulse, the blips do not breathe, the core does not glow |

**Colour.** Red. The only red shot in the film besides 24 frames of D1. The ring
is `#E5484D` dashed `(5,7)`; the core is **hollow** — a stroked ring, r 5.5,
width 4 — and the blips sit at a flat 0.22. The hollow core is the entire read:
*the centre is empty, nothing is holding this.* Never fill it.

**Deliberately empty.** The rule and the readout slot are both gone — there is no
readout, because with the guard off there is nothing being measured. And the
sound is gone. 55 frames of dead-still red on a silent field is the loudest
thing in the film, and it is achieved entirely by subtraction.


---

### 4.9 · C1 `hold.geo` — f690 … f779 (90 f) — `scene_hold.py`

**Idea:** *You leave the country — the request is held for a different reason.*

**Cut in:** hard cut. The mark is back at the canonical circle in **`clear`**,
and the audio bed returns. The guard must be visibly restored before location
takes it away, or `off` and `holdGeo` collapse into one memory.

**Layout M.**

```
label    HOLD · LOCATION           mono_bold 24 UPPER, +3.4, #E6A93C, x=160, y=444
rule     1 px #242426, x 160 → 760, y=576
readout  Tehran, IR — outside CA   mono 26, x=160, y=612
         leading run  "Tehran, IR — "  -> #8B8B86   (20 ch incl. "outside")
         fault word   "outside"        -> #E6A93C
         trailing run " CA"            -> #8B8B86   (fixed x, never changes)
```
Only the word **`outside`** takes the accent. The target `CA` stays `#8B8B86` in
both readings — it is not the fault, it is the reference, and colouring it amber
would say the country is the problem. Earlier drafts amber-ed the whole clause
`outside CA`, which also contradicted the "trailing `CA` never changes" device
below, since it would have had to change colour.
No caption. The label and the readout carry it.

**Copy.**

| text | words | on screen | reveal |
|---|---|---|---|
| `Toronto, CA — inside` *(readout, leading run)* | — | **f702 … f727** | kinetic in 13 f, then relays out |
| `Tehran, IR — outside` *(readout, leading run)* | — | **f728 … f779** | see the run swap below |
| ` CA` *(readout, trailing run)* | — | **f702 … f779 — never changes, never moves, never dips in opacity** | — |
| `HOLD · LOCATION` | 2 | **f728 … f779** (full f736 → f779 = 44 f ≥ 42 f floor, margin 2) | **opacity-only, 8 f `EASE_SOBER`** |

Both readouts are real observed values from `analysis/footage.json`: the inside
reading `Toronto, CA` / target `CA`, and the outside reading `Tehran, IR`. No IP
is shown anywhere in the film — not redacted, simply **never drawn**, because
nothing was captured so there is nothing to hide (craft §8.14 bans redaction
bars, and a redaction bar tells the viewer you were hiding something).

**The readout run swap at f720.** The line is drawn as **two independent runs**
sharing one baseline: a leading run at x=160 and the trailing run ` CA` at the
fixed x its 20th character occupies. The leading run relays — `Toronto, CA —
inside` exits **f720…f727** on 8 f `EASE_SOBER`, and only when it is fully gone
does `Tehran, IR — outside` enter **f728…f735** on 8 f `EASE_SOBER`. **The
trailing `CA` never moves, never changes and never dips in opacity** — it is the
target country, it was always `CA`, and it holds at full opacity through the
whole swap while everything before it is replaced. The two leading runs are 20
characters each so the line does not reflow by a single pixel.

*This was a cross-fade in an earlier draft* — the outgoing run ran f720–727 and
the incoming one entered at f724, overlapping by 4 frames, in the same slot, four
sections after §4.4 declares that "two strings cross-fading in the same slot is
the one thing that always reads cheap" and §2.8 bans it outright. It is now a
RELAY. It costs 4 frames and the slot is briefly empty, which is *better*: the
half-second where the location line is blank while the mark is already amber is
the truest frame in the film — the verdict lands before the explanation does,
exactly as it does in the product.

That stillness at the end of a changing line is the most expensive-looking detail
in the film and it costs nothing.

**Motion.**

| f | what |
|---|---|
| 690–695 | mark alone in `clear`, 6 f |
| 696 | rule draws on, 16 f `EASE_MOVE` |
| 702 | readout `Toronto, CA — inside CA` enters, 13 f `EASE_ENTER` |
| 715–719 | **5 frames of dead stillness.** The anticipation before the film's biggest beat |
| **720** | **THE FLIP.** A multiple of 60. Two things change on the same frame — the mark and the readout — because in the real product they do (`ui-truth.md` §6: the location card, the header and the plan card all flip in one frame) |
| **720–734** | **MORPH M3 · `clear → holdGeo`**, 15 f `SETTLE`. Ring → `#E6A93C` but **stays solid**. Core **stays filled neutral**. Blips 0.80 → 0.00. The `clear` pulse ring **contracts and locks to r = 15**, turns amber, and its dash morphs solid → `(4,5)` — one ring literally becomes the fence |
| 720–727 | the readout's leading run exits, sober. The slot is empty on f728 for one frame |
| 728–735 | the readout's new leading run enters, sober. `HOLD · LOCATION` enters on the same frame — both are consequences of the same flip, so they are one moving element |
| 735–750 | **the ray draws outward from the hub** to (72,32), `clip_reveal` along its axis, 16 f `EASE_MOVE` |
| 735– | the fence begins rotating, 45 °/s = 8.000 s per revolution |
| 750–758 | **the off-country contact lands** at (72,32), r 5, amber, opacity-only 8 f `EASE_SOBER` |
| 758–779 | the contact begins its lunge: `6·(0.5 + 0.5·sin(P·2.2))` along `(−0.773, +0.634)`, scale `1 + 0.16·sin(P·3.0)`, halo `r = 5 + hp·9` at `hp = (P·1.1) mod 1`. **It lunges toward the fence and is pushed back, forever. Closest approach d = 22.43; the fence sits at 15. It never gets in.** |

**Colour.** Amber, one hue, ≈2.1 % coverage. **Off-country is amber, never red.**
If a render shows red in this shot the render is wrong and the product has been
misrepresented.

**Deliberately empty.** The caption slot stays empty for the whole shot. C1 does
not explain itself in prose — it shows the fence and the contact that cannot get
past it, and lets the next shot do the explaining. And there are still no
contacts inside the scope.

---

### 4.10 · C2 `hold.which` — f780 … f869 (90 f) — `scene_hold.py`

**Idea:** *Two holds, two causes — the mark tells you which.*

This shot is the thesis. Amendment A: *"holdNet vs holdGeo is the film's entire
thesis… These two states must be directly contrasted on screen. Do not let them
blur together."*

**Layout C.** Symmetric, centred, sanctioned (§2.4).

```
left mark   holdNet   centre (700,500),  300 px, box (550,350)→(850,650)
right mark  holdGeo   centre (1220,500), 300 px, box (1070,350)→(1370,650)
                                                  gutter 220 px
left label   HOLD · CONNECTION   centred x=700,  baseline y=720   (299 px wide)
right label  HOLD · LOCATION     centred x=1220, baseline y=720   (264 px wide)
caption      Tower tells you which.   centred x=960, baseline y=828, ui 36, #9A9A95
```

**Copy.**

| text | words | on screen | reveal |
|---|---|---|---|
| `HOLD · CONNECTION` | 2 | **f784 … f869** (full f792) | opacity-only, 8 f `EASE_SOBER` |
| `HOLD · LOCATION` | 2 | **f788 … f869** (full f796) | opacity-only, 8 f `EASE_SOBER` |
| `Tower tells you which.` | 4 | **f791 … f869** (full f804 → f869 = **66 f** ≥ 64 f floor, margin 2) | kinetic, 13 f `EASE_ENTER`, rise 5 px |

**Motion — the alternating spotlight.** This is the shot's whole design and it is
how "one loudest thing at a time" and "show both, side by side" are both
satisfied at once.

| f | what |
|---|---|
| 780–788 | left mark fades up, opacity-only 8 f `EASE_SOBER` |
| 784–792 | right mark fades up, 4 f behind — one choreographed GROUP (§2.8) |
| 784 / 788 | the two labels, same stagger |
| 791–804 | the caption, kinetic |
| **805–835** | **LEFT LIVE.** `holdNet` at α 1.0 running its native 1.4286 s two-ping sonar. **RIGHT FROZEN** at its documented Reduce-Motion still values (fence rotation 0, lunge 0, scale 1, halo r 10 at α 0.5) and held at **α 0.45**. Right label at α 0.55 |
| **836–843** | **the attention swaps**, 8 f `EASE_SOBER`: left α 1.0 → 0.45 and freezes to *its* still values (pings at r 11/18, α 0.55/0.30); right α 0.45 → 1.0 and resumes its live cycle on global `P` — no phase reset, so the fence and lunge pick up mid-cycle with zero judder |
| **844–869** | **RIGHT LIVE.** `holdGeo` at α 1.0: fence turning, contact lunging, halo pulsing. **LEFT FROZEN** |

**The dimmed mark sits at α 0.45, not 0.30.** Amber `#E6A93C` at 30 % over
`#0C0C0E` resolves to roughly `#4B3B1F` — a mark you can see but not *read*, which
defeats the whole shot: the frozen side is supposed to be a fully legible diagram
of the other answer, not a ghost. 0.45 keeps the four-way difference table below
resolvable in a frozen frame while still leaving a 2.2× contrast gap to the live
side, which is more than enough to say which one is speaking. This is the one
number in C2 that decides whether the thesis lands.

**On the length of the live windows.** Left gets 31 frames, right gets 26. Both
are shorter than their marks' own cycles (holdNet 42.9 f, holdGeo's lunge 85.7 f),
and that is deliberate but it is also the shot's known limit, so state the
mitigation rather than pretend: holdNet's two pings run half a period apart, so a
*ping event* occurs every 21.4 f and the left window shows 1.4 of them — enough to
read "expanding sonar". holdGeo's lunge is **not** completed here; it is completed
across the cut into C3, where the same mark runs live and phase-continuous from
f870 to f944 — f844 → f944 is 101 frames, comfortably more than the 85.7 f lunge
period. **Do not "fix" C2 by re-phasing either mark to fit its window.** Global
`P` continuity (§2.10) is what makes the C2→C3 cut carry the lunge, and resetting
phase to squeeze a whole cycle into 26 frames would break the one device that
makes the film feel like a single machine.

At no frame are both marks animating. Exactly one thing is loud, always. And
because design.md guarantees every radar state has a *legible still frame*, the
frozen side is never a blank — it is a fully readable diagram of the other
answer.

**What the viewer is meant to resolve, and why 90 frames is the right length:**

| | `holdNet` (left) | `holdGeo` (right) |
|---|---|---|
| ring | amber, **broken** `(5,6)` | amber, **solid** |
| core | **amber** | **neutral** |
| interior | two expanding sonar pings | a rotating dashed fence + a ray + a contact outside it |
| blips | none | none |

Two of those four differences are visible in a single frozen frame at any moment.
That is the payload.

**Colour.** Amber, one hue, both sides. ≈2.6 % coverage — the highest in the
film, still under 3 %.

**Deliberately empty.** Everything above y=350 and below y=850. No title, no
kicker, no numbers, no arrows, no connecting lines, no "vs". Two marks, two
labels, one sentence.

---

### 4.11 · C3 `hold.pending` — f870 … f944 (75 f) — `scene_hold.py`

**Idea:** *The held turn is pending, and it survives.*

**Cut in:** hard cut back to the canonical circle. State unchanged (`holdGeo`,
phase continuous — the fence is exactly where C2 left it). The cut carries no
state information; the **scale** does.

**Layout M′ — the pending variant** (§2.4). This is the one shot in the film that
changes typographic scale, and the reason is structural. In an earlier draft C3
was the fourth consecutive composition built from a 24 px label, a 36 px caption
and 26 px readouts; C1, C2 and C3 ran 240 frames — eight seconds — at an identical
type scale, in the middle of the film, on the film's most important idea. That is
how a minimal film turns into a tasteful screensaver. craft §6.5 asks for four
scale jumps of ≥3× and names "a 160 px number" as one of them; the film had three
jumps and they were all in the first fourteen seconds.

So the mechanism gets the size. `503` is the single most load-bearing string in
the film — it is the difference between "your turn is waiting" and "your turn
died" — and it is now 160 px of tabular mono in the copy column, a **6.7× jump**
across the f870 cut and the largest piece of type in the film after the wordmark.

```
label     PENDING                  mono_bold 24 UPPER, +3.4, #E6A93C, x=160, y=444
caption   The turn survives.       ui 36, #9A9A95,                    x=160, y=516
rule      1 px #242426, x 160 → 760, y=576
number    503                      mono_bold 160, #E7E6E2,            x=160, y=720
annot 1   · Retry-After            mono 26, #8B8B86,                  x=478, y=696
annot 2   Retrying · attempt 3/8   mono 26, #8B8B86,                  x=478, y=732
```

`503` is **neutral `#E7E6E2`, not amber and not red.** A 503 is the mechanism, not
the fault; the fault is already amber on the mark and on `PENDING`. A 160 px amber
`503` would read as an error code the size of a building, which is the exact
misreading this film exists to prevent — and it would push accent coverage past
the 3 % cap on its own. Neutral, large, and calm: the number is *equipment*.

The number and its two annotations are **one text object** (a big-number lockup,
craft §3.4), so the shot carries three text objects: the label, the caption, and
the lockup. Geometry, gutters and the 259 px clearance to the mark box are worked
out in §2.4.

**Copy.**

| text | words | on screen | reveal |
|---|---|---|---|
| `PENDING` | 1 | **f876 … f944** *(and it persists visually until C4 replaces it)* (full f884 → f944 = 61 f, margin 19) | opacity-only, 8 f `EASE_SOBER` |
| `The turn survives.` | 3 | **f882 … f1019** — **this line spans C3 and C4** (full f890 → f1019 = **130 f**) | opacity-only, 8 f `EASE_SOBER` |
| `503` *(readout, big number)* | — | **f892 … f967** (full f900 → f944 = 45 f in this shot) | **opacity-only, 8 f `EASE_SOBER`. No scale-in, no draw-on, no settle** |
| `· Retry-After` *(readout)* | — | **f898 … f970** (full f906) | opacity-only, 8 f `EASE_SOBER` |
| `Retrying · attempt 3/8` *(readout)* | — | **f902 … f973** (full f910) | opacity-only, 8 f `EASE_SOBER` |

**The 160 px numeral fades. It does not scale in.** A number that grows into place
is a celebration, and this one belongs to a hold (§2.7: no overshoot, no scale, no
`ARRIVE`, on anything held). The drama is that it is *already* that big when it
appears. Opacity only, 8 frames, `EASE_SOBER`, then still.

`The turn survives.` deliberately runs across the shot boundary into the
recovery. It is the only copy in the film that spans two shots, it is true in
both, and holding it across the release is what makes the release feel earned
rather than announced.

**The one mechanical event.** At **f930** the `3` in `attempt 3/8` becomes a `4`
— a **digit-in-place swap**, 4 f `EASE_SNAP`, no roll, no slide, no odometer.
JetBrains Mono is tabular so nothing reflows. That single character is the proof
that the retry budget is real and counting, and it is the only number that
changes in the entire film. Note the deliberate asymmetry: the film's *biggest*
number never moves, and its *smallest* one does. The 26 px digit is the only thing
in the frame with a pulse, so it is where the eye goes.

**Motion.** f870–f875 mark alone. f876 label. f882 caption. f886 rule draws on
(16 f `EASE_MOVE`). f892 the numeral. f898 / f902 the two annotations — a GROUP
under the lockup, on 4-frame staggers. f910–f929 static. f930 the digit.
f931–f944 static, and **the audio bed thins toward silence** — the anticipation
before the release.

**Colour.** Amber, one hue, and only on the mark and the `PENDING` label. Every
piece of type in the copy column below the label is neutral or muted. Accent
coverage ≈ 2.1 %, unchanged from C1 — the 160 px numeral adds a lot of ink and
**zero accent**, which is exactly why it can be that big.

**Honesty, non-negotiable, and this shot is where it is spent.** The status code
on screen is **503**. It is never 403. The words on screen are `PENDING`,
`Retry-After`, `Retrying · attempt 3/8`, `The turn survives.` The words `FAILED`,
`ERROR`, `403`, `DENIED`, `DROPPED`, `BLOCKED-AND-LOST` appear nowhere in this
film. `Retrying · attempt 3/8` is Claude Code's own native spinner string, which
is exactly the point: Tower does not invent a pending UI, it hands the request to
one that already exists.

**Deliberately empty.** No progress bar. No spinner. No countdown. No percentage.
No "please wait". The mark is already saying *held*, and duplicating that with a
second indicator would break "the mark is the state" (design.md §4.4.1).

---

### 4.12 · C4 `hold.clear` — f945 … f1019 (75 f) — `scene_hold.py`

**Idea:** *It clears itself and the turn resumes. Nobody restarts anything.*

**No cut.** Continuous from C3. This is the single most important structural
decision in the film: **nothing may cut between the hold and its release**, or a
viewer is free to assume someone intervened.

**Copy.**

| text | words | on screen | reveal |
|---|---|---|---|
| `The turn survives.` | — | **held, unchanged, from f882** | — |
| `PENDING` | — | exits **f960 … f967** | opacity-only, 8 f `EASE_SOBER` |
| `CLEARED` | 1 | enters **f962**, full f975 → f1019 = **44 f** ≥ 42 f floor | kinetic, 13 f `EASE_ENTER` — the state is good again, so the reveal may be kinetic |
| `503` *(big number)* | — | exits **f960 … f967** | opacity-only, 8 f `EASE_SOBER`. **It fades at its full size — it never shrinks away** |
| `· Retry-After` *(readout)* | — | exits **f963 … f970** | opacity-only, 8 f `EASE_SOBER` |
| `Retrying · attempt 4/8` *(readout)* | — | exits **f966 … f973** | opacity-only, 8 f `EASE_SOBER` |
| `Toronto, CA — inside CA` *(readout 1)* | — | enters **f972**, full f985, at Layout M's y=612 | kinetic, 13 f |
| `allowed 124200` *(readout 2)* | — | enters **f976**, full f989 | kinetic, 13 f. `124200` in `#E7E6E2` — the real end-of-recording counter from `footage.json` |

**Motion.**

| f | what |
|---|---|
| 945–959 | **15 frames of dead stillness.** The mark holds; the bed is at its quietest. The held silence before the resolve (craft §6.2) |
| **960** | **THE RECOVERY.** A multiple of 60 |
| **960–974** | **MORPH M5 · `holdGeo → verify`**, 15 f `SETTLE`. The contact + halo fade out (8 f `EASE_SOBER`); the ray **retracts into the hub** (12 f `EASE_MOVE`); the fence **expands r 15 → 33 and is absorbed into the outer ring**, alpha going to 0 as it arrives; the ring goes `#E6A93C` → `#E7E6E2` |
| 966–979 | the needle and wedge draw on from the hub, 13 f `EASE_MOVE` |
| 972– | blips 0.00 → 0.30, staggered 3 f |
| 975–1004 | **`verify` runs for 30 frames.** One full second of honest re-confirmation. Tower does not go straight from held to passing — it checks first, and the film shows it checking |
| **1005–1019** | **MORPH M1 · `verify → clear`** — the same 15 f `SETTLE` used at f262. The film's rhyme: the state that opened it is the state it recovers to. The spring **completes exactly on f1019**, so the cut to D1 at f1020 lands clean, never mid-spring |

The fence expanding into the ring reverses M3's ring-becoming-fence exactly. The
two shapes are the same circle at two radii, and watching it travel back out is
the sentence "the fence is no longer needed", spoken without a word.

**C4 also carries the film's scale release.** C3's 160 px `503` fades out on f967
and `CLEARED` — 24 px — arrives at f962 in the label slot. The frame goes from the
largest type in the film to the smallest in nine frames, without a cut and without
anything scaling. That drop is the visual of the pressure coming off, and it is
why the release does not need a flash, a checkmark or a colour change to read.
The copy column returns to plain **Layout M** from f972: label, caption, rule, two
readout lines. Layout M′ exists for 102 frames and never returns.

**The layouts do not overlap in time.** The numeral's box (x 160…448, y 605…720)
and readout 1's box (x 160…519, y 593…618) intersect, so their occupancy is
strictly sequenced: the numeral is at zero opacity from f967, readout 1 begins at
f972 — a 4-frame vacancy. Assert it; do not let the two windows drift together.

**Colour.** Amber → neutral over 15 frames. From f975 the frame is fully
neutral. **No green.** Nothing turns green when it recovers, because in the
product nothing does — `clear` is `#E7E6E2` and the passing radar is calm, not
celebratory.

**Deliberately empty.** No checkmark. No "resumed!". No flash. No burst of
allowed rows. The recovery is quiet because in the product it is quiet — you
don't watch it happen, you come back and it already did.

---

### 4.13 · D1 `end.set` — f1020 … f1079 (60 f) — `scene_end.py`

**Idea:** *All five states, one mark.*

**Cut in: the pure match cut.** On f1020 the label, the caption, the rule and
both readout lines vanish in a single frame. **The mark is bit-identical across
f1019 / f1020** — same centre, same size, same state, same phase. The only thing
that changes is that everything else stops existing.

**Layout.** The mark alone at the canonical circle. Columns 1–5 empty. **No copy
at all.**

**Copy.** None. Zero words. Amendment A's *"individually legible and individually
labelled"* requirement is discharged by the five dedicated beats — A3
(`VERIFYING`), A4 (`CLEARED`), B3 (`HOLD · CONNECTION`), B4 (`UNGUARDED`), C1
(`HOLD · LOCATION`) — each at hero scale with its own label and its own real
readout. D1 is the **recap**, and a recap that re-labels is a recap that doesn't
trust its own film.

**Motion — the run.** Ten equal 6-frame beats: five poses, five morphs, in the
identity study's canonical order, landing home.

| f | beat | detail |
|---|---|---|
| 1020–1025 | pose **`clear`** | continuous from C4 — no jump on the cut |
| 1026–1031 | morph → `verify` | 6 f `EASE_SNAP`. M1 reversed: needle draws out, wedge to 0.16, blips 0.80→0.30, pulse dies |
| 1032–1037 | pose **`verify`** | |
| 1038–1043 | morph → `holdNet` | 6 f `EASE_SNAP`. Ring neutral→amber and **solid → `(5,6)`**; core → amber; blips → 0 |
| 1044–1049 | pose **`holdNet`** | |
| 1050–1055 | morph → `holdGeo` | 6 f `EASE_SNAP`. **Ring dash `(5,6)` → solid** (it re-knits); core amber → neutral; the pings collapse into the fence at r 15; the ray and contact snap on |
| 1056–1061 | pose **`holdGeo`** | |
| 1062–1067 | morph → `off` | 6 f **`EASE_SOBER`** — entering a failure state is always sober. Ring amber→red, dash `(4,5)`→`(5,7)`; the fence, ray, contact and halo fade out; **the core hollows** — inner hole radius 0 → 3.5 while the outer goes 4.5 → 5.5; blips → flat 0.22 |
| 1068–1073 | pose **`off`** | dead still, and **silent** |
| 1074–1079 | morph → `clear` | 6 f `EASE_SNAP`. Red → neutral, dash `(5,7)` → solid, the core re-fills, blips 0.22 → 0.80, the pulse is born. **Lands exactly on f1079** so D2 opens on a settled `clear` |

The holdNet → holdGeo morph at f1050 is the one to get right: it is the *only*
place in the film where the ring re-knits from broken to solid, and it is the
same two-state difference C2 spent 90 frames teaching, replayed in six frames.
If the viewer's eye catches it, the film has landed.

**Colour.** One hue at a time, always: neutral (1020–1043), amber (1044–1061),
red (1062–1073), neutral (1074–1079). The amber→red morph passes through a
single interpolated orange — one hue, never two.

**Deliberately empty.** Everything. This is the emptiest shot in the film after
A1: one object, ≈88 % field, zero words, sixty frames.

---

### 4.14 · D2 `end.card` — f1080 … f1199 (120 f) — `scene_end.py`

**Idea:** *Tower. Here is where you get it.*

**Cut in:** hard cut. The mark relocates from (1290,540)/420 px to
(960,340)/200 px. Only a cut may move it — 330 px of travel is three times the
115 px cap, and a film that has never moved an element must not start now.

**Layout E**, centred, sanctioned.

```
mark      (960, 340), 200 px, clear, AT ITS REDUCE-MOTION STILL VALUES
          pulse frozen at r = 22 units (44 px), alpha 0.30. Nothing animates.
wordmark  TOWER         serif 200 wght 560, +12 px track, #E7E6E2, x=960 c, y=660
tagline   A control tower for your Claude agents.
                        ui 36 wght 400, #9A9A95,                  x=960 c, y=744
url       ghhrmnzdh.github.io/tower
                        mono 30, #8B8B86, with "tower" in #E7E6E2, x=960 c, y=852
```
Wordmark width = 5 ch · ≈130 + 4 · 12 = **698 px** → 611 … 1309. Tagline ≈684 px
→ 618 … 1302. URL 25 ch · 18 = **450 px** → 735 … 1185. Mark bottom 440;
wordmark cap top ≈ 516; 76 px of clearance.

**Copy.**

| text | words | on screen | reveal |
|---|---|---|---|
| `TOWER` | 1 | **f1083 … f1199** (full f1096 → f1199 = 104 f) | kinetic, 0.78 f/char over 5 chars, envelope 13 f `EASE_ENTER`, rise 28 px |
| `A control tower for your Claude agents.` | 7 | **f1086 … f1199** (full f1099 → f1199 = **101 f** ≥ 98 f floor, margin 3) | kinetic, span capped 10 f, 13 f `EASE_ENTER`, rise 5 px |
| `ghhrmnzdh.github.io/tower` *(url)* | — | **f1120 … f1199** (full f1136 → f1199 = 64 f = 2.13 s) | **`clip_reveal` left→right, 16 f `EASE_MOVE`** — a draw-on, not a fade |

The tagline is `brand.json.voice.lines[0]`, verbatim from README.md.

**On the URL.** The brief's shorthand was "tower.sh". **There is no `tower.sh`.**
The canonical URL in `site/index.html` is `https://ghhrmnzdh.github.io/tower/`
and the install one-liner is
`curl -fsSL https://ghhrmnzdh.github.io/tower/install.sh | sh`. The full curl
line is 48 characters and would push the frame to 14 visible words, over the
11-word ceiling — so the film shows the site, not the command; the command is one
click away and is the first thing on the page. **Do not print a domain that does
not resolve.** If a short domain is ever registered, swap this one string and
re-render D2; nothing else in the film depends on it.

**Motion.**

| f | what |
|---|---|
| 1080–1082 | the mark alone, **completely static**, 3 f |
| 1083 | the wordmark draws on, kinetic |
| 1086 | the tagline, 3 f behind — one choreographed GROUP |
| 1099–1119 | **21 frames static** |
| 1120–1136 | the URL wipes on, `clip_reveal` |
| **1176–1199** | **24 frames absolutely static.** No animation into the freeze (craft §6.12). The film ends on a hold, and the audio has already decayed to silence by f1176 |

**Colour.** Fully neutral. Zero accent. The film's last 120 frames contain no
amber and no red — it ends where it started, calm.

**Deliberately empty.** No button. No "download". No badge. No "available for
macOS". No feature list. No social icons. No QR code. Four objects: a mark, a
word, a line, an address.


---

## 5. THE COPY DECK

Every word in the film, in order. **51 words of copy** against craft §3.2's
ceiling of 60.

Two budgets are counted separately and both are capped:

* **Copy** — kickers, hero lines, captions, state labels, the wordmark, the
  tagline. Language the film is speaking. **Cap 60. Actual 51.**
* **Readout tokens** — strings drawn as the product's own readout. This is Tower
  speaking, not the film, and every one of them is a real observed value from
  `analysis/footage.json`. **Cap 40. Actual 30.**

The **11-words-visible-in-one-frame** ceiling applies to copy *and* readout
tokens together, and is checked per frame, not per shot.

**THE COUNTING CONVENTION — declare it once and use it everywhere.** A line that
is at full opacity on frames *a* through *b* **inclusive** is on screen for
`b − a + 1` frames. An earlier draft mixed `b − a + 1` and `b − a` from row to
row; under the stricter reading one line was actually *below* its floor and six
more had margin 0 or 1, which is not a margin, it is a rounding accident. The
floor in frames is `ceil(30 · max(1.40, 0.60 + 0.38·words))`, and this film now
requires **at least 2 frames of margin over the floor** on every line. Nothing
sits on the line.

| # | shot | tier | text (verbatim) | w | full-opacity frames | s | floor (f) | margin |
|---|---|---|---|---|---|---|---|---|
| 1 | A2 | kicker | `CHECK ONE` | 2 | f121 – f179 (59) | 1.97 | 42 | **+17** |
| 2 | A2 | hero | `Where you are.` | 3 | f124 – f179 (56) | 1.87 | 53 | **+3** |
| 3 | A3 | state label | `VERIFYING` | 1 | f199 – f254 (56) | 1.87 | 42 | **+14** |
| 4 | A4 | state label | `CLEARED` | 1 | f283 – f329 (47) | 1.57 | 42 | **+5** |
| 5 | A4 | caption | `Confirmed in-country.` | 2 | f286 – f329 (44) | 1.47 | 42 | **+2** |
| 6 | B1 | kicker | `CHECK TWO` | 2 | f349 – f419 (71) | 2.37 | 42 | **+29** |
| 7 | B1 | hero | `How the wire is.` | 4 | f352 – f419 (68) | 2.27 | 64 | **+4** |
| 8 | B2 | state label | `SLOW LINK · STILL ALLOWED` | 4 | f443 – f509 (67) | 2.23 | 64 | **+3** |
| 9 | B3 | state label | `HOLD · CONNECTION` | 2 | f548 – f614 (67) | 2.23 | 42 | **+25** |
| 10 | B3 | caption | `No usable path.` | 3 | f554 – f614 (61) | 2.03 | 53 | **+8** |
| 11 | B4 | state label | `UNGUARDED` | 1 | f632 – f689 (58) | 1.93 | 42 | **+16** |
| 12 | B4 | caption | `Claude connects directly.` | 3 | f635 – f689 (55) | 1.83 | 53 | **+2** |
| 13 | C1 | state label | `HOLD · LOCATION` | 2 | f736 – f779 (44) | 1.47 | 42 | **+2** |
| 14 | C2 | state label | `HOLD · CONNECTION` | 2 | f792 – f869 (78) | 2.60 | 42 | **+36** |
| 15 | C2 | state label | `HOLD · LOCATION` | 2 | f796 – f869 (74) | 2.47 | 42 | **+32** |
| 16 | C2 | caption | `Tower tells you which.` | 4 | f804 – f869 (66) | 2.20 | 64 | **+2** |
| 17 | C3 | state label | `PENDING` | 1 | f884 – f944 (61) | 2.03 | 42 | **+19** |
| 18 | C3–C4 | caption | `The turn survives.` | 3 | f890 – f1019 (130) | 4.33 | 53 | **+77** |
| 19 | C4 | state label | `CLEARED` | 1 | f975 – f1019 (45) | 1.50 | 42 | **+3** |
| 20 | D2 | wordmark | `TOWER` | 1 | f1096 – f1199 (104) | 3.47 | 42 | **+62** |
| 21 | D2 | tagline | `A control tower for your Claude agents.` | 7 | f1099 – f1199 (101) | 3.37 | 98 | **+3** |
| | | | **total copy** | **51** | | | | ≤ 60 ✓ |

Note the kicker floor. craft §3.3 lets a kicker off with 1.00 s, but this film
applies the universal 1.40 s / 42 f floor to every line including the two
kickers — they clear it by 17 and 29 frames anyway, so the exemption was never
load-bearing and carrying it would only create a second rule to check.

**Readout strings** (the product's voice — every value real):

| shot | text | tokens | frames | source |
|---|---|---|---|---|
| A3 | `Confirming location…` | 2 | f211 – f269 | `GuardStatus` "Blocking — confirming location…" |
| A4 | `Toronto, CA — inside CA` | 4 | f291 – f727 (spans A4→C1) | `LocationRow`, footage.json |
| B2 | `net 82 ms · api 273 ms` | 6 | f463 – f535 | footage.json t=40, popover `fmtMs` format |
| B3 | `internet down` | 2 | f560 – f614 | TUI NETWORK card, offline line |
| C1 | `Tehran, IR — outside CA` | 4 | f736 – f779 | footage.json off-country reading |
| C3 | `503` *(big number)* | 1 | f900 – f967 | `towerd` block response, README |
| C3 | `· Retry-After` | 1 | f906 – f970 | the `Retry-After` header the 503 carries |
| C3 | `Retrying · attempt 3/8` → `4/8` | 3 | f910 – f973 | Claude Code's own retry spinner |
| C4 | `Toronto, CA — inside CA` | 4 | f985 – f1019 | as above |
| C4 | `allowed 124200` | 2 | f989 – f1019 | footage.json final `guard.allowed` |
| D2 | `ghhrmnzdh.github.io/tower` | 1 | f1136 – f1199 | `site/index.html` canonical |
| | **total** | **30** | | ≤ 40 ✓ |

(The earlier draft's header said 33 and its table footed to 32; the column sums
to **30**. Splitting `503 · Retry-After` into a 160 px numeral and a 26 px
annotation does not change the count — one 2-token string became a 1-token and a
1-token one.)

**Per-frame word check** — the worst frame of every shot, copy + readout:

| shot | worst frame | words | ≤11 |
|---|---|---|---|
| A1 | any | 0 | ✓ |
| A2 | f130 | 5 | ✓ |
| A3 | f220 | 1 + 2 = 3 | ✓ |
| A4 | f300 | 3 + 4 = 7 | ✓ |
| B1 | f380 | 6 | ✓ |
| B2 | f480 | 4 + 6 = **10** | ✓ |
| B3 | f580 | 5 + 2 = 7 | ✓ |
| B4 | f660 | 4 + 0 = 4 | ✓ |
| C1 | f750 | 2 + 4 = 6 | ✓ |
| C2 | f830 | 8 + 0 = 8 | ✓ |
| C3 | f920 | 4 + 5 = 9 | ✓ |
| *(C3 detail)* | `PENDING` 1 + `The turn survives.` 3 · `503` 1 + `· Retry-After` 1 + `Retrying · attempt 3/8` 3 | | |
| C4 | f1000 | 4 + 6 = **10** | ✓ |
| D1 | any | 0 | ✓ |
| D2 | f1150 | 8 + 1 = 9 | ✓ |

**Words the film may never contain**, asserted as a string scan over the
manifest: `403` · `FAILED` · `FAIL` · `ERROR` · `DENIED` · `DROPPED` · `BLOCKED`
(as a verdict on a Claude turn) · `VPN` (as a description of Tower) · `firewall`
· `kill switch` · `secure` · `encrypted` · `private` · `notarized` · `Windows` ·
`Intel` · `Linux` · any running-agent count · any IP address · any dollar figure
· any personal name.

**Register check.** Every line is a short declarative. Nothing exclaims, nothing
promises, nothing sells. Four lines are verbatim product strings, three are
verbatim from README, and the rest are two-to-four-word statements of fact. The
film never says Tower is good; it shows Tower being accurate, including when the
news is bad.

---

## 6. AUDIO HIT POINTS

Amendment C: *"the music should be more minimal, changes in ui should have nice
sound effects."* This is not a score. It is a near-silent bed plus designed UI
sound effects landing on exact frames. **Silence is the default; sound is the
exception.**

Frame *f* begins at `t = f / 30` seconds. Every cue below is scheduled at the
**first sample of its frame** and its transient must land there — pre-roll goes
before the frame boundary, never after.

### 6.1 The bed

A single band-limited noise floor, 120–900 Hz, no pitch, no rhythm, no melody,
**−42 dBFS**. It is the room the machine is in. It is not music and it never
develops.

| frames | bed |
|---|---|
| 0 – 614 | −42 dBFS, flat |
| **615 – 689** | **TRUE SILENCE.** Hard duck on f615, 0 ms. This is the `off` shot |
| 690 – 929 | −42 dBFS returns on f690 |
| 930 – 959 | thins to −54 dBFS by f959 (the anticipation before the recovery) |
| 960 – 1135 | −42 dBFS |
| 1136 – 1175 | decays to silence over 40 f |
| **1176 – 1199** | **TRUE SILENCE.** The film ends silent and static |

Three state textures ride on the bed, each at **−48 dBFS**, each locked to the
mark's own period so the ear learns the same rhythm the eye is watching:

| texture | frames | period | character |
|---|---|---|---|
| `TEX_SWEEP` | 70 – 261, 975 – 1004 | 2.400 s | a barely-there rotating air, one revolution per sweep |
| `TEX_PING` | 540 – 614, 805 – 843 | 1.4286 s | two soft filtered taps per cycle, half a period apart, matching the sonar exactly |
| `TEX_FENCE` | 735 – 779, 836 – 959 | 8.000 s sweep + 2.856 s tap | a slow band-passed air for the fence, plus one soft dry tap per lunge |

The two C2 windows overlap by design only across the 8-frame crossfade
f836–f843, which is the same 8 frames as the visual attention swap. Outside that
window exactly one texture is audible, mirroring "one loudest thing" in the ear.
`TEX_FENCE` is absent f780–835 (the right mark is frozen and silent) and returns
with the swap.

### 6.2 The sound vocabulary

Nine sounds. Every one is a soft transient plus a short tuned body — well-designed
OS feedback, not a synth. **No beeps, no stabs, no melody, no reverse cymbals, no
risers, no braams, no musical phrase anywhere.**

| name | length | character |
|---|---|---|
| `SFX_DRAW` | 380 ms | filtered noise swell with no pitch centre; the sound of a line being made |
| `SFX_SEAT` | 160 ms | a soft transient with a low, quickly-damped body; something mechanical seating into place |
| `SFX_LATCH` | 140 ms | the film's **pass** sound. Soft transient, short tuned body, resolves *down* a whole tone. Used only when a state becomes good |
| `SFX_HOLD` | 180 ms | the film's **hold** sound. A damped low knock. No rise, no shimmer, no alarm. It is pending, not broken |
| `SFX_HOLD_GEO` | 220 ms | the same knock, tuned **a minor third below** `SFX_HOLD` and 40 ms longer. The ear must be able to tell holdNet from holdGeo blind |
| `SFX_TYPE` | 40 ms | an extremely quiet air tick. **One per line, never one per character** |
| `SFX_RULE` | 200 ms | a fine sweep travelling with the hairline, panned with it |
| `SFX_TICK` | 30 ms | a single dry tick. Digits and pose changes only |
| `SFX_DEAD` | 25 ms | one dry click with **no body and no tail**. The sound of something stopping |

### 6.3 The exhaustive hit list

Every state change, every mark transition, every element entrance that deserves a
sound. **The audio author builds to this list and nothing else.**

| frame | t (s) | cue | dB | what is happening on screen |
|---|---|---|---|---|
| 12 | 0.400 | `SFX_DRAW` | −24 | the outer ring begins drawing on |
| 48 | 1.600 | `SFX_SEAT` | −22 | the core seats into the hub |
| 60 | 2.000 | `SFX_TICK` ×3 @ 60/63/66 | −38 | the three blips arrive, staggered |
| 70 | 2.333 | `TEX_SWEEP` in | −48 | the state resolves to `verify`; the sweep starts turning |
| 90 | 3.000 | — | — | **hard cut. No cue.** A cut with a sound on it is a cut you notice |
| 108 | 3.600 | `SFX_TYPE` | −30 | kicker `CHECK ONE` |
| 111 | 3.700 | `SFX_TYPE` | −26 | hero `Where you are.` — slightly fuller than the kicker's |
| 180 | 6.000 | — | — | hard cut |
| 186 | 6.200 | `SFX_TYPE` | −30 | label `VERIFYING` |
| 192 | 6.400 | `SFX_RULE` | −28 | the hairline draws on, panned L→R with it |
| 198 | 6.600 | `SFX_TYPE` | −32 | readout `Confirming location…` |
| 261 | 8.700 | `TEX_SWEEP` out | — | fades under the latch, one frame ahead of it |
| **262** | **8.733** | **`SFX_LATCH`** | **−18** | **MORPH M1 — `verify → clear`. The film's first state change and its first pass sound** |
| 270 | 9.000 | `SFX_TYPE` | −30 | `CLEARED` enters |
| 273 | 9.100 | `SFX_TYPE` | −32 | caption `Confirmed in-country.` |
| 278 | 9.267 | `SFX_TYPE` | −34 | readout `Toronto, CA — inside CA` |
| 330 | 11.000 | — | — | hard cut |
| 336 | 11.200 | `SFX_TYPE` | −30 | kicker `CHECK TWO` |
| 339 | 11.300 | `SFX_TYPE` | −26 | hero `How the wire is.` |
| 420 | 14.000 | — | — | hard cut (the match cut — deliberately silent, so the eye notices the mark is unchanged) |
| 426 | 14.200 | `SFX_RULE` | −28 | the hairline |
| 430 | 14.333 | `SFX_TYPE` | −28 | label `SLOW LINK · STILL ALLOWED` — **the first amber on screen. No hold sound: nothing is being held** |
| 450 | 15.000 | `SFX_TYPE` | −32 | readout `net 82 ms · api 273 ms` |
| **525** | **17.500** | **`SFX_HOLD`** | **−16** | **MORPH M2 — `clear → holdNet`. The ring breaks. The film's first hold sound** |
| 540 | 18.000 | `TEX_PING` in | −48 | ping #1 joins; the sonar doubles |
| 540 | 18.000 | `SFX_TYPE` | −30 | label `HOLD · CONNECTION` |
| 546 | 18.200 | `SFX_TYPE` | −32 | caption `No usable path.` |
| 552 | 18.400 | `SFX_TYPE` | −34 | readout `internet down` |
| **615** | **20.500** | **BED → TRUE SILENCE** | — | **hard cut into 6 empty frames. Everything stops** |
| **621** | **20.700** | **`SFX_DEAD`** | **−20** | **the `off` mark fades up. One dry click, no body, no tail** |
| 622 – 689 | 20.73 – 23.0 | — | — | **68 frames of absolute silence.** The loudest passage in the film. Note it starts at f622, one frame after the click — `SFX_DEAD` is 25 ms and has no tail, so it is over inside its own frame. The label at f624 and the caption at f627 are **silent**: nothing sounds in this shot after the click |
| 690 | 23.000 | bed returns | −42 | hard cut; the guard is restored |
| 696 | 23.200 | `SFX_RULE` | −28 | the hairline |
| 702 | 23.400 | `SFX_TYPE` | −32 | readout `Toronto, CA — inside CA` |
| **720** | **24.000** | **`SFX_HOLD_GEO`** | **−14** | **MORPH M3 — `clear → holdGeo`, and the readout flips to `Tehran, IR — outside CA` on the same frame. The single biggest hit in the film. A minor third below f525's knock — the ear is being taught the difference** |
| 728 | 24.267 | `SFX_TYPE` (dulled) | −32 | label `HOLD · LOCATION`, sober |
| 735 | 24.500 | `SFX_RULE` (short, descending) | −30 | the ray draws outward from the hub |
| 735 | 24.500 | `TEX_FENCE` in | −48 | the fence begins turning |
| 750 | 25.000 | `SFX_TICK` | −26 | the off-country contact lands |
| 780 | 26.000 | — | — | hard cut to the pair |
| 784 | 26.133 | `SFX_TYPE` | −30 | left label |
| 788 | 26.267 | `SFX_TYPE` | −30 | right label, 4 f behind |
| 791 | 26.367 | `SFX_TYPE` | −28 | caption `Tower tells you which.` |
| 805 | 26.833 | `TEX_PING` solo | −44 | **left live.** Only the sonar is audible |
| **836** | **27.867** | **texture crossfade** | — | `TEX_PING` → `TEX_FENCE` over 8 f, matching the visual attention swap exactly (f836–843) |
| 844 | 28.133 | `SFX_TICK` | −34 | the attention lands on the right |
| 870 | 29.000 | — | — | hard cut |
| 876 | 29.200 | `SFX_TYPE` | −30 | label `PENDING` |
| 882 | 29.400 | `SFX_TYPE` | −28 | caption `The turn survives.` |
| 886 | 29.533 | `SFX_RULE` | −28 | the hairline |
| **892** | **29.733** | **`SFX_SEAT`** | **−22** | **the 160 px `503` appears.** The film's only big number, and the only place `SFX_SEAT` is used between the core at f48 and the wordmark at f1083. Same sound, three times, always for "an object exists now" |
| 898 | 29.933 | `SFX_TYPE` | −34 | annotation `· Retry-After` |
| 902 | 30.067 | `SFX_TYPE` | −34 | annotation `Retrying · attempt 3/8` |
| **930** | **31.000** | **`SFX_TICK`** | **−24** | **the digit 3 → 4. One dry tick. The sound of the retry budget counting, and the only number that moves in the film** |
| 930 – 959 | 31.0 – 32.0 | bed thins to −54 | — | anticipation |
| 959 | 31.967 | `TEX_FENCE` out | — | under the release, one frame ahead of it |
| **960** | **32.000** | **`SFX_LATCH` (release variant)** | **−16** | **MORPH M5 — the hold lets go. The transient is soft and the body resolves *upward* a whole tone: the inverse of `SFX_HOLD`. This is the only upward gesture before the end.** The 160 px `503` fades out on the same frame, unaccompanied — the biggest object in the film leaves in silence |
| 966 | 32.200 | `SFX_RULE` (short) | −30 | the ray retracts; the hairline stays |
| 972 | 32.400 | `SFX_TYPE` | −30 | `CLEARED` |
| 975 | 32.500 | `TEX_SWEEP` in | −48 | 30 frames of re-confirmation |
| 976 | 32.533 | `SFX_TYPE` | −32 | readout `allowed 124200` |
| **1005** | **33.500** | **`SFX_LATCH`** | **−18** | **MORPH M1 again — `verify → clear`. Identical to f262. The film's audio rhyme: it ends the way it began** |
| 1020 | 34.000 | — | — | the match cut. **Silent by design** — nothing changed but the emptiness |
| 1026 | 34.200 | `SFX_TICK` | −30 | pose → `verify` |
| 1038 | 34.600 | `SFX_TICK` | −28 | pose → `holdNet` |
| 1050 | 35.000 | `SFX_TICK` | −26 | pose → `holdGeo` — the ring re-knits |
| 1062 | 35.400 | `SFX_DEAD` | −24 | pose → `off` |
| 1068 – 1073 | 35.6 – 35.8 | **silence** | — | the `off` pose is always silent |
| 1074 | 35.800 | `SFX_LATCH` | −20 | pose → `clear`. Home |
| 1080 | 36.000 | — | — | hard cut to the card |
| **1083** | **36.100** | **`SFX_SEAT` (long body)** | **−16** | **the wordmark. The fullest sound in the film — and still just a transient with a body. No chord, no chime, no logo sting** |
| 1086 | 36.200 | `SFX_TYPE` | −28 | the tagline |
| 1120 | 37.333 | `SFX_RULE` | −26 | the URL wipes on, panned L→R |
| 1136 – 1175 | 37.9 – 39.2 | bed decays to silence | — | |
| **1176 – 1199** | **39.2 – 40.0** | **TRUE SILENCE** | — | **24 frames, static picture, no sound. The film ends on a hold** |

**Cue count:** **54** discrete hits in 1200 frames (counting `SFX_*` only; bed
moves and `TEX_*` fades are not hits) — one every 0.74 s on average, and they are
deliberately not evenly spread:

| | |
|---|---|
| densest passage | **C3, 7 hits in 75 frames** (f876–930) — the shot where the mechanism is explained |
| C1 | 6 hits in 90 frames |
| B3 | 4 hits in 105 frames |
| **longest silence** | **f622 – f689, 68 consecutive frames** |
| second longest | f1176 – f1199, 24 frames, and the film ends there |

**The list above is sorted by frame and must stay sorted.** An earlier draft had
three rows out of order (a `TEX_SWEEP` out at f261 printed after f278, a
`TEX_FENCE` out at f959 printed after f976), which is a trap in a document whose
own instruction is "the audio author builds to this list and nothing else". Every
row is now in ascending frame order, and where a texture fades *under* a hit it
is printed on the frame before it.

**Rules the audio author may not break.**

1. **A hard cut never carries a sound of its own.** Sounds land on *changes*, not
   on edits. f90, f180, f330, f420, f690, f780, f870, f1020 and f1080 are all
   silent frames.
2. **Nothing rises.** No riser, no whoosh, no swell into a cut. The film's
   tension comes from the bed thinning and from silence, never from a build.
3. **A hold never sounds like an alarm.** `SFX_HOLD` and `SFX_HOLD_GEO` are
   knocks that damp immediately. If it sounds urgent, it is wrong — the product's
   whole point is that a hold is not an emergency.
4. **The `off` state is silent.** Both times.
5. **Loudness:** integrated −20 LUFS, true peak ≤ −3 dBTP, and the whole piece
   must remain intelligible at −30 dB monitoring. It is designed to be watched
   quietly.
6. Delivered as `promo/film/media/film.wav`, 48 kHz 16-bit stereo, **exactly
   1 920 000 samples = 40.000 s**, synthesised with numpy only — no samples, no
   scipy, no external libraries, and fully deterministic.


---

## 7. WHY THIS ISN'T THE OLD FILM

The user's verdict on `promo/` was *"too messy and people can not focus."*
craft.md §8 turns that into 24 named failures, every one of which the old cut
actually committed. For each, the specific structural choice here that makes it
impossible — not "we'll be careful", a structural impossibility.

| # | old-film failure | the structure that prevents it |
|---|---|---|
| 1 | **Captured pixels** | There is no footage in the pipeline. `promo/film/` never opens an image file; `core.py` exposes no loader. The only inputs are three font files. |
| 2 | **Content touching a frame edge** (`TOW…` clipped at x=0, `…da` at x=1919) | Every element in §4 has an explicit bbox and the widest object in the film is the 698 px wordmark. The mark's box is `(1080,330)→(1500,750)` — 260 px of clearance. `safe_ring_clean()` fails the *build*, not the review. |
| 3 | **Mid-word clipping** (`A control tower for your Claude ag`, `owhere in the tree`, `Fabl`) | Nothing is ever cropped because nothing is ever zoomed. There is no camera in this film — not one push, not one scale, not one crop. Every string's rendered width is computed and asserted against its column in §4. |
| 4 | **Type over live UI text** (`"The wire was fine."` on `Usage paused — location not confirmed`) | Layout M puts copy in columns 1–4 and the mark in columns 6–8, disjoint on **x** with a 140 px gutter that is never narrower than 496 px in practice. Layout H has no UI at all. They cannot reach each other. |
| 5 | **Scrim-as-a-fix** (`super_scrim()`, the 0.94-alpha plate) | There is no plate anywhere in the film, because there is no type sitting on busy pixels. `core.py` deliberately does not port `super_scrim` or the `draw_stat` backing plate. If someone needs one, the layout is wrong. |
| 6 | **Cross-dissolve of dense layers** (a 200 px `TOWER` ghosted over a populated terminal) | **Zero dissolves in the film**, asserted in the manifest. The three places a dissolve would have been reached for are morphs (A4, B3, C4); the two chapter changes are match cuts (B2, D1); the one gap is 6 empty frames (B4). |
| 7 | **Overlay pile-up** (a HUD + a caption strip + a TUI + a ghosted super + a mask + a traffic log, simultaneously) | Max **two** overlay families and **three** text objects per frame, and §5 tabulates the worst frame of all fourteen shots: the maximum is 10 words and 2 families. Nine of fourteen shots carry exactly one mark, one label, one caption. |
| 8 | **Always-on chrome** | There is no persistent element in this film. No HUD, no corner badge, no watermark, no logo bug, no progress bar, no timecode. The mark itself disappears twice, for 90 frames each time (A2 and B1) — even the identity is not always-on. |
| 9 | **Corner brackets / reticles / targeting language** | The film draws exactly **three** kinds of object — the radar mark, type, and a 1 px rule — and nothing else (§2.11). Tower is an honest status layer, not a weapons HUD. |
| 10 | **CRT / retro effects** | `grade_static(vig=0.32, pitch=0, scan_a=0.0)` — scanlines off at the API level. No chromatic aberration, no RGB split, no glitch, no flare, no leak. The grade is a 0.32 vignette and 1-unit grain, and nothing else. |
| 11 | **Speed ramps** | Nothing is retimed because nothing is recorded. Every value is authored at 30 fps as a function of the integer frame index. Speed *contrast* is achieved structurally — 18 empty frames before A2's kicker, 6 before B1's; 15-frame morphs in the acts, 6-frame morphs in the recap. |
| 12 | **Heavy vignette** | 0.32, against the old film's 0.55, asserted in the grade call. |
| 13 | **Fake window chrome / third-party UI** (a real Terminal title bar, a real macOS menu) | The film contains no window, no title bar, no tab strip, no traffic lights, no terminal frame, no popover frame, no panel, no card. Tower's surfaces appear only as their *content* — a state label, a readout line, a hairline — abstracted into the film's own language. |
| 14 | **Redaction** (`PRIVACY MASK` plates, `***.***.***.***`) | No IP appears anywhere, redacted or otherwise. Nothing was captured, so there is nothing to hide, and a redaction bar tells the viewer you were hiding something. The city/country/ISP-class facts that *are* the product's point appear in full: `Toronto, CA`, `Tehran, IR`, `outside CA`. |
| 15 | **Text below 20 px or 55 % alpha** | The smallest glyph in the film is the 20 px kicker. The lowest alpha any text reaches is 0.55, and only on the dimmed label in C2's spotlight. Both are asserted per frame. |
| 16 | **Bounce on a hold / block / off / failure** | Every amber and red element in the film enters and exits on `EASE_SOBER`, opacity-only, 8 frames, and then stops. The morphs into `holdNet`, `holdGeo` and `off` use `SETTLE` (0.63 % overshoot) or `EASE_SOBER` (0 %). The only overshoot anywhere is `ARRIVE` on the neutral core at f48. |
| 17 | **Red for "outside target"** | C1's flip is `#E7E6E2 → #E6A93C`. The label is `HOLD · LOCATION` in amber, the readout clause `outside CA` is amber. Red appears only where routing is *off* (B4, D1) — the state where Tower is not guarding at all. |
| 18 | **"degraded ⇒ blocked", `403`, "failed" for a held request** | B2 exists for exactly this: a slow link, an amber *label*, and a **neutral mark** — the radar does not move, because a degraded link still passes. C3 shows `503 · Retry-After` and `Retrying · attempt 3/8` and says `The turn survives.` The strings `403`, `FAILED` and `ERROR` are in the banned-word scan in §5. |
| 19 | **Two things moving at once / a push plus a dissolve** | There is no camera, so a push is impossible. Simultaneous motion is permitted only inside a single choreographed entrance group (§2.8) — same idea, opacity and ≤17 px rise only, 3–4 frame stagger. C2 enforces it hardest: two marks on screen, never both animating, with an explicit 8-frame attention swap. |
| 20 | **Decorative loops when the state is fine** | The only motion in a passing frame is the mark's own `clear` pulse at α ≤ 0.5 on a 2.381 s cycle — the maximum idle loop the design system permits. There are no particles, no drifting gradients, no breathing backgrounds, no waveform, no slow push. D2's end card freezes the pulse at its Reduce-Motion still values: **the last 120 frames contain no animation at all.** |
| 21 | **>6-word hero, wrapped hero, >3 tiers, >11 words** | Heroes are 3 and 4 words, one line each. Max tiers in any shot is 3 (label + caption + readout). Max words in any frame is 10, tabulated per shot in §5. Film total: 51 copy words against a ceiling of 60. |
| 22 | **Unseeded randomness, clock reads, frame-order dependence** | `render(f, im)` is a pure function of `f` by contract (§2.1). The grain plates are pre-rolled from `RandomState(1917)` and indexed by `f % 12`. The determinism check hashes every frame twice at `-j 1` and `-j 8` and fails the build on any difference. |
| 23 | **New dependencies** | numpy 1.26.4, Pillow 10.1.0, Python stdlib, ffmpeg 7.0.1. Nothing else. The audio is numpy + `wave`. |
| 24 | **Touching `promo/*.py`** | Everything new lives in `promo/film/`. The old pipeline is read for technique (`overlays.py`'s `font()`, `Layer`, `bfill`, `clip_reveal`, `draw_kinetic`, `dash_arc`, `render_radar`, `_digit_cell`, `_frame_buckets`) and copied into `core.py` — never imported, never edited. |

And the three failures the user named directly:

* **"Cropped text bleeding off frame edges"** → there is no camera and no crop.
  Every glyph is drawn once, at its native size, inside `(160,120)→(1760,960)`.
* **"Cross-dissolves ghosting two dense UI layers"** → zero dissolves, and no
  frame in the film contains two dense layers to begin with. The densest frame in
  the film is C2, which is two marks and three short lines.
* **"Subtitles landing on top of live UI text"** → copy and mark occupy disjoint
  column ranges, permanently, by construction.

---

## 8. THE CANONICAL FIXTURE

One fixture. No shot invents its own numbers. Every value below is a real
observed reading from `analysis/footage.json`, and the whole film is internally
consistent with a single 40-second story: a machine in Toronto, on a real link,
that briefly appears in Tehran and comes back.

```python
FIXTURE = {
    "target_cc":     "CA",
    "home_city":     "Toronto",   "home_cc": "CA",
    "away_city":     "Tehran",    "away_cc": "IR",
    "net_ms":        82,          # footage t=40, online
    "api_ms":        273,         # footage t=40, online
    "offline_line":  "internet down",
    "status_code":   503,
    "retry_from":    3, "retry_to": 4, "retry_max": 8,
    "allowed_final": 124200,      # footage t=86, real endpoint
    "url":           "ghhrmnzdh.github.io/tower",
}
```

Never shown, anywhere, ever: an IP address, a dollar figure, a token count, a
plan percentage, an agent name, a running-agent count, a project path, a person's
name, a timestamp, a macOS clock, a window, or a third-party string.

**Why no plan meters.** `do_not_claim` #18: usage numbers may never be shown
while the guard is holding. The film spends 255 of its 1200 frames in a hold, and
a meter in any adjacent shot would invite the viewer to carry it across the cut.
The honest, simple answer is that this film is not about usage — one idea per
shot, one argument per film.

---

## 9. BUILD-TIME ASSERTIONS

`promo/film/check.py` runs these. A shot that fails `manifest_lint()` does not
render; a frame that fails `safe_ring_clean()` fails the build.

**Manifest**

```
sum(dur for shots) == 1200
ranges tile 0..1199 exactly, no gap, no overlap
each module's shots form ONE contiguous range
for every shot: f_in % 15 == 0  and  36 <= dur <= 165
the three structural landmarks are 720, 960, 1020 and each is % 60 == 0
every shot declares idea <= 8 words
sum(copy words) <= 60          # actual 51
sum(readout tokens) <= 40      # actual 30

# reading floor. INCLUSIVE frame count: a line full-opacity on frames a..b
# occupies b - a + 1 frames. Do not use b - a anywhere.
floor_f(words) = ceil(30 * max(1.40, 0.60 + 0.38 * words))
per line: (last_full - first_full + 1) >= floor_f(words) + 2      # >= 2 f margin
                                                                  # min actual margin: +2

# entrance patterns (§2.8) -- every animated text entrance is tagged one of these
GROUP: members staggered 3 or 4 f, all inside a 12 f window
RELAY: incoming.first_frame > outgoing.last_frame     # strict; never equal
assert no two strings are simultaneously non-zero-alpha in the same slot
assert no two elements with intersecting bboxes are simultaneously non-zero-alpha
       # catches C3's 160 px `503` against C4's readout 1 at y=612

per shot: <= 1 accent hue, <= 3 text objects, <= 2 overlay families
       # C3's big-number lockup (503 + 2 annotations) counts as ONE text object
accent_frames_amber == 464 and accent_frames_red == 87   # §2.6, recount if retimed
dissolve_count == 0
banned-word scan over all copy and readout strings passes
audio hit list is sorted strictly ascending by frame
```

**Per frame**

```
field_frac      >= 0.62   (>= 0.78 on A2, B1, D1, D2)
ink_frac        <= 0.25   (<= 0.12 on A2, B1, D1, D2)
accent_frac     <= 0.03
hue_count       <= 1
safe_ring_clean == True    # 96 px ring, max |dluma| <= 10
black_point     in 10..14  # never 0
banding         <= 40 px max run of identical luma in the field
words_visible   <= 11
min_glyph_px    >= 20
min_text_alpha  >= 0.55
```

**Determinism**

```
sha256(frame f) identical across two runs
sha256(frame f) identical at -j 1 and -j 8
no module reads time, os.environ, or an unseeded RNG   (AST scan)
```

**The one-frozen-frame test, run by eye on a contact sheet** (1 still every 15
frames, 10 × 8 grid): **pause anywhere. You must be able to name the guard state
from that single frame, and read every word on it.** If you can't, the
composition is wrong — not the rule. This is Reduce Motion discipline applied to
composition, and it is the direct, literal fix for *"too messy and people can not
focus."*

**Reduce-Motion render path.** `REDUCE=1` produces a valid 1200-frame output in
which every mark uses its documented still values (design.md §2.5–2.9) and every
transition becomes a 6-frame `EASE_IN_OUT` fade. It may never ship, but it must
build — having it forces every composition to survive being frozen, which is
exactly the discipline the old film lacked.

---

## 10. THE NINE-POINT CHECK, PER SHOT

Print this next to the shot list. Every shot passes all nine or it is wrong.

1. **The mark is the state.** Exactly one radar in frame (two in C2, by design),
   and its state is the literal truth of what the copy says at that instant. No
   decorative mark, no contradicting logo bug, no sixth state.
2. **Motion = state change.** Every moving pixel corresponds to a state changing.
   Nothing moves for atmosphere.
3. **One loudest thing.** Exactly one element animating above 0.3 alpha
   amplitude; everything else still.
4. **Failure never bounces.** Every amber/red/hold/off beat: `EASE_SOBER`, 8
   frames, then dead still.
5. **Legible in one frozen frame.**
6. **Nothing is cropped.** Ever.
7. **No cross-dissolve.** Zero in the film.
8. **The quiet state is quiet.** The `clear` pulse at α ≤ 0.5 is the only idle
   loop permitted, and D2 doesn't even have that.
9. **Honest.** Off-country is amber. A degraded link still passes. A block is
   503 + PENDING. The passing radar is neutral, not green. Nothing from
   `brand.json.do_not_claim` appears in copy or in imagery.

---

## 11. THE TEMPO AUDIT — is this exciting, or is it a tasteful screensaver?

The brief asks for "completely exciting". A minimal film gets there through
control, not decoration, but control is measurable, so measure it. This section
exists because the honest answer to that question, for an earlier draft of this
document, was *"it is a tasteful screensaver from f420 to f1019"* — 600 frames,
twenty seconds, one composition, one type scale, one tempo, in the middle of the
film, on the film's most important idea.

### 11.1 Tempo per shot

`events` counts discrete visible changes (an entrance, an exit, a morph, a
draw-on, a digit). `still` is the longest run of frames in which nothing changes
except a mark's own loop.

| shot | f | dur | events | longest still run | subject scale | tempo |
|---|---|---|---|---|---|---|
| A1 | 0 | 90 | 6 | 7 | 420 px mark | slow build |
| A2 | 90 | 90 | 2 | 56 | 120 px type | **held** |
| A3 | 180 | 75 | 3 | 44 | 420 px mark | settle |
| A4 | 255 | 75 | 6 | 38 | 420 px mark | change |
| B1 | 330 | 90 | 2 | 68 | 120 px type | **held** |
| B2 | 420 | 90 | 3 | 47 | 420 px mark | settle |
| B3 | 510 | 105 | 7 | 54 | 420 px mark | **change** |
| B4 | 615 | 75 | 3 | 55 | 420 px mark | **dead stop** |
| C1 | 690 | 90 | 8 | 21 | 420 px mark | **busiest** |
| C2 | 780 | 90 | 7 | 26 | two 300 px marks | comparison |
| C3 | 870 | 75 | 7 | 20 | **160 px numeral** | **explain** |
| C4 | 945 | 75 | 9 | 30 | 420 px mark | **release** |
| D1 | 1020 | 60 | 10 | 6 | 420 px mark | **fastest in the film** |
| D2 | 1080 | 120 | 3 | 24 | 200 px mark + 200 px word | rest |

No two adjacent shots share a tempo. The sequence held → settle → change → dead
stop → busiest → comparison → explain → release → fastest → rest has no plateau
in it, and the two extremes are adjacent to their opposites: B4's dead stop is
followed immediately by C1's busiest, and D1's ten events in sixty frames are
followed by the stillest shot in the film.

### 11.2 The five devices, and where each one is actually spent

craft §6 names the devices. Naming them is not using them; here is the ledger.

| device | spent at |
|---|---|
| **Anticipation** (dead stillness before a move) | f255–261 (7 f), f510–524 (**15 f**, the longest), f715–719 (5 f), f945–959 (15 f) |
| **Held silence before a reveal** | f0–11 (12 f, empty frame), f90–107 (18 f), f615–620 (6 f **and the audio cut to true silence**) |
| **The hard cut on the beat** | all 14 in-points are % 15; nine cuts carry no sound at all |
| **One accent arriving in a field of neutral** | **f430**, after 430 unbroken neutral frames — 14.3 s |
| **Scale contrast ≥3×** | f90, f180, f420, and **f870 at 6.7×** (§1) |
| **Speed contrast** | 18 empty frames before A2's kicker vs 6 before B1's; 15-frame morphs in the acts vs 6-frame morphs in D1's run |
| **Precision** | the digit at f930; the `CA` that never moves through C1's swap; M1 completing exactly on f1019 so the cut to D1 is never mid-spring |
| **The match cut on the ring** | f420 (`clear`→`clear`, bit-identical across 90 frames of type) and f1020 (everything else vanishes, the mark does not move by a pixel) |
| **Draw-on rather than fade-in** | the ring (f12–47), five hairline rules, the ray (f735), the URL (f1120) |
| **End on a hold** | f1176–1199, 24 frames, no motion, no sound |

### 11.3 Known remaining risk, stated rather than hidden

**Nine of fourteen shots put the mark in the same 420 px circle at the same
screen position.** That is the film's central identity device and it is why every
cut is a match cut — but it is also, structurally, the same picture nine times.
Three things carry the load instead, and if any of them is under-built in the
render the film will go flat in exactly the way the user complained about:

1. **The mark must actually morph, not swap.** §3 is not a nice-to-have. If M2's
   ring does not visibly *break into segments* marching from the 3 o'clock seam,
   and M3's ring visibly *refuses* to break, the film has no thesis — it has two
   amber circles.
2. **The copy column must change register, not just words.** Layout M′ in C3 is
   the only structural change in the copy column across 840 frames. It is load-
   bearing. Do not "simplify" it back to two 26 px readout lines.
3. **The still runs must be genuinely still.** A 55-frame static shot is either
   confident or dead depending entirely on whether the preceding 8 frames earned
   it. Every static run in the table above is preceded by a change and followed
   by a cut. None of them is a hold for its own sake.

And one thing the film deliberately does not do, so nobody "fixes" it later:
**it never moves the camera and never moves an element more than 17 px.** Every
temptation to add energy will present itself as a slow push. There is no camera.
The energy budget is spent on cuts, scale, silence and the mark's own geometry,
and those are the four things that survive being paused — which is the whole
point, because the failure being corrected is *"people can not focus."*

---

# 12. REVISION R2 — WHAT CHANGED AFTER THE FIRST CUT, AND WHY

Everything above §12 is the EDL as it was locked *before* the film existed.
It got built, four reviewers watched it frame by frame
(`notes/review-craft.md`, `review-focus.md`, `review-story.md`,
`review-motion.md`), and the verdicts agreed on four things: the mark's dashed
ring rendered as a **sunburst** at hero scale, the frame was **under-filled and
mis-centred**, the off-country contact **broke the mark's silhouette** on 189
frames, and the five-state run — the beat Amendment A calls the point of the
whole film — was a **slideshow of one-frame pops**.

This section is the delta. Where it contradicts §1–§11, this section wins, and
the code is the final authority over both.

## 12.1 The frame budget

Only one shot boundary moved. The module ranges are untouched, so `make.py`'s
shot table is unchanged and still tiles 0…1199 exactly.

| shot | was | now | why |
|---|---|---|---|
| D1 `end.set` | 1020…1079 (60 f) | **1020…1109 (90 f)** | Amendment A. Five 6-frame morphs are a step function on any curve; twelve frames is the minimum in which a viewer can watch a ring break and re-knit. |
| D2 `end.card` | 1080…1199 (120 f) | **1110…1199 (90 f)** | Paid for D1 out of dead frames: the card was frozen for 67 of its 120. It now holds 32 static frames, which is still the film's second silence. |

Everything else keeps its in-point. Total is still **exactly 1200**.

## 12.2 The mark — five changes, all geometry

1. **Dash length.** `holdNet [5, 6]` and `off [5, 7]` are Glyph.swift's literal
   unit values, and at menu-bar size they are correct. At 374 px of ring they
   draw a 21 px dash against a 25 px stroke — a *square block*, nineteen of
   them around a circle, i.e. a roulette wheel. It made the film's three
   serious states read as a different symbol from its two calm ones and
   destroyed the C2 comparison the thesis rests on. The film now uses
   `holdNet (13.82, 6.91)` = 10 dashes, `off (15.36, 7.68)` = 9,
   `fence (7.854, 3.927)` = 8, each period an exact divisor of its
   circumference so the pattern closes with no seam. **This is the one place
   the film's mark is optically scaled rather than literally copied, and it is
   called out in README.md.**
2. **The off-country contact and its halo** move from d = 28.4 / halo reach
   42.4 to **d = 21.0 / halo reach 29.0**, so the whole geo group lives inside
   the ring's inner edge at 30. Closest approach is 16.0 against a fence at 15
   — it still never gets in. (§4/M3's `d = 22.43` is superseded by `d = 16.0`.)
3. **The holdNet pings are arcs, not closed rings** — two opposed 130° wave-
   fronts, with the trailing one scaled to 0.42 so the two are never at equal
   weight. Two matched concentric rings inside a dashed ring is a bullseye,
   which craft §8.9 bans, and it was the signature of the state the film shows
   most.
4. **The `clear` pulse** runs at **30/91 turns per second** and stops at r 28.
   The rate makes f329 and f420 phase-identical, so B2's "structural match
   cut" is one for the first time (it used to leave on an invisible pulse and
   return on a fully-lit one). The range keeps it clear of the ring stroke.
   Every travelling ring in the film now also **fades up over the first 15 %
   of its cycle** — born at full alpha it was a hard pop six times over, four
   of them inside `HOLD · CONNECTION`.
5. **The verify sweep** is drawn *under* the ring and clamped to 27.5 units,
   and its trail is twelve stacked slices ramping to zero instead of one
   flat-alpha pie wedge. It used to halve the white band along its arc and
   fuse the needle into the ring.

**And one rendering bug.** `ImageDraw.Draw(im)` on an RGBA image *replaces* the
destination pixel. Every semi-transparent ornament crossing the opaque ring was
punching an 11 px hole through it. Three files now pass `'RGBA'`; measured
minimum luma inside the ring stroke on a `clear` frame is 226 on every frame
(it used to drop to 20).

## 12.3 Layout — one type tier up, and in from the margin

Layout M's copy column ran at 24 / 26 / 36 px against a 302 px ring 1,100 px
away. Two focal points, four hundred pixels of dead corridor between them, and
the one that won had no words on it.

| | was | now |
|---|---|---|
| mark | `(1290, 540)` box 420 | **`(1350, 540)` box 520** |
| copy column x | 160 | **200** |
| state label | mono_bold 24, track 3.4 | **mono_bold 32, track 4.6** |
| caption | ui 36 | **ui 46** |
| readout | mono 26 | **mono 32** |
| kicker | mono_bold 20, `#6E6E6A` | **mono_bold 22, `#7C7C77`** (2.6:1 → 3.4:1) |
| hairline | `#242426` | **`#34343A`** (it was below the grain) |
| baselines | 444 / 516 / 576 / 612 / 648 | **432 / 516 / 588 / 636** |
| Layout H | kicker 360, hero 480 | **kicker 432, hero 564** — the same spine as Layout M, so A2 → A3 is a rhyme, not an 84 px jump |
| rule | x 160→760 / 600 px | **x 200→760**, and **x 200→960** in C3 only, where the lockup is wider |

Measured ink bounding box across all 1200 frames moves from `x 158…1444` to
**`x 200…1537`**, and the 96 px action-safe ring is still clean on every frame
(max luma 16, which is grain).

## 12.4 Shot-level changes

* **A1.** The ring draws on as **two opposed 180° arcs closing** at 3 and 9
  o'clock, not one 360° sweep. A single sweep spends its middle second as a
  white C-arc on black, which is the indeterminate progress spinner, and the
  first 1.5 s of a promo is not a place to be ambiguous. Beats pulled 2–4 f
  earlier throughout.
* **A2.** Kicker f108 → **f102**, hero f111 → **f105**. 18 frames of black at
  second 3 was the exact moment a viewer decides whether to keep watching.
* **The type reveal envelope** goes 13 f / 10 f stagger cap → **24 f / 9 f**.
  At 13 f a 14-character line gave each glyph a 3-frame fade and the leading
  edge crossed the line in 11 frames — one glyph per frame, a typewriter, and
  the 17 px rise collapsed into a single frame so it never rendered. Measured
  after: the largest single-frame change in the A2 hero is **7.1 %** of the
  final ink (it was 22 %), and the ramp is monotone.
* **B3.** `net 82 ms · api 273 ms` now exits **with** the label at f525, not 3 f
  behind it: the frame used to read *the internet is measurably fine* beside a
  fully broken amber ring. Ping #1 arrives at **f534**, closing a 7-frame hole
  where the mark was a hollow crown with one dot in it.
* **C1.** A `CLEARED` label enters at **f694** and relays out on the flip. The
  label slot used to sit empty for the 38 frames that were supposed to prove
  the guard had been restored. The trailing ` CA` — which never moves and never
  leaves — now **dips to 0.45** across the relay, so the slot is never occupied
  by the word `CA` alone with 330 px of empty field to its left.
* **C2.** Marks 300 → **380 px**, `C2_DIM` 0.45 → **0.80**, centres
  `(660, 462)` / `(1260, 462)`. At 0.45 the frozen side resolved to `#513F21`
  — dark brown at 2.5:1 — and the amber core, the one channel that separates
  holdNet from holdGeo, could not be read at all. The swap is now a **relay in
  time** (left dims f832–839, right rises f841–848) instead of two elements
  crossing in opposite directions over the same five frames.
* **C3.** `503` enters at **f873**, three frames after the cut, not f892. The
  one cut in the film that changes the size of the world now carries the event
  that changes it. The numeral is set in **SFNS 176 / weight 700**, not
  JetBrains Mono Bold — a dotted programmer zero at hero size reads as a
  defect, and a code face blown to 176 px is literally "a terminal screenshot
  scaled up". The annotations keep mono (they are data), lose the orphaned
  leading `· `, and line 2 now shares the numeral's baseline exactly.
* **C4.** The whole M′ block clears in **one gesture, f957–f964**, instead of
  three staggered exits that left a 12 % ghost of a 160 px numeral behind live
  text. `allowed 124200` is **cut**: a bare six-digit counter with no unit and
  no prior appearance is texture pretending to be data. The release (M5) now
  keeps the fence **amber** for its whole journey and only recolours the ring
  once the fence has been absorbed — it used to lerp the fence to grey while it
  expanded, which put a dark-grey dashed ring inside a cream one for six
  frames: a clock face, an object Tower does not have.
* **D1.** 90 frames, **12 f morphs / 6 f poses**, mark at **(960, 470) box
  620** — the frame's optical centre, and the largest mark in the film. The
  eases are `EASE_IN_OUT` (a real S-curve) except the two hold/failure entries,
  which stay `EASE_SOBER`; `EASE_SNAP` at a 6-frame beat put 68 % of every
  state change on the first frame. One caption, `Five states. One mark.`, holds
  for the whole shot.
* **D2.** Card mark 200 → **280 px** (it was exactly cap height, so it read as
  a shirt button), baselines re-spaced on a ratio, `TOWER` gets optical kerning
  (`T|O −8, O|W −8, W|E +8`) so it stops reading "TO WER", and the URL arrives
  as a **staggered pair** — dim host, then lit path 5 f later — instead of a
  16-frame clip reveal that spent half a second showing a plausible, wrong,
  fully-legible `ghhrmnzdh.github.io/to`.

## 12.5 The grade

The grain was `abs()` of a normal composited as a white overlay: half-normal,
strictly additive, so it could only ever *lift* the field. Measured, the mean
of an empty frame sat 1.6 luma above `#0C0C0E` and 38.8 % of pixels changed by
more than 3 levels every frame, on a film that is still for a third of its
length. It is now a **signed, zero-mean int16 add**, σ 1.8 clipped to ±4, at
full resolution, **37 plates held 3 frames each** (a 111-frame cycle). Measured
after: empty-field mean **12.67** against an `INK` of (12, 12, 14), σ 2.0,
range 7…18.

## 12.6 Audio — §6 supersedes to 57 hits

Every retimed picture beat has its cue moved with it. The list is in
`score.py:TIMELINE` and that is the authority. Three structural changes:

* **D1's five morphs** are cued at f1026 / f1044 / f1062 / f1080 / f1098 and
  are the only passage in the film **panned to zero** — the mark is dead centre
  and the ear should not be able to place it either. `f1092–1097`, the `off`
  pose, is gated to digital silence as before.
* **Two new anticipations.** The bed thins into `f525` (the ring breaking) and
  into `f720` (the flip to holdGeo) with the same shape as the f930→f959
  thin-and-release, which was the only tension arc in forty seconds. Both
  pictures are already dead still there, so it costs nothing.
* The final decay runs **f1160 → f1180**, and the last **20 frames are true
  digital silence**.

---

# 13. REVISION R3 — THE SECOND SCORE (BUILT, AUDITIONED, **REVERTED**)

**This revision is not in the film.** It was written, rendered and muxed, the
user heard it against the first score, and their verdict was that the first
score was better. `score.py` was restored to its pre-R3 state and
`out/score.wav` re-rendered from it — byte-identical to the R2 render. **§6 and
§12.6 are therefore still the authority for the delivered audio**, and nothing
below describes a sound that ships.

It is kept as a record of what was tried and what was measured, because the
measurements in §13.1 are real and the failure is instructive: the second score
is louder, wider and brighter on every meter, and it was still the wrong film.
The picture was never touched by R3 — not one frame was re-rendered — so
§1–§5 and §7–§12.5 stand exactly as written either way.

Read everything from here down in the past conditional: *would have been* —
**with one exception, §13.4.** On hearing the restored score the user's one
remaining note was the hairline, by ear and by the clock: *"the minor sound in
the internet disconnection is not good enough … it's happening in second 6, 14,
24."* Those are `f192`, `f426` and `f692`/`f735` — the SFX_RULE windows, and the
descending glide §13.4 had already diagnosed. So the **third** hairline, and
only that, was ported out of R3 and into the shipped score: `score.py:_hairline`,
feeding `sfx_rule` and `sfx_rule_short`. Nothing else about the audio moved —
the two cues sit at their old timeline levels (−28 / −30 dB), measure within
1 dB A-weighted of the sounds they replace, and the render differs from the
restored R2 wav only inside those four windows and their room tails.

## 13.1 Why

The brief changed, from the user and in their words: **subtle music, modern,
premium, minimal sound effects.** §6's brief was the opposite of that — *"this
is not a score"* — and the first attempt then had a drone, a progression, a
tune and a room patched into it one amendment at a time until it was a score
wearing a bed's clothes. Measured, the delivered WAV said what it sounded like:

| | first score | second score |
|---|---|---|
| K-weighted centroid | 731 Hz | 1344 Hz |
| 95 % of energy below | 2.9 kHz | 6.4 kHz |
| energy above 8 kHz | 0.36 % | 2.4 % |
| side/mid | 0.168 | 0.323 |
| integrated loudness | −26.0 LUFS | −17.5 LUFS |
| true peak | −1.0 dBTP | −5.0 dBTP |

The first column is not a mix that is *quiet*. It is a mix that is *small*:
no ceiling, no width, and peak-normalised rather than loudness-normalised, so
a high crest factor bought nothing but headroom nobody hears.

## 13.2 What the second score is

A real ensemble, all of it synthesised, none of it sampled:

* a detuned additive **pad** — three voices per pitch at ±6.5 cents, panned
  wide, a sawtooth spectrum through one fixed 3.1 kHz corner, and a global
  +4.2 dB/oct tilt so amplitude does not get mistaken for loudness;
* a **sub** on the root of each chord, 36–58 Hz, mono and centred;
* a **felt key** for the tune — mildly inharmonic partials, two strings a
  unison apart, a lowpassed hammer;
* **air**: the chord's own upper voices at ×4/×8/×16/×24/×32, plus a whisper
  of 4–11 kHz breath gated by the music's envelope;
* **two rooms** — a 2.6 s hall for the music, a 0.9 s plate for the cues;
* a **sidechain duck**, 3.2 dB, so the cues read as present rather than loud;
* one stage of soft **saturation**, and a harmonic **exciter** that buys the
  top end from the music instead of from noise.

**The harmony carries the story.** Ten voicings out of D minor *with ninths*.
CLEARED goes to the relative major; the connection hold goes to the
subdominant, still inside the key; the location hold goes to a **chromatic
B♭ minor** — the only notes in the film outside D natural minor, and they
sound at the exact frame the location goes out of country. The 503 sits on a
B♭m(maj7)9 that cannot resolve. The build is harmonic, never rhythmic.

**There is a tune, and it finishes.** A–G–F–D. Posed in Act A, stalled on the
third at both holds, bent chromatically flat under off-country, resolved
unprompted on the release at f960, and played in full for the first time over
the end card.

**Still no drums.** That verdict stands and it is the more important
principle: every cue in §7 is structurally a drum hit, so an actual grid
underneath them would make it impossible to tell which taps are the film
telling you something. The cues are the rhythm section.

## 13.3 The sync, which is the part that was actually broken

Two independent errors, both in the same direction:

1. **A cue fired on the frame the animation starts.** Every text entrance runs
   a 24-frame reveal on `EASE_ENTER` with a per-character stagger. Worked out
   from the authored maths, a line is at **3–6 % opacity on its own first
   frame** and does not reach half until four or five frames later. Text cues
   therefore moved **+4** frames (24-frame kinetic reveals), **+3** (the 14–18
   frame reveals in `scene_hold`) or **+1** (the sober 8-frame opacity fades,
   which are front-loaded). The three D1 morphs on `EASE_IN_OUT` moved **+4** —
   that curve is at 2 %, 8 %, 19 % over its first three frames. Everything on
   `SETTLE` or `EASE_SOBER` did not move: those are front-loaded, and on a
   state change the sound is the cause, not a comment.
2. **A cue was placed by its first sample, not by where it is heard.** Each
   cue's pre-roll is now measured from the cue itself (`score.pat()` — the
   first crossing of 70 % of its smoothed envelope peak). 2.6 ms for a tick,
   63 ms for the draw swell. `Hit.f` means *heard here*.

Every `Hit`'s note now quotes the scene constant it derives from — `RING_AT`,
`CORE_AT`, `BLIP_AT`, `M1_AT`, `C3_BIG`, `C3_RULE`, `AT_WORD`, `_RUN`, and the
rest — so a picture retime and its cue can be checked against one another.

## 13.4 The hairline, which has now been wrong twice — **THIS ONE SHIPS**

The only part of R3 that is in the delivered film. In the shipped R2 timeline
the cue keeps its name, `SFX_RULE`, and its own frames — **f192 / f426 / f692 /
f890**, plus the two short variants at f735 and f966 (R3's f196 / f430 / f696 /
f893 were its retimes, and those did not come with it). It is the most-repeated
designed sound in the film and the easiest to get wrong.

* **v1: a granular noise sweep.** Broadband, 44 ms attack, spectral flatness
  0.150 — structurally a brushed snare, and the one sound in the set the ear
  filed as percussion.
* **v2: a tonal glide, A3 → G3.** Fixed the percussion problem and introduced
  a worse one. A pitch falling a whole tone is not the sound of a line being
  drawn; it is the sound of something deflating. The user heard it at seconds
  6, 14 and 23 — which are f192, f426 and f692, the only cue those three
  windows have in common.
* **v3: no pitch motion at all.** A hairline is a *travel*, and the travel is
  carried where the picture carries it — across the stereo field. What sounds
  is a fixed narrow resonance (Q 3.4, about a third of an octave, so it reads
  as a line and not as a wash) with a soft rise and a smooth fall, plus one
  30 ms tuned tick at the head that is the pen touching down. The tick is on a
  chord tone so the cue still belongs to the film's pitch object; it never
  becomes a note.

## 13.5 What did not change, and may not

The film's rules, not the score's:

* a hard cut carries no sound of its own — f90, f180, f330, f420, f690, f780,
  f870, f1020, f1110;
* a hold is PENDING, not FAILED, and never sounds like an alarm;
* the `off` state is silent both times — f615–689 and f1081–1097;
* nothing rises into a cut;
* the last 20 frames are true digital silence;
* holdNet and holdGeo are distinguishable with your eyes shut — a clean minor
  third, now in the chord as well as in the knock;
* deterministic: named PRNG streams, no clock reads, byte-identical every run.
