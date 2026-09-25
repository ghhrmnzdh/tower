"""brand.py — the shared surface for the Tower film.

Colours, font loading, easing tokens, the layout grid, and the `Ctx` dataclass
that every scene module's `draw(ctx)` receives.

AUTHORITY.  The values here are lifted from, in order of precedence:
  · promo/analysis/brand.json          (the brand's own colour table)
  · src/Glyph.swift, docs/DESIGN.md    (the marks and the motion law)
  · promo/film/FILM.md §2              (the locked shared visual system)

A NOTE ON WHY THIS FILE IS SMALL, AND ON `font`.
The four scene modules were authored in parallel, before this file existed, and
each one carries a faithful *local* copy of the primitives it needs, guarded by
an adapter that prefers a shared symbol when one is importable:

    EASE_ENTER = _shared(_B, 'EASE_ENTER') or _bezier(0.16, 1.00, 0.30, 1.00)

So anything exported from here silently *replaces* a scene's local copy. That is
fine for the easing tokens and the palette — they are exported below and are
constant-for-constant identical to every scene's fallback, so the override is a
no-op by construction and the film gains a single point of truth.

It is NOT fine for the font loader. The variable-axis order differs per face and
the scenes do not agree on the signature (`scene_hold` decouples the optical-size
axis from the render size so a run can be rasterised at 3x without changing its
design; the other three do not). Exporting `font` from here would silently
re-weight one act's type. The loader below is therefore called `load_font`, which
no scene probes for, and each scene keeps its own. Same reason there is no
`ui.radar_tile`: `scene_wire` probes for one and would hand its mark over to it,
which would put a *different implementation* on the two halves of the f329/f420
match cut. The scenes own their marks. See make.py's module docstring.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# ══════════════════════════════════════════════════════════════════════════
#  1.  CANVAS
# ══════════════════════════════════════════════════════════════════════════

W, H, FPS, TOTAL = 1920, 1080, 30, 1200
DURATION = TOTAL / FPS                      # 40.000 s, exactly

# ══════════════════════════════════════════════════════════════════════════
#  2.  COLOUR — FILM.md §2.6, analysis/brand.json
# ══════════════════════════════════════════════════════════════════════════

INK      = (0x0C, 0x0C, 0x0E)     # the field. every frame, flat. never #000000
SURFACE  = (0x14, 0x14, 0x16)     # a raised card
HAIRLINE = (0x34, 0x34, 0x3A)     # the only rule weight.  #242426 sat at
                                  # luma 36 against a field whose grain peaked at
                                  # 25 — a 1 px line at delta-11 reads as an encode
                                  # artefact, not as a rule.
TEXT     = (0xE7, 0xE6, 0xE2)
TEXT2    = (0x9A, 0x9A, 0x95)
MUTED    = (0x8B, 0x8B, 0x86)
KICKER   = (0x7C, 0x7C, 0x77)      # was #6E6E6A: 2.6:1 on ink, a grey smear
                                  # on a phone.  3.4:1 — still an eyebrow.

GREEN    = (0x30, 0xD1, 0x58)     # pass.  DEFINED, DELIBERATELY NEVER DRAWN —
                                  # the passing radar is neutral, not green
                                  # (FILM §2.6). Kept so the table is complete.
AMBER    = (0xE6, 0xA9, 0x3C)     # hold / warn.  off-country is AMBER, not red
RED      = (0xE5, 0x48, 0x4D)     # danger — `off`, and only `off`

#: The five radar states, in the order src/Glyph.swift declares them, with the
#: accent each one is allowed to use. `clear` and `verify` are neutral.
RADAR_STATES = ('clear', 'verify', 'holdNet', 'holdGeo', 'off')
STATE_ACCENT = {'clear': None, 'verify': None,
                'holdNet': AMBER, 'holdGeo': AMBER, 'off': RED}

# ── THE MARK'S SHARED GEOMETRY ────────────────────────────────────────────
#  Every scene carries its own copy of these; they are stated once here so a
#  future edit has one place to look. Units are Glyph.swift's 0…100 box.
#
#  DASH LENGTHS.  The ring stroke is 6.0 units wide.  The original (5, 6)
#  therefore drew each "dash" 21 px long by 25 px thick at hero scale — a
#  square block, and 24 of them around a circle is a sunburst, not a broken
#  ring.  A dash must be several times longer than the stroke is wide before
#  the eye reads "this ring has opened".  Every period below divides the
#  circumference into a whole number of dashes so the pattern closes with no
#  seam.
RING_CIRC = 2.0 * math.pi * 33.0                # 207.345 — "solid", as a dash
DASH_HOLDNET = (13.82, 6.91)      # 10 dashes, duty 2/3
DASH_OFF     = (15.36, 7.68)      #  9 dashes, duty 2/3
DASH_FENCE   = (7.854, 3.927)     #  8 dashes on the r = 15 fence

#  THE `clear` PULSE.  0.42 turns/s left f329 and f420 — the film's structural
#  match cut — on completely different phases.  30/91 puts exactly one cycle in
#  the 91-frame gap, so the cut is bit-identical by construction.  The range
#  stops at r 28 so the pulse dissolves *before* the ring stroke (r 30…36)
#  instead of drawing a second hairline inside it.
PULSE_RATE = 30.0 / 91.0          # turns per second  (0.32967…)
PULSE_R0, PULSE_DR = 8.0, 20.0
PULSE_BIRTH_FADE = 0.15           # fraction of a cycle spent fading up: a ring
                                  # born at full alpha is a pop, six times over

#  THE off-COUNTRY CONTACT.  It used to sit 28.4 units out with a halo reaching
#  42.4 — welded across a ring whose stroke starts at 30.  Pulled in to 21.0
#  with the halo capped at 8.0, the whole geo group lives inside the ring and
#  the mark keeps its silhouette.  Closest approach is 21.0 − 5.0 = 16.0
#  against a fence at 15: it still never gets in.
GEO_CONTACT = (66.5, 37.0)        # d = 21.0 from the hub at (50, 50)
GEO_LUNGE = 5.0


def mix(a, b, k):
    """Linear blend of two RGB tuples. k is clamped to 0..1."""
    k = 0.0 if k < 0.0 else (1.0 if k > 1.0 else k)
    return (int(round(a[0] + (b[0] - a[0]) * k)),
            int(round(a[1] + (b[1] - a[1]) * k)),
            int(round(a[2] + (b[2] - a[2]) * k)))


def rgba(c, a=1.0):
    """RGB tuple + float alpha -> RGBA tuple."""
    v = int(round(a * 255))
    return (c[0], c[1], c[2], 0 if v < 0 else (255 if v > 255 else v))


# ══════════════════════════════════════════════════════════════════════════
#  3.  GRID — FILM.md §2.2, §2.3
# ══════════════════════════════════════════════════════════════════════════

MARGIN = 160                      # outer margin, all four sides
SAFE_RING = 96                    # nothing but field inside this border ring
COL = 12                          # 12-column grid inside the margins
GUTTER = 40

#: The spine of the film. Ten of the fourteen shots hold the mark here, so
#: every cut between them is a match cut and only the state changes.
MARK_C = (1350.0, 540.0)
MARK_BOX = 520                    # px across, = 5.2 px per Glyph.swift unit.
#  420 drew a 302 px object against a 476 px dead right margin: the loudest
#  thing on screen carried none of the meaning and the frame read mis-centred.
#  520 draws 374 px and lands the right margin at 383 against a 200 px left.

#: Layout H — a hero line alone on the field. Layout M — the mark on its circle
#: with a label column to its left. FILM.md §2.4: copy and UI never share a slot.
LAYOUT_H_BASELINE = 600
LAYOUT_M_COL_X = 200              # left edge of the label column
LAYOUT_M_COL_W = 760              # ends at 1010; the mark's box starts at 1080


def col_x(i: int) -> float:
    """Left edge of grid column i (0-based)."""
    w = (W - 2 * MARGIN - (COL - 1) * GUTTER) / COL
    return MARGIN + i * (w + GUTTER)


# ══════════════════════════════════════════════════════════════════════════
#  4.  TYPE — FILM.md §2.5. These are the only sizes the film has.
# ══════════════════════════════════════════════════════════════════════════

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
F_SERIF  = '/System/Library/Fonts/NewYork.ttf'
F_UI     = '/System/Library/Fonts/SFNS.ttf'
F_MONO   = os.path.join(_REPO, 'src', 'Fonts', 'JetBrainsMono-Medium.ttf')
F_MONO_B = os.path.join(_REPO, 'src', 'Fonts', 'JetBrainsMono-Bold.ttf')

SIZE = {
    'hero':    120,   # the three chapter lines
    'big':     160,   # C3's `503`
    'label':    32,   # the state labels
    'read':     32,   # readouts
    'kicker':   22,
    'card':     64,   # D2's wordmark
}

_FONTS: dict = {}


def load_font(kind: str, size: float, weight: Optional[int] = None):
    """promo/overlays.py:font() — the axis ORDER differs per face and getting it
    wrong silently produces the wrong weight, so each face is handled by name.

    Named `load_font`, not `font`, on purpose — see this module's docstring.
    """
    size = int(round(size))
    key = (kind, size, weight)
    f = _FONTS.get(key)
    if f is not None:
        return f
    if kind == 'serif':
        f = ImageFont.truetype(F_SERIF, size)
        try:                              # axes: [Optical Size, Weight, GRAD]
            f.set_variation_by_axes([max(12, min(256, size * 2)),
                                     weight or 520, 0])
        except Exception:
            pass
    elif kind == 'ui':
        f = ImageFont.truetype(F_UI, size)
        try:                      # axes: [Width, Optical Size, GRAD, Weight]
            f.set_variation_by_axes([100, max(17, min(96, size)), 400,
                                     weight or 400])
        except Exception:
            pass
    elif kind == 'mono_b':
        f = ImageFont.truetype(F_MONO_B, size)
    else:
        f = ImageFont.truetype(F_MONO, size)
    _FONTS[key] = f
    return f


# ══════════════════════════════════════════════════════════════════════════
#  5.  EASING — FILM.md §2.7. Nothing in this film is linear, ever.
# ══════════════════════════════════════════════════════════════════════════

def clamp01(x):
    return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)


def lerp(a, b, k):
    return a + (b - a) * k


def bezier(x1, y1, x2, y2, eps=1e-6):
    """cubic-bezier(x1,y1,x2,y2), Newton, 8 iterations, seeded from t = x."""
    def bx(u):
        return 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u * u * x2 + u ** 3

    def by(u):
        return 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u * u * y2 + u ** 3

    def dbx(u):
        return (3 * (1 - u) ** 2 * x1 + 6 * (1 - u) * u * (x2 - x1)
                + 3 * u * u * (1 - x2))

    def f(x):
        x = clamp01(x)
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


def spring(response, zeta):
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


EASE_ENTER = bezier(0.16, 1.00, 0.30, 1.00)   # type and marks arriving
EASE_MOVE  = bezier(0.65, 0.00, 0.35, 1.00)   # something travelling
EASE_SOBER = bezier(0.33, 1.00, 0.68, 1.00)   # every hold / amber / red move.
                                              # DESIGN.md motion law: failure
                                              # never bounces. Ease-out only.
EASE_EXIT  = bezier(0.32, 0.00, 0.67, 0.00)   # leaving
EASE_SNAP  = bezier(0.22, 1.00, 0.36, 1.00)   # D1's fast run

SETTLE = spring(0.45, 0.85)                   # mechanical settle, no overshoot
ARRIVE = spring(0.55, 0.72)                   # a little life on a *good* state

#: Reduce Motion swaps every transition for this over 6 frames (FILM §9).
EASE_IN_OUT = bezier(0.42, 0.00, 0.58, 1.00)


def seg(f, a, b):
    """Progress of absolute frame `f` through the INCLUSIVE frame span a..b.

    Returns 0.0 at f == a and 1.0 at f == b. Inclusive because a value that is
    'full at f == b' must actually reach 1.0 on b — the reading-floor maths in
    FILM §9 counts frames the same way (b - a + 1) and an exclusive span here
    would leave every settle one frame short of its target.
    """
    if b <= a:
        return 1.0 if f >= b else 0.0
    return clamp01((f - a) / float(b - a))


# ══════════════════════════════════════════════════════════════════════════
#  6.  THE FIXTURE — FILM.md §8. One story, real observed numbers.
# ══════════════════════════════════════════════════════════════════════════

FIXTURE = {
    'target_cc':    'CA',
    'home_city':    'Toronto',  'home_cc': 'CA',
    'away_city':    'Tehran',   'away_cc': 'IR',
    'net_ms':       82,
    'api_ms':       273,
    'offline_line': 'internet down',
    'status_code':  503,
    'retry_from':   3, 'retry_to': 4, 'retry_max': 8,
    'allowed_final': 124200,
    'url':          'ghhrmnzdh.github.io/tower',
}


# ══════════════════════════════════════════════════════════════════════════
#  7.  THE SCENE CONTRACT
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Ctx:
    """What every scene module's `draw(ctx)` receives.

    The canvas arrives already filled with INK, and the scene is expected to
    paint the WHOLE frame: scenes are opaque and total. There is no alpha
    compositing between scenes and no scene bleeds into another — a cross-cut
    is handled inside whichever scene owns those frames.

    `f` is the ABSOLUTE frame index and is the load-bearing field: every frame
    number in FILM.md is absolute, and the mark's phase P = f / 30 is global and
    never resets, so the radar is one continuous machine for the whole 40 s.
    `t` / `k` / `sf` are scene-relative conveniences.
    """
    img: Image.Image      # RGB, 1920x1080, pre-filled with INK
    d: ImageDraw.ImageDraw
    f: int                # absolute frame, 0..1199
    t: float              # seconds into this scene
    dur: float            # this scene's duration, seconds
    k: float              # progress through this scene, 0..1
    sf: int               # frame index into this scene, 0-based

    @property
    def P(self) -> float:
        """Global phase in seconds — the argument to every mark formula."""
        return self.f / float(FPS)


def make_ctx(f: int, img: Image.Image, first: int, last: int) -> Ctx:
    """Build the Ctx for absolute frame `f` in a scene spanning `first..last`
    INCLUSIVE."""
    n = last - first + 1
    sf = f - first
    return Ctx(img=img, d=ImageDraw.Draw(img), f=f,
               t=sf / float(FPS), dur=n / float(FPS),
               k=(sf / float(n - 1)) if n > 1 else 1.0, sf=sf)
