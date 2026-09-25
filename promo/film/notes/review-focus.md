# review-focus.md — one lens: focus and legibility

Reviewer pass over `out/tower-film.mp4`. All 1200 frames extracted with ffmpeg
to `qa_focus/` (`-vsync 0`, jpg q2). ~50 full frames read individually, plus
four per-frame contact sheets covering 120 consecutive frames across the four
motion beats (f716–739, f958–981, f1014–1025, f864–877, f1020–1079). Numeric
sweeps (ink bbox, safe ring, accent coverage, HSV green scan, cut-identity
diffs) run over all 1200 PNG masters, not the encode.

**Verdict: fail.** The old film was messy because too much competed. This one is
the opposite failure with the same result: in the eight `Layout M` shots — 600
of 1200 frames, half the film — the loudest object on screen carries none of the
meaning, and the object that carries the meaning is 24 px of grey mono 1,100 px
away from it. A viewer's eye lands on the ring and never travels. On top of that
there are five places where the mark degenerates into an unreadable or actively
wrong shape (a bullseye, a cream dial, a keyhole, a broken ring), one place
where a two-letter fragment floats alone in the middle of frame, and one place
where the film's own URL is legible and wrong for half a second.

The good news is at the bottom and it is real: **nothing is cropped, anywhere,
in any frame.** That was the brief's first sin and it is comprehensively fixed.

---

## Ranked findings

### 1 — The subject and the payload are inverted in half the film
**Frames: 180–329, 420–689, 690–779, 870–1019 (all of Layout M / M′). Evidence
frames read: 199, 229, 254, 299, 327, 469, 569, 659, 759, 894, 911, 931, 994.**

In every Layout M frame the highest-contrast, largest object is a ~302 px pure
`#E7E6E2` ring at (1290, 540). The information — the state label — is 24 px
mono at `#E6A93C`/`#E7E6E2`, sitting at x=160, and the readout below it is 26 px
at `#8B8B86`. Between them is a 400 px empty corridor (copy right edge ≈584,
mark left edge 1139). There are two focal points, they are far apart, and the
one that wins is the one with no words on it.

Measured across all 1200 frames: every pixel of ink lives inside
`x 158…1444, y 264…859`. So the composition's optical centre is x≈801 while the
frame's is 960 — **there is a permanent dead band of 476 px on the right and
221 px at the bottom**, and the eye reads the whole film as slightly
mis-framed. Max ink coverage in any frame is **3.9 %** (peak f1139); the film is
not minimal, it is under-filled.

*Fix (brand.py + all four scene modules):*
- `brand.py` `MARK_BOX = 420` → `520`, `MARK_C = (1290.0, 540.0)` → `(1360.0, 540.0)`.
  Ring outer diameter goes 302→374 px, spanning x 1173…1547; right margin
  becomes 373 px against a 160 px left margin — near-balanced instead of 476 vs
  158 — and the mark becomes unambiguously the subject at a size that survives a
  phone.
- Raise the copy so it is a readable caption rather than a competing block:
  state label 24 px → **32 px** (tracking scales to +4.5), readout 26 px →
  **30 px**, and extend the rule from `x 160→760` to `x 160→900`. Do **not**
  raise the caption above 36 px — it is already correct.

### 2 — f726–f729: an orphaned `CA` floats alone in the middle of the frame
**Read: f723, f726, f727, f728, f729, f733 (cropped 8× on the readout slot).**

The C1 readout is drawn as two runs. The leading run `Toronto, CA — inside`
exits f720–727 and `Tehran, IR — outside` does not enter until f728. On f727 and
f728 the readout slot contains **nothing but the word `CA`, at x≈490, y=603,
under a 600 px hairline, with 330 px of empty field to its left.** It reads
exactly like a truncated string — the failure mode the ban list exists to
prevent — not like "the target country never changes". FILM.md calls this "the
truest frame in the film"; on screen it is a bug.

*Fix (`scene_hold.py`, C1 readout relay):* compress the relay so the slot is
never occupied by the trailing run alone — leading run out **f716–f723**, new
leading run in **f724–f731**. Additionally drive the trailing ` CA` alpha to
`0.35` across f720–f727 and back to `1.0` by f733: it still never moves and
never leaves, which is the actual device, but it stops being the only thing on
the line.

### 3 — The off-country contact and its halo collide with, and overrun, the ring
**Frames: 752–944 (C1+C3) and 1052–1061 (D1). Read: f759, f894, f911, f931,
plus the f864–877 sheet (every frame) and the f1020–1079 sheet, row 4.**

Geometry, from `scene_hold.py`: `_RAY_END = (72.0, 32.0)` → 28.43 units from the
hub = **119.4 px**; contact radius 5 units = 21 px; `_geo_live` halo
`hr = 5 + hp*9` units → up to **58.8 px**. The outer ring stroke occupies
**126 → 151.2 px**. So the contact disc reaches 140 px — *inside the ring
stroke* — and the halo reaches 178 px, **outside the mark entirely**.

On screen this is an amber blob welded across the ring at 1–2 o'clock that
breaks the mark's silhouette on every one of ~170 frames. It is the single
biggest "what am I looking at" moment in the middle of the film, and it destroys
the read the shot is built on (a contact held *outside the fence*, not a contact
chewing through the hull).

*Fix (`scene_hold.py`):* in `_geo_live`, clamp the halo to
`hr = _lerp(9.0, 5.0 + hp * 6.0, amp)` (max 11 units = 46 px) and clip the
contact + halo draw calls (the `t.circle` / `t.ring` at lines ~403–408) to a
disc of radius **28 units (117.6 px)** about the hub, so nothing ever enters the
ring stroke. The contact stays at 28.4 units — comfortably outside the r=15
fence, which is the honest claim — and stops touching the ring.

### 4 — `holdNet` renders as a shooting target
**Frames: 540–614 (B3), 780–869 (C2 left), 1044–1049 (D1). Read: f569, f781,
f806, f840, f860, plus the D1 sheet row 3 (frames 1040–1049).**

Two concentric dim-amber ping rings plus a filled amber core, inside a ring of
~24 rectangular ticks, is a bullseye. It is not readable as expanding sonar in a
still frame, it looks like a reticle — `craft.md` §8.9 bans corner brackets,
crosshairs, reticles and targeting language outright — and at f781/f806 the two
pings sit at 0.55 and 0.30 alpha simultaneously, so the interior is a solid
banded disc rather than two travelling wavefronts.

*Fix (`scene_wire.py`, the `_ch_holdnet` ping construction ~L596–610):* draw the
pings as **arcs, not closed rings** — two opposed 130° arcs sharing the ping's
phase — and let only **one** ping be above 0.35 alpha at a time (currently
`a_s = 0.55 - i * 0.25` puts both up). Two arcs marching outward reads as sonar;
two closed rings read as a target.

### 5 — f960–f970: the recovery turns the mark into an off-palette cream dial
**Read: f964, f971, plus the f958–981 sheet (row 1 cols 5–8, row 2 cols 1–3).**

Two separate bugs stack on the film's second-most-important beat:
- `scene_hold.py:581` — `ch["fence"]["rgb"] = _mix(AMBER, TEXT, k5)`. The fence
  *turns grey* while it expands, so for ~6 frames the mark contains a dark-grey
  dashed ring: it reads as a **clock face with tick marks**.
- The outer ring's `AMBER → TEXT` lerp spends f963–f967 at roughly `#E0D2A8`, a
  warm cream that exists nowhere in the brand.

The result at f964 is an object that is neither `holdGeo` nor `verify` nor
anything Tower has. The same cream appears on the way *in* at f720–f723 (M3,
f716–739 sheet, row 1 cols 5–7), on the beat FILM.md calls the film's biggest
moment.

*Fix:* keep `fence.rgb = AMBER` and drive only its alpha, `a = (1.0 - k5) ** 2`,
so it is gone by k5≈0.45 and never coexists with a neutral ring. Drive the ring
colour with `EASE_SNAP(k5)` instead of the raw spring so it commits to its
destination hue in the first ~5 frames and the cream mid-point lasts 2 frames,
not 6. Apply the identical change to the M3 lerp at f720.

### 6 — f960–f971: three states of the same block on screen at once
**Read: f964, f971.**

At f964 the copy column simultaneously carries: a ~10 % ghost of `PENDING`, a
~12 % ghost of the **160 px** `503`, a live `The turn survives.`, a live rule,
and a fully-lit `Retrying · attempt 4/8`. A 160 px numeral at 12 % alpha behind
live text is a ghosted layer — the exact "two legible layers, neither readable"
failure the new film was commissioned to avoid, just contained to one column.

*Fix (`scene_hold.py` C4):* shorten the `503` and `PENDING` exits to **5 frames**
(`f960–f964`) with `EASE_EXIT`, and move the `Retrying · attempt 4/8` exit
forward to `f960–f965` so the whole M′ block clears in one gesture instead of
three staggered ones. Keep `CLEARED` at f967 and the readouts at f972 — the
4-frame vacancy FILM.md asserts is good and should stay.

### 7 — f870 is a jump cut wearing the costume of a scale cut
**Read: the f864–877 sheet, plus f871. Measured: 49,086 px in the 420×420 mark
box differ across f869/f870, max Δ243.**

The mark translates from (1220, 500) to (1290, 540) — **79 px** — and scales
300→420 px, **1.4×**. A near-match that isn't a match is the sloppiest cut
available: the eye is tracking that object and it lurches.

FILM.md claims f870 is "the film's biggest scale jump, 24 px labels → a 160 px
`503`, 6.7×". It isn't: the `503` does not enter until **f892**, 22 frames
later. At the cut itself the largest type on screen goes from 24 px to *nothing*.

*Fix — pick one:*
- (a) make the claim true: bring `503`'s entry to **f876** and push `PENDING` to
  f882, so the scale jump actually lands on the cut; **or**
- (b) stop the near-match: `scene_hold.py:720–721` →
  `C2_L = (640.0, 470.0)`, `C2_R = (1180.0, 470.0)`, putting both C2 marks
  ≥150 px from the canonical circle so f870 reads as a recompose.

Do (a) at minimum. (a)+(b) together is the correct fix.

### 8 — f1129–f1135: the film's URL is legible and wrong for half a second
**Read: f1130.**

`scene_end.py:_draw_url` reveals the URL with a 16-frame `clip_reveal`
(`URL_DRAW = 16`, `EASE_MOVE`). At f1129 the frame reads
`ghhrmnzdh.github.io/to`. For ~16 frames the one string in the film that has to
be exact is a plausible, wrong, fully-legible address. This is mid-word clipping
by another name.

*Fix (`scene_end.py`):* replace the clip-reveal with an **8-frame `EASE_ENTER`
opacity fade** on the whole string. A draw-on is the right instinct for a rule;
it is the wrong instinct for a URL. If the draw-on must stay, `URL_DRAW = 5`.

### 9 — C3's big-number lockup, the film's payload frame, has its weakest typography
**Read: f895, f912, f932.**

`scene_hold.py:777–779` — `Y_BIG = 720`, `X_ANNOT = 478`, `Y_A1, Y_A2 = 696, 732`.
The `503` occupies a cap band of y 605…720. Both annotations sit *below* its
optical centre, and annotation 2 hangs 12 px **below the numeral's baseline**, so
the lockup reads as two unrelated objects jammed together rather than one. On
top of that, `· Retry-After` opens with an orphaned bullet, which at 26 px looks
like a bullet-list marker that lost its list.

*Fix:* `X_ANNOT = 500.0` (a 50 px optical gap from the `503`'s right edge at
x≈450), `Y_A1, Y_A2 = 660.0, 696.0` — both inside the numeral's cap band, so
the block centres on the number. Change the string `· Retry-After` →
`Retry-After`.

### 10 — f324–f329 (and every `clear` shot): the pulse ring collides with the outer ring
**Read: f325, f328, f330.**

The `clear` pulse expands to r = 142.8 px. The ring stroke occupies 126→151.2 px.
So at the top of every pulse cycle the pulse draws a thin hairline **inside** the
white ring, separated by a ~4 px dark gap. At f327 this reads unmistakably as an
aliasing artefact — a doubled ring — not as a pulse. It recurs in A4, B2 and C4:
roughly one frame in eight of every `clear` shot has a visible ring defect on the
film's most-shown object.

*Fix:* in the clear-pulse channel, multiply the pulse alpha by
`smoothstep(1.0, 0.72, r / 33.0)` so it is fully faded by r ≈ 118 px and never
enters the ring stroke. The pulse should *dissolve into* the ring, not draw a
second one inside it.

### 11 — C2's dimmed side is not legible, and during the swap neither side is loud
**Read: f806, f840, f860.**

`C2_DIM = 0.45` (scene_hold.py:725). `#E6A93C` at 45 % over `#0C0C0E` resolves to
≈`#6E5220` — contrast ≈2.5:1 against the field. The four differences the shot
exists to teach (ring broken vs solid, core amber vs neutral) **cannot be
resolved on the dim side** at that value; the frozen mark is a smudge, not the
"fully readable diagram" FILM.md promises. Worse: across f836–f843 both marks
pass through comparable alpha, so for 8 frames the frame has two equal subjects
and no loudest thing.

*Fix:* `C2_DIM = 0.62`, `C2_DIM_LABEL = 0.62`. Make the swap a relay in time
rather than a cross-fade: dim the outgoing side over **f836–f841**, hold both
low for 1 frame, then raise the incoming over **f842–f849**. Exactly one side
loud on every frame — which is what the shot's own spec asks for.

### 12 — D1 is 2 seconds of a small icon, off-centre, with no words and four broken-ring frames
**Read: the full f1020–f1079 per-frame sheet.**

- Poses are 6 frames (0.2 s). Nothing on screen but the mark. A first-time viewer
  cannot resolve five states in two seconds — the shot flashes past.
- f1050, f1062, f1074, f1075 each show the ring mid-dash-lerp with large,
  arbitrary gaps: they read as a **damaged** ring, not as a state in transition.
- f1038–f1039: the `verify` needle and trail wedge are still drawn, in neutral,
  over an already-amber broken ring. Two states superimposed.
- Composition: the only object sits at x=1290 with the left 56 % of frame empty
  and no copy column to justify the asymmetry. Layout M's mark position was
  inherited into a shot that has no Layout M.

*Fix (`scene_end.py`, D1 branch):* place the mark at **(960, 540)** for D1 only —
the recap is a centred object, and moving it is free because f1020 is a cut.
Re-time to **8-frame poses / 4-frame morphs** (5×8 + 5×4 = 60, the budget is
unchanged) so each state gets a quarter-second hold. Retract the needle and wedge
to zero *before* the ring starts its colour change at f1038.

### 13 — D2's mark is smaller than the wordmark's cap height
**Read: f1081, f1091, f1130, f1200.**

`CARD_BOX = 200` (scene_end.py:348) draws a ring ~144 px across. `TOWER` at
serif 200 has caps ≈140 px. The identity mark the film spent 34 seconds
establishing at 302 px arrives on the end card the same size as a letter, and at
f1080–f1082 it is alone on screen as a 144 px dot with 1,000 px of nothing under
it. That is a limp final beat.

*Fix:* `CARD_BOX = 200` → `280`, `CARD_C = (960.0, 340.0)` → `(960.0, 320.0)`
(preserves ~76 px of clearance from the mark's bottom edge to the wordmark's cap
top at y≈516).

### 14 — f994–f1019: four text objects, one of them noise
**Read: f995.**

`CLEARED` / `The turn survives.` / `Toronto, CA — inside CA` / `allowed 124200`.
FILM.md's own ceiling is three text objects. `allowed 124200` is a bare six-digit
number with no unit, no label and no prior appearance in the film — a viewer
cannot parse it, so it is grey noise competing with the caption on the shot that
is supposed to feel like relief.

*Fix (`scene_hold.py` C4):* delete readout line 2 (the f976 entry). The shot is
better with three objects and more field.

### 15 — the kicker is at the floor of legibility
**Read: f125, f360.**

`CHECK ONE` / `CHECK TWO` at mono_bold 20 px in `#6E6E6A` on `#0C0C0E` is a
contrast ratio of ≈2.6:1. On a laptop it is fine; on a phone or a compressed
social re-encode it is a grey smear. It is also the smallest type in the film and
it is the first word the viewer ever reads.

*Fix:* 20 px → **22 px**, `KICKER #6E6E6A` → `#7C7C77` (still well below the
caption, still an eyebrow, ≈3.4:1). One value in `brand.py`.

### 16 — 47 frames (1.57 s) of literally nothing
**Runs measured on the PNG masters (ink < 400 px): f0–f14, f90–f108, f330–f336,
f615–f620.**

The f90–f108 hole is **19 frames = 0.63 s of black at second 3** of a 40-second
promo — the exact moment a viewer decides whether to keep watching. FILM.md
budgets 18 frames of held silence there; the reading floor gives `CHECK ONE`
17 frames of slack.

*Fix (`scene_open.py` A2):* pull the kicker entry from f108 to **f99** and the
hero from f111 to **f102**. `CHECK ONE` still holds full opacity for 50 frames
against a 42-frame floor. The f615–f620 gap before `off` is correct and should
stay — it is the only one that is load-bearing.

### 17 — transient sub-55 % text (low priority, but note it)
Every 8-frame sober fade takes its string below the film's own 55 % alpha floor
for ~4 frames: f723 (`Toronto, CA — inside` at ≈15 %), f964 (`PENDING` at ≈10 %).
This is inherent to opacity fades and is only actually *visible* as a defect in
the f964 case, which finding 6 already fixes. Do not chase the rest.

---

## What is excellent — do not break these

- **Nothing is cropped, clipped, or near an edge, in any of 1200 frames.**
  Measured ink bounding box across the whole film: `x 158…1444, y 264…859`
  against a content box of `(160,120)–(1760,960)` and a 96 px safe ring that is
  clean on every frame (max blurred deviation 8/255). The old film's cardinal sin
  is comprehensively gone. Any fix that moves the mark must re-run this check.
- **Zero green.** HSV scan over 400 sampled frames: no pixel in the green band
  anywhere. The passing radar is neutral, as the design system requires.
- **The honest colour splits are perfect.** f469 `SLOW LINK` amber /
  `· STILL ALLOWED` neutral; f733 `Tehran, IR — ` muted / `outside` amber /
  ` CA` muted. Both are exactly right, both are readable, and the C4 recovery
  never turns green. Do not touch the colour logic in these two runs.
- **The M3 pulse→fence contraction, f724–f739**, is the best motion in the film:
  the expanding neutral pulse contracting and locking into an amber dashed fence
  is legible frame by frame, has no judder, and states the idea without a word.
  Whatever else changes, protect this.
- **The two hero cards, f125 and f360.** One idea, 120 px, three seconds, 96 %
  field. These are the only frames in the film where the answer to "where do I
  look" is instant and unambiguous. They are the target the Layout M shots should
  be measured against.
- **f995 and f1199** are the two cleanest composed frames in the piece.
- **No cross-dissolves anywhere**, confirmed at every sampled cut. Black point is
  `#0C0C0E`, grain is invisible at 100 %, no banding in the field, no visible
  encode blocking.
