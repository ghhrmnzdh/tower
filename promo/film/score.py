#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""promo/film/score.py — the film's sound.

This is **not a score.** Amendment C: *"the music should be more minimal,
changes in ui should have nice sound effects."*  So what this module builds is:

  1. a near-silent band-limited noise bed (§6.1 of FILM.md) that never plays a
     note, never changes chord and never builds — and that drops to *true
     digital silence* for the `off` shot and for the last 24 frames;
  2. three state textures locked to the mark's own periods (sweep 2.400 s,
     sonar 1.4286 s, fence 8.000 s / lunge 2.856 s), phase-locked to global
     time exactly as FILM.md §2.10 requires of the picture;
  3. **54 designed UI sound effects**, sample-accurate on the frames listed in
     FILM.md §6.3, and on no other frame.

Nine sounds, one pitch object.  Every cue is a short transient plus a short
tuned body plus a fast tail — well-designed OS feedback, not a synth.  Every
pitch comes from one D-minor-pentatonic set so the whole film sounds like one
machine, and pitch carries meaning:

    better  →  resolves UP      (`SFX_LATCH_UP`, the recovery at f960)
    good    →  resolves DOWN a whole tone, A3 → G3   (`SFX_LATCH`)
    hold    →  a damped low knock at C3              (`SFX_HOLD`)
    worse   →  the same knock a minor third BELOW, A2 (`SFX_HOLD_GEO`)

`SFX_HOLD` and `SFX_HOLD_GEO` are a clean 3-semitone step (130.813 / 110.000 =
1.1892) so the ear can tell holdNet from holdGeo blind — which is the film's
entire thesis, in the one sense that is not looking at the screen.

Rules taken from FILM.md §6.3 and not negotiable here:
  · a hard cut never carries a sound of its own (f90, f180, f330, f420, f690,
    f780, f870, f1020, f1080 are silent);
  · nothing rises — no riser, no whoosh, no swell into a cut;
  · a hold never sounds like an alarm (a hold is PENDING, not FAILED);
  · the `off` state is silent, both times.

Deliverable: 48 kHz, 16-bit stereo, **exactly 1 920 000 samples = 40.000 s**,
numpy + stdlib `wave` only, fully deterministic (fixed PCG64 seeds, no clock
reads, no unseeded RNG).

    python3 promo/film/score.py            -> promo/film/out/score.wav
    python3 promo/film/score.py path.wav   -> anywhere else
"""

from __future__ import annotations

import math
import os
import sys
import time
import wave
from dataclasses import dataclass

import numpy as np

# ============================================================ §0  the clock

SR = 48_000                      # samples / s
FPS = 30                         # frames / s
NFRAMES = 1200                   # exactly 40.000 s
SPF = SR // FPS                  # 1600 samples per frame, exactly
N = NFRAMES * SPF                # 1 920 000
DUR = N / SR                     # 40.000

assert SPF * FPS == SR, 'the frame grid must be sample-exact'
assert N == 1_920_000 and DUR == 40.0

TWO_PI = 2.0 * math.pi
SEED = 20260726

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(_HERE, 'out', 'score.wav')


def fs(frame):
    """Frame index -> sample index.  Frame f begins at t = f/30 s, exactly."""
    return int(round(float(frame) * SPF))


def rng(tag):
    """A named, order-independent PRNG.  Same tag -> same noise, every run.

    Deriving the stream from an explicit per-cue integer (never `hash()`, never
    call order) is what makes frame-for-frame determinism survive refactoring
    the timeline.
    """
    return np.random.default_rng(SEED + _STREAM[tag])


_STREAM = {
    'bed_mid': 101, 'bed_side': 102,
    'motif': 104,                    # the tune's struck attack (§6b)
    'ir_l': 105, 'ir_r': 106,        # the room's decorrelated tails (§6b)
    'tex_sweep': 111, 'tex_ping': 112, 'tex_fence': 113,
    'draw': 201, 'seat': 202, 'seat_long': 203,
    'latch': 204, 'latch_up': 205,
    'hold': 206, 'hold_geo': 207,
    'type': 208, 'type_dull': 209,
    'rule': 210, 'rule_short': 211,
    'tick': 212, 'dead': 213,
}

# ======================================================= §1  the pitch object
#
# One set for the whole film: D minor pentatonic (D F G A C).  Nothing outside
# this table is allowed to sound.  Sub-octaves are listed because the knock and
# the seat need weight, not because they are separate pitches.

A1, C2, D1, D2 = 55.0000, 65.4064, 36.7081, 73.4162      # weight, not pitches
A2, C3, D3, G3, A3 = 110.0000, 130.8128, 146.8324, 195.9977, 220.0000
A5, D6, C7, G7 = 880.0000, 1174.6591, 2093.0045, 3135.9635

# F completes the pentatonic set (D F G A C).  It was never needed while the
# bed held one static note; the teaser voicings need the minor third, because
# a third is the difference between "a tone is playing" and "a chord is".
F2, F3 = 87.3071, 174.6141

# The upper register, for the motif and the air. The score measured 95 % of its
# energy below 320 Hz — all floor, no ceiling — which is why it read as small
# and dark rather than as expensive. These are the notes that give it altitude.
D4, F4, A4 = 293.6648, 349.2282, 440.0000
D5, F5, C6 = 587.3295, 698.4565, 1046.5023
A6, D7 = 1760.0000, 2349.3181          # genuine air lives up here, not at A4

# the knock pair, stated as an interval so the relationship is checkable
assert abs((C3 / A2) - 2 ** (3 / 12)) < 1e-3, 'hold/holdGeo must be a minor 3rd'
assert abs((A3 / G3) - 2 ** (2 / 12)) < 1e-3, 'latch must resolve a whole tone'


# ============================================================ §2  DSP kit
#
# Machinery lifted wholesale from promo/audio.py (the proven, loop-free,
# FFT-domain filter set).  The composition is new; the primitives are not.

def rcos(n):
    """Raised-cosine ramp 0 -> 1 over n samples."""
    n = max(int(n), 1)
    if n == 1:
        return np.zeros(1)
    return 0.5 - 0.5 * np.cos(np.pi * np.linspace(0.0, 1.0, n))


def smoothstep(x):
    x = np.clip(np.asarray(x, dtype=np.float64), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def _fft_filter(x, H_of_w):
    """Apply an LTI transfer function evaluated on rfft bins, zero-padded."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n == 0:
        return x
    M = 1 << int(math.ceil(math.log2(n + 8192)))
    w = TWO_PI * np.fft.rfftfreq(M)
    return np.fft.irfft(np.fft.rfft(x, M) * H_of_w(w), M)[:n]


def onepole_lp(x, fc):
    a = 1.0 - math.exp(-TWO_PI * fc / SR)
    return _fft_filter(x, lambda w: a / (1.0 - (1.0 - a) * np.exp(-1j * w)))


def onepole_hp(x, fc):
    return np.asarray(x, dtype=np.float64) - onepole_lp(x, fc)


def bandpass(x, lo, hi):
    return onepole_hp(onepole_lp(x, hi), lo)


def biquad_coefs(kind, f0, q):
    """RBJ cookbook coefficients, normalised by a0."""
    w0 = TWO_PI * f0 / SR
    c, s = math.cos(w0), math.sin(w0)
    alpha = s / (2.0 * q)
    if kind == 'lp':
        b = [(1 - c) / 2, 1 - c, (1 - c) / 2]
    elif kind == 'hp':
        b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]
    elif kind == 'bp':                      # constant 0 dB peak
        b = [q * alpha, 0.0, -q * alpha]
    else:
        raise ValueError(kind)
    a = [1 + alpha, -2 * c, 1 - alpha]
    return [v / a[0] for v in b], [v / a[0] for v in a]


def biquad_ft(x, kind, f0, q):
    b, a = biquad_coefs(kind, f0, q)

    def H(w):
        z1 = np.exp(-1j * w)
        z2 = z1 * z1
        return ((b[0] + b[1] * z1 + b[2] * z2) /
                (a[0] + a[1] * z1 + a[2] * z2))

    return _fft_filter(x, H)


def expdec(n, tau, atk=0.0015):
    """Exponential decay with a raised-cosine attack — the workhorse envelope."""
    n = int(n)
    e = np.exp(-(np.arange(n) / SR) / tau)
    a = max(int(atk * SR), 1)
    e[:a] *= rcos(a)
    return e


def damp(n, power=1.2):
    """A (1-t)^p window on top of a decay, so a knock genuinely *stops*.

    An exponential never reaches zero; a hold that keeps ringing reads as an
    alarm.  This is what makes SFX_HOLD a door closing.
    """
    return (1.0 - np.linspace(0.0, 1.0, int(n))) ** power


def tail_out(x, ms=4.0):
    """Raised-cosine both ends; guarantees x[0] == x[-1] == 0 exactly."""
    x = np.asarray(x, dtype=np.float64).copy()
    n = len(x)
    if n < 4:
        return np.zeros(n)
    k = max(2, min(int(ms * SR / 1000.0), n // 2))
    x[:k] *= rcos(k)
    x[-k:] *= rcos(k)[::-1]
    x[0] = 0.0
    x[-1] = 0.0
    return x


def dc_kill(x):
    x = np.asarray(x, dtype=np.float64)
    return x - x.mean() if len(x) else x


def norm_peak(x, db=0.0):
    x = np.asarray(x, dtype=np.float64)
    p = float(np.max(np.abs(x))) if len(x) else 0.0
    if p < 1e-12:
        return x
    return x * (10.0 ** (db / 20.0) / p)


def norm_rms(x, db=0.0):
    x = np.asarray(x, dtype=np.float64)
    r = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    if r < 1e-12:
        return x
    return x * (10.0 ** (db / 20.0) / r)


def db2lin(db):
    return 10.0 ** (np.asarray(db, dtype=np.float64) / 20.0)


def noise(tag, n, pad=0):
    return rng(tag).standard_normal(int(n) + int(pad))


def transient(tag, n, lo, hi, tau, gain=1.0):
    """A filtered click — shaped noise, never a square wave.

    Every cue in this film starts with one of these.  It is a few milliseconds
    long and it is what makes the sound feel like a physical object rather than
    an oscillator being switched on.
    """
    n = int(n)
    z = np.zeros(n)
    m = min(int(tau * 8 * SR) + 8, n)
    z[:m] = bandpass(noise(tag, m), lo, hi) * np.exp(-(np.arange(m) / SR) / tau)
    a = max(int(0.0004 * SR), 1)
    z[:a] *= rcos(a)
    return gain * norm_peak(z, 0.0)


def partials(n, freqs, amps, taus, glide=None, glide_ms=45.0):
    """A tuned body: a few decaying sines, optionally sharing one pitch glide.

    `glide` is a ratio applied to every partial over `glide_ms` — that is how
    SFX_LATCH resolves a whole tone without ever sounding like two notes.
    """
    n = int(n)
    t = np.arange(n) / SR
    if glide is None:
        ratio = np.ones(n)
    else:
        g = int(min(max(glide_ms * SR / 1000.0, 1), n))
        r = np.ones(n) * glide
        r[:g] = 1.0 + (glide - 1.0) * smoothstep(np.arange(g) / g)
        ratio = r
    # a shared ratio curve -> phase must be integrated, not multiplied
    ph = TWO_PI * np.cumsum(ratio) / SR
    y = np.zeros(n)
    for f, a, tau in zip(freqs, amps, taus):
        y += a * np.sin(f * ph) * expdec(n, tau)
    return y


# ============================================== §3  equal-power placement

def place(bus, sig, start, gain_db=0.0, pan=0.0, pan_to=None):
    """Drop a mono cue onto the (2, N) bus at an exact sample.

    `pan_to` gives a cue a *travelling* stereo position on a smoothstep — used
    for `SFX_RULE`, which moves with the hairline it is the sound of.  Panning
    one mono source with an equal-power law is fully mono-compatible: the sum
    only changes level, never phase.
    """
    sig = np.asarray(sig, dtype=np.float64)
    if len(sig) == 0:
        return
    assert abs(sig[0]) < 1e-9 and abs(sig[-1]) < 1e-9, 'cue has non-zero edges'
    g = db2lin(gain_db)
    if pan_to is None:
        p = np.full(len(sig), float(pan))
    else:
        p = pan + (pan_to - pan) * smoothstep(np.linspace(0, 1, len(sig)))
    l = g * np.cos((p + 1.0) * math.pi / 4.0)
    r = g * np.sin((p + 1.0) * math.pi / 4.0)
    a, b = int(start), int(start) + len(sig)
    s0 = 0
    if a < 0:
        s0, a = -a, 0
    b = min(b, bus.shape[1])
    if b - a <= 0:
        return
    k = b - a
    bus[0, a:b] += l[s0:s0 + k] * sig[s0:s0 + k]
    bus[1, a:b] += r[s0:s0 + k] * sig[s0:s0 + k]


def pan_stereo(mono, pan):
    """Equal-power pan of a full-length mono buffer; `pan` may be an array."""
    p = np.asarray(pan, dtype=np.float64)
    return np.stack([mono * np.cos((p + 1.0) * math.pi / 4.0),
                     mono * np.sin((p + 1.0) * math.pi / 4.0)])


# ================================================== §4  the nine sounds
#
# Each generator returns a mono buffer, peak-normalised to 1.0, with exactly
# zero at both edges.  Level is applied later from the timeline, so the
# hit list's dB column is the single source of loudness truth.

def sfx_draw():
    """380 ms · a filtered noise swell with no pitch centre.

    The sound of a line being made.  Two complementary bands: the bright one
    peaks early, the low one peaks late, so the texture *darkens* across the
    gesture.  It swells, but it never rises — there is no upward pitch motion
    anywhere in it, which is what FILM.md rule 2 actually forbids.
    """
    n = int(0.380 * SR)
    t = np.linspace(0.0, 1.0, n)
    src = noise('draw', n)
    bright = bandpass(src, 1250.0, 3100.0)
    low = bandpass(src, 480.0, 1350.0)
    e_hi = np.sin(np.pi * np.clip(t / 0.62, 0, 1) ** 0.85) ** 1.6
    e_lo = np.sin(np.pi * np.clip((t - 0.18) / 0.82, 0, 1) ** 1.1) ** 1.3
    # a slow grain, like a nib on paper — keeps the swell from reading as a pad
    grain = onepole_lp(noise('draw', n), 26.0)
    grain = 0.82 + 0.18 * norm_peak(grain, 0.0)
    y = (bright * e_hi * 0.75 + low * e_lo * 1.0) * grain
    y = onepole_lp(y, 4200.0)
    return norm_peak(tail_out(dc_kill(y), ms=14.0), 0.0)


def _seat(dur, freqs, amps, taus, lp, bloom=0.0):
    n = int(dur * SR)
    body = partials(n, freqs, amps, taus)
    body *= damp(n, 1.05)
    thump = np.zeros(n)
    m = int(0.006 * SR)
    thump[:m] = onepole_lp(noise('seat', m), 380.0) * np.exp(
        -(np.arange(m) / SR) / 0.0016)
    y = (body / max(sum(amps), 1e-9)
         + 0.55 * norm_peak(thump, 0.0)
         + transient('seat', n, 1800.0, 9000.0, 0.0012, 0.22))
    if bloom > 0.0:
        y = y + bloom * onepole_lp(y, 900.0)
    y = onepole_lp(y, lp)
    return norm_peak(tail_out(dc_kill(y), ms=6.0), 0.0)


def sfx_seat():
    """160 ms · something mechanical seating into place.

    Octaves only (D2 + D3) — "fullest" must never become "a chord".  Used three
    times in the film and always for the same statement: *an object exists now.*
    """
    return _seat(0.160, [D2, D3, A3], [1.00, 0.62, 0.14],
                 [0.040, 0.030, 0.012], lp=2600.0)


def sfx_seat_long():
    """320 ms · the wordmark.  The fullest sound in the film, still not a chord."""
    return _seat(0.320, [D1, D2, D3], [0.55, 1.00, 0.46],
                 [0.130, 0.110, 0.070], lp=2200.0, bloom=0.22)


def _latch(dur, root, glide, tau, bloom):
    n = int(dur * SR)
    body = partials(n, [root, root * 2.0, root * 3.0],
                    [1.00, 0.30, 0.09],
                    [tau, tau * 0.62, tau * 0.40],
                    glide=glide, glide_ms=48.0)
    body *= damp(n, 0.9)
    y = body + transient('latch', n, 900.0, 4200.0, 0.0016, 0.20)
    if bloom > 0.0:
        # the only bloom in the film: a short, dark, diffuse skirt on the
        # recovery.  Two fixed allpass-ish taps, nothing that rings on.
        tail = np.zeros(n)
        for d, g in ((int(0.017 * SR), 0.34), (int(0.029 * SR), 0.22)):
            tail[d:] += g * y[:n - d]
        y = y + bloom * onepole_lp(tail, 2400.0)
    y = onepole_lp(y, 3600.0)
    return norm_peak(tail_out(dc_kill(y), ms=8.0), 0.0)


def sfx_latch():
    """140 ms · the PASS sound.  Resolves DOWN a whole tone, A3 -> G3.

    Used only when a state becomes good.  Warm, short, no shimmer.
    """
    return _latch(0.140, A3, G3 / A3, 0.042, bloom=0.0)


def sfx_latch_up():
    """260 ms · the RELEASE.  The inverse: G3 -> A3, resolving UP.

    f960, the hold letting go.  The only upward gesture before the end, and the
    only cue permitted any bloom at all.
    """
    return _latch(0.260, G3, A3 / G3, 0.075, bloom=0.30)


def _knock(dur, root, sub, tau, lp, tag):
    """A damped low knock.  No rise, no shimmer, no alarm — pending, not broken."""
    n = int(dur * SR)
    body = partials(n,
                    [root, sub, root * 2.76],
                    [1.00, 0.68, 0.085],
                    [tau, tau * 1.25, tau * 0.22])
    body *= damp(n, 1.35)                      # it stops; it does not ring on
    wood = transient(tag, n, 240.0, 1900.0, 0.0022, 0.30)
    y = onepole_lp(body + wood, lp)
    y = onepole_lp(y, lp * 1.6)                # 12 dB/oct — genuinely dark
    return norm_peak(tail_out(dc_kill(y), ms=10.0), 0.0)


def sfx_hold():
    """180 ms · the HOLD sound.  A damped knock on C3.  A door closing."""
    return _knock(0.180, C3, C2, 0.046, 1700.0, 'hold')


def sfx_hold_geo():
    """220 ms · the same knock a minor third below, on A2.  40 ms longer.

    holdNet vs holdGeo is the film's thesis.  These two cues must be
    distinguishable with your eyes shut, and a clean minor third is how.
    """
    return _knock(0.220, A2, A1, 0.060, 1350.0, 'hold_geo')


def _type(lp):
    """40 ms · an extremely quiet air tick.  One per line, never per character."""
    n = int(0.040 * SR)
    air = bandpass(noise('type', n), 2600.0, 8800.0)
    air *= expdec(n, 0.0058, atk=0.0006)
    ping = partials(n, [A5, D6], [0.5, 0.3], [0.0042, 0.0030])
    y = onepole_lp(air + 0.10 * ping, lp)
    return norm_peak(tail_out(dc_kill(y), ms=3.0), 0.0)


def sfx_type():
    return _type(11000.0)


def sfx_type_dull():
    """The same tick with the top rolled off — sober, for the line that lands
    under the holdGeo knock.  A bright tick there would sound like good news."""
    return _type(3200.0)


def _hairline(dur, fc, q, atk, dec, core_f, core_db, lp, tag):
    """A swipe: a tick at the head, then a narrow band of air travelling.

    THIS SOUND HAS NO PITCH MOTION, AND THAT IS THE POINT.

    It has been wrong twice, in two different directions.  First it was a
    granular *noise* sweep — broadband, 44 ms attack, spectral flatness 0.150 —
    structurally a brushed snare, and against §4's other cues (all of them
    transient-plus-tuned-body) it was the one sound the ear filed as
    percussion.  Replacing it with a tonal glide, two partials falling a whole
    tone A3 -> G3, fixed that and introduced a worse problem: a pitch falling
    is not the sound of a line being drawn, it is the sound of something
    deflating.  Four of them in forty seconds, each a small descending "wah",
    and the user heard them at second 6, second 14 and second 24 — f192, f426
    and f692/f735, which are exactly the windows SFX_RULE has in common.

    So this version moves nothing in pitch at all.  A hairline is a TRAVEL,
    and the travel is carried where the picture carries it: across the stereo
    field, by `Hit.pan -> Hit.pan_to` (§5, RULE_A -> RULE_B).  What sounds is
    a fixed narrow resonance — Q 3.4, about a third of an octave, so it reads
    as a *line* and not as a wash — with a soft 40 ms rise and a smooth fall,
    and one very short tuned tick at the head that is the pen touching down.
    The tick is on a chord tone, so the cue still belongs to §1's pitch object;
    it decays in 30 ms and never becomes a note.

    `atk` and `dec` are fractions of the cue's own length, so the envelope
    scales with the gesture instead of being retuned per variant.
    """
    n = int(dur * SR)
    t = np.linspace(0.0, 1.0, n)
    # a third of an octave of noise, standing still: the line itself
    air = biquad_ft(noise(tag, n), 'bp', fc, q)
    env = np.where(t < atk, smoothstep(t / atk), np.exp(-(t - atk) / dec))
    air = norm_peak(air * env, 0.0)
    # the pen touching down — tuned, mildly inharmonic, gone in 30 ms
    head = partials(n, [core_f, core_f * 2.01, core_f * 3.02],
                    [1.0, 0.24, 0.08], [0.030, 0.019, 0.011])
    y = onepole_lp(air + db2lin(core_db) * norm_peak(head, 0.0), lp)
    return norm_peak(tail_out(dc_kill(y), ms=10.0), 0.0)


def sfx_rule():
    """200 ms · the hairline drawing across, panned L -> R with it."""
    return _hairline(0.200, 2700.0, 3.4, 0.20, 0.26, A4, -7.0, 7000.0, 'rule')


def sfx_rule_short():
    """140 ms · the ray drawing out of the hub, and retracting into it.

    Same construction, a lower and slightly wider resonance, so the ray reads
    as a heavier object than the hairline without being any louder.
    """
    return _hairline(0.140, 1750.0, 2.6, 0.16, 0.20, D5, -9.0, 5200.0,
                     'rule_short')


def sfx_tick():
    """30 ms · one dry tick.  Digits and pose changes only."""
    n = int(0.030 * SR)
    body = partials(n, [C7, G7], [1.0, 0.42], [0.0044, 0.0032])
    y = body + transient('tick', n, 3800.0, 12000.0, 0.0011, 0.55)
    return norm_peak(tail_out(dc_kill(y), ms=2.5), 0.0)


def sfx_dead():
    """25 ms · one dry click.  No body, no tail.  The sound of something stopping.

    It has no tuned component at all, and it is over inside its own frame — so
    the 68 frames of silence that follow it at f622 are genuinely silent.
    """
    n = int(0.025 * SR)
    z = np.zeros(n)
    m = int(0.008 * SR)
    z[:m] = bandpass(noise('dead', m), 900.0, 6000.0) * np.exp(
        -(np.arange(m) / SR) / 0.0013)
    a = max(int(0.0003 * SR), 1)
    z[:a] *= rcos(a)
    return norm_peak(tail_out(dc_kill(z), ms=2.0), 0.0)


CUES = {
    'SFX_DRAW': sfx_draw,
    'SFX_SEAT': sfx_seat,
    'SFX_SEAT_LONG': sfx_seat_long,
    'SFX_LATCH': sfx_latch,
    'SFX_LATCH_UP': sfx_latch_up,
    'SFX_HOLD': sfx_hold,
    'SFX_HOLD_GEO': sfx_hold_geo,
    'SFX_TYPE': sfx_type,
    'SFX_TYPE_DULL': sfx_type_dull,
    'SFX_RULE': sfx_rule,
    'SFX_RULE_SHORT': sfx_rule_short,
    'SFX_TICK': sfx_tick,
    'SFX_DEAD': sfx_dead,
}


# =================================================== §5  the timeline (data)
#
# FILM.md §6.3, verbatim and in frame order.  54 discrete SFX_* hits.  If a
# frame is not in this list it is silent, and a cue can be retimed or repanned
# here without touching one line of synthesis.
#
# Pan follows the picture (FILM.md §2.3 / §2.4), halved so it stays subtle and
# mono-safe.  The copy column lives at x 160…940 (left of centre); the mark's
# canonical circle is at x 1290 (right of centre); C2's pair sits at 700 / 1220;
# the end card is dead centre.

PAN_MARK = +0.19        # the 520 px mark at (1350, 540)
PAN_COPY = -0.26        # the label / kicker column at x = 200
PAN_LINE = -0.22        # captions and readouts, a little wider than the label
PAN_BIG = -0.22         # the 176 px `503` lockup
PAN_ANNO = -0.10        # its annotations at x = 590
PAN_L = -0.17           # C2 left mark  (660, 462)
PAN_R = +0.17           # C2 right mark (1260, 462)
PAN_RAY = +0.23         # the holdGeo ray / off-country contact
RULE_A, RULE_B = -0.40, -0.10   # the hairline drawing x 200 -> 760
PAN_RUN = 0.0           # D1's five-state run is dead centre


@dataclass(frozen=True)
class Hit:
    f: int                       # frame — the cue's transient lands on its first sample
    cue: str
    db: float                    # peak level, dBFS, in the design domain
    pan: float = 0.0
    pan_to: float | None = None  # a travelling pan, on a smoothstep
    pre_ms: float = 0.0          # pre-roll BEFORE the frame boundary, never after
    note: str = ''


TIMELINE = [
    # ---- A1 open.mark ------------------------------------------------ f0
    Hit(8, 'SFX_DRAW', -24, PAN_MARK, pre_ms=40.0,
        note='two opposed arcs begin closing on the ring'),
    Hit(46, 'SFX_SEAT', -22, PAN_MARK, note='the core seats into the hub'),
    Hit(58, 'SFX_TICK', -38, +0.20, note='blip 1 of 3'),
    Hit(61, 'SFX_TICK', -38, +0.14, note='blip 2 of 3'),
    Hit(64, 'SFX_TICK', -38, +0.19, note='blip 3 of 3'),
    # f90 hard cut — no cue
    # ---- A2 open.where ----------------------------------------------- f90
    Hit(102, 'SFX_TYPE', -30, PAN_COPY, note='kicker CHECK ONE'),
    Hit(105, 'SFX_TYPE', -26, -0.22, note='hero "Where you are." — fuller'),
    # f180 hard cut — no cue
    # ---- A3 open.verify --------------------------------------------- f180
    Hit(186, 'SFX_TYPE', -30, PAN_COPY, note='label VERIFYING'),
    Hit(192, 'SFX_RULE', -28, RULE_A, RULE_B, note='the hairline, L->R'),
    Hit(198, 'SFX_TYPE', -32, PAN_LINE, note='readout "Confirming location…"'),
    # ---- A4 open.clear ---------------------------------------------- f255
    Hit(262, 'SFX_LATCH', -18, PAN_MARK,
        note='MORPH M1 verify -> clear.  The first state change, the first pass'),
    Hit(270, 'SFX_TYPE', -30, PAN_COPY, note='CLEARED enters'),
    Hit(273, 'SFX_TYPE', -32, PAN_LINE, note='caption "Confirmed in-country."'),
    Hit(278, 'SFX_TYPE', -34, PAN_LINE, note='readout "Toronto, CA — inside CA"'),
    # f330 hard cut — no cue
    # ---- B1 wire.how ------------------------------------------------ f330
    Hit(336, 'SFX_TYPE', -30, PAN_COPY, note='kicker CHECK TWO'),
    Hit(339, 'SFX_TYPE', -26, -0.22, note='hero "How the wire is."'),
    # f420 the match cut — deliberately silent
    # ---- B2 wire.slow ----------------------------------------------- f420
    Hit(426, 'SFX_RULE', -28, RULE_A, RULE_B, note='the hairline'),
    Hit(430, 'SFX_TYPE', -28, PAN_COPY,
        note='SLOW LINK · STILL ALLOWED — first amber.  No hold sound: '
             'nothing is being held'),
    Hit(450, 'SFX_TYPE', -32, PAN_LINE, note='readout "net 82 ms · api 273 ms"'),
    # ---- B3 wire.hold ----------------------------------------------- f510
    Hit(525, 'SFX_HOLD', -16, PAN_MARK,
        note='MORPH M2 clear -> holdNet.  The ring breaks; the first hold'),
    Hit(540, 'SFX_TYPE', -30, PAN_COPY, note='label HOLD · CONNECTION'),
    Hit(546, 'SFX_TYPE', -32, PAN_LINE, note='caption "No usable path."'),
    Hit(552, 'SFX_TYPE', -34, PAN_LINE, note='readout "internet down"'),
    # ---- B4 wire.off ------------------------------------------------ f615
    #      f615 the bed cuts to TRUE SILENCE, 6 empty frames
    Hit(621, 'SFX_DEAD', -20, PAN_MARK,
        note='the off mark fades up.  One dry click, then 68 frames of nothing'),
    # ---- C1 hold.geo ------------------------------------------------ f690
    Hit(692, 'SFX_RULE', -28, RULE_A, RULE_B, note='the hairline'),
    Hit(694, 'SFX_TYPE', -30, PAN_COPY,
        note='label CLEARED — the guard is visibly restored BEFORE location '
             'takes it away'),
    Hit(700, 'SFX_TYPE', -32, PAN_LINE, note='readout "Toronto, CA — inside CA"'),
    Hit(720, 'SFX_HOLD_GEO', -14, PAN_MARK,
        note='MORPH M3 clear -> holdGeo.  The biggest hit in the film, a minor '
             'third below f525 — the ear is being taught the difference'),
    Hit(728, 'SFX_TYPE_DULL', -32, PAN_LINE, note='label HOLD · LOCATION, sober'),
    Hit(735, 'SFX_RULE_SHORT', -30, PAN_MARK, PAN_RAY,
        note='the ray draws outward from the hub'),
    Hit(750, 'SFX_TICK', -26, PAN_RAY, note='the off-country contact lands'),
    # f780 hard cut — no cue
    # ---- C2 hold.which ---------------------------------------------- f780
    Hit(784, 'SFX_TYPE', -30, PAN_L, note='left label'),
    Hit(788, 'SFX_TYPE', -30, PAN_R, note='right label, 4 f behind'),
    Hit(791, 'SFX_TYPE', -28, 0.0, note='caption "Tower tells you which."'),
    Hit(841, 'SFX_TICK', -34, PAN_R, note='the attention lands on the right'),
    # f870 hard cut — no cue
    # ---- C3 hold.pending -------------------------------------------- f870
    Hit(873, 'SFX_SEAT', -22, PAN_BIG,
        note='the 176 px `503` appears — 3 frames after the cut, not 22.  '
             'The one cut in the film that changes the size of the world has '
             'to carry the event that changes it'),
    Hit(880, 'SFX_TYPE', -30, PAN_COPY, note='label PENDING'),
    Hit(886, 'SFX_TYPE', -28, PAN_LINE, note='caption "The turn survives."'),
    Hit(890, 'SFX_RULE', -28, RULE_A, RULE_B, note='the hairline'),
    Hit(894, 'SFX_TYPE', -34, PAN_ANNO, note='annotation "Retry-After"'),
    Hit(898, 'SFX_TYPE', -34, PAN_ANNO, note='annotation "Retrying · attempt 3/8"'),
    Hit(930, 'SFX_TICK', -24, PAN_ANNO,
        note='the digit 3 -> 4.  The only number that moves in the film'),
    # ---- C4 hold.clear ---------------------------------------------- f945
    Hit(960, 'SFX_LATCH_UP', -16, PAN_MARK,
        note='MORPH M5 — the hold lets go.  Resolves UP a whole tone, the '
             'inverse of SFX_HOLD.  The 503 leaves unaccompanied'),
    Hit(966, 'SFX_RULE_SHORT', -30, PAN_RAY, PAN_MARK, note='the ray retracts'),
    Hit(967, 'SFX_TYPE', -30, PAN_COPY, note='CLEARED'),
    Hit(972, 'SFX_TYPE', -32, PAN_LINE, note='readout "Toronto, CA — inside CA"'),
    Hit(1005, 'SFX_LATCH', -18, PAN_MARK,
        note='MORPH M1 again.  Identical to f262 — the film ends the way it began'),
    # f1020 the recompose cut — silent by design
    # ---- D1 end.set ------------------------------------------------ f1020
    #      Five 12-frame morphs, each its own cue.  The mark is dead centre,
    #      so the run is the one passage in the film that is panned to zero:
    #      the ear should not be able to place it either.
    Hit(1024, 'SFX_TYPE', -30, PAN_RUN, note='caption "Five states. One mark."'),
    Hit(1026, 'SFX_TICK', -30, PAN_RUN, note='clear -> verify'),
    Hit(1044, 'SFX_TICK', -28, PAN_RUN, note='verify -> holdNet, the ring breaks'),
    Hit(1062, 'SFX_TICK', -26, PAN_RUN,
        note='holdNet -> holdGeo.  The only place in the film where the ring '
             'RE-KNITS, and now it takes twelve frames to do it'),
    Hit(1080, 'SFX_DEAD', -24, PAN_RUN, note='holdGeo -> off'),
    #      f1092–1097 the off pose is always silent
    Hit(1098, 'SFX_LATCH', -20, PAN_RUN, note='off -> clear.  Home'),
    # f1110 hard cut — no cue
    # ---- D2 end.card ----------------------------------------------- f1110
    Hit(1113, 'SFX_SEAT_LONG', -16, 0.0,
        note='the wordmark.  No chord, no chime, no logo sting'),
    Hit(1117, 'SFX_TYPE', -28, 0.0, note='the tagline'),
    Hit(1140, 'SFX_TYPE', -30, -0.10, note='the address — the host'),
    Hit(1145, 'SFX_TICK', -30, +0.10, note='and the path, 5 f behind it'),
    #      f1160–1179 the bed decays to silence
    #      f1180–1199 TRUE SILENCE.  The film ends on a hold.
]

assert len(TIMELINE) == 57, 'the hit list and FILM.md §6.3 must agree'
assert all(h.cue in CUES for h in TIMELINE)
assert TIMELINE == sorted(TIMELINE, key=lambda h: h.f), 'the list must stay sorted'

# Frames that carry a hard cut and must not carry a sound of their own
# (FILM.md §6.3 rule 1).  Nothing may *start* here.
SILENT_CUTS = (90, 180, 330, 420, 690, 780, 870, 1020, 1110)
assert not any(h.f in SILENT_CUTS for h in TIMELINE), 'a cut carries no cue'


# ================================================= §6  the bed and textures
#
# The bed is a TUNED DRONE, not a room and not a noise floor.
#
# It used to be band-limited noise.  Measured in the delivered WAV that landed
# at a constant −31 dBFS RMS across nearly the whole film — only ~29 dB under
# the peak — which is audible, continuous hiss.  User verdict, and they are
# right: "who puts noise on a promo video".  A promo does not carry a noise
# floor.  So the bed is now four pure partials drawn from §1's pitch table, at
# a level well under the cues: the same musical object the sfx come from,
# rather than a room tone competing with them.
#
# It still never plays a melody and never develops.  Levels here are RMS
# (cue levels are peak); both live in one design domain and the master
# normalisation at the end preserves every relationship between them.

BED_RMS_DB = -50.0

# FILM.md §6.1 states the bed at −42 dBFS and the textures at −48, and §6.3
# states the loudest cue at −14 — one internally consistent *design* domain.
# The delivery instruction is different: normalise the true peak to −1 dBTP and
# keep the bed genuinely subliminal.  Those are only reconcilable by trimming
# the floor after the normalisation gain, which is what this is.
#
# The bed sits 13 dB below its old noise value.  Two reasons it can: a tuned
# drone at a fixed pitch is far easier to hear than broadband noise at the same
# RMS, so equal level would be *louder* in perception; and unlike a room tone,
# it has no job to do when nothing is sounding.  The textures keep their old
# trim — only the bed moved — so the hit list's internal relationships are
# untouched.
FLOOR_TRIM_DB = -4.0
BED_TRIM_DB = -4.0


# ------------------------------------------------- §6a  the teaser layer
#
# WHY THIS EXISTS.  The first cut of this score obeyed "more minimal" so
# literally that it became *empty*: one static note for forty seconds, no
# pulse, and two holes where nothing at all happened for 5.0 s (f270-420) and
# 3.0 s (f435-525).  User verdict: "this is too empty", refine for "a more
# teaser sound".  So three earlier rules are deliberately relaxed here, and
# only these three:
#
#   · "never changes chord"  -> the bed now moves, on state boundaries only.
#   · "no build"             -> there is one build, f870-944, and it is a
#                               pulse doubling, not a riser.
#   · "nothing rises"        -> one sub swell, f585-614, into the silence.
#
# Everything else holds. No whooshes, no percussion grid, no melody, no cue on
# a hard-cut frame, and the 68 frames of silence stay untouched — in fact the
# swell exists to make them bigger.
#
# THE PROGRESSION.  Five voicings, all inside the §1 pentatonic set, changing
# only where the picture changes state.  The third is the storyteller: absent
# while the guard is clear (an open fifth reads as unresolved, not as sad),
# arriving with the first hold, darkening under holdGeo, lifting on recovery.

VOICINGS = {
    # open fifth — spacious, unresolved, no third to colour it
    'OPEN':  {D1: 0.16, D2: 1.00, A2: 0.30},
    # the minor third arrives with the first hold
    'MINOR': {D1: 0.16, D2: 1.00, F3: 0.22, A2: 0.30},
    # holdGeo: C below the root pulls it flat and dark. The lowest voicing.
    'DARK':  {D1: 0.22, C2: 0.32, D2: 0.85, F3: 0.26},
    # the 503. The build is HARMONIC, not rhythmic: the b7 arrives on top of a
    # voicing that already has the third, so the chord thickens and refuses to
    # resolve. Density where a trailer would have put a drum.
    'TENSE': {D1: 0.28, C2: 0.34, D2: 0.92, F3: 0.32, C3: 0.20},
    # the recovery — the octave opens, the darkness leaves
    'LIFT':  {D1: 0.14, D2: 1.00, A2: 0.34, D3: 0.16},
    # the card — the only full chord in the film
    'FULL':  {D1: 0.16, D2: 1.00, F3: 0.20, A2: 0.34, D3: 0.20},
}

# (frame, voicing). Each change crossfades over CHORD_XFADE_F frames CENTRED on
# the frame, so a partial is never born or killed at full amplitude.
CHORD_PLAN = [
    (0,    'OPEN'),      # A1 — the mark draws onto nothing
    (510,  'MINOR'),     # B3 — the first hold arrives on the mark
    (780,  'DARK'),      # C2 — holdNet vs holdGeo, the thesis
    (870,  'TENSE'),     # C3 — the 503. The build, by density.
    (945,  'LIFT'),      # C4 — the recovery begins, unprompted
    (1080, 'FULL'),      # D2 — the card
]
CHORD_XFADE_F = 24

# NO PULSE, NO DRUMS — and this is a deliberate reversal.
#
# A rhythmic sub pulse was tried here and cut. User verdict: "the music
# shouldn't have drums because it messes up with the sound effects", which is
# correct and is the more important principle. Every cue in §4 is a transient
# plus a tuned body — i.e. structurally a drum hit. Putting an actual drum on a
# grid underneath them means the ear cannot tell which taps are the film
# TELLING you something and which are just tempo. The sfx are the rhythm
# section. Nothing else may compete for that job.
#
# So the film's energy is carried ENTIRELY by harmony and dynamics: the
# progression above, the section breathing below, and the one swell. Motion
# without metre.
#
# BREATHING. Each section gets a slow raised-cosine arc — the bed leans in and
# settles back over seconds, never on a beat. This is what keeps a sustained
# chord from reading as a held organ note. (start, peak, end, depth dB).
BREATH_ARCS = [
    (0,    120,  260,  +2.0),   # A — the mark draws on, the room opens
    (270,  330,  420,  +3.0),   # fills the old f270-420 hole, off-grid
    (420,  480,  520,  +2.5),   # B2, easing into the duck at f524
    (533,  585,  610,  +3.5),   # B3 — leans into the swell
    (690,  740,  790,  +2.5),   # C1 — the guard restored
    (790,  845,  868,  +3.0),   # C2 — the thesis, both marks live
    (870,  930,  944,  +5.0),   # C3 — THE BUILD, and it is dynamic, not metric
    (966,  1000, 1019, +2.5),   # C4 — release
    (1020, 1055, 1079, +3.0),   # D1 — the five-state run
    (1099, 1130, 1160, +3.5),   # D2 — the card blooms, then decays out
]

# THE SWELL — 30 frames of sub rising into the hard cut at f615, and nothing
# else in the film does this. It is not a whoosh: it is the existing root an
# octave down, gaining 9 dB and no brighter. The silence that follows is the
# loudest passage in the film and this is what makes it land.
SWELL_IN_F, SWELL_OUT_F = 585, 614
SWELL_DB = -34.0

# (frame, dB) breakpoints; `None` means digital silence.  FILM.md §6.1.
#  ANTICIPATION.  There used to be exactly ONE tension arc in forty seconds —
#  the bed thinning f930 -> f959 and releasing on f960 — and it is the best
#  thirty frames in the film, which makes its absence everywhere else the
#  problem.  The same shape now runs into the two other state changes that
#  matter: the ring breaking at f525 and the flip to holdGeo at f720.  In both
#  places the picture is already dead still, so the duck costs nothing and
#  turns a flat cut into a held breath.
BED_PLAN = [
    (0, BED_RMS_DB),
    (496, BED_RMS_DB),
    (524, -52.0),          # thins into MORPH M2 — the ring breaks on f525
    (525, -52.0),
    (533, BED_RMS_DB),
    (615, None),           # the off shot — hard duck, 0 ms
    (690, BED_RMS_DB),     # the guard is restored
    (692, BED_RMS_DB),
    (719, -52.0),          # thins into MORPH M3 — the flip on f720
    (720, -52.0),
    (728, BED_RMS_DB),
    (930, BED_RMS_DB),
    (959, -54.0),          # thins under the anticipation
    (960, -54.0),
    (966, BED_RMS_DB),     # the room comes back, under the release
    (1160, BED_RMS_DB),
    (1180, None),          # 20 frames, static picture, no sound
]

# Texture windows: (in_frame, out_frame, dB, pan).  A texture fades in over 8
# frames from `in`, and fades out over the 8 frames ENDING at `out + 1` — which
# is what "fades under the latch, one frame ahead of it" means, and which makes
# the f836–843 TEX_PING -> TEX_FENCE crossfade exact by construction.
TEX_FADE_F = 8
TEX_WINDOWS = {
    'TEX_SWEEP': [(66, 261, -48.0, PAN_MARK), (975, 1004, -48.0, PAN_MARK)],
    'TEX_PING': [(534, 614, -48.0, PAN_MARK), (805, 839, -44.0, PAN_L)],
    'TEX_FENCE': [(735, 779, -48.0, PAN_MARK), (841, 959, -48.0, PAN_R)],
}
TEX_RMS_REF = 0.0


def _bed_envelope():
    """Linear gain over the whole film, from the BED_PLAN breakpoints."""
    g = np.zeros(N)
    hard = int(0.002 * SR)          # 2 ms — reads as instant, but never clicks
    pts = BED_PLAN
    for i in range(len(pts) - 1):
        (f0, d0), (f1, d1) = pts[i], pts[i + 1]
        a, b = fs(f0), fs(f1)
        if d0 is None:
            continue                # silence runs to the next breakpoint
        if d1 is None or d0 == d1:
            g[a:b] = db2lin(d0)
        else:
            g[a:b] = db2lin(d0 + (d1 - d0) * rcos(b - a))
    f_last, d_last = pts[-1]
    if d_last is not None:
        g[fs(f_last):] = db2lin(d_last)

    # The final decay, f1160 -> f1180, arriving at exactly zero.
    a, b = fs(1160), fs(1180)
    g[a:b] *= rcos(b - a)[::-1]
    g[fs(1180):] = 0.0

    # The f615 duck and the f690 return are cuts, not fades — but a genuinely
    # 0-sample cut of a live noise floor *is* a broadband click at the floor's
    # own level, and a click is a sound, and f615 is supposed to be the moment
    # sound stops.  So each edge gets 2 ms (0.06 of a frame) of raised cosine:
    # far too short to read as a fade, long enough to have no transient.  The
    # duck ramp goes BEFORE the boundary so the bed is already at zero on the
    # first sample of f615; the return ramp goes after it.
    s = fs(615)
    g[s - hard:s] *= rcos(hard)[::-1]
    s = fs(690)
    g[s:s + hard] *= rcos(hard)

    # fade in from digital silence
    fi = int(0.030 * SR)
    g[:fi] *= rcos(fi)
    return g


def build_bed():
    """A tuned drone: D minor, four pure partials, no noise anywhere.

    Every frequency comes from §1's pitch table, so the bed is the same musical
    object as the cues that sound over it — a low D with its fifth and octave,
    sustained, never resolving and never moving.  There is no noise generator
    in here at all; noise survives in this score only *inside* a cue's own
    transient, where it is a click and not a floor.

    It breathes rather than sits still: each partial has its own very slow
    amplitude drift, at rates chosen to be mutually incommensurate so the sum
    never audibly repeats inside 40 s.  Depth is small — this is a bed that
    stays put, not a pad that swells.

    Mono safety: L and R carry identical partials at identical phase, and the
    stereo image comes only from the *drift phase* of the two upper voices.
    Amplitude differences sum on a mono speaker; they cannot cancel, which a
    decorrelated noise side could.
    """
    t = np.arange(N, dtype=np.float64) / SR

    #  drift rate (Hz), depth, stereo drift-phase offset — per partial, by index
    #  into the sorted partial set. Rates are mutually incommensurate.
    drift_spec = [(0.0143, 0.08, 0.00), (0.0197, 0.12, 0.00),
                  (0.0271, 0.16, 0.35), (0.0331, 0.20, 0.55),
                  (0.0389, 0.18, 0.20), (0.0433, 0.14, 0.45)]

    partial_set = sorted({f for v in VOICINGS.values() for f in v})
    amp_env = {f: _chord_amp_env(f) for f in partial_set}

    st = np.zeros((2, N))
    for i, f in enumerate(partial_set):
        rate, depth, width = drift_spec[i % len(drift_spec)]
        ph = TWO_PI * ((0.137 * (i + 1)) % 1.0)   # nothing starts aligned
        # ONE continuous oscillator per pitch, amplitude-enveloped by the
        # progression. Phase never resets, so a voicing change can never click
        # however abruptly the plan moves.
        tone = np.sin(TWO_PI * f * t + ph) * amp_env[f]
        for c in (0, 1):
            drift = 1.0 + depth * np.sin(
                TWO_PI * rate * t + ph + (width * np.pi if c else 0.0))
            st[c] += tone * drift

    # felt, never fizzy — the drone has no business above the speaking range
    for c in (0, 1):
        st[c] = onepole_lp(st[c], 1200.0)

    st *= db2lin(BED_RMS_DB + BED_TRIM_DB) / float(np.sqrt(np.mean(st ** 2)))
    env = (_bed_envelope() / db2lin(BED_RMS_DB)) * _breath_envelope()
    return st * env


def _chord_amp_env(freq):
    """Amplitude envelope for ONE partial across the whole progression.

    Piecewise-constant between CHORD_PLAN breakpoints, raised-cosine
    crossfaded over CHORD_XFADE_F frames centred on each change. A partial
    absent from a voicing simply has amplitude 0 there, so voices enter and
    leave by fading rather than by being switched.
    """
    g = np.zeros(N)
    half = int(CHORD_XFADE_F * SPF / 2)
    pts = [(f, VOICINGS[name].get(freq, 0.0)) for f, name in CHORD_PLAN]

    g[:] = pts[0][1]
    for i in range(1, len(pts)):
        f_at, a_to = pts[i]
        a_from = pts[i - 1][1]
        c = fs(f_at)
        a, b = max(0, c - half), min(N, c + half)
        g[b:] = a_to
        if b > a and a_from != a_to:
            g[a:b] = a_from + (a_to - a_from) * rcos(b - a)
        elif b > a:
            g[a:b] = a_to
    return g


def _breath_envelope():
    """Slow dynamic arcs over the bed — motion without metre.

    One raised-cosine hump per section from BREATH_ARCS, asymmetric (the rise
    and the fall have their own lengths, set by where `peak` sits), summed in
    dB and floored at 0. Nothing here repeats on a period, so it can never be
    heard as tempo — which is the entire point, because the sfx own the rhythm.
    """
    g_db = np.zeros(N)
    for (f0, f_pk, f1, depth) in BREATH_ARCS:
        a, p, b = fs(f0), fs(f_pk), fs(f1)
        if p > a:
            g_db[a:p] = np.maximum(g_db[a:p], depth * rcos(p - a))
        if b > p:
            g_db[p:b] = np.maximum(g_db[p:b], depth * rcos(b - p)[::-1])
    return db2lin(g_db)


def build_swell():
    """One sub swell, f585-614, into the hard cut to silence at f615.

    The root an octave down, rising 9 dB over 30 frames and getting no
    brighter — tension by weight, not by a riser's pitch sweep. It is cut, not
    faded, exactly on f615: the silence does the release.
    """
    y = np.zeros(N)
    a, b = fs(SWELL_IN_F), fs(SWELL_OUT_F + 1)
    n = b - a
    t = np.arange(n) / SR
    ramp = db2lin(-9.0 + 9.0 * smoothstep(np.linspace(0.0, 1.0, n)))
    tone = (np.sin(TWO_PI * D1 * t) + 0.42 * np.sin(TWO_PI * D2 * t))
    seg = tone * ramp
    seg[:int(0.020 * SR)] *= rcos(int(0.020 * SR))     # never click in
    y[a:b] = norm_peak(seg, 0.0) * db2lin(SWELL_DB)
    return np.stack([y, y])


def _tex_gain(name):
    """Per-texture linear gain over the whole film, from its windows."""
    g = np.zeros(N)
    for (f_in, f_out, db, _pan) in TEX_WINDOWS[name]:
        a, b = fs(f_in), fs(f_out + 1)
        fade = TEX_FADE_F * SPF
        seg = np.ones(b - a)
        k = min(fade, len(seg) // 2)
        seg[:k] = rcos(k)
        seg[-k:] = rcos(k)[::-1]
        g[a:b] = np.maximum(g[a:b], seg * db2lin(db + FLOOR_TRIM_DB))
    return g


def _tex_pan(name):
    p = np.zeros(N)
    for (f_in, f_out, _db, pan) in TEX_WINDOWS[name]:
        p[fs(f_in):fs(f_out + 1)] = pan
    return p


def _pulse_train(tag, period, phase, decay, lo, hi, tone=None, tone_a=0.0):
    """Soft filtered taps on a globally phase-locked grid.

    The mark's phase is global and never resets (FILM.md §2.10), so the taps are
    derived from absolute time, not from the window they happen to sound in.
    """
    n_tap = int(min(period, 0.30) * SR)
    tap = bandpass(noise(tag, n_tap), lo, hi) * expdec(n_tap, decay, atk=0.0018)
    if tone is not None:
        tap = tap + tone_a * partials(n_tap, [tone, tone * 2.0],
                                      [1.0, 0.25], [decay * 1.4, decay * 0.7])
    tap = norm_peak(tail_out(dc_kill(tap), ms=6.0), 0.0)
    y = np.zeros(N + n_tap)
    k = 0
    while True:
        s = int(round((phase + k * period) * SR))
        if s >= N:
            break
        if s >= 0:
            y[s:s + n_tap] += tap
        k += 1
    return y[:N]


def build_textures():
    """Three state textures, each at the mark's own period.  −48 dBFS RMS.

    They exist so the ear learns the same rhythm the eye is watching: the
    2.400 s sweep, the 1.4286 s sonar, the 8 s fence with its 2.856 s lunge.
    Outside the one sanctioned 8-frame crossfade, exactly one is ever audible —
    "one loudest thing at a time", in the ear.
    """
    t = np.arange(N) / SR
    out = np.zeros((2, N))

    # -- TEX_SWEEP: a barely-there rotating air, one revolution per 2.400 s.
    air = bandpass(noise('tex_sweep', N), 380.0, 1900.0)
    ang = TWO_PI * t / 2.400
    lobe = 0.34 + 0.66 * (0.5 + 0.5 * np.cos(ang)) ** 2.2
    sweep = norm_rms(air * lobe, TEX_RMS_REF)
    sweep_pan = _tex_pan('TEX_SWEEP') + 0.30 * np.sin(ang)
    out += pan_stereo(sweep * _tex_gain('TEX_SWEEP'), sweep_pan)

    # -- TEX_PING: two soft taps per 1.4286 s cycle, half a period apart —
    #    the holdNet sonar, exactly (design.md §2.7: pr = (P·0.7 + i·0.5) mod 1).
    ping = _pulse_train('tex_ping', 1.0 / 0.7 / 2.0, 0.0, 0.030,
                        620.0, 2400.0, tone=A3, tone_a=0.18)
    ping = norm_rms(ping, TEX_RMS_REF)
    out += pan_stereo(ping * _tex_gain('TEX_PING'), _tex_pan('TEX_PING'))

    # -- TEX_FENCE: an 8 s band-passed air, plus one dry tap per 2.856 s lunge
    #    (design.md §2.8: lunge = 6·(0.5 + 0.5·sin(P·2.2)), peak at P = 0.714).
    fence_air = bandpass(noise('tex_fence', N), 260.0, 1150.0)
    fence_air *= 0.45 + 0.55 * (0.5 + 0.5 * np.sin(TWO_PI * t / 8.000)) ** 1.4
    lunge = _pulse_train('tex_fence', 2.856, 0.714, 0.018, 400.0, 1600.0)
    fence = norm_rms(fence_air, TEX_RMS_REF) + 0.55 * norm_rms(lunge, TEX_RMS_REF)
    fence = norm_rms(fence, TEX_RMS_REF)
    out += pan_stereo(fence * _tex_gain('TEX_FENCE'), _tex_pan('TEX_FENCE'))
    return out


# ============================== §6b  space, altitude, and the motif
#
# Three things the score was missing, found by measuring rather than by taste:
#
#   · 95 % of all energy sat below 320 Hz. No ceiling. A film score with no
#     altitude reads as small however well the low end is voiced.
#   · Stereo width measured 0.133 side/mid — very nearly mono, and completely
#     dry. Nothing had a room to be in, so every cue sounded stuck to the
#     speaker instead of placed in a space.
#   · There was no TUNE. Harmony and dynamics, but nothing a person could
#     carry out of the room. A 40-second film can hold one idea; it should.

# ---- the room -----------------------------------------------------------
#
# An algorithmic IR: sparse early reflections, then an exponentially decaying
# diffuse tail, band-limited so it never adds hiss or mud. NOTE ON NOISE: the
# tail is generated from noise, and that is not the same mistake as the old
# noise bed. A reverb IR is *convolved with the signal*, so it is only ever
# audible while something is sounding — it is diffusion, not a floor. Between
# cues it decays to nothing, and the silences stay silent.
IR_DUR = 2.20            # s
IR_DECAY = 0.62          # s, e-fold — a small hall, not a cathedral
IR_PREDELAY_MS = 17.0
REVERB_DB = -15.0        # send level; the room supports, it never blooms
IR_LO, IR_HI = 220.0, 7200.0

# Early reflections: (delay ms, gain, pan). Asymmetric on purpose — a
# symmetric pattern images as a point, an asymmetric one images as a place.
_ER = [(11.0, 0.62, -0.35), (17.0, 0.55, +0.42), (23.0, 0.44, +0.18),
       (31.0, 0.38, -0.52), (43.0, 0.30, +0.61), (57.0, 0.24, -0.28)]


def fftconv(x, h):
    """Linear convolution via FFT. np.convolve would be O(n·m) and this is a
    1.92 M-sample signal — it has to be done in the frequency domain."""
    L = len(x) + len(h) - 1
    n = 1 << int(np.ceil(np.log2(L)))
    return np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(h, n), n)[:L]


def _build_ir():
    """Stereo IR: decorrelated tails, shared early-reflection geometry."""
    n = int(IR_DUR * SR)
    pre = int(IR_PREDELAY_MS * SR / 1000.0)
    t = np.arange(n) / SR
    decay = np.exp(-t / IR_DECAY)
    # the tail is decorrelated L/R so the room has width; the ER pattern is
    # shared so it still images as ONE room rather than two.
    ir = np.zeros((2, n))
    for c, tag in ((0, 'ir_l'), (1, 'ir_r')):
        tail = bandpass(noise(tag, n), IR_LO, IR_HI) * decay
        # a short build to the tail's peak — real rooms do not start at max
        build = np.minimum(1.0, t / 0.012)
        ir[c, pre:] = (tail * build)[:n - pre]
    for (ms, g, pan) in _ER:
        s = pre + int(ms * SR / 1000.0)
        if s < n:
            l = g * math.sqrt(0.5 * (1.0 - pan))
            r = g * math.sqrt(0.5 * (1.0 + pan))
            ir[0, s] += l
            ir[1, s] += r
    for c in (0, 1):
        ir[c] = onepole_hp(ir[c], 180.0)          # no rumble in the room
        ir[c] /= (np.sqrt(np.sum(ir[c] ** 2)) + 1e-12)   # unity energy
    return ir


def build_air():
    """Altitude: a very quiet high shimmer, tonal, slowly moving.

    Two partials a fifth apart in the top two octaves of the pitch set, each
    breathing on its own slow rate, panned wide and opposite. This is the
    layer that stops the mix reading as a dark hum; you should never be able
    to point at it, only notice its absence.
    """
    t = np.arange(N, dtype=np.float64) / SR
    st = np.zeros((2, N))
    # NOTE THE REGISTER, twice corrected by measurement. A4 (440 Hz) was tried
    # first and was not air but midrange — it took 60 % of the film's total
    # energy and read honky. D5/A5 was better and still sat entirely in the
    # presence band. Air is above 1 kHz; anything lower competes with the tune.
    for i, (f, a, rate, pan) in enumerate(
            [(A5, 1.00, 0.0171, -0.55), (D6, 0.70, 0.0233, +0.58),
             (A6, 0.34, 0.0307, +0.30), (D7, 0.16, 0.0367, -0.34)]):
        ph = TWO_PI * ((0.211 * (i + 1)) % 1.0)
        drift = 0.55 + 0.45 * np.sin(TWO_PI * rate * t + ph)
        tone = a * np.sin(TWO_PI * f * t + ph) * drift
        st[0] += tone * math.sqrt(0.5 * (1.0 - pan))
        st[1] += tone * math.sqrt(0.5 * (1.0 + pan))
    st *= db2lin(AIR_RMS_DB) / float(np.sqrt(np.mean(st ** 2)))
    # the air follows the bed's dynamics, so it ducks into every silence too
    return st * (_bed_envelope() / db2lin(BED_RMS_DB)) * _breath_envelope()


AIR_RMS_DB = -56.0

# ---- the motif ----------------------------------------------------------
#
# One idea, five statements, and it is the film's argument in miniature:
# a falling A - F - D. It is posed incomplete, held unresolved through both
# holds, and only completes when the guard clears ITSELF. Nobody restarts
# anything, and the tune finishes on its own.
#
#   (frame, note, dB, pan, decay s, note)
MOTIF = [
    (126,  A4, -30.0, +0.10, 2.6, 'the question. one note, and it is left open'),
    (352,  A4, -31.0, -0.12, 2.2, 'restated for the second lane'),
    (372,  F4, -32.0, +0.14, 2.8, 'falls to the third — still unresolved'),
    (556,  F4, -30.0, +0.16, 3.0, 'the first hold. it stops HERE, on the third'),
    (905,  A4, -29.0, -0.10, 1.9, 'the 503. it tries again'),
    (925,  F4, -30.0, +0.12, 2.2, 'and stalls on the same note. still no D'),
    (960,  D5, -25.0, +0.00, 3.6, 'THE RESOLUTION — on the recovery, unprompted'),
    (1104, D4, -27.0, +0.00, 4.2, 'the card. the same note, an octave down, home'),
]


def _bell(dur, f0, decay):
    """A soft struck tone. Harmonic, not inharmonic — a bell proper would
    fight a tuned bed; this is closer to a celeste, and it belongs to the
    chord underneath it."""
    n = int(dur * SR)
    y = partials(n,
                 [f0, f0 * 2.0, f0 * 3.0, f0 * 4.0],
                 [1.00, 0.34, 0.13, 0.05],
                 [decay, decay * 0.55, decay * 0.30, decay * 0.18])
    # a breath of attack noise, 4 ms, so it is struck rather than faded on
    y += 0.05 * transient('motif', n, 1800.0, 6500.0, 0.004)
    y *= np.minimum(1.0, np.arange(n) / (0.004 * SR))
    return norm_peak(tail_out(dc_kill(y), ms=24.0), 0.0)


# Struck at the levels in MOTIF the tune measured 68.5 % of the film's TOTAL
# energy — because a 3-second decay carries far more energy than its peak
# suggests, and peak is what those dB values set. The tune supports the cues;
# it does not outrank them. This is the trim that puts it back underneath.
MOTIF_TRIM_DB = -11.0


def build_motif():
    """The tune. Sparse by design — eight notes in forty seconds."""
    y = np.zeros((2, N + int(5.0 * SR)))
    for (f_at, note, db, pan, decay, _why) in MOTIF:
        sig = _bell(min(5.0, decay * 1.6), note, decay) * db2lin(
            db + MOTIF_TRIM_DB)
        s = fs(f_at)
        l = math.sqrt(0.5 * (1.0 - pan))
        r = math.sqrt(0.5 * (1.0 + pan))
        y[0, s:s + len(sig)] += sig * l
        y[1, s:s + len(sig)] += sig * r
    return y[:, :N]


# ==================================================== §7  mandated silence
#
# FILM.md is explicit that silence is a beat.  These spans are gated to exact
# digital zero after the master chain, so no filter tail can smear a whisper
# into a passage whose entire job is to be empty.

SILENCE_SPANS = [
    (615.0, 621.0, '6 empty frames — the bed cuts, 0 ms'),
    (621.75, 690.0, '68 frames of absolute silence, the loudest passage'),
    (1081.0, 1098.0, 'the off pose is always silent'),
    (1180.0, 1200.0, '20 frames, static picture, no sound'),
]


# ============================================================ §8  the mix

def true_peak(x, os_=4):
    """4x oversampled peak, in dBFS.  Blocked, so memory stays modest."""
    tp = 0.0
    blk, ov = 1 << 18, 4096
    for ch in x:
        s = 0
        while s < len(ch):
            seg = ch[max(s - ov, 0):min(s + blk + ov, len(ch))]
            m = len(seg)
            up = np.fft.irfft(np.fft.rfft(seg), m * os_) * os_
            tp = max(tp, float(np.max(np.abs(up))))
            s += blk
    return 20.0 * math.log10(max(tp, 1e-12))


PEAK_DBTP = -1.0        # delivery ceiling, true peak (4x oversampled)


def render_score(out_path=None, verbose=False):
    """Build the whole 40.000 s piece and (optionally) write the WAV."""
    t0 = time.time()

    def log(m):
        if verbose:
            print('  %-14s %5.1f s' % (m, time.time() - t0))

    # TWO BUSES. `dry` is everything that is already diffuse or already
    # everywhere — the bed, the air, the sub swell. Putting a room on a drone
    # only makes it muddy. `send` is everything that is an EVENT: the cues,
    # the state textures and the motif. Those are the things that need to
    # sound like they happened somewhere.
    bus = np.zeros((2, N))
    send = np.zeros((2, N))

    bus += build_bed()
    log('bed')
    bus += build_air()
    log('air')
    bus += build_swell()
    log('swell')
    send += build_textures()
    log('textures')
    send += build_motif()
    log('motif')

    cache = {}
    for h in TIMELINE:
        if h.cue not in cache:
            cache[h.cue] = CUES[h.cue]()
        start = fs(h.f) - int(round(h.pre_ms * SR / 1000.0))
        place(send, cache[h.cue], start, h.db, h.pan, h.pan_to)
    log('cues')

    bus += send
    ir = _build_ir()
    for c in (0, 1):
        bus[c] += fftconv(send[c], ir[c])[:N] * db2lin(REVERB_DB)
    log('reverb')

    # -- master chain.  No limiter and no saturation: the brief asks for a film
    #    that is quiet and un-squashed, and peak normalisation alone is enough
    #    when the loudest object is a 220 ms knock.
    #    12 dB/oct at 17 kHz only tames the noise chips' inter-sample overshoot.
    for c in (0, 1):
        bus[c] = onepole_lp(onepole_lp(bus[c], 17000.0), 17000.0)
        bus[c] = onepole_hp(bus[c] - bus[c].mean(), 22.0)

    for (fa, fb, _why) in SILENCE_SPANS:
        bus[:, fs(fa):fs(fb)] = 0.0

    tp = true_peak(bus)
    bus *= db2lin(PEAK_DBTP - tp)

    fi = int(0.030 * SR)
    bus[:, :fi] *= rcos(fi)
    bus[:, 0] = 0.0
    bus[:, -1] = 0.0
    log('master')

    # -- checks the film's honesty depends on
    assert bus.shape == (2, N), bus.shape
    assert np.all(np.isfinite(bus))
    assert float(np.max(np.abs(bus))) < 1.0, 'no clipping, anywhere'
    for (fa, fb, why) in SILENCE_SPANS:
        seg = bus[:, fs(fa):fs(fb)]
        assert float(np.max(np.abs(seg))) == 0.0, 'not silent: %s' % why

    if out_path:
        q = np.clip(np.rint(bus * 32767.0), -32768, 32767).astype(np.int16)
        frames = np.column_stack([q[0], q[1]]).astype('<i2').tobytes()
        d = os.path.dirname(os.path.abspath(out_path))
        if d:
            os.makedirs(d, exist_ok=True)
        with wave.open(out_path, 'wb') as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(frames)
        log('wav')
    return bus


# ============================================================ §9  analysis

def rms_arc(y, bucket=0.5):
    b = int(bucket * SR)
    m = (y[0] + y[1]) * 0.5
    out = []
    for s in range(0, len(m), b):
        seg = m[s:s + b]
        r = float(np.sqrt(np.mean(seg ** 2)))
        out.append((s / SR, 20.0 * math.log10(max(r, 1e-12))))
    return out


def _main(argv):
    out = argv[1] if len(argv) > 1 else DEFAULT_OUT
    t0 = time.time()
    y = render_score(out, verbose=True)
    dt = time.time() - t0

    n = y.shape[1]
    peak = float(np.max(np.abs(y)))
    print('\nwrote %s' % out)
    print('  %d samples/ch = %.6f s @ %d Hz, %d cues' % (n, n / SR, SR,
                                                         len(TIMELINE)))
    print('  sample peak %.2f dBFS   true peak %.2f dBTP   dc %.2e' %
          (20 * math.log10(peak), true_peak(y), float(y.mean())))
    print('  built in %.1f s' % dt)

    print('\nRMS envelope, 0.5 s buckets  (bar = 1 dB, floor -96 dB):')
    for t, db in rms_arc(y):
        f = int(round(t * FPS))
        tag = ''
        for h in TIMELINE:
            if 0 <= h.f - f < 15:
                tag = h.cue
                break
        bar = '#' * max(0, int(db + 96))
        print('  %5.1f s  f%-5d %8.2f dB  %-52s %s'
              % (t, f, db if db > -95 else float('-inf'), bar, tag))


if __name__ == '__main__':
    _main(sys.argv)
