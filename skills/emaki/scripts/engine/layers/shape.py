"""Vector shapes: rect, ellipse, polygon, star, line, arc, SVG path, polyline, morph.

Rect/Ellipse/Polygon/Star/Arc are centered on the layer origin (like AE shape layers).
Stroke draw-on uses `trim` (start/end/offset Props, 0..1), per contour ("each") or over
the total length ("whole").
"""
import math
import re

import numpy as np

from ..core import Layer, Prop, P_, color, skcolor, skia
from .fill import as_fill, Solid


# ----------------------------------------------------------------------------- SVG path parsing

_cmd = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)")


def svg_path(d):
    """Parse SVG path data into a skia.Path (M L H V C S Q T A Z, abs + rel)."""
    toks = [(m.group(1), m.group(2)) for m in _cmd.finditer(d)]
    p = skia.Path()
    i = 0
    cur = [0.0, 0.0]
    start = [0.0, 0.0]
    last_ctrl = None
    last_cmd = None
    cmd = None

    def num():
        nonlocal i
        c, n = toks[i]
        i += 1
        return float(n)

    while i < len(toks):
        c, n = toks[i]
        if c:
            cmd = c
            i += 1
        elif cmd is None:
            raise ValueError("path must start with a command")
        rel = cmd.islower()
        C = cmd.upper()
        ox, oy = (cur if rel else (0.0, 0.0))
        if C == "M":
            x, y = num() + ox, num() + oy
            p.moveTo(x, y)
            cur = [x, y]
            start = [x, y]
            cmd = "l" if rel else "L"
            last_ctrl = None
        elif C == "L":
            x, y = num() + ox, num() + oy
            p.lineTo(x, y)
            cur = [x, y]
            last_ctrl = None
        elif C == "H":
            x = num() + (cur[0] if rel else 0)
            p.lineTo(x, cur[1])
            cur[0] = x
            last_ctrl = None
        elif C == "V":
            y = num() + (cur[1] if rel else 0)
            p.lineTo(cur[0], y)
            cur[1] = y
            last_ctrl = None
        elif C == "C":
            x1, y1, x2, y2, x, y = num() + ox, num() + oy, num() + ox, num() + oy, num() + ox, num() + oy
            p.cubicTo(x1, y1, x2, y2, x, y)
            last_ctrl = ("C", x2, y2)
            cur = [x, y]
        elif C == "S":
            if last_ctrl and last_ctrl[0] == "C":
                x1, y1 = 2 * cur[0] - last_ctrl[1], 2 * cur[1] - last_ctrl[2]
            else:
                x1, y1 = cur
            x2, y2, x, y = num() + ox, num() + oy, num() + ox, num() + oy
            p.cubicTo(x1, y1, x2, y2, x, y)
            last_ctrl = ("C", x2, y2)
            cur = [x, y]
        elif C == "Q":
            x1, y1, x, y = num() + ox, num() + oy, num() + ox, num() + oy
            p.quadTo(x1, y1, x, y)
            last_ctrl = ("Q", x1, y1)
            cur = [x, y]
        elif C == "T":
            if last_ctrl and last_ctrl[0] == "Q":
                x1, y1 = 2 * cur[0] - last_ctrl[1], 2 * cur[1] - last_ctrl[2]
            else:
                x1, y1 = cur
            x, y = num() + ox, num() + oy
            p.quadTo(x1, y1, x, y)
            last_ctrl = ("Q", x1, y1)
            cur = [x, y]
        elif C == "A":
            rx, ry, rot, large, sweep = num(), num(), num(), num(), num()
            x, y = num() + ox, num() + oy
            p.arcTo(rx, ry, rot, skia.Path.ArcSize.kLarge_ArcSize if large else skia.Path.ArcSize.kSmall_ArcSize,
                    skia.PathDirection.kCW if sweep else skia.PathDirection.kCCW, x, y)
            cur = [x, y]
            last_ctrl = None
        elif C == "Z":
            p.close()
            cur = list(start)
            last_ctrl = None
            cmd = None if i >= len(toks) or toks[i][0] else cmd
        last_cmd = C
    return p


def to_path(x):
    if isinstance(x, skia.Path):
        return x
    if isinstance(x, str):
        return svg_path(x)
    if isinstance(x, (list, tuple)):
        return polyline_path(x)
    raise TypeError(f"cannot make a path from {type(x)}")


def polyline_path(pts, closed=False, smooth=0.0):
    """Points -> path. smooth>0 uses Catmull-Rom (tension = smooth) cubic segments."""
    p = skia.Path()
    if not pts:
        return p
    pts = [tuple(map(float, q)) for q in pts]
    p.moveTo(*pts[0])
    if smooth <= 0 or len(pts) < 3:
        for q in pts[1:]:
            p.lineTo(*q)
    else:
        n = len(pts)
        for i in range(n - 1 + (1 if closed else 0)):
            p0 = pts[(i - 1) % n] if (closed or i > 0) else pts[i]
            p1 = pts[i % n]
            p2 = pts[(i + 1) % n]
            p3 = pts[(i + 2) % n] if (closed or i + 2 < n) else p2
            k = smooth / 6 * 2
            c1 = (p1[0] + (p2[0] - p0[0]) * k, p1[1] + (p2[1] - p0[1]) * k)
            c2 = (p2[0] - (p3[0] - p1[0]) * k, p2[1] - (p3[1] - p1[1]) * k)
            p.cubicTo(*c1, *c2, *p2)
    if closed:
        p.close()
    return p


def trim_path(path, start, end, offset=0.0, mode="each"):
    """Return the [start, end] portion (0..1, with offset and wrap) of a path."""
    if start <= 0 and end >= 1:
        return path
    out = skia.Path()
    if end - start <= 1e-5:
        return out
    pm = skia.PathMeasure(path, False)
    contours = []
    while True:
        L = pm.getLength()
        if L > 0:
            contours.append(L)
        if not pm.nextContour():
            break
    if not contours:
        return out
    total = sum(contours)

    def seg(ranges_by_contour):
        pm2 = skia.PathMeasure(path, False)
        ci = 0
        while True:
            L = pm2.getLength()
            if L > 0:
                for a, b in ranges_by_contour.get(ci, []):
                    if b > a:
                        pm2.getSegment(a, b, out, True)
                ci += 1
            if not pm2.nextContour():
                break

    def wrap(a, b):
        a, b = a + offset, b + offset
        sh = math.floor(a)
        a, b = a - sh, b - sh
        return [(a, min(b, 1.0))] + ([(0.0, b - 1.0)] if b > 1 else [])

    rng = {}
    if mode == "each":
        for ci, L in enumerate(contours):
            rng[ci] = [(a * L, b * L) for a, b in wrap(start, end)]
    else:
        acc = 0.0
        spans = [(a * total, b * total) for a, b in wrap(start, end)]
        for ci, L in enumerate(contours):
            for a, b in spans:
                lo, hi = max(a, acc), min(b, acc + L)
                if hi > lo:
                    rng.setdefault(ci, []).append((lo - acc, hi - acc))
            acc += L
    seg(rng)
    return out


def resample(path, n=240):
    """Even resampling of the first contour -> (n, 2) array (for morphing)."""
    pm = skia.PathMeasure(path, False)
    L = pm.getLength()
    pts = []
    for i in range(n):
        pos, _ = pm.getPosTan(L * i / n if pm.isClosed() else L * i / (n - 1))
        pts.append((pos.x(), pos.y()))
    return np.array(pts), pm.isClosed()


def path_point(path, u):
    """Point and tangent angle at fraction u (0..1) of the whole path length."""
    pm = skia.PathMeasure(path, False)
    lens = []
    while True:
        L = pm.getLength()
        lens.append(L)
        if not pm.nextContour():
            break
    total = sum(lens)
    if total <= 0:
        return None
    target = max(0.0, min(1.0, u)) * total
    pm = skia.PathMeasure(path, False)
    acc = 0.0
    for L in lens:
        if acc + L >= target - 1e-6 and L > 0:
            pos, tan = pm.getPosTan(min(L, target - acc))
            return pos.x(), pos.y(), math.atan2(tan.y(), tan.x())
        acc += L
        if not pm.nextContour():
            break
    return None


def _light_ground():
    """True when the design's background is light (luminance > 0.5)."""
    try:
        from ..core import CURRENT, luminance
        d = CURRENT["design"]
        return d is not None and luminance(color("bg")) > 0.5
    except Exception:
        return False


def glow_dot(canvas, x, y, r, col, glow=1.0, core="#FFFFFF"):
    """Lead-element head. glow > 0: radial halo + bright core; glow = 0: flat dot."""
    c = color(col)
    if glow > 0:
        R = r * (3.5 + 2.5 * glow)
        # additive light only reads on dark grounds; on a light ground kPlus clips to white and the
        # head becomes a white disc, "a hole" (critic, clean test v2): draw the halo as tinted paint
        light = _light_ground()
        a0, a1 = (0.40, 0.15) if light else (0.55, 0.18)
        sh = skia.GradientShader.MakeRadial(
            skia.Point(x, y), R,
            [skia.Color4f(c[0], c[1], c[2], a0 * min(1.0, glow)), skia.Color4f(c[0], c[1], c[2], a1 * min(1.0, glow)),
             skia.Color4f(c[0], c[1], c[2], 0.0)], [0.0, 0.35, 1.0])
        canvas.drawCircle(x, y, R, skia.Paint(AntiAlias=True, Shader=sh,
                                              BlendMode=skia.BlendMode.kSrcOver if light else skia.BlendMode.kPlus))
        k = color(core)
        canvas.drawCircle(x, y, r * 0.55, skia.Paint(AntiAlias=True, Color4f=skia.Color4f(*k)))
    else:
        canvas.drawCircle(x, y, r * 0.6, skia.Paint(AntiAlias=True, Color4f=skia.Color4f(*c)))


# ----------------------------------------------------------------------------- shape layers

CAPS = {"butt": "kButt_Cap", "round": "kRound_Cap", "square": "kSquare_Cap"}
JOINS = {"miter": "kMiter_Join", "round": "kRound_Join", "bevel": "kBevel_Join"}


class Shape(Layer):
    kind = "shape"

    def __init__(self, fill=None, stroke=None, stroke_width=None, cap="round", join="round",
                 dash=None, trim=None, trim_mode="each", **kw):
        super().__init__(**kw)
        self.fill = as_fill(fill)
        self.stroke = None if stroke is None else Solid(stroke) if not hasattr(stroke, "paint") else stroke
        from ..core import CURRENT
        d = CURRENT["design"]
        self.stroke_width = P_(stroke_width if stroke_width is not None else (d.stroke if d else 3), "stroke_width")
        self.cap, self.join = cap, join
        self.dash = dash             # (on, off, phase Prop/number)
        self.trim_start = Prop(0.0, "trim_start")
        self.trim_end = Prop(1.0, "trim_end")
        self.trim_offset = Prop(0.0, "trim_offset")
        self.trim_mode = trim_mode
        if trim:
            self.trim_start.set(trim[0])
            self.trim_end.set(trim[1])

    def path(self, t):
        raise NotImplementedError

    def local_bounds(self, t):
        r = self.path(t).computeTightBounds()
        sw = self.stroke_width.at(t) if self.stroke else 0
        return (r.left() - sw, r.top() - sw, r.right() + sw, r.bottom() + sw)

    def draw_on(self, t, dur=None, ease=None, frm=0.0):
        """Stroke draws on: trim end frm -> 1."""
        dur = self._dur(dur, "long")
        self.trim_end.key(t, frm).key(t + dur, 1.0, ease or self._ez(None, "move"))
        return self

    def draw_off(self, t, dur=None, ease=None):
        dur = self._dur(dur, "medium")
        self.trim_start.key(t, 0.0).key(t + dur, 1.0, ease or self._ez(None, "exit"))
        return self

    def render(self, canvas, t, ctx):
        path = self.path(t)
        if self.fill is not None:
            canvas.drawPath(path, self.fill.paint(t, ctx))
        if self.stroke is not None:
            a, b, o = self.trim_start.at(t), self.trim_end.at(t), self.trim_offset.at(t)
            sp = trim_path(path, a, b, o, self.trim_mode) if (a > 0 or b < 1) else path
            paint = self.stroke.paint(t, ctx)
            paint.setStyle(skia.Paint.kStroke_Style)
            paint.setStrokeWidth(self.stroke_width.at(t))
            paint.setStrokeCap(getattr(skia.Paint, CAPS[self.cap]))
            paint.setStrokeJoin(getattr(skia.Paint, JOINS[self.join]))
            if self.dash:
                on, off = self.dash[0], self.dash[1]
                ph = self.dash[2].at(t) if len(self.dash) > 2 and isinstance(self.dash[2], Prop) else (self.dash[2] if len(self.dash) > 2 else 0)
                paint.setPathEffect(skia.DashPathEffect.Make([on, off], ph))
            canvas.drawPath(sp, paint)


class Rect(Shape):
    kind = "rect"

    def __init__(self, w, h, radius=None, **kw):
        super().__init__(**kw)
        from ..core import CURRENT
        d = CURRENT["design"]
        self.size = P_((w, h), "size")
        self.radius = P_(radius if radius is not None else (d.radius if d else 0), "radius")

    def path(self, t):
        w, h = self.size.at(t)
        r = min(self.radius.at(t), abs(w) / 2, abs(h) / 2)
        p = skia.Path()
        rect = skia.Rect.MakeXYWH(-w / 2, -h / 2, w, h)
        if r > 0:
            p.addRRect(skia.RRect.MakeRectXY(rect, r, r))
        else:
            p.addRect(rect)
        return p

    def grow(self, t, axis="x", dur=None, ease=None, origin="start"):
        """Grow width/height from 0 (origin 'start' keeps the left/top edge fixed)."""
        dur = self._dur(dur)
        w, h = self.size.rest()
        x, y = self.position.rest()
        e = ease or self._ez(None, "enter")
        if axis == "x":
            self.size.key(t, (0.0, h)).key(t + dur, (w, h), e)
            if origin == "start":
                self.position.key(t, (x - w / 2, y)).key(t + dur, (x, y), e)
        else:
            self.size.key(t, (w, 0.0)).key(t + dur, (w, h), e)
            if origin == "start":
                self.position.key(t, (x, y + h / 2)).key(t + dur, (x, y), e)
        return self


class Ellipse(Shape):
    kind = "ellipse"

    def __init__(self, w, h=None, **kw):
        super().__init__(**kw)
        self.size = P_((w, h if h is not None else w), "size")

    def path(self, t):
        w, h = self.size.at(t)
        p = skia.Path()
        p.addOval(skia.Rect.MakeXYWH(-w / 2, -h / 2, w, h))
        return p


class Polygon(Shape):
    kind = "polygon"

    def __init__(self, sides=6, radius=100, roundness=0.0, **kw):
        super().__init__(**kw)
        self.sides, self.radius = sides, P_(radius, "radius")
        self.roundness = roundness

    def path(self, t):
        r = self.radius.at(t)
        pts = [(r * math.cos(-math.pi / 2 + 2 * math.pi * i / self.sides),
                r * math.sin(-math.pi / 2 + 2 * math.pi * i / self.sides)) for i in range(self.sides)]
        p = polyline_path(pts, closed=True)
        if self.roundness > 0:
            p2 = skia.Path()
            skia.CornerPathEffect.Make(self.roundness * r).filterPath(p2, p, skia.StrokeRec(skia.StrokeRec.InitStyle.kFill_InitStyle), None)
            return p2
        return p


class Star(Shape):
    kind = "star"

    def __init__(self, points=5, outer=100, inner=45, **kw):
        super().__init__(**kw)
        self.points, self.outer, self.inner = points, P_(outer), P_(inner)

    def path(self, t):
        ro, ri = self.outer.at(t), self.inner.at(t)
        pts = []
        for i in range(self.points * 2):
            r = ro if i % 2 == 0 else ri
            a = -math.pi / 2 + math.pi * i / self.points
            pts.append((r * math.cos(a), r * math.sin(a)))
        return polyline_path(pts, closed=True)


class Line(Shape):
    kind = "line"

    def __init__(self, p0, p1, **kw):
        kw.setdefault("stroke", "text")
        super().__init__(**kw)
        self.p0, self.p1 = P_(p0, "p0"), P_(p1, "p1")

    def path(self, t):
        p = skia.Path()
        p.moveTo(*self.p0.at(t))
        p.lineTo(*self.p1.at(t))
        return p


class Arc(Shape):
    """Circular arc centered on origin. start/sweep in degrees (0 = 12 o'clock, clockwise)."""
    kind = "arc"

    def __init__(self, radius, start=0.0, sweep=360.0, **kw):
        kw.setdefault("stroke", "accent")
        super().__init__(**kw)
        self.radius, self.start_deg, self.sweep = P_(radius), P_(start), P_(sweep)

    def path(self, t):
        r = self.radius.at(t)
        p = skia.Path()
        sw = max(-359.99, min(359.99, self.sweep.at(t)))
        if abs(sw) < 0.01:
            return p
        p.addArc(skia.Rect.MakeXYWH(-r, -r, 2 * r, 2 * r), self.start_deg.at(t) - 90, sw)
        return p


class PathShape(Shape):
    """Arbitrary path: SVG `d` string, skia.Path or list of points (smooth=0..1)."""
    kind = "path"

    def __init__(self, d, closed=False, smooth=0.0, **kw):
        super().__init__(**kw)
        if isinstance(d, (list, tuple)):
            self._path = polyline_path(d, closed, smooth)
            self.points = d
        else:
            self._path = to_path(d)
            self.points = None
        self.d = d if isinstance(d, str) else None

    def path(self, t):
        return self._path


class Morph(Shape):
    """Morph between two or more paths. `progress` goes 0..len(paths)-1."""
    kind = "morph"

    def __init__(self, paths, progress=0.0, samples=240, **kw):
        super().__init__(**kw)
        arrs = []
        closed = True
        for p in paths:
            a, c = resample(to_path(p), samples)
            closed = closed and c
            arrs.append(a)
        # rotate each target's start index to best match the previous shape
        for k in range(1, len(arrs)):
            prev, cur = arrs[k - 1], arrs[k]
            if closed:
                best = min(range(0, samples, 2), key=lambda s: float(np.sum((np.roll(cur, -s, 0) - prev) ** 2)))
                arrs[k] = np.roll(cur, -best, 0)
        self.arrs = arrs
        self.closed = closed
        self.progress = P_(progress, "progress")

    def morph_to(self, t, index, dur=None, ease=None):
        dur = self._dur(dur)
        self.progress.key(t, self.progress.at(t)).key(t + dur, float(index), ease or self._ez(None, "move"))
        return self

    def path(self, t):
        v = max(0.0, min(len(self.arrs) - 1.0, self.progress.at(t)))
        i = min(int(v), len(self.arrs) - 2) if len(self.arrs) > 1 else 0
        f = v - i
        a = self.arrs[i] if len(self.arrs) == 1 else self.arrs[i] * (1 - f) + self.arrs[i + 1] * f
        return polyline_path(a.tolist(), closed=self.closed)


def svg_shapes(svg_file):
    """Minimal SVG importer -> list of PathShape layers (path/rect/circle/ellipse/polygon/
    polyline with fill/stroke colors; group transforms: translate/scale only)."""
    import xml.etree.ElementTree as ET
    tree = ET.parse(svg_file)
    root = tree.getroot()
    out = []

    def tf(s):
        m = skia.Matrix()
        for name, args in re.findall(r"(\w+)\(([^)]*)\)", s or ""):
            v = [float(x) for x in re.split(r"[ ,]+", args.strip()) if x]
            if name == "translate":
                m.preTranslate(v[0], v[1] if len(v) > 1 else 0)
            elif name == "scale":
                m.preScale(v[0], v[1] if len(v) > 1 else v[0])
            elif name == "matrix":
                mm = skia.Matrix()
                mm.setAll(v[0], v[2], v[4], v[1], v[3], v[5], 0, 0, 1)
                m.preConcat(mm)
        return m

    def walk(el, m, inherited):
        tag = el.tag.split("}")[-1]
        st = dict(inherited)
        for k in ("fill", "stroke", "stroke-width"):
            if el.get(k):
                st[k] = el.get(k)
        if el.get("style"):
            for kv in el.get("style").split(";"):
                if ":" in kv:
                    k, v = kv.split(":", 1)
                    st[k.strip()] = v.strip()
        mm = skia.Matrix()
        mm.setConcat(m, tf(el.get("transform")))
        p = None
        if tag == "path":
            p = svg_path(el.get("d", ""))
        elif tag == "rect":
            x, y, w, h = (float(el.get(k, 0)) for k in ("x", "y", "width", "height"))
            rx = float(el.get("rx", 0) or 0)
            p = skia.Path()
            p.addRRect(skia.RRect.MakeRectXY(skia.Rect.MakeXYWH(x, y, w, h), rx, rx))
        elif tag in ("circle", "ellipse"):
            cx, cy = float(el.get("cx", 0)), float(el.get("cy", 0))
            rx = float(el.get("r", el.get("rx", 0)))
            ry = float(el.get("r", el.get("ry", rx)))
            p = skia.Path()
            p.addOval(skia.Rect.MakeLTRB(cx - rx, cy - ry, cx + rx, cy + ry))
        elif tag in ("polygon", "polyline"):
            v = [float(x) for x in re.split(r"[ ,]+", el.get("points", "").strip()) if x]
            p = polyline_path(list(zip(v[0::2], v[1::2])), closed=(tag == "polygon"))
        if p is not None:
            p.transform(mm)
            fill = st.get("fill", "#000000")
            stroke = st.get("stroke")
            out.append(PathShape(p, fill=None if fill in ("none", None) else fill,
                                 stroke=None if stroke in ("none", None) else stroke,
                                 stroke_width=float(st.get("stroke-width", 1)), name=el.get("id")))
        for c in el:
            walk(c, mm, st)

    walk(root, skia.Matrix(), {})
    return out
