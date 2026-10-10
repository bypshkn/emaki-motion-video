"""Loudness (ITU-R BS.1770-4 / EBU R128), true peak and a true-peak-aware limiter.

Target by default: -14 LUFS integrated, true peak <= -1 dBTP.
"""
import json
import subprocess

import numpy as np
from scipy import signal, ndimage

from .dsp import SR, stereo

# K-weighting coefficients for 48 kHz (BS.1770-4)
_K1 = ([1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585])
_K2 = ([1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621])


def kweight(x):
    y = signal.lfilter(*_K1, x, axis=0)
    return signal.lfilter(*_K2, y, axis=0)


def lufs(x):
    """Integrated loudness in LUFS (gated)."""
    x = stereo(np.asarray(x, np.float64))
    y = kweight(x)
    blk, hop = int(0.4 * SR), int(0.1 * SR)
    if len(y) < blk:
        z = np.mean(y ** 2, axis=0)
        return -0.691 + 10 * np.log10(np.sum(z) + 1e-12)
    sq = y ** 2
    cs = np.vstack([np.zeros((1, 2)), np.cumsum(sq, axis=0)])
    starts = np.arange(0, len(y) - blk + 1, hop)
    z = (cs[starts + blk] - cs[starts]) / blk           # (blocks, ch)
    lk = -0.691 + 10 * np.log10(np.sum(z, axis=1) + 1e-12)
    g1 = lk > -70
    if not np.any(g1):
        return -70.0
    zm = np.mean(z[g1], axis=0)
    rel = -0.691 + 10 * np.log10(np.sum(zm) + 1e-12) - 10
    g2 = g1 & (lk > rel)
    zm = np.mean(z[g2], axis=0)
    return -0.691 + 10 * np.log10(np.sum(zm) + 1e-12)


def true_peak_db(x):
    x = stereo(np.asarray(x, np.float64))
    up = signal.resample_poly(x, 4, 1, axis=0)
    return 20 * np.log10(np.max(np.abs(up)) + 1e-12)


def limiter(x, ceiling_db=-1.0, lookahead=0.0015, release=0.08, block=32):
    """True-peak-aware brickwall limiter. Detection on 4x oversampled signal; gain computed
    at control rate (block samples) with instant attack (via lookahead) and exponential
    release, then interpolated back to audio rate."""
    x = stereo(np.asarray(x, np.float64))
    n = len(x)
    c = 10 ** (ceiling_db / 20)
    up = np.abs(signal.resample_poly(x, 4, 1, axis=0)).max(axis=1)[: n * 4]
    pk = up.reshape(-1, 4).max(axis=1) if len(up) >= n * 4 else np.pad(up, (0, n * 4 - len(up))).reshape(-1, 4).max(axis=1)
    la = max(1, int(lookahead * SR))
    pk = ndimage.maximum_filter1d(pk, size=2 * la + 1, mode="nearest")
    nb = int(np.ceil(n / block))
    pkb = np.pad(pk, (0, nb * block - n)).reshape(nb, block).max(axis=1)
    need = np.minimum(1.0, c / np.maximum(pkb, 1e-9))
    a = np.exp(-block / (release * SR))
    g = np.empty(nb)
    prev = 1.0
    for i in range(nb):
        v = need[i]
        prev = v if v < prev else prev * a + v * (1 - a)
        g[i] = prev
    # control points at block starts; take min with neighbour so interpolation never overshoots
    gmin = np.minimum(g, np.concatenate([g[1:], g[-1:]]))
    gs = np.interp(np.arange(n), np.arange(nb) * block, gmin)
    return x * gs[:, None]


def master(x, target=-14.0, ceiling=-1.0, iters=4):
    """Normalize to target LUFS with a true-peak ceiling. Returns (y, report)."""
    y = stereo(np.asarray(x, np.float64))
    gain_db = 0.0
    for _ in range(iters):
        l0 = lufs(y)
        y = y * 10 ** ((target - l0) / 20)
        gain_db += target - l0
        if true_peak_db(y) > ceiling:
            y = limiter(y, ceiling - 0.15)
        if abs(lufs(y) - target) < 0.2 and true_peak_db(y) <= ceiling:
            break
    rep = {"lufs": round(lufs(y), 2), "true_peak_db": round(true_peak_db(y), 2), "gain_db": round(gain_db, 2)}
    return y, rep


def ffmpeg_loudness(path):
    """Independent check with ffmpeg's ebur128 filter -> {'I': LUFS, 'TP': dBTP}."""
    r = subprocess.run(["ffmpeg", "-nostats", "-hide_banner", "-i", path, "-filter_complex",
                        "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    txt = r.stderr
    out = {}
    try:
        tail = txt[txt.rindex("Summary:"):]
        for line in tail.splitlines():
            line = line.strip()
            if line.startswith("I:"):
                out["I"] = float(line.split()[1])
            elif line.startswith("Peak:"):
                out["TP"] = float(line.split()[1])
            elif line.startswith("LRA:"):
                out["LRA"] = float(line.split()[1])
    except ValueError:
        pass
    return out
