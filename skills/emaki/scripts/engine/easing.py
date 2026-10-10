"""Easing library.

Every easing maps progress u in [0, 1] to eased progress (may overshoot for back,
elastic, spring). Named easings from the cubic family are defined as cubic-bezier
curves so the Python render and the After Effects export (speed/influence) are the
same curve, not approximations of each other.

Spec strings accepted by `ease()`:
  linear | hold | smooth
  in_/out_/in_out_ + sine|quad|cubic|quart|quint|expo|circ|back      e.g. "out_expo"
  back_out(2.2)            overshoot amount (default 1.70158)
  bezier(.2,.8,.2,1)       custom CSS-style cubic-bezier
  elastic_out(1, .3)       amplitude, period   (also elastic_in, elastic_in_out)
  bounce_out | bounce_in | bounce_in_out
  spring | spring(170,26) | spring(170,26,1) | spring:gentle|wobbly|stiff|slow|snappy
  steps(4)
CSS aliases: ease, ease-in, ease-out, ease-in-out.
"""
import math
import re
from functools import lru_cache

BEZIERS = {
    "in_sine": (0.12, 0, 0.39, 0), "out_sine": (0.61, 1, 0.88, 1), "in_out_sine": (0.37, 0, 0.63, 1),
    "in_quad": (0.11, 0, 0.5, 0), "out_quad": (0.5, 1, 0.89, 1), "in_out_quad": (0.45, 0, 0.55, 1),
    "in_cubic": (0.32, 0, 0.67, 0), "out_cubic": (0.33, 1, 0.68, 1), "in_out_cubic": (0.65, 0, 0.35, 1),
    "in_quart": (0.5, 0, 0.75, 0), "out_quart": (0.25, 1, 0.5, 1), "in_out_quart": (0.76, 0, 0.24, 1),
    "in_quint": (0.64, 0, 0.78, 0), "out_quint": (0.22, 1, 0.36, 1), "in_out_quint": (0.83, 0, 0.17, 1),
    "in_expo": (0.7, 0, 0.84, 0), "out_expo": (0.16, 1, 0.3, 1), "in_out_expo": (0.87, 0, 0.13, 1),
    "in_circ": (0.55, 0, 1, 0.45), "out_circ": (0, 0.55, 0.45, 1), "in_out_circ": (0.85, 0, 0.15, 1),
    "in_back": (0.36, 0, 0.66, -0.56), "out_back": (0.34, 1.56, 0.64, 1), "in_out_back": (0.68, -0.6, 0.32, 1.6),
    # CSS keywords
    "ease": (0.25, 0.1, 0.25, 1), "ease-in": (0.42, 0, 1, 1), "ease-out": (0, 0, 0.58, 1),
    "ease-in-out": (0.42, 0, 0.58, 1), "smooth": (0.37, 0, 0.63, 1),
}
SPRINGS = {  # stiffness, damping, mass (react-spring style presets)
    "default": (170, 26, 1), "gentle": (120, 14, 1), "wobbly": (180, 12, 1),
    "stiff": (210, 20, 1), "slow": (280, 60, 1), "snappy": (400, 28, 1),
}
DEFAULT = "in_out_cubic"


def _bezier_fn(x1, y1, x2, y2):
    cx, bx = 3 * x1, 3 * (x2 - x1) - 3 * x1
    ax = 1 - cx - bx
    cy, by = 3 * y1, 3 * (y2 - y1) - 3 * y1
    ay = 1 - cy - by

    def sx(s):
        return ((ax * s + bx) * s + cx) * s

    def dsx(s):
        return (3 * ax * s + 2 * bx) * s + cx

    def f(u):
        if u <= 0:
            return 0.0
        if u >= 1:
            return 1.0
        s = u
        for _ in range(8):
            x = sx(s) - u
            d = dsx(s)
            if abs(x) < 1e-7:
                break
            if abs(d) < 1e-6:
                break
            s -= x / d
        if not (0 <= s <= 1) or abs(sx(s) - u) > 1e-5:
            lo, hi = 0.0, 1.0
            s = u
            for _ in range(40):
                x = sx(s)
                if abs(x - u) < 1e-7:
                    break
                if x < u:
                    lo = s
                else:
                    hi = s
                s = (lo + hi) / 2
        return ((ay * s + by) * s + cy) * s
    return f


def _elastic(kind, amp=1.0, period=0.3):
    amp = max(1.0, amp)
    s = period / (2 * math.pi) * math.asin(1 / amp)

    def out(u):
        if u <= 0:
            return 0.0
        if u >= 1:
            return 1.0
        return amp * 2 ** (-10 * u) * math.sin((u - s) * 2 * math.pi / period) + 1

    if kind == "out":
        return out
    if kind == "in":
        return lambda u: 1 - out(1 - u)
    return lambda u: (1 - out(1 - 2 * u)) / 2 if u < 0.5 else (1 + out(2 * u - 1)) / 2


def _bounce_out(u):
    n1, d1 = 7.5625, 2.75
    if u < 1 / d1:
        return n1 * u * u
    if u < 2 / d1:
        u -= 1.5 / d1
        return n1 * u * u + 0.75
    if u < 2.5 / d1:
        u -= 2.25 / d1
        return n1 * u * u + 0.9375
    u -= 2.625 / d1
    return n1 * u * u + 0.984375


def spring_curve(stiffness=170.0, damping=26.0, mass=1.0, velocity=0.0):
    """Damped harmonic oscillator 0 -> 1, time-normalized so the segment ends at rest."""
    w0 = math.sqrt(stiffness / mass)
    zeta = damping / (2 * math.sqrt(stiffness * mass))

    if zeta < 1:
        wd = w0 * math.sqrt(1 - zeta * zeta)

        def x(t):
            e = math.exp(-zeta * w0 * t)
            return 1 - e * (math.cos(wd * t) + (zeta * w0 - velocity) / wd * math.sin(wd * t))
        settle = -math.log(0.001) / (zeta * w0)
    elif zeta == 1:
        def x(t):
            return 1 - math.exp(-w0 * t) * (1 + (w0 - velocity) * t)
        settle = 9.0 / w0
    else:
        r1 = -w0 * (zeta - math.sqrt(zeta * zeta - 1))
        r2 = -w0 * (zeta + math.sqrt(zeta * zeta - 1))
        c2 = (velocity - r1) / (r2 - r1) if r2 != r1 else 0
        c1 = -1 - c2

        def x(t):
            return 1 + c1 * math.exp(r1 * t) + c2 * math.exp(r2 * t)
        settle = -math.log(0.001) / abs(r1)
    end = x(settle)

    def f(u):
        if u <= 0:
            return 0.0
        if u >= 1:
            return 1.0
        v = x(u * settle) / end
        if u > 0.95:  # glide the last 5% onto exactly 1.0
            w = (u - 0.95) / 0.05
            v = v * (1 - w) + w
        return v
    f.settle = settle
    return f


class Ease:
    """Callable easing with metadata for the After Effects exporter."""

    def __init__(self, spec, fn, bezier=None, kind="bezier", params=None):
        self.spec = spec
        self.fn = fn
        self.bezier = bezier
        self.kind = kind          # bezier | linear | hold | expr
        self.params = params or {}

    def __call__(self, u):
        return self.fn(u)

    def __repr__(self):
        return f"Ease({self.spec!r})"

    def overshoots(self, n=64):
        return any(not (-1e-6 <= self.fn(i / n) <= 1 + 1e-6) for i in range(n + 1))


_num = r"[-+]?\d*\.?\d+(?:e[-+]?\d+)?"


@lru_cache(maxsize=512)
def ease(spec=None):
    """Return an Ease for a spec string (or pass through an Ease/callable)."""
    if spec is None:
        spec = DEFAULT
    if isinstance(spec, Ease):
        return spec
    if callable(spec):
        return Ease(getattr(spec, "__name__", "custom"), spec, kind="expr", params={"custom": True})
    s = str(spec).strip().lower().replace(" ", "")
    s = s.replace("ease_", "").replace("easeinout", "in_out_").replace("ease-", "ease-")
    if s == "linear":
        return Ease(s, lambda u: min(1.0, max(0.0, u)), bezier=(0, 0, 1, 1), kind="linear")
    if s == "hold":
        return Ease(s, lambda u: 1.0 if u >= 1 else 0.0, kind="hold")
    if s in BEZIERS:
        return Ease(s, _bezier_fn(*BEZIERS[s]), bezier=BEZIERS[s])
    m = re.fullmatch(r"(in|out|in_out)_back\((%s)\)" % _num, s) or re.fullmatch(r"back_(in|out|in_out)\((%s)\)" % _num, s)
    if m:
        k, amt = m.group(1), float(m.group(2))
        r = amt / 1.70158
        base = {"in": (0.36, 0, 0.66, -0.56), "out": (0.34, 1.56, 0.64, 1), "in_out": (0.68, -0.6, 0.32, 1.6)}[k]
        x1, y1, x2, y2 = base
        if k == "in":
            y2 = y2 * r
        elif k == "out":
            y1 = 1 + (y1 - 1) * r
        else:
            y1, y2 = y1 * r, 1 + (y2 - 1) * r
        bz = (x1, y1, x2, y2)
        return Ease(s, _bezier_fn(*bz), bezier=bz)
    m = re.fullmatch(r"back_(in|out|in_out)", s)
    if m:
        return ease(f"{m.group(1)}_back")
    m = re.fullmatch(r"bezier\((%s),(%s),(%s),(%s)\)" % ((_num,) * 4), s) or \
        re.fullmatch(r"cubic-bezier\((%s),(%s),(%s),(%s)\)" % ((_num,) * 4), s)
    if m:
        bz = tuple(float(g) for g in m.groups())
        if not (0 <= bz[0] <= 1 and 0 <= bz[2] <= 1):
            raise ValueError(f"bezier x control points must be in [0,1]: {spec}")
        return Ease(s, _bezier_fn(*bz), bezier=bz)
    m = re.fullmatch(r"elastic_(in|out|in_out)(?:\((%s)?,?(%s)?\))?" % (_num, _num), s)
    if m:
        amp = float(m.group(2)) if m.group(2) else 1.0
        per = float(m.group(3)) if m.group(3) else 0.3
        return Ease(s, _elastic(m.group(1), amp, per), kind="expr",
                    params={"type": "elastic", "mode": m.group(1), "amp": amp, "period": per})
    m = re.fullmatch(r"bounce_(in|out|in_out)", s)
    if m:
        k = m.group(1)
        if k == "out":
            fn = _bounce_out
        elif k == "in":
            def fn(u):
                return 1 - _bounce_out(1 - u)
        else:
            def fn(u):
                return (1 - _bounce_out(1 - 2 * u)) / 2 if u < 0.5 else (1 + _bounce_out(2 * u - 1)) / 2
        return Ease(s, fn, kind="expr", params={"type": "bounce", "mode": k})
    m = re.fullmatch(r"spring(?::(\w+))?(?:\((%s)?,?(%s)?,?(%s)?\))?" % (_num, _num, _num), s)
    if m:
        if m.group(1):
            k, c, ms = SPRINGS[m.group(1)]
        else:
            k, c, ms = SPRINGS["default"]
            if m.group(2):
                k = float(m.group(2))
            if m.group(3):
                c = float(m.group(3))
            if m.group(4):
                ms = float(m.group(4))
        return Ease(s, spring_curve(k, c, ms), kind="expr",
                    params={"type": "spring", "stiffness": k, "damping": c, "mass": ms})
    m = re.fullmatch(r"steps\((\d+)\)", s)
    if m:
        n = int(m.group(1))
        return Ease(s, lambda u: min(1.0, math.floor(u * n) / n) if u < 1 else 1.0, kind="expr",
                    params={"type": "steps", "n": n})
    raise ValueError(f"Unknown easing spec: {spec!r}")


def lerp(a, b, p):
    """Interpolate numbers, tuples/lists (component-wise) or hold non-numeric values."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a + (b - a) * p
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)) and len(a) == len(b):
        return tuple(x + (y - x) * p for x, y in zip(a, b))
    return b if p >= 1 else a


def tween(t, t0, t1, a, b, spec=None):
    """Value at time t of a single eased tween a->b over [t0, t1]."""
    if t1 <= t0:
        return b if t >= t1 else a
    u = (t - t0) / (t1 - t0)
    if u <= 0:
        return a
    if u >= 1:
        return b
    return lerp(a, b, ease(spec)(u))


def progress(t, t0, t1, spec=None):
    """Eased 0..1 progress of t within [t0, t1]."""
    return tween(t, t0, t1, 0.0, 1.0, spec)
