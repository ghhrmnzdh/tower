# High-Energy Tech Promo — ffmpeg 7.0.1 Technique Cookbook

Constrained toolchain: **ffmpeg 7.0.1 filters only** + **Pillow/numpy-generated RGBA PNG overlays**.
No After Effects, no moviepy, no third-party filter plugins.

Every recipe below is tagged:

- **VERIFIED** — the exact command was *executed* on this machine's ffmpeg build and produced the
  expected output (frame counts / durations / pixel measurements checked). Filter existence and
  parameter names checked with `ffmpeg -h filter=NAME`.
- **VERIFIED (filter only)** — `ffmpeg -h filter=NAME` confirms the filter and its option names on
  this build, but the specific artistic recipe was not rendered end-to-end.
- **UNVERIFIED** — reasoning/craft guidance, not a runnable claim.

Build fingerprint (`ffmpeg -version`):

```
ffmpeg version 7.0.1  (homebrew, /opt/homebrew/bin/ffmpeg)
libavutil 59.8.100 / libavcodec 61.3.100
--enable-gpl --enable-libx264 --enable-libx265 --enable-libass --enable-libfreetype
--enable-libzimg --enable-videotoolbox --enable-libvidstab --enable-frei0r
503 filters available
```

Test source used for all verification runs:
`/Users/omega/room/mainprojects/tower/promo/media/source.mov`
— 3032x1490, H.264, **variable frame rate** (`r_frame_rate=240/1`, `avg_frame_rate≈53.87`), 87.4 s.
That is a typical macOS screen recording and it is the reason §0 exists.

Convention used throughout:

```bash
SRC=/Users/omega/room/mainprojects/tower/promo/media/source.mov
W=1920; H=1080; FPS=30
```

---

## 0. The three rules that make everything else work

These are not style notes. Every one of them was a *measured failure* during verification.

### 0.1 Normalize the VFR screen recording to CFR **first** — VERIFIED

A macOS screen recording is variable-frame-rate. Every frame-count, beat-grid and `trim=start_frame`
calculation downstream is nonsense until you force CFR.

```bash
ffmpeg -y -i "$SRC" \
  -vf "fps=30,scale=1920:-2:flags=lanczos,pad=1920:1080:0:(1080-ih)/2:black,setsar=1,format=yuv420p" \
  -fps_mode cfr -r 30 \
  -c:v libx264 -crf 16 -preset slow -an normalized.mp4
```

Verified: 6.033 s in → 181 frames out at exactly `r_frame_rate=30/1`.

### 0.2 `setpts` and `trim` destroy the frame-rate metadata — you MUST restate it — VERIFIED

This is the single nastiest trap in the whole toolchain.

```bash
# WRONG — silently produces a 25 fps file and DROPS 9 of 60 frames
ffmpeg -i normalized.mp4 -vf "trim=start_frame=0:end_frame=60,setpts=PTS-STARTPTS" out.mp4
#   measured: nb_frames=51, duration=2.040000   <-- 51/2.04 = 25 fps

# RIGHT — restate the rate on the output (and/or end the chain with fps=30)
ffmpeg -i normalized.mp4 -vf "trim=start_frame=0:end_frame=60,setpts=PTS-STARTPTS" \
  -fps_mode cfr -r 30 out.mp4
#   measured: nb_frames=60, duration=2.000000
```

Rule: **every** command in this cookbook ends with `-fps_mode cfr -r 30`, and every filtergraph that
touches PTS ends with `fps=30`. ffmpeg 7's default `-fps_mode auto` is VFR-passthrough for MP4 and
will happily drop or duplicate frames to match whatever rate it guessed.

(Note: the online docs list a `strip_fps` option on `setpts`. It does **not** exist on this 7.0.1
build — `ffmpeg -h filter=setpts` shows only `expr`.)

### 0.3 `trim=start_frame/end_frame` is frame-exact; `-ss` is not — VERIFIED

`end_frame` is **exclusive**: `trim=start_frame=0:end_frame=60` yields exactly 60 frames (measured).
`select` is the equivalent and is **inclusive** on both ends:

```bash
# frames 45..89 inclusive = 45 frames  (measured: 45)
ffmpeg -y -i normalized.mp4 -vf "select='between(n,45,89)',setpts=N/30/TB" \
  -fps_mode cfr -r 30 -c:v libx264 -crf 18 out.mp4
```

`setpts=N/30/TB` is the "renumber to a clean 30 fps grid from frame 0" idiom. Use it any time you
have re-ordered, frozen, reversed or spliced frames.

Input `-ss` seeks to the nearest decodable point and is only frame-exact if placed *after* `-i`
(slow). For hyperframe work, decode from 0 and cut with `trim`/`select`. — UNVERIFIED (craft note)

---

## 1. Speed ramps

### 1.1 Constant speed change — VERIFIED

```bash
# 2x faster
ffmpeg -y -i normalized.mp4 -vf "setpts=0.5*PTS,fps=30" -fps_mode cfr -r 30 \
  -c:v libx264 -crf 18 -an fast.mp4
# measured: 6.033 s -> 3.033 s
```

`fps=30` at the end is mandatory: without it you get duplicated/dropped frames when the retimed PTS
grid does not land on 30 fps boundaries.

Slow motion: `setpts=2.0*PTS`. On a 30 fps source this just holds frames. If you want *real* slow
motion you need a high-fps source (the raw `source.mov` is nominally 240 fps VFR — capture at high
rate and normalize to 30 only after the ramp) or `minterpolate` (present on this build, expensive,
and it smears UI text — avoid for screen recordings). — UNVERIFIED (craft note)

### 1.2 Smooth speed ramp across a shot (the real thing) — VERIFIED

A ramp is not a step. If speed varies continuously as `s(t)`, output time is the integral of
`1/s(t)`. For a **linear** speed ramp from `s0` to `s1` over the first `D` seconds, then holding at
`s1`:

```
k       = (s1 - s0) / D
out(T)  = (1/k) * ln( (s0 + k*T) / s0 )                 for T <  D
out(T)  = (1/k) * ln( s1 / s0 ) + (T - D) / s1          for T >= D
```

Feed that to `setpts` divided by `TB`. Example: ramp 1x → 3x over the first 2 s, then hold 3x:

```bash
# k = (3-1)/2 = 1  ->  1/k = 1
ffmpeg -y -i normalized.mp4 \
  -vf "setpts='(if(lt(T,2), 1.0*log((1+1.0*T)/1), 1.0*log(3/1) + (T-2)/3))/TB',fps=30" \
  -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an ramp.mp4
```

Verified numerically: predicted output duration `ln(3) + (6.0333-2)/3 = 2.4316 s`;
**measured 2.433 s**. The formula is right, not hand-waved.

Handy closed forms (all use `T` = input time in seconds, `TB` = timebase):

| Ramp | `setpts` expr body |
|---|---|
| ease *into* speed (1x→Nx over D) | `(D/(N-1))*log((1+((N-1)/D)*T)/1)` |
| ease *out of* speed (Nx→1x over D) | `(D/(1-N))*log((N+((1-N)/D)*T)/N)` |
| hold after the ramp | `+ (T-D)/N` |

**Do not** try to build a ramp by concatenating 5 constant-speed `setpts` segments. The seams are
visible as velocity steps — that is the classic "cheap ramp" tell. — UNVERIFIED (craft note)

### 1.3 Freeze frames

**Best recipe — one filter, frame-exact — VERIFIED**

```bash
# hold frame 59 for 12 frames total (1 original + 11 clones)
ffmpeg -y -i normalized.mp4 -vf "loop=loop=11:size=1:start=59,fps=30" \
  -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an freeze.mp4
# measured: 181 -> 193 frames (exactly +11)
```

`loop=loop=N:size=1:start=F` freezes input frame `F` for `N` extra frames and correctly retimes
everything after it. This is by far the cleanest freeze on this build.

**Freeze the LAST frame (tail hold) — VERIFIED**

```bash
ffmpeg -y -i normalized.mp4 -vf "tpad=stop_mode=clone:stop_duration=0.5" \
  -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an tail.mp4
# measured: 181 -> 196 frames (+15 = 0.5 s @30)
```

**Split/trim/tpad/concat form (if you need to run different filters on the frozen segment) — VERIFIED**

```bash
ffmpeg -y -i normalized.mp4 -filter_complex "\
[0:v]split=3[a][b][c];\
[a]trim=start_frame=0:end_frame=60,setpts=PTS-STARTPTS[A];\
[b]trim=start_frame=59:end_frame=60,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop=11,setpts=N/30/TB[F];\
[c]trim=start_frame=60,setpts=PTS-STARTPTS[C];\
[A][F][C]concat=n=3:v=1:a=0,fps=30[v]" \
 -map "[v]" -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an freeze2.mp4
# measured: 193 frames — identical to the loop-filter version
```

> **Trap (measured):** `trim` down to a single frame destroys the frame *duration*, so
> `tpad=stop_mode=clone` emits all 12 clones **at the same PTS** (`showinfo` showed
> `pts_time:0, 0.0333, 0.0333, 0.0333, ...`) and the encoder collapsed them to **2** frames.
> The `setpts=N/30/TB` after `tpad` is what fixes it. Without it the freeze silently vanishes.

### 1.4 Reverse-hold (play forward, snap back, play on) — VERIFIED

```bash
ffmpeg -y -i normalized.mp4 -filter_complex "\
[0:v]split=3[a][b][c];\
[a]trim=start_frame=0:end_frame=60,setpts=PTS-STARTPTS[A];\
[b]trim=start_frame=41:end_frame=60,setpts=PTS-STARTPTS,reverse,setpts=PTS-STARTPTS[R];\
[c]trim=start_frame=41,setpts=PTS-STARTPTS[C];\
[A][R][C]concat=n=3:v=1:a=0,fps=30[v]" \
 -map "[v]" -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an revhold.mp4
# measured: 60 + 19 + 140 = 219 frames, exactly as designed
```

`reverse` buffers the *entire* input segment in RAM — always `trim` **before** `reverse`, never
after. The second `setpts=PTS-STARTPTS` after `reverse` is required (reverse leaves the PTS
descending relative to the segment origin).

---

## 2. Zoom / punch-in on a static screen recording, without shimmer

### 2.1 Why naive `zoompan` jitters

`zoompan` internally computes an integer crop rectangle in the *input* pixel grid, then scales that
rectangle to the output size. Because `x`, `y` and the crop dimensions are **rounded to whole input
pixels**, a slow zoom advances in discrete steps: the image sticks for a frame or two, then jumps.
On a static screen recording — where nothing else in the frame is moving to mask it — that reads as
shimmer/vibration on every piece of UI text.

The fix is to make one input pixel *much smaller than one output pixel*: **upscale hard before
`zoompan`**, so the rounding error is a fraction of an output pixel. `scale=8000:-2` is the classic
number — it is not magic, it is "big enough that 1 input px ≈ 0.24 output px at 1920 wide."

**Measured on this machine** (3s punch-in on a static screen recording; "roughness" = mean deviation
of the frame-to-frame difference series from its own local trend, normalized — higher = more
stick-and-jump):

| Chain | mean inter-frame diff | roughness |
|---|---|---|
| static control (no zoom) | 0.007 | — |
| zoompan direct on 2648x1490 source | 5.99 | **26.21 %** |
| `scale=8000:-2` → zoompan (linear zoom) | 4.87 | **10.39 %** |
| zoompan direct, eased curve | 2.74 | **15.56 %** |
| `scale=8000:-2` → zoompan, eased curve | 2.42 | **9.26 %** |

The upscale cuts jitter by **~2.5x** on the same zoom curve. Easing helps too, independently.

### 2.2 The chain that works — VERIFIED

```bash
# 3032x1490 source. First crop to the 16:9 the output wants (2648x1490),
# THEN upscale, THEN zoompan, and let zoompan do the 1920x1080 landing.
ffmpeg -y -i "$SRC" -filter_complex "\
sws_flags=lanczos;\
[0:v]fps=30,\
crop=2648:1490,\
scale=8000:-2,\
zoompan=z='if(lte(on,45),1+0.18*(1-pow(1-on/45,3)),1.18)':d=1\
       :x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30,\
setsar=1,format=yuv420p[v]" \
 -map "[v]" -fps_mode cfr -r 30 -c:v libx264 -crf 16 -preset slow punch.mp4
```

Four non-obvious things in there, all load-bearing:

1. **`crop` to the output aspect *before* `zoompan`.** `zoompan` does not preserve aspect — it
   stretches its crop rectangle to `s=`. A 3032x1490 (2.035:1) source fed straight to `s=1920x1080`
   comes out horizontally squashed. `crop=2648:1490` gives exactly 16:9 first.
2. **`d=1`.** `zoompan`'s default `d=90` means *each input frame is held for 90 output frames* —
   correct for a still image, catastrophic for video. With `d=1` the input and output frame counts
   match and `on` becomes a global output frame index.
3. **`sws_flags=lanczos;` as a filtergraph prefix.** `zoompan` does its own internal `swscale` and
   gives you no way to set the flags per-filter. The graph-level `sws_flags=...;` prefix (verified
   working in `-filter_complex`) upgrades that internal scale from bilinear to lanczos. On UI text
   this is the difference between "punch-in" and "punch-in through vaseline".
4. **Eased curve via `on`, not the incremental `zoom+0.0015` idiom.** `1+A*(1-pow(1-on/N,3))` is a
   cubic ease-out: fast off the mark, settling gently. The incremental form is linear and its
   `min()` clamp makes the zoom *stop dead* at the top — a hard velocity discontinuity you can see.

Cost, measured: 6 s of 30 fps 1920x1080 output through the 8000-wide path took **3.17 s wall**
(376 % CPU) on this machine. The upscale is affordable; don't skip it to save time.

### 2.3 Eased-curve library (drop into `z=`) — UNVERIFIED (math; the ease-out cubic form is VERIFIED)

Let `p = on/N` clamped to `[0,1]`, `A` = zoom amount (e.g. `0.18` for a 1.18x punch):

| Feel | expression |
|---|---|
| ease-out cubic (default punch) | `1+A*(1-pow(1-p,3))` |
| ease-out quint (snappier) | `1+A*(1-pow(1-p,5))` |
| ease-in-out cubic (drifty push) | `1+A*if(lt(p,0.5), 4*pow(p,3), 1-pow(-2*p+2,3)/2)` |
| linear (Ken Burns drift) | `1+A*p` |

Punch *out* is the same with `1+A-A*(...)`.

### 2.4 Why you cannot do this with `crop` alone — VERIFIED

`crop`'s `w`/`h` are evaluated **once at init** on this build; only `x`/`y` are re-evaluated per
frame. So `crop` can pan but cannot zoom. Also measured on this build:

```
[Parsed_crop_0] Timeline ('enable' option) not supported with filter 'crop'
```

`crop` has **no `enable` support here** — gate it inside the `x`/`y` expressions instead (see §4.4).
(`crop` also has no `eval` option on this build; `ffmpeg -h filter=crop` lists only
`out_w/w, out_h/h, x, y, keep_aspect, exact`.)

### 2.5 Pan-only (no zoom) — VERIFIED pattern

If you only need a drift, `crop` is cheaper and pixel-exact:

```bash
ffmpeg -y -i normalized.mp4 \
  -vf "crop=w=1880:h=1058:x='20+40*(n/180)':y='11',scale=1920:1080:flags=lanczos,setsar=1,fps=30" \
  -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an pan.mp4
```

Same integer-rounding caveat applies — for a *slow* pan, put a `scale=8000:-2` in front and a
`scale=1920:1080` behind.

---

## 3. Transitions

### 3.1 Hard cut on the beat — VERIFIED

```bash
# cut from A to B exactly at frame 45
ffmpeg -y -i A.mp4 -i B.mp4 -filter_complex "\
[0:v]trim=start_frame=0:end_frame=45,setpts=PTS-STARTPTS[a];\
[1:v]trim=start_frame=0:end_frame=45,setpts=PTS-STARTPTS[b];\
[a][b]concat=n=2:v=1:a=0,fps=30[v]" \
 -map "[v]" -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an cut.mp4
# measured: exactly 90 frames
```

For long timelines, the **concat demuxer** on pre-rendered, identically-encoded segments is faster
and stream-copies — VERIFIED:

```bash
printf "file '%s'\nfile '%s'\n" /abs/A.mp4 /abs/B.mp4 > list.txt
ffmpeg -y -f concat -safe 0 -i list.txt -c copy timeline.mp4
# measured: 181 + 181 = 362 frames, no re-encode
```

Requires identical codec/resolution/pixfmt/timebase across segments. Render every segment with the
same encoder settings and this is bulletproof.

### 3.2 `xfade` — the complete transition list on **this** build — VERIFIED

`ffmpeg -h filter=xfade` on 7.0.1 reports `transition` in range **-1 to 57**. All 58 named
transitions were **smoke-tested and all 58 rendered successfully**:

```
custom(-1)  fade(0)        wipeleft(1)    wiperight(2)   wipeup(3)      wipedown(4)
slideleft(5) slideright(6) slideup(7)     slidedown(8)   circlecrop(9)  rectcrop(10)
distance(11) fadeblack(12) fadewhite(13)  radial(14)     smoothleft(15) smoothright(16)
smoothup(17) smoothdown(18) circleopen(19) circleclose(20) vertopen(21) vertclose(22)
horzopen(23) horzclose(24) dissolve(25)   pixelize(26)   diagtl(27)     diagtr(28)
diagbl(29)   diagbr(30)    hlslice(31)    hrslice(32)    vuslice(33)    vdslice(34)
hblur(35)    fadegrays(36) wipetl(37)     wipetr(38)     wipebl(39)     wipebr(40)
squeezeh(41) squeezev(42)  zoomin(43)     fadefast(44)   fadeslow(45)   hlwind(46)
hrwind(47)   vuwind(48)    vdwind(49)     coverleft(50)  coverright(51) coverup(52)
coverdown(53) revealleft(54) revealright(55) revealup(56) revealdown(57)
```

There is **no whip-pan transition** and **no glitch transition** in that list. Build those yourself
(§3.5, §4).

Options: `transition`, `duration` (0–60 s, default 1), `offset` (start relative to input 0),
`expr` (only for `transition=custom`).

**Hard requirement:** both inputs must have identical resolution, pixel format, frame rate *and
timebase*. Normalize both with `fps=30,format=yuv420p,setsar=1` before `xfade` or it will refuse or
misbehave.

Useful ones for a tech promo, and what they actually read as — UNVERIFIED (craft note):

| Transition | Reads as |
|---|---|
| `fadewhite` | flash cut / impact — the workhorse |
| `fadeblack` | dip to black — a breath, a chapter break |
| `fadefast` / `fadeslow` | weighted dissolve; `fadefast` is punchier than plain `fade` |
| `smoothleft/right` | soft directional wipe — good under a whip |
| `zoomin` | push-through — pairs with a punch-in on the outgoing shot |
| `pixelize`, `dissolve` | data/glitch flavor, use sparingly |
| `circleopen`, `radial` | avoid — reads as 2003 slideshow |

### 3.3 Flash / whiteout

**(a) Hard 2-frame white insert — VERIFIED**

```bash
ffmpeg -y -i normalized.mp4 -f lavfi -t 0.0667 -i "color=c=white:s=1920x1080:r=30" \
 -filter_complex "\
[0:v]split=2[a][c];\
[a]trim=start_frame=0:end_frame=45,setpts=PTS-STARTPTS[A];\
[1:v]format=yuv420p,setsar=1,trim=end_frame=2,setpts=PTS-STARTPTS[FL];\
[c]trim=start_frame=45,setpts=PTS-STARTPTS[C];\
[A][FL][C]concat=n=3:v=1:a=0,fps=30[v]" \
 -map "[v]" -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an flash.mp4
# measured: 181 + 2 = 183 frames
```

This *adds* 2 frames to the timeline. It is the "hyperframe" flash — a true insert.

**(b) Decaying whiteout that does NOT add frames — VERIFIED (this is the better-looking one)**

`eq` supports per-frame expressions with `eval=frame`, so you can author a proper exponential
falloff instead of a binary strobe:

```bash
ffmpeg -y -i normalized.mp4 \
  -vf "eq=brightness='if(between(n,45,53), 1.0*pow(1-(n-45)/8,1.0), 0)':eval=frame,fps=30" \
  -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an whiteout.mp4
```

Measured in the master render (§9): frame 60 mean luma **217.7** decaying to **164.9** by frame 62,
against a base of ~32. Change the exponent for the falloff shape: `pow(...,1)` linear,
`pow(...,2.2)` snappier, `pow(...,0.6)` heavier.

`eq` expression variables available: `n` (frame), `t` (seconds), `pos`, `r` (frame rate).
Remember `eval=frame` — without it the expression is evaluated once and you get a constant.

### 3.4 Dip to black — VERIFIED

```bash
# 4-frame out, 4-frame in, centred on frame 45 @30fps
ffmpeg -y -i normalized.mp4 \
  -vf "fade=t=out:st=1.4:d=0.133:c=black,fade=t=in:st=1.533:d=0.133:c=black,fps=30" \
  -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an dip.mp4
```

`fade` also accepts frame-domain params directly, which is what you want for hyperframe work:
`fade=t=out:start_frame=42:nb_frames=4:c=black`. And `fade` has `alpha=1` for fading RGBA overlays
without touching the plate. Between two clips, `xfade=transition=fadeblack` is the one-shot form.

### 3.5 Whip pan — build it, it doesn't exist as a transition — VERIFIED

A whip is three things: a fast directional *slide*, a directional *blur that ramps up and back down*,
and a *hard landing*. `dblur`'s `radius` is a float with runtime-command support (`T` flag) but is
not an expression — so ramp it with the **`sendcmd`** filter, which is the general answer to
"animate a parameter that has no expression".

```bash
ffmpeg -y -i A.mp4 -i B.mp4 -filter_complex "\
[0:v][1:v]xfade=transition=slideleft:duration=0.2:offset=1.8[xf];\
[xf]sendcmd=c='\
 1.800 dblur@whip radius 60;\
 1.867 dblur@whip radius 110;\
 1.933 dblur@whip radius 60;\
 2.000 dblur@whip radius 0',\
 dblur@whip=angle=0:radius=0,fps=30[v]" \
 -map "[v]" -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an whip.mp4
```

Notes:

- **`sendcmd` syntax (measured the hard way):** an interval is `TIME target command arg` and
  *additional commands in the same interval are comma-separated with no repeated timestamp*.
  Writing `1.5 f a 1, 1.5 f b 2` fails with
  `Missing separator or extraneous data found at the end of interval #0`. Correct: `1.5 f a 1, f b 2`.
  Intervals are separated by `;`.
- The `@label` instance name (`dblur@whip`) is how `sendcmd` addresses a specific filter instance.
- `dblur=angle=0` is horizontal (whip left/right); `angle=90` vertical (whip up/down).
- Any option printed with the `T` flag by `ffmpeg -h filter=NAME` can be driven this way. On this
  build that includes `rgbashift`, `chromashift`, `dblur`, `gblur`, `vibrance`, `colorchannelmixer`,
  `eq`, `hue`, `noise`.

**`xfade=transition=custom` also works** — VERIFIED. Variables: `X, Y, W, H, P` (progress 0→1),
`PLANE`, `A`, `B`, and the samplers `a0(x,y)..a3(x,y)` / `b0(x,y)..b3(x,y)`. Minimal directional
push, confirmed rendering:

```bash
... xfade=transition=custom:duration=0.2:offset=0.4:expr='if(lt(X+W*P*1.0,W), A, B)' ...
```

The `a0()/b0()` samplers always read plane 0, so multi-plane custom exprs need `PLANE` branching —
in practice prefer the `sendcmd` + real-filter approach above. — UNVERIFIED (craft note)

---

## 4. Glitch, RGB split, and shake

### 4.1 `rgbashift` — full option set on this build — VERIFIED

```
rh rv gh gv bh bv ah av   (int, -255..255, default 0)   edge = smear | wrap
```

All options carry the `T` flag; the filter **has timeline `enable` support**.

**Critical gotcha (verified):** the shift amounts are `<int>`, **not expressions**. You cannot write
`rh='-20*sin(n)'`. You get exactly two ways to animate it — `enable` (on/off) or `sendcmd`.

**3-frame RGB split hit — VERIFIED**

```bash
ffmpeg -y -i normalized.mp4 \
  -vf "rgbashift=rh=-14:bh=14:edge=smear:enable='between(n,45,47)',fps=30" \
  -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an glitch.mp4
```

**Decaying split, stacked-`enable` form — VERIFIED**

```bash
ffmpeg -y -i normalized.mp4 -vf "\
rgbashift=rh=-24:bh=24:enable='eq(n,45)',\
rgbashift=rh=-12:bh=12:enable='eq(n,46)',\
rgbashift=rh=-5:bh=5:enable='eq(n,47)',fps=30" \
 -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an glitch2.mp4
```

**Decaying split, `sendcmd` form (cleaner for long ramps) — VERIFIED**

```bash
ffmpeg -y -i normalized.mp4 -vf "\
sendcmd=c='1.5000 rgbashift@g rh -24, rgbashift@g bh 24;\
           1.5333 rgbashift@g rh -10, rgbashift@g bh 10;\
           1.5667 rgbashift@g rh 0,   rgbashift@g bh 0',\
rgbashift@g=rh=0:bh=0,fps=30" \
 -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an glitch3.mp4
```

Verified end-to-end in the master render: mean |R−B| in the frame jumped from **4.21** (frame 44) to
**9.69** (frame 46) — the hit is real and it lands on the frame you asked for.

### 4.2 `chromashift` — the subtler, more "premium" split — VERIFIED

```
cbh cbv crh crv   (int, -255..255)   edge = smear | wrap
```

```bash
ffmpeg -y -i normalized.mp4 \
  -vf "chromashift=cbh=-10:crh=10:enable='between(n,45,47)',fps=30" \
  -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an chroma.mp4
```

`rgbashift` displaces whole RGB channels (loud, obviously "glitch"). `chromashift` displaces only
the Cb/Cr planes — luma edges stay registered, so text stays legible and the artifact reads as a
*signal* problem rather than a *filter*. On a dark UI capture, `chromashift` at ±8..12 for 2–3
frames is the tasteful version; `rgbashift` at ±20+ is the "hyperpop" version. — UNVERIFIED (craft)

### 4.3 Combining into a real glitch hit — UNVERIFIED (craft note)

A convincing 3-frame glitch stacks four things on the *same* frames:
`rgbashift` (or `chromashift`) + a 1-frame luma spike (`eq=brightness`) + a 2px `crop` jolt +
a `noise` burst. All four are `enable`-gated to the same `between(n,A,B)` window. One of them alone
always looks like a filter; four together looks like a dropped frame.

### 4.4 Light camera shake — VERIFIED

`crop` has **no `enable` support** on this build (measured), so gate the shake inside the
expressions. Always `crop` a margin then `scale` back to full frame, so the shake never reveals an
edge:

```bash
# constant idle shake
ffmpeg -y -i normalized.mp4 -vf "\
crop=w=1880:h=1058:x='20+8*sin(n*1.9)+4*sin(n*4.3)':y='11+6*cos(n*2.3)',\
scale=1920:1080:flags=lanczos,setsar=1,fps=30" \
 -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an shake.mp4

# 6-frame impact shake that decays to zero, on the beat at frame 45
ffmpeg -y -i normalized.mp4 -vf "\
crop=w=1880:h=1058\
:x='20+if(between(n,45,50),14*sin(n*3.1)*(1-(n-45)/6),0)'\
:y='11+if(between(n,45,50),10*cos(n*4.7)*(1-(n-45)/6),0)',\
scale=1920:1080:flags=lanczos,setsar=1,fps=30" \
 -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an impact.mp4
```

Two incommensurate sine frequencies (`1.9` and `4.3`) avoid an obvious repeating loop.
`(1-(n-45)/6)` is the decay envelope — an impact shake that doesn't decay reads as a broken tripod.

> **Naming correction:** `vibrance` is **not** a shake filter. On this build it is a saturation
> filter (`intensity`, `rbal`, `gbal`, `bbal`, `rlum`, `glum`, `blum`, `alternate`) that boosts
> low-saturation pixels more than already-saturated ones — VERIFIED via `-h filter=vibrance`. It is
> genuinely useful for grade (§6.5), just not for movement.

---

## 5. Overlaying an RGBA PNG sequence at 30 fps

Author the overlays in Pillow/numpy at exactly **1920x1080 RGBA, straight (non-premultiplied)
alpha**, numbered from 0: `ov_0000.png`, `ov_0001.png`, …

### 5.1 The incantation — VERIFIED

```bash
ffmpeg -y -i base.mp4 \
  -framerate 30 -start_number 0 -i "ov/ov_%04d.png" \
  -filter_complex "\
[1:v]format=rgba,setpts=PTS-STARTPTS[ovl];\
[0:v][ovl]overlay=x=0:y=0:format=auto:eof_action=pass:shortest=0[v]" \
 -map "[v]" -fps_mode cfr -r 30 \
 -c:v libx264 -crf 16 -preset slow -pix_fmt yuv420p -an out.mp4
```

### 5.2 The alpha / timing pitfalls, each measured

**(a) `-framerate` goes BEFORE `-i`. `-r` after `-i` is a different, wrong thing.** — VERIFIED

```
-framerate 30 -i "ov_%04d.png"   ->  60 files -> 60 frames, 2.000 s, r_frame_rate=30/1   ✅
-i "ov_%04d.png" -r 30           ->  60 files -> 72 frames, 2.400 s                      ❌
```

The image2 demuxer defaults to **25 fps**. `-r 30` as an *output* option then duplicates 12 frames
to stretch 2.4 s. Your 60-frame animation silently runs 20 % slow with stutter.

**(b) `eof_action` defaults to `repeat` — your overlay burns in forever.** — VERIFIED, and this is
the worst one because it looks fine in the first two seconds.

Measured: a 60-frame (2 s) overlay composited onto a 181-frame (6 s) base with default settings —
at **frame 170**, mean brightness along the overlay's progress-bar row was **253.0** (the last PNG
still fully painted). With `eof_action=pass`: **30.6** (clean plate). Always set
`eof_action=pass`.

**(c) `shortest=0` (the default) is what you want** when the base is the longer stream.
`shortest=1` truncates the output to the PNG sequence.

**(d) Delaying the sequence: pad with *transparent* frames, then renumber.** — VERIFIED

```bash
[1:v]format=rgba,tpad=start=60:start_mode=add:color=#00000000,setpts=N/30/TB[ovl];
```

`color=#00000000` is a fully transparent pad (the default `black` is opaque and will black out your
video for those 60 frames). The `setpts=N/30/TB` re-lays the padded sequence on the 30 fps grid.

**(e) Premultiplied alpha.** Pillow's `Image.save()` writes **straight** alpha, which matches
`overlay`'s default `alpha=straight`. If you ever produce premultiplied RGBA (e.g. by compositing in
numpy without dividing back out), tell `overlay`:
`overlay=...:alpha=premultiplied` — VERIFIED (with a deliberately premultiplied PNG, RMSE against
the true straight-alpha composite was **2.25** with the flag vs **2.69** without). There are also
standalone `premultiply` / `unpremultiply` filters on this build if you need to convert.

**(f) `overlay`'s `format` option.** Default is `yuv420` — the overlay's chroma gets subsampled
during the composite. Options on this build: `yuv420 yuv420p10 yuv422 yuv422p10 yuv444 yuv444p10
rgb gbrp auto`. Measured against a ground-truth straight-alpha composite done in numpy, on a
yuv420p screen-recording plate with white text, text-region RMSE was:

| overlay format chain | RMSE |
|---|---|
| `format=yuv420` (default) | 1.97 |
| `format=auto` | 2.15 |
| `format=gbrp` (plate → gbrp, back to yuv420p) | 2.30 |
| `format=yuv444` (plate → yuv444p, back to yuv420p) | 2.43 |

**Honest conclusion:** when the plate is already 4:2:0 and the overlay is white/high-contrast, the
`format` choice is in the noise — all four are within one 8-bit code value, and the extra colorspace
round-trips are marginally *worse*. `format=auto` is the safe default; don't spend a `yuv444p`
round-trip on it. The chroma-subsampling argument only bites for **saturated colored text on a
saturated background**, and the real fix there is a design change (§7). — the numbers are VERIFIED;
the generalization is UNVERIFIED.

**(g) Overlay position.** `overlay` evaluates `x`/`y` per frame by default (`eval=frame`), with
`n`, `t`, `W`, `H`, `w`, `h`, `x`, `y` available. So you can slide a full-frame RGBA card in with
`x='-1920+1920*min(1,(n-60)/8)'` without re-rendering the PNGs. — UNVERIFIED (craft note)

### 5.3 Generating the sequence (Pillow) — VERIFIED pattern

```python
from PIL import Image, ImageDraw, ImageFont
W, H, N = 1920, 1080, 60
FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"   # exists on this machine
f = ImageFont.truetype(FONT, 96)
for i in range(N):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))   # fully transparent
    d  = ImageDraw.Draw(im)
    a  = int(255 * min(1, i / 12))                 # 12-frame fade-in
    d.text((160, 620), "FAIL-CLOSED BY DEFAULT", font=f, fill=(255, 255, 255, a))
    im.save(f"ov/ov_{i:04d}.png")
```

`/System/Library/Fonts/SFNSDisplay.ttf` does **not** exist on this machine (verified — Pillow raises
`OSError: cannot open resource`). Use `/System/Library/Fonts/Supplemental/Arial Bold.ttf`,
`/System/Library/Fonts/Avenir Next.ttc`, or ship a font with the project. Wrap
`ImageFont.truetype()` in a check that *fails loudly* — a silent fallback to
`ImageFont.load_default()` gives you an 11px bitmap font in a 1080p frame and you will not notice
until the render.

---

## 6. Premium treatments (letterbox / vignette / grain / scanlines)

The difference between "premium" and "cheap" here is almost entirely **amplitude**. Every one of
these effects is 3x too strong at its default.

### 6.1 Letterbox — VERIFIED

```bash
# (a) true 2.39:1 crop — loses the top/bottom of the screen recording
ffmpeg -y -i normalized.mp4 \
  -vf "crop=1920:804:0:(ih-804)/2,pad=1920:1080:0:138:black,setsar=1,fps=30" \
  -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an letterbox_crop.mp4

# (b) fit inside the bars — keeps all the content, content gets smaller
ffmpeg -y -i normalized.mp4 \
  -vf "scale=1920:804:force_original_aspect_ratio=decrease:flags=lanczos,\
pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30" \
  -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an letterbox_fit.mp4
```

`1920/2.39 = 803.3 → 804` (must be even for yuv420p). Bar height `(1080-804)/2 = 138`.
For a screen recording, (b) is usually right — you rarely want to amputate the menu bar. Bars are
also free real estate for lower-third overlays that never touch the UI. — UNVERIFIED (craft note)

### 6.2 Vignette — VERIFIED, with a measured strength table

`vignette` options on this build: `angle/a` (default `PI/5`), `x0`, `y0`, `mode` (forward/backward),
`eval` (init/frame), `dither` (default **true** — leave it on, it is what stops banding on a dark
gradient), `aspect`.

**Larger `angle` = stronger vignette.** Measured corner luma on a dark UI frame (centre stays ~34.4
throughout, i.e. the filter is correctly centre-neutral):

| `angle` | corner luma | vs none |
|---|---|---|
| *(no vignette)* | 10.20 | — |
| `PI/10` | 8.10 | −21 % |
| `PI/8` | 7.06 | −31 % |
| `PI/6` | 5.08 | −50 % |
| `PI/5` (default) | 3.45 | **−66 %** |
| `PI/4` | 1.07 | −90 % |

```bash
# premium: you should not be able to point at it
ffmpeg -y -i normalized.mp4 -vf "vignette=angle=PI/8:dither=1,fps=30" \
  -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an vig.mp4
```

The default `PI/5` crushes corners by two-thirds — on an already-dark app UI that is instantly
"cheap YouTube filter". `PI/10`–`PI/8` is the range that reads as lighting.

**Or generate the vignette as a PNG and control the falloff exactly** — VERIFIED (used in the master
render). This gets you a non-radially-symmetric or gamma-shaped falloff that `vignette` can't do,
plus explicit dithering:

```python
import numpy as np
from PIL import Image
W, H = 1920, 1080
yy, xx = np.mgrid[0:H, 0:W]
r  = np.sqrt(((xx-W/2)/(W/2))**2 + ((yy-H/2)/(H/2))**2) / np.sqrt(2)
al = np.clip((r-0.35)/0.65, 0, 1)**1.8 * 0.55           # start at 35% radius, gamma 1.8, max 55%
al = al + (np.random.default_rng(7).random((H, W)) - 0.5)/255.0   # ±0.5 LSB dither kills banding
v = np.zeros((H, W, 4), np.uint8)
v[..., 3] = np.clip(al*255, 0, 255).astype(np.uint8)     # black with varying alpha
Image.fromarray(v, "RGBA").save("vignette.png")
```

### 6.3 Grain — VERIFIED, and it is a **bitrate bomb**

`noise` addresses planes as `c0`(Y) `c1`(Cb) `c2`(Cr) `c3`(A), with `alls`/`allf` for all.
Flags: `a` averaged, `p` (semi)regular pattern, `t` **temporal**, `u` uniform.

```bash
# premium: luma-only, temporal, low amplitude
ffmpeg -y -i normalized.mp4 -vf "noise=c0s=3:c0f=t+u,fps=30" \
  -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an grain.mp4
```

- **`t` (temporal) is non-negotiable.** Without it the noise pattern is *frozen* to the frame — it
  looks like a dirty lens, not grain. Compare `noise=alls=7:allf=u` (static) against
  `noise=c0s=7:c0f=t+u`. VERIFIED both render.
- **Luma-only (`c0`)**, never `alls`. Chroma noise on a dark UI reads as compression failure.
- **Measured bitrate cost** — 6 s, 1920x1080, x264 `-crf 18 -preset veryfast`, base file 233 KB:

| grain | file size | vs base |
|---|---|---|
| none | 233 KB | — |
| `c0s=2` | 295 KB | +27 % |
| `c0s=4` | 407 KB | +75 % |
| `c0s=7` | **8,137 KB** | **+3390 %** |
| `c0s=4` + `-tune grain` | **4,561 KB** | +1856 % |

There is a **cliff between strength 4 and 7**. Stay at `c0s=2..4`. And do **not** reach for
`-tune grain` — it tells x264 to *preserve* the noise, which is exactly the wrong trade for a promo
that has to be a reasonable download. If you need heavier grain, raise CRF to pay for it
(`c0s=4 -crf 22` measured at 175 KB — smaller than the clean `-crf 18` base).

- **Apply grain last**, after all scaling/overlays, immediately before `format=yuv420p`. Grain that
  goes through a `scale` is no longer grain, it is mush. — UNVERIFIED (craft note)

### 6.4 Scanlines — VERIFIED

Do this as a numpy PNG, not with `geq` (which is slow and awkward to tune):

```python
import numpy as np
from PIL import Image
W, H = 1920, 1080
a = np.zeros((H, W, 4), np.uint8)
a[1::3, :, 3] = 26          # 1px black line every 3px, alpha 26/255 ≈ 10%
Image.fromarray(a, "RGBA").save("scanlines.png")
```

```bash
ffmpeg -y -i normalized.mp4 -i scanlines.png -i vignette.png -filter_complex "\
[0:v][1:v]overlay=0:0:format=auto[a];\
[a][2:v]overlay=0:0:format=auto,format=yuv420p[v]" \
 -map "[v]" -fps_mode cfr -r 30 -c:v libx264 -crf 18 -an treated.mp4
```

Craft rules — UNVERIFIED:
- **Pitch ≥ 3 px at 1080p.** A 2px pitch (1 on, 1 off) aliases horribly against UI text and against
  the encoder's 8x8 transform. 3px is the minimum that survives.
- **Alpha ≤ 12 %.** At 25 % it is a CRT costume; at 10 % it is a texture you feel and don't see.
- Scanlines and grain together are usually one effect too many. Pick one.
- Because the PNG is 1-pixel-detail, it **must** be composited at native 1920x1080 with no scaling
  anywhere after it — and it will cost bitrate for the same reason grain does.

### 6.5 Grade — UNVERIFIED (craft note), filters VERIFIED to exist

For a dark app UI, a light hand:

```bash
-vf "eq=contrast=1.06:saturation=1.04:gamma=0.98,vibrance=intensity=0.15,\
curves=preset=none:m='0/0 0.25/0.22 0.75/0.79 1/1'"
```

`eq`, `vibrance`, `curves`, `colorbalance`, `colortemperature`, `colorlevels`, `lut3d` all exist on
this build. Prefer `vibrance` over `eq=saturation` — it protects already-saturated accent colors
from clipping. A gentle S-curve (`curves`) does more for "premium" than any amount of saturation.

---

## 7. Keeping 1920x1080 text crisp

**Rule: render every text/graphic overlay in Pillow at exactly 1920x1080 and never let ffmpeg scale
it. Not up, not down, not by 1 pixel.**

Measured (same text, same font, composited onto the same plate, both encoded identically). "Soft-edge
pixels" = share of pixels in the text region at intermediate luma; "p99.5 gradient" = edge contrast:

| Overlay authored at | soft-edge pixels | p99.5 gradient |
|---|---|---|
| **native 1920x1080** | **23.62 %** | **189.0** |
| 1280x720 → `scale=1920:1080:flags=lanczos` | 25.03 % | 151.0 |
| 1280x720 → `scale=1920:1080:flags=bicubic` | 25.33 % | 150.0 |

Upscaling costs **~20 % of edge contrast** and adds soft pixels — and lanczos's ringing means naive
"sharpness" metrics (mean gradient energy) actually go *up* while the text looks worse. Don't trust
mean-gradient; trust edge contrast.

Checklist — VERIFIED where marked:

1. Pillow canvas exactly `(1920, 1080)`, RGBA. No `im.resize()` anywhere. — VERIFIED (measured above)
2. `setsar=1` on the video before compositing; a non-1 SAR makes the player rescale your pixel-exact
   overlay at playback time. — UNVERIFIED (craft note)
3. Never put a `scale` filter *after* the overlay. If you need a punch-in on a shot that carries
   text, do the punch on the **plate**, composite the text on top afterwards. — UNVERIFIED (craft)
4. Output dimensions even (`-2` in `scale`, not `-1`) — `yuv420p` requires it. — VERIFIED (used
   throughout; `scale=8000:-2` in §2.2)
5. `-pix_fmt yuv420p` for compatibility. Its 4:2:0 chroma softens *colored* text edges; the design
   answer is **white/near-white text, or high-luma-contrast color**, not a 4:4:4 encode that half
   the world can't play. — UNVERIFIED (craft note)
6. Encode with `-preset slow -crf 16..18`. Text is high-frequency; a fast preset spends its bits
   elsewhere and you get mosquito noise around glyphs. — UNVERIFIED (craft note)
7. If the source screen recording is already scaled (e.g. a Retina capture downscaled), do that
   downscale **once**, with `flags=lanczos`, and never touch it again. — UNVERIFIED (craft note)

---

## 8. Audio/video sync and muxing a WAV

`-shortest` is more dangerous than its reputation. All four cases below were **measured** on a
6.033 s video + 6.000 s WAV.

| # | Command shape | Result |
|---|---|---|
| A1 | `-map 0:v -map 1:a -c:v copy -shortest` | ❌ **video truncated to 5.900 s** |
| A2 | `[1:a]apad[a]` + `-shortest -fflags +shortest` | ❌ **hangs forever** (killed at 40 s) |
| A3 | `[1:a]apad=whole_dur=<video_dur>[a]`, **no** `-shortest` | ✅ video 6.033 s / audio 6.033 s |
| A4 | `-stream_loop -1 -i beat.wav` + `-shortest -fflags +shortest` | ✅ video 6.033 s / audio 5.973 s |

**A1 is the trap.** When the audio is even slightly shorter than the video, `-shortest` does not
just stop the audio — it **chops the tail off your video**, and it chops more than the difference
(133 ms of audio shortfall cost 133 ms of video *plus* another ~100 ms of muxer buffering). Your
last beat and your logo card disappear and the file still looks valid.

**A2 is worse.** Unbounded `apad` + `-shortest` deadlocks: `apad` will generate silence forever and
`-shortest` never fires. `-fflags +shortest -max_interleave_delta 100M` does **not** save it. Never
combine bare `apad` with `-shortest`.

### 8.1 The safe recipe — VERIFIED

Pad the audio to the **exact** video duration and drop `-shortest` entirely:

```bash
VDUR=$(ffprobe -v error -select_streams v:0 -show_entries stream=duration -of csv=p=0 video.mp4)

ffmpeg -y -i video.mp4 -i beat.wav \
  -filter_complex "[1:a]aresample=async=1:first_pts=0,apad=whole_dur=${VDUR}[a]" \
  -map 0:v:0 -map "[a]" \
  -c:v copy -c:a aac -b:a 192k -ar 48000 \
  -movflags +faststart out.mp4
# measured: video 6.033333, audio 6.033000
```

### 8.2 Looping a music bed — VERIFIED

```bash
ffmpeg -y -i video.mp4 -stream_loop -1 -i beat.wav \
  -map 0:v:0 -map 1:a:0 \
  -c:v copy -c:a aac -b:a 192k -ar 48000 \
  -shortest -fflags +shortest -max_interleave_delta 100M \
  -movflags +faststart out.mp4
# measured: video 6.033333 (intact), audio 5.973
```

Here `-shortest` is safe **because the audio is infinite** — video is unambiguously the shortest
stream. `-fflags +shortest` makes the muxer honour it promptly instead of over-buffering.

### 8.3 Sync notes

- `aresample=async=1:first_pts=0` normalizes the audio start to 0 and lets ffmpeg stretch/squeeze to
  correct drift. Include it whenever the WAV came from another tool. — VERIFIED (used in A2/A3)
- Author the WAV at **48000 Hz** to match AAC/MP4 convention and avoid a resample at mux time.
- If you build the whole promo in one filtergraph, add `-t <exact_duration>` on the output. It is
  the only thing that guarantees an exact frame count regardless of what the filters did.
  — VERIFIED (used in the master render, §9: `-t 4` → exactly 120 frames).
- `-movflags +faststart` for web delivery (moves `moov` to the front). — VERIFIED (used above)

---

## 9. "Hyperframe" editing — what it actually means, and how to author it

### 9.1 The idea

At 30 fps one frame is **33.333 ms**. Hyperframe editing means treating the frame — not the second,
not "about there" — as the unit of the edit:

- **Cuts land on the frame the transient lands on.** Not the frame after. A cut 1 frame late reads
  as sloppy; 2 frames late reads as broken.
- **Hits are 1–4 frames long.** A white flash is 2 frames. An RGB split is 3. A shake is 6 with a
  decay envelope. Anything you can *watch happen* is too long — the effect should register as an
  impression, not a shot.
- **Density is the energy.** A high-energy promo has an event every 8–15 frames (a cut, a punch, a
  hit, a text change). Not necessarily a *cut* — but something changes.
- **Asymmetry sells it.** Alternating "hit on every 4th beat" is a metronome. Hit on 1, 1e, 2, 4,
  skip 5, double-hit 6 — that is a performance.

None of this is achievable by eye in a timeline. It is achievable trivially if you author the edit
as a **frame-numbered list in Python** and emit the ffmpeg commands from it.

— UNVERIFIED (craft note); the mechanics below are VERIFIED.

### 9.2 The beat grid

```python
FPS = 30
BPM = 124
frames_per_beat = FPS * 60 / BPM          # 14.516  -> beats do NOT land on integer frames
def beat_frame(b):   return round(b * FPS * 60 / BPM)
def bar_frame(bar):  return beat_frame(bar * 4)
```

At 124 BPM a beat is 14.516 frames. **Round once, at the top, and store integers.** If you compute
cut points from seconds inside each ffmpeg command you accumulate drift and by bar 16 you are a
frame and a half late — audible as flam against the music.

Snap every event to an integer frame, build the timeline as a list, then generate:

```python
EVENTS = [
    dict(kind="cut",    at=beat_frame(0)),
    dict(kind="punch",  at=beat_frame(0),  n=45, amount=0.18),
    dict(kind="rgb",    at=beat_frame(4),  n=3,  amt=18),
    dict(kind="flash",  at=beat_frame(8),  n=2),
    dict(kind="shake",  at=beat_frame(8),  n=6,  amp=14),
    dict(kind="cut",    at=beat_frame(12)),
]
```

…and emit `enable='between(n,A,B)'` clauses. Because `enable` takes an arbitrary expression, a whole
track of hits collapses into one filter instance:

```python
wins = [(e["at"], e["at"]+e["n"]-1) for e in EVENTS if e["kind"] == "rgb"]
en   = "+".join(f"between(n,{a},{b})" for a, b in wins)   # '+' works as OR for 0/1 terms
vf   = f"rgbashift=rh=-18:bh=18:enable='{en}'"
```

### 9.3 The three frame-exact authoring primitives — all VERIFIED

| You want | Use | Note |
|---|---|---|
| an effect ON for frames A..B | `enable='between(n,A,B)'` | works on any filter whose `-h` output ends with *"This filter has support for timeline through the 'enable' option"*. **Not `crop`** on this build. |
| a parameter to *change value* at frame F | `sendcmd=c='<F/30> filt@lbl opt val'` | works on any option flagged `T` in `-h filter=`. Intervals separated by `;`, commands within an interval by `,` with **no repeated timestamp**. |
| an effect that *animates continuously* | a per-frame expression using `n` | only on options typed `<string>`: `crop` x/y, `overlay` x/y, `eq` (needs `eval=frame`), `hue`, `zoompan` z/x/y, `geq`. |

Cheat sheet of what animates how on this build — VERIFIED via `-h filter=`:

```
expressions (n, t):   crop.x/y   overlay.x/y   eq.*(eval=frame)   hue.h/s/H/b   zoompan.z/x/y   geq.*
enable only:          rgbashift  chromashift   vignette  noise  fade  drawbox  overlay  vibrance
                      dblur  gblur  boxblur  colorchannelmixer
sendcmd only:         dblur.radius/angle  gblur.sigma  rgbashift.*  chromashift.*  vibrance.*
no timeline at all:   crop        (verified error: "Timeline ('enable' option) not supported")
```

### 9.4 Inserting vs overlaying frames

Two different hyperframe moves, don't confuse them:

- **Insert** (`concat` a 2-frame white `color` source, §3.3a) — the timeline gets **longer** by 2
  frames. Everything after shifts. Recompute your beat grid or your music desyncs.
  Measured: 181 → 183 frames.
- **Overlay/modulate** (`eq=brightness` flash, `enable`-gated `rgbashift`) — the timeline length is
  **unchanged**. This is almost always what you want once the edit is locked to music.

A good default: use inserts during the rough cut (they're punchier), then convert them to
modulations once the beat grid is fixed. — UNVERIFIED (craft note)

### 9.5 Verifying a hyperframe edit

Never eyeball it. Extract the frames you claim to have modified and measure them:

```bash
ffmpeg -y -v error -i master.mp4 -vf "select=eq(n\,46)" -frames:v 1 -update 1 f46.png
```

```python
import numpy as np; from PIL import Image
a = np.asarray(Image.open("f46.png").convert("RGB")).astype(np.float32)
print("mean luma      :", a.mean())
print("R-B split      :", np.abs(a[...,0]-a[...,2]).mean())
```

Measured on the master render below, which is how the effects in it were confirmed to land on the
requested frames:

```
frame 44: mean= 32.28   R-B split= 4.21      <- clean
frame 46: mean= 32.49   R-B split= 9.69      <- rgbashift hit  ✅
frame 60: mean=217.71                        <- whiteout peak  ✅
frame 62: mean=164.90                        <- whiteout decay ✅
```

---

## 10. Master pipeline — everything at once — VERIFIED

Renders in **4.45 s wall** for 4 s of 1920x1080/30 output (678 % CPU) and produces exactly
**120 video frames, 4.000 s, 3.1 MB**.

```bash
SRC=/Users/omega/room/mainprojects/tower/promo/media/source.mov

ffmpeg -y -hide_banner -ss 10 -t 4 -i "$SRC" \
 -framerate 30 -i "ov/ov_%04d.png" \
 -i scanlines.png \
 -i vignette.png \
 -i beat.wav \
 -filter_complex "\
sws_flags=lanczos;\
[0:v]fps=30,crop=2648:1490,scale=8000:-2,\
zoompan=z='if(lte(on,45),1+0.18*(1-pow(1-on/45,3)),1.18)':d=1\
       :x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30,\
setsar=1,format=yuv420p[base];\
[base]rgbashift=rh=-18:bh=18:enable='between(n,45,47)',\
eq=brightness='if(between(n,60,64),0.9*(1-(n-60)/5),0)':eval=frame,\
crop=w=1880:h=1058\
 :x='20+if(between(n,45,50),12*sin(n*3.1)*(1-(n-45)/6),0)'\
 :y='11+if(between(n,45,50),9*cos(n*4.7)*(1-(n-45)/6),0)',\
scale=1920:1080,setsar=1[fx];\
[1:v]format=rgba,setpts=N/30/TB[ovl];\
[fx][ovl]overlay=0:0:format=auto:eof_action=pass[c1];\
[c1][2:v]overlay=0:0:format=auto[c2];\
[c2][3:v]overlay=0:0:format=auto[c3];\
[c3]noise=c0s=3:c0f=t+u,format=yuv420p[v];\
[4:a]aresample=async=1:first_pts=0,apad=whole_dur=4.0,atrim=0:4.0[a]" \
 -map "[v]" -map "[a]" -fps_mode cfr -r 30 -t 4 \
 -c:v libx264 -preset slow -crf 17 -profile:v high -level 4.1 -pix_fmt yuv420p \
 -c:a aac -b:a 192k -movflags +faststart master.mp4
```

Order of operations, and why:

1. **`fps=30` first** — everything downstream counts frames.
2. **`crop` to output aspect**, then **`scale=8000:-2`**, then **`zoompan`** — §2.
3. **Effects on the plate** (`rgbashift` → `eq` flash → shake `crop`+`scale`) — before any text.
4. **Overlays last, at native 1920x1080**, never scaled — §7.
5. **`noise` after everything**, immediately before `format=yuv420p` — §6.3.
6. **`-t 4` on the output** guarantees the frame count regardless of filter arithmetic — §8.3.

---

## Appendix A — verification method

- Filter existence and exact option names: `ffmpeg -h filter=NAME` on this build for every filter
  named in this document.
- `xfade` transitions: enumerated from `-h filter=xfade` (range −1..57) **and** all 58 rendered in a
  loop against `testsrc2`/`smptebars` — 0 failures.
- Frame counts: `ffprobe -v error -count_frames -select_streams v:0 -show_entries
  stream=nb_read_frames`.
- Zoom jitter: decoded each variant to raw `gray`, computed the per-frame mean absolute difference
  series `d[n]`, then `roughness = mean(|d[n] − (d[n−1]+d[n+1])/2|) / mean(d)`. A perfectly smooth
  zoom gives a smooth `d[n]`; stick-and-jump gives an oscillating one.
- Overlay alpha correctness: composited the same PNG over the same extracted frame in numpy
  (straight-alpha `src*a + dst*(1−a)`) and measured RMSE of each ffmpeg variant against it.
- Text crispness: soft-edge-pixel fraction and 99.5th-percentile horizontal gradient over the text
  region.
- Grain/vignette: file sizes and region-mean luma from extracted PNG frames.

Scratch workspace with every rendered artifact (t1..t6, x1..x4, z0..z4, g1..g4, s1..s2, o1..o6,
l1..l2, v1..v2, n1..n2, w1, a1..a4, master.mp4):
`/private/tmp/claude-501/-Users-omega-room-mainprojects-tower/908b75bd-c3f6-4842-895a-38edec9120de/scratchpad/fftest/`

## Appendix B — sources consulted for craft

- [Smooth Zoom with FFmpeg: Fixing Shaky/Jittery Zoom Effects](https://usercomp.com/news/1214682/smoothing-out-ffmpeg-zoom)
- [How to Create Videos with a Ken Burns Effect using FFmpeg — Bannerbear](https://www.bannerbear.com/blog/how-to-do-a-ken-burns-style-effect-with-ffmpeg/)
- [ffmpeg: smooth zoompan with no jiggle](https://www.datarecoveryunion.com/video-ffmpeg-smooth-zoompan-with-no-jiggle/)
- [How to Preserve Transparency in FFmpeg: Codecs, Pixel Formats, and Best Practices](https://hoop.dev/blog/how-to-preserve-transparency-in-ffmpeg-codecs-pixel-formats-and-best-practices)
- [Handling Transparency in FFmpeg](https://hoop.dev/blog/handling-transparency-in-ffmpeg)
- [Change Video Speed with FFmpeg — Audio Sync Guide](https://ffmpeg-cookbook.com/en/articles/change-video-speed/)
- [How to Speed Up or Slow Down Video Playback Using FFmpeg — OTTVerse](https://ottverse.com/how-to-speed-up-slow-down-video-playback-using-ffmpeg/)
- [FFmpeg filter documentation](https://ffmpeg.org/ffmpeg-filters.html) (zoompan / setpts / xfade
  expression-variable tables; note the online docs are trunk and list a `setpts` `strip_fps` option
  that does **not** exist on 7.0.1)
