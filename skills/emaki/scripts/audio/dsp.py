"""DSP building blocks: oscillators, noise, envelopes, biquads, pan, WAV IO. 48 kHz stereo,
float32/float64 numpy arrays shaped (n,) mono or (n, 2) stereo."""
import math
import wave

import numpy as np
from scipy import signal

SR = 48000


def secs(n):
    return n / SR


def samples(t):
    return int(round(t * SR))


def tt(dur):
    return np.arange(samples(dur)) / SR


def db(x):
    return 10 ** (x / 20.0)


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12.0)


# ----------------------------------------------------------------------------- oscillators

def sine(f, dur, phase=0.0):
    t = tt(dur)
    if callable(f):
        ph = 2 * np.pi * np.cumsum(f(t)) / SR
        return np.sin(ph + phase)
    return np.sin(2 * np.pi * f * t + phase)


def additive(f, dur, harmonics, phase_rng=None):
    """Band-limited additive tone: harmonics = [(k, amp), ...], skips partials > Nyquist."""
    t = tt(dur)
    out = np.zeros_like(t)
    for k, a in harmonics:
        if f * k >= SR / 2 - 200:
            break
        ph = phase_rng.uniform(0, 2 * np.pi) if phase_rng is not None else 0.0
        out += a * np.sin(2 * np.pi * f * k * t + ph)
    return out


def saw(f, dur, n=None, rng=None):
    n = n or max(1, int((SR / 2 - 200) / f))
    return additive(f, dur, [(k, (1 / k)) for k in range(1, min(n, 60) + 1)], rng) * (2 / np.pi)


def square(f, dur, rng=None):
    n = max(1, int((SR / 2 - 200) / f))
    return additive(f, dur, [(k, 1 / k) for k in range(1, min(n, 60) + 1, 2)], rng) * (4 / np.pi)


def triangle(f, dur):
    n = max(1, int((SR / 2 - 200) / f))
    return additive(f, dur, [(k, ((-1) ** ((k - 1) // 2)) / k ** 2) for k in range(1, min(n, 40) + 1, 2)]) * (8 / np.pi ** 2)


def fm(fc, ratio, index, dur, index_env=None):
    t = tt(dur)
    fmod = fc * ratio
    idx = index * (index_env if index_env is not None else 1.0)
    return np.sin(2 * np.pi * fc * t + idx * np.sin(2 * np.pi * fmod * t))


def noise(dur, rng, color="white"):
    n = rng.standard_normal(samples(dur))
    if color == "pink":
        b, a = [0.049922035, -0.095993537, 0.050612699, -0.004408786], [1, -2.494956002, 2.017265875, -0.522189400]
        n = signal.lfilter(b, a, n) * 3.0
    elif color == "brown":
        n = np.cumsum(n)
        n = signal.lfilter([1, -1], [1, -0.995], n)
        n /= (np.max(np.abs(n)) + 1e-9)
    return n


# ----------------------------------------------------------------------------- envelopes

def adsr(dur, a=0.01, d=0.1, s=0.7, r=0.2, total=None):
    """ADSR envelope: note held for `dur`, exponential release ~`r` seconds."""
    total = total if total is not None else dur + r
    t = np.arange(samples(total)) / SR
    a = max(a, 1e-4)
    d = max(d, 1e-4)
    env = np.interp(t, [0, a, a + d], [0, 1, s], right=s)
    lvl = float(np.interp(dur, [0, a, a + d], [0, 1, s], right=s))
    rel = t >= dur
    env[rel] = lvl * np.exp(-(t[rel] - dur) / max(r / 5.0, 1e-4))
    return env


def exp_decay(dur, tau):
    return np.exp(-tt(dur) / max(tau, 1e-5))


def fade(x, fin=0.005, fout=0.01):
    n = len(x)
    a, b = min(n, samples(fin)), min(n, samples(fout))
    w = np.ones(n)
    if a:
        w[:a] = np.linspace(0, 1, a)
    if b:
        w[-b:] *= np.linspace(1, 0, b)
    return x * (w if x.ndim == 1 else w[:, None])


# ----------------------------------------------------------------------------- filters (RBJ)

def biquad(kind, f, q=0.707, gain_db=0.0):
    f = min(max(f, 10.0), SR / 2 * 0.98)
    w0 = 2 * np.pi * f / SR
    cw, sw = np.cos(w0), np.sin(w0)
    alpha = sw / (2 * q)
    A = 10 ** (gain_db / 40)
    if kind == "lp":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "hp":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "bp":
        b = [alpha, 0, -alpha]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "peak":
        b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
        a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    elif kind == "lowshelf":
        sq = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) - (A - 1) * cw + sq), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sq)]
        a = [(A + 1) + (A - 1) * cw + sq, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sq]
    elif kind == "highshelf":
        sq = 2 * np.sqrt(A) * alpha
        b = [A * ((A + 1) + (A - 1) * cw + sq), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sq)]
        a = [(A + 1) - (A - 1) * cw + sq, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sq]
    else:
        raise ValueError(kind)
    b, a = np.array(b) / a[0], np.array(a) / a[0]
    return np.concatenate([b, a])[None, :]


def filt(x, kind, f, q=0.707, gain_db=0.0):
    sos = biquad(kind, f, q, gain_db)
    if x.ndim == 2:
        return np.stack([signal.sosfilt(sos, x[:, c]) for c in range(x.shape[1])], 1)
    return signal.sosfilt(sos, x)


def sweep_filter(x, kind, f_curve, q=0.707, block=256):
    """Time-varying biquad: f_curve(t_array)->Hz evaluated per block, state carried."""
    n = len(x)
    out = np.zeros_like(x)
    zi = np.zeros((1, 2)) if x.ndim == 1 else np.zeros((x.shape[1], 1, 2))
    for s in range(0, n, block):
        e = min(n, s + block)
        f = float(f_curve(np.array([(s + e) / 2 / SR]))[0])
        sos = biquad(kind, f, q)
        if x.ndim == 1:
            out[s:e], zi = signal.sosfilt(sos, x[s:e], zi=zi)
        else:
            for c in range(x.shape[1]):
                out[s:e, c], zi[c] = signal.sosfilt(sos, x[s:e, c], zi=zi[c])
    return out


# ----------------------------------------------------------------------------- stereo

def pan(x, p=0.0):
    """Equal-power pan of mono x; p in [-1, 1]."""
    ang = (p + 1) * np.pi / 4
    return np.stack([x * np.cos(ang), x * np.sin(ang)], 1)


def stereo(x):
    return x if x.ndim == 2 else np.stack([x, x], 1) * 0.7071


def width(x, w=1.0):
    m = (x[:, 0] + x[:, 1]) / 2
    s = (x[:, 0] - x[:, 1]) / 2 * w
    return np.stack([m + s, m - s], 1)


def mix_into(buf, x, at):
    """Add x into buf starting at sample `at` (clipped to buffer)."""
    if at >= len(buf):
        return
    if at < 0:
        x = x[-at:]
        at = 0
    e = min(len(buf), at + len(x))
    buf[at:e] += x[:e - at] if x.ndim == buf.ndim else stereo(x)[:e - at]


# ----------------------------------------------------------------------------- IO

def write_wav(path, x, bits=24):
    x = stereo(np.asarray(x, dtype=np.float64))
    x = np.clip(x, -1.0, 1.0)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setframerate(SR)
        if bits == 16:
            w.setsampwidth(2)
            w.writeframes((x * 32767).astype("<i2").tobytes())
        else:
            w.setsampwidth(3)
            i = (x * 8388607).astype("<i4")
            b = i.view(np.uint8).reshape(-1, 4)[:, :3]
            w.writeframes(b.tobytes())


def read_wav(path):
    with wave.open(path, "rb") as w:
        n, ch, sw, sr = w.getnframes(), w.getnchannels(), w.getsampwidth(), w.getframerate()
        raw = w.readframes(n)
    if sw == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float64) / 32768
    elif sw == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
        i = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        i = np.where(i & 0x800000, i - 0x1000000, i)
        x = i.astype(np.float64) / 8388608
    else:
        x = np.frombuffer(raw, "<i4").astype(np.float64) / 2 ** 31
    x = x.reshape(-1, ch)
    return x, sr
