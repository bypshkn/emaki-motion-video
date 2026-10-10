"""Fills: solid, linear/radial/conic gradients, noise, patterns. Geometry is in the owning
layer's local coordinates; Props make gradient geometry animatable."""
import math

from ..core import Layer, Prop, P_, color, skcolor, skia, CURRENT


def _stops(stops):
    cols = [skcolor(color(c)) for _, c in stops]
    pos = [float(p) for p, _ in stops]
    return cols, pos


class Fill:
    kind = "fill"

    def shader(self, t, ctx):
        return None

    def paint(self, t, ctx, opacity=1.0):
        p = skia.Paint(AntiAlias=True)
        sh = self.shader(t, ctx)
        if sh is not None:
            p.setShader(sh)
            p.setAlphaf(opacity)
        return p


class Solid(Fill):
    kind = "solid"

    def __init__(self, c):
        self.color = P_(color(c), "color")

    def paint(self, t, ctx, opacity=1.0):
        c = self.color.at(t)
        return skia.Paint(AntiAlias=True, Color4f=skia.Color4f(c[0], c[1], c[2], c[3] * opacity))


class Linear(Fill):
    kind = "linear"

    def __init__(self, p0, p1, stops):
        self.p0, self.p1 = P_(p0), P_(p1)
        self.stops = stops

    def shader(self, t, ctx):
        cols, pos = _stops(self.stops)
        a, b = self.p0.at(t), self.p1.at(t)
        return skia.GradientShader.MakeLinear([skia.Point(*a), skia.Point(*b)], cols, pos)


class Radial(Fill):
    kind = "radial"

    def __init__(self, center, radius, stops):
        self.center, self.radius = P_(center), P_(radius)
        self.stops = stops

    def shader(self, t, ctx):
        cols, pos = _stops(self.stops)
        return skia.GradientShader.MakeRadial(skia.Point(*self.center.at(t)), max(0.1, self.radius.at(t)), cols, pos)


class Conic(Fill):
    """Angular gradient around `center`, starting at `angle` degrees (0 = 3 o'clock)."""
    kind = "conic"

    def __init__(self, center, stops, angle=0.0):
        self.center, self.angle = P_(center), P_(angle)
        self.stops = stops

    def shader(self, t, ctx):
        cols, pos = _stops(self.stops)
        cx, cy = self.center.at(t)
        m = skia.Matrix()
        m.setRotate(self.angle.at(t), cx, cy)
        return skia.GradientShader.MakeSweep(cx, cy, cols, pos, localMatrix=m)


class Noise(Fill):
    """Fractal noise, tinted between two colors; `drift` px/s moves it for a living texture."""
    kind = "noise"

    def __init__(self, freq=0.004, octaves=3, seed=1, c0="bg", c1="surface", drift=(12, 0), turbulence=False):
        self.freq, self.octaves, self.seed = freq, octaves, seed
        self.c0, self.c1, self.drift, self.turb = c0, c1, drift, turbulence

    def shader(self, t, ctx):
        f = self.freq
        mk = skia.PerlinNoiseShader.MakeTurbulence if self.turb else skia.PerlinNoiseShader.MakeFractalNoise
        sh = mk(f, f, self.octaves, float(self.seed))
        m = skia.Matrix()
        m.setTranslate(-self.drift[0] * t, -self.drift[1] * t)
        sh = sh.makeWithLocalMatrix(m)
        a, b = color(self.c0), color(self.c1)
        # noise -> luminance -> lerp(a, b)
        lum = skia.ColorFilters.Matrix([0.33, 0.33, 0.33, 0, 0] * 3 + [0, 0, 0, 0, 1])
        k = [b[i] - a[i] for i in range(3)]
        tint = skia.ColorFilters.Matrix([k[0], 0, 0, 0, a[0], 0, k[1], 0, 0, a[1], 0, 0, k[2], 0, a[2], 0, 0, 0, 0, 1])
        return sh.makeWithColorFilter(skia.ColorFilters.Compose(tint, lum))


class Pattern(Fill):
    """Repeating pattern: dots | lines | grid | checker | diagonal. `move` px/s scrolls it."""
    kind = "pattern"

    def __init__(self, kind="dots", spacing=40, size=3, c="text@0.15", bg=None, angle=0.0, move=(0, 0)):
        self.pkind, self.spacing, self.size, self.c, self.bg = kind, spacing, size, c, bg
        self.angle, self.move = angle, move

    def shader(self, t, ctx):
        s = float(self.spacing)
        rec = skia.PictureRecorder()
        cv = rec.beginRecording(skia.Rect.MakeWH(s, s))
        if self.bg:
            cv.drawColor(skcolor(color(self.bg)))
        p = skia.Paint(AntiAlias=True, Color4f=skia.Color4f(*color(self.c)))
        k = self.pkind
        if k == "dots":
            cv.drawCircle(s / 2, s / 2, self.size, p)
        elif k == "lines":
            cv.drawRect(skia.Rect.MakeXYWH(0, s / 2 - self.size / 2, s, self.size), p)
        elif k == "grid":
            cv.drawRect(skia.Rect.MakeXYWH(0, 0, s, self.size), p)
            cv.drawRect(skia.Rect.MakeXYWH(0, 0, self.size, s), p)
        elif k == "checker":
            cv.drawRect(skia.Rect.MakeXYWH(0, 0, s / 2, s / 2), p)
            cv.drawRect(skia.Rect.MakeXYWH(s / 2, s / 2, s / 2, s / 2), p)
        elif k == "diagonal":
            p.setStyle(skia.Paint.kStroke_Style)
            p.setStrokeWidth(self.size)
            cv.drawLine(0, s, s, 0, p)
            cv.drawLine(-s / 2, s / 2, s / 2, -s / 2, p)
            cv.drawLine(s / 2, s * 1.5, s * 1.5, s / 2, p)
        pic = rec.finishRecordingAsPicture()
        m = skia.Matrix()
        m.setRotate(self.angle)
        m.postTranslate(self.move[0] * t, self.move[1] * t)
        return pic.makeShader(skia.TileMode.kRepeat, skia.TileMode.kRepeat, skia.FilterMode.kLinear, m, None)


def as_fill(f):
    if f is None or isinstance(f, Fill):
        return f
    return Solid(f)


class Background(Layer):
    """Full-frame fill. screen_space=True (default) keeps it locked to the frame even under
    a moving camera or inside a group, so the scene's edge never shows."""
    kind = "background"

    def __init__(self, fill="bg", screen_space=True, **kw):
        super().__init__(**kw)
        self.fill = as_fill(fill)
        self.screen_space = screen_space

    def local_bounds(self, t):
        p = CURRENT["project"]
        return (0, 0, p.W, p.H)

    def render(self, canvas, t, ctx):
        p = CURRENT["project"]
        sm = getattr(ctx, "screen_matrix", None)
        if self.screen_space and sm is not None:
            canvas.save()
            canvas.setMatrix(sm)
            canvas.drawRect(skia.Rect.MakeWH(p.W, p.H), self.fill.paint(t, ctx))
            canvas.restore()
        else:
            canvas.drawRect(skia.Rect.MakeWH(p.W, p.H), self.fill.paint(t, ctx))
