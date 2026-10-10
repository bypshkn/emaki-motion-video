"""Synth instruments and drums. Each returns a mono float64 array (or stereo where noted)
starting at the note onset and including its release tail."""
import numpy as np
from scipy import signal

from .dsp import (SR, samples, tt, adsr, exp_decay, additive, saw, square, triangle, sine, fm,
                  noise, filt, sweep_filter, pan, stereo, fade)


# ----------------------------------------------------------------------------- tonal

def warm_pad(f, dur, vel=0.8, rng=None, bright=0.4):
    """Soft pad: sine + triangle partials, slow swell. Editorial/ambient."""
    rel = 1.6
    n = dur + rel
    x = additive(f, n, [(1, 1.0), (2, 0.35 * bright + 0.1), (3, 0.18 * bright), (4, 0.08 * bright)], rng)
    x += 0.5 * additive(f * 1.003, n, [(1, 0.8), (2, 0.2)], rng)
    x += 0.5 * additive(f * 0.997, n, [(1, 0.8), (3, 0.1)], rng)
    env = adsr(dur, 0.8, 0.5, 0.85, rel, n)
    return fade(x * env * vel * 0.33)


def pad(f, dur, vel=0.8, rng=None, bright=0.5):
    """Detuned saw pad, low-passed. Electronic/minimal."""
    rel = 1.4
    n = dur + rel
    x = np.zeros(samples(n))
    for d in (-0.008, -0.003, 0.0, 0.004, 0.009):
        x += saw(f * (1 + d), n, n=24, rng=rng)
    x /= 5
    x = filt(x, "lp", 900 + 2600 * bright, 0.6)
    env = adsr(dur, 0.6, 0.6, 0.8, rel, n)
    return fade(x * env * vel * 0.5)


def strings(f, dur, vel=0.8, rng=None):
    rel = 1.2
    n = dur + rel
    t = tt(n)
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.2 * t) * np.clip(t / 0.8, 0, 1)
    x = np.zeros(len(t))
    for d in (-0.006, 0.0, 0.006):
        ph = 2 * np.pi * np.cumsum(f * (1 + d) * vib) / SR
        x += sum(np.sin(k * ph) / k for k in range(1, 14) if f * k < 12000)
    x = filt(x / 3, "lp", 2800, 0.5)
    x = filt(x, "hp", 90)
    env = adsr(dur, 0.9, 0.4, 0.9, rel, n)
    return fade(x * env * vel * 0.18)


def sub(f, dur, vel=0.9, rng=None):
    rel = 0.12
    n = dur + rel
    x = sine(f, n) + 0.12 * sine(2 * f, n)
    return fade(x * adsr(dur, 0.008, 0.05, 0.9, rel, n) * vel * 0.7, 0.004, 0.02)


def bass_synth(f, dur, vel=0.9, rng=None):
    rel = 0.1
    n = dur + rel
    x = 0.7 * saw(f, n, n=30) + 0.6 * sine(f, n)
    fc = lambda t: 260 + 1400 * np.exp(-t / 0.09)
    x = sweep_filter(x, "lp", fc, 0.9)
    return fade(x * adsr(dur, 0.004, 0.15, 0.75, rel, n) * vel * 0.55, 0.003, 0.02)


def bass_pluck(f, dur, vel=0.9, rng=None):
    n = min(dur, 0.5) + 0.1
    x = triangle(f, n) + 0.4 * sine(f, n)
    return fade(x * exp_decay(n, 0.18) * vel * 0.6, 0.003, 0.02)


def pluck(f, dur, vel=0.8, rng=None, bright=0.6, decay=0.996):
    """Karplus-Strong string via a single IIR (vectorized)."""
    rng = rng or np.random.default_rng(0)
    N = max(2, int(round(SR / f)))
    n = samples(min(max(dur, 0.6), 2.5))
    burst = rng.uniform(-1, 1, N)
    burst = filt(burst, "lp", 1500 + 7000 * bright)
    x = np.zeros(n)
    x[:N] = burst
    a = np.zeros(N + 2)
    a[0] = 1.0
    a[N] = -decay / 2
    a[N + 1] = -decay / 2
    y = signal.lfilter([1.0], a, x)
    y = filt(y, "hp", 70)
    return fade(y * vel * 0.5, 0.001, 0.05)


def bell(f, dur, vel=0.7, rng=None):
    n = max(dur, 1.8)
    t = tt(n)
    ienv = 2.2 * np.exp(-t / 0.35)
    x = np.sin(2 * np.pi * f * t + ienv * np.sin(2 * np.pi * f * 3.5 * t))
    x += 0.3 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t / 0.6)
    return fade(x * np.exp(-t / 0.9) * vel * 0.28, 0.002, 0.1)


def marimba(f, dur, vel=0.8, rng=None):
    n = 0.9
    t = tt(n)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.28)
    x += 0.35 * np.sin(2 * np.pi * f * 3.93 * t) * np.exp(-t / 0.06)
    x += 0.12 * np.sin(2 * np.pi * f * 9.2 * t) * np.exp(-t / 0.02)
    click = (rng or np.random.default_rng(1)).standard_normal(samples(0.004)) * 0.2
    x[: len(click)] += click
    return fade(x * vel * 0.45, 0.001, 0.05)


def epiano(f, dur, vel=0.75, rng=None):
    rel = 0.4
    n = dur + rel
    t = tt(n)
    x = np.sin(2 * np.pi * f * t + 0.8 * np.exp(-t / 0.4) * np.sin(2 * np.pi * f * t))
    x += 0.25 * np.sin(2 * np.pi * f * 14 * t) * np.exp(-t / 0.03)
    x *= 1 + 0.08 * np.sin(2 * np.pi * 4.5 * t)
    env = adsr(dur, 0.004, 1.2, 0.45, rel, n)
    return fade(x * env * vel * 0.4)


def piano(f, dur, vel=0.75, rng=None, felt=True):
    """Additive soft piano: inharmonic partials with per-partial decay; felt = darker, softer."""
    n = max(dur + 0.6, 1.2)
    t = tt(n)
    B = 0.0004
    x = np.zeros(len(t))
    for k in range(1, 13):
        fk = f * k * np.sqrt(1 + B * k * k)
        if fk > 14000:
            break
        amp = (1 / k ** (1.4 if felt else 1.0)) * (0.9 + 0.2 * ((k * 7919) % 5) / 5)
        tau = 2.6 / (1 + 0.35 * k) * (440 / max(f, 60)) ** 0.25
        x += amp * np.sin(2 * np.pi * fk * t) * np.exp(-t / tau)
    hold = np.ones(len(t))
    r = samples(dur)
    if r < len(t):
        hold[r:] = np.exp(-(t[r:] - dur) / 0.18)
    x *= hold
    x *= np.clip(t / (0.008 if felt else 0.002), 0, 1)
    if felt:
        x = filt(x, "lp", 3200, 0.5)
    return fade(x * vel * 0.3, 0.001, 0.05)


def arp_synth(f, dur, vel=0.7, rng=None):
    n = min(dur, 0.35) + 0.12
    x = 0.6 * square(f, n) + 0.5 * saw(f * 1.005, n, n=30)
    x = sweep_filter(x, "lp", lambda t: 600 + 4200 * np.exp(-t / 0.06), 1.1)
    return fade(x * adsr(min(dur, 0.35), 0.002, 0.08, 0.4, 0.12, n) * vel * 0.3, 0.002, 0.02)


def drone(dur, root=55.0, vel=1.0):
    """The 'terminal' drone: detuned low sines with slow phase and amplitude LFOs."""
    t = tt(dur)
    x = np.zeros(len(t))
    for k, amp in [(1.0, .30), (1.0073, .25), (1.4982, .18), (2.0036, .12), (2.996, .06), (4.009, .04)]:
        x += amp * np.sin(2 * np.pi * root * k * t + np.sin(2 * np.pi * 0.07 * t) * 2)
    x *= 0.35 * (0.7 + 0.3 * np.sin(2 * np.pi * 0.11 * t))
    return x * vel


def shimmer(dur, f=880.0, vel=1.0):
    t = tt(dur)
    return 0.03 / 0.35 * np.sin(2 * np.pi * f * t) * np.sin(2 * np.pi * 0.5 * t) ** 2 * vel


# ----------------------------------------------------------------------------- drums

def kick(vel=1.0, rng=None, tight=False):
    n = 0.45 if not tight else 0.3
    t = tt(n)
    f = 45 + 110 * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-t / (0.16 if not tight else 0.1))
    x += 0.25 * (rng or np.random.default_rng(2)).standard_normal(len(t)) * np.exp(-t / 0.003)
    return fade(np.tanh(x * 1.6) * vel * 0.9, 0.0005, 0.02)


def snare(vel=1.0, rng=None):
    rng = rng or np.random.default_rng(3)
    n = 0.3
    t = tt(n)
    nz = filt(rng.standard_normal(len(t)), "bp", 2200, 0.7) * np.exp(-t / 0.07)
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05)
    return fade((nz * 0.9 + tone * 0.6) * vel * 0.6, 0.0005, 0.02)


def clap(vel=1.0, rng=None):
    rng = rng or np.random.default_rng(4)
    n = 0.35
    t = tt(n)
    x = np.zeros(len(t))
    for k, d in enumerate((0.0, 0.011, 0.022, 0.034)):
        s = samples(d)
        L = len(t) - s
        x[s:] += rng.standard_normal(L) * np.exp(-np.arange(L) / SR / (0.008 if k < 3 else 0.09))
    x = filt(x, "bp", 1300, 0.8)
    return fade(x * vel * 0.55, 0.0005, 0.02)


def hat(vel=1.0, rng=None, open_=False):
    rng = rng or np.random.default_rng(5)
    n = 0.35 if open_ else 0.06
    t = tt(n)
    x = filt(rng.standard_normal(len(t)), "hp", 7200, 0.7)
    x *= np.exp(-t / (0.12 if open_ else 0.014))
    return fade(x * vel * 0.28, 0.0005, 0.01)


def shaker(vel=1.0, rng=None):
    rng = rng or np.random.default_rng(6)
    n = 0.09
    t = tt(n)
    x = filt(rng.standard_normal(len(t)), "bp", 6500, 1.2)
    env = np.clip(t / 0.015, 0, 1) * np.exp(-t / 0.025)
    return fade(x * env * vel * 0.3, 0.001, 0.01)


def rim(vel=1.0, rng=None):
    n = 0.08
    t = tt(n)
    x = filt((rng or np.random.default_rng(7)).standard_normal(len(t)), "bp", 1700, 3) * np.exp(-t / 0.01)
    x += 0.4 * np.sin(2 * np.pi * 820 * t) * np.exp(-t / 0.015)
    return fade(x * vel * 0.4, 0.0005, 0.01)


def tom(vel=1.0, rng=None, f0=110):
    n = 0.6
    t = tt(n)
    f = f0 * (1 + 0.6 * np.exp(-t / 0.04))
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.22)
    return fade(np.tanh(x * 1.4) * vel * 0.7, 0.0005, 0.03)


def crash(vel=1.0, rng=None):
    rng = rng or np.random.default_rng(8)
    n = 2.2
    t = tt(n)
    x = filt(rng.standard_normal(len(t)), "hp", 3800, 0.5) * np.exp(-t / 0.7)
    x += 0.15 * filt(rng.standard_normal(len(t)), "bp", 6000, 4) * np.exp(-t / 1.1)
    return fade(x * vel * 0.22, 0.0005, 0.2)


TONAL = {"warm_pad": warm_pad, "pad": pad, "strings": strings, "sub": sub, "bass_synth": bass_synth,
         "bass_pluck": bass_pluck, "pluck": pluck, "bell": bell, "marimba": marimba, "epiano": epiano,
         "piano": piano, "arp_synth": arp_synth}
DRUMS = {"kick": kick, "snare": snare, "clap": clap, "hat": hat, "ohat": lambda vel=1.0, rng=None: hat(vel, rng, True),
         "shaker": shaker, "rim": rim, "tom": tom, "crash": crash}
