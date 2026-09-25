"""scene_end.py — Act D of the Tower film.

Frames 1020 … 1199 inclusive (180 frames, 34.000 s – 40.000 s).

    D1  end.set    1020 … 1079   the five-state run.  One mark, no words.
    D2  end.card   1080 … 1199   Layout E.  Mark, wordmark, tagline, address.

Everything here is a pure function of the absolute frame index.  No clock, no
unseeded randomness, no neighbour-frame state.  Frame N is byte-identical
every run and at every `-j`.

Public surface is exactly:

    RANGE = (1020, 1199)
    def draw(ctx) -> None

`ctx` is the Ctx dataclass from brand.py: ctx.img (RGB 1920x1080, already
filled with INK), ctx.d, ctx.f (absolute frame), ctx.t, ctx.dur, ctx.k,
ctx.sf.  Only ctx.img and ctx.f are load-bearing here — every frame number in
FILM.md is absolute, so this module drives off ctx.f and never off ctx.t.

brand.py / draw.py / ui.py did not exist when this module was written (they
are being authored in parallel).  Section 0 therefore *prefers* the shared
helpers when they are importable and otherwise falls back to a local
implementation that is faithful, constant for constant, to notes/design.md §2
and FILM.md §2–§4.  `scene_wire.py` uses the identical adapter and the
identical rasterisation helpers, so the mark lands on the same pixels in both.

Why the radar is drawn here rather than delegated: D1 is a *morph* run, not
a pose run.  Ten 6-frame beats interpolate the ring dash from solid to
`(5,7)`, the core from a filled disc to a hollow annulus, the verify needle
out of the hub, the holdNet pings into the holdGeo fence.  None of that is
expressible as "draw state X" — FILM.md §3 is explicit that a state change is
interpolated geometry, never a cross-fade of two finished pictures — so
`_radar_tile` takes a resolved *channel spec* and `_blend` produces it.  That
spec is a superset of the one scene_wire.py uses (it carries `sweep`, `geo`
and `geo_col`, which Act B has no state that needs), and a helper written for
the smaller shape would accept this one and silently drop the sweep and the
whole holdGeo group.  So the mark is NOT routed through `ui.radar_tile`: the
constants, the draw order and the rasterisation are copied from design.md §2
and from scene_wire.py §2 line for line instead, which is what actually makes
the two acts land on the same pixels.  Fonts and easing curves are shared
where they are importable, because those are value-identical or nothing.
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFont

# =====================================================================
#  0.  ADAPTER — prefer the shared toolkit, fall back to a local one
# =====================================================================

#  Only `brand` and `draw` are consulted.  `ui` is deliberately not: the one
#  thing this act would take from it is the radar, and that is resolved
#  locally for the reason given in the module docstring.
_B = _D = None
for _mod in ('brand', 'draw'):
    try:                                        # package-relative first
        _m = __import__('promo.film.' + _mod, fromlist=[_mod])
    except Exception:
        try:
            _m = __import__(_mod)
        except Exception:
            _m = None
    if _mod == 'brand':
        _B = _m
    else:
        _D = _m


def _shared(mod, *names):
    """First attribute of `mod` that exists, else None."""
    if mod is None:
        return None
    for n in names:
        v = getattr(mod, n, None)
        if v is not None:
            return v
    return None


# --------------------------------------------------------------- canvas
W, H, FPS = 1920, 1080, 30

RANGE = (1020, 1199)

# --------------------------------------------------------------- colour
INK = (0x0C, 0x0C, 0x0E)         # the field; the driver has already laid it
TEXT = (0xE7, 0xE6, 0xE2)
TEXT2 = (0x9A, 0x9A, 0x95)
MUTED = (0x8B, 0x8B, 0x86)
AMBER = (0xE6, 0xA9, 0x3C)
RED = (0xE5, 0x48, 0x4D)
# No HAIRLINE and no KICKER: Act D is the one act that draws neither a rule
# nor an eyebrow.  D1 has no copy at all and D2 has four objects, none of
# them structural.
# GREEN #30D158 is deliberately absent: the passing radar is neutral, not
# green, and there is no `done` agent in this film.


def _mix(a, b, k):
    k = 0.0 if k < 0.0 else (1.0 if k > 1.0 else k)
    return (int(round(a[0] + (b[0] - a[0]) * k)),
            int(round(a[1] + (b[1] - a[1]) * k)),
            int(round(a[2] + (b[2] - a[2]) * k)))


def _rgba(c, a=1.0):
    v = int(round(a * 255))
    return (c[0], c[1], c[2], 0 if v < 0 else (255 if v > 255 else v))


# ----------------------------------------------------------------- font
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_F_SERIF = '/System/Library/Fonts/NewYork.ttf'
_F_UI = '/System/Library/Fonts/SFNS.ttf'
_F_MONO = os.path.join(_REPO, 'src', 'Fonts', 'JetBrainsMono-Medium.ttf')
_F_MONO_B = os.path.join(_REPO, 'src', 'Fonts', 'JetBrainsMono-Bold.ttf')

_FONTS = {}
_shared_font = _shared(_B, 'font') or _shared(_D, 'font')


def _font(kind, size, weight=None):
    """promo/overlays.py:font() verbatim — the axis order differs per face."""
    if _shared_font is not None:
        try:
            return _shared_font(kind, size, weight)
        except Exception:
            pass
    size = int(round(size))
    key = (kind, size, weight)
    f = _FONTS.get(key)
    if f is not None:
        return f
    if kind == 'serif':
        f = ImageFont.truetype(_F_SERIF, size)
        try:                              # axes: [Optical Size, Weight, GRAD]
            f.set_variation_by_axes([max(12, min(256, size * 2)),
                                     weight or 520, 0])
        except Exception:
            pass
    elif kind == 'ui':
        f = ImageFont.truetype(_F_UI, size)
        try:                      # axes: [Width, Optical Size, GRAD, Weight]
            f.set_variation_by_axes([100, max(17, min(96, size)), 400,
                                     weight or 400])
        except Exception:
            pass
    elif kind == 'mono':
        f = ImageFont.truetype(_F_MONO, size)
    elif kind == 'mono_bold':
        f = ImageFont.truetype(_F_MONO_B, size)
    else:
        raise ValueError(kind)
    _FONTS[key] = f
    return f


# --------------------------------------------------------------- easing
def _clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def _lerp(a, b, k):
    return a + (b - a) * k


def _bezier(x1, y1, x2, y2, eps=1e-6):
    """cubic-bezier(x1,y1,x2,y2), Newton, 8 iterations, seeded from t = x."""
    def bx(u):
        return 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u * u * x2 + u ** 3

    def by(u):
        return 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u * u * y2 + u ** 3

    def dbx(u):
        return (3 * (1 - u) ** 2 * x1 + 6 * (1 - u) * u * (x2 - x1)
                + 3 * u * u * (1 - x2))

    def f(x):
        x = _clamp01(x)
        u = x
        for _ in range(8):
            e = bx(u) - x
            if abs(e) < eps:
                break
            d = dbx(u)
            if abs(d) < 1e-9:
                break
            u -= e / d
        return by(u)
    return f


EASE_ENTER = _shared(_B, 'EASE_ENTER') or _bezier(0.16, 1.00, 0.30, 1.00)
EASE_MOVE = _shared(_B, 'EASE_MOVE') or _bezier(0.65, 0.00, 0.35, 1.00)
EASE_SOBER = _shared(_B, 'EASE_SOBER') or _bezier(0.33, 1.00, 0.68, 1.00)
EASE_SNAP = _shared(_B, 'EASE_SNAP') or _bezier(0.22, 1.00, 0.36, 1.00)
EASE_EXIT = _shared(_B, 'EASE_EXIT') or _bezier(0.32, 0.00, 0.67, 0.00)
#  A SYMMETRIC S-CURVE.  EASE_SNAP has y1 = y2 = 1.0, so it reduces to
#  1 - (1-u)^3: sampled at the old 6-frame beat it returned
#  0, 0.68, 0.92, 0.98, 0.999, 1.0 — 68 % of every state change happened on
#  the FIRST frame and the last three frames of every morph were visually
#  dead.  Measured, the verify -> holdNet "morph" moved the ring's hue 83 % of
#  its travel in one frame, with a whole-frame delta larger than every
#  scripted cut in the film bar three.  That is a cut in the middle of a shot,
#  and it is why the five-state run read as a slideshow.  EASE_IN_OUT at a
#  12-frame beat gives 0, .04, .12, .25, .40, .55, .70, .82, .91, .96, .99, 1
#  — a real accelerate-and-decelerate with no overshoot, therefore still legal
#  on a hold entry.
EASE_IN_OUT = _shared(_B, 'EASE_IN_OUT') or _bezier(0.42, 0.00, 0.58, 1.00)
# Nothing in this act is linear.  Nothing in this act overshoots: EASE_SNAP's
# control points are (0.22,1.00) (0.36,1.00) — monotone, peak exactly 1.0 —
# so even the amber and red beats obey "failure never bounces".

# Every timed value in this module is `ease((f - at + 1) / dur)`: frame `at`
# is the first frame that shows movement and `at + dur - 1` is the frame that
# lands.  scene_wire.py uses the same convention, so the two acts agree about
# what "a 6-frame beat" means.


# =====================================================================
#  1.  TEXT — sub-pixel, per-character, tracked
# =====================================================================
#  Pillow snaps ImageDraw.text() to integer pixels, which judders a 28 px
#  rise into 28 visible steps and instantly reads cheap (Amendment B).  Every
#  glyph is rasterised once into a cached alpha mask and stamped at a float
#  position; the fractional part is a bilinear affine shift of the mask
#  alone, so the colour never fringes.  Identical to scene_wire.py §1.

_GLYPH = {}


def _glyph_mask(fkey, ch):
    key = (fkey, ch)
    hit = _GLYPH.get(key)
    if hit is not None:
        return hit
    f = _font(*fkey)
    size = fkey[1]
    pad = max(6, int(size * 0.40))
    adv = f.getlength(ch)
    w = int(math.ceil(adv)) + 2 * pad
    asc = int(size * 1.45)
    desc = int(size * 0.65)
    h = asc + desc + 2 * pad
    im = Image.new('L', (max(2, w), max(2, h)), 0)
    ImageDraw.Draw(im).text((pad, pad + asc), ch, font=f, fill=255,
                            anchor='ls')
    hit = (im, -pad, -(pad + asc), adv)
    _GLYPH[key] = hit
    return hit


def _stamp(dst, mask, x, y, colour, alpha):
    """Composite a single-colour alpha mask at float (x, y)."""
    if alpha <= 0.004:
        return
    ix = int(math.floor(x))
    iy = int(math.floor(y))
    fx = x - ix
    fy = y - iy
    if fx > 1e-3 or fy > 1e-3:
        mask = mask.transform(mask.size, Image.AFFINE,
                              (1, 0, -fx, 0, 1, -fy), Image.BILINEAR)
    if alpha < 0.999:
        mask = mask.point(lambda v, k=alpha: int(v * k))
    tile = Image.new('RGBA', mask.size, (colour[0], colour[1], colour[2], 0))
    tile.putalpha(mask)
    dst.alpha_composite(tile, (ix, iy))


def _run_w(fkey, s, tracking, kern=None):
    if not s:
        return 0.0
    f = _font(*fkey)
    w = sum(f.getlength(c) for c in s) + tracking * (len(s) - 1)
    if kern:
        w += sum(kern.get(s[i:i + 2], 0.0) for i in range(len(s) - 1))
    return w


def _centre_x(cx, fkey, segs, tracking, kern=None):
    """Optical centring (craft §3.4): centre the *ink*, not the advances.

    At 200 px with +12 px tracking the side bearings of `T` and `R` are worth
    several pixels, and a wordmark that is off-centre under a centred mark is
    the first thing a viewer sees without being able to say why."""
    s = ''.join(t for t, _ in segs)
    if not s:
        return cx
    f = _font(*fkey)
    total = _run_w(fkey, s, tracking, kern)
    try:
        lb = float(f.getbbox(s[0])[0])
    except Exception:
        lb = 0.0
    try:
        rb = float(f.getlength(s[-1]) - f.getbbox(s[-1])[2])
    except Exception:
        rb = 0.0
    return cx - (total - lb - rb) / 2.0 - lb


def _text(dst, x, y, segs, fkey, tracking=0.0, alpha=1.0, rise=0.0,
          p=1.0, stagger=0.0, ease=None, span_cap=1.0, kern=None):
    """Draw one line as a run of (string, colour) segments.

    p == 1 and stagger == 0 -> a plain tracked line at full opacity.
    Otherwise every glyph gets its own eased progress: alpha and a `rise` px
    upward settle, staggered by `stagger` (in units of p).  This is the film's
    only kinetic reveal.  Nothing in this act is a hold, so both lines that
    use it are allowed to be revealed kinetically.  `kern` is an optional
    {pair: delta} table applied on top of `tracking` — see KERN_WORD."""
    n = sum(len(s) for s, _ in segs)
    if n == 0 or alpha <= 0.004:
        return
    if stagger > 0.0:
        span = stagger * (n - 1)
        if span > span_cap:
            stagger *= span_cap / span
            span = span_cap
        win = max(1e-6, 1.0 - span)
    else:
        span = 0.0
        win = 1.0
    ease = ease or EASE_ENTER
    f = _font(*fkey)
    flat = ''.join(t for t, _ in segs)
    cx = float(x)
    i = 0
    for s, col in segs:
        for ch in s:
            adv = f.getlength(ch) + tracking
            if kern:
                adv += kern.get(flat[i:i + 2], 0.0)
            if ch != ' ':
                if stagger > 0.0:
                    ci = ease(_clamp01((p - i * stagger) / win))
                else:
                    ci = 1.0
                a = alpha * ci
                if a > 0.004:
                    m, ox, oy, _ = _glyph_mask(fkey, ch)
                    _stamp(dst, m, cx + ox,
                           y + oy + (1.0 - ci) * rise, col, a)
            cx += adv
            i += 1


# =====================================================================
#  2.  THE RADAR MARK — notes/design.md §2, verbatim constants
# =====================================================================
#  0..100 unit box, hub (50,50), y down, 0 deg = 3 o'clock, clockwise.
#  Drawn at 4x (6x for the 200 px card mark) and LANCZOS-downsampled:
#  ImageDraw has no AA on arcs or diagonals.
#  Draw order is design.md §2.1 — ring, sweep, pulse/pings, blips, geo, core.

#  brand.py is the AUTHORITY for the mark's geometry; the literals below are
#  only the fallback for running this module standalone. Do not edit them here
#  — edit brand.py, or the four scenes will disagree about the icon.
MARK_C = _shared(_B, 'MARK_C') or (1350.0, 540.0)   # canonical circle, FILM §2.3
MARK_BOX = _shared(_B, 'MARK_BOX') or 520           # 5.2 px per Glyph unit
#  D1 is the only shot in the film with no copy column, so it does not inherit
#  Layout M's off-centre seat: a 302 px object at x 1290 with 1130 px of
#  nothing to its left and no second element looks like a caption failed to
#  render.  The five-state run is the beat Amendment A asks for, so it gets
#  the frame's optical centre and the largest mark in the film.
RUN_C = (960.0, 470.0)
RUN_BOX = 620                     # 6.2 px per unit — 446 px of ring
CARD_C = (960.0, 300.0)           # Layout E, FILM §2.4
CARD_BOX = 280                    # 2.8 px per unit.  At 200 the mark drew a
#  144 px ring against a 143 px cap height, so the identity the film spent 34
#  seconds establishing arrived on the end card the same size as a letter and
#  read as a shirt button with three thread holes.

PULSE_RATE = 30.0 / 91.0
PULSE_R0, PULSE_DR = 8.0, 20.0
SWEEP_MAX = 27.5

#  See brand.py and scene_wire.py: at hero scale a dash shorter than the
#  6-unit stroke is a square block, and 19 of them is a sunburst.
DASH_HOLDNET = (13.82, 6.91)
DASH_OFF = (15.36, 7.68)
DASH_FENCE = (7.854, 3.927)
_PING_ARCS = ((205.0, 130.0), (25.0, 130.0))
#  the off-country contact, pulled inside the ring — see scene_hold.py
GEO_XY = (66.5, 37.0)
GEO_LUNGE = 5.0

BLIPS = ((64, 41), (38, 58), (58, 66))
CIRC33 = 2.0 * math.pi * 33.0     # 207.345 unit lengths — "solid", as a dash

_TILE_CACHE = {}


def _ring(d, cx, cy, r, w, colour, alpha, dash=None, phase_deg=0.0):
    """Stroke centred on radius r.  Pillow strokes inward from the bbox, so
    the bbox is built for r + w/2 (design.md §1.2 rule 3)."""
    if alpha <= 0.004 or r <= 0 or w <= 0:
        return
    ro = r + w / 2.0
    box = (cx - ro, cy - ro, cx + ro, cy + ro)
    ink = _rgba(colour, alpha)
    wi = max(1, int(round(w)))
    if not dash or dash[1] <= 1e-4:
        d.ellipse(box, outline=ink, width=wi)
        return
    circ = 2.0 * math.pi * r
    on_d = 360.0 * dash[0] / circ
    off_d = 360.0 * dash[1] / circ
    if on_d + off_d <= 0.05:
        d.ellipse(box, outline=ink, width=wi)
        return
    if on_d >= 359.9:
        d.ellipse(box, outline=ink, width=wi)
        return
    a = phase_deg
    end = phase_deg + 360.0
    while a < end:
        d.arc(box, a, min(a + on_d, end), fill=ink, width=wi)
        a += on_d + off_d


def _dashed_seg(d, p0, p1, colour, w, dash, alpha, frac=1.0, cap=True):
    """A dashed segment drawn from p0 outward.  `frac` clips it along its own
    axis, which is how the holdGeo ray draws itself out of the hub."""
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    full = math.hypot(dx, dy)
    ln = full * _clamp01(frac)
    if full < 1 or ln < 0.5 or alpha <= 0.004:
        return
    ux, uy = dx / full, dy / full
    on, off = dash
    ink = _rgba(colour, alpha)
    wi = max(1, int(round(w)))
    s = 0.0
    while s < ln:
        a, b = s, min(ln, s + on)
        if b > a:
            ax, ay = x0 + ux * a, y0 + uy * a
            bx, by = x0 + ux * b, y0 + uy * b
            d.line((ax, ay, bx, by), fill=ink, width=wi)
            if cap:                       # design.md §2.8 — round caps here
                rr = w / 2.0
                d.ellipse((ax - rr, ay - rr, ax + rr, ay + rr), fill=ink)
                d.ellipse((bx - rr, by - rr, bx + rr, by + rr), fill=ink)
        s += on + off


# --------------------------------------------------------------- channels
#  A `spec` is the resolved channel state, never a state *name*, so a morph
#  is interpolated geometry and never a cross-fade (Amendment B / FILM §3).
#
#   ring   (colour, (on, off))            dash in unit lengths; off<=0 = solid
#   rings  [(r, w, colour, alpha, (on, off) | None, phase_deg)]
#                                         the travelling ring: clear pulse,
#                                         holdNet pings, holdGeo fence
#   blips  [a0, a1, a2]
#   core   (r_outer, r_inner, colour)     inner 0 = filled; off = 7.5 / 3.5,
#                                         i.e. design.md's r 5.5 stroke w 4
#   sweep  (needle_len, wedge_alpha, rot_deg)
#   geo    (ray_frac, ray_alpha, bx, by, blip_r, blip_alpha, halo_r, halo_a)
#   geo_col the fence/ray/contact colour — always the pose's OWN ring colour,
#           so the whole mark changes hue as one object and a frame can never
#           carry two accents

_SOLID = (CIRC33, 0.0)


def _pose(state, P, orn=None, still=False):
    """The five documented poses, as channels.  `orn` is the phase used by
    ornaments *born* inside this act (FILM §2.10's only exception); it starts
    at that element's cycle origin so nothing pops in mid-radius."""
    A = 0.0 if still else 1.0
    Q = P if orn is None else orn
    s = {'ring': (TEXT, _SOLID),
         'rings': [],
         'blips': [0.0, 0.0, 0.0],
         'core': (4.5, 0.0, TEXT),
         'sweep': (0.0, 0.0, 0.0),
         'geo': (0.0, 0.0, GEO_XY[0], GEO_XY[1], 0.0, 0.0, 0.0, 0.0),
         'geo_col': TEXT}

    if state == 'clear':
        if still:
            r, a = 25.0, 0.22
        else:
            pr = (Q * PULSE_RATE) % 1.0
            r = PULSE_R0 + pr * PULSE_DR
            a = (1.0 - pr) * _clamp01(pr / 0.15) * 0.5
        s['rings'] = [(r, 3.0, TEXT, a, None, 0.0)]
        s['blips'] = [_clamp01(0.8 + 0.2 * math.sin(P * 1.6 + i * 1.3) * A)
                      for i in range(3)]

    elif state == 'verify':
        s['sweep'] = (SWEEP_MAX, 0.20,
                      (P * 150.0) % 360.0 if not still else 0.0)
        s['blips'] = [_clamp01(0.3 + 0.12 * math.sin(P * 2.2 + i) * A)
                      for i in range(3)]

    elif state == 'holdNet':
        s['ring'] = (AMBER, DASH_HOLDNET)
        s['geo_col'] = AMBER
        s['core'] = (4.5, 0.0, AMBER)
        rs = []
        for i in (0, 1):
            if still:
                r, a = 10.0 + i * 11.0, 0.80 - i * 0.46
            else:
                pr = ((Q * 0.7) + i * 0.5) % 1.0
                r = 7.0 + pr * 19.0
                a = (max(0.0, 1.0 - pr) ** 0.55 * _clamp01(pr / 0.10)
                     * (1.0 if i == 0 else 0.42))
            rs.append((r, 3.0, AMBER, a, None, 0.0))
        s['rings'] = rs

    elif state == 'holdGeo':
        s['ring'] = (AMBER, _SOLID)      # it does NOT break — the thesis
        s['geo_col'] = AMBER
        s['rings'] = [(15.0, 3.0, AMBER, 0.9, DASH_FENCE,
                       (P * 45.0) % 360.0 if not still else 0.0)]
        lunge = 0.0 if still else GEO_LUNGE * (0.5 + 0.5 * math.sin(P * 2.2))
        sc = 1.0 if still else 1.0 + 0.16 * math.sin(P * 3.0)
        bx = GEO_XY[0] - 0.773 * lunge  # (-0.773, +0.634) points at the hub:
        by = GEO_XY[1] + 0.634 * lunge  # the contact lunges and is pushed back
        if still:
            hr, ha = 6.5, 0.5
        else:
            hp = (P * 1.1) % 1.0
            hr, ha = 3.0 + hp * 5.0, (1.0 - hp) * 0.8
        s['geo'] = (1.0, 0.9, bx, by, 4.5 * sc, 1.0, hr, ha)

    elif state == 'off':
        s['ring'] = (RED, DASH_OFF)
        s['geo_col'] = RED
        s['core'] = (7.5, 3.5, RED)      # hollow: nothing is holding this
        s['blips'] = [0.22, 0.22, 0.22]  # dead, and no P appears anywhere

    else:
        raise ValueError(state)
    return s


def _align_rings(ra, rb):
    """Pair up the two sides' travelling rings so a morph never fades a
    finished circle in on top of the frame.  Which way a missing ring is
    padded is decided by what is happening to it:

    * a ring being **born** emerges from the hub (r 0 -> target), which is
      how FILM §3 describes the `clear` pulse and the holdNet pings;
    * a ring that is **dying** and has a sibling on the far side travels into
      it — that is 'the pings collapse into the fence at r 15' (M6, f1050);
    * a ring that is dying with nothing to merge into fades where it stands,
      opacity only.  That is the `clear` pulse when the sweep takes over
      (f1026) and the holdGeo fence when the guard goes off (f1062); in both
      cases inventing a travel would be motion that reports nothing, and the
      second one is a failure entrance, which is opacity-only and sober.
    """
    ra, rb = list(ra), list(rb)
    n = max(len(ra), len(rb))
    survivor = rb[0] if rb else None
    while len(ra) < n:                       # born: out of the hub
        _r, w, c, _a, d, ph = rb[len(ra)]
        ra.append((0.0, w, c, 0.0, d, ph))
    while len(rb) < n:                       # dying
        r, w, c, _a, d, ph = ra[len(rb)]
        if survivor is not None:             # ... into the ring that survives
            r2, w2, c2, _a2, d2, p2 = survivor
            rb.append((r2, w2, c2, 0.0, d2, p2))
        else:                                # ... in place, opacity only
            rb.append((r, w, c, 0.0, d, ph))
    return ra, rb


def _blend_dash(a, b, k, circ=CIRC33):
    """Morph one dash pattern into another.  Solid is (circumference, 0), so
    solid <-> (5,6) is a real interpolation of the ring's geometry and never a
    cross-fade: the ring breaks into segments that march out from the 0 deg
    seam, and re-knits the same way.  FILM §3.

    The interpolation is **linear in the segment count** and linear on the
    duty cycle.  The segment count is the quantity the eye actually reads —
    "how many dashes are there" — so making that the linear channel is what
    makes the break and the re-knit look like one continuous mechanism.

    FILM §3 writes this as `on = lerp(207.345, 5, k)`.  That is linear in the
    dash *length*, which is hyperbolic in the count: solid -> (5,6) stays
    visually solid until k > 0.85 and then snaps.  Interpolating the period
    geometrically instead — the previous version of this function — has the
    opposite failure: at the halfway point of a 6-frame beat it puts the ring
    through **three or four enormous arcs**, a shape that belongs to neither
    pose and reads as a third state flashing past.  Both were checked on
    rendered frames.  Linear count avoids both: 1 -> 19 segments passes
    through 5, 9, 13, 17 and every frame is legibly on its way somewhere.
    Endpoints are identical at k = 0 and k = 1, so no pose anywhere in the
    film changes; only the shape of the frames in between does."""
    solid = (circ, 0.0)
    a = a or solid
    b = b or solid
    pa = max(1e-6, a[0] + a[1])
    pb = max(1e-6, b[0] + b[1])
    n = _lerp(circ / pa, circ / pb, k)        # segments around the ring
    per = circ / max(1e-6, n)
    duty = _lerp(a[0] / pa, b[0] / pb, k)
    on = per * duty
    return (on, max(0.0, per - on))


def _colour_k(k):
    """Colour runs ahead of geometry.

    design.md §2.12: 'A state transition must change the ring first — colour
    and dash are the fastest-read channel.'  Advancing the colour channel
    keeps a morph honest to that law and, on the two beats that cross between
    red and neutral, keeps the ring out of the pastel midpoint a straight
    lerp would sit on for a frame.  FILM §4.13 asks D1 for one hue at a time
    and names its four runs neutral / amber / red / neutral by pose boundary;
    biasing the hue onto the leading frame of each morph is what makes that
    literally true, and it leaves all six frames of *geometry* to carry the
    change — which is the channel the viewer is meant to be reading."""
    m = 1.0 - _clamp01(k)
    return 1.0 - m * m * m


def _alpha_k(va, vb, k, kc):
    """An element that is *leaving* goes out on the fast colour curve; one
    that is arriving takes the full geometric curve.

    This is what keeps the one-hue law (FILM §2.6: 'amber and red never
    coexist in a frame') true through f1062, where the ring turns red while
    the amber fence, ray and contact are still on screen.  Faded on the
    geometry curve they would overlap the new hue for two frames; faded ahead
    of it they are gone before the red arrives, and the frame carries exactly
    one accent — which is also the honest reading, since what leaves when the
    guard goes off is the guard itself."""
    return _lerp(va, vb, kc if vb < va else k)


#  Channel delays, in frames, inside a 6-frame morph.  Amendment B: "elements
#  do not all move together on the same frame.  Stagger entrances 2-4 frames
#  apart so motion has a leading edge."  A morph is not an entrance, so the
#  stagger is scaled to the beat — but the principle is the same, and it is
#  also design.md §2.12's law of reading order made temporal: the ring leads
#  (colour and dash are the fastest read at any size), the core and the
#  travelling ring follow a frame later, the contacts and the whole geo group
#  a frame after that.  Every channel still lands on the beat's last frame, so
#  the pose that follows is always fully settled.
#
#  Without this the ten beats of D1 are ten simultaneous parameter jumps and
#  the run reads as a slideshow of five pictures.  With it each morph has a
#  leading edge you can actually watch.
_CH_DELAY = {'ring': 0, 'rings': 1, 'core': 1, 'sweep': 1,
             'blips': 2, 'geo': 2}


def _kset(f, start, ease, dur=6):
    """Per-channel eased progress for the morph beginning on frame `start`.

    Frame `start` is the first frame that shows movement and
    `start + dur - 1` is the frame that lands — the same convention the rest
    of this module and scene_wire.py use.  The channel delays are stated for a
    6-frame beat and scale with `dur`, so lengthening a morph lengthens the
    stagger with it instead of leaving every channel bunched at the front."""
    sc = dur / 6.0
    def k(channel):
        d = int(round(_CH_DELAY.get(channel, 0) * sc))
        span = max(1, dur - d)
        return _clamp01(ease((f - start + 1 - d) / float(span)))
    return k


def _blend(a, b, kk):
    """Channel-wise interpolation of two poses.  `kk` is either a scalar
    progress or a callable channel -> progress (see `_kset`).  Angles are the
    one thing that is never interpolated — an element must not appear to
    rotate (craft §4.3) — so a rotating angle is taken from whichever side
    actually owns a rotating element."""
    if not callable(kk):
        _k = float(kk)

        def kk(_ch, _v=_k):
            return _v

    k = kk('ring')
    kc = _colour_k(k)
    ac, ad = a['ring']
    bc, bd = b['ring']
    ring_col = _mix(ac, bc, kc)
    out = {'ring': (ring_col, _blend_dash(ad, bd, k)),
           'geo_col': _mix(a['geo_col'], b['geo_col'], kc)}

    #  Departures do not wait their turn.  `_CH_DELAY` staggers the *arrival*
    #  of each channel so the morph has a leading edge, but an element that is
    #  leaving rides the ring's own fast colour curve — it is gone before the
    #  new hue lands.  That is what keeps FILM §2.6's one-accent law literally
    #  true through f1062, where the ring turns red while the amber fence, ray
    #  and contact are still on screen: delayed, they would linger for three
    #  frames wearing the new colour, which is both two hues and a lie (the
    #  fence is not a danger element).  Led out, they are simply gone.
    kfast = kc

    kr = kk('rings')
    krc = _colour_k(kr)
    ra, rb = _align_rings(a['rings'], b['rings'])
    rings = []
    for i in range(len(ra)):
        r0, w0, c0, a0, d0, p0 = ra[i]
        r1, w1, c1, a1, d1, p1 = rb[i]
        r = _lerp(r0, r1, kr)
        # "solid" is this ring's own circumference, not the outer ring's, so a
        # pulse at r 34 becoming a fence at r 15 breaks at the right rate.
        dash = _blend_dash(d0, d1, kr, max(1e-3, 2.0 * math.pi * max(r, 1e-3)))
        # a ring on its way out with nothing to become adopts the *outer*
        # ring's new colour, so the mark never shows an old accent beside a
        # new one
        col = ring_col if (a1 <= 1e-4 < a0) else _mix(c0, c1, krc)
        rings.append((r, _lerp(w0, w1, kr), col,
                      _alpha_k(a0, a1, kr, kfast),
                      None if dash[1] <= 1e-4 else dash,
                      p1 if d1 else (p0 if d0 else 0.0)))
    out['rings'] = rings

    kb = kk('blips')
    out['blips'] = [_lerp(a['blips'][i], b['blips'][i], kb) for i in range(3)]

    kco = kk('core')
    ao, ai, acol = a['core']
    bo, bi, bcol = b['core']
    out['core'] = (_lerp(ao, bo, kco), _lerp(ai, bi, kco),
                   _mix(acol, bcol, _colour_k(kco)))

    ks = kk('sweep')
    an, aw, arot = a['sweep']
    bn, bw, brot = b['sweep']
    rot = brot if bn > 0.05 else (arot if an > 0.05 else 0.0)
    out['sweep'] = (_lerp(an, bn, ks), _lerp(aw, bw, ks), rot)

    # geo = (ray_frac, ray_a, bx, by, blip_r, blip_a, halo_r, halo_a)
    kg = kk('geo')
    _ga = (1, 5, 7)                          # the three opacity components
    out['geo'] = tuple(
        _alpha_k(a['geo'][i], b['geo'][i], kg, kfast) if i in _ga
        else _lerp(a['geo'][i], b['geo'][i], kg)
        for i in range(8))
    return out


def _spec_key(spec):
    return (spec['ring'][0], tuple(round(v, 3) for v in spec['ring'][1]),
            tuple((round(r, 3), round(w, 3), c, round(al, 4),
                   None if dsh is None else (round(dsh[0], 3),
                                             round(dsh[1], 3)),
                   round(ph, 2))
                  for (r, w, c, al, dsh, ph) in spec['rings']),
            tuple(round(v, 4) for v in spec['blips']),
            (round(spec['core'][0], 3), round(spec['core'][1], 3),
             spec['core'][2]),
            tuple(round(v, 3) for v in spec['sweep']),
            tuple(round(v, 3) for v in spec['geo']), spec['geo_col'])


def _radar_tile(size, spec, ss=4):
    """Render the mark into an RGBA tile of `size` px."""
    key = (size, ss) + _spec_key(spec)
    hit = _TILE_CACHE.get(key)
    if hit is not None:
        return hit

    n = size * ss
    im = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    #  'RGBA': without it ImageDraw REPLACES the destination pixel on an RGBA
    #  image, so a translucent ornament crossing the opaque ring erased a band
    #  out of the stroke.  See scene_open.py.
    d = ImageDraw.Draw(im, 'RGBA')
    u = n / 100.0
    hx = hy = 50.0 * u

    # 1 — the verify sweep, UNDER the ring and clamped inside its inner edge.
    #     The wedge lags the needle: it is a trail, not a comet flying
    #     tail-first (design.md §2.6), and it DECAYS — a flat-alpha pie slice
    #     with two hard radial edges is a loading-spinner asset.
    nlen, walpha, rot = spec['sweep']
    nlen = min(nlen, SWEEP_MAX)
    if walpha > 0.002:
        for i in range(12):
            a0 = math.radians(270.0 - 61.5 * i / 12.0 + rot)
            a1 = math.radians(270.0 - 61.5 * (i + 1) / 12.0 + rot)
            sa = walpha * (1.0 - i / 12.0) ** 1.35
            if sa <= 0.003:
                continue
            d.polygon([(hx, hy),
                       (hx + SWEEP_MAX * u * math.cos(a0),
                        hy + SWEEP_MAX * u * math.sin(a0)),
                       (hx + SWEEP_MAX * u * math.cos(a1),
                        hy + SWEEP_MAX * u * math.sin(a1))],
                      fill=_rgba(TEXT, sa))
    if nlen > 0.05:
        a = math.radians(270.0 + rot)
        ex, ey = hx + nlen * u * math.cos(a), hy + nlen * u * math.sin(a)
        ink = _rgba(TEXT, min(1.0, nlen / 14.0))
        d.line((hx, hy, ex, ey), fill=ink, width=max(1, int(round(4.0 * u))))
        rr = 2.0 * u                       # round cap
        d.ellipse((ex - rr, ey - rr, ex + rr, ey + rr), fill=ink)
        d.ellipse((hx - rr, hy - rr, hx + rr, hy + rr), fill=ink)

    # 2 — the outer ring.  Colour and dash are the fastest-read channel at
    #     any size, so they morph first (design.md §2.12).
    rc, (don, doff) = spec['ring']
    _ring(d, hx, hy, 33.0 * u, 6.0 * u, rc, 1.0,
          None if doff <= 1e-4 else (don * u, doff * u), 0.0)

    # 3/4 — the travelling ring: the clear pulse, the holdNet pings, the
    #       holdGeo fence.  One channel, re-tuned; that is why a pulse can
    #       *become* a fence without anything fading.  A ping is drawn as two
    #       opposed wavefronts, never as a closed ring: two concentric circles
    #       inside a dashed one is a bullseye.
    is_ping = spec['ring'][0] == AMBER and spec['ring'][1][1] > 1e-4
    for (r, w, col, al, dsh, ph) in spec['rings']:
        if al > 0.004 and r > 0.2:
            if is_ping and dsh is None:
                ro = r * u + w * u / 2.0
                box = (hx - ro, hy - ro, hx + ro, hy + ro)
                for a0, sweep in _PING_ARCS:
                    d.arc(box, a0, a0 + sweep, fill=_rgba(col, al),
                          width=max(1, int(round(w * u))))
            else:
                _ring(d, hx, hy, r * u, w * u, col, al,
                      None if dsh is None else (dsh[0] * u, dsh[1] * u), ph)

    # 5 — the contacts.  Never amber, never red: they are the neutral.
    for i, (bx, by) in enumerate(BLIPS):
        al = spec['blips'][i]
        if al > 0.001:
            rr = 3.6 * u
            d.ellipse((bx * u - rr, by * u - rr, bx * u + rr, by * u + rr),
                      fill=_rgba(TEXT, min(1.0, al)))

    # 6 — the holdGeo group.  The contact's closest approach is d=16.0 and
    #     the fence is at 15: it never gets in.  Protect that.  Its far edge
    #     reaches 26 against a ring stroke that starts at 30, so the mark
    #     keeps its silhouette — see scene_hold.py for why that matters.
    rfrac, ralpha, gx, gy, gr, ga, hr, ha = spec['geo']
    gcol = spec['geo_col']
    if ralpha > 0.004:
        _dashed_seg(d, (hx, hy), (GEO_XY[0] * u, GEO_XY[1] * u), gcol, 2.5 * u,
                    (2.2 * u, 2.4 * u), ralpha, rfrac)
    if ga > 0.004 and gr > 0.05:
        bx, by, rr = gx * u, gy * u, gr * u
        d.ellipse((bx - rr, by - rr, bx + rr, by + rr), fill=_rgba(gcol, ga))
        if ha > 0.004 and hr > 0.05:
            hrr = hr * u
            _ring(d, bx, by, hrr, 2.5 * u, gcol, ha)

    # 8 — the core.  Hollow only in `off`; never fill it there.
    ro, ri, ccol = spec['core']
    if ro > 0.2:
        if ri > 0.15:
            _ring(d, hx, hy, (ro + ri) / 2.0 * u, (ro - ri) * u, ccol, 1.0)
        else:
            rr = ro * u
            d.ellipse((hx - rr, hy - rr, hx + rr, hy + rr),
                      fill=_rgba(ccol, 1.0))

    out = im.resize((size, size), Image.LANCZOS)
    if len(_TILE_CACHE) < 128:
        _TILE_CACHE[key] = out
    return out


def _blit_mark(dst, spec, alpha=1.0, size=MARK_BOX, centre=MARK_C, ss=4):
    if alpha <= 0.004:
        return
    tile = _radar_tile(size, spec, ss)
    if alpha < 0.999:
        tile = tile.copy()
        tile.putalpha(tile.getchannel('A').point(
            lambda v, k=alpha: int(v * k)))
    dst.alpha_composite(tile, (int(round(centre[0] - size / 2.0)),
                               int(round(centre[1] - size / 2.0))))


# =====================================================================
#  3.  D1 — THE FIVE-STATE RUN
# =====================================================================
#  Ten equal 6-frame beats: five poses, five morphs, in the identity study's
#  canonical order, landing home on f1079 so D2 opens on a settled `clear`.
#  Zero words: Amendment A's "individually labelled" requirement is
#  discharged by the five dedicated beats earlier in the film, and a recap
#  that re-labels is a recap that does not trust its own film.

D1_IN, D2_IN, LAST = 1020, 1110, 1199

#  D1 grew 60 -> 90 frames, paid for out of D2's dead tail (the end card was
#  frozen for 67 of its 120 frames; it is now frozen for 32, which is still
#  the film's second silence).  Amendment A: "the TRANSITIONS BETWEEN STATES
#  are the point, not just the static poses" — so the morph is the long beat
#  and the pose is the short one, 12 f against 6, not the other way round.
PULSE_BIRTH_C4 = 1005    # scene_hold births the clear pulse here (FILM §4.12)
PULSE_BIRTH_D1 = 1098    # and the run re-births it on the final morph
PING_BIRTH_D1 = 1044     # the holdNet pings are born inside their own morph

MORPH, POSE = 12, 6

#  (first frame, kind, from, to, easing).  Entering `off` is the only beat
#  that is sober — entering a failure state always is, and EASE_SOBER is
#  ease-out only, so it cannot bounce.  Everything else runs on a symmetric
#  S: at 12 frames it spends its middle six on the middle half of the travel,
#  which is the only way a viewer can watch a ring break and re-knit.
_RUN = (
    (1020, 'pose', 'clear', None, None),
    (1026, 'morph', 'clear', 'verify', EASE_IN_OUT),
    (1038, 'pose', 'verify', None, None),
    (1044, 'morph', 'verify', 'holdNet', EASE_SOBER),
    (1056, 'pose', 'holdNet', None, None),
    #  THE BEAT.  holdNet -> holdGeo is the only place in the film where the
    #  ring re-knits from broken to solid, and it is the same difference C2
    #  spent 90 frames teaching, replayed in twelve.  At six frames on an
    #  ease-out the 24 dashes collapsed into 4 giant arcs and then 2 over
    #  three frames, which reads as a glitch rather than as a knit.
    (1062, 'morph', 'holdNet', 'holdGeo', EASE_IN_OUT),
    (1074, 'pose', 'holdGeo', None, None),
    (1080, 'morph', 'holdGeo', 'off', EASE_SOBER),
    (1092, 'pose', 'off', None, None),
    (1098, 'morph', 'off', 'clear', EASE_IN_OUT),
)
BEAT = MORPH


def _orn_phase(state, f, P):
    """FILM §2.10: the mark's phase is global and never resets.  The only
    exceptions are elements *born* mid-film, which run on P_local so they
    start at their cycle origin."""
    if state == 'clear':
        birth = PULSE_BIRTH_D1 if f >= PULSE_BIRTH_D1 else PULSE_BIRTH_C4
        return (f - birth) / 30.0
    if state == 'holdNet':
        return (f - PING_BIRTH_D1) / 30.0
    return P


def _spec_run(f):
    """The resolved mark for any frame of D1."""
    P = f / 30.0
    for start, kind, a, b, ease in reversed(_RUN):
        if f < start:
            continue
        if kind == 'pose':
            return _pose(a, P, _orn_phase(a, f, P))
        return _blend(_pose(a, P, _orn_phase(a, f, P)),
                      _pose(b, P, _orn_phase(b, f, P)),
                      _kset(f, start, ease, MORPH))
    return _pose('clear', P, (f - PULSE_BIRTH_C4) / 30.0)


D1_CAP = 'Five states. One mark.'
FK_D1_CAP = ('ui', 44, 400)
Y_D1_CAP = 812
AT_D1_CAP = 1026


def _shot_d1(dst, f):
    """D1 `end.set` — f1020 … f1109.  The five-state run.

    Cut in hard: on f1020 the label, the caption, the rule and the readout
    stop existing and the mark RECOMPOSES — 520 px off-centre-right becomes
    620 px dead centre.  A near-match (390 px of travel at almost the same
    scale) is the sloppiest cut available, because the eye is tracking that
    object and it lurches; a frank recompose reads as "now look here".

    Amendment A asks for the five states as a SET, and for the transitions
    between them to be the subject.  Each of the five is individually named at
    hero scale earlier in the film — `VERIFYING`, `CLEARED`,
    `HOLD · CONNECTION`, `UNGUARDED`, `HOLD · LOCATION` — for 75 to 105 frames
    apiece; this shot is where they are put side by side in time, so it names
    the idea once and then gets out of the way.  Re-labelling five poses at
    six frames each would be five strings nobody can read, and it would take
    the eye off the only thing here worth watching.
    """
    _blit_mark(dst, _spec_run(f), size=RUN_BOX, centre=RUN_C)
    if f >= AT_D1_CAP:
        segs = ((D1_CAP, TEXT2),)
        _text(dst, _centre_x(RUN_C[0], FK_D1_CAP, segs, 0.36), Y_D1_CAP,
              segs, FK_D1_CAP, tracking=0.36, rise=6.0,
              p=_clamp01((f - AT_D1_CAP + 1) / float(REVEAL)),
              stagger=STAG, ease=EASE_ENTER, span_cap=SPAN_CAP)


# =====================================================================
#  4.  D2 — THE END CARD
# =====================================================================
#  Layout E, centred, sanctioned.  Four objects: a mark, a word, a line, an
#  address.  No button, no badge, no feature list, no QR code, no logo bug.
#  Fully neutral: the last 120 frames of the film contain no amber and no
#  red — it ends where it started, calm.

WORDMARK = 'TOWER'
TAGLINE = 'A control tower for your Claude agents.'   # README, verbatim
URL_DIM = 'ghhrmnzdh.github.io/'                      # site/index.html
URL_LIT = 'tower'                                     # canonical, and it
#  resolves.  The brief's shorthand "tower.sh" does not exist; the install
#  one-liner is 48 characters and would push this frame past the 11-word
#  ceiling, so the film shows the site and the site shows the command.

FK_WORD = ('serif', 200, 560)
FK_TAG = ('ui', 36, 400)
FK_URL = ('mono', 30, None)
TR_WORD = 12.0
TR_TAG = 0.36

Y_WORD, Y_TAG, Y_URL = 660, 756, 888     # every baseline is 120 + 12k.
#  Three near-identical gaps (105 / 84 / 108) for three different hierarchical
#  distances is not a rhythm.  140 / 96 / 132 locks the mark and the wordmark
#  together and clearly detaches the address.

#  OPTICAL KERNING, on top of the +12 flat track.  Measured inter-glyph gaps
#  were T|O 24, O|W 20, W|E 18, E|R 25 — in a high-contrast serif the optical
#  requirement runs the other way, because O|W (round against diagonal) opens
#  the biggest hole and W|E (diagonal terminal against a flat stem) closes the
#  tightest.  The word read "TO WER" with a lump at WE.
KERN_WORD = {'TO': -8.0, 'OW': -8.0, 'WE': +8.0, 'ER': 0.0}

REVEAL = 24                              # type reveal envelope, frames
SPAN_CAP = 9.0 / REVEAL                  # per-char stagger span cap, 9 f
STAG = 0.62 / REVEAL                     # 0.62 f per character

AT_WORD, AT_TAG = 1113, 1117
AT_URL_DIM, AT_URL_LIT = 1140, 1145


def _url_segments():
    return ((URL_DIM, MUTED), (URL_LIT, TEXT))


def _shot_d2(dst, f):
    """D2 `end.card` — f1110 … f1199.

    Cut in: hard.  The mark relocates from (960,470)/620 px to (960,300)/
    280 px — a change of size, not of place, so the eye stays put and the
    world shrinks around it.

    The mark is at its REDUCE-MOTION still values and nothing about it
    animates: pulse frozen at r 25 units, alpha 0.22.  craft §4.7 — the quiet
    state is completely still, and the end card is the quietest thing in the
    film.  (The frozen pulse is what used to make this mark read as a button
    with three thread holes; at 0.22 and r 25 it is a faint echo just inside
    the ring, not a second concentric circle.)

    Choreography: 3 frames of the mark alone, then one GROUP (wordmark, then
    the tagline 4 f behind it), then the address arrives as a staggered PAIR —
    the dim host, then the lit path 5 f later.  It used to wipe on with a
    16-frame clip reveal, which meant the one string in the film that has to
    be exact spent half a second reading `ghhrmnzdh.github.io/to`: a
    plausible, wrong, fully legible address.  Two objects entering in
    sequence is the same gesture and it can never spell something else.
    """
    _blit_mark(dst, _pose('clear', 0.0, still=True), size=CARD_BOX,
               centre=CARD_C, ss=6)

    if f >= AT_WORD:
        segs = ((WORDMARK, TEXT),)
        _text(dst, _centre_x(CARD_C[0], FK_WORD, segs, TR_WORD, KERN_WORD),
              Y_WORD, segs, FK_WORD, tracking=TR_WORD, rise=28.0,
              p=_clamp01((f - AT_WORD + 1) / float(REVEAL)),
              stagger=STAG, ease=EASE_ENTER, span_cap=SPAN_CAP,
              kern=KERN_WORD)

    if f >= AT_TAG:
        segs = ((TAGLINE, TEXT2),)
        _text(dst, _centre_x(CARD_C[0], FK_TAG, segs, TR_TAG), Y_TAG,
              segs, FK_TAG, tracking=TR_TAG, rise=5.0,
              p=_clamp01((f - AT_TAG + 1) / float(REVEAL)),
              stagger=STAG, ease=EASE_ENTER, span_cap=SPAN_CAP)

    if f >= AT_URL_DIM:
        _draw_url(dst, f)


def _draw_url(dst, f):
    """The address, as two objects on one baseline: the host in MUTED, then
    the path in TEXT five frames later.  The whole string is laid out first so
    the host never moves when the path arrives."""
    segs = _url_segments()
    x0 = _centre_x(CARD_C[0], FK_URL, segs, 0.0)
    a_dim = EASE_ENTER(_clamp01((f - AT_URL_DIM + 1) / 12.0))
    a_lit = EASE_ENTER(_clamp01((f - AT_URL_LIT + 1) / 12.0))
    r_dim = (1.0 - a_dim) * 5.0
    r_lit = (1.0 - a_lit) * 5.0
    _text(dst, x0, Y_URL + r_dim, ((URL_DIM, MUTED),), FK_URL, alpha=a_dim)
    if a_lit > 0.004:
        _text(dst, x0 + _run_w(FK_URL, URL_DIM, 0.0), Y_URL + r_lit,
              ((URL_LIT, TEXT),), FK_URL, alpha=a_lit)


# =====================================================================
#  5.  THE SCENE CONTRACT
# =====================================================================

def draw(ctx) -> None:
    """Paint this scene's content onto ctx.img, in place."""
    f = int(ctx.f)
    if f < RANGE[0] or f > RANGE[1]:
        return

    im = ctx.img
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))

    if f < D2_IN:
        _shot_d1(lay, f)
    else:
        _shot_d2(lay, f)

    if im.mode == 'RGBA':
        im.alpha_composite(lay)
    else:
        im.paste(lay, (0, 0), lay)
