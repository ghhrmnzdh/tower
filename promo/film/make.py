#!/usr/bin/env python3
"""make.py — the Tower film driver.

    python3 promo/film/make.py                 # the whole thing, all cores
    python3 promo/film/make.py --fast          # 720p / veryfast, for iteration
    python3 promo/film/make.py --frames 690:780 --stage frames
    python3 promo/film/make.py --stage encode --open

WHAT THIS DOES, IN ORDER
  1. fills a 1920x1080 RGB canvas with INK
  2. dispatches the frame to whichever scene module owns it (SHOTS, below)
  3. applies the global grade — vignette 0.32, grain 1, nothing else
  4. writes out/frames/f_%05d.png
  5. encodes libx264 crf 16 preset slow yuv420p +faststart
  6. muxes out/score.wav as AAC 192k / 48 kHz
  7. writes out/tower-film.mp4 and out/tower-film-poster.jpg

Frames render in parallel across processes. Every frame is a pure function of
its absolute index — no clock, no unseeded RNG, no neighbour-frame state — so
the work is embarrassingly parallel and frame N is byte-identical at any --jobs.
Frames are handed out in CONTIGUOUS chunks rather than round-robin, so a worker
stays inside one scene and its per-process caches (font faces, the supersampled
radar tile, the grain plates) actually hit.

ON THE SHARED MODULES.  brand.py and draw.py exist and are imported here. There
is no ui.py, on purpose. The four scene modules were authored in parallel and
each carries its own faithful copy of the mark; scene_wire probes for a
`ui.radar_tile` and would hand its mark over to one if it found it. The film's
structural match cut (f329 -> f420) depends on scene_open and scene_wire drawing
the mark with the *same* implementation, constant for constant. Introducing a
third implementation that only one of them adopts is the one change that
silently breaks it. If ui.py is ever written, both modules adopt it together or
neither does.
"""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from PIL import Image                                          # noqa: E402

import brand                                                   # noqa: E402
import draw as gdraw                                           # noqa: E402
from brand import FPS, H, INK, TOTAL, W, make_ctx              # noqa: E402

OUT = os.path.join(_HERE, 'out')
FRAMES = os.path.join(OUT, 'frames')
MP4 = os.path.join(OUT, 'tower-film.mp4')
POSTER = os.path.join(OUT, 'tower-film-poster.jpg')
WAV = os.path.join(OUT, 'score.wav')
SCORE_PY = os.path.join(_HERE, 'score.py')

# ══════════════════════════════════════════════════════════════════════════
#  THE SHOT TABLE — FILM.md §1
#
#  Four contiguous module ranges tiling 0..1199 with no gap and no overlap.
#  Inclusive on both ends.
# ══════════════════════════════════════════════════════════════════════════

SHOTS = [
    # module        first  last   act   owns
    ('scene_open',     0,   329),  # A  cold open + the fence lane
    ('scene_wire',   330,   689),  # B  the wire lane + `off`
    ('scene_hold',   690,  1019),  # C  off-country -> holdGeo -> PENDING
    ('scene_end',   1020,  1199),  # D  the five-state run + the card
]


def _assert_tiling():
    """The shot table must tile 0..1199 exactly. Checked at import, not at
    render — a gap discovered on frame 700 has already cost you 700 frames."""
    assert SHOTS, 'empty shot table'
    cursor = 0
    for name, a, b in SHOTS:
        assert a == cursor, (
            f'{name} starts at {a}, expected {cursor} — '
            f'{"gap" if a > cursor else "overlap"} in the shot table')
        assert b >= a, f'{name} has a backwards range {a}..{b}'
        cursor = b + 1
    assert cursor == TOTAL, (
        f'shot table covers {cursor} frames, need exactly {TOTAL}')
    # and each module appears exactly once, so a module's shots are contiguous
    names = [s[0] for s in SHOTS]
    assert len(names) == len(set(names)), 'a module owns two disjoint ranges'


_assert_tiling()


def shot_of(f: int):
    """(module_name, first, last) owning absolute frame f."""
    for name, a, b in SHOTS:
        if a <= f <= b:
            return name, a, b
    raise IndexError(f'frame {f} is outside 0..{TOTAL - 1}')


# ══════════════════════════════════════════════════════════════════════════
#  RENDER
# ══════════════════════════════════════════════════════════════════════════

_MODS: dict = {}


def _mod(name):
    m = _MODS.get(name)
    if m is None:
        m = importlib.import_module(name)
        if not hasattr(m, 'draw'):
            raise AttributeError(
                f'{name}.py does not expose draw(ctx) — the scene contract')
        _MODS[name] = m
    return m


def render_frame(f: int) -> Image.Image:
    """Frame `f`, graded, as an opaque RGB Image. Pure function of f."""
    name, a, b = shot_of(f)
    img = Image.new('RGB', (W, H), INK)
    _mod(name).draw(make_ctx(f, img, a, b))
    return gdraw.apply_grade(img, f)


_JOB = {}          # per-worker settings, set once by _init


def _init(fast: bool):
    _JOB['fast'] = fast
    # Pillow's own thread pool fights the process pool on a big -j.
    os.environ.setdefault('OMP_NUM_THREADS', '1')


def _render_chunk(span):
    """Render an inclusive [lo, hi] span in one worker. Returns (n, bytes)."""
    lo, hi = span
    fast = _JOB.get('fast', False)
    n = 0
    total_bytes = 0
    for f in range(lo, hi + 1):
        im = render_frame(f)
        if fast:
            im = im.resize((1280, 720), Image.LANCZOS)
        p = os.path.join(FRAMES, 'f_%05d.png' % f)
        # compress_level 1. PNG is the whole cost of this stage — the grain is
        # noise by construction, so zlib has nothing to find and the levels
        # above 1 buy ~7% of file size for ~35% of the wall clock (measured:
        # cl1 1.70 s/675 kB, cl3 2.30 s/631 kB, cl6 3.64 s/552 kB per frame,
        # against 0.46 s to draw the frame and 0.28 s to grade it). Lossless
        # either way, and ffmpeg reads each file exactly once.
        im.save(p, 'PNG', compress_level=1)
        n += 1
        total_bytes += os.path.getsize(p)
    return n, total_bytes


def stage_frames(lo, hi, jobs, fast):
    os.makedirs(FRAMES, exist_ok=True)
    count = hi - lo + 1
    if jobs <= 1:
        _init(fast)
        _render_chunk((lo, hi))
        return count

    # contiguous chunks, ~4 per worker so a straggler scene can be stolen
    import concurrent.futures as cf
    target = max(1, count // (jobs * 4))
    spans = [(s, min(s + target - 1, hi)) for s in range(lo, hi + 1, target)]
    done = 0
    t0 = time.time()
    with cf.ProcessPoolExecutor(max_workers=jobs,
                                initializer=_init, initargs=(fast,)) as ex:
        for n, _ in ex.map(_render_chunk, spans):
            done += n
            el = time.time() - t0
            rate = done / el if el > 0 else 0
            sys.stderr.write('\r  frames %5d/%-5d  %5.1f f/s  eta %4.0fs'
                             % (done, count, rate,
                                (count - done) / rate if rate else 0))
            sys.stderr.flush()
    sys.stderr.write('\n')
    return done


# ══════════════════════════════════════════════════════════════════════════
#  ENCODE
# ══════════════════════════════════════════════════════════════════════════

def _run(cmd, what):
    """Run ffmpeg. On failure: print the command and the tail of stderr, and
    exit non-zero — a silent ffmpeg failure that leaves a 0-byte mp4 behind is
    the single most expensive way to lose an hour here."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print('\n!! %s FAILED (exit %d)\n' % (what, p.returncode),
              file=sys.stderr)
        print('   command:\n     %s\n' % ' '.join(cmd), file=sys.stderr)
        tail = (p.stderr or '').strip().splitlines()[-40:]
        print('   last %d lines of stderr:' % len(tail), file=sys.stderr)
        for line in tail:
            print('     ' + line, file=sys.stderr)
        sys.exit(1)
    return p


def ensure_score():
    if os.path.exists(WAV) and os.path.getsize(WAV) > 1000:
        return False
    print('  score.wav missing — running score.py')
    p = subprocess.run([sys.executable, SCORE_PY, WAV],
                       capture_output=True, text=True)
    if p.returncode != 0 or not os.path.exists(WAV):
        print(p.stdout, file=sys.stderr)
        print(p.stderr, file=sys.stderr)
        sys.exit('score.py failed')
    return True


def stage_encode(fast):
    ensure_score()
    pat = os.path.join(FRAMES, 'f_%05d.png')
    if not os.path.exists(pat % 0):
        sys.exit('no frames on disk — run --stage frames first')

    vopts = (['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23']
             if fast else
             ['-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
              '-x264-params', 'aq-mode=3'])

    cmd = ['ffmpeg', '-y',
           '-framerate', str(FPS), '-start_number', '0', '-i', pat,
           '-i', WAV,
           *vopts,
           '-pix_fmt', 'yuv420p',
           '-r', str(FPS),
           '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
           '-shortest', '-movflags', '+faststart',
           MP4]
    _run(cmd, 'encode')

    # poster — the end card, the frame the film is arguing toward
    _run(['ffmpeg', '-y', '-i', pat % POSTER_FRAME,
          '-q:v', '2', POSTER], 'poster')


POSTER_FRAME = 1185


# ══════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════

def main():
    global POSTER_FRAME
    ap = argparse.ArgumentParser(description='render the Tower film')
    ap.add_argument('--fast', action='store_true',
                    help='720p / veryfast / crf 23, for iteration')
    ap.add_argument('--frames', metavar='A:B',
                    help='render only this inclusive frame subrange')
    ap.add_argument('--stage', choices=('frames', 'encode', 'all'),
                    default='all')
    ap.add_argument('--jobs', '-j', type=int, default=os.cpu_count() or 4)
    ap.add_argument('--open', action='store_true', dest='do_open')
    ap.add_argument('--poster-frame', type=int, default=POSTER_FRAME)
    a = ap.parse_args()
    POSTER_FRAME = a.poster_frame

    lo, hi = 0, TOTAL - 1
    if a.frames:
        s, _, e = a.frames.partition(':')
        lo, hi = int(s), int(e or s)
        lo, hi = max(0, lo), min(TOTAL - 1, hi)
        if hi < lo:
            sys.exit('--frames A:B with B < A')

    os.makedirs(OUT, exist_ok=True)
    timings = []
    t_all = time.time()

    print('Tower film — %d frames, %d shots, %s'
          % (TOTAL, len(SHOTS), '1280x720 fast' if a.fast else '1920x1080'))
    for name, s, e in SHOTS:
        print('   %-11s %5d .. %-5d  %4d f  %6.3f s'
              % (name, s, e, e - s + 1, (e - s + 1) / FPS))

    if a.stage in ('frames', 'all'):
        t = time.time()
        n = stage_frames(lo, hi, max(1, a.jobs), a.fast)
        timings.append(('render %d frames (j=%d)' % (n, a.jobs),
                        time.time() - t))

    if a.stage in ('encode', 'all'):
        if lo != 0 or hi != TOTAL - 1:
            print('  (skipping encode — a partial frame range was rendered)')
        else:
            t = time.time()
            fresh = ensure_score()
            if fresh:
                timings.append(('score.py', time.time() - t))
            t = time.time()
            stage_encode(a.fast)
            timings.append(('encode + mux + poster', time.time() - t))

    timings.append(('TOTAL', time.time() - t_all))
    print('\n  stage                              seconds')
    print('  ' + '-' * 42)
    for label, secs in timings:
        print('  %-32s %8.1f' % (label, secs))

    if os.path.exists(MP4):
        print('\n  %s  (%.1f MB)' % (MP4, os.path.getsize(MP4) / 1e6))
    if a.do_open and os.path.exists(MP4):
        subprocess.run(['open', MP4])


if __name__ == '__main__':
    main()
