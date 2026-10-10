"""Sound effects for timeline events. Each generator returns (stereo array, offset_s) where
offset_s is where the sound's perceptual hit sits relative to its start, so the hit lands
exactly on the event frame (a whoosh peaks at the cut, a riser ends at the accent)."""
import numpy as np

from .dsp import (SR, samples, tt, filt, sweep_filter, pan, stereo, fade, noise, sine, db, exp_decay)
from . import instruments as I
from .fx import reverb


def whoosh(rng, dur=0.7, bright=1.0, direction=1, **_):
    t = tt(dur)
    x = noise(dur, rng, "pink")
    peak = 0.62
    fcurve = lambda tt_: 350 + 2600 * bright * np.exp(-((tt_ / dur - peak) ** 2) / 0.05)
    x = sweep_filter(x, "bp", fcurve, 1.1)
    env = np.exp(-((t / dur - peak) ** 2) / (0.045 if dur < 0.5 else 0.06))
    x = x * env
    p = np.clip((t / dur - 0.5) * 2.2 * direction, -1, 1)
    out = np.stack([x * np.cos((p + 1) * np.pi / 4), x * np.sin((p + 1) * np.pi / 4)], 1)
    return fade(out * 0.9, 0.01, 0.05), dur * peak


def swish(rng, dur=0.32, **kw):
    x, off = whoosh(rng, dur, bright=1.6, **kw)
    return filt(x, "hp", 900) * 0.8, off


def riser(rng, dur=2.0, **_):
    t = tt(dur)
    nz = noise(dur, rng, "white")
    nz = sweep_filter(nz, "bp", lambda tt_: 400 * 2 ** (tt_ / dur * 4), 1.4)
    f = 180 * 2 ** (t / dur * 1.5)
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.25
    env = (t / dur) ** 2.2
    x = (nz * 0.8 + tone) * env
    out = reverb(stereo(x), 0.35, 1.6)
    return fade(out * 0.7, 0.05, 0.004), dur


def downlifter(rng, dur=1.4, **_):
    x, _o = riser(rng, dur)
    return x[::-1].copy(), 0.0


def impact(rng, size=1.0, **_):
    dur = 2.4
    t = tt(dur)
    f = 32 + 48 * np.exp(-t / 0.12)
    subx = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / (0.55 * size))
    nz = filt(noise(dur, rng), "lp", 2500) * np.exp(-t / 0.06)
    crack = filt(noise(dur, rng), "hp", 3000) * np.exp(-t / 0.012)
    x = np.tanh((subx * 1.1 + nz * 0.5 + crack * 0.25) * 1.4)
    out = reverb(stereo(x), 0.3, 2.4)
    return fade(out * 0.9, 0.0005, 0.3), 0.0


def sub_hit(rng, **_):
    """Demo-style sub hit: 60->38 Hz sine sweep, 1.2 s."""
    dur = 1.2
    t = tt(dur)
    f = 60 * np.exp(-t * 3) + 38
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3)
    return stereo(fade(x * 0.55 / 0.35, 0.001, 0.05)), 0.0


def click(rng, freq=2400, **_):
    """UI/typing click: 12 ms noise + tone (as in the terminal demo)."""
    L = samples(0.012)
    env = np.exp(-np.linspace(0, 9, L))
    fq = freq + rng.uniform(-400, 400)
    x = (rng.normal(0, 1, L) * 0.5 + np.sin(2 * np.pi * fq * np.arange(L) / SR)) * env
    return stereo(x * 0.1 / 0.35), 0.0


def type_(rng, **kw):
    return click(rng, **kw)


def tick(rng, **_):
    L = samples(0.02)
    t = np.arange(L) / SR
    x = np.sin(2 * np.pi * 3200 * t) * np.exp(-t / 0.004) + 0.2 * rng.normal(0, 1, L) * np.exp(-t / 0.002)
    return stereo(x * 0.18), 0.0


def blip(rng, freq=1200, **_):
    dur = 0.12
    t = tt(dur)
    f = freq * (1 + 0.35 * np.clip(t / 0.05, 0, 1))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.clip(t / 0.004, 0, 1) * np.exp(-t / 0.04)
    return stereo(x * 0.3), 0.0


def pop(rng, **_):
    dur = 0.14
    t = tt(dur)
    f = 650 * np.exp(-t / 0.03) + 220
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.035)
    return stereo(x * 0.45), 0.0


def chime(rng, freq=1046.5, **_):
    a = I.bell(freq, 0.8, 0.8, rng)
    b = I.bell(freq * 1.5, 0.8, 0.6, rng)
    n = max(len(a), len(b) + samples(0.11))
    x = np.zeros(n)
    x[: len(a)] += a
    x[samples(0.11): samples(0.11) + len(b)] += b
    return reverb(stereo(x), 0.25, 1.8), 0.0


def glitch(rng, dur=0.14, **_):
    """Bit-crushed noise burst (demo style), centered on the event."""
    L = samples(dur)
    nz = rng.normal(0, 1, L)
    crush = np.repeat(nz[::40], 40)[:L]
    env = np.exp(-np.linspace(0, 5, L))
    return stereo(0.22 / 0.35 * crush * env), 0.05


def shimmer(rng, dur=1.5, **_):
    t = tt(dur)
    x = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) for f in (1760, 2217, 2637, 3520)) / 4
    x *= np.sin(np.pi * np.clip(t / dur, 0, 1)) * (0.6 + 0.4 * np.sin(2 * np.pi * 7 * t))
    return reverb(stereo(x * 0.25), 0.4, 2.0), dur * 0.3


def beep(rng, freq=880, dur=0.15, **_):
    t = tt(dur)
    x = np.sin(2 * np.pi * freq * t) * np.clip(t / 0.005, 0, 1) * np.clip((dur - t) / 0.01, 0, 1)
    return stereo(x * 0.25), 0.0


def crash(rng, **_):
    return stereo(I.crash(1.0, rng)), 0.0


def kick(rng, **_):
    return stereo(I.kick(1.0, rng)), 0.0


SFX = {"whoosh": whoosh, "swish": swish, "riser": riser, "downlifter": downlifter, "impact": impact,
       "hit": impact, "sub_hit": sub_hit, "sub": sub_hit, "click": click, "type": type_, "tick": tick,
       "blip": blip, "pop": pop, "chime": chime, "notify": chime, "glitch": glitch, "shimmer": shimmer,
       "beep": beep, "crash": crash, "kick": kick}

# Levels after the 2026-10-08 review: low-end hits (impact, sub_hit, kick) were the loudest thing
# in the mix and made it muddy; they now sit 4-6 dB lower and every SFX goes through sfx_eq().
LEVEL_DB = {"whoosh": -7, "swish": -8, "riser": -8, "downlifter": -9, "impact": -7, "hit": -7, "sub_hit": -6,
            "sub": -6, "click": -2, "type": -2, "tick": -6, "blip": -8, "pop": -6, "chime": -8, "notify": -8,
            "glitch": -2, "shimmer": -6, "beep": -10, "crash": -10, "kick": -9}


def sfx_eq(x):
    """High-pass 40 Hz and -4 dB under 100 Hz: hits keep their weight without flooding the sub."""
    from .dsp import filt
    return filt(filt(x, "hp", 40, 0.7), "lowshelf", 100, 0.7, -4.0)


def render(events, n, seed=17, gain_db=0.0, warn=None):
    """events: list of engine Event -> stereo array (n, 2)."""
    out = np.zeros((n, 2))
    for k, e in enumerate(events):
        fn = SFX.get(e.kind)
        if fn is None:
            if warn:
                warn(f"unknown sfx kind '{e.kind}' -> blip")
            fn = blip
        rng = np.random.default_rng(seed * 100003 + k)
        params = {kk: v for kk, v in (e.params or {}).items() if kk not in ("source", "i", "gain_db", "pan")}
        x, off = fn(rng, **params)
        x = stereo(x)
        g = db(LEVEL_DB.get(e.kind, -6) + gain_db + (e.params or {}).get("gain_db", 0))
        p = (e.params or {}).get("pan")
        if p is not None:
            m = (x[:, 0] + x[:, 1]) / 2
            x = pan(m, p) * 1.2
        s = samples(e.t - off)
        if s < 0:
            x = x[-s:]
            s = 0
        e2 = min(n, s + len(x))
        if e2 > s:
            out[s:e2] += x[: e2 - s] * g
    return sfx_eq(out) if np.any(out) else out
