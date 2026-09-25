# review-story.md — Tower film, 40 s, reviewed for STORY and EXCITEMENT

Reviewed against `FILM.md`, `notes/craft.md`, `CLAUDE.md`, `promo/analysis/brand.json`.
Grounded in frames extracted from `out/tower-film.mp4` with ffmpeg into
`/private/tmp/.../scratchpad/qa_story/` — 1200 single frames plus consecutive-frame
strips through f255–278, f520–543, f715–744, f832–847, f955–984, f1020–1079,
f1118–1141, and numeric measurements of ring duty-cycle, ring colour, ink
fraction, accent fraction and the audio envelope.

---

## VERDICT

**The lanes are taught. The payload lands. The film is not exciting.**

It teaches `where you are` and `how the wire is` cleanly, it contrasts holdNet
against holdGeo, and it spends its best asset — the 160 px `503` — on the right
idea. Honesty is clean: I scanned every 10th frame and there is **not one green
pixel in the film**; "outside target" is amber (f770); a slow link is shown as
allowed (f480); the block is `PENDING` / `503` / `Retry-After` / `Retrying ·
attempt 3/8` and never 403/failed (f925). Nothing from `brand.json.do_not_claim`
appears. That part is done.

But this is a **tasteful screensaver**. Fourteen still posters, each with a
302 px mark looping quietly inside it, joined by transitions. Nothing ever
travels. Over 40 % of the runtime is frames where the only changing pixels live
inside that one circle. Nothing is at stake for the first **14.3 seconds**. The
audio envelope confirms it: a flat −29 dB bed for the whole film, seven
transients, and **exactly one** tension arc in 40 seconds (f930→f959 thinning
to −40 dB, released at f960). That one arc is the best thirty frames in the
film, and it proves the technique works — which makes its absence everywhere
else the central failure.

Grade: **fail on excitement, pass on argument, pass on honesty.**

---

## FINDINGS — most severe first

### 1. Nothing is at stake until f430 (14.3 s = 36 % of the runtime)

**Frames:** f0 (empty), f30, f89, f140, f230, f320, f419 — then f430.

f0–f429 is 430 consecutive frames of *everything is fine*. The mark draws on,
a card says `Where you are.`, the mark confirms, a card says `How the wire is.`
The first thing that could possibly create tension is the first amber at f430 —
and it is **two words of 24 px type covering 0.09 % of the frame**
(`SLOW LINK`), which is not a fault at all, it is a non-fault ("still allowed").
The first real fault is the hold at f525, **17.5 seconds in**.

FILM.md §2.6 celebrates this: *"the 430-frame neutral run… Amber arrives once,
14.3 seconds in."* Scarcity is a good instinct for *colour*. It is a disastrous
one for *stakes*. A promo has five seconds to make the viewer want the next
thirty-five, and this one spends its first eleven on a radar agreeing with
itself.

**Fix.** Re-budget in `FILM.md` §1 and the two owning modules:
* A2 `open.where` f90–179: **90 f → 45 f** (kicker f96, hero f99, static from
  f112 — still 24 f over the 3-word floor of 53 f… so instead hold the hero and
  cut the 18 empty frames f90–107 to 6, giving 78 f). Net −12 f.
* B1 `wire.how` f330–419: **90 f → 60 f**. Net −30 f.
* A1 `open.mark` f0–89: **90 f → 60 f** — the ring draw-on (f12–47) plus the
  core seat (f48–66) is done by f66; f67–89 is 23 frames of a static radar
  before the film has said one word. Net −30 f.

That reclaims **72 frames**. Spend them on §3 (C2) and §2 (C3). The first amber
then lands around **f358 (11.9 s)** and the first hold around **f453 (15.1 s)**.

Better still, and worth costing: **open on the fault.** Shot 1 is the amber
`HOLD · LOCATION` mark with no explanation, 30 frames, silent. Shot 2 cuts to
`CHECK ONE / Where you are.` and the film becomes an answer to a question the
viewer already has. Right now it is an answer to a question nobody asked.

---

### 2. f870 — "the film's biggest scale jump" does not happen at the cut

**Frames:** f868, f869, f870, f871, f875, f880, f885, f890, f892, f895, f900,
f925.

FILM.md §1 calls f870 *"the film's biggest scale jump… the one cut in the film
that changes the size of the world, and it lands on the honesty payload."*
Measured ink fraction across the cut:

| f | total ink | left-half ink |
|---|---|---|
| 869 | 0.0262 | 0.0241 |
| **870** | **0.0231** | **0.0073** |
| 892 | 0.0257 | 0.0116 |
| 900 | 0.0330 | 0.0282 |

The cut goes from a sparse frame to a **sparser** frame. The `503` enters at
f892 and is not full until f900 — **30 frames (1.00 s) after the cut**. So the
biggest planned event in the film is decoupled from its own cut, and f870–f891
is 22 frames of a lone mark on an empty field, which is the emptiest the frame
has been since B4.

This is the most fixable serious problem in the film.

**Fix.** `scene_hold.py:804` — `a_big = … _fade_in(f, 892)` → `_fade_in(f, 871)`.
Then push everything else behind it so the numeral is the *first* thing after
the cut: `scene_hold.py:787` label `_fade_in(f, 876)` → `_fade_in(f, 882)`;
`scene_hold.py:797/799` caption f882 → f886; `scene_hold.py:801` `_rule(img, f,
886)` → `_rule(img, f, 890)`; annotations f898/f902 → f879/f883. Pay for the
reading floors from the static tail (f931–f944 is already dead).

The cut then delivers what the EDL promised: 24 px labels on f869, a **160 px
numeral on f871**.

---

### 3. The thesis shot dims one lane to a brown ghost

**Frames:** f820, f860, f869, and the consecutive strip f832–f847.

C2 is the film's thesis (FILM.md §4.10: *"holdNet vs holdGeo is the film's
entire thesis"*). It shows both marks and alternates which one is "live" by
dropping the other to `C2_DIM = 0.45` (`scene_hold.py:725`). Measured mean
colour of the drawn pixels:

| f | side | mean RGB | peak luma |
|---|---|---|---|
| 820 | left, live holdNet | (154,116,51) | 242 |
| 820 | right, frozen holdGeo | **(103,81,41)** | **127** |
| 860 | left, frozen holdNet | **(81,63,33)** | **125** |
| 860 | right, live holdGeo | (207,156,67) | 253 |

`(81,63,33)` is `#513F21`. That is not amber, it is dark brown, and at f860 the
one channel that separates holdNet from holdGeo — **the amber core** — is not
readable on the frozen side at all. FILM.md claims 0.45 *"keeps the four-way
difference table below resolvable in a frozen frame"*. It does not; I looked at
the frames.

Worse, it is a **story** error, not just a legibility one. The shot's entire
idea is *two independent causes, equally valid, and Tower tells you which*.
Rendering one at 45 % says one of them is less important — it reads as a
disabled UI element, not as the other answer.

**Fix.** `scene_hold.py:725` `C2_DIM = 0.45` → **`0.72`**, and get the
"one loudest thing" separation from **motion alone** (frozen side dead still,
live side animating), which is what design.md's legible-still-frame guarantee
exists for. Raise the frozen label from α 0.55 to **0.80** in the same file.
Also spend ~30 of the frames reclaimed in §1 here: at 90 f the shot gives each
side ~28 live frames, which is under both marks' own cycle.

Secondary: at 300 px per mark the differentiating features (core colour, ring
broken vs solid) are ~10 px details. On a phone this shot is two amber circles.
Consider **340 px** marks at centres (680,500) and (1240,500) — gutter still
220 px, still inside the content box.

---

### 4. D1 (f1020–1079) is a slideshow, not a run

**Frames:** every frame f1020–f1079 (strip `run_1020.jpg`), plus per-frame ring
measurements.

The five-state recap is built from ten 6-frame beats at `EASE_SNAP`
(`scene_end.py:830–840`, `BEAT = 6`). Measured ring duty-cycle and mean colour:

```
1037  0.91  (226,225,222)   <- verify, neutral, solid
1038  0.65  (220,170,78)    <- ONE frame later: already amber, already breaking
1039  0.50  (219,164,66)
1040  0.45  (217,164,66)    <- settled.  Total: 3 frames.

1049  0.46                  <- holdNet
1050  0.77                  <- the re-knit begins
1051  0.92
1052  0.96                  <- done.  Total: 3 frames.

1061  0.93  (224,167,64)
1062  0.72  (219, 92,77)    <- amber -> red in ONE frame
1074  0.77  (226,216,214)   <- red -> neutral in ONE frame
```

**Every colour change in D1 completes in a single frame.** `EASE_SNAP` is
`bezier(0.22,1.00,0.36,1.00)`; at t = 1/6 it already returns ≈ 0.87. A 6-frame
beat on that curve is a step function.

FILM.md §4.13 stakes the whole recap on one moment: *"The holdNet → holdGeo
morph at f1050 is the one to get right… If the viewer's eye catches it, the film
has landed."* At 30 fps a 2-frame re-knit is **67 ms**. The eye does not catch
it. What actually plays is five icons cutting to each other — which is exactly
the "cross-fade between two finished pictures" the film swore off, done at
higher speed.

**Fix.** In `scene_end.py`:
* line 840: `BEAT = 6` → **`BEAT = 10`**;
* lines 830, 832, 834, 838: `EASE_SNAP` → **`EASE_MOVE`** (the dash lerp needs
  its whole span visible; `EASE_SOBER` on line 836 stays);
* extend D1 from 60 f to **100 f** by taking 40 f from D2, which is static from
  f1099 anyway and holds a dead freeze f1176–f1199. New ranges: D1 f1020–1119,
  D2 f1120–1199 (80 f — still 20 f over the tagline's 98-f… recheck: keep D2 at
  100 f and take the remaining 20 f from §1's reclaimed budget).

If the frame budget will not stretch, **drop one state** rather than keep five
unreadable ones: run `clear → verify → holdNet → holdGeo → off`, end on red, cut
to the card. Four 10-frame morphs read; five 6-frame ones do not.

---

### 5. C1's first 38 frames say nothing (f690–f727)

**Frames:** f700, f719.

FILM.md §4.9: *"The guard must be visibly restored before location takes it
away, or `off` and `holdGeo` collapse into one memory."* On screen, f700 is a
neutral mark and a 60 px hairline stub — no label, no caption. f719 is a neutral
mark and one 26 px readout line. **The state label slot at y=444 is empty for
38 frames (1.27 s)**, and the only thing saying "restored" is the mark's colour,
which the viewer must recall across the intervening red `off` shot.

So the film's most important setup is carried by nothing, and the composition is
the thinnest in the middle of the picture — a screensaver frame in the exact
place the film needs a before/after.

**Fix.** `scene_hold.py:688–713` — add a `CLEARED` label (mono_bold 24, +3.4,
`#E7E6E2`, x=160, baseline y=444) entering **f696**, kinetic 13 f `EASE_ENTER`,
relaying out **f720–f727** into `HOLD · LOCATION` at f728 (the relay machinery
is already there for the readout). The slot is empty, the copy budget has room
(51 of 60 words), and it is the cheapest before/after in the film.

---

### 6. The flip does not land on f720

**Frames:** consecutive f715–f744 (strip `flip_715.jpg`), ring colour measured
per frame.

```
719  (227,226,222)
720  (228,222,211)   <- indistinguishable from f719
723  (226,191,126)
726  (225,173, 78)
```

FILM.md §1 names f720 as one of the film's three landmarks (*"the amber HOLD ·
LOCATION arrival"*, a multiple of 60). The SETTLE spring starts at k = 0, so on
f720 the picture is identical to f719 and nothing changes for ~3 frames.
Meanwhile the audio hit **is** on f720 (measured −11.8 dB, the loudest transient
in the film). Picture and sound are 3 frames apart on the film's biggest beat —
which is exactly the "did something just happen?" feeling that kills a cut.

**Fix.** Either start the morph at **f717** so its perceptual midpoint sits on
f720, or give f720 one instantaneous channel of its own: drop the three blips to
α 0 on f720 exactly (they are already going to 0 in M3), so *something* visibly
changes on the landmark frame. `scene_hold.py`, C1 morph block.

---

### 7. The end card changes the subject

**Frame:** f1199 (and f1095, f1150).

Thirty-four seconds arguing *two things can go wrong, we tell you which, your
turn goes pending not failed* — and the card closes on
`A control tower for your Claude agents.` A capability the film never shows, and
a sentence that answers a different question. **The film's own thesis is never
stated in words anywhere in the 40 seconds.** FILM.md states it in its first
paragraph and then never puts it on screen.

**Fix.** `scene_end.py` D2, tagline slot (ui 36, `#9A9A95`, centred x=960,
baseline y=744): replace with the argument. `Held, never failed.` (2 words,
floor 42 f, you have 101) or `Two checks. One honest answer.` (5 words, floor
79 f, still fits). Keep the README line only if it can be added as a fourth
object without breaking the three-object ceiling — it cannot, so choose.

---

### 8. `allowed 124200` is the last number the film shows and it means nothing

**Frame:** f1010 (also f990, f1019).

No unit, no context, no prior mention of a counter anywhere in the film. A
viewer reads "allowed 124200" and gets nothing. It is texture pretending to be
data, in the one shot whose job is *"it cleared itself and the turn resumed."*

**Fix.** `scene_hold.py` C4 readout line 2 (y=648): delete it — the frame
returns to two text objects and `Toronto, CA — inside CA` carries the whole
recovery — or replace with `resumed on its own`, which is the actual payload and
is true.

---

### 9. holdNet's interior renders as a bullseye, not a sonar

**Frames:** f532, f590, f820, f860, f869; strip f520–543 rows 3–4.

The two pings draw as **dark, low-contrast concentric rings at near-static
radii**. At f590 the mark is a bright dashed amber ring around a dartboard of
three brown circles. Two problems:

1. It inverts the sonar read. A ping should be brightest at birth and fade as it
   expands; here the interior rings are the *dimmest* thing in an otherwise
   bright mark, so they read as fixed geometry rather than as motion.
2. Register. craft §8.9 bans *"corner brackets, crosshairs, reticles or
   targeting language — Tower is an honest status layer, not a weapons HUD."* A
   concentric-ring bullseye is the same register, and it is the signature of the
   state the film shows most.

**Fix.** In the ping draw (`brand.py` radar / `scene_wire.py` holdNet block):
set ping alpha to fall with radius, `a = 0.70 * (1 - r_frac)`, and widen the
r-range from 7→22 units to **7→30** so that at any phase only one ring is inside
the fence radius. The "expanding, fading" read then costs nothing and the
dartboard disappears.

---

### 10. f532: measured latencies shown under a fully-broken amber ring

**Frame:** f532 (also f533, f534, f535).

The `SLOW LINK · STILL ALLOWED` label has already exited (f525–f532) but the
readout `net 82 ms · api 273 ms` runs to f535. For four frames the frame reads
*the internet is measurably fine* beside a fully amber, fully broken holdNet
ring whose next line will be `internet down`. It is brief, but it is a
self-contradicting frame in a film whose subject is honest status.

**Fix.** `scene_wire.py` — start the readout exit at **f525** with the label
rather than f528. The slot is empty from f533 either way and the relay into
`internet down` at f552 is unaffected.

---

### 11. The off-country contact collides with the outer ring

**Frames:** f770 (colliding), f873 (clear), f925 (partially).

Contact base is unit (72,32) → 119.4 px from the hub, radius 21 px, so it spans
98–140 px. The ring band is 126–151 px. At the outward extreme of its lunge the
contact **overlaps the ring** and reads as a bump welded onto it (f770) rather
than as a contact being held outside the fence. The read the shot is built on —
*it lunges at the fence and is pushed back, forever, it never gets in* — is
about the **fence**, but the eye is drawn to the ring collision instead.

**Fix.** `scene_hold.py` / `brand.py` holdGeo geometry: move the contact base
from unit **(72,32) → (66,29)** (d = 100 px, clears the ring's inner edge by
≥5 px at full lunge), or drop the blip radius from 5 → 4 units. Also lengthen
the ray: at f770 it is 2–3 dashes and reads as noise, not as a line from the hub.

---

### 12. One tension arc in forty seconds

**Evidence:** audio RMS envelope sampled every 5 frames across the whole film,
plus the static-frame census.

The bed sits at ≈ −29 dB for the entire runtime. Seven transients reach −12 to
−16 dB (f260, f525, f720, f890, f960, f1005, f1080). There is exactly **one**
build: f930 −27 → f959 −40, released on f960 at −11.9. That thirty-frame
thin-and-release is the best beat in the picture — you actually lean in.

Everywhere else the film is flat. B3's hold (f525) gets a hit and then 54
frames of unchanged bed and unchanged picture (f561–f614). B4 gets 55 dead-still
frames (f635–f689). B1 gets 68 (f352–f419). The picture census is worse: more
than 40 % of the 1200 frames are stills whose only moving pixels are inside the
mark's 302 px circle.

**Fix.** The technique is already in the file — use it three times, not once.
Duck the bed from f505 → f524 (into the holdNet morph) and from f700 → f719
(into the flip), matching the f930–f959 shape. Costs nothing in `score.py`, and
it converts two flat cuts into two anticipations. Pair each with the picture
going still for the same window (both already are).

---

### 13. Minor: the film's first 1.5 s is an indeterminate progress spinner

**Frames:** f18, f24, f30, f36.

f12–f47 draws the ring as a 360° arc sweep. At f30 (looked at it) the frame is a
white C-arc on black, i.e. **exactly the loading spinner every user has seen ten
thousand times**. The intended read is "a mark makes itself"; the first read is
"this video is buffering." It resolves by f48, but the opening 1.5 s of a promo
is not a place to be ambiguous.

**Fix.** Draw the ring on from **two opposing arcs meeting** (0° and 180°, each
sweeping 180°) rather than one 360° sweep. Same 36 frames, same `EASE_MOVE`,
same event — but it is never a spinner at any single frame, and the two arcs
closing is a stronger "seat" than an arc chasing its own tail.

---

## WHAT IS EXCELLENT — do not break these

* **The ring breaking at f525–f535** (strip `m2_520.jpg`). Solid → 2 segments →
  4 → 8 → 24 over eleven frames, duty-cycle measured 0.97 → 0.46. This is the
  single best piece of animation in the film and it is doing real semantic work.
  FILM.md's claim that "that single animation is worth more than any effect in
  the film" is, for once, accurate. Leave it exactly as it is.
* **The gap at f615–f620.** Six frames of empty field with the audio measured at
  true digital silence (−240 dB from f625 to f685). A cut to nothing, then a red
  mark that simply *is* there. The best cut in the film, and the only place the
  film has any nerve.
* **The fence expanding back into the ring, f960–f974** (strip `rec_955.jpg`).
  The reverse of M3 is instantly legible as "the fence is no longer needed" and
  it needs no caption. Keep.
* **The match-cut spine is real.** Measured mark bbox on f230, f320, f480, f600,
  f770, f925, f1000, f1035, f1046, f1058, f1078: **302 × 302 at (1139,389) –
  (1440,690) on every one**, across every state. Bit-identical geometry across
  ten shots. That is the film's whole identity device and it is engineered
  correctly.
* **f480 — `SLOW LINK · STILL ALLOWED` beside a fully neutral mark.** This is the
  hardest honesty note in the brief and the film nails it in one frame with no
  hedging. `SLOW LINK` amber, `· STILL ALLOWED` neutral, radar unchanged.
* **f925 — the `503` lockup.** Neutral, 160 px, no scale-in, no spinner, no
  progress bar. It is calm and it is enormous, which is exactly the point.
* **Honesty overall.** Zero green pixels anywhere (scanned every 10th frame).
  Amber for off-country (f770), never red. `PENDING` / `503` / `Retry-After` /
  `Retrying · attempt 3/8` (f925), never 403 or "failed". No VPN, firewall, kill
  switch, telemetry or agent-count claim. Nothing from
  `brand.json.do_not_claim`. Accent coverage measured ≤ 1.3 % on the worst frame
  (f925), one hue per frame throughout.
* **f140 — the A2 hero card.** New York at 120/520 with −1.2 tracking on that
  field is genuinely handsome. The type system is not the problem with this
  film; the pacing is.
