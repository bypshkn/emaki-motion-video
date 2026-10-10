"""Stateless particle system: every particle's state is a closed-form function of its age,
so any frame renders independently (multiprocessing-safe, deterministic by seed).

After Effects has no faithful native equivalent, so the AE exporter bakes this layer to a
ProRes 4444 clip with alpha and marks it [BAKED].
"""
import math

import numpy as np

from ..core import Layer, color, skia, xform


class Particles(Layer):
    kind = "particles"
    exportable = False

    def __init__(self, emitter="point", at=(0, 0), size_of_emitter=(0, 0), rate=40.0, bursts=None,
                 t0=0.0, t1=None, life=(1.5, 3.0), speed=(80, 200), direction=-90.0, spread=360.0,
                 gravity=(0.0, 0.0), drag=0.0, size=(3, 8), size_end=0.0, colors=("text",),
                 opacity=(1.0, 0.0), shape="circle", turbulence=0.0, turb_freq=0.6, spin=(0, 0),
                 seed=1, max_particles=4000, stretch=0.0, **kw):
        super().__init__(**kw)
        self.cfg = dict(emitter=emitter, at=at, esize=size_of_emitter, rate=rate, bursts=bursts or [], t0=t0,
                        t1=t1, life=life, speed=speed, direction=direction, spread=spread, gravity=gravity,
                        drag=drag, size=size, size_end=size_end, colors=colors, opacity=opacity, shape=shape,
                        turbulence=turbulence, turb_freq=turb_freq, spin=spin, stretch=stretch)
        self.seed = seed
        self.max = max_particles
        self._built = None

    def _build(self, scene_dur):
        c = self.cfg
        rng = np.random.default_rng(self.seed)
        t1 = c["t1"] if c["t1"] is not None else scene_dur
        births = []
        if c["rate"] > 0 and t1 > c["t0"]:
            n = int((t1 - c["t0"]) * c["rate"])
            births += list(c["t0"] + (np.arange(n) + rng.uniform(0, 1, n)) / c["rate"])
        for bt, cnt in c["bursts"]:
            births += [bt] * int(cnt)
        births = np.array(births[: self.max], dtype=np.float64)
        n = len(births)
        life = rng.uniform(c["life"][0], c["life"][1], n)
        ang = np.radians(c["direction"] + rng.uniform(-c["spread"] / 2, c["spread"] / 2, n))
        spd = rng.uniform(c["speed"][0], c["speed"][1], n)
        vx, vy = np.cos(ang) * spd, np.sin(ang) * spd
        ax, ay = c["at"]
        ew, eh = c["esize"]
        em = c["emitter"]
        if em == "point":
            x0, y0 = np.full(n, ax, float), np.full(n, ay, float)
        elif em == "line":
            u = rng.uniform(-0.5, 0.5, n)
            x0, y0 = ax + u * ew, ay + u * eh
        elif em == "rect":
            x0, y0 = ax + rng.uniform(-0.5, 0.5, n) * ew, ay + rng.uniform(-0.5, 0.5, n) * eh
        elif em in ("circle", "ring"):
            a = rng.uniform(0, 2 * np.pi, n)
            r = (np.sqrt(rng.uniform(0, 1, n)) if em == "circle" else 1.0) * ew / 2
            x0, y0 = ax + np.cos(a) * r, ay + np.sin(a) * r
        else:
            raise ValueError(em)
        size = rng.uniform(c["size"][0], c["size"][1], n)
        col = rng.integers(0, len(c["colors"]), n)
        spin = rng.uniform(c["spin"][0], c["spin"][1], n)
        rot0 = rng.uniform(0, 360, n)
        ph = rng.uniform(0, 2 * np.pi, (n, 4))
        self._built = dict(b=births, life=life, vx=vx, vy=vy, x0=x0, y0=y0, size=size, col=col, spin=spin,
                           rot0=rot0, ph=ph)

    def state(self, t):
        if self._built is None:
            self._build(getattr(self.scene, "dur", 10.0))
        B = self._built
        c = self.cfg
        age = t - B["b"]
        alive = (age >= 0) & (age < B["life"])
        idx = np.nonzero(alive)[0]
        a = age[idx]
        k = c["drag"]
        gx, gy = c["gravity"]
        if k > 1e-6:
            e = np.exp(-k * a)
            fx = (1 - e) / k
            gxx = gx * (a / k - (1 - e) / k ** 2)
            gyy = gy * (a / k - (1 - e) / k ** 2)
        else:
            fx = a
            gxx, gyy = 0.5 * gx * a * a, 0.5 * gy * a * a
        x = B["x0"][idx] + B["vx"][idx] * fx + gxx
        y = B["y0"][idx] + B["vy"][idx] * fx + gyy
        if c["turbulence"] > 0:
            f = c["turb_freq"]
            ph = B["ph"][idx]
            x += c["turbulence"] * (np.sin(2 * np.pi * f * a + ph[:, 0]) + 0.5 * np.sin(4.1 * np.pi * f * a + ph[:, 1]))
            y += c["turbulence"] * (np.sin(2 * np.pi * f * a + ph[:, 2]) + 0.5 * np.sin(3.7 * np.pi * f * a + ph[:, 3]))
        u = a / B["life"][idx]
        sz = B["size"][idx] * (1 + (c["size_end"] - 1) * u)
        o0, o1 = c["opacity"]
        op = (o0 + (o1 - o0) * u) * np.clip(u / 0.08, 0, 1)
        rot = B["rot0"][idx] + B["spin"][idx] * a
        return idx, x, y, sz, op, rot, u

    def local_bounds(self, t):
        return None

    def render(self, canvas, t, ctx):
        idx, x, y, sz, op, rot, u = self.state(t)
        if len(idx) == 0:
            return
        cols = [color(cc) for cc in self.cfg["colors"]]
        shape = self.cfg["shape"]
        B = self._built
        paint = skia.Paint(AntiAlias=True)
        glyph = None
        if shape.startswith("glyph:"):
            from .. import fonts as F
            face, var, _ = F.resolve("DejaVu Sans", 400)
            ch = shape.split(":", 1)[1]
            gid = face.gid(ch)
            glyph = face.glyph_path(gid, var) if gid else None
        for n in range(len(idx)):
            cc = cols[B["col"][idx[n]]]
            paint.setColor4f(skia.Color4f(cc[0], cc[1], cc[2], cc[3] * max(0.0, min(1.0, op[n]))))
            s = max(0.0, sz[n])
            if s <= 0.05:
                continue
            if shape == "circle":
                canvas.drawCircle(x[n], y[n], s / 2, paint)
            elif shape == "square":
                canvas.save()
                canvas.translate(x[n], y[n])
                canvas.rotate(rot[n])
                canvas.drawRect(skia.Rect.MakeXYWH(-s / 2, -s / 2, s, s), paint)
                canvas.restore()
            elif shape in ("line", "spark"):
                vx, vy = B["vx"][idx[n]], B["vy"][idx[n]]
                L = math.hypot(vx, vy) + 1e-6
                ln = s * (3 + self.cfg["stretch"])
                paint.setStyle(skia.Paint.kStroke_Style)
                paint.setStrokeWidth(max(1.0, s / 4))
                paint.setStrokeCap(skia.Paint.kRound_Cap)
                canvas.drawLine(x[n], y[n], x[n] - vx / L * ln, y[n] - vy / L * ln, paint)
                paint.setStyle(skia.Paint.kFill_Style)
            elif glyph is not None:
                m = skia.Matrix()
                m.setTranslate(x[n], y[n])
                m.preRotate(rot[n])
                m.preScale(s, s)
                m.preTranslate(-0.3, 0.35)
                canvas.drawPath(xform(glyph, m), paint)
