"""scene_wire.py — Act B of the Tower film.

Frames 330 … 689 inclusive (360 frames, 11.000 s – 23.000 s).

    B1  wire.how    330 … 419   Layout H   "How the wire is."
    B2  wire.slow   420 … 509   Layout M   clear, SLOW LINK · STILL ALLOWED
    B3  wire.hold   510 … 614   Layout M   MORPH M2 clear -> holdNet
    B4  wire.off    615 … 689   Layout M   6 empty frames, then off

Everything here is a pure function of the absolute frame index. No clock, no
unseeded randomness, no neighbour-frame state. Frame N is byte-identical every
run.

Public surface is exactly:

    RANGE = (330, 689)
    def draw(ctx) -> None

`ctx` is the Ctx dataclass from brand.py: ctx.img (RGB 1920x1080, already
filled with INK), ctx.d, ctx.f (absolute frame), ctx.t, ctx.dur, ctx.k, ctx.sf.
Only ctx.img and ctx.f are load-bearing here — every frame number in FILM.md is
absolute, so this module drives off ctx.f and never off ctx.t.

brand.py / draw.py / ui.py did not exist when this module was written (they are
being authored in parallel).  Section 0 below therefore *prefers* the shared
helpers when they are importable and falls back to a local implementation that
is faithful, constant for constant, to notes/design.md §2 and FILM.md §2–§4.
The one thing that must stay bit-identical across modules is the radar mark at
f420 (the film's structural match cut with scene_open's f329); `_radar_tile()`
is the single seam where that swap happens.
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
W, H, FPS = 1920, 1080, 1200 // 40

RANGE = (330, 689)

# --------------------------------------------------------------- colour
INK = (0x0C, 0x0C, 0x0E)
HAIRLINE = (0x34, 0x34, 0x3A)
TEXT = (0xE7, 0xE6, 0xE2)
TEXT2 = (0x9A, 0x9A, 0x95)
MUTED = (0x8B, 0x8B, 0x86)
KICKER = (0x7C, 0x7C, 0x77)
AMBER = (0xE6, 0xA9, 0x3C)
RED = (0xE5, 0x48, 0x4D)


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


def _build_font(kind, size, weight=None, axis_size=None):
    """promo/overlays.py:font() verbatim — the axis order differs per face.

    `axis_size` lets the face be instantiated at a supersampled pixel size
    while its variation axes stay pinned to the *nominal* design size, so a
    3x raster is the same typeface, only better sampled.
    """
    size = int(round(size))
    a = int(round(axis_size if axis_size is not None else size))
    if kind == 'serif':
        f = ImageFont.truetype(_F_SERIF, size)
        try:                              # axes: [Optical Size, Weight, GRAD]
            f.set_variation_by_axes([max(12, min(256, a * 2)),
                                     weight or 520, 0])
        except Exception:
            pass
    elif kind == 'ui':
        f = ImageFont.truetype(_F_UI, size)
        try:                      # axes: [Width, Optical Size, GRAD, Weight]
            f.set_variation_by_axes([100, max(17, min(96, a)), 400,
                                     weight or 400])
        except Exception:
            pass
    elif kind == 'mono':
        f = ImageFont.truetype(_F_MONO, size)
    elif kind == 'mono_bold':
        f = ImageFont.truetype(_F_MONO_B, size)
    else:
        raise ValueError(kind)
    return f


def _font(kind, size, weight=None):
    """The metric font — advances, bearings, layout.  Shared when available."""
    if _shared_font is not None:
        try:
            return _shared_font(kind, size, weight)
        except Exception:
            pass
    key = (kind, int(round(size)), weight)
    f = _FONTS.get(key)
    if f is None:
        f = _FONTS[key] = _build_font(kind, size, weight)
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


def _fade_in(f, at, dur, ease):
    """0 before `at`, 1 from `at + dur - 1`. Frame `at` is the first visible."""
    return ease((f - at + 1) / float(dur))


def _fade_out(f, at, dur, ease):
    """1 before `at`, reaching 0 on `at + dur - 1`.  `at` is the first frame
    that is visibly dimmer; the slot is empty from `at + dur`."""
    return 1.0 - ease((f - at + 1) / float(dur)) if f >= at else 1.0


# =====================================================================
#  1.  TEXT — sub-pixel, per-character, tracked
# =====================================================================
#  Pillow snaps ImageDraw.text() to integer pixels, which judders a 17 px
#  rise into 17 visible steps and instantly reads cheap (Amendment B).  Every
#  glyph here is rasterised once into a cached alpha mask and stamped at a
#  float position; the fractional part is applied as a bilinear affine shift
#  of the mask alone, so the colour never fringes.

_GLYPH = {}
_SS_TEXT = 3


def _glyph_mask(fkey, ch):
    """One cached alpha mask per (face, size, weight, character).

    Rasterised at 3x and LANCZOS-downsampled.  This is not a nicety: New York
    Display at opsz 240 draws the `H` crossbar as a 0.75 px hairline, and a
    1x Pillow raster drops it entirely — the hero line `How the wire is.`
    literally rendered as `Iow the wire is.` before this.  Supersampling keeps
    the hairline as a real, light stroke, which is what the typeface actually
    looks like.
    """
    key = (fkey, ch)
    hit = _GLYPH.get(key)
    if hit is not None:
        return hit
    kind, size, weight = fkey
    f = _font(*fkey)
    pad = max(6, int(size * 0.40))
    adv = f.getlength(ch)
    w = max(2, int(math.ceil(adv)) + 2 * pad)
    asc = int(size * 1.45)
    desc = int(size * 0.65)
    h = max(2, asc + desc + 2 * pad)

    s = _SS_TEXT
    fs = _build_font(kind, size * s, weight, axis_size=size)
    big = Image.new('L', (w * s, h * s), 0)
    ImageDraw.Draw(big).text((pad * s, (pad + asc) * s), ch, font=fs,
                             fill=255, anchor='ls')
    im = big.resize((w, h), Image.LANCZOS)

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


def _run_w(fkey, s, tracking):
    if not s:
        return 0.0
    f = _font(*fkey)
    return sum(f.getlength(c) for c in s) + tracking * (len(s) - 1)


def _lsb(fkey, ch):
    """Left side bearing — for optical alignment on a flat-sided glyph."""
    try:
        return _font(*fkey).getbbox(ch)[0]
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
#  Draw order is design.md §2.1 — ring, motion ornament, blips, core.

#  brand.py is the AUTHORITY for the mark's geometry; the literals below are
#  only the fallback for running this module standalone. Do not edit them here
#  — edit brand.py, or the four scenes will disagree about the icon.
MARK_C = _shared(_B, 'MARK_C') or (1350.0, 540.0)   # canonical circle, FILM §2.3
MARK_BOX = _shared(_B, 'MARK_BOX') or 520           # 5.2 px per Glyph unit
_SS = 4

#  Shared with scene_open, constant for constant — see that module's docstring
#  and brand.py.  The rate puts exactly one pulse cycle in the 91-frame gap
#  between f329 and f420, which is what makes that cut an actual match cut.
PULSE_RATE = 30.0 / 91.0
PULSE_R0, PULSE_DR = 8.0, 20.0
PULSE_FADE = 0.15

#  THE DASH.  The ring stroke is 6.0 units wide; (5, 6) drew each dash 21 px
#  long by 25 px thick at hero scale.  A dash shorter than the stroke is a
#  square block, and 24 of them around a circle is a sunburst — a roulette
#  wheel, an aperture, a loading crown.  It made the film's three serious
#  states read as a completely different symbol from its two calm ones, which
#  destroyed the C2 comparison the whole thesis rests on.  Below, every dash
#  is twice the stroke width and the period divides the circumference into a
#  whole number of dashes, so the pattern closes with no seam.
#  Authority: brand.py. Changing a dash here and not there is exactly how the
#  `holdNet` icon starts looking like a different symbol between two acts.
DASH_HOLDNET = _shared(_B, 'DASH_HOLDNET') or (13.82, 6.91)   # 10 on r = 33
DASH_OFF = _shared(_B, 'DASH_OFF') or (15.36, 7.68)           #  9 dashes

_TILE_CACHE = {}

# The one seam where this module would hand the mark over to ui.py.  It is
# resolved ONCE, at import, against a probe spec — never per frame — so the
# whole act is drawn by one implementation and can never mix two.  Mixing is
# the only way f420's match cut with scene_open's f329 could break.
_shared_radar = _shared(_U, 'radar_tile')
if _shared_radar is not None:
    try:
        _probe = _shared_radar(8, {'ring': (TEXT, None), 'rings': [],
                                   'blips': (0.0, 0.0, 0.0),
                                   'core': ('fill', TEXT)})
        if not (isinstance(_probe, Image.Image) and _probe.size == (8, 8)):
            _shared_radar = None
    except Exception:
        _shared_radar = None


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
    a = phase_deg
    end = phase_deg + 360.0
    while a < end:
        d.arc(box, a, min(a + on_d, end), fill=ink, width=wi)
        a += on_d + off_d


def _dashed_seg(d, p0, p1, colour, w, dash, alpha, cap=True):
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    ln = math.hypot(dx, dy)
    if ln < 1 or alpha <= 0.004:
        return
    ux, uy = dx / ln, dy / ln
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
            if cap:
                rr = w / 2.0
                d.ellipse((ax - rr, ay - rr, ax + rr, ay + rr), fill=ink)
                d.ellipse((bx - rr, by - rr, bx + rr, by + rr), fill=ink)
        s += on + off


BLIPS = ((64, 41), (38, 58), (58, 66))


def _radar_tile(size, spec):
    """Render the mark into an RGBA tile of `size` px.

    `spec` is the resolved channel state — not a state *name* — so a morph is
    expressed as interpolated channels rather than a cross-fade of two
    finished pictures (Amendment B / FILM §3).

        ring   (colour, dash|None)     dash in unit lengths
        rings  [(r, w, colour, alpha)] the pulse / pings, unit lengths
        blips  [a0, a1, a2]
        core   ('fill', colour) | ('hollow', colour)
    """
    if _shared_radar is not None:
        return _shared_radar(size, spec)
    key = (size,
           spec['ring'][0], spec['ring'][1],
           tuple((round(r[0], 4), round(r[1], 4), r[2], round(r[3], 4),
                  r[4] if len(r) > 4 else None) for r in spec['rings']),
           tuple(round(a, 4) for a in spec['blips']),
           spec['core'])
    hit = _TILE_CACHE.get(key)
    if hit is not None:
        return hit

    n = size * _SS
    im = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    #  'RGBA' or an ornament at alpha 0.03 crossing the opaque ring REPLACES
    #  those pixels and erases a band out of the stroke.  See scene_open.
    d = ImageDraw.Draw(im, 'RGBA')
    u = n / 100.0
    hx = hy = 50.0 * u

    # 1 — the outer ring.  Colour and dash are the fastest-read channel at any
    #     size, so they morph first (design.md §2.12).
    rc, rd = spec['ring']
    _ring(d, hx, hy, 33.0 * u, 6.0 * u, rc, 1.0,
          (rd[0] * u, rd[1] * u) if rd else None, 0.0)

    # 2 — the motion ornament (clear pulse / holdNet pings), under the blips.
    #     A ping carries an ARC list.  Two closed concentric rings inside a
    #     dashed ring is a bullseye — a reticle, which craft §8.9 bans outright
    #     and which is the signature of the state the film shows most.  Two
    #     opposed 130 deg wavefronts marching outward read as sonar and cannot
    #     read as a target on any single frame.
    for ring in spec['rings']:
        r, w, col, a = ring[0], ring[1], ring[2], ring[3]
        arcs = ring[4] if len(ring) > 4 else None
        if arcs:
            ro = r * u + w * u / 2.0
            box = (hx - ro, hy - ro, hx + ro, hy + ro)
            if a > 0.004 and r > 0:
                for a0, sweep in arcs:
                    d.arc(box, a0, a0 + sweep, fill=_rgba(col, a),
                          width=max(1, int(round(w * u))))
        else:
            _ring(d, hx, hy, r * u, w * u, col, a)

    # 3 — the contacts.  Never amber, never red: they are the neutral.
    for i, (bx, by) in enumerate(BLIPS):
        a = spec['blips'][i]
        if a > 0.001:
            rr = 3.6 * u
            d.ellipse((bx * u - rr, by * u - rr, bx * u + rr, by * u + rr),
                      fill=_rgba(TEXT, min(1.0, a)))

    # 4 — the core.  Hollow only in `off`: the centre is empty, nothing is
    #     holding this.  Never fill it.
    mode, col = spec['core']
    if mode == 'hollow':
        _ring(d, hx, hy, 5.5 * u, 4.0 * u, col, 1.0)
    else:
        rr = 4.5 * u
        d.ellipse((hx - rr, hy - rr, hx + rr, hy + rr), fill=_rgba(col, 1.0))

    out = im.resize((size, size), Image.LANCZOS)
    if len(_TILE_CACHE) < 96:
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
#  3.  ACT B TIMELINE
# =====================================================================

B1, B2, B3, B4, B_END = 330, 420, 510, 615, 690

M2_AT, M2_DUR = 525, 15           # clear -> holdNet
PING1_AT = 534                    # the sonar doubles, one beat after.
#  At 540 the blips had already gone to 0 and ping #1 had not arrived, so for
#  seven frames the mark was a hollow ring with one dot in it.
OFF_AT = 621                      # the `off` mark fades up
PULSE_BORN = 262                  # A4's clear pulse; phase never resets

# --- Layout M slots (FILM §2.4) --------------------------------------
#  One type tier up and in from x=160 — see scene_open for why.  Layout H
#  (B1) now sits on Layout M's spine so the cut at f420 is a rhyme.
X_COPY = 200
Y_KICKER = 432
Y_HERO = 564
Y_LABEL = 432
Y_CAPTION = 516
Y_RULE = 588
Y_READOUT = 636
RULE_X0 = 200
RULE_X1 = 760

FK_KICKER = ('mono_bold', 22, None)
FK_HERO = ('serif', 120, 520)
FK_LABEL = ('mono_bold', 32, None)
FK_CAPTION = ('ui', 46, 400)
FK_READOUT = ('mono', 32, None)

TR_KICKER = 5.2
TR_HERO = -1.2
TR_LABEL = 4.6
TR_CAPTION = 0.36

REVEAL = 24                       # type reveal envelope, frames
SPAN_CAP = 9.0 / REVEAL           # per-char stagger span cap, 9 f
STAG = 0.62 / REVEAL              # 0.62 f per character


def _m2k(f):
    """Progress through MORPH M2, 15 f on SETTLE.  0 before f525, 1 by f539.
    Driven in seconds because SETTLE is a real spring.

    The clamp is load-bearing, not defensive: SETTLE peaks at +0.63 % around
    f535, and docs/DESIGN.md's motion law is that a hold never overshoots.
    Clamping keeps the spring's slow-in/slow-out shape while removing the
    bounce, so the amber arrives and stops.
    """
    if f < M2_AT:
        return 0.0
    return _clamp01(SETTLE((f - (M2_AT - 1)) / 30.0))


def _ping_phase(f):
    """Continuous phase, in turns, of the ring that is the `clear` pulse
    before f525 and holdNet ping #0 after it.

    The rate morphs 30/91 -> 0.7 Hz across M2.  Lerping the *rate* inside a
    (rate x time) product would jump the phase, so the rate is integrated
    frame by frame instead — still a pure function of f, still deterministic,
    at most 15 iterations.
    """
    if f <= M2_AT - 1:
        return PULSE_RATE * (f - PULSE_BORN) / 30.0
    ph = PULSE_RATE * ((M2_AT - 1) - PULSE_BORN) / 30.0
    for g in range(M2_AT, min(f, PING1_AT) + 1):
        ph += _lerp(PULSE_RATE, 0.70, _m2k(g)) / 30.0
    if f > PING1_AT:
        ph += 0.70 * (f - PING1_AT) / 30.0
    return ph


def _spec_clear_to_holdnet(f):
    """The B-act mark: `clear` held, then M2 into `holdNet`.

    Every channel is interpolated; nothing cross-fades.  Only two of the five
    ring/core channels will later distinguish this from holdGeo (C1), and both
    are absences — so get these right or the film's thesis has no geometry.
    """
    k = _m2k(f)
    P = f / 30.0
    col = _mix(TEXT, AMBER, k)

    # ring: solid -> DASH_HOLDNET.  Interpolated on the SEGMENT COUNT, which
    # is the quantity the eye actually reads ("how many dashes are there"):
    # 1 -> 10 passes through 3, 5, 7 and every frame is legibly on its way
    # somewhere.  Linear in dash *length* is hyperbolic in the count — it
    # stays visually solid until k > 0.85 and then snaps.
    if k <= 1e-4:
        dash = None
    else:
        nseg = _lerp(1.0, 10.0, k)
        duty = _lerp(1.0, DASH_HOLDNET[0] / sum(DASH_HOLDNET), k)
        per = 207.345 / nseg
        dash = (per * duty, per * (1.0 - duty))
        if dash[1] <= 1e-4:
            dash = None

    rings = []
    # ping #0 — the clear pulse, re-tuned.  Same ring, new range and weight.
    pr = _ping_phase(f) % 1.0
    r0 = _lerp(PULSE_R0, 7.0, k) + pr * _lerp(PULSE_DR, 19.0, k)
    w0 = _lerp(3.0, 3.0, k)
    #  The alpha falls with the SQUARE of the radius, not linearly.  Linear
    #  put both wavefronts at 0.5 whenever pr = 0.5 — two equal concentric
    #  arcs, which is the dartboard the sonar is meant not to be.  Squared,
    #  one wavefront is always three to ten times the other, so the eye reads
    #  a leading edge travelling outward and a faint echo behind it.
    a0 = _lerp(max(0.0, 1.0 - pr) * _clamp01(pr / PULSE_FADE) * 0.5,
               max(0.0, 1.0 - pr) ** 0.55 * _clamp01(pr / 0.10) * 0.92, k)
    rings.append((r0, w0, col, a0, _PING_ARCS if k > 0.45 else None))
    # ping #1 — born a beat after the state lands, half a period out of phase.
    if f >= PING1_AT:
        a1g = EASE_ENTER((f - PING1_AT + 1) / 15.0)
        pr1 = (_ping_phase(f) + 0.5) % 1.0
        rings.append((7.0 + pr1 * 19.0, 3.0, AMBER,
                      max(0.0, 1.0 - pr1) ** 0.55
                      * _clamp01(pr1 / 0.10) * 0.42 * a1g, _PING_ARCS))

    # the scope loses its contacts.  Nothing is getting through.
    ba = []
    for i in range(3):
        ba.append(_clamp01(0.8 + 0.2 * math.sin(P * 1.6 + i * 1.3)) * (1.0 - k))

    return {'ring': (col, dash), 'rings': rings, 'blips': ba,
            'core': ('fill', col)}


#  Two opposed 130 deg arcs, centred on 12 and 6 o'clock, leaving the ring
#  open at 3 and 9.  See the note in `_radar_tile`.
_PING_ARCS = ((205.0, 130.0), (25.0, 130.0))


def _spec_off():
    """`off` — unguarded.  Dead still: P appears in no expression here."""
    return {'ring': (RED, DASH_OFF), 'rings': [],
            'blips': (0.22, 0.22, 0.22), 'core': ('hollow', RED)}


# --- the copy, verbatim (FILM §5) ------------------------------------
LBL_SLOW = (('SLOW LINK', AMBER), (' · STILL ALLOWED', TEXT))
RO_NET = (('net ', MUTED), ('82', TEXT), (' ms ', MUTED), ('· ', MUTED),
          ('api ', MUTED), ('273', TEXT), (' ms', MUTED))
LBL_HOLD = (('HOLD · CONNECTION', AMBER),)
CAP_HOLD = (('No usable path.', TEXT2),)
RO_DOWN = (('internet down', AMBER),)
LBL_OFF = (('UNGUARDED', RED),)
CAP_OFF = (('Claude connects directly.', TEXT2),)


# =====================================================================
#  4.  THE SHOTS
# =====================================================================

def _shot_b1(dst, f):
    """B1 `wire.how` — f330 … f419.  Layout H, type only, zero accent.

    6 frames of empty field (one third of A2's 18 — the second card arrives
    faster because the viewer already knows the form), then one choreographed
    GROUP: kicker at f336, hero 3 f behind it.  Static from f349.
    """
    if f < 336:
        return
    p = _clamp01((f - 336 + 1) / float(REVEAL))
    _text(dst, X_COPY, Y_KICKER, (('CHECK TWO', KICKER),), FK_KICKER,
          tracking=TR_KICKER, rise=3.0, p=p, stagger=STAG,
          ease=EASE_ENTER, span_cap=SPAN_CAP)

    if f < 339:
        return
    ph = _clamp01((f - 339 + 1) / float(REVEAL))
    # optical alignment on the flat left of `H`, not the advance origin
    hx = X_COPY - _lsb(FK_HERO, 'H')
    _text(dst, hx, Y_HERO, (('How the wire is.', TEXT),), FK_HERO,
          tracking=TR_HERO, rise=17.0, p=ph, stagger=STAG,
          ease=EASE_ENTER, span_cap=SPAN_CAP)


def _rule(dst, f, at):
    """The hairline under the copy column, x 200 -> 900.  It DRAWS ON, left to right,
    16 f EASE_MOVE — it never fades on."""
    if f < at:
        return
    frac = EASE_MOVE((f - at + 1) / 16.0)
    if frac <= 0.0:
        return
    n = int(RULE_X1 - RULE_X0)
    w = n * frac
    if w < 1.0:
        return
    # soft leading edge, 10 % of the run, so the tip is not a chopped pixel
    soft = max(1.0, 0.1 * n)
    lay = Image.new('RGBA', (n, 1), (0, 0, 0, 0))
    px = lay.load()
    ink = _rgba(HAIRLINE, 1.0)
    for x in range(n):
        d = w - x
        if d <= 0:
            break
        a = 1.0 if d >= soft else d / soft
        px[x, 0] = (ink[0], ink[1], ink[2], int(round(255 * a)))
    dst.alpha_composite(lay, (X_COPY, Y_RULE))


def _shot_b2(dst, f):
    """B2 `wire.slow` — f420 … f509.  The film's structural match cut: the
    mark returns to the exact geometry it left at f329, in the exact state,
    with P never having reset.

    The mark stays NEUTRAL.  A degraded link is high-latency but reachable and
    should_block() does not fire on it; an amber radar here would be a lie.
    """
    _blit_mark(dst, _spec_clear_to_holdnet(f))
    _rule(dst, f, 426)
    if f >= 430:
        p = _clamp01((f - 430 + 1) / float(REVEAL))
        _text(dst, X_COPY, Y_LABEL, LBL_SLOW, FK_LABEL, tracking=TR_LABEL,
              rise=3.0, p=p, stagger=STAG, ease=EASE_ENTER,
              span_cap=SPAN_CAP)
    if f >= 450:
        p = _clamp01((f - 450 + 1) / float(REVEAL))
        _text(dst, X_COPY, Y_READOUT, RO_NET, FK_READOUT, rise=3.0, p=p,
              stagger=STAG, ease=EASE_ENTER, span_cap=SPAN_CAP)


def _shot_b3(dst, f):
    """B3 `wire.hold` — f510 … f614.  No cut; continuous from B2.

    15 frames of dead stillness, then MORPH M2.  Every copy slot is fully
    vacated before it is refilled (a RELAY, never a cross-fade), and every
    hold element enters opacity-only on EASE_SOBER — a hold is not celebrated
    and it never bounces.
    """
    _blit_mark(dst, _spec_clear_to_holdnet(f))
    _rule(dst, f, 426)

    # outgoing — the neutral verdict leaves before the amber one arrives
    #  Both copy slots vacate BEFORE the ring breaks, not across it.
    #  EASE_EXIT is deliberately back-loaded — an outgoing string holds its
    #  weight and then goes, rather than lingering as a ghost — so starting it
    #  on f525 left `SLOW LINK · STILL ALLOWED` and `net 82 ms · api 273 ms`
    #  at ~88 % on the frames where the ring is visibly breaking into a hold.
    #  The internet is measurably fine beside a mark that is about to say
    #  `internet down`.  Three frames earlier and the slot is empty before the
    #  contradiction can exist, which also makes the break itself the only
    #  thing moving on f525.
    if f <= 529:
        a = _fade_out(f, 522, 8, EASE_EXIT)
        if a > 0.004:
            _text(dst, X_COPY, Y_LABEL, LBL_SLOW, FK_LABEL,
                  tracking=TR_LABEL, alpha=a)
    if f <= 531:
        #  Out two frames behind the label — a GROUP with a leading edge, not
        #  two things moving on the same frame (Amendment B).
        a = _fade_out(f, 524, 8, EASE_EXIT)
        if a > 0.004:
            _text(dst, X_COPY, Y_READOUT, RO_NET, FK_READOUT, alpha=a)

    # incoming — sober, opacity only, staggered 6 f apart
    if f >= 540:
        _text(dst, X_COPY, Y_LABEL, LBL_HOLD, FK_LABEL, tracking=TR_LABEL,
              alpha=_clamp01(_fade_in(f, 540, 8, EASE_SOBER)))
    if f >= 546:
        _text(dst, X_COPY, Y_CAPTION, CAP_HOLD, FK_CAPTION,
              tracking=TR_CAPTION,
              alpha=_clamp01(_fade_in(f, 546, 8, EASE_SOBER)))
    if f >= 552:
        _text(dst, X_COPY, Y_READOUT, RO_DOWN, FK_READOUT,
              alpha=_clamp01(_fade_in(f, 552, 8, EASE_SOBER)))


def _shot_b4(dst, f):
    """B4 `wire.off` — f615 … f689.  The argument's control case.

    6 frames of completely empty field — the film's only gap — then the mark
    simply IS there: 8 f EASE_SOBER on opacity alone.  No draw-on, no scale,
    no settle.  From f635 nothing moves at all.  No rule, no readout: with the
    guard off there is nothing being measured.
    """
    if f < OFF_AT:
        return
    a = _clamp01(_fade_in(f, OFF_AT, 8, EASE_SOBER))
    _blit_mark(dst, _spec_off(), alpha=a)
    if f >= 624:
        _text(dst, X_COPY, Y_LABEL, LBL_OFF, FK_LABEL, tracking=TR_LABEL,
              alpha=_clamp01(_fade_in(f, 624, 8, EASE_SOBER)))
    if f >= 627:
        _text(dst, X_COPY, Y_CAPTION, CAP_OFF, FK_CAPTION,
              tracking=TR_CAPTION,
              alpha=_clamp01(_fade_in(f, 627, 8, EASE_SOBER)))


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

    if f < B2:
        _shot_b1(lay, f)
    elif f < B3:
        _shot_b2(lay, f)
    elif f < B4:
        _shot_b3(lay, f)
    else:
        _shot_b4(lay, f)

    if im.mode == 'RGBA':
        im.alpha_composite(lay)
    else:
        im.paste(lay, (0, 0), lay)
