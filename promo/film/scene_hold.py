"""scene_hold.py — Act C of the Tower film.  Frames 690 … 1019 inclusive.

    OFF-COUNTRY  ->  HOLD  ->  RECOVERY

    C1  hold.geo      f690 … f779   (90 f)  clear -> holdGeo (morph M3)
    C2  hold.which    f780 … f869   (90 f)  the contrast pair, alternating spotlight
    C3  hold.pending  f870 … f944   (75 f)  layout M', the 160 px 503
    C4  hold.clear    f945 … f1019  (75 f)  holdGeo -> verify (M5) -> clear (M1)

Authority: promo/film/FILM.md §2, §3, §4.9–4.12; notes/design.md §1–2, §4.

Public surface:  RANGE, draw(ctx)

NOTE ON THE SHARED MODULES.  `brand.py` / `draw.py` / `ui.py` did not exist when
this module was written (they are being authored in parallel), and FILM.md's
own `core.py` sketch exposes only `radar_morph(a, b, k, P)` — a whole-state
crossfade parameterisation that cannot express M3's and M5's *staged* builds
(ray at f735, contact at f750, lunge at f758; fence absorbed into the ring at
f960 while the needle draws on at f966).  So the mark is drawn here from a
channel-level description, transcribed verbatim from design.md §2 and FILM.md
§2.3/§3.  Everything under "SHARED SURFACE MIRROR" below is a literal copy of
FILM.md §2.5–2.7 and is the seam to swap at integration; nothing below it
invents a value.
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageFont

# ── ADAPTER.  brand.py is the authority for the mark's geometry. This module
#    renders the radar by interpolated CHANNELS rather than by the spec dict
#    the other three scenes use, so it cannot share their tile renderer — but
#    it must not be allowed to disagree with them about the numbers.
_B = None
for _cand in ('promo.film.brand', 'brand'):
    try:
        _B = __import__(_cand, fromlist=['brand'])
        break
    except Exception:
        continue


def _shared(name, fallback):
    """brand.py's value if it has one, else the standalone fallback."""
    return getattr(_B, name, None) if getattr(_B, name, None) is not None \
        else fallback


RANGE = (690, 1019)

# ══════════════════════════════════════════════════════════════════════════
#  SHARED SURFACE MIRROR — FILM.md §2.2, §2.5, §2.6, §2.7
# ══════════════════════════════════════════════════════════════════════════

W, H = 1920, 1080

INK      = (0x0C, 0x0C, 0x0E)
HAIRLINE = (0x34, 0x34, 0x3A)
TEXT     = (0xE7, 0xE6, 0xE2)
TEXT2    = (0x9A, 0x9A, 0x95)
MUTED    = (0x8B, 0x8B, 0x86)
AMBER    = (0xE6, 0xA9, 0x3C)
# GREEN #30D158 is defined by the system and deliberately NEVER used in the film.
# RED   #E5484D belongs to `off`, which this act never enters.

FONT_UI        = "/System/Library/Fonts/SFNS.ttf"
FONT_MONO      = "/Users/omega/room/mainprojects/tower/src/Fonts/JetBrainsMono-Medium.ttf"
FONT_MONO_BOLD = "/Users/omega/room/mainprojects/tower/src/Fonts/JetBrainsMono-Bold.ttf"

_FONTS: dict = {}


def _font(kind, px, optical=None, weight=None):
    """promo/overlays.py:font(), with the optical-size axis decoupled from the
    render size so a run can be rasterised at 3x without changing its design."""
    px = int(round(px))
    optical = px if optical is None else int(round(optical))
    key = (kind, px, optical, weight)
    f = _FONTS.get(key)
    if f is not None:
        return f
    if kind == "ui":
        f = ImageFont.truetype(FONT_UI, px)
        try:                      # axes: [Width, Optical Size, GRAD, Weight]
            f.set_variation_by_axes([100, max(17, min(96, optical)), 400,
                                     weight or 400])
        except Exception:
            pass
    elif kind == "mono":
        f = ImageFont.truetype(FONT_MONO, px)
    elif kind == "mono_bold":
        f = ImageFont.truetype(FONT_MONO_BOLD, px)
    else:
        raise ValueError(kind)
    _FONTS[key] = f
    return f


def _cubic_bezier(x1, y1, x2, y2, eps=1e-6):
    def bx(u): return 3 * (1 - u) ** 2 * u * x1 + 3 * (1 - u) * u * u * x2 + u ** 3
    def by(u): return 3 * (1 - u) ** 2 * u * y1 + 3 * (1 - u) * u * u * y2 + u ** 3
    def dbx(u): return 3 * (1 - u) ** 2 * x1 + 6 * (1 - u) * u * (x2 - x1) + 3 * u * u * (1 - x2)

    def f(x):
        x = 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)
        u = x
        for _ in range(8):
            e = bx(u) - x
            if abs(e) < eps:
                break
            dd = dbx(u)
            if abs(dd) < 1e-9:
                break
            u -= e / dd
        return by(u)
    return f


def _spring(response, zeta):
    w0 = 2.0 * math.pi / response
    if zeta < 1.0:
        wd = w0 * math.sqrt(1.0 - zeta * zeta)
        return lambda t: 0.0 if t <= 0 else 1.0 - math.exp(-zeta * w0 * t) * (
            math.cos(wd * t) + (zeta * w0 / wd) * math.sin(wd * t))
    return lambda t: 0.0 if t <= 0 else 1.0 - math.exp(-w0 * t) * (1.0 + w0 * t)


EASE_ENTER = _cubic_bezier(0.16, 1.00, 0.30, 1.00)
EASE_MOVE  = _cubic_bezier(0.65, 0.00, 0.35, 1.00)
EASE_SOBER = _cubic_bezier(0.33, 1.00, 0.68, 1.00)
EASE_SNAP  = _cubic_bezier(0.22, 1.00, 0.36, 1.00)
_SETTLE    = _spring(0.45, 0.85)


def _clamp01(x): return 0.0 if x < 0.0 else (1.0 if x > 1.0 else x)
def _lerp(a, b, k): return a + (b - a) * k
def _mix(c0, c1, k):
    return (_lerp(c0[0], c1[0], k), _lerp(c0[1], c1[1], k), _lerp(c0[2], c1[2], k))


def _seg(f, a, b):
    """0 at frame a, 1 at frame b, clamped.  Never linear at the call site."""
    return _clamp01((float(f) - a) / float(b - a))


def _settle(f, start, n=15):
    """A radar state morph.  15 f, SETTLE, complete on frame start+n-1.
    Clamped to 1.0: SETTLE overshoots +0.63 % and this act's morphs land on
    amber / held states, where DESIGN.md forbids any overshoot at all."""
    return _clamp01(_SETTLE((float(f) - start + 1.0) / 30.0))


def _fade_in(f, start, n=8, ease=EASE_SOBER):
    """Sober opacity in.  Zero on `start`, full on `start + n`."""
    return ease(_clamp01((float(f) - start) / n))


def _fade_out(f, start, n=8, ease=EASE_SOBER):
    """Sober opacity out.  Full on `start - 1`, zero on `start + n - 1`."""
    return 1.0 - ease(_clamp01((float(f) - start + 1.0) / n))


# ══════════════════════════════════════════════════════════════════════════
#  TYPE  — sub-pixel in x and y, supersampled, blended straight onto the field
# ══════════════════════════════════════════════════════════════════════════

_TSS = 3          # text supersample


def _adv(kind, px):
    """JetBrains Mono is 0.6 em and tabular by construction (FILM.md §2.5)."""
    return 0.6 * px


def _run_w(text, kind, px, track):
    if kind == "ui":
        fs = _font("ui", px * _TSS, optical=px)
        return fs.getlength(text) / _TSS + track * max(0, len(text) - 1)
    return _adv(kind, px) * len(text) + track * max(0, len(text) - 1)


def _glyph(img, ch, kind, px, x, base, rgb, a, optical=None, weight=None):
    """One character, baseline-left at (x, base), both coordinates float."""
    if a <= 0.004 or ch == " ":
        return
    a = 1.0 if a > 1.0 else a
    ss = _TSS
    pad_l = int(math.ceil(px * 0.45))
    pad_r = int(math.ceil(px * 1.25))
    pad_t = int(math.ceil(px * 1.35))
    pad_b = int(math.ceil(px * 0.55))
    ox = int(math.floor(x)) - pad_l
    oy = int(math.floor(base)) - pad_t
    tw, th = pad_l + pad_r, pad_t + pad_b
    if tw <= 0 or th <= 0:
        return
    tile = Image.new("L", (tw * ss, th * ss), 0)
    ImageDraw.Draw(tile).text(
        ((x - ox) * ss, (base - oy) * ss),
        ch, font=_font(kind, px * ss, optical=optical or px, weight=weight),
        fill=255, anchor="ls")
    mask = tile.resize((tw, th), Image.LANCZOS)
    if a < 0.999:
        mask = mask.point([int(i * a + 0.5) for i in range(256)])
    img.paste(rgb, (ox, oy), mask)


def _draw_text(img, text, kind, px, x, base, rgb, track=0.0, a=1.0,
               optical=None, weight=None, per_char=None):
    """Draw a tracked run.  `per_char(i, n) -> (alpha_mult, dy)` drives kinetic
    reveals; without it the run is a flat, settled block of type."""
    n = len(text)
    if kind == "ui":
        fs = _font("ui", px * _TSS, optical=optical or px)
        cx = x
        for i, ch in enumerate(text):
            am, dy = (1.0, 0.0) if per_char is None else per_char(i, n)
            _glyph(img, ch, kind, px, cx, base + dy, rgb, a * am,
                   optical=optical or px, weight=weight)
            cx += fs.getlength(ch) / _TSS + track
    else:
        adv = _adv(kind, px) + track
        for i, ch in enumerate(text):
            am, dy = (1.0, 0.0) if per_char is None else per_char(i, n)
            _glyph(img, ch, kind, px, x + i * adv, base + dy, rgb, a * am)


def _kinetic(f, start, rise, span_f=24):
    """A 24 f envelope, 0.62 f/char stagger capped at 8 f, 0.14 em rise,
    EASE_ENTER.  Returns a `per_char` callable.

    At the original 13 f with a 7 f cap a 23-character readout gave every
    glyph a 6-frame fade and the leading edge crossed the line in 7 frames —
    measured on rendered frames, one glyph per frame, which is a typewriter,
    the one text effect the brief calls cheap.  It also collapsed the rise
    into a single frame, so the channel that makes a reveal feel authored
    never rendered at all.  24 f with an 8 f leading edge gives each glyph
    ~16 frames: a cascade with a leading edge, and a rise you can see."""
    def mk(i, n):
        span = min(8.0, 0.62 * max(0, n - 1))
        win = max(12.0, span_f - span)
        d = 0.0 if n <= 1 else span * i / (n - 1.0)
        p = EASE_ENTER(_clamp01(((float(f) - start) - d) / win))
        return p, (1.0 - p) * rise
    return mk


def _offset(per_char, i0, n_total):
    """Re-index a per-char callable so several coloured runs on one baseline
    share a single reveal cascade."""
    if per_char is None:
        return None
    return lambda i, _n: per_char(i0 + i, n_total)


# ══════════════════════════════════════════════════════════════════════════
#  THE RADAR MARK — design.md §1–2, drawn from a channel description
# ══════════════════════════════════════════════════════════════════════════

_BLIPS = ((64.0, 41.0), (38.0, 58.0), (58.0, 66.0))

#  THE OFF-COUNTRY CONTACT.  Glyph.swift puts it at (72, 32) — 28.43 units from
#  the hub — with a halo reaching 42.4.  In the menu bar that is a 4 px dot on
#  a 20 px mark and nothing collides.  At 374 px the contact's disc reached
#  34.2 and the halo 42.4 against a ring stroke that spans 30…36: the amber
#  blob was welded ACROSS the ring at 1–2 o'clock and its halo bit a dark
#  crescent out of the inner edge, on 189 frames including all 91 of the
#  film's payload shot.  That broke the film's own thesis on screen —
#  "holdNet breaks the ring; holdGeo does not" — while holdGeo's ring was
#  visibly broken.  Pulled in to 21.0 with the halo capped at 8.0, the entire
#  geo group lives inside the ring and the silhouette survives.  The semantic
#  is untouched and still honest: closest approach is 21.0 − 5.0 = 16.0
#  against a fence at 15.  It never gets in.
_RAY_END = (66.5, 37.0)
_RAY_LEN = math.hypot(16.5, 13.0)             # 21.001
_RAY_DIR = (16.5 / _RAY_LEN, -13.0 / _RAY_LEN)
_LUNGE = 5.0
_LUNGE_DIR = (-0.773, 0.634)                  # literal constants, Glyph.swift:139
_RING_CIRC = 2.0 * math.pi * 33.0             # 207.345

#  THE DASH.  See brand.py: at hero scale a dash shorter than the 6-unit
#  stroke is a square block and 19 of them is a sunburst, not a broken ring.
DASH_HOLDNET = _shared('DASH_HOLDNET', (13.82, 6.91))   # 10 on the r = 33 ring
DASH_FENCE = _shared('DASH_FENCE', (7.854, 3.927))      #  8 on the r = 15 fence

#  Two opposed 130 deg wavefronts, centred on 12 and 6 o'clock.  Two CLOSED
#  concentric rings inside a dashed ring is a bullseye, which craft §8.9 bans
#  outright and which was the signature of the state the film shows most.
_PING_ARCS = ((205.0, 130.0), (25.0, 130.0))

PULSE_RATE = 30.0 / 91.0
PULSE_R0, PULSE_DR = 8.0, 20.0
SWEEP_MAX = 27.5


class _Tile:
    """An RGBA glyph tile in unit space (0…100), supersampled.  One layer per
    translucent element (design.md §1.2 rule 2 — no alpha accumulation)."""

    def __init__(self, out_px, ss=4):
        self.out = int(out_px)
        self.S = int(round(out_px * ss))
        self.u = self.S / 100.0
        self.acc = Image.new("RGBA", (self.S, self.S), (0, 0, 0, 0))
        self._lay = None
        self._d = None

    @property
    def d(self):
        if self._lay is None:
            self._lay = Image.new("RGBA", (self.S, self.S), (0, 0, 0, 0))
            self._d = ImageDraw.Draw(self._lay)
        return self._d

    def flush(self):
        if self._lay is not None:
            self.acc = Image.alpha_composite(self.acc, self._lay)
            self._lay = None
            self._d = None

    def result(self):
        self.flush()
        return self.acc.resize((self.out, self.out), Image.LANCZOS)

    # ---- unit-space primitives -------------------------------------------

    def _box(self, cx, cy, r):
        u = self.u
        return [(cx - r) * u, (cy - r) * u, (cx + r) * u, (cy + r) * u]

    def circle(self, cx, cy, r, rgba):
        self.d.ellipse(self._box(cx, cy, r), fill=rgba)

    def ring(self, cx, cy, r, w, rgba):
        """Stroke centred on radius r.  Pillow strokes inward from the bbox."""
        self.d.ellipse(self._box(cx, cy, r + w / 2.0), outline=rgba,
                       width=max(1, int(round(w * self.u))))

    def arc(self, cx, cy, r, w, rgba, a0, a1):
        if a1 - a0 < 0.02:
            return
        self.d.arc(self._box(cx, cy, r + w / 2.0), a0, a1, fill=rgba,
                   width=max(1, int(round(w * self.u))))

    def dash_ring(self, cx, cy, r, w, rgba, on_len, off_len, rot=0.0):
        """Dashes laid from the 0° seam, butt caps, last dash clipped short —
        the period does not divide 360 and that is faithful (design.md §2.2)."""
        if off_len <= 1e-4 or on_len <= 0.0:
            self.ring(cx, cy, r, w, rgba)
            return
        c = 2.0 * math.pi * r
        on_d = 360.0 * on_len / c
        off_d = 360.0 * off_len / c
        per = on_d + off_d
        if per <= 0.05:
            self.ring(cx, cy, r, w, rgba)
            return
        if on_d >= 359.0:
            self.ring(cx, cy, r, w, rgba)
            return
        a = float(rot)
        end = rot + 360.0
        guard = 0
        while a < end and guard < 4000:
            self.arc(cx, cy, r, w, rgba, a, min(a + on_d, end))
            a += per
            guard += 1

    def seg(self, p0, p1, w, rgba, cap=True):
        u = self.u
        self.d.line([p0[0] * u, p0[1] * u, p1[0] * u, p1[1] * u],
                    fill=rgba, width=max(1, int(round(w * u))))
        if cap:
            for p in (p0, p1):
                self.d.ellipse(self._box(p[0], p[1], w / 2.0), fill=rgba)

    def poly(self, pts, rgba):
        u = self.u
        self.d.polygon([(x * u, y * u) for x, y in pts], fill=rgba)


def _rgba(rgb, a):
    a = 0.0 if a < 0.0 else (1.0 if a > 1.0 else a)
    return (int(round(rgb[0])), int(round(rgb[1])), int(round(rgb[2])),
            int(round(255.0 * a)))


def _render_mark(ch, out_px, ss=4):
    """`ch` is the channel dict built by the timeline functions below.
    Draw order is design.md §2.1."""
    t = _Tile(out_px, ss)

    # 1 · outer ring ------------------------------------------------------
    ring = ch["ring"]
    t.dash_ring(50, 50, 33.0, 6.0, _rgba(ring["rgb"], ring["a"]),
                ring["on"], ring["off"])
    t.flush()

    # 2 · verify sweep ----------------------------------------------------
    #  Clamped to SWEEP_MAX so it lives inside the ring's inner edge (30), and
    #  drawn as twelve adjacent slices ramping to zero behind the needle: a
    #  radar trail DECAYS, and a flat-alpha pie wedge with two hard radial
    #  edges is a loading-spinner asset.  Identical to scene_open's.
    wedge = ch.get("wedge")
    if wedge and wedge["a"] > 0.002:
        rot = wedge["rot"]
        for i in range(12):
            a0 = math.radians(270.0 - 61.5 * i / 12.0 + rot)
            a1 = math.radians(270.0 - 61.5 * (i + 1) / 12.0 + rot)
            sa = wedge["a"] * (1.0 - i / 12.0) ** 1.35
            if sa <= 0.003:
                continue
            t.poly([(50.0, 50.0),
                    (50.0 + SWEEP_MAX * math.cos(a0),
                     50.0 + SWEEP_MAX * math.sin(a0)),
                    (50.0 + SWEEP_MAX * math.cos(a1),
                     50.0 + SWEEP_MAX * math.sin(a1))],
                   _rgba(TEXT, sa))
        t.flush()
    needle = ch.get("needle")
    if needle and needle["len"] > 0.2 and needle["a"] > 0.002:
        ang = math.radians(270.0 + needle["rot"])
        ln = min(needle["len"], SWEEP_MAX)
        p1 = (50.0 + ln * math.cos(ang), 50.0 + ln * math.sin(ang))
        #  A round-capped 4-unit line shorter than ~2.5 caps is a keyhole, not
        #  a needle.  Taper the opacity over the last 14 units so the tip
        #  dissolves into the hub instead of parking there as an exclamation
        #  mark for the two frames of its draw-on.
        t.seg((50.0, 50.0), p1, 4.0,
              _rgba(TEXT, needle["a"] * min(1.0, ln / 14.0)))
        t.flush()

    # 3 · holdNet pings ---------------------------------------------------
    for p in ch.get("pings", ()):
        if p["a"] > 0.002:
            for a0, sweep in _PING_ARCS:
                t.arc(50, 50, p["r"], 3.0, _rgba(AMBER, p["a"]), a0, a0 + sweep)
            t.flush()

    # 4 · blips -----------------------------------------------------------
    for (bx, by), ba in zip(_BLIPS, ch.get("blips", (0.0, 0.0, 0.0))):
        if ba > 0.002:
            t.circle(bx, by, 3.6, _rgba(TEXT, ba))
    t.flush()

    # 5 · the inner ring: the clear pulse, and what it becomes ------------
    fen = ch.get("fence")
    if fen and fen["a"] > 0.002 and fen["r"] > 0.5:
        t.dash_ring(50, 50, fen["r"], fen["w"], _rgba(fen["rgb"], fen["a"]),
                    fen["on"], fen["off"], rot=fen.get("rot", 0.0))
        t.flush()

    # 6 · the geo group ---------------------------------------------------
    ray = ch.get("ray")
    if ray and ray["a"] > 0.002 and ray["frac"] > 0.001:
        lim = _RAY_LEN * ray["frac"]
        col = _rgba(AMBER, ray["a"])
        s = 0.0
        while s < lim:
            s1 = min(s + 2.2, lim)
            p0 = (50.0 + _RAY_DIR[0] * s, 50.0 + _RAY_DIR[1] * s)
            p1 = (50.0 + _RAY_DIR[0] * s1, 50.0 + _RAY_DIR[1] * s1)
            t.seg(p0, p1, 2.5, col)
            s += 4.6
        t.flush()
    con = ch.get("contact")
    if con and con["a"] > 0.002:
        t.circle(con["x"], con["y"], con["r"], _rgba(AMBER, con["a"]))
        t.flush()
    halo = ch.get("halo")                       # over the contact, Glyph.swift:151
    if halo and halo["a"] > 0.002:
        t.ring(halo["x"], halo["y"], halo["r"], 2.5, _rgba(AMBER, halo["a"]))
        t.flush()

    # 7 · core ------------------------------------------------------------
    core = ch["core"]
    if core["a"] > 0.002:
        if core.get("hollow"):
            t.ring(50, 50, core["r"], core["w"], _rgba(core["rgb"], core["a"]))
        else:
            t.circle(50, 50, core["r"], _rgba(core["rgb"], core["a"]))
    return t.result()


def _paste_mark(img, tile, cx, cy, a=1.0):
    if a < 0.999:
        tile = tile.copy()
        tile.putalpha(tile.getchannel("A").point(
            [int(i * a + 0.5) for i in range(256)]))
    s = tile.size[0]
    img.paste(tile, (int(round(cx - s / 2.0)), int(round(cy - s / 2.0))), tile)


# ══════════════════════════════════════════════════════════════════════════
#  STATE CHANNELS — every value a pure function of the global frame index
# ══════════════════════════════════════════════════════════════════════════
#
#  §2.10: the mark's phase is global and never resets.  P = f / 30.

def _P(f): return f / 30.0


def _blips_clear(f, A=1.0):
    P = _P(f)
    return tuple(0.8 + 0.2 * math.sin(P * 1.6 + i * 1.3) * A for i in range(3))


def _blips_verify(f, A=1.0):
    P = _P(f)
    return tuple(0.3 + 0.12 * math.sin(P * 2.2 + i) * A for i in range(3))


def _pulse_clear(f, born=None):
    """design.md §2.5.  `born` gives the element a local phase origin so it
    emerges at r=8 instead of popping in mid-radius (FILM.md §2.10)."""
    P = _P(f) if born is None else (f - born) / 30.0
    pr = (P * PULSE_RATE) % 1.0
    #  Stops at r 28 so it dissolves BEFORE the ring stroke (30…36) instead of
    #  drawing a second hairline inside it; ramps up over the first 15 % of the
    #  cycle so it is not a hard pop at the hub every cycle.
    return (PULSE_R0 + pr * PULSE_DR,
            (1.0 - pr) * _clamp01(pr / 0.15) * 0.5)


def _pings_holdnet(f, live=1.0):
    """design.md §2.7, blended toward the documented Reduce-Motion still."""
    P = _P(f)
    out = []
    for i in (0, 1):
        pr = ((P * 0.7) + i * 0.5) % 1.0
        r_l = 7.0 + pr * 19.0
        #  The trailing wavefront is scaled to 0.42 so the two are never at
        #  equal weight: a linear falloff put both at 0.35 whenever pr = 0.5,
        #  which is two matched concentric rings — the dartboard.
        a_l = (max(0.0, 1.0 - pr) ** 0.55 * _clamp01(pr / 0.10)
               * (1.0 if i == 0 else 0.42))
        r_s = 10.0 + i * 11.0
        a_s = 0.80 - i * 0.46
        out.append({"r": _lerp(r_s, r_l, live), "a": _lerp(a_s, a_l, live)})
    return out


_FENCE_ROT_START = 735          # C1: "from f735 it rotates at 45 °/s"
_LUNGE_START = 758              # C1: the contact begins its lunge
_FENCE_DASH_PERIOD = 360.0 * sum(DASH_FENCE) / (2.0 * math.pi * 15.0)  # 45.0°


def _fence_rot(f):
    return ((max(0.0, f - _FENCE_ROT_START) / 30.0) * 45.0) % 360.0


def _geo_live(f, live=1.0):
    """The holdGeo contact: lunge, scale and halo, blended toward the
    documented Reduce-Motion still (lunge 0, s 1, halo r 6.5 @ 0.5).
    Closest approach is d = 16.0 against a fence at 15 — it never gets in."""
    P = _P(f)
    amp = _clamp01((f - _LUNGE_START) / 8.0)
    amp = EASE_SOBER(amp) * live
    lunge = _LUNGE * (0.5 + 0.5 * math.sin(P * 2.2)) * amp
    s = 1.0 + 0.16 * math.sin(P * 3.0) * amp
    mx = _RAY_END[0] + _LUNGE_DIR[0] * lunge
    my = _RAY_END[1] + _LUNGE_DIR[1] * lunge
    hp = (P * 1.1) % 1.0
    #  capped at 8.0 -> the halo's outer edge reaches 29.0, one unit inside the
    #  ring's inner edge at 30.0.  It used to reach 42.4, i.e. outside the mark.
    hr = _lerp(6.5, 3.0 + hp * 5.0, amp)
    ha = _lerp(0.5, (1.0 - hp) * 0.8, amp)
    return {"x": mx, "y": my, "r": 4.5 * s, "hr": hr, "ha": ha}


def _ch_clear(f):
    r, a = _pulse_clear(f)
    return {
        "ring":  {"rgb": TEXT, "a": 1.0, "on": _RING_CIRC, "off": 0.0},
        "core":  {"rgb": TEXT, "a": 1.0, "r": 4.5, "w": 0.0},
        "blips": _blips_clear(f),
        "fence": {"r": r, "w": 3.0, "rgb": TEXT, "a": a, "on": _RING_CIRC,
                  "off": 0.0, "rot": 0.0},
    }


def _ch_holdgeo(f, ray_frac=1.0, contact_a=1.0, live=1.0, blips=(0.0, 0.0, 0.0)):
    g = _geo_live(f, live)
    return {
        "ring":  {"rgb": AMBER, "a": 1.0, "on": _RING_CIRC, "off": 0.0},
        "core":  {"rgb": TEXT, "a": 1.0, "r": 4.5, "w": 0.0},
        "blips": blips,
        "fence": {"r": 15.0, "w": 3.0, "rgb": AMBER, "a": 1.0,
                  "on": DASH_FENCE[0], "off": DASH_FENCE[1],
                  "rot": _fence_rot(f) * live},
        "ray":   {"frac": ray_frac, "a": 1.0},
        "contact": {"x": g["x"], "y": g["y"], "r": g["r"], "a": contact_a},
        "halo":  {"x": g["x"], "y": g["y"], "r": g["hr"],
                  "a": g["ha"] * contact_a},
    }


def _ch_holdnet(f, live=1.0):
    return {
        "ring":  {"rgb": AMBER, "a": 1.0,
                  "on": DASH_HOLDNET[0], "off": DASH_HOLDNET[1]},
        "core":  {"rgb": AMBER, "a": 1.0, "r": 4.5, "w": 0.0},
        "blips": (0.0, 0.0, 0.0),
        "pings": _pings_holdnet(f, live),
    }


# ---- the canonical mark, f690 … f1019 -----------------------------------

def _hue_k(k):
    """Colour runs ahead of geometry.

    design.md §2.12: a state transition must change the ring FIRST — colour and
    dash are the fastest-read channel.  A straight lerp between neutral and
    amber sits on a warm cream (#E0D2A8) that exists nowhere in the brand for
    six frames of a fifteen-frame morph; on this curve it passes through in
    two, and the remaining thirteen frames are spent on the geometry, which is
    the channel the viewer is meant to be reading."""
    m = 1.0 - _clamp01(k)
    return 1.0 - m * m * m


def _ch_canonical(f):
    """One continuous machine.  clear -> (M3) -> holdGeo -> (M5) -> verify
    -> (M1) -> clear."""

    # ---- C1 f690…f719 : clear ------------------------------------------
    if f < 720:
        return _ch_clear(f)

    # ---- M3  clear -> holdGeo,  f720…f734 ------------------------------
    if f < 735:
        k = _settle(f, 720)
        kc = _hue_k(k)          # the hue commits in the first ~4 frames
        ch = _ch_clear(f)
        ch["ring"]["rgb"] = _mix(TEXT, AMBER, kc)
        ch["blips"] = tuple(b * (1.0 - k) for b in _blips_clear(f))
        # the clear pulse *becomes* the fence: one ring, re-tuned.
        pr = ((720.0 / 30.0) * PULSE_RATE) % 1.0 + (f - 720) / 30.0 * PULSE_RATE
        pr_r = PULSE_R0 + pr * PULSE_DR
        pr_a = (1.0 - pr) * 0.5
        ch["fence"] = {
            "r":   _lerp(pr_r, 15.0, k),
            "w":   3.0,
            "rgb": _mix(TEXT, AMBER, kc),
            "a":   _lerp(pr_a, 1.0, k),
            "on":  _lerp(_RING_CIRC, DASH_FENCE[0], k),
            "off": _lerp(0.0, DASH_FENCE[1], k),
            "rot": 0.0,
        }
        return ch

    # ---- C1 tail / C2 right / C3 / C4 head : holdGeo --------------------
    if f < 960:
        return _ch_holdgeo(
            f,
            ray_frac=EASE_MOVE(_seg(f, 734, 750)),
            contact_a=_fade_in(f, 750),
        )

    # ---- M5  holdGeo -> verify,  f960…f974 ------------------------------
    # ---- verify,                 f975…f1004 ----------------------------
    # ---- M1  verify -> clear,    f1005…f1019 ---------------------------
    ch = _ch_holdgeo(f, ray_frac=1.0 - EASE_MOVE(_seg(f, 959, 971)),
                     contact_a=_fade_out(f, 960))
    #  THE RELEASE, re-choreographed.  It used to lerp the fence's COLOUR from
    #  amber to neutral while the fence expanded, so for ~6 frames the mark
    #  held a dark-grey dashed ring inside a cream one — a clock face with tick
    #  marks, an object Tower does not have.  Now the fence stays amber for its
    #  whole journey (the travel is the story: "the fence is no longer needed"),
    #  is absorbed into the ring over the last 5 frames, and only THEN does the
    #  ring commit to neutral.  One hue at a time, and the movement is legible
    #  instead of being out-run by its own fade.
    #  Strictly one channel at a time: the fence travels out (f960-969), is
    #  absorbed (f969-971), and only then does the ring commit to neutral
    #  (f971-980).  Overlapped, the amber dashes sit ON a ring that is already
    #  half-neutral and the mark reads as a speckled dial for four frames.
    ch["ring"]["rgb"] = _mix(AMBER, TEXT, _hue_k(EASE_SOBER(_seg(f, 970, 980))))
    ch["fence"]["r"] = _lerp(15.0, 33.0, EASE_MOVE(_seg(f, 959, 969)))
    ch["fence"]["a"] = 1.0 - EASE_MOVE(_seg(f, 968, 971))
    ch["fence"]["rgb"] = AMBER

    rot = (_P(f) * 150.0) % 360.0
    nf = EASE_MOVE(_seg(f, 965, 978))               # needle + wedge draw on
    if f >= 1005:                                    # M1: the needle retracts
        k1 = _settle(f, 1005)
        nf = 1.0 - k1
    ch["needle"] = {"len": SWEEP_MAX * nf, "a": 1.0, "rot": rot}
    ch["wedge"] = {"a": 0.20 * nf, "rot": rot}

    bl = _blips_verify(f)
    if f >= 1005:
        k1 = _settle(f, 1005)
        bc = _blips_clear(f)
        ch["blips"] = tuple(_lerp(bl[i], bc[i], k1) for i in range(3))
        pr_r, pr_a = _pulse_clear(f, born=1005)
        ch["fence"] = {"r": pr_r, "w": 3.0, "rgb": TEXT,
                       "a": pr_a * EASE_ENTER(_seg(f, 1004, 1012)),
                       "on": _RING_CIRC, "off": 0.0, "rot": 0.0}
    else:
        ch["blips"] = tuple(b * EASE_SOBER(_seg(f, 971 + 3 * i, 979 + 3 * i))
                            for i, b in enumerate(bl))
    return ch


# ══════════════════════════════════════════════════════════════════════════
#  LAYOUT — FILM.md §2.4.  Copy lives in columns 1–4, the mark in 6–8.
# ══════════════════════════════════════════════════════════════════════════

MARK_C = _shared('MARK_C', (1350.0, 540.0))
MARK_PX = 520
COPY_X = 200.0
Y_LABEL, Y_CAPTION, Y_RULE, Y_R1 = 432.0, 516.0, 588.0, 636.0
RULE_X1 = 760.0        # caps the widest line in a standard Layout M shot
RULE_X1_BIG = 960.0    # C3 only: the `503` lockup runs wider

LABEL_TRACK = 4.6
LABEL_PX = 32
CAPTION_PX = 46
READ_PX = 32


def _rule(img, f, start, y=Y_RULE, x0=COPY_X, x1=RULE_X1, n=16):
    """A 1 px hairline that draws on — never fades on (craft §6.9)."""
    w = (x1 - x0) * EASE_MOVE(_seg(f, start - 1, start + n - 1))
    if w < 1.0:
        return
    ImageDraw.Draw(img).rectangle([x0, y, x0 + w - 1, y], fill=HAIRLINE)


def _label(img, text, x, base, rgb, a=1.0, per_char=None, centred=False):
    if a <= 0.004:
        return
    w = _run_w(text, "mono_bold", LABEL_PX, LABEL_TRACK)
    _draw_text(img, text, "mono_bold", LABEL_PX,
               x - w / 2.0 if centred else x, base, rgb,
               track=LABEL_TRACK, a=a, per_char=per_char)


def _caption(img, text, x, base, a=1.0, per_char=None, centred=False):
    if a <= 0.004:
        return
    w = _run_w(text, "ui", CAPTION_PX, 0.36)
    _draw_text(img, text, "ui", CAPTION_PX,
               x - w / 2.0 if centred else x, base,
               TEXT2, track=0.36, a=a, optical=CAPTION_PX, weight=400,
               per_char=per_char)


def _readout(img, spans, x, base, a=1.0, per_char=None, px=READ_PX,
             i0=0, n_total=None):
    """A readout line as coloured runs sharing one baseline.  Only the fault
    clause takes the accent (FILM.md §2.6).  `i0`/`n_total` place this line's
    characters inside a longer reveal cascade."""
    if a <= 0.004:
        return
    adv = _adv("mono", px)
    n = n_total if n_total is not None else sum(len(s) for s, _ in spans)
    k = i0
    for text, rgb in spans:
        if text:
            _draw_text(img, text, "mono", px, x + (k - i0) * adv, base, rgb,
                       a=a, per_char=_offset(per_char, k, n))
        k += len(text)


# ══════════════════════════════════════════════════════════════════════════
#  COPY — verbatim from FILM.md §5.  Every readout value is a real observed
#  reading from analysis/footage.json.
# ══════════════════════════════════════════════════════════════════════════

IN_RUN    = "Toronto, CA — inside"
OUT_HEAD  = "Tehran, IR — "             # muted: not the fault
OUT_FAULT = "outside"                   # the accent falls here, and only here
OUT_RUN   = OUT_HEAD + OUT_FAULT
TAIL_RUN  = " CA"                       # the target: never changes, ever

# The two leading runs must be the same length or the line reflows across the
# relay and the trailing ` CA` — which never moves — would appear to jump.
assert len(IN_RUN) == len(OUT_RUN) == 20

X_TAIL = COPY_X + len(IN_RUN) * _adv("mono", READ_PX)


# ══════════════════════════════════════════════════════════════════════════
#  C1 · hold.geo — f690 … f779
# ══════════════════════════════════════════════════════════════════════════

def _c1(img, f):
    _paste_mark(img, _render_mark(_ch_canonical(f), MARK_PX), *MARK_C)

    _rule(img, f, 692)

    #  THE BEFORE.  The guard must be visibly RESTORED before location takes
    #  it away, or `off` and `holdGeo` collapse into one memory — and the label
    #  slot used to sit empty for the 38 frames that were supposed to prove it.
    #  `CLEARED` holds it, and relays out into `HOLD · LOCATION` on the flip.
    if 694 <= f <= 727:
        _label(img, "CLEARED", COPY_X, Y_LABEL, TEXT,
               a=_fade_out(f, 720) if f >= 720 else 1.0,
               per_char=_kinetic(f, 694, 3.4, span_f=16) if f < 711 else None)

    # readout — two independent runs on one baseline.  The leading run relays;
    # the trailing ` CA` never moves and never leaves.  It DIPS, though: with
    # the leading run gone and the tail at full opacity the slot spent two
    # frames holding nothing but the word `CA`, 330 px of empty field to its
    # left, which reads exactly like a truncated string rather than like "the
    # target country never changes".
    n_line = len(IN_RUN) + len(TAIL_RUN)
    if f >= 700:
        #  a shorter envelope than the film's standard 24 f: this line has to
        #  be fully settled before the flip takes it at f720, and a reveal
        #  still running into its own exit is a smear, not a relay.
        pc = _kinetic(f, 700, 3.6, span_f=18) if f < 719 else None
        if f < 720:
            _readout(img, [(IN_RUN, MUTED)], COPY_X, Y_R1,
                     per_char=pc, n_total=n_line)
        else:
            a_out = _fade_out(f, 720)
            if a_out > 0.004:
                _readout(img, [(IN_RUN, MUTED)], COPY_X, Y_R1, a=a_out)
            a_in = _fade_in(f, 727)
            if a_in > 0.004:
                # only the fault word takes the accent; the target does not.
                _readout(img, [(OUT_HEAD, MUTED), (OUT_FAULT, AMBER)],
                         COPY_X, Y_R1, a=a_in)
        tail_a = 1.0
        if 719 <= f <= 734:
            tail_a = _lerp(1.0, 0.45,
                           EASE_SOBER(_seg(f, 719, 724))
                           * (1.0 - EASE_SOBER(_seg(f, 728, 734))))
        _readout(img, [(TAIL_RUN, MUTED)], X_TAIL, Y_R1, a=tail_a,
                 per_char=pc, i0=len(IN_RUN), n_total=n_line)

    # the verdict lands on f720; the explanation follows at f728.
    if f >= 728:
        _label(img, "HOLD · LOCATION", COPY_X, Y_LABEL, AMBER,
               a=_fade_in(f, 728))


# ══════════════════════════════════════════════════════════════════════════
#  C2 · hold.which — f780 … f869.  The thesis: two holds, two causes.
# ══════════════════════════════════════════════════════════════════════════

C2_L = (660.0, 462.0)
C2_R = (1260.0, 462.0)
C2_PX = 380              # 274 px of ring against the hero's 374.  The four
#  differences this shot exists to teach — ring broken vs solid, core amber vs
#  neutral, sonar vs fence, no ray vs ray — are 10 px details at 300.
C2_Y_LABEL = 700.0
C2_Y_CAPTION = 820.0
C2_DIM = 0.80          # a diagram, not a ghost.  At 0.45 the frozen side
#  resolved to #513F21 — dark brown at 2.5:1 against the field — and the amber
#  core, the one channel that separates holdNet from holdGeo, could not be read
#  at all.  Worse, it is a STORY error: rendering one cause at 45 % says one of
#  them matters less, when the shot's whole idea is that they are two equally
#  valid answers and Tower tells you which.  The hierarchy comes from MOTION
#  instead — the focused side animates, the other is dead still — which is
#  exactly what design.md's legible-still-frame guarantee exists for.
C2_DIM_LABEL = 0.58


def _c2_dim_l(f):
    """Left goes quiet over f832…f839."""
    return EASE_SOBER(_seg(f, 831, 839))


def _c2_live_r(f):
    """Right comes up over f841…f848 — AFTER the left has landed, never on the
    same frame.  Two elements moving in opposite directions across the same
    five frames is a cross-fade with extra steps, and Amendment B's RELAY rule
    says the outgoing element vacates first."""
    return EASE_SOBER(_seg(f, 840, 848))


def _c2(img, f):
    kl, kr = _c2_dim_l(f), _c2_live_r(f)

    # ---- left · holdNet -------------------------------------------------
    # The marks' 8 f sober rise is seated one frame early so the cut frame
    # f780 carries ink.  EASE_SOBER is front-loaded, so f780 lands at 0.42 —
    # the mark reads as already there and settling, not as a dip to black.
    # The labels are NOT shifted; their copy-deck "full at" frames are exact.
    la = _fade_in(f, 779) * _lerp(1.0, C2_DIM, kl)
    if la > 0.004:
        _paste_mark(img, _render_mark(_ch_holdnet(f, live=1.0 - kl),
                                      C2_PX, ss=4),
                    *C2_L, a=la)

    # ---- right · holdGeo ------------------------------------------------
    ra = _fade_in(f, 783) * _lerp(C2_DIM, 1.0, kr)
    if ra > 0.004:
        ch = _ch_holdgeo(f, live=kr)
        # resume without a jump: the dash pattern repeats every 45°, so blend
        # toward the live angle's nearest equivalent.  At k = 1 the picture is
        # identical to the live pose; nothing spins up.
        live_rot = _fence_rot(f)
        eq = live_rot - round(live_rot / _FENCE_DASH_PERIOD) * _FENCE_DASH_PERIOD
        ch["fence"]["rot"] = _lerp(0.0, eq, kr)
        _paste_mark(img, _render_mark(ch, C2_PX, ss=4), *C2_R, a=ra)

    # ---- labels · relayed one at a time ---------------------------------
    _label(img, "HOLD · CONNECTION", C2_L[0], C2_Y_LABEL, AMBER,
           a=_fade_in(f, 784) * _lerp(1.0, C2_DIM_LABEL, kl), centred=True)
    _label(img, "HOLD · LOCATION", C2_R[0], C2_Y_LABEL, AMBER,
           a=_fade_in(f, 788) * _lerp(C2_DIM_LABEL, 1.0, kr), centred=True)

    if f >= 791:
        _caption(img, "Tower tells you which.", 960.0, C2_Y_CAPTION,
                 per_char=_kinetic(f, 791, 5.0) if f < 816 else None,
                 centred=True)


# ══════════════════════════════════════════════════════════════════════════
#  C3 · hold.pending — f870 … f944.  Layout M′.
#  C4 · hold.clear   — f945 … f1019. Layout M′ -> M, without a cut.
# ══════════════════════════════════════════════════════════════════════════

#  THE PAYLOAD LOCKUP.
#
#  Face.  `503` was set in JetBrains Mono Bold, whose programmer zero carries a
#  dot.  At 160 px, in the middle of the most important string in the film,
#  that dot reads as a defect — an eye, a bullet hole, a typo — and nothing
#  else in the film has a dotted counter, so it looks like an accident.  A code
#  face blown to hero size is also literally "a terminal screenshot scaled up",
#  the exact read the brief exists to prevent.  SFNS at 700 is the macOS
#  numeral: it is the app's own UI face, it is calm and enormous, and it has no
#  dotted zero.  The annotations stay mono, because they are data.
#
#  Alignment.  The annotations used to sit at the numeral's mid-height and 12 px
#  BELOW its baseline, so the lockup read as two unrelated objects jammed
#  together.  Line 2 now shares the numeral's baseline exactly and line 1 sits
#  inside its cap band, which turns two stray lines into one object.  The
#  leading `· ` is gone: a mid-dot has wide sidebearings, so line 1 read as
#  indented by 14 px against line 2, and at 26 px it looked like a bullet-list
#  marker that had lost its list.
Y_BIG = 760.0
BIG_PX = 176
FK_BIG = ("ui", 700)
ANNOT_PX = 28
X_ANNOT = 590.0
Y_A1, Y_A2 = 708.0, 760.0

C3_BIG, C3_LABEL, C3_CAP = 873, 880, 886
C3_RULE, C3_AN1, C3_AN2 = 890, 894, 898
C4_OUT = 957            # the whole M-prime block clears in ONE gesture


def _c34(img, f):
    _paste_mark(img, _render_mark(_ch_canonical(f), MARK_PX), *MARK_C)

    # ---- label slot · a RELAY, never a cross-fade -----------------------
    a_pending = (_fade_out(f, C4_OUT, 6) if f >= C4_OUT
                 else _fade_in(f, C3_LABEL))
    if a_pending > 0.004:
        _label(img, "PENDING", COPY_X, Y_LABEL, AMBER, a=a_pending)
    if f >= 967:
        # PENDING is at zero alpha from f963; CLEARED's first ink is f967.
        # The state is good again, so this reveal may be kinetic.
        _label(img, "CLEARED", COPY_X, Y_LABEL, TEXT,
               per_char=_kinetic(f, 966, 3.0, span_f=14) if f < 981 else None)

    # ---- the one line that spans the hold and its release ---------------
    if f >= C3_CAP:
        _caption(img, "The turn survives.", COPY_X, Y_CAPTION,
                 a=_fade_in(f, C3_CAP))

    _rule(img, f, C3_RULE, x1=RULE_X1_BIG)

    # ---- the big-number lockup · one text object ------------------------
    #  It enters 3 frames after the cut, not 22.  The cut at f870 is the one
    #  place in the film where the size of the world changes, and the numeral
    #  was arriving a full second behind it — so the biggest planned event in
    #  the piece was decoupled from its own cut and f870–f891 was the emptiest
    #  the frame had been since `off`.
    a_big = _fade_out(f, C4_OUT, 6) if f >= C4_OUT else _fade_in(f, C3_BIG)
    if a_big > 0.004:
        # 503 is the mechanism, not the fault: neutral, large and calm.
        # It fades at full size — it never scales in and never shrinks away.
        _draw_text(img, "503", "ui", BIG_PX, COPY_X, Y_BIG, TEXT,
                   track=-3.0, a=a_big, optical=BIG_PX, weight=700)

    a_an1 = _fade_out(f, C4_OUT + 1, 6) if f >= C4_OUT + 1 else _fade_in(f, C3_AN1)
    if a_an1 > 0.004:
        _draw_text(img, "Retry-After", "mono", ANNOT_PX, X_ANNOT, Y_A1,
                   MUTED, a=a_an1)

    a_an2 = _fade_out(f, C4_OUT + 2, 6) if f >= C4_OUT + 2 else _fade_in(f, C3_AN2)
    if a_an2 > 0.004:
        head = "Retrying · attempt "
        _draw_text(img, head, "mono", ANNOT_PX, X_ANNOT, Y_A2, MUTED, a=a_an2)
        xd = X_ANNOT + len(head) * _adv("mono", ANNOT_PX)
        # the only number that changes in the whole film: a digit-in-place
        # swap at f930, 4 f EASE_SNAP.  Tabular mono — nothing reflows.
        ks = EASE_SNAP(_seg(f, 929, 933))
        if ks < 0.999:
            _draw_text(img, "3", "mono", ANNOT_PX, xd, Y_A2, MUTED,
                       a=a_an2 * (1.0 - ks))
        if ks > 0.001:
            _draw_text(img, "4", "mono", ANNOT_PX, xd, Y_A2, MUTED, a=a_an2 * ks)
        _draw_text(img, "/8", "mono", ANNOT_PX, xd + _adv("mono", ANNOT_PX),
                   Y_A2, MUTED, a=a_an2)

    # ---- the copy column returns to Layout M ----------------------------
    #  ONE readout line, not two.  `allowed 124200` was a bare six-digit
    #  counter with no unit, no label and no prior appearance anywhere in the
    #  film: a viewer cannot parse it, so it was grey noise competing with the
    #  caption on the one shot whose job is relief.  Three objects and more
    #  field is the better frame.
    if f >= 972:
        n_line = len(IN_RUN) + len(TAIL_RUN)
        pc = _kinetic(f, 972, 3.6) if f < 997 else None
        _readout(img, [(IN_RUN, MUTED)], COPY_X, Y_R1,
                 per_char=pc, n_total=n_line)
        _readout(img, [(TAIL_RUN, MUTED)], X_TAIL, Y_R1,
                 per_char=pc, i0=len(IN_RUN), n_total=n_line)


# ══════════════════════════════════════════════════════════════════════════

def draw(ctx) -> None:
    """Paint one frame of Act C onto ctx.img, in place."""
    f = int(ctx.f)
    if f < 690 or f > 1019:
        return
    img = ctx.img
    if f < 780:
        _c1(img, f)
    elif f < 870:
        _c2(img, f)
    else:
        _c34(img, f)
