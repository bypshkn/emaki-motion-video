"""Data layers: CSV/JSON loading, counters, bar/line/donut charts.

Charts are Groups of ordinary primitives (Rect, PathShape, Arc, Text, Counter), so they
export to After Effects as shape and text layers.
"""
import csv
import json
import math
import os

from ..core import Group, Layer, Prop, P_, color, skia, CURRENT
from ..easing import ease as _ease
from .text import Text, layout_text
from .shape import Rect, Line, PathShape, Arc, Ellipse, polyline_path


# ----------------------------------------------------------------------------- loading

def _num(v):
    if v is None:
        return v
    s = str(v).strip().replace(" ", "").replace(" ", "")
    if s.endswith("%"):
        s = s[:-1]
    try:
        if s.count(",") == 1 and "." not in s:
            s = s.replace(",", ".")
        f = float(s.replace(",", ""))
        return int(f) if f.is_integer() and "." not in s else f
    except ValueError:
        return v


def load_csv(path, delimiter=None):
    """CSV -> list of dicts with numbers converted. Delimiter auto-detected (, ; tab)."""
    p = path if os.path.isabs(path) else os.path.join(getattr(CURRENT["project"], "root", "") or "", path)
    with open(p, encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        if delimiter is None:
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
            except csv.Error:
                delimiter = ","
        rows = list(csv.DictReader(f, delimiter=delimiter))
    return [{k.strip(): _num(v) for k, v in r.items()} for r in rows]


def load_json(path):
    p = path if os.path.isabs(path) else os.path.join(getattr(CURRENT["project"], "root", "") or "", path)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def nice_max(v, steps=(1, 2, 2.5, 5, 10)):
    """Round an axis maximum up to a 'nice' number."""
    if v <= 0:
        return 1.0
    e = 10 ** math.floor(math.log10(v))
    for s in steps:
        if v <= s * e:
            return s * e
    return 10 * e


def fmt_number(v, decimals=0, sep=None, dec=None, prefix="", suffix=""):
    """Separators follow the project language unless given: English "1,284.5", other languages
    "1\u202f284,5" (narrow nbsp and a decimal comma). The currency sign comes from the copy
    (prefix / suffix)."""
    sep, dec = _separators(sep, dec)
    s = f"{abs(v):,.{decimals}f}"
    s = s.replace(",", "\x00").replace(".", dec).replace("\x00", sep)
    return f"{'-' if v < 0 else ''}{prefix}{s}{suffix}"


def _separators(sep=None, dec=None):
    from .. import fonts as _F
    english = getattr(_F, "LANGUAGE", "en") == "en"
    return (("," if english else "\u202f") if sep is None else sep,
            ("." if english else ",") if dec is None else dec)


# ----------------------------------------------------------------------------- counter

class Counter(Text):
    """Number that counts from a to b over [t0, t0+dur]. Tabular figures keep digits from
    jittering. sound='tick' emits rate-limited tick events as digits change."""
    kind = "counter"

    def __init__(self, a, b, t0, dur=1.6, ease="out_expo", decimals=0, sep=None, dec=None,
                 prefix="", suffix="", style="display", align="left", sound=None, **kw):
        self.value = Prop(float(a), "value")
        self.value.key(t0, float(a)).key(t0 + dur, float(b), ease)
        sep, dec = _separators(sep, dec)
        self.fmt = dict(decimals=decimals, sep=sep, dec=dec, prefix=prefix, suffix=suffix)
        feats = kw.pop("features", None) or {}
        feats.setdefault("tnum", True)
        # separators the font lacks (U+202F is missing in many fonts) fall back to nbsp / space
        try:
            from .. import fonts as _F
            d = CURRENT["design"]
            spec = d.font(kw.get("style", style)) if d else {}
            face, _, _ = _F.resolve(kw.get("font") or spec.get("family", "DejaVu Sans"), kw.get("weight") or spec.get("weight", 400))
            for ch in (self.fmt["sep"],):
                if ch.strip() == "" and ord(ch) not in face.cmap:
                    self.fmt["sep"] = "\u00a0" if 0xA0 in face.cmap else " "
        except Exception:
            pass
        final = fmt_number(b, **self.fmt)
        super().__init__(final, style=style, align=align, features=feats, **kw)
        self._cache = {}
        self.t0, self.dur, self.sound = t0, dur, sound
        self.a, self.b = a, b
        self.src = kw.get("src", "brief")

    def text_at(self, t):
        return fmt_number(self.value.at(t), **self.fmt)

    def render(self, canvas, t, ctx):
        s = self.text_at(t)
        L = self._cache.get(s)
        if L is None:
            L = layout_text(s, self.st, None, "left", CURRENT["design"])
            # align to the final layout box
            dx = {"left": 0.0, "center": (self.L.width - L.width) / 2, "right": self.L.width - L.width}[self.align]
            for g in L.glyphs:
                g.x += dx
            self._cache[s] = L
        keep = self.L
        self.L = L
        try:
            super().render(canvas, t, ctx)
        finally:
            self.L = keep

    def audio_events(self):
        if not self.sound:
            return []
        ev = []
        last = None
        fps = 30
        n = int(self.dur * fps)
        lt = -1
        for i in range(n + 1):
            t = self.t0 + i / fps
            s = self.text_at(t)
            if s != last and (t - lt) >= 1 / 18:
                ev.append((t, self.sound, {"i": i}))
                lt = t
            last = s
        return ev


# ----------------------------------------------------------------------------- charts

class BarChart(Group):
    """Bars grow from a baseline with stagger. data: list of (label, value).
    Local coords: chart area (0, 0) .. (w, h); bars grow up (orientation 'v') or right ('h')."""
    kind = "bar_chart"

    def __init__(self, data, w, h, t0=0.0, orientation="v", max_value=None, bar="accent", other=None,
                 highlight=None, gap=0.35, radius=None, values=True, labels=True, label_style="caption",
                 value_style="body", stagger=None, dur=None, ease=None, axis=True, decimals=0,
                 suffix="", prefix="", value_color="text", label_color="muted", **kw):
        super().__init__(**kw)
        d = CURRENT["design"]
        dur = dur or (d.motion.durations["long"] if d else 1.0)
        stagger = stagger if stagger is not None else (d.motion.stagger * 2 if d else 0.08)
        ease = ease or (d.motion.easing["enter"] if d else "out_expo")
        n = len(data)
        mv = max_value or nice_max(max(v for _, v in data))
        self.w, self.h = w, h
        hl = set(highlight or [])
        if axis:
            if orientation == "v":
                ax = Line((0, h), (w, h), stroke="muted", stroke_width=max(1.5, (d.stroke if d else 2)), name="Axis")
            else:
                ax = Line((0, 0), (0, h), stroke="muted", stroke_width=max(1.5, (d.stroke if d else 2)), name="Axis")
            ax.draw_on(t0 - 0.2 if t0 >= 0.2 else t0, dur * 0.6)
            self.add(ax)
        slot = (w if orientation == "v" else h) / n
        bw = slot * (1 - gap)
        r = radius if radius is not None else min(bw * 0.12, d.radius if d else 6)
        for i, (lab, val) in enumerate(data):
            ti = t0 + i * stagger
            col = bar if (not hl or i in hl) else (other or "muted")
            if orientation == "v":
                bh = h * val / mv
                cx = slot * (i + 0.5)
                rect = Rect(bw, bh, radius=r, fill=col, pos=(cx, h - bh / 2), name=f"Bar {lab}")
                rect.grow(ti, axis="y", dur=dur, ease=ease)
                self.add(rect)
                if values:
                    c = Counter(0, val, ti, dur, ease="out_expo", decimals=decimals, suffix=suffix, prefix=prefix,
                                style=value_style, color=value_color, align="center", anchor="bc", src="data",
                                pos=(cx, h - bh - 0.25 * (d.size(value_style) if d else 24)), name=f"Value {lab}")
                    c.fade_in(ti, 0.25)
                    self.add(c)
                if labels:
                    tl = Text(str(lab), style=label_style, color=label_color, align="center", anchor="tc", src="data",
                              pos=(cx, h + 0.6 * (d.size(label_style) if d else 20)), name=f"Label {lab}")
                    tl.fade_in(ti, 0.3)
                    self.add(tl)
            else:
                bl = w * val / mv
                cy = slot * (i + 0.5)
                rect = Rect(bl, bw, radius=r, fill=col, pos=(bl / 2, cy), name=f"Bar {lab}")
                rect.grow(ti, axis="x", dur=dur, ease=ease)
                self.add(rect)
                if values:
                    c = Counter(0, val, ti, dur, ease="out_expo", decimals=decimals, suffix=suffix, prefix=prefix,
                                style=value_style, color=value_color, anchor="cl", src="data",
                                pos=(bl + 0.4 * (d.size(value_style) if d else 24), cy), name=f"Value {lab}")
                    c.fade_in(ti, 0.25)
                    self.add(c)
                if labels:
                    tl = Text(str(lab), style=label_style, color=label_color, align="right", anchor="cr", src="data",
                              pos=(-0.6 * (d.size(label_style) if d else 20), cy), name=f"Label {lab}")
                    tl.fade_in(ti, 0.3)
                    self.add(tl)


class LineChart(Group):
    """Line draws on left->right; optional area fill, dots, end-dot that rides the line
    tip and a grid. series: list of y values (evenly spaced) or (x, y) pairs."""
    kind = "line_chart"

    def __init__(self, series, w, h, t0=0.0, dur=None, ease="in_out_cubic", stroke="accent", stroke_width=None,
                 area=True, dots=False, tip=True, min_value=None, max_value=None, smooth=0.6, grid=4,
                 labels=None, label_style="caption", area_color=None, area_opacity=0.35, **kw):
        super().__init__(**kw)
        d = CURRENT["design"]
        dur = dur or (d.motion.durations["long"] * 1.8 if d else 2.0)
        sw = stroke_width or max(3.0, (d.stroke if d else 3) * 1.5)
        ys = [p[1] if isinstance(p, (tuple, list)) else p for p in series]
        xs = [p[0] if isinstance(p, (tuple, list)) else i for i, p in enumerate(series)]
        lo = min_value if min_value is not None else min(0, min(ys))
        hi = max_value or nice_max(max(ys))
        x0, x1 = min(xs), max(xs)
        pts = [((x - x0) / (x1 - x0 or 1) * w, h - (y - lo) / (hi - lo) * h) for x, y in zip(xs, ys)]
        self.pts = pts
        if grid:
            for k in range(grid + 1):
                y = h * k / grid
                gl = Line((0, y), (w, y), stroke="muted@0.35", stroke_width=1.5, name=f"Grid {k}")
                gl.draw_on(t0 - 0.3 + k * 0.05 if t0 >= 0.3 else t0, 0.6)
                self.add(gl)
        if area:
            ap = list(pts) + [(w, h), (0, h)]
            from .fill import Linear
            sc = color(area_color or stroke)
            ar = PathShape(polyline_path(pts, False, smooth), fill=Linear((0, 0), (0, h), [(0, (sc[0], sc[1], sc[2], area_opacity)), (1, (sc[0], sc[1], sc[2], 0.0))]), name="Area")
            path = polyline_path(pts, False, smooth)
            path.lineTo(w, h)
            path.lineTo(0, h)
            path.close()
            ar._path = path
            ar.clip = Prop((0, -h, 0, 3 * h), "clip")
            ar.clip.key(t0, (0, -h, 0, 3 * h)).key(t0 + dur, (0, -h, w, 3 * h), ease)
            self.add(ar)
        ln = PathShape(polyline_path(pts, False, smooth), stroke=stroke, stroke_width=sw, name="Line")
        ln.draw_on(t0, dur, ease)
        self._t0, self._dur, self._ease, self._w = t0, dur, _ease(ease), w
        self.line = ln
        self.add(ln)
        if dots:
            for i, (x, y) in enumerate(pts):
                tt = t0 + dur * (x / w if w else 0)
                dt = Ellipse(sw * 3.2, fill="bg", stroke=stroke, stroke_width=sw * 0.8, pos=(x, y), name=f"Dot {i}")
                dt.pop_in(tt - 0.05, 0.35, "out_back")
                self.add(dt)
        if tip:
            path = ln._path
            pm = skia.PathMeasure(path, False)
            L = pm.getLength()
            tipd = Ellipse(sw * 3.6, fill=stroke, name="Tip")
            e = _ease(ease)

            def where(t, _pm=pm, _L=L):
                u = (t - t0) / dur
                u = 0 if u < 0 else 1 if u > 1 else e(u)
                pos, _ = _pm.getPosTan(_L * u)
                return (pos.x(), pos.y())
            tipd.position.drive(where)
            tipd.ae["follow"] = ln          # AE: expression rides the line's trim end
            tipd.opacity.key(t0, 0).key(t0 + 0.15, 1, "out_quad")
            self.add(tipd)
        if labels:
            for i, lab in enumerate(labels):
                if lab is None:
                    continue
                x = pts[i][0]
                tl = Text(str(lab), style=label_style, color="muted", align="center", anchor="tc", src="data",
                          pos=(x, h + 0.6 * (d.size(label_style) if d else 18)), name=f"XLabel {i}")
                tl.fade_in(t0 + dur * (x / w if w else 0) - 0.1, 0.3)
                self.add(tl)


def _line_point_time(self, i):
    """Scene time (group-local) when the drawn line's tip reaches point i (for syncing hits)."""
    x = self.pts[i][0]
    target = x / self._w if self._w else 0.0
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if self._ease(mid) < target:
            lo = mid
        else:
            hi = mid
    return self._t0 + self._dur * (lo + hi) / 2


LineChart.point_time = _line_point_time


class Donut(Group):
    """Donut segments sweep in sequence. values -> fractions of the total."""
    kind = "donut"

    def __init__(self, values, radius, thickness, colors=None, t0=0.0, dur=None, ease=None, gap_deg=2.0,
                 track="muted@0.2", **kw):
        super().__init__(**kw)
        d = CURRENT["design"]
        dur = dur or (d.motion.durations["long"] * 1.4 if d else 1.5)
        ease = ease or "in_out_cubic"
        total = float(sum(values))
        colors = colors or ["accent", "accent_2", "text", "muted"]
        if track:
            tr = Arc(radius, 0, 359.99, stroke=track, stroke_width=thickness, cap="butt", name="Track")
            tr.opacity.key(t0 - 0.3, 0).key(t0, 1, "out_quad")
            self.add(tr)
        acc = 0.0
        for i, v in enumerate(values):
            frac = v / total
            start = acc * 360 + gap_deg / 2
            sweep = max(0.1, frac * 360 - gap_deg)
            a = Arc(radius, start, 0.0, stroke=colors[i % len(colors)], stroke_width=thickness, cap="butt",
                    name=f"Segment {i}")
            ts = t0 + acc * dur
            a.sweep.key(ts, 0.0).key(ts + frac * dur, sweep, ease)
            self.add(a)
            acc += frac
