"""Dynamic primitives: the moving parts that keep a frame alive, independent of the look.

Comet        a lead element (glowing nib, ink pen, cursor) travelling along a path, with a tail;
             can leave the line drawn behind it. glow=0 gives a flat "pen" for non-neon styles.
GridPlane    a grid sheet; tilt it (rx) under a camera for a perspective floor, scroll it for speed.
Wire3D       rotating wireframe solids (cube, tetra, octa, icosa) with their own perspective.
Waveform     audio-reactive bars/line (reads out/audio/mix.wav when it exists).
KineticWords one word per beat, sized to fill the frame, with punch and optional colour flashes.
Flash        full-frame colour flash (a hit on a beat, or a cut disguised as light).
"""
import math
import os

import numpy as np

from ..core import Group, Layer, Prop, P_, color, skia, CURRENT, Pulse
from ..easing import ease as _ease
from .shape import to_path, trim_path, path_point, glow_dot
from .text import Text
from .fill import Background


class Comet(Layer):
    exportable = False      # AE: baked (glow head + tail); the drawn line could be a trimmed path
    """Lead element travelling along `path` (scene/local coords: SVG d, points or skia.Path).
    progress 0..1 is keyed by (t0, dur, ease); `keep` leaves the stroke drawn behind."""
    kind = "comet"

    def __init__(self, path, t0=0.0, dur=1.0, ease="in_out_cubic", tail=0.22, head=9.0, stroke="accent",
                 width=3.0, glow=1.0, core="#FFFFFF", keep=True, fade_out=None, **kw):
        super().__init__(**kw)
        self.path = to_path(path)
        self.progress = Prop(0.0, "progress")
        self.progress.key(t0, 0.0, "linear").key(t0 + dur, 1.0, ease)
        self.t0, self.dur = float(t0), float(dur)
        self.tail, self.head, self.stroke_c, self.width = tail, head, stroke, width
        self.glow, self.core, self.keep = glow, core, keep
        self.head_fade = fade_out       # seconds after arrival to fade the head (not self.fade_out:
                                        # that would shadow Layer.fade_out() and break .exit())

    def local_bounds(self, t):
        r = self.path.computeTightBounds()
        pad = self.head * 1.5
        return (r.left() - pad, r.top() - pad, r.right() + pad, r.bottom() + pad)

    def render(self, canvas, t, ctx):
        p = self.progress.at(t)
        if p <= 0:
            return
        c = color(self.stroke_c)
        if self.keep:
            seg = trim_path(self.path, 0.0, p, 0.0, "whole")
            canvas.drawPath(seg, skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=self.width,
                                            StrokeCap=skia.Paint.kRound_Cap, Color4f=skia.Color4f(*c)))
        # bright tail: a few segments with rising width/alpha toward the head
        if p < 1.0 or not self.keep:
            n = 6
            for i in range(n):
                a = max(0.0, p - self.tail * (1 - i / n))
                b = max(0.0, p - self.tail * (1 - (i + 1) / n))
                if b <= a:
                    continue
                seg = trim_path(self.path, a, b, 0.0, "whole")
                k = (i + 1) / n
                canvas.drawPath(seg, skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style,
                                                StrokeWidth=self.width * (1 + 1.2 * k * (self.glow > 0)),
                                                StrokeCap=skia.Paint.kRound_Cap,
                                                Color4f=skia.Color4f(c[0], c[1], c[2], c[3] * k)))
        head_alpha = 1.0
        if p >= 1.0 and self.head_fade is not None:
            head_alpha = max(0.0, 1 - (t - (self.t0 + self.dur)) / max(1e-3, self.head_fade))
        if head_alpha > 0:
            pt = path_point(self.path, p)
            if pt:
                canvas.saveLayer(None, skia.Paint(Alphaf=head_alpha)) if head_alpha < 1 else canvas.save()
                glow_dot(canvas, pt[0], pt[1], self.head, self.stroke_c, self.glow, self.core)
                canvas.restore()


class GridPlane(Layer):
    """Grid sheet centred on its position. Tilt with rx (e.g. 70) for a perspective floor;
    `scroll` (px/s) moves the lines for a sense of travel; `fade` softens the far edges."""
    kind = "grid_plane"
    exportable = False      # AE: baked with its camera projection

    def __init__(self, w=2400, h=2400, step=80, stroke="muted@0.35", width=1.5, scroll=(0.0, 0.0),
                 fade=0.35, **kw):
        super().__init__(**kw)
        self.w, self.h, self.step, self.stroke_c, self.width = w, h, step, stroke, width
        self.scroll, self.fade = scroll, fade

    def local_bounds(self, t):
        return (-self.w / 2, -self.h / 2, self.w / 2, self.h / 2)

    def render(self, canvas, t, ctx):
        c = color(self.stroke_c)
        paint = skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=self.width,
                           Color4f=skia.Color4f(*c))
        ox = (self.scroll[0] * t) % self.step
        oy = (self.scroll[1] * t) % self.step
        hw, hh = self.w / 2, self.h / 2
        if self.fade > 0:
            canvas.saveLayer(None, None)
        x = -hw + ox
        while x <= hw:
            canvas.drawLine(x, -hh, x, hh, paint)
            x += self.step
        y = -hh + oy
        while y <= hh:
            canvas.drawLine(-hw, y, hw, y, paint)
            y += self.step
        if self.fade > 0:
            r = max(hw, hh)
            sh = skia.GradientShader.MakeRadial(skia.Point(0, 0), r, [skia.ColorBLACK, skia.ColorBLACK, skia.ColorTRANSPARENT],
                                                [0.0, 1 - self.fade, 1.0])
            canvas.drawPaint(skia.Paint(Shader=sh, BlendMode=skia.BlendMode.kDstIn))
            canvas.restore()


_SOLIDS = {
    "cube": ([(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)],
             [(0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3), (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7)]),
    "tetra": ([(1, 1, 1), (-1, -1, 1), (-1, 1, -1), (1, -1, -1)], [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]),
    "octa": ([(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)],
             [(0, 2), (0, 3), (0, 4), (0, 5), (1, 2), (1, 3), (1, 4), (1, 5), (2, 4), (2, 5), (3, 4), (3, 5)]),
}
_phi = (1 + 5 ** 0.5) / 2
_ico_v = [(-1, _phi, 0), (1, _phi, 0), (-1, -_phi, 0), (1, -_phi, 0), (0, -1, _phi), (0, 1, _phi), (0, -1, -_phi),
          (0, 1, -_phi), (_phi, 0, -1), (_phi, 0, 1), (-_phi, 0, -1), (-_phi, 0, 1)]
_ico_e = sorted({tuple(sorted((i, j))) for i in range(12) for j in range(12) if i < j and
                 abs(sum((a - b) ** 2 for a, b in zip(_ico_v[i], _ico_v[j])) - 4.0) < 1e-6})
_SOLIDS["icosa"] = (_ico_v, _ico_e)


class Wire3D(Layer):
    """Rotating wireframe solid centred on its position. spin = deg/s around (x, y, z)."""
    kind = "wire3d"
    exportable = False

    def __init__(self, solid="cube", size=160, spin=(20, 35, 0), rot0=(15, 25, 0), stroke="text",
                 width=2.0, dots=True, focal=900, **kw):
        super().__init__(**kw)
        v, self.edges = _SOLIDS[solid]
        v = np.array(v, float)
        self.verts = v / np.abs(v).max() * size / 2
        self.size, self.spin, self.rot0 = size, spin, rot0
        self.stroke_c, self.width, self.dots, self.focal = stroke, width, dots, focal

    def local_bounds(self, t):
        s = self.size
        return (-s, -s, s, s)

    def render(self, canvas, t, ctx):
        ax, ay, az = (math.radians(self.rot0[i] + self.spin[i] * t) for i in range(3))
        cx, sx = math.cos(ax), math.sin(ax)
        cy, sy = math.cos(ay), math.sin(ay)
        cz, sz = math.cos(az), math.sin(az)
        R = (np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]]) @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]) @
             np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]]))
        p = self.verts @ R.T
        k = self.focal / (self.focal + p[:, 2])
        xy = p[:, :2] * k[:, None]
        c = color(self.stroke_c)
        paint = skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=self.width,
                           StrokeCap=skia.Paint.kRound_Cap)
        zmin, zmax = p[:, 2].min(), p[:, 2].max()
        for i, j in self.edges:
            zm = (p[i, 2] + p[j, 2]) / 2
            depth = 1 - 0.55 * (zm - zmin) / (zmax - zmin + 1e-6)     # far edges dimmer
            paint.setColor4f(skia.Color4f(c[0], c[1], c[2], c[3] * depth))
            canvas.drawLine(xy[i, 0], xy[i, 1], xy[j, 0], xy[j, 1], paint)
        if self.dots:
            dp = skia.Paint(AntiAlias=True, Color4f=skia.Color4f(*c))
            for q in xy:
                canvas.drawCircle(q[0], q[1], self.width * 1.6, dp)


class Waveform(Layer):
    """Audio-reactive display of the last `window` seconds. mode: bars | line | mirror.
    Uses <project>/out/audio/mix.wav when present, else a deterministic stand-in."""
    kind = "waveform"
    exportable = False

    def __init__(self, w=800, h=160, bars=72, mode="mirror", stroke="accent", window=1.6, gain=1.0, **kw):
        super().__init__(**kw)
        self.w, self.h, self.bars, self.mode, self.stroke_c = w, h, bars, mode, stroke
        self.window, self.gain = window, gain
        self._env = None

    def _load(self):
        if self._env is not None:
            return
        proj = CURRENT["project"]
        path = os.path.join(getattr(proj, "root", "") or "", "out", "audio", "mix.wav")
        if os.path.exists(path):
            import wave
            with wave.open(path, "rb") as wv:
                n, ch, sw, sr = wv.getnframes(), wv.getnchannels(), wv.getsampwidth(), wv.getframerate()
                raw = wv.readframes(n)
            if sw == 3:
                b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
                x = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
                x = np.where(x & 0x800000, x - 0x1000000, x) / 8388608.0
            else:
                x = np.frombuffer(raw, "<i2") / 32768.0
            x = np.abs(x.reshape(-1, ch)).mean(axis=1)
            hop = sr // 200
            self._env = np.array([x[i:i + hop].max() for i in range(0, len(x) - hop, hop)])
            self._env /= max(1e-6, np.percentile(self._env, 98))
            self._rate = 200.0
        else:
            rng = np.random.default_rng(11)
            n = 200 * 600
            base = np.abs(np.convolve(rng.standard_normal(n), np.ones(9) / 9, "same"))
            self._env = base / base.max() * 1.6
            self._rate = 200.0

    def local_bounds(self, t):
        return (0, -self.h / 2, self.w, self.h / 2)

    def render(self, canvas, t, ctx):
        self._load()
        t_abs = ctx.t_abs
        c = color(self.stroke_c)
        vals = []
        for i in range(self.bars):
            tt = t_abs - self.window * (1 - i / max(1, self.bars - 1))
            k = int(tt * self._rate)
            v = self._env[k] if 0 <= k < len(self._env) else 0.0
            vals.append(min(1.0, v * self.gain))
        bw = self.w / self.bars
        paint = skia.Paint(AntiAlias=True, Color4f=skia.Color4f(*c))
        if self.mode == "line":
            p = skia.Path()
            for i, v in enumerate(vals):
                x, y = i * bw, -v * self.h / 2 * math.sin(i * 1.7 + t_abs * 9)
                p.moveTo(x, y) if i == 0 else p.lineTo(x, y)
            canvas.drawPath(p, skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=2.5,
                                          Color4f=skia.Color4f(*c)))
            return
        for i, v in enumerate(vals):
            hh = max(1.5, v * self.h / 2)
            x = i * bw + bw * 0.2
            if self.mode == "mirror":
                canvas.drawRoundRect(skia.Rect.MakeXYWH(x, -hh, bw * 0.6, 2 * hh), bw * 0.3, bw * 0.3, paint)
            else:
                canvas.drawRoundRect(skia.Rect.MakeXYWH(x, self.h / 2 - 2 * hh, bw * 0.6, 2 * hh), bw * 0.3, bw * 0.3, paint)


class _HoldZoom:
    def __init__(self, t0, t1, amount):
        self.t0, self.t1, self.amount = t0, t1, amount

    def eval(self, t, base):
        if not (self.t0 <= t <= self.t1):
            return base
        k = 1 + self.amount * (t - self.t0) / max(1e-3, self.t1 - self.t0)
        return tuple(b * k for b in base) if isinstance(base, tuple) else base * k

    def ae_expression(self):
        return (f"(time>={self.t0:g} && time<={self.t1:g}) ? mul(value, 1+{self.amount:g}*(time-{self.t0:g})/"
                f"{max(1e-3, self.t1 - self.t0):g}) : value")


def Flash(t, color_="accent", dur=0.16, peak=1.0, hold=0.0, name=None):
    """Full-frame colour flash: up in 2 frames, down over `dur` (a beat hit or a disguised cut)."""
    f = Background(color_, name=name or f"Flash {t:.2f}")
    f.on_top = True          # in a 3D scene it covers the whole set, not only the far layers
    f.opacity.key(t - 0.04, 0.0, "linear").key(t, peak, "out_quad").key(t + hold, peak, "linear") \
        .key(t + hold + dur, 0.0, "out_cubic")
    f.show(t - 0.05, t + hold + dur + 0.02)
    return f


class KineticWords(Group):
    """Words that land on beats. mode='replace': one word at a time, sized to fill
    `max_width`; mode='stack': words build up line by line. `flashes` cycles background
    colours per word (full frame), `colors` cycles word colours. Place the group at (0, 0):
    words are laid out in scene coordinates around `center`."""
    kind = "kinetic_words"

    def __init__(self, words, times, center=None, style="display", max_width=None, max_size=None,
                 mode="replace", colors=("text",), flashes=None, punch=0.18, end=None, enter="pop",
                 src="brief", line_gap=0.05, hold_zoom=0.06, **kw):
        super().__init__(**kw)
        P = CURRENT["project"]
        D = CURRENT["design"]
        cx, cy = center or (P.W / 2, P.H / 2)
        x0, _, x1, _ = D.safe() if D else (0, 0, P.W, 0)
        max_width = max_width or (x1 - x0)
        end = end if end is not None else (times[-1] + 1.0)
        self.words = list(words)
        self.end = end
        probes = [Text(w, style=style, src=src) for w in words]
        base = probes[0].st["size"]
        if mode == "replace":
            for i, (w, t0) in enumerate(zip(words, times)):
                t1 = times[i + 1] if i + 1 < len(times) else end
                if flashes:
                    fl = Background(flashes[i % len(flashes)], name=f"Word BG {i + 1}")
                    fl.show(t0, t1)
                    self.add(fl)
                pw = probes[i].width
                size = base * min(max_size / base if max_size else 99, max_width / max(pw, 1))
                tx = Text(w, style=style, size=size, color=colors[i % len(colors)], align="center", anchor="center",
                          pos=(cx, cy), src=src, name=f"Word {i + 1}")
                tx.show(t0, t1)
                tx.phrase_of = self
                if hold_zoom:
                    # never static: the word keeps growing slowly while it holds
                    tx.scale.mods.append(_HoldZoom(t0, t1, hold_zoom))
                if enter == "pop":
                    tx.scale.key(t0, (1 + punch, 1 + punch), "linear").key(t0 + 0.18, (1.0, 1.0), "out_expo")
                elif enter == "rise":
                    tx.reveal(t0, "rise", by="char", dur=0.22, stagger=0.02, ease="out_expo")
                elif enter == "mask":
                    tx.reveal(t0, "mask", by="line", dur=0.25, ease="out_expo")
                self.add(tx)
        else:
            lines = [Text(w, style=style, color=colors[i % len(colors)], align="left", anchor="tl", src=src,
                          name=f"Word {i + 1}") for i, w in enumerate(words)]
            widest = max(l.width for l in lines)
            k = min(max_size / base if max_size else 99, max_width / max(widest, 1))
            lines = [Text(w, style=style, size=base * k, color=colors[i % len(colors)], align="left", anchor="tl",
                          src=src, name=f"Word {i + 1}") for i, w in enumerate(words)]
            total_h = sum(l.height for l in lines) + line_gap * base * k * (len(lines) - 1) * 4
            y = cy - total_h / 2
            for i, (l, t0) in enumerate(zip(lines, times)):
                l.position.set((cx - max(x.width for x in lines) / 2, y))
                l.show(t0, end)
                l.phrase_of = self
                l.reveal(t0, "mask", by="line", dur=0.28, ease="out_expo")
                self.add(l)
                y += l.height + line_gap * base * k * 4
        self.times = list(times)
