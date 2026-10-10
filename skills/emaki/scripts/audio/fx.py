"""Audio effects: convolution reverb with a synthetic IR, delay, chorus, sidechain ducking,
saturation, bus compressor."""
import numpy as np
from scipy import signal

from .dsp import SR, samples, filt, stereo


_ir_cache = {}


def impulse(rt60=2.2, predelay=0.02, damp=6000.0, width=1.0, seed=11, early=True):
    """Synthetic stereo room IR: decaying noise that darkens over time + sparse early
    reflections. rt60 = decay to -60 dB in seconds."""
    key = (round(rt60, 3), round(predelay, 3), round(damp), round(width, 2), seed, early)
    if key in _ir_cache:
        return _ir_cache[key]
    rng = np.random.default_rng(seed)
    n = samples(rt60 * 1.1)
    t = np.arange(n) / SR
    env = 10 ** (-3 * t / rt60)
    out = np.zeros((n, 2))
    for c in range(2):
        nz = rng.standard_normal(n)
        bright = nz
        dark = filt(nz, "lp", damp * 0.35)
        mixk = np.clip(t / (rt60 * 0.6), 0, 1)
        out[:, c] = (bright * (1 - mixk) + dark * mixk) * env
    out = filt(out, "lp", damp)
    out = filt(out, "hp", 120)
    m = (out[:, 0] + out[:, 1]) / 2
    s = (out[:, 0] - out[:, 1]) / 2 * width
    out = np.stack([m + s, m - s], 1)
    if early:
        for k in range(8):
            d = int(rng.uniform(0.006, 0.07) * SR)
            if d < n:
                out[d, 0] += rng.uniform(0.2, 0.6) * (1 if rng.random() > 0.5 else -1)
                out[d + int(rng.uniform(1, 9) * SR / 1000) if d + 400 < n else d, 1] += rng.uniform(0.2, 0.6)
    pd = samples(predelay)
    out = np.concatenate([np.zeros((pd, 2)), out])
    out /= np.sqrt(np.sum(out ** 2) / 2) + 1e-9
    _ir_cache[key] = out
    return out


def reverb(x, mix=0.25, rt60=2.2, predelay=0.02, damp=6000.0, width=1.0):
    x = stereo(x)
    ir = impulse(rt60, predelay, damp, width)
    wet = np.stack([signal.oaconvolve(x[:, c], ir[:, c])[: len(x)] for c in range(2)], 1)
    return x * (1 - mix) + wet * mix


def delay(x, time=0.375, feedback=0.35, mix=0.25, pingpong=True, damp=5000.0):
    x = stereo(x)
    d = samples(time)
    n = len(x)
    out = np.zeros_like(x)
    tap = x.copy()
    g = 1.0
    for k in range(1, 8):
        g *= feedback
        if g < 0.02 or d * k >= n:
            break
        tap = filt(tap, "lp", damp)
        sh = np.zeros_like(x)
        sh[d * k:] = tap[: n - d * k] * g
        if pingpong and k % 2 == 1:
            sh = sh[:, ::-1]
        out += sh
    return x + out * mix


def chorus(x, depth=0.003, rate=0.6, mix=0.4):
    x = stereo(x)
    n = len(x)
    t = np.arange(n) / SR
    out = x.copy()
    for c, ph in ((0, 0.0), (1, np.pi / 2)):
        dl = (0.012 + depth * (1 + np.sin(2 * np.pi * rate * t + ph)) / 2) * SR
        idx = np.arange(n) - dl
        idx = np.clip(idx, 0, n - 1)
        i0 = np.floor(idx).astype(int)
        fr = idx - i0
        i1 = np.minimum(i0 + 1, n - 1)
        out[:, c] = x[:, c] * (1 - mix) + (x[i0, c] * (1 - fr) + x[i1, c] * fr) * mix
    return out


def duck_env(n, times, depth=0.6, attack=0.005, release=0.18):
    """Sidechain gain curve (n samples) dipping at each trigger time."""
    g = np.ones(n)
    rel = samples(release * 5)
    curve = 1 - depth * np.exp(-np.arange(rel) / SR / release)
    att = samples(attack)
    if att > 0:
        curve[:att] = 1 - depth * np.linspace(0, 1, att)
    for t in times:
        s = samples(t)
        if s >= n:
            continue
        e = min(n, s + rel)
        g[s:e] = np.minimum(g[s:e], curve[: e - s])
    return g


def saturate(x, drive=1.5):
    return np.tanh(x * drive) / np.tanh(drive)


def compress(x, threshold_db=-18.0, ratio=3.0, attack=0.01, release=0.15, makeup_db=0.0):
    """Simple feed-forward RMS compressor (stereo-linked)."""
    xs = stereo(x)
    lvl = np.sqrt(np.mean(xs ** 2, axis=1) + 1e-12)
    win = max(1, samples(0.01))
    lvl = np.sqrt(signal.lfilter(np.ones(win) / win, [1], lvl ** 2) + 1e-12)
    ldb = 20 * np.log10(lvl)
    over = np.maximum(0, ldb - threshold_db)
    gr = over * (1 - 1 / ratio)
    a_a = np.exp(-1 / (attack * SR))
    a_r = np.exp(-1 / (release * SR))
    sm = np.zeros_like(gr)
    prev = 0.0
    # one-pole with separate attack/release (vectorized in chunks via lfilter approximation)
    sm_a = signal.lfilter([1 - a_a], [1, -a_a], gr)
    sm_r = signal.lfilter([1 - a_r], [1, -a_r], gr)
    sm = np.maximum(sm_a, sm_r * 0.98)
    g = 10 ** ((-sm + makeup_db) / 20)
    return xs * g[:, None]
