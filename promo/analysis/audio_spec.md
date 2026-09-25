# Tower — 60 s promo score + sound design spec

**Deliverable:** `promo/media/tower_promo.wav` — 48 000 Hz, 16-bit PCM, stereo,
60.000 s exactly (2 880 000 frames).
**Constraint:** synthesized from scratch, `numpy` only. No samples, no `scipy`,
no `sox`, no external libs. `wave` (stdlib) or a hand-written RIFF header for
the file. Everything below is specified to be implementable literally.

Working precision is `float64` end-to-end; the only quantisation is the final
int16 conversion (§9.6).

---

## 0. Conventions research → what this spec inherits

Trailer/tech-promo scoring has a stable grammar, and this spec follows it rather
than inventing one:

- **Three acts plus a fourth.** Setup → build → climax, then a short, punchy
  fourth act for the titles/logo after a stop-down. ([Nathan Fields][nf],
  [Master the Score][mts], [Richard Pryn][rp])
- **Stop-downs are structural.** A cue wants 2–3 moments of *complete silence*,
  typically at act boundaries; the "big hit → pause" is the editor's natural cut
  point. ([Richard Pryn][rp], [Rareform][rf])
- **Risers/swells/whooshes are the announcement** that a cut is coming; they are
  the connective tissue between acts. ([Rareform][rf], [Point Blank][pb])
- **The impact is always a layer stack** — distorted kick + sub + a mid crunch +
  a processed cymbal + an atmospheric tail — never one sound. ([Ableton][ab])
- **The braam** is the low-brass swell that punctuates cuts: detuned saw stack an
  octave low + a sub oscillator + drive + a resonant LP, with a pulsing swell.
  ([Ableton][ab], [Uppbeat][ub], [Baratatronix][bx])
- **Reverse cymbal into the downbeat** is the canonical lead-in to an impact.
  ([Point Blank][pb], [Motion Array][ma])
- **Riser design** = start subtle, grow: pitch rise + filter sweep (≈150 Hz →
  ≈10 kHz) + rising resonance, and gate/tremolo it in the last bar.
  ([Unison][un], [Point Blank][pb], [How To Make Electronic Music][htm])
- **Tempo.** Product/tech promo beds sit ~90–110 BPM when captions need room,
  110–140 BPM when the piece is the energy. ([TunePocket][tp], [AudioJungle][aj])
  This piece is the energy → **128 BPM**, which also lands a whole number of bars
  in 60 s (below).

*On-brand note (docs/DESIGN.md):* Tower's design law is "quiet tower, clear
signal — motion is earned; failure never bounces." The audio obeys the same
rule: the **denied/off-country beat is a held, amber-coloured pulse, not a harsh
alarm** (§7.4) — it must read as *pending*, not *broken*, exactly like the amber
hold states. The **confirm chime rises a perfect fifth** (§7.5) — the one place
in the piece that resolves upward.

[nf]: https://www.nathanfieldsmusic.com/blog/three-act-structure-trailer-music
[mts]: https://www.masterthescore.com/article/how-to-write-trailer-music-a-step-by-step-guide
[rp]: https://richardpryn.com/how-to-structure-trailer-music/
[rf]: https://www.rareformaudio.com/blog/how-production-music-reveals-trailer-structure
[pb]: https://www.pointblankmusicschool.com/blog/designing-unique-risers-and-fx-for-transitions-to-level-up-your-tracks/
[ab]: https://www.ableton.com/en/blog/learn-how-to-make-high-impact-sounds-for-movies-and-trailers/
[ub]: https://uppbeat.io/sfx/category/film/braam
[bx]: https://www.baratatronix.com/blog/brass-synthesis
[ma]: https://motionarray.com/sound-effects/riser-cymbal-1195693/
[un]: https://unison.audio/how-to-create-risers/
[htm]: https://howtomakeelectronicmusic.com/how-to-create-an-effective-rising-build-up/
[tp]: https://www.tunepocket.com/music-product-videos/
[aj]: https://audiojungle.net/category/music/corporate/tech

---

## 1. Tempo, grid, form

| Quantity | Value | Samples @ 48 kHz |
|---|---|---|
| Sample rate `SR` | 48 000 Hz | — |
| Tempo | **128.000 BPM**, 4/4 | — |
| Beat | 0.468 75 s | **22 500** |
| Bar (4 beats) | 1.875 s | **90 000** |
| 8th | 0.234 375 s | 11 250 |
| **16th (the grid)** | 0.117 187 5 s | **5 625** |
| 32nd | 0.058 593 75 s | 2 812.5 → use 2 812 (only for type ticks) |
| Total | **32 bars = 60.000 s** | **2 880 000** |

128 BPM is chosen so that 32 bars is *exactly* 60 s and every 16th is an integer
sample count — no accumulating drift, no fractional-sample scheduling anywhere
except the 32nd-note typewriter ticks, which are deliberately humanised anyway.

```python
SR   = 48_000
BPM  = 128.0
SPB  = SR * 60.0 / BPM          # 22500.0 samples per beat
BAR  = int(4 * SPB)             # 90000
STEP = int(SPB / 4)             # 5625  (16th)
N    = 32 * BAR                 # 2880000
def at(bar, beat=0.0, six=0.0): # 1-indexed bar, 0-indexed beat/16th
    return int((bar - 1) * BAR + beat * SPB + six * STEP)
```

### Key / scale

**F natural minor (Aeolian)**, root F. Dark, wide, and the bVI–bVII cadence
gives the drop lift without turning major/"corporate cheerful".

Exact equal-tempered frequencies (A4 = 440 Hz), the only pitch table the
implementation needs:

| Note | MIDI | Hz | Note | MIDI | Hz | Note | MIDI | Hz |
|---|---|---|---|---|---|---|---|---|
| C1  | 24 | 32.703 | C3  | 48 | 130.813 | C5  | 72 | 523.251 |
| Db1 | 25 | 34.648 | Db3 | 49 | 138.591 | Db5 | 73 | 554.365 |
| Eb1 | 27 | 38.891 | Eb3 | 51 | 155.563 | Eb5 | 75 | 622.254 |
| F1  | 29 | **43.654** | F3 | 53 | **174.614** | F5 | 77 | 698.456 |
| G1  | 31 | 48.999 | G3  | 55 | 195.998 | G5  | 79 | **783.991** |
| Ab1 | 32 | **51.913** | Ab3 | 56 | **207.652** | Ab5 | 80 | 830.609 |
| Bb1 | 34 | 58.270 | Bb3 | 58 | 233.082 | Bb5 | 82 | 932.328 |
| C2  | 36 | 65.406 | C4  | 60 | **261.626** | C6  | 84 | 1046.502 |
| Db2 | 37 | **69.296** | Db4 | 61 | 277.183 | Db6 | 85 | 1108.731 |
| Eb2 | 39 | **77.782** | Eb4 | 63 | **311.127** | Eb6 | 87 | 1244.508 |
| F2  | 41 | **87.307** | F4 | 65 | 349.228 | F6 | 89 | 1396.913 |
| G2  | 43 | 97.999 | G4  | 67 | **391.995** | G6 | 91 | 1567.982 |
| Ab2 | 44 | 103.826 | Ab4 | 68 | 415.305 | Ab6 | 92 | 1661.219 |

Or compute: `f(midi) = 440.0 * 2 ** ((midi - 69) / 12)`.

### Harmony

4-bar loop, **i – i – bVI – bVII** = `Fm | Fm | Db | Eb`. Bass roots:
`F1 43.654 → F1 → Db2 69.296 → Eb2 77.782`.
Pad voicings (top three voices move, root doubled at F2):

| Chord | Pad notes (Hz) |
|---|---|
| Fm(add9) | F3 174.614 · Ab3 207.652 · C4 261.626 · G4 391.995 |
| Db maj9  | Db3 138.591 · F3 174.614 · Ab3 207.652 · C4 261.626 |
| Eb sus2/4| Eb3 155.563 · F3 174.614 · Bb3 233.082 · C4 261.626 |

**Arp / pulse pattern** (16ths, 8-step, repeats twice per bar), degrees over the
current chord root; concrete Hz for the Fm bars:

`F3 174.614 · C4 261.626 · Ab3 207.652 · C4 261.626 · Eb4 311.127 · C4 261.626 · Ab3 207.652 · G3 195.998`

Transpose the same shape by −4 semitones for the Db bar (×0.79370) and −2 for
the Eb bar (×0.89090) — i.e. multiply the whole pattern by `2**(-4/12)` and
`2**(-2/12)`. (Multiplying frequencies keeps the additive band-limit logic in
§3.2 valid without a second table.)

---

## 2. Core numpy DSP primitives

Build these first; every layer is expressed in terms of them. All are numpy-only
and all avoid per-sample Python loops on long buffers.

### 2.1 Phase from an instantaneous-frequency curve

Never `np.mod` a phase and never restart it — glides and vibrato must be
phase-continuous or you get a click at every update.

```python
def phase(f, sr=SR, phi0=0.0):
    """f: (N,) instantaneous freq in Hz -> (N,) phase in radians."""
    return phi0 + 2*np.pi*np.cumsum(f)/sr
```

### 2.2 Band-limited additive saw / square (§ anti-alias law, §10.2)

Sum harmonics only up to `K` such that `K * f_max <= 0.45 * SR` (21 600 Hz),
which leaves a guard band under Nyquist. Apply a **Lanczos sigma taper** to kill
Gibbs ringing on the truncated series.

```
saw(φ)    = (2/π) · Σ_{k=1..K}  σ_k · (-1)^(k+1) · sin(kφ) / k
square(φ) = (4/π) · Σ_{k=1,3,5..K} σ_k · sin(kφ) / k
σ_k       = sinc(k / (K+1)) = sin(π k /(K+1)) / (π k /(K+1))
K         = max(1, floor(0.45 · SR / f_max))          # f_max = max(f[:]) over the segment
```

```python
def bl_saw(f, sr=SR, phi0=0.0):
    ph = phase(f, sr, phi0); fmax = float(np.max(f))
    K  = max(1, int(0.45*sr/fmax))
    y  = np.zeros_like(ph)
    for k in range(1, K+1):
        s = np.sinc(k/(K+1))                       # np.sinc is sin(pi x)/(pi x)
        y += s * ((-1)**(k+1)) * np.sin(k*ph)/k
    return (2/np.pi)*y
```

`f_max` **must** include glide/vibrato extremes, not the nominal pitch. For
`f_max = 700 Hz` this is K=30 partials; for the sub at 43.654 Hz it is K=494 —
so use a *pure sine* for the sub (§3.1) and cap K at 64 for anything above 200 Hz
(higher partials are inaudible against the noise layers and cost time).

### 2.3 One-pole lowpass, exact, loop-free (LTI / constant cutoff)

Evaluate the analytic transfer function on the rfft bins. Verified to
4.4e-16 max error against the sample recurrence.

```python
def onepole_lp(x, fc, sr=SR):
    a = 1 - np.exp(-2*np.pi*fc/sr)
    n = len(x); M = 1 << int(np.ceil(np.log2(n + 8192)))   # pad: no circular wrap
    w = 2*np.pi*np.fft.rfftfreq(M)
    H = a / (1 - (1-a)*np.exp(-1j*w))
    return np.fft.irfft(np.fft.rfft(x, M) * H, M)[:n]
```

`onepole_hp(x, fc) = x - onepole_lp(x, fc)`. A 12 dB/oct slope = apply twice.

### 2.4 Biquad (RBJ cookbook) — for resonance, short segments only

Direct-form-I with a Python loop; acceptable because it is only ever run on
bursts < 0.5 s (~24 000 samples). For long buffers use §2.3 or §2.5.

```
ω0 = 2π f0/SR ;  α = sin(ω0)/(2Q)
LP:  b = [(1-cos ω0)/2, 1-cos ω0, (1-cos ω0)/2]
HP:  b = [(1+cos ω0)/2, -(1+cos ω0), (1+cos ω0)/2]
BP:  b = [α, 0, -α]                     (constant 0 dB peak: b = [Q·α, 0, -Q·α])
a = [1+α, -2 cos ω0, 1-α]               ; normalise all by a[0]
y[n] = b0 x[n] + b1 x[n-1] + b2 x[n-2] - a1 y[n-1] - a2 y[n-2]
```

Serial cascade for steeper slopes. Bandpass "BP low..high" in this doc means
`onepole_hp(onepole_lp(x, high), low)` unless a Q is given, in which case use the
biquad.

### 2.5 Time-varying filter — STFT mask (risers, pad sweeps, whooshes)

The only correct way to do a smooth filter *sweep* over seconds without a
per-sample loop. Hann window, 75 % overlap = COLA-exact.

```python
def stft_filter(x, mask_fn, nfft=2048, hop=512, sr=SR):
    """mask_fn(t_sec, freqs)->(F,) gain in [0,1] for the frame centred at t_sec."""
    w = np.hanning(nfft+1)[:nfft]                     # periodic Hann
    n = len(x); pad = nfft
    xp = np.concatenate([np.zeros(pad), x, np.zeros(nfft*2)])
    frames = 1 + (len(xp)-nfft)//hop
    idx = np.arange(nfft)[None,:] + hop*np.arange(frames)[:,None]
    F  = np.fft.rfft(xp[idx]*w, axis=1)
    fr = np.fft.rfftfreq(nfft, 1/sr)
    for i in range(frames):                            # frames ≈ 5600 for 60 s: fine
        F[i] *= mask_fn((i*hop + nfft/2 - pad)/sr, fr)
    out = np.zeros(len(xp)); acc = np.zeros(len(xp))
    blk = np.fft.irfft(F, nfft, axis=1)*w
    for i in range(frames):
        s = i*hop; out[s:s+nfft] += blk[i]; acc[s:s+nfft] += w*w
    return (out/np.maximum(acc,1e-9))[pad:pad+n]
```

Mask helpers (`fr` = bin freqs, all vectorised):

```
LP mask,  cutoff fc, slope s dB/oct:  10 ** (-(s/6) * np.log2(np.maximum(fr,1)/fc).clip(0) / 20 * 6)
        simpler: 1/np.sqrt(1+(fr/fc)**(2*order))            # Butterworth magnitude
HP mask:  (fr/fc)**order / np.sqrt(1+(fr/fc)**(2*order))
BP+Q  :   1/np.sqrt(1 + Q**2*(fr/fc - fc/np.maximum(fr,1))**2)
```

### 2.6 Comb / allpass / delay — exact block recurrence

`y[n] = x[n] + g·y[n-D]` is a recurrence, but samples `n` and `n-D` are `D`
apart, so it vectorises into `N/D` block operations. **Verified bit-exact (max
error 0.0) against the sample loop.**

```python
def comb(x, D, g):
    y = x.astype(np.float64).copy()
    for s in range(D, len(y), D):
        e = min(s+D, len(y)); y[s:e] += g*y[s-D:e-D]
    return y

def allpass(x, D, g):
    v = -g*x.copy(); v[D:] += x[:-D]          # v[n] = x[n-D] - g x[n]
    return comb(v, D, g)                       # then y[n] = v[n] + g y[n-D]

def delay(x, D, g=0.35, mix=0.30):             # feedback delay / echo
    return (1-mix)*x + mix*(comb(np.concatenate([np.zeros(D), x])[:len(x)], D, g))
```

### 2.7 Reverb — Schroeder (default) and FDN-lite (impacts/logo tail)

**Schroeder** (4 parallel combs → 2 series allpasses), classic Freeverb-ish
delays scaled to 48 kHz, prime-ish so modes don't coincide:

| Comb | D (samples) | g |
|---|---|---|
| 1 | 3 517 | 0.805 |
| 2 | 3 907 | 0.790 |
| 3 | 4 391 | 0.776 |
| 4 | 4 799 | 0.762 |

| Allpass | D | g |
|---|---|---|
| 1 | 1 231 | 0.5 |
| 2 |   401 | 0.5 |

```python
def reverb(x, rt=2.2, damp_hz=5200, spread=23):
    combs = [(3517,.805),(3907,.790),(4391,.776),(4799,.762)]
    k = rt/2.2                                  # scale g toward 1 for longer tails
    def one(sig, off):
        y = sum(comb(onepole_lp(sig, damp_hz), D+off, min(g**(1/k), 0.94))
                for D, g in combs)/4
        return allpass(allpass(y, 1231+off, .5), 401+off, .5)
    return np.stack([one(x, 0), one(x, spread)])   # -> (2, N) stereo, decorrelated
```

**FDN-lite** for the two big impacts and the logo tail — 4 delay lines with a
4×4 Hadamard feedback matrix, processed in blocks of `min(D)` so the block
recurrence still holds:

```
D = [1861, 2131, 2477, 2843]   (samples)
H = 0.5 * [[1,1,1,1],[1,-1,1,-1],[1,1,-1,-1],[1,-1,-1,1]]   (orthogonal, unit gain)
per block of B = 1861:
    out_block = state_lines_read(B)
    fed = (H @ out_block) * g   with g = 10**(-3*B/(RT60*SR)/20) per line
    write x_block/2 + fed into the lines
```
Use `RT60 = 3.4 s` for impacts, `4.2 s` for the logo tail, with a 4.5 kHz damping
one-pole in the loop.

### 2.8 Envelopes

```python
def adsr(n, a=0.005, d=0.10, s=0.6, r=0.20, sr=SR):
    """Never let a<0.005s (5 ms) — see §10.1."""
    A = max(int(a*sr),1); D = int(d*sr); R = int(r*sr); S = max(n-A-D-R, 0)
    env = np.concatenate([
        0.5-0.5*np.cos(np.pi*np.linspace(0,1,A)),      # raised-cosine attack
        s + (1-s)*np.exp(-np.linspace(0,5,D)),
        np.full(S, s),
        s*np.exp(-np.linspace(0,6,R))])[:n]
    return np.pad(env, (0, max(0, n-len(env))))

def expdec(n, tau, sr=SR, atk=0.005):
    t = np.arange(n)/sr
    e = np.exp(-t/tau)
    A = max(int(atk*sr),1); e[:A] *= 0.5-0.5*np.cos(np.pi*np.linspace(0,1,A))
    return e
```

### 2.9 Placement (mix-bus write)

```python
def place(bus, sig, start, gain_db=0.0, pan=0.0):
    """bus: (2,N). pan -1..+1, equal-power."""
    g = 10**(gain_db/20)
    l = g*np.cos((pan+1)*np.pi/4); r = g*np.sin((pan+1)*np.pi/4)
    n = min(len(sig), bus.shape[1]-start)
    if n <= 0: return
    bus[0, start:start+n] += l*sig[:n]; bus[1, start:start+n] += r*sig[:n]
```

Every `sig` handed to `place` **must already start and end at zero** (§10.1).

---

## 3. Layers — synthesis recipes

RNG: one seeded generator for the whole render, `rng = np.random.default_rng(20260726)`,
so the output is byte-reproducible.

### 3.1 SUB — sine + slight drive

Pure sine (no harmonics to alias), then a gentle asymmetric-free `tanh` drive
which adds only odd harmonics at 131/218/306 Hz — nowhere near Nyquist, safe
without oversampling.

```
f(t)  : per-chord root, F1 43.654 / Db2 69.296 / Eb2 77.782, with a 60 ms
        portamento between roots: f = prev + (next-prev)*(1-exp(-t/0.020))
env   : per-8th note gate — attack 8 ms raised-cosine, sustain 1.0,
        release 45 ms; on the drop, tie whole bars (no gate) for weight
drive : y = tanh(1.8*x)/tanh(1.8)
tilt  : onepole_lp(y, 180)     # keep the drive's grit out of the low-mid
hpf   : onepole_hp(y, 24)      # rumble/DC guard
gain  : -6.0 dBFS peak (see §9)
mono  : sub is ALWAYS mono/centre (pan 0). Never widen below 120 Hz.
```

A separate **sub-drop** variant for §7.2: glide `F3 174.614 → 25 Hz` over 1.15 s,
`f(t) = 25 + (174.614-25)*exp(-t/0.28)`, amplitude `expdec(n, 0.55)`,
`onepole_lp(·, 120)`.

### 3.2 PULSE / ARP — band-limited saw (the "tech" motor)

```
osc   : bl_saw (§2.2) on the 8-step 16th pattern of §1, one note per STEP,
        each note's f is a constant array of length STEP (so f_max = that note)
env   : per-step, attack 5 ms, exp decay tau = 0.070 s, hard tail-out over the
        last 5 ms of the step so consecutive steps never overlap-click
unison: 2 voices, ±7 cents (× 2**(±7/1200)), pan ∓0.35, second voice -3 dB
filter: static onepole_lp at 2.4 kHz in tension, 5.5 kHz in drop/groove
        (implement as two different renders, not a sweep — cheaper, and the
         section change IS the filter change)
reso  : optional biquad BP, f0 = 1.6 kHz, Q = 1.1, 25 % wet, for the drop only
accent: steps 0 and 4 of each 8 get +2.5 dB and tau 0.090
gain  : -11 dBFS
```

A **square** variant (`bl_square`, odd harmonics only) is used for the tension
section's 8th-note pulse at F2 87.307 — hollower, sits under the ticking bed.

### 3.3 PAD — detuned saw stack + slow filter

```
voices: 7 saws per chord note, detune in cents [-14,-9,-4,0,+4,+9,+14]
        each with an independent random start phase phi0 = rng.uniform(0,2π)
        per-voice gain 1/sqrt(7); pan = detune/14 * 0.55 (widest voices widest)
notes : the 3–4 chord tones of §1 + root doubled at F2 87.307
K cap : 40 partials (chord tops reach 392 Hz → 40*392 = 15.7 kHz, under 21.6)
env   : attack 350 ms, release 700 ms per chord, raised-cosine both ends,
        chords crossfade (overlap 250 ms) so the pad never gaps
sweep : stft_filter LP, cutoff follows the section intensity curve (§4):
        fc(t) = 420 * (14000/420) ** I(t)      # 420 Hz at I=0, 14 kHz at I=1
        order 2, plus a fixed HP at 90 Hz to leave room for the sub
chorus: sum with a 17 ms delayed copy modulated ±0.6 ms at 0.23 Hz — implement
        as a static 17 ms delay + a second at 23 ms, opposite-panned (cheaper
        than fractional-delay modulation and inaudibly different at this depth)
verb  : send 0.45 to the Schroeder reverb, rt 2.6 s
gain  : -14 dBFS (dry) / -18 dBFS (wet return)
```

### 3.4 KICK — pitch-swept sine + click

```
pitch : f(t) = 47 + (155-47)*exp(-t/0.032)          # 155 Hz -> 47 Hz
body  : sin(phase(f)) * exp(-t/0.26), attack 2 ms raised-cosine
        (2 ms is the ONE exception to the 5 ms rule: it is a transient that
         starts from silence at a zero crossing; see §10.1)
click : 2.5 ms of white noise -> onepole_hp(·, 1500), * exp(-t/0.0018)
        + 1.6 kHz sine * exp(-t/0.004),  click at -9 dB rel. body
sub-t : add sin(2π·43.654·t) * exp(-t/0.16) at -5 dB for the drop kicks only
drive : y = tanh(2.4*y)/tanh(2.4)  (then re-normalise to the pre-drive peak)
dcblk : dc_block(y)      # the pitch sweep + tanh leaves a small DC tail
len   : 0.45 s buffer, final 5 ms raised-cosine fade to zero
gain  : -3.5 dBFS (the loudest musical element)
```

### 3.5 SNARE / CLAP

**Snare** (backbeat, beats 2 and 4):
```
body  : two sines 185 Hz and 331 Hz, * exp(-t/0.085), -8 dB
noise : white -> BP 180..1800 (onepole_hp(onepole_lp(n,1800),180)) * exp(-t/0.13)
crack : white -> onepole_hp(·, 2600) * exp(-t/0.045), -4 dB
sum, attack 1.5 ms, total len 0.30 s, 5 ms tail fade
verb  : send 0.30, rt 1.4 s   (short room; long snare verb muddies a 60 s promo)
gain  : -8 dBFS, pan 0
```

**Clap** (drop + groove, layered with or replacing the snare):
```
4 noise bursts at offsets [0, 11, 21, 30] ms, each * exp(-t/0.011),
level [1.0, 0.85, 0.95, 0.7], each with an independent noise draw
tail   : one burst at 30 ms * exp(-t/0.16)
filter : BP 900..3600, biquad BP f0=1900 Q=0.8 at 40 % wet for the "room" honk
stereo : bursts alternate pan ±0.18; tail centre
gain   : -9 dBFS
```

### 3.6 HATS

```
closed: white -> onepole_hp(·, 7000) twice (12 dB/oct) * exp(-t/0.026), 0.10 s
open  : same, * exp(-t/0.155), 0.40 s, + a biquad BP f0=9500 Q=1.2 at 30 % wet
metal : (optional, drop only) 6 squares at ratios [1, 1.4471, 1.6170, 1.9265,
        2.5028, 2.6637] × 320 Hz, summed, then HP 6.5 kHz — the 808 recipe
grid  : closed on every off-8th; open on the "and" of 4 into each new section
pan   : alternating ±0.22 by step index; velocity ±2 dB humanise
gain  : -17 dBFS closed / -15 dBFS open
```

### 3.7 TICK BED — the Tower signature

Tower is a control tower; the bed is a **radar/clock tick**, and it is the one
element that plays in nearly every section. This is the "ticking percussive bed"
of the trailer grammar, and it doubles as the brand's own sound.

```
tick  : white noise, 9 ms buffer
        -> biquad BP f0 = 4200 Hz, Q = 2.2   (bright, dry, close)
        -> * exp(-t/0.0055), attack 0.8 ms
        -> 5 ms raised-cosine tail to zero (buffer is 9 ms; tail overlaps decay)
tock  : same, f0 = 900 Hz, Q = 1.6, tau 0.011 — plays on every 4th tick
grid  : 16ths. level pattern per 16th index i%4: [0 dB, -7, -4.5, -7]
humanise: timing jitter ±96 samples (±2 ms), level jitter ±2 dB, both from rng
pan   : hard-ish alternation, pan = +0.45 if (i%2) else -0.45; the tock centre
        (this is what makes it read as a *scanning* radar, not a metronome)
sweep : a slow stft_filter LP from 3 kHz to 11 kHz across the tension section —
        the bed "wakes up"
gain  : -19 dBFS in cold open, -15 dBFS from the drop on
```

### 3.8 BRAAM — the punctuation

```
osc   : 5 detuned bl_saw at Ab2 103.826 (or the chord root ×2), cents
        [-18,-9,0,+9,+18], K capped at 64
sub   : + sin at F1 43.654 (or root/2) at -2 dB, the "weight"
scoop : all voices start -35 cents and rise to 0 over 300 ms:
        f(t) = f0 * 2**((-35/1200) * exp(-t/0.10))
swell : attack 420 ms (raised-cosine), hold, release 1.15 s
pulse : × (0.60 + 0.40 * square-ish 8th-note tremolo), 8 ms edges — the
        Zimmer pulsing braam. Depth 0 for the single long logo braam.
filter: stft_filter LP, 400 Hz -> 2500 Hz over the swell, order 2, then a
        biquad BP f0=650 Q=1.4 at 35 % wet for the brass "formant"
drive : tanh(3.0*x)/tanh(3.0), 2× oversampled (§9.4) — this one WILL alias
        without it, because the saw stack already reaches 15 kHz
verb  : send 0.5, FDN-lite rt 3.4 s
gain  : -5 dBFS
```

---

## 4. Sections — bar map, intensity, active layers

`I(t)` is the master intensity curve in [0,1]. It drives the pad filter (§3.3),
the tick bed level, and the riser depth. Interpolate **linearly between the
control points below, then smooth with `onepole_lp(I, 1.2)`** so no layer's
timbre steps at a bar line.

| # | Section | Bars | Time (s) | I: start → end |
|---|---|---|---|---|
| 1 | Cold open | 1–3 | 0.000 – 5.625 | 0.08 → 0.18 |
| 2 | Tension / problem | 4–10 | 5.625 – 18.750 | 0.20 → 0.72 (stop-down to 0.0 at 18.40) |
| 3 | Reveal / drop | 11–13 | 18.750 – 24.375 | **1.00** → 0.86 |
| 4 | Demo groove | 14–24 | 24.375 – 45.000 | 0.74 → 0.58 (bars 19–20) → 0.80 |
| 5 | Stakes beat | 25–28 | 45.000 – 52.500 | 0.40 → 0.97 |
| 6 | Final hit + logo tail | 29–32 | 52.500 – 60.000 | **1.00** → 0.00 |

### Layer activity matrix

`●` = full, `◐` = reduced/filtered, `·` = absent.

| Layer | 1 Cold open | 2 Tension | 3 Drop | 4 Groove | 5 Stakes | 6 Final/logo |
|---|---|---|---|---|---|---|
| Sub bass (§3.1) | · | ◐ 8ths from bar 7, LP 120 | ● tied whole bars | ● 8ths | ◐ pedal F1 only | ● hit at 29.1, then · |
| Pulse/arp (§3.2) | · | ◐ square 8ths @F2, LP 2.4k | ● saw 16ths, LP 5.5k | ● saw 16ths | · (returns bar 28, gated) | ● 2 bars, stops at 56.25 |
| Pad (§3.3) | ◐ Fm(add9), fc 420 Hz | ● sweeping up | ● wide, fc 11 k | ● | ● swelling | ● → tail only |
| Kick (§3.4) | · | · (single kick at bar 8.1) | ● 4-on-floor | ● 4-on-floor + 16th ghost on 4& | · until bar 28.4 | ● 29.1, 30.1, 31.1 then · |
| Snare/clap (§3.5) | · | · | ● clap on 2 & 4 | ● clap 2 & 4 + snare roll bar 24 | ● snare roll bars 27–28 (accel.) | ● one clap at 29.1 |
| Hats (§3.6) | · | ◐ closed on 8th-offs from bar 9 | ● closed 8ths + open on 4& | ● closed 16ths | ◐ closed, accel. | ● one open at 29.1 → choke |
| Tick bed (§3.7) | ● alone, -19 dB | ● sweeping, -17 dB | ● -15 dB | ● -15 dB | ● doubling to 32nds | ● stops at 56.25, one last tick |
| Braam (§3.8) | · | ● one at bar 8.1 | ● at 11.1 (with impact) | · | ● at 25.1 | ● at 29.1 and 31.1 (logo) |

### Section notes

**1. Cold open (0.000–5.625 s).** Silence for the first 120 ms. Tick bed alone,
one pad note (Fm, fc 420 Hz) fading in over 1.2 s. A single **UI lock tick**
(§7.3) at 1.875 s (bar 2.1) and 3.750 s (bar 3.1). This is the "quiet tower".
A **whoosh** (§7.1, short variant, 0.6 s) lands on 5.625 s.

**2. Tension / problem (5.625–18.750 s).** The bed wakes: tick sweep opens, sub
enters on 8ths at bar 7 (11.250 s), square pulse from bar 4, hats from bar 9.
The **denied/alarm pulse** (§7.4) at bar 8.1 (13.125 s) with a braam under it —
this is the off-country/blocked beat. Typewriter ticks (§7.6) across bars 5–6 for
kinetic type. **Long riser** (§7.1) starts at bar 9.1 (15.000 s) and runs 3.75 s.
**Stop-down: hard-mute every layer at 18.400 s** (a 25 ms fade) — 350 ms of true
silence except the riser's last 120 ms and the reverse cymbal.

**3. Reveal / drop (18.750–24.375 s).** **Impact** (§7.2) + braam + sub-drop
exactly on 18.750 s, with a **reverse cymbal** (§7.7) leading in for 1.4 s
before it. Everything at full. 4-on-floor kick, clap on 2 & 4, saw 16ths, pad
wide open. A **confirm chime** (§7.5) at bar 12.1 (20.625 s) — the "allowed /
guard is green" moment, riding over the drop.

**4. Demo groove (24.375–45.000 s).** The bed for feature callouts. Deliberately
2–4 dB below the drop and with the pad filter pulled back, so VO and on-screen
type win. Bars 19–20 (`I` dips to 0.58) is the built-in **breath** for a
long caption — arp drops to 8ths, kick keeps time. Small **whooshes** on each
4-bar boundary (bars 18.1, 22.1) to punctuate cuts. UI lock ticks on bars 16.3,
20.3, 23.3 for interface beats. Snare roll through bar 24 into the next section.

**5. Stakes beat (45.000–52.500 s).** Drums out. Sub pedal on F1, pad swelling,
braam at 45.000 s. The tick bed doubles to 32nds and the snare roll accelerates
(16ths → 24ths → 32nds across bars 27–28). **Riser** (§7.1) starts at bar 27.1
(48.750 s), 3.75 s long, gated to 16ths in its final bar. Stop-down at 52.30 s
(a 30 ms fade to silence).

**6. Final hit + logo tail (52.500–60.000 s).** **Impact + braam + sub-drop** on
52.500 s. Two more kicks at 54.375 (30.1) and 56.250 (31.1). At **56.250 s**
everything stops except: the **logo stinger** (§7.8), the FDN-lite tail, and one
last isolated tick at 56.60 s. Tail decays to true digital silence by 59.90 s;
the final 100 ms is a hard raised-cosine fade to exactly 0.0.

---

## 5. Event schedule (concrete sample offsets)

| Time (s) | Sample | Bar.beat | Event |
|---|---|---|---|
| 0.000 | 0 | 1.1 | fade-in start (30 ms), tick bed in |
| 1.875 | 90 000 | 2.1 | UI lock tick |
| 3.750 | 180 000 | 3.1 | UI lock tick ×2 (double-confirm motif) |
| 5.625 | 270 000 | 4.1 | short whoosh → tension |
| 8.437 | 405 000 | 5.3 | typewriter burst (12 ticks over 0.9 s) |
| 11.250 | 540 000 | 7.1 | sub enters |
| 13.125 | 630 000 | 8.1 | **denied pulse** + braam |
| 15.000 | 720 000 | 9.1 | **long riser** starts (3.75 s) |
| 17.350 | 832 800 | — | reverse cymbal starts (1.40 s) |
| 18.400 | 883 200 | — | **stop-down** (25 ms fade, 350 ms silence) |
| **18.750** | **900 000** | **11.1** | **IMPACT + braam + sub-drop → DROP** |
| 20.625 | 990 000 | 12.1 | confirm chime |
| 24.375 | 1 170 000 | 14.1 | groove starts |
| 30.000 | 1 440 000 | 17.1 | whoosh (cut punctuation) |
| 31.875 | 1 530 000 | 18.1 | UI lock tick |
| 33.750 | 1 620 000 | 19.1 | breath: `I` dips |
| 37.500 | 1 800 000 | 21.1 | whoosh + typewriter burst |
| 43.125 | 2 070 000 | 24.1 | snare roll begins |
| **45.000** | **2 160 000** | **25.1** | braam, drums out, stakes |
| 48.750 | 2 340 000 | 27.1 | **riser** starts (3.75 s), roll accelerates |
| 52.300 | 2 510 400 | — | **stop-down** (30 ms fade) |
| **52.500** | **2 520 000** | **29.1** | **FINAL IMPACT** + braam + sub-drop + clap |
| 54.375 | 2 610 000 | 30.1 | kick |
| **56.250** | **2 700 000** | **31.1** | **LOGO STINGER**, all else stops |
| 56.600 | 2 716 800 | — | last isolated tick |
| 59.900 | 2 875 200 | — | final 100 ms fade to 0.0 |
| 60.000 | 2 880 000 | — | end |

---

## 6. SFX — parameters

All SFX are rendered into their own buffer and `place`d; all obey §10.1.

### 7.1 Whoosh / riser

Two variants of one recipe. `T` = duration, `t` = 0..T.

```
noise  : white, len T
sweep  : stft_filter BP mask, centre fc(t) = 180 * (9000/180)**(t/T)**1.6
         Q(t)  = 0.7 + 2.6*(t/T)                       # resonance rises
tone   : a Shepard-ish additive layer, 3 sines at f0, 2f0, 4f0 with
         f0(t) = 110 * 2**(1.9*t/T), each weighted by a fixed log-Gaussian
         spectral envelope W(f) = exp(-((log2(f)-log2(1400))**2)/(2*0.9**2))
         -> the pitch rises forever without running out of top end
amp    : (t/T)**2.2, then a 5 ms fade-in and (for the riser) a 90 ms tail
gate   : final 25 % of T only — multiply by a 16th-note square, depth 0.85,
         8 ms edges (the "gated riser" convention)
verb   : send 0.35, rt 1.8 s; pan: LFO 0.28 Hz between -0.7 and +0.7
tail   : the riser must END at the impact sample, not before; its last 60 ms
         is a raised-cosine drop to zero so the impact starts on silence
```

| Variant | T | Peak gain | Notes |
|---|---|---|---|
| Short whoosh (cut punctuation) | 0.60 s | −16 dBFS | no gate, no tone layer, pan sweep L→R |
| Long riser (into a drop) | 3.75 s (2 bars) | −8 dBFS | full recipe, gated last bar |
| Downer (after an impact) | 1.20 s | −18 dBFS | reverse the fc curve (9 kHz → 180 Hz), amp `exp(-t/0.4)` |

### 7.2 Impact / boom

Six stacked components, all starting at the same sample:

| # | Component | Recipe | Gain |
|---|---|---|---|
| a | Sub | sine, `f = 30 + (58-30)*exp(-t/0.30)`, `exp(-t/0.85)`, LP 90 | −4 dB |
| b | Low thump | noise → BP 55..190 → `exp(-t/0.32)`, tanh drive 2.0 | −8 dB |
| c | Mid crunch | noise → BP 320..2600 → `exp(-t/0.11)`, biquad BP f0 700 Q 1.3 at 45 % wet | −11 dB |
| d | HF transient | noise → HP 5 kHz → `exp(-t/0.0035)`, 4 ms | −14 dB |
| e | Metallic tail | 6 sines at 90 Hz × [1, 1.41, 1.62, 1.93, 2.50, 2.66], `exp(-t/1.1)`, HP 200 | −20 dB |
| f | Pre-swell | the **downer** of §7.1 reversed, 30 ms, ending exactly at t=0 (i.e. placed at `start - 1440` samples) | −22 dB |

Sum → `tanh(1.6·x)/tanh(1.6)` (2× oversampled, §9.4) → FDN-lite reverb, send
0.55, RT60 3.4 s → total buffer 3.0 s → **−1.5 dBFS peak** (the loudest single
element in the piece). Ducks everything (§9.3).

### 7.3 UI "lock" tick

The interface confirming a state. Small, dry, expensive-sounding.

```
two sines: 2100 Hz and 3150 Hz (exact 3:2), equal level
env      : attack 1.0 ms raised-cosine, exp decay tau = 0.016 s, len 60 ms
noise    : + 1.5 ms of HP-8 kHz noise at -12 dB rel. (the "mechanism")
verb     : send 0.18, rt 0.9 s (a tiny room — it must not sound wet)
gain     : -22 dBFS, pan 0.0; the "double-confirm" motif = two ticks 90 ms apart,
           the second at 2100·(6/5) = 2520 Hz and 3780 Hz (up a minor third)
```

### 7.4 Denied / held pulse (the blocked / off-country beat)

**Design law:** this is a *hold*, not a failure. Two even pulses, no downward
resolve, no harshness spike — amber, not red. (docs/DESIGN.md: "failure never
bounces".)

```
core   : two detuned band-limited squares at 210.0 Hz and 222.0 Hz
         (beating at 12 Hz -> the "unsettled" feel without dissonant harshness)
         K capped at 64
sub    : + sine at 105 Hz at -6 dB
gate   : × (0.35 + 0.65 * square LFO at 14 Hz), 6 ms edges
filter : BP 300..3000 (onepole cascade), then biquad BP f0 = 780, Q = 2.0,
         50 % wet -> a nasal, "held" timbre
drive  : tanh(2.2*x)/tanh(2.2)
shape  : two pulses of 0.22 s, separated by 0.16 s of silence; each pulse
         attack 12 ms, release 60 ms. NO pitch descent.
verb   : send 0.30, rt 1.6 s
gain   : -13 dBFS, pan 0 (a hold is centred; it is the whole picture)
```

### 7.5 Confirm chime (restored / allowed)

The one upward resolution in the piece: a perfect fifth, C5 → G5.

```
partials: additive bell, ratios [1.00, 2.00, 3.01, 4.21, 5.43, 6.79]
          amplitudes [1.0, 0.55, 0.32, 0.20, 0.12, 0.07]
          per-partial decay tau_k = 1.30 / k**0.62  (higher partials die first)
strike 1: f0 = C5 523.251 Hz at t = 0
strike 2: f0 = G5 783.991 Hz at t = 0.135 s, at -2 dB
env     : attack 4 ms raised-cosine on each strike, total buffer 2.0 s
filter  : onepole_lp(·, 6500) — warm, not glassy
verb    : send 0.40, Schroeder rt 2.4 s
gain    : -15 dBFS, pan +0.10 / -0.10 for the two strikes (a tiny widening)
```

### 7.6 Typewriter tick (kinetic type)

```
per tick: noise, 7 ms -> biquad BP f0 = rng.uniform(2600, 4400), Q = 1.8
          × exp(-t/0.0028), attack 0.5 ms
        + a 1.2 ms HP-4 kHz noise click at -6 dB rel.
grid    : 32nds (2812 samples), with ±60 samples jitter and a 25 % chance of a
          skipped step (so it reads as typing, not as a machine gun)
level   : -20 dBFS ± 2.5 dB per tick (rng)
pan     : rng.uniform(-0.25, 0.25) per tick
bursts  : 10–14 ticks per burst; a burst ends with a "return" = one tick at
          f0 = 1400 Hz, Q = 1.2, -14 dBFS
```

### 7.7 Reverse cymbal

```
source : white noise, len 1.40 s
spectrum: biquad BP f0 = 7200 Q = 0.6, + 8 resonant partials at
          420 Hz × [1, 2.76, 5.40, 8.93, 13.34, 18.64, 24.81, 31.87]
          (Bessel-ish inharmonic ratios), each a sine at -14 dB, all noise-AM'd
env    : rising, env = (t/T)**3.0
sweep  : stft_filter HP, fc(t) = 200 * (9000/200)**(t/T)   -> opens as it rises
stop   : the LAST 5 ms is a raised-cosine drop to exactly 0.0 — the cymbal must
         die a hair BEFORE the impact so the impact's transient is clean
verb   : send 0.25 (pre-fader, so the tail does not survive the stop)
gain   : -12 dBFS, stereo: two independent noise draws, L/R (fully decorrelated)
```

Implementation shortcut: build it forward-decaying and `np.flip` it — identical
result, and it makes the "reverse" character obvious in code.

### 7.8 Logo stinger

The 4th act. One gesture, 3.75 s, over silence.

```
t=0.000 : impact (§7.2) at -3.0 dBFS, FDN-lite RT60 4.2 s
t=0.000 : braam (§3.8) with pulse depth 0, swell 500 ms, release 2.4 s,
          root F1 43.654 + Ab2 103.826 stack
t=0.060 : confirm chime (§7.5) transposed to F5 698.456 -> C6 1046.502,
          at -12 dBFS  (the fifth again: the guard is up)
t=0.350 : one isolated tick (§3.7) at -21 dBFS, pan 0 — the tower still scanning
t=0.000+: pad, one Fm(add9) chord, attack 800 ms, release 2.6 s, fc 3 kHz,
          reverb send 0.6
tail    : from t=1.2 s, reverb only. Apply a global raised-cosine fade over the
          final 100 ms of the file so the tail ends at exactly 0.0.
```

---

## 8. Bus routing

```
DRY BUSES
  bed      = sub + pulse + pad + tick + hats          # ducked by impacts & kicks
  drums    = kick + snare/clap                        # ducked by impacts only
  sfx      = whooshes, risers, ticks, chimes, denied  # not ducked
  hits     = impacts, braams, sub-drops, logo stinger # never ducked
REVERB SENDS (post-fader, pre-duck)
  verb_A   Schroeder  rt 2.2 s  <- pad 0.45, snare 0.30, chime 0.40, whoosh 0.35
  verb_B   FDN-lite   rt 3.4 s  <- impacts 0.55, braams 0.50, logo 0.60
DELAY
  dly      620 ms (= dotted 8th at 128 BPM = 0.703 s; use 0.703 s = 33 750 smp)
           feedback 0.32, mix 0.18  <- arp only, in the groove section
MASTER
  sum -> dc_block -> soft-knee limiter -> tanh safety -> peak normalise -> int16
```

Dotted-8th delay: 0.703 125 s = **33 750 samples** exactly.

---

## 9. Mixing

### 9.1 Per-layer gains

Gains are **peak dBFS of that layer's own rendered buffer** before summing.
Set them, sum, then let the limiter (§9.5) take 2–4 dB on the loud sections.

| Layer / element | Gain (dBFS peak) | Pan | Notes |
|---|---|---|---|
| Impact (§7.2) | **−1.5** | 0 | loudest single element |
| Logo stinger impact | −3.0 | 0 | |
| Kick (§3.4) | −3.5 | 0 | |
| Braam (§3.8) | −5.0 | ±0.15 (2 voices) | |
| Sub (§3.1) | −6.0 | 0 (mono, always) | |
| Snare (§3.5) | −8.0 | 0 | |
| Long riser (§7.1) | −8.0 | LFO ±0.7 | |
| Clap (§3.5) | −9.0 | ±0.18 | |
| Pulse / arp (§3.2) | −11.0 | ±0.35 | |
| Reverse cymbal (§7.7) | −12.0 | L/R decorrelated | |
| Denied pulse (§7.4) | −13.0 | 0 | |
| Pad dry (§3.3) | −14.0 | ±0.55 spread | |
| Open hat (§3.6) | −15.0 | ±0.22 | |
| Confirm chime (§7.5) | −15.0 | ±0.10 | |
| Tick bed (§3.7) | −19 cold / **−15** from drop | ±0.45 alt | |
| Short whoosh (§7.1) | −16.0 | sweeping | |
| Closed hat (§3.6) | −17.0 | ±0.22 | |
| Pad wet return | −18.0 | wide | |
| Typewriter tick (§7.6) | −20.0 ±2.5 | ±0.25 rnd | |
| UI lock tick (§7.3) | −22.0 | 0 | |

### 9.2 Static EQ / spectral hygiene

- Everything except the sub and the kick: `onepole_hp(·, 90)` — keeps the low end
  for two elements only.
- Sub: `onepole_lp(·, 180)`; kick body: `onepole_lp(·, 320)` after the drive.
- Pad: a −3 dB shelf dip around 300–500 Hz (implement as
  `x - 0.29*biquad_BP(x, f0=400, Q=0.7)`) — the classic mud carve.
- Tick bed and hats: `onepole_lp(·, 16000)` so the top is not brittle at 48 kHz.

### 9.3 Sidechain-style ducking

Not a real compressor — an explicit, scheduled gain envelope. For each trigger
at sample `s` with depth `D` and recovery `τ`:

```
g(n) = 1 - D · w(n)
w(n) = 0                                   n < s
     = (n-s)/A                             s <= n < s+A       (A = 3 ms attack)
     = exp(-(n-s-A)/(τ·SR))                n >= s+A
```

Accumulate all triggers multiplicatively (`g_total = Π g_i`), clamp to
`[0.12, 1.0]`, then smooth with `onepole_lp(g_total, 90)` so there is no step at
the attack corner. Apply to the **bed** bus (and, for impacts only, to **drums**).

| Trigger | Target bus | Depth D | τ |
|---|---|---|---|
| Kick | bed | 0.35 | 0.13 s |
| Clap / snare | bed | 0.18 | 0.09 s |
| Impact | bed **and** drums | 0.75 | 0.34 s |
| Braam | bed | 0.45 | 0.50 s |
| Logo stinger | everything except itself | 0.90 | 0.90 s |

This is also what makes the bed "breathe" in the groove section and what makes
the impacts feel physically large without extra level.

### 9.4 2× oversampled saturation (for anything driven hard)

`tanh` on a signal that already has energy near Nyquist folds harmonics back as
aliasing. Oversample with FFT zero-padding (= ideal sinc interpolation), saturate,
decimate. Verified: 1 kHz sine round-trips with the expected 2× length and unity
peak.

```python
def sat_os2(x, drive):
    n = len(x)
    X = np.fft.rfft(x); T = np.zeros(n+1, complex); T[:len(X)] = X
    u = np.fft.irfft(T, 2*n) * 2                      # 2x upsample
    u = np.tanh(drive*u)/np.tanh(drive)
    U = np.fft.rfft(u)[:n//2+1]                       # truncate = ideal LP
    return np.fft.irfft(U, n) * 0.5
```

Pad the buffer with ~2048 zeros on each side before this (circular FFT) and trim
after. Required for: braam, impact, drum bus. Not required for the sub (its
harmonics land below 400 Hz).

### 9.5 Soft-knee limiter

Feed-forward, dB-domain gain computer with lookahead. Threshold **T = −1.5 dBFS**,
knee **W = 6 dB**, ratio ∞, attack 1.0 ms (lookahead 64 samples), release 120 ms.

```
L_dB(n) = 20·log10(max(|x_L(n)|, |x_R(n)|, 1e-12))        # linked stereo
over    = L_dB - T
red_dB  = 0                          if over <= -W/2
        = over² / (2W) + over/2 + W/8   if |over| < W/2   # soft knee
        = over                       if over >=  W/2
g_dB(n) = -red_dB   -> smooth with a one-pole: attack coeff on falling g,
                       release coeff on rising g
        a_atk = 1 - exp(-1/(0.001·SR)) ;  a_rel = 1 - exp(-1/(0.120·SR))
y = x_delayed_by_64 · 10**(g_smoothed/20)
```

The smoothing is a two-coefficient recurrence — run it as a Python loop over the
gain array only (2.88 M iterations, ~2 s; acceptable once per render), or in
1024-sample blocks with a held coefficient.

Then a final safety: `y = np.tanh(1.02*y)/np.tanh(1.02)` — inaudible below
−3 dBFS, catches any inter-sample overshoot the limiter missed.

**Never `np.clip` the master.** Hard clipping produces broadband, unmaskable
aliasing.

### 9.6 Targets, fades, output

- **Target peak: −1.0 dBFS.** After the limiter:
  `y *= 10**(-1.0/20) / np.max(np.abs(y))`.
- **Target loudness: −11 LUFS integrated** for the standalone music-only file
  (trailer/promo territory: dense, loud, sits under fast cuts). **If VO or SFX
  from the video will be laid over it, render a second pass at −17 LUFS** and let
  §9.3-style ducking under the VO do the rest. Expect LRA ≈ 8–11 LU (cold open to
  drop is a real 20 dB swing) and true-peak ≈ −0.7 dBTP.
- Measure with ITU-R BS.1770-4 K-weighting; exact 48 kHz biquad coefficients
  (the only reason a filter loop is needed on the full buffer):

  ```
  stage 1 (shelf): b = [1.53512485958697, -2.69169618940638,  1.19839281085285]
                   a = [1.0,              -1.69065929318241,  0.73248077421585]
  stage 2 (RLB HP): b = [1.0, -2.0, 1.0]
                    a = [1.0, -1.99004745483398, 0.99007225036621]
  LUFS = -0.691 + 10·log10( Σ_ch G_ch · mean(y_ch²) ),  G_L = G_R = 1.0
  gated: 400 ms blocks, 75 % overlap, absolute gate -70 LUFS,
         relative gate at (ungated loudness - 10 LU)
  ```

- **Fade-in:** 30 ms raised-cosine at sample 0 (the piece starts with 120 ms of
  near-silence anyway).
  **Fade-out:** 100 ms raised-cosine ending at sample 2 879 999, value exactly 0.0.

- **int16 conversion — the rounding rule:**

  ```python
  y = np.clip(y, -1.0, 1.0)
  q = np.rint(y * 32767.0).astype(np.int32)     # round-half-to-even, 32767 not 32768
  q = np.clip(q, -32768, 32767).astype(np.int16)
  frames = np.column_stack([q[0], q[1]]).astype('<i2').tobytes()   # L,R interleaved
  ```

  Scale by **32767**, not 32768 — 32768 makes a full-scale negative sample wrap on
  some readers, and the −1.0 dBFS normalise means the difference is inaudible.
  `np.rint` (banker's rounding) rather than truncation: truncation is a
  half-LSB DC offset plus asymmetric distortion.

- **Dither is not required.** The quantisation error floor at 16 bit is −96 dBFS;
  every section of this piece contains synthesised noise (tick bed, hats, reverb
  tail) well above that, which self-dithers. The one place it could matter is the
  final 100 ms fade into silence — if a stepped fade tail is audible on
  headphones, add TPDF dither at ±1 LSB *only over the fade region*:
  `q += (rng.random(n) - rng.random(n))` before `np.rint`. State it in the code
  comment either way; do not dither the whole file.

- WAV header: `wave` stdlib module — `setnchannels(2)`, `setsampwidth(2)`,
  `setframerate(48000)`, `writeframes(frames)`.

---

## 10. Anti-artifact rules (non-negotiable)

### 10.1 Click-free envelopes

1. **Every** buffer handed to `place()` starts at 0.0 and ends at 0.0.
   Assert it: `assert abs(sig[0]) < 1e-9 and abs(sig[-1]) < 1e-9`.
2. **Minimum 5 ms (240 samples) raised-cosine fade** at both ends of every
   segment: `0.5 - 0.5*cos(π·linspace(0,1,240))`. Linear ramps are audible as a
   faint tick at low levels; raised-cosine is not.
   *Sole exception:* percussive transients (kick 2 ms, click 1 ms, tick 0.8 ms)
   whose attack is the point. These are still ramps, never step discontinuities,
   and they always start from digital silence.
3. Adjacent arp/gate steps must not overlap-sum with a discontinuity: give each
   step its own 5 ms tail *inside* its step length.
4. Never restart an oscillator's phase mid-note. Phase comes from `np.cumsum`
   (§2.1) across the whole note, glide included.
5. Section boundaries: crossfade layer renders over ≥ 25 ms rather than swapping.
   The two intentional stop-downs use a 25 ms / 30 ms fade — audible as a *cut*,
   not as a click.

### 10.2 No aliasing

1. Additive oscillators: `K = max(1, floor(0.45·SR / f_max))` where `f_max` is the
   **maximum instantaneous frequency over the whole segment** (glide + vibrato +
   detune included), not the nominal pitch. Guard band = 5 % of SR.
   `assert K*f_max <= 0.45*SR`.
2. Lanczos-sigma taper on the truncated series (§2.2) — otherwise the truncation
   edge rings.
3. Any `tanh`/waveshaping on a signal with energy above ~4 kHz goes through
   `sat_os2` (§9.4). Sub-only drive is exempt.
4. All filter sweeps go through `stft_filter` (§2.5), never through a per-sample
   coefficient jump — jumped biquad coefficients produce a burst of broadband
   noise at every update.
5. Noise sources are generated at 48 kHz directly (`rng.standard_normal`); there
   is no resampling anywhere in the pipeline, so no resampler artifacts exist.
6. No hard clipping at any stage (§9.5).

### 10.3 DC offset

1. Every element: `sig -= sig.mean()` before placement — the pitch-swept kick and
   the asymmetric-driven braam both leave a measurable DC tail.
2. Master DC blocker before the limiter:
   `y[n] = x[n] - x[n-1] + R·y[n-1]`, `R = 0.9995` (corner ≈ 3.8 Hz at 48 kHz).
   Implement via §2.3's frequency-domain form: `H(ω) = (1-e^{-jω})/(1-R·e^{-jω})`.
3. `assert abs(y.mean()) < 1e-5` on the master before conversion.

### 10.4 Reproducibility & sanity checks

```python
assert out.shape == (2, 2_880_000)
assert np.all(np.isfinite(out))
assert np.max(np.abs(out)) <= 10**(-1.0/20) + 1e-9      # -1 dBFS
assert abs(out[:, 0]).max() < 1e-9 and abs(out[:, -1]).max() < 1e-9
assert abs(out.mean()) < 1e-5
```

One seeded `default_rng(20260726)` for the whole render; no `np.random.*` global
calls anywhere.

---

## 11. Render order (suggested implementation sequence)

1. Primitives (§2) + the assert harness (§10.4).
2. Tick bed alone, full 60 s → listen. If the bed is right, the piece is right.
3. Sub + pulse + pad on the §1 harmony, section-gated per §4.
4. Drums.
5. Impacts, braams, sub-drops on the §5 schedule — with the ducking envelopes.
6. Risers/whooshes/reverse cymbal, back-timed so they *end* on the impacts.
7. UI ticks, denied pulse, confirm chime, typewriter, logo stinger.
8. Reverb sends, delay, EQ hygiene.
9. Master chain: DC block → limiter → tanh → normalise → fades → int16 → WAV.
10. Verify LUFS and peak; re-render the −17 LUFS VO-bed variant if needed.
