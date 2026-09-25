"""draw.py — low-level drawing primitives shared by the driver.

The four scene modules each carry their own faithful copies of the primitives
they draw *with* (tracked text, hairlines, rounded rects, the supersampled
radar tile) — they were authored in parallel and a scene owning its own mark is
what keeps the f329/f420 match cut bit-identical. What lives here is what the
DRIVER owns and no scene may touch: the global grade.

Deliberately NOT exported from this module: a symbol named `font`. Every scene
probes `draw.font` and would swap its own loader for it, and the variable-axis
handling is not identical across the three faces. See brand.py's docstring.
"""

from __future__ import annotations

import math

import numpy as np
from PIL import Image

from brand import H, W

# ══════════════════════════════════════════════════════════════════════════
#  THE GRADE — FILM.md §2.9
#
#  Vignette 0.32 (the old, messy film ran 0.55). Scanlines OFF. No chromatic
#  anything, no glitch, no flare, no leak, no drop shadow, no hue-shifting
#  gradient. Grain exists for exactly one reason — to break up 8-bit banding
#  in a very flat, very dark field — and must be invisible when you look for
#  it, so it is clipped at 14/255.
# ══════════════════════════════════════════════════════════════════════════

_GRADE: dict = {}


def grade_static(vig=0.32, pitch=0, scan_a=0.0):
    """The static grade plate: an RGBA black layer whose alpha is the vignette.

    `pitch` / `scan_a` drive scanlines and are wired through only so the call
    site can state, in the source, that they are OFF. Passing anything non-zero
    is a spec violation (FILM §7 row 10).
    """
    key = ('static', vig, pitch, scan_a)
    hit = _GRADE.get(key)
    if hit is not None:
        return hit
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    nx = (xx - (W - 1) / 2.0) / ((W - 1) / 2.0)
    ny = (yy - (H - 1) / 2.0) / ((H - 1) / 2.0)
    r = np.sqrt(nx * nx + ny * ny) / math.sqrt(2.0)
    v = np.clip((r - 0.52) / 0.48, 0, 1) ** 1.7 * (vig * 0.62)
    s = np.zeros((H, 1), np.float32)
    if pitch and scan_a:
        s[::int(pitch), 0] = scan_a
    a = 1.0 - (1.0 - v) * (1.0 - s)
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    im.putalpha(Image.fromarray((a * 255).astype(np.uint8), 'L'))
    _GRADE[key] = im
    return im


_GRAIN: dict = {}
GRAIN_PLATES = 37          # a prime: no beat the eye can lock onto.  12 plates
                           # gave a 0.4 s loop, which on a near-still film reads
                           # as a dirty overlay rather than as grain.
GRAIN_SIGMA = 1.8          # was 5.0
GRAIN_CLIP = 4             # was 14
GRAIN_HOLD = 3             # frames each plate is held.  Grain exists to break
                           # up 8-bit banding, which is a SPATIAL problem; a new
                           # field every frame buys nothing and costs a visible
                           # crawl on a film that is still for a third of its
                           # length — plus about a third of the encode's bits.
                           # 37 x 3 = 111 frames before the cycle repeats.


def grain_layer(i, amount=1):
    """`GRAIN_PLATES` pre-rolled SIGNED luma-grain plates, cycled by frame.

    Deterministic by construction: one fixed seed, pre-rolled once, indexed by
    `i % GRAIN_PLATES`. Never reads the clock and never advances an RNG per
    frame, so frame N is byte-identical at any -j.

    SIGNED is the whole point.  The previous version took `abs()` of a normal
    and composited it as a white overlay, which made the grain half-normal and
    strictly additive: it could only ever *lift* the field.  Measured, the
    darkest pixel in the film was 10 and the mean of an empty frame sat 1.6
    luma above `#0C0C0E` — the blacks were grey, and the mottle was plainly
    visible at 1:1 on a field that is 98 % flat.  Zero-mean noise at sigma 1.8
    clipped to +/-4 kills banding and disappears, and it costs the encoder a
    quarter of the bits.

    Returns an int16 (H, W) array to be ADDED to the frame, not an RGBA layer:
    an alpha overlay cannot subtract.
    """
    plates = _GRAIN.get(amount)
    if plates is None:
        plates = []
        rs = np.random.RandomState(1917)          # fixed seed: deterministic
        for _ in range(GRAIN_PLATES):
            # full resolution: the half-res NEAREST upscale made the grain
            # 2x2 blocky, which is chunky digital noise, not film grain
            n = rs.normal(0.0, GRAIN_SIGMA * amount, (H, W))
            plates.append(np.clip(np.round(n), -GRAIN_CLIP,
                                  GRAIN_CLIP).astype(np.int16))
        _GRAIN[amount] = plates
    return plates[(i // GRAIN_HOLD) % GRAIN_PLATES]


def apply_grade(img: Image.Image, f: int, vig=0.32, grain=1) -> Image.Image:
    """Composite the grade onto an opaque RGB frame. Returns RGB.

    The vignette composites in RGBA; the grain is a signed add on the array
    afterwards.  The frame comes back to RGB because the encoder wants opaque
    frames and because an accidental alpha channel surviving to ffmpeg is a
    silent yuv420p conversion bug.
    """
    base = img.convert('RGBA')
    base.alpha_composite(grade_static(vig, 0, 0.0))
    out = base.convert('RGB')
    if grain:
        a = np.asarray(out, dtype=np.int16)
        a = a + grain_layer(f, grain)[:, :, None]
        out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), 'RGB')
    return out
