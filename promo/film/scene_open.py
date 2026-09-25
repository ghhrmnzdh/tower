"""scene_open.py — Act A of the Tower film.

Frames 0 … 329 inclusive (330 frames, 0.000 s – 11.000 s).

    A1  open.mark     0 …  89   the mark draws itself onto nothing
    A2  open.where   90 … 179   Layout H   "Where you are."
    A3  open.verify 180 … 254   Layout M   verify · VERIFYING
    A4  open.clear  255 … 329   Layout M   MORPH M1 verify -> clear

Everything here is a pure function of the absolute frame index. No clock, no
unseeded randomness, no neighbour-frame state. Frame N is byte-identical every
run and at every `-j`.

Public surface is exactly:

    RANGE = (0, 329)
    def draw(ctx) -> None

`ctx` is the Ctx dataclass from brand.py: ctx.img (RGB 1920x1080, already
filled with INK), ctx.d, ctx.f (absolute frame), ctx.t, ctx.dur, ctx.k, ctx.sf.
Only ctx.img and ctx.f are load-bearing — every frame number in FILM.md is
absolute, so this module drives off ctx.f and never off ctx.t.

brand.py / draw.py / ui.py did not exist when this module was written (they are
being authored in parallel).  Section 0 below therefore *prefers* the shared
helpers when they are importable and falls back to a local implementation that
is faithful, constant for constant, to notes/design.md §2 and FILM.md §2–§4.

THE SEAM THAT MATTERS.  f329 is the outgoing half of the film's structural
match cut (FILM §1: the mark leaves in `clear` at (1350,540)/520 px and returns
bit-identical at f420 in scene_wire).  The pulse rate is 30/91 turns per second
for exactly that reason — one whole cycle in the 91-frame gap.  `_radar_tile()` and `_spec_clear()` here
are line-for-line the same code and the same constants as scene_wire's, and the
`clear` pulse runs on the same global birth frame (262).  Change one and the
match cut stops being a match cut.
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFont

# =====================================================================
#  0.  ADAPTER — prefer the shared toolkit, fall back to a local one
# =====================================================================

_B = _D = _U = None
for _mod in ('brand', 'draw', 'ui'):
    try:                                        # package-relative first
        _m = __import__('promo.film.' + _mod, fromlist=[_mod])
    except Exception:
        try:
            _m = __import__(_mod)
        except Exception:
            _m = None
    if _mod == 'brand':
        _B = _m
    elif _mod == 'draw':
        _D = _m
    else:
        _U = _m


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

RANGE = (0, 329)

# --------------------------------------------------------------- colour
INK = (0x0C, 0x0C, 0x0E)
HAIRLINE = (0x34, 0x34, 0x3A)
TEXT = (0xE7, 0xE6, 0xE2)
TEXT2 = (0x9A, 0x9A, 0x95)
MUTED = (0x8B, 0x8B, 0x86)
KICKER = (0x7C, 0x7C, 0x77)
AMBER = (0xE6, 0xA9, 0x3C)
RED = (0xE5, 0x48, 0x4D)
# GREEN #30D158 is defined by the system and deliberately never used in this
# film: the passing radar is neutral, not green (FILM §2.6).


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
    """promo/overlays.py:font() verbatim — the axis order differs per face and
    getting it wrong silently produces the wrong weight."""
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


def _spring(response, zeta):
    """SwiftUI .spring(response:dampingFraction:) -> f(t seconds)."""
    w0 = 2.0 * math.pi / response
    if zeta < 1.0:
        wd = w0 * math.sqrt(1.0 - zeta * zeta)

        def f(t):
            if t <= 0:
                return 0.0
            return 1.0 - math.exp(-zeta * w0 * t) * (
                math.cos(wd * t) + (zeta * w0 / wd) * math.sin(wd * t))
        return f

    def g(t):
        return 0.0 if t <= 0 else 1.0 - math.exp(-w0 * t) * (1.0 + w0 * t)
    return g


EASE_ENTER = _shared(_B, 'EASE_ENTER') or _bezier(0.16, 1.00, 0.30, 1.00)
EASE_MOVE = _shared(_B, 'EASE_MOVE') or _bezier(0.65, 0.00, 0.35, 1.00)
EASE_SOBER = _shared(_B, 'EASE_SOBER') or _bezier(0.33, 1.00, 0.68, 1.00)
EASE_EXIT = _shared(_B, 'EASE_EXIT') or _bezier(0.32, 0.00, 0.67, 0.00)
SETTLE = _shared(_B, 'SETTLE') or _spring(0.45, 0.85)
ARRIVE = _shared(_B, 'ARRIVE') or _spring(0.55, 0.72)


def _fade_in(f, at, dur, ease):
    """0 before `at`, 1 from `at + dur - 1`. Frame `at` is the first visible."""
    return _clamp01(ease((f - at + 1) / float(dur)))


def _fade_out(f, at, dur, ease):
    """1 before `at`, 0 at `at + dur - 1` — an 8 f exit vacates the slot on
    f = at+7 so the incoming line may legally start on at+8 (FILM §2.8 RELAY:
    never a frame of overlap)."""
    if f < at:
        return 1.0
    return _clamp01(1.0 - ease((f - at + 1) / float(dur)))


# =====================================================================
#  1.  TEXT — sub-pixel, per-character, tracked
# =====================================================================
#  Pillow snaps ImageDraw.text() to integer pixels, which judders a 17 px rise
#  into 17 visible steps and instantly reads cheap (Amendment B).  Every glyph
#  here is rasterised once into a cached alpha mask and stamped at a float
#  position; the fractional part is applied as a bilinear affine shift of the
#  mask alone, so the colour never fringes.

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


def _run_w(fkey, s, tracking=0.0):
    if not s:
        return 0.0
    f = _font(*fkey)
    return sum(f.getlength(c) for c in s) + tracking * (len(s) - 1)


def _lsb(fkey, ch):
    """Left side bearing — for optical alignment on a flat-sided glyph
    (craft §3.4: align on the flat left of the first glyph, not the advance
    origin, or the column looks broken against the label beneath it)."""
    try:
        return float(_font(*fkey).getbbox(ch)[0])
    except Exception:
        return 0.0


def _text(dst, x, y, segs, fkey, tracking=0.0, alpha=1.0, rise=0.0,
          p=1.0, stagger=0.0, ease=None, span_cap=1.0):
    """Draw one line as a run of (string, colour) segments.

    p == 1 and stagger == 0 -> a plain tracked line at full opacity.
    Otherwise every glyph gets its own eased progress: alpha and a `rise` px
    upward settle, staggered by `stagger` (in units of p).  This is the film's
    only kinetic reveal.  Holds, offs and failures pass stagger=0 and drive
    `alpha` instead — a hold is never revealed kinetically.
    """
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
    cx = float(x)
    i = 0
    for s, col in segs:
        for ch in s:
            adv = f.getlength(ch) + tracking
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
#  Drawn at 4x and LANCZOS-downsampled: ImageDraw has no AA on arcs.
#  Draw order is design.md §2.1 — ring, sweep, pulse, blips, core.

#  brand.py is the AUTHORITY for the mark's geometry; the literals below are
#  only the fallback for running this module standalone. Do not edit them here
#  — edit brand.py, or the four scenes will disagree about the icon.
MARK_C = _shared(_B, 'MARK_C') or (1350.0, 540.0)   # canonical circle, FILM §2.3
MARK_BOX = _shared(_B, 'MARK_BOX') or 520           # 5.2 px per Glyph unit
_SS = 4

#  The `clear` pulse.  See brand.py: 30/91 turns/s puts exactly one cycle in
#  the 91-frame gap between f329 and f420, which is the only way that cut is
#  actually a match cut; and the range stops at r 28 so the pulse dissolves
#  before the ring stroke (r 30…36) instead of drawing a hairline inside it.
PULSE_RATE = 30.0 / 91.0
PULSE_R0, PULSE_DR = 8.0, 20.0
PULSE_FADE = 0.15

SWEEP_MAX = 27.5                  # needle + wedge stop 1 unit short of the
#  ring's inner edge (30.0) — 27.5 plus the needle's 2-unit round cap lands
#  at 29.5.  At 33.0 they were drawn ON the ring: the wedge
#  halved the white band along its arc and the needle's round cap landed
#  inside it, fusing the two into a blob with a spur.

_TILE_CACHE = {}

# NOTE — deliberately NOT delegated to `ui.radar_tile`.  Act A is the only act
# that draws the mark *incomplete*: a partial ring arc with an opening stroke
# width (f12–f47), a growing core (f48–f66) and a growing/retracting sweep
# (f70–f82, f262–f276).  The spec below is therefore a superset of the shared
# one, and a shared implementation that silently ignored `arc`, `ring_w`,
# `sweep` or the core's third element would not raise — it would just render a
# finished mark for 90 frames and delete the whole cold open.  The `clear` pose
# this file hands to the f329/f420 match cut is byte-verified against
# scene_wire's own tile instead.

BLIPS = ((64, 41), (38, 58), (58, 66))


def _ring(d, cx, cy, r, w, colour, alpha, dash=None, phase_deg=0.0,
          arc=None):
    """Stroke centred on radius r.  Pillow strokes inward from the bbox, so
    the bbox is built for r + w/2 (design.md §1.2 rule 3).

    `arc` is a SEQUENCE of (start_deg, sweep_deg) pairs for the A1 draw-on;
    `dash` is a (on, off) pair in the same units as r.  They are mutually
    exclusive — a ring is either being made or being patterned, never both.
    """
    if alpha <= 0.004 or r <= 0 or w <= 0:
        return
    ro = r + w / 2.0
    box = (cx - ro, cy - ro, cx + ro, cy + ro)
    ink = _rgba(colour, alpha)
    wi = max(1, int(round(w)))
    if arc is not None:
        for a0, sweep in arc:
            if sweep > 0.01:
                d.arc(box, a0, a0 + min(360.0, sweep), fill=ink, width=wi)
        return
    if not dash or dash[1] <= 1e-4:
        d.ellipse(box, outline=ink, width=wi)
        return
    circ = 2.0 * math.pi * r
    on_d = 360.0 * dash[0] / circ
    off_d = 360.0 * dash[1] / circ
    if on_d + off_d <= 0.05:
        d.ellipse(box, outline=ink, width=wi)
        return
    a = phase_deg
    end = phase_deg + 360.0
    while a < end:
        d.arc(box, a, min(a + on_d, end), fill=ink, width=wi)
        a += on_d + off_d


def _radar_tile(size, spec):
    """Render the mark into an RGBA tile of `size` px.

    `spec` is the resolved channel state — not a state *name* — so a morph is
    expressed as interpolated channels rather than a cross-fade of two
    finished pictures (Amendment B / FILM §3).

        ring    (colour, dash|None)     dash in unit lengths
        ring_w  float                   unit stroke width (6.0 canonical)
        arc     (start_deg, sweep_deg)|None    the A1 draw-on
        sweep   (rot_deg, needle_len, wedge_r, wedge_alpha)|None
        rings   [(r, w, colour, alpha)] the pulse, in unit lengths
        blips   [a0, a1, a2]
        core    ('fill', colour, r) | ('hollow', colour) | None
    """
    key = (size,
           spec['ring'][0], spec['ring'][1],
           round(spec.get('ring_w', 6.0), 4),
           spec.get('arc') and tuple((round(a0, 4), round(sw, 4))
                                     for a0, sw in spec['arc']),
           spec.get('sweep') and tuple(round(v, 4) for v in spec['sweep']),
           tuple(tuple(round(v, 4) if isinstance(v, float) else v
                       for v in r) for r in spec['rings']),
           tuple(round(a, 4) for a in spec['blips']),
           spec['core'] and (spec['core'][0], spec['core'][1],
                             round(spec['core'][2], 4)
                             if len(spec['core']) > 2 else None))
    hit = _TILE_CACHE.get(key)
    if hit is not None:
        return hit

    n = size * _SS
    im = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    #  'RGBA' mode is load-bearing, not stylistic.  ImageDraw on an RGBA image
    #  without it REPLACES the destination pixel, so any semi-transparent
    #  ornament crossing the opaque ring wrote alpha 8/255 over it and *erased*
    #  an 11 px band out of the stroke — a travelling hole that split the ring
    #  into two contours once every pulse cycle.
    d = ImageDraw.Draw(im, 'RGBA')
    u = n / 100.0
    hx = hy = 50.0 * u

    # 1 — the verify sweep, UNDER the ring.  Everything here is clamped to
    #     SWEEP_MAX so it lives inside the ring's inner edge; drawing it first
    #     as well means that if anything ever does reach the band, the ring
    #     wins and the silhouette survives.
    sw = spec.get('sweep')
    if sw:
        rot, nlen, wr, wa = sw
        wr = min(wr, SWEEP_MAX)
        nlen = min(nlen, SWEEP_MAX)
        if wa > 0.004 and wr > 0.3:
            #  A radar trail DECAYS.  A flat-alpha pie slice with two hard
            #  radial edges reads as a loading-spinner asset; twelve adjacent
            #  slices ramping to zero behind the needle read as a trail.
            #  Adjacent, never overlapping, so nothing double-composites.
            for j in range(12):
                a0 = math.radians(270.0 - 61.5 * j / 12.0 + rot)
                a1 = math.radians(270.0 - 61.5 * (j + 1) / 12.0 + rot)
                sa = wa * (1.0 - j / 12.0) ** 1.35
                if sa <= 0.003:
                    continue
                d.polygon([(hx, hy),
                           (hx + wr * u * math.cos(a0),
                            hy + wr * u * math.sin(a0)),
                           (hx + wr * u * math.cos(a1),
                            hy + wr * u * math.sin(a1))],
                          fill=_rgba(TEXT, sa))
        if nlen > 0.3:
            a = math.radians(270.0 + rot)
            nx = hx + nlen * u * math.cos(a)
            ny = hy + nlen * u * math.sin(a)
            # A round-capped 4-unit line shorter than ~2.5 caps is a blob, not
            # a needle.  Taper opacity over the last 10 units so the tip
            # dissolves into the hub instead of parking there as a comma.
            ink = _rgba(TEXT, min(1.0, nlen / 14.0))
            nw = max(1, int(round(4.0 * u)))
            d.line((hx, hy, nx, ny), fill=ink, width=nw)
            cr = 4.0 * u / 2.0                      # round cap, design §2.6
            d.ellipse((nx - cr, ny - cr, nx + cr, ny + cr), fill=ink)
            d.ellipse((hx - cr, hy - cr, hx + cr, hy + cr), fill=ink)

    # 2 — the outer ring.  Colour and dash are the fastest-read channel at any
    #     size, so they morph first (design.md §2.12).
    rc, rd = spec['ring']
    rw = spec.get('ring_w', 6.0)
    _ring(d, hx, hy, 33.0 * u, rw * u, rc, 1.0,
          (rd[0] * u, rd[1] * u) if rd else None, 0.0,
          arc=spec.get('arc'))

    # 3 — the motion ornament (the `clear` pulse), under the blips.
    for (r, w, col, a) in spec['rings']:
        _ring(d, hx, hy, r * u, w * u, col, a)

    # 4 — the contacts.  Never amber, never red: they are the neutral.
    for i, (bx, by) in enumerate(BLIPS):
        a = spec['blips'][i]
        if a > 0.001:
            rr = 3.6 * u
            d.ellipse((bx * u - rr, by * u - rr, bx * u + rr, by * u + rr),
                      fill=_rgba(TEXT, min(1.0, a)))

    # 5 — the core.  Hollow only in `off`: the centre is empty, nothing is
    #     holding this.  Never fill it.  (No `off` pose lives in Act A.)
    if spec['core']:
        mode = spec['core'][0]
        col = spec['core'][1]
        if mode == 'hollow':
            _ring(d, hx, hy, 5.5 * u, 4.0 * u, col, 1.0)
        else:
            rr = (spec['core'][2] if len(spec['core']) > 2 else 4.5) * u
            if rr > 0.2:
                d.ellipse((hx - rr, hy - rr, hx + rr, hy + rr),
                          fill=_rgba(col, 1.0))

    out = im.resize((size, size), Image.LANCZOS)
    if len(_TILE_CACHE) < 128:
        _TILE_CACHE[key] = out
    return out


def _blit_mark(dst, spec, alpha=1.0, size=MARK_BOX, centre=MARK_C):
    if alpha <= 0.004:
        return
    tile = _radar_tile(size, spec)
    if alpha < 0.999:
        tile = tile.copy()
        tile.putalpha(tile.getchannel('A').point(
            lambda v, k=alpha: int(v * k)))
    dst.alpha_composite(tile, (int(round(centre[0] - size / 2.0)),
                               int(round(centre[1] - size / 2.0))))


# =====================================================================
#  3.  ACT A TIMELINE
# =====================================================================

A1, A2, A3, A4, A_END = 0, 90, 180, 255, 330

# --- A1, the draw-on ---------------------------------------------------
RING_AT, RING_DUR = 8, 36         # two opposed 180 deg arcs closing, EASE_MOVE
RINGW_AT, RINGW_DUR = 8, 10       # stroke width 0 -> 6 units, EASE_ENTER
CORE_AT, CORE_DUR = 46, 19        # ARRIVE — the film's only overshoot
BLIP_AT = (58, 61, 64)            # staggered 3 f, EASE_ENTER 13 f each
SWEEP_AT, SWEEP_DUR = 66, 15      # the state resolves to `verify`

# --- A4, the morph -----------------------------------------------------
M1_AT, M1_DUR = 262, 15           # verify -> clear, SETTLE
PULSE_BORN = 262                  # the `clear` pulse's phase origin.  Global:
#                                   scene_wire reads the same number at f420.

# --- Layout M slots (FILM §2.4) ---------------------------------------
#  Everything moved up one type tier and in from x=160 to x=200.  At 24/26/36
#  the copy column was UI-caption sizing dropped into a 1920x1080 film: the
#  state label's cap height was 1.6 % of frame height, the whole picture ran
#  at 1.6 % ink, and the eye went to the ring — the one object with no words
#  on it — and never travelled back.  Layout H now shares Layout M's spine
#  (kicker 432 / first line 564 against label 432 / caption 516), so the cut
#  from a hero card into the mark is a rhyme instead of an 84 px jump.
X_COPY = 200.0
Y_KICKER = 432.0
Y_HERO = 564.0
Y_LABEL = 432.0
Y_CAPTION = 516.0
Y_RULE = 588.0
Y_READOUT = 636.0
RULE_W = 560.0                    # x 200 -> 760

FK_KICKER = ('mono_bold', 22, None)
FK_HERO = ('serif', 120, 520)
FK_LABEL = ('mono_bold', 32, None)
FK_CAPTION = ('ui', 46, 400)
FK_READOUT = ('mono', 32, None)

TR_KICKER = 5.2
TR_HERO = -1.2
TR_LABEL = 4.6
TR_CAPTION = 0.36

#  THE REVEAL ENVELOPE.  At 13 f with a 10 f stagger cap a 14-character line
#  gave every glyph a 3-frame fade — which is a typewriter, the one text
#  effect the brief calls cheap, and it collapsed the 17 px rise into a single
#  frame so the "authored" channel never rendered at all.  24 f with a 9 f
#  leading edge gives each glyph ~15 frames: a cascade with a leading edge,
#  and a rise you can actually see.
REVEAL = 24                       # type reveal envelope, frames
SPAN_CAP = 9.0 / REVEAL           # per-char stagger span cap, 9 f
STAG = 0.62 / REVEAL              # 0.62 f per character


def _p(f, at, dur=REVEAL):
    """Reveal progress. Frame `at` is the first visible frame; full at
    `at + dur - 1`."""
    return _clamp01((f - at + 1) / float(dur))


# --- the copy, verbatim (FILM §5) -------------------------------------
KICK_ONE = (('CHECK ONE', KICKER),)
HERO_ONE = (('Where you are.', TEXT),)
LBL_VERIFY = (('VERIFYING', TEXT),)
RO_CONFIRM = (('Confirming location…', MUTED),)
LBL_CLEAR = (('CLEARED', TEXT),)
CAP_CLEAR = (('Confirmed in-country.', TEXT2),)
# No fault clause, so no accent: the whole reading is MUTED.  scene_hold draws
# the identical string the identical way at f985 — the accent in
# `Tehran, IR — outside CA` falls on `outside` only, and there is no `outside`
# here to colour.  A green "inside" would invent a colour language the app
# does not use (FILM §2.6: GREEN is defined and never used).
RO_INSIDE = (('Toronto, CA — inside CA', MUTED),)


# =====================================================================
#  4.  THE MARK'S CHANNELS, FRAME BY FRAME
# =====================================================================
#  P is global and never resets (FILM §2.10): the mark is one continuous
#  machine for the whole 40 s, turning across cuts and across the 90-frame
#  type card at f90–f179 where it is not even drawn.

def _sweep_rot(f):
    """The verify sweep, 150 deg/s clockwise -> 2.400 s per revolution."""
    return (f / 30.0 * 150.0) % 360.0


def _blips_verify(f):
    """0.3 +/- 0.12, faint. design.md §2.4."""
    P = f / 30.0
    return [_clamp01(0.3 + 0.12 * math.sin(P * 2.2 + i)) for i in range(3)]


def _blips_clear(f):
    """0.8 +/- 0.2, alive.  Must be bit-identical to scene_wire's at f420."""
    P = f / 30.0
    return [_clamp01(0.8 + 0.2 * math.sin(P * 1.6 + i * 1.3)) for i in range(3)]


def _pulse(f, gain=1.0):
    """The `clear` pulse — one calm outward ring, born at the hub on f262.

    r 8 -> 28 units, width 3.  `gain` is the morph's own birth envelope: at
    k=0 the ring does not exist, so it emerges from the hub instead of popping
    into being at r=8, alpha 0.5.

    Two things are deliberate here and are shared verbatim with scene_wire:

    * the RATE is 30/91 turns per second, so exactly one cycle fits the
      91-frame gap between f329 and f420 and the film's structural match cut
      is bit-identical instead of merely nearly-so (it used to leave on an
      invisible pulse and return on a fully-lit one);
    * the alpha ramps UP over the first 15 % of the cycle.  Born at 0.5 it was
      a hard pop every 2.4 s — six of them, four inside the `HOLD · CONNECTION`
      beat, which is the one place in the film nothing may flash.
    """
    pr = ((f - PULSE_BORN) / 30.0 * PULSE_RATE) % 1.0
    a = max(0.0, 1.0 - pr) * _clamp01(pr / PULSE_FADE) * 0.5 * gain
    return (PULSE_R0 + pr * PULSE_DR, 3.0, TEXT, a)


def _spec_a1(f):
    """A1 — the mark makes itself.  Four channels open in sequence, each on
    its own curve, none of them linear, and only ever one leading edge."""
    # ring: TWO opposed 180 deg arcs, from 12 and 6 o'clock, closing on 3 and
    # 9.  A single 360 deg sweep spends its middle second as a white C-arc on
    # black — which is the indeterminate progress spinner every viewer has
    # seen ten thousand times, and the first 1.5 s of a promo is not a place
    # to be ambiguous.  Two arcs closing is never a spinner on any frame, and
    # two halves meeting is a stronger seat than an arc chasing its own tail.
    # Deliberately NOT starting at the 0 deg dash seam — when the ring later
    # breaks into dashes at f525 the break starts at 3 o'clock, somewhere the
    # eye has never been anchored.
    if f >= RING_AT + RING_DUR - 1:
        arc = None
    else:
        sweep = 180.0 * EASE_MOVE(_p(f, RING_AT, RING_DUR))
        arc = ((-90.0, sweep), (90.0, sweep))
    if f >= RINGW_AT + RINGW_DUR - 1:
        rw = 6.0
    else:
        rw = 6.0 * EASE_ENTER(_p(f, RINGW_AT, RINGW_DUR))

    # core: the one sanctioned overshoot in the film (+3.8 %), on a neutral
    # entrance, which is the single place craft §4.6 permits it.
    core = None
    if f >= CORE_AT:
        if f >= CORE_AT + CORE_DUR:
            cr = 4.5
        else:
            cr = 4.5 * ARRIVE((f - (CORE_AT - 1)) / 30.0)
        if cr > 0.02:
            core = ('fill', TEXT, cr)

    # blips: three contacts, 3 f apart, each on its own 13 f envelope.  A
    # GROUP (FILM §2.8) — one moving element with a leading edge.
    live = _blips_verify(f)
    blips = []
    for i in range(3):
        g = EASE_ENTER(_p(f, BLIP_AT[i])) if f >= BLIP_AT[i] else 0.0
        blips.append(live[i] * g)

    # sweep: the needle draws OUTWARD from the hub and the trail lights up
    # behind it.  FILM §4.1 specifies needle length 0->33 and wedge alpha
    # 0->0.16; the wedge radius is carried on the same eased length so the
    # trail grows out of the hub with the needle instead of hanging in space
    # at r=33 behind a stub.  It is the same channel, not a new one.
    sweep = None
    if f >= SWEEP_AT:
        kn = EASE_MOVE(_p(f, SWEEP_AT, SWEEP_DUR))
        ka = EASE_ENTER(_p(f, SWEEP_AT, SWEEP_DUR))
        sweep = (_sweep_rot(f), SWEEP_MAX * kn, SWEEP_MAX * kn, 0.20 * ka)

    return {'ring': (TEXT, None), 'ring_w': rw, 'arc': arc, 'sweep': sweep,
            'rings': [], 'blips': blips, 'core': core}


def _spec_verify(f):
    """A3 — `verify` at full value.  Neutral: Tower is not amber while it
    checks; it simply has not answered yet, and it is holding the request
    until it has."""
    return {'ring': (TEXT, None), 'ring_w': 6.0, 'arc': None,
            'sweep': (_sweep_rot(f), SWEEP_MAX, SWEEP_MAX, 0.20),
            'rings': [], 'blips': _blips_verify(f), 'core': ('fill', TEXT, 4.5)}


def _m1k(f):
    """Progress through MORPH M1, 15 f on SETTLE.  0 before f262, 1 from
    f276.  Driven in seconds because SETTLE is a real spring."""
    if f < M1_AT:
        return 0.0
    return _clamp01(SETTLE((f - (M1_AT - 1)) / 30.0))


def _spec_a4(f):
    """A4 — MORPH M1 `verify -> clear`, every channel interpolated.

    The ring does not change at all, and that is the point: the film's first
    state change is legible entirely in the sweep stopping and the scope
    starting to breathe.  Nothing flashes, nothing bounces, nothing turns
    green.
    """
    k = _m1k(f)
    if k <= 1e-6:
        return _spec_verify(f)
    if k >= 1.0 - 1e-6:
        return _spec_clear(f)

    # the needle retracts INTO the hub and the trail goes with it
    nlen = SWEEP_MAX * (1.0 - k)
    sweep = (_sweep_rot(f), nlen, nlen, 0.20 * (1.0 - k))

    # 0.30 -> 0.80: the scope stops looking and starts holding contacts.
    # Both formulas are evaluated at f and blended on k, so each end of the
    # morph is phase-exact and nothing jumps at either seam.
    bv, bc = _blips_verify(f), _blips_clear(f)
    blips = [_lerp(bv[i], bc[i], k) for i in range(3)]

    return {'ring': (TEXT, None), 'ring_w': 6.0, 'arc': None, 'sweep': sweep,
            'rings': [_pulse(f, gain=k)], 'blips': blips,
            'core': ('fill', TEXT, 4.5)}


def _spec_clear(f):
    """`clear` at full value.  THE MATCH-CUT SEAM — this is the pose the mark
    leaves on at f329 and returns on, bit-identical, at f420 in scene_wire."""
    return {'ring': (TEXT, None), 'ring_w': 6.0, 'arc': None, 'sweep': None,
            'rings': [_pulse(f)], 'blips': _blips_clear(f),
            'core': ('fill', TEXT, 4.5)}


# =====================================================================
#  5.  THE 1 px RULE — it draws on, it never fades on
# =====================================================================

_RULE_CACHE = {}


def _rule(dst, f, at, dur=16):
    """600 px of 1 px hairline arriving left-to-right in 0.53 s (craft §6.9:
    draw-on, not fade-in).  It is the only thing in the shot with an edge and
    it gives the copy column a floor."""
    if f < at:
        return
    frac = EASE_MOVE(_p(f, at, dur))
    if frac <= 0.0:
        return
    w = RULE_W * frac
    if w < 0.6:
        return
    key = round(w, 2)
    lay = _RULE_CACHE.get(key)
    if lay is None:
        n = int(RULE_W)
        lay = Image.new('RGBA', (n, 1), (0, 0, 0, 0))
        px = lay.load()
        soft = 60.0                      # 10 % of the run: no chopped tip
        for x in range(n):
            d = w - x
            if d <= 0:
                break
            a = 1.0 if d >= soft else d / soft
            px[x, 0] = (HAIRLINE[0], HAIRLINE[1], HAIRLINE[2],
                        int(round(255 * a)))
        if len(_RULE_CACHE) < 64:
            _RULE_CACHE[key] = lay
    dst.alpha_composite(lay, (int(X_COPY), int(Y_RULE)))


# =====================================================================
#  6.  THE SHOTS
# =====================================================================

def _shot_a1(dst, f):
    """A1 `open.mark` — f0 … f89.  Idea: the mark draws itself onto nothing.

    Zero words.  The film's first three seconds contain no language at all —
    the thing being introduced is a mark, not a sentence, and it arrives
    before its name does.  Columns 1–5, the entire left 56 % of the frame,
    are empty field for the whole shot; f0–f11 the whole frame is.
    """
    if f < RING_AT:
        return                            # 12 frames of pure #0C0C0E
    _blit_mark(dst, _spec_a1(f))


def _shot_a2(dst, f):
    """A2 `open.where` — f90 … f179.  Layout H, type only, zero accent.

    12 frames of completely empty frame, then one choreographed GROUP: the
    kicker, and the hero 3 f behind it — inside the reveal window, one leading
    edge (FILM §2.8).  18 frames of black at second 3 of a 40-second promo is
    the exact moment a viewer decides whether to keep watching; the reading
    floor gave `CHECK ONE` 17 frames of slack, so 6 of them were spent here.

    Columns 6–8 are deliberately empty: the mark's seat is left visibly vacant
    for 90 frames, which is what makes its return at f180 read as a return.
    """
    if f >= 102:
        _text(dst, X_COPY, Y_KICKER, KICK_ONE, FK_KICKER, tracking=TR_KICKER,
              rise=3.0, p=_p(f, 102), stagger=STAG, ease=EASE_ENTER,
              span_cap=SPAN_CAP)
    if f >= 105:
        # optical alignment on the flat left of `W`, not the advance origin
        hx = X_COPY - _lsb(FK_HERO, 'W')
        _text(dst, hx, Y_HERO, HERO_ONE, FK_HERO, tracking=TR_HERO,
              rise=17.0, p=_p(f, 105), stagger=STAG, ease=EASE_ENTER,
              span_cap=SPAN_CAP)


def _shot_a3(dst, f):
    """A3 `open.verify` — f180 … f254.  Layout M.

    The mark returns to the canonical circle with its phase untouched — the
    sweep is exactly where 6 seconds of turning put it.  The type disappeared
    in one frame and the mark reappeared in the same frame; nothing is ever
    half-there.

    The caption slot at baseline 516 stays deliberately empty here and fills
    in A4.  That empty line is a promise that something is coming.
    """
    _blit_mark(dst, _spec_verify(f))
    if f >= 186:
        _text(dst, X_COPY, Y_LABEL, LBL_VERIFY, FK_LABEL, tracking=TR_LABEL,
              rise=3.0, p=_p(f, 186), stagger=STAG, ease=EASE_ENTER,
              span_cap=SPAN_CAP)
    _rule(dst, f, 192)
    if f >= 198:
        _text(dst, X_COPY, Y_READOUT, RO_CONFIRM, FK_READOUT, rise=3.0,
              p=_p(f, 198), stagger=STAG, ease=EASE_ENTER, span_cap=SPAN_CAP)


def _shot_a4(dst, f):
    """A4 `open.clear` — f255 … f329.  No cut; continuous from A3.

    7 frames of dead stillness (anticipation, craft §6.1), then MORPH M1 at
    f262 — the film's first state change, and it is deliberately unexciting.
    An all-clear that celebrated itself would make every later hold read as an
    alarm.

    Both copy slots swap as RELAYs (FILM §2.8): the outgoing string vacates
    completely, then the incoming one starts.  `VERIFYING` clears on f269 and
    `CLEARED` starts on f270; the readout clears on f277 and the new one
    starts on f278.  Never a frame of overlap — two strings at partial opacity
    in one slot is a cross-fade, and this film contains none.
    """
    _blit_mark(dst, _spec_a4(f))
    _rule(dst, f, 192)

    # --- label slot: VERIFYING out, CLEARED in ------------------------
    if f <= 269:
        a = _fade_out(f, 262, 8, EASE_EXIT)
        if a > 0.004:
            _text(dst, X_COPY, Y_LABEL, LBL_VERIFY, FK_LABEL,
                  tracking=TR_LABEL, alpha=a)
    else:
        _text(dst, X_COPY, Y_LABEL, LBL_CLEAR, FK_LABEL, tracking=TR_LABEL,
              rise=3.0, p=_p(f, 270), stagger=STAG, ease=EASE_ENTER,
              span_cap=SPAN_CAP)

    # --- caption slot: empty in A3, fills here, 3 f behind the label ---
    if f >= 273:
        _text(dst, X_COPY, Y_CAPTION, CAP_CLEAR, FK_CAPTION,
              tracking=TR_CAPTION, rise=5.0, p=_p(f, 273), stagger=STAG,
              ease=EASE_ENTER, span_cap=SPAN_CAP)

    # --- readout slot: the product's own voice, real observed values ---
    if f <= 277:
        a = _fade_out(f, 270, 8, EASE_EXIT)
        if a > 0.004:
            _text(dst, X_COPY, Y_READOUT, RO_CONFIRM, FK_READOUT, alpha=a)
    else:
        _text(dst, X_COPY, Y_READOUT, RO_INSIDE, FK_READOUT, rise=3.0,
              p=_p(f, 278), stagger=STAG, ease=EASE_ENTER, span_cap=SPAN_CAP)


# =====================================================================
#  7.  THE SCENE CONTRACT
# =====================================================================

def draw(ctx) -> None:
    """Paint this scene's content onto ctx.img, in place."""
    f = int(ctx.f)
    if f < RANGE[0] or f > RANGE[1]:
        return

    im = ctx.img
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))

    if f < A2:
        _shot_a1(lay, f)
    elif f < A3:
        _shot_a2(lay, f)
    elif f < A4:
        _shot_a3(lay, f)
    else:
        _shot_a4(lay, f)

    if im.mode == 'RGBA':
        im.alpha_composite(lay)
    else:
        im.paste(lay, (0, 0), lay)
