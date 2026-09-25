# promo/film — the Tower film

A 40-second promo for Tower. **1920 × 1080, 30 fps, exactly 1200 frames.**

    out/tower-film.mp4          the deliverable
    out/tower-film-poster.jpg   the poster frame (f1185, the settled end card)
    out/score.wav               48 kHz / 16-bit stereo, 40.000 s
    out/frames/f_00000.png …    the lossless masters

---

## THE HONESTY NOTE — read this first

**This film contains no footage.** There is no screen recording, no capture, no
photograph, no stock, no external asset of any kind. Every pixel of every one of
the 1200 frames is *drawn from code* — Python stdlib + numpy + Pillow — and
encoded with ffmpeg. The audio is synthesised the same way: `score.py` writes
every sample.

Because the UI is drawn rather than captured, the film owes the product an
extra duty of care. The rules it holds itself to:

* **Every number on screen is a real observed value.** They live in one place,
  `brand.FIXTURE`, and they come from `promo/analysis/footage.json` — a table of
  values observed from a real Tower session. `Toronto, CA`, `Tehran, IR`,
  `net 82 ms`, `api 273 ms`, `503`, `Retry-After`, `attempt 3/8 → 4/8`. Nothing
  is invented and nothing is rounded for looks.
* **The colour language is the product's.** `#0C0C0E` ink, `#E7E6E2` text,
  `#E6A93C` amber, `#E5484D` red, from `promo/analysis/brand.json`, which is
  itself read from `src/Glyph.swift` and `docs/DESIGN.md`. `#30D158` green is
  defined in `brand.py` and **deliberately never drawn**: Tower's passing radar
  is neutral, not green, and inventing a green "all clear" would invent a colour
  language the app does not use.
* **Off-country is AMBER, never red.** Red belongs to `off` (UNGUARDED) and to
  nothing else.
* **A degraded link is still ALLOWED.** `SLOW LINK · STILL ALLOWED` is set with
  the fault clause amber and the verdict neutral, beside a completely neutral
  radar, because a high-latency-but-reachable path does not fire
  `should_block()`. Only offline / captive / edge-unreachable blocks.
* **A block is `503` + `PENDING`, never `403` and never "failed."** The film's
  payload shot says `PENDING`, `The turn survives.`, `503`, `Retry-After`,
  `Retrying · attempt 4/8`, and then shows it clearing *by itself*. Nobody
  restarts anything.
* **Nothing from `brand.json.do_not_claim` appears.** No VPN, no firewall, no
  kill switch, no telemetry, no agent-count claim, no feature Tower does not
  have.

### The one place the mark is not a literal copy

The radar mark's geometry is transcribed from `src/Glyph.swift` unit for unit —
ring at r 33 stroke 6, core 4.5, blips at (64,41)/(38,58)/(58,66), fence at
r 15, sweep at 150 °/s, all of it. **Two values are optically scaled instead of
literally copied, and they are the only two:**

1. **The dashed ring's period.** Glyph.swift uses `[5, 6]` for `holdNet` and
   `[5, 7]` for `off`. Those are correct at menu-bar size. At the film's 374 px
   of ring they draw a 21 px dash against a 25 px stroke — a *square block*,
   nineteen of them around a circle, which reads as a gear or a roulette wheel
   rather than as a ring that has opened. The film uses `(13.82, 6.91)` = 10
   dashes and `(15.36, 7.68)` = 9, each period an exact divisor of the
   circumference. The *appearance* at 20× matches what the app looks like at 1×;
   the unit numbers do not.
2. **The `holdNet` sonar pings** are drawn as two opposed 130° wavefronts rather
   than as closed circles, and the trailing one is scaled to 0.42 of the
   leading one. Two matched concentric rings inside a dashed ring is a bullseye
   at hero scale. The semantic — expanding wavefronts, probing for a path — is
   unchanged.

Both are documented at their call sites and in `FILM.md` §12.2. Everything else
about the mark is the product's own geometry.

---

## RENDER IT

Requirements: Python 3.12, numpy 1.26, Pillow 10.1, ffmpeg 7.0.1. No other
dependencies, and none may be added.

    cd promo/film

    python3 make.py                    # everything: frames → encode → mux → poster
    python3 make.py -j 10              # pick the worker count (default: all cores)
    python3 make.py --fast             # 1280x720 / veryfast / crf 23, for iteration

    python3 make.py --frames 690:780 --stage frames    # one shot only
    python3 make.py --stage encode --open              # re-encode what is on disk

    python3 score.py out/score.wav     # the audio alone

About three minutes end to end on a 10-core machine (~65 s of frames, ~80 s of
x264 at `crf 16 preset slow`). `make.py` refuses to encode a partial frame
range, and `score.py` is run automatically if `out/score.wav` is missing.

**Determinism is a hard requirement, not an aspiration.** Every frame is a pure
function of its absolute index — no clock reads, no unseeded RNG, no
neighbour-frame state — so frame *N* is byte-identical on every run and at every
`-j`. The grain plates are pre-rolled once from a fixed seed. If you add a
`time.time()` or a bare `random`, you have broken the build even though nothing
will fail.

---

## THE MODULE ARCHITECTURE

    brand.py        colour, fonts, easing tokens, the layout grid, the mark's
                    shared geometry constants, the fixture, and the Ctx dataclass
    draw.py         what the DRIVER owns: the vignette and the grain
    make.py         the CLI — shot table, render, encode, mux, poster
    score.py        writes out/score.wav

    scene_open.py   Act A   f   0 … 329   the mark draws itself · "Where you are."
    scene_wire.py   Act B   f 330 … 689   "How the wire is." · holdNet · off
    scene_hold.py   Act C   f 690 … 1019  off-country · the contrast · PENDING
    scene_end.py    Act D   f1020 … 1199  the five-state run · the end card

    FILM.md         the EDL. §1–§11 is the pre-build spec; §12 is the revision
                    that the shipped film actually implements
    notes/          design.md (the marks), ui-truth.md (the product),
                    craft.md (the acceptance spec), review-*.md (four passes
                    over the first cut)

### The scene contract

Every scene module exposes exactly one function:

```python
def draw(ctx) -> None:
    """Paint this scene's content onto ctx.img, in place."""
```

`ctx` is `brand.Ctx`:

| field | |
|---|---|
| `ctx.img` | `PIL.Image`, `RGB`, 1920×1080, already filled with `INK` |
| `ctx.d` | `ImageDraw.Draw(ctx.img)` |
| `ctx.f` | **absolute** frame index, 0…1199 — the load-bearing field |
| `ctx.t` / `ctx.dur` / `ctx.k` / `ctx.sf` | scene-relative conveniences |
| `ctx.P` | global phase in seconds, `f / 30` |

Scenes are **opaque and total**: a scene paints the whole frame, no scene bleeds
into another, and there is no compositing between scenes. A cross-cut is handled
inside whichever scene owns those frames.

Every frame number in `FILM.md` and in the code is **absolute**. Scenes drive off
`ctx.f`, never off `ctx.t`. The mark's phase `P = f / 30` is global and never
resets, so the radar is one continuous machine for the whole forty seconds — it
keeps turning across cuts and across the type cards where it is not even drawn.

### Why there is no `ui.py`

The four scene modules were authored in parallel and each carries its own copy of
the mark. That is deliberate and it is load-bearing: the film's structural match
cut depends on `scene_open` and `scene_wire` drawing the mark with the *same*
implementation, constant for constant, across the 91-frame gap between f329 and
f420. `scene_wire` probes for a `ui.radar_tile` and would adopt one if it found
it — which would put a different implementation on the two halves of that cut.
**If `ui.py` is ever written, both modules adopt it together or neither does.**

The trade is real — four renderers, and they have diverged far enough that they
can no longer read each other's arguments (`scene_open`'s spec dict raises in
`scene_wire` and `scene_end`). But the part that could actually be *seen* has
been closed: **`brand.py` is now the authority for the mark's geometry, not
merely its documentation.** All four scenes resolve

    MARK_C  ·  MARK_BOX  ·  DASH_HOLDNET  ·  DASH_OFF  ·  DASH_FENCE

from `brand.py` at import time, keeping their literal only as a standalone
fallback. `scene_hold` reaches them through a small adapter of its own, since it
draws the mark from interpolated *channels* rather than from a spec dict and
cannot share the other three's tile renderer.

So the duplication that remains is plumbing. Edit a dash in `brand.py` and all
four acts follow; there is no longer a path by which the `holdNet` icon comes
out looking like a different symbol in Act B than in Act C. Verified by
re-rendering 22 frames spanning all four scenes and diffing against the master:
**pixel-identical, zero channels changed.**

If `ui.py` is ever written, the match-cut rule above still binds: `scene_open`
and `scene_wire` adopt it together or neither does.

---

## HOW TO CHANGE A SHOT

1. **Find who owns the frame.** `make.py:SHOTS` maps frame ranges to modules and
   asserts at import that they tile 0…1199 exactly. A gap discovered on frame 700
   has already cost you 700 frames.
2. **Read the shot's docstring.** Every `_shot_*` / `_cN` function states the
   idea of the shot and why its beats land where they do.
3. **Change it, then render just that range:**

       python3 make.py --frames 780:869 --stage frames
       open out/frames/f_00800.png

4. **Move the sound with the picture.** `score.py:TIMELINE` is a flat list of
   `Hit(frame, cue, dB, pan, …)`. Every cue is frame-exact and every state change
   has one. If you retime a beat and do not retime its cue, the film goes soft in
   a way that is very hard to diagnose from the picture.
5. **Re-render everything before you ship.** Several beats are coupled across
   module boundaries — the pulse phase at f329/f420, the mark's global phase, the
   C4 → D1 hand-off.

### The rules a change has to keep

These are in `FILM.md` and `notes/craft.md` in full; the short version:

* **Nothing linear, ever.** Every animated value rides a named easing curve from
  `brand.py`. `EASE_ENTER` arrives, `EASE_MOVE` travels, `EASE_SOBER` holds,
  `EASE_EXIT` leaves, `EASE_IN_OUT` morphs, `SETTLE` / `ARRIVE` are real springs.
* **Failure never bounces.** Any entrance into amber or red is ease-out only.
  `EASE_SOBER` and `EASE_IN_OUT` are monotone by construction; do not put a
  spring on a hold.
* **A state change MORPHS.** Interpolate the geometry — arc sweep, dash count,
  fence radius, needle length — never cross-fade two finished pictures. The
  scenes describe the mark as a *channel dict*, not a state name, precisely so
  that a morph is expressible.
* **A relay, never a cross-fade.** When one string replaces another in a slot,
  the outgoing one vacates completely before the incoming one starts.
* **Stagger.** Elements do not all move on the same frame. 2–4 frames apart, so
  motion has a leading edge.
* **Sub-pixel.** Animate in float, render supersampled. Integer-snapped movement
  judders and instantly reads cheap. The mark is drawn at 4× and LANCZOS-
  downsampled; type is stamped from cached glyph masks at float positions.
* **One loudest thing per frame.** At most three text objects, at most one accent
  hue.
* **Nothing inside the 96 px action-safe ring.** Verified: max luma there is 16
  across all 1200 frames, which is grain.

---

## VERIFYING A BUILD

```
ffprobe -v error -count_frames -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,nb_read_frames,duration \
  -of default=nw=1 out/tower-film.mp4
```

Must read exactly `1920 × 1080`, `30/1`, `nb_read_frames=1200`,
`duration=40.000000`, plus an AAC stream at 48 kHz / 2 ch / 40.000 s.

Worth re-running after any layout change:

* ink bounding box across all frames stays inside the content box, and the 96 px
  safe ring stays clean;
* zero pixels in the green band, anywhere;
* minimum luma inside the ring stroke stays ≥ 200 on frames where the ring is
  solid (this catches the `ImageDraw.Draw(im)` vs `Draw(im, 'RGBA')` puncture
  bug — on an RGBA image the former *replaces* the destination pixel, so a
  translucent ornament crossing the ring erases a band out of it);
* the empty-field mean stays at `#0C0C0E` ± 1 (the grain is signed and
  zero-mean; if someone reintroduces `abs()` it will only ever lift the black).

---

## WHAT THIS REPLACES

The pipeline in `promo/*.py` cut a 3032 × 1490 screen recording with heavy zooms
and speed ramps. It is not used here, it is not imported here, and nothing in
this directory reads a frame of video. `promo/analysis/footage.json` survives for
one reason only: it is the table of real observed values that `brand.FIXTURE`
copies from, so the drawn UI shows true numbers instead of invented ones.
