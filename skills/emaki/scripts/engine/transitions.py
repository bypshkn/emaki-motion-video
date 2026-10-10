"""Scene transitions. A transition overlaps the end of scene A with the start of scene B
for `dur` seconds and composites both. `sound` adds an SFX event at the transition
midpoint (None to disable). Each transition also describes itself for the AE exporter.
"""
import math

from .core import color, c4f, skcolor, skia, CURRENT, FX_SCALE
from .easing import ease as _ease


class Transition:
    kind = "cut"
    default_sound = None

    def __init__(self, dur=0.5, ease=None, sound="default", **params):
        d = CURRENT["design"]
        self.dur = float(dur)
        self.ease = _ease(ease or (d.motion.easing.get("transition", d.motion.easing["move"]) if d else "in_out_cubic"))
        self.sound = self.default_sound if sound == "default" else sound
        self.params = params

    def W(self, ctx):
        return ctx.project.W

    def H(self, ctx):
        return ctx.project.H

    def render(self, canvas, draw_a, draw_b, p, ctx):
        (draw_b if p >= 0.5 else draw_a)(canvas)

    def on_add(self, project, t_mid):
        if self.sound:
            project.sfx(t_mid, self.sound, source="transition", accent=False)

    def ae(self):
        return {"type": self.kind, "dur": self.dur, "ease": self.ease.spec, **self.params}


class Cut(Transition):
    kind = "cut"

    def __init__(self, **kw):
        super().__init__(dur=0.0, **kw)


class Fade(Transition):
    kind = "fade"

    def render(self, canvas, draw_a, draw_b, p, ctx):
        draw_a(canvas)
        canvas.saveLayer(None, skia.Paint(Alphaf=self.ease(p)))
        draw_b(canvas)
        canvas.restore()


class Dip(Transition):
    """A fades to a color, then B fades up from it."""
    kind = "dip"

    def __init__(self, dur=0.6, color_="bg", **kw):
        super().__init__(dur, **kw)
        self.color = color_
        self.params["color"] = color_

    def render(self, canvas, draw_a, draw_b, p, ctx):
        c = color(self.color)
        if p < 0.5:
            draw_a(canvas)
            a = self.ease(p * 2)
        else:
            draw_b(canvas)
            a = 1 - self.ease((p - 0.5) * 2)
        canvas.drawColor(c4f((c[0], c[1], c[2], a)))


_DIR = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}


class Push(Transition):
    """B pushes A out. direction = where the content travels."""
    kind = "push"
    default_sound = "whoosh"

    def __init__(self, dur=0.6, direction="left", **kw):
        super().__init__(dur, **kw)
        self.direction = direction
        self.params["direction"] = direction

    def render(self, canvas, draw_a, draw_b, p, ctx):
        dx, dy = _DIR[self.direction]
        e = self.ease(p)
        W, H = self.W(ctx), self.H(ctx)
        canvas.save()
        canvas.translate(dx * W * e, dy * H * e)
        draw_a(canvas)
        canvas.restore()
        canvas.save()
        canvas.translate(-dx * W * (1 - e), -dy * H * (1 - e))
        draw_b(canvas)
        canvas.restore()


class Slide(Transition):
    """B slides over A; A drifts slightly (parallax)."""
    kind = "slide"
    default_sound = "whoosh"

    def __init__(self, dur=0.6, direction="left", parallax=0.25, **kw):
        super().__init__(dur, **kw)
        self.direction, self.parallax = direction, parallax
        self.params.update(direction=direction, parallax=parallax)

    def render(self, canvas, draw_a, draw_b, p, ctx):
        dx, dy = _DIR[self.direction]
        e = self.ease(p)
        W, H = self.W(ctx), self.H(ctx)
        canvas.save()
        canvas.translate(dx * W * e * self.parallax, dy * H * e * self.parallax)
        draw_a(canvas)
        canvas.restore()
        canvas.save()
        canvas.translate(-dx * W * (1 - e), -dy * H * (1 - e))
        canvas.clipRect(skia.Rect.MakeWH(W, H))
        draw_b(canvas)
        canvas.restore()


class Wipe(Transition):
    """Linear wipe revealing B. softness = feather as a fraction of the frame."""
    kind = "wipe"
    default_sound = "swish"

    def __init__(self, dur=0.6, direction="right", softness=0.0, **kw):
        super().__init__(dur, **kw)
        self.direction, self.softness = direction, softness
        self.params.update(direction=direction, softness=softness)

    def render(self, canvas, draw_a, draw_b, p, ctx):
        e = self.ease(p)
        W, H = self.W(ctx), self.H(ctx)
        draw_a(canvas)
        dx, dy = _DIR[self.direction]
        if self.softness <= 0:
            canvas.save()
            if dx > 0:
                r = skia.Rect.MakeLTRB(0, 0, W * e, H)
            elif dx < 0:
                r = skia.Rect.MakeLTRB(W * (1 - e), 0, W, H)
            elif dy > 0:
                r = skia.Rect.MakeLTRB(0, 0, W, H * e)
            else:
                r = skia.Rect.MakeLTRB(0, H * (1 - e), W, H)
            canvas.clipRect(r, True)
            draw_b(canvas)
            canvas.restore()
            return
        L = (W if dx else H)
        s = self.softness * L
        pos = -s + (L + 2 * s) * e
        canvas.saveLayer(None, None)
        draw_b(canvas)
        if dx:
            a, b = (pos - s, pos) if dx > 0 else (L - pos + s, L - pos)
            pts = [skia.Point(a, 0), skia.Point(b, 0)]
        else:
            a, b = (pos - s, pos) if dy > 0 else (L - pos + s, L - pos)
            pts = [skia.Point(0, a), skia.Point(0, b)]
        sh = skia.GradientShader.MakeLinear(pts, [skia.ColorBLACK, skia.ColorTRANSPARENT])
        canvas.drawPaint(skia.Paint(Shader=sh, BlendMode=skia.BlendMode.kDstIn))
        canvas.restore()


class Iris(Transition):
    """Circle reveal of B from `center` (scene px; default frame center)."""
    kind = "iris"
    default_sound = "whoosh"

    def __init__(self, dur=0.7, center=None, **kw):
        super().__init__(dur, **kw)
        self.center = center
        self.params["center"] = center

    def render(self, canvas, draw_a, draw_b, p, ctx):
        W, H = self.W(ctx), self.H(ctx)
        cx, cy = self.center or (W / 2, H / 2)
        R = max(math.hypot(cx - x, cy - y) for x, y in ((0, 0), (W, 0), (0, H), (W, H)))
        draw_a(canvas)
        path = skia.Path()
        path.addCircle(cx, cy, max(0.01, R * self.ease(p)))
        canvas.save()
        canvas.clipPath(path, doAntiAlias=True)
        draw_b(canvas)
        canvas.restore()


class Zoom(Transition):
    """Zoom-through: A scales up and fades, B settles in from slightly small."""
    kind = "zoom"
    default_sound = "whoosh"

    def __init__(self, dur=0.6, amount=0.35, **kw):
        super().__init__(dur, **kw)
        self.amount = amount
        self.params["amount"] = amount

    def render(self, canvas, draw_a, draw_b, p, ctx):
        W, H = self.W(ctx), self.H(ctx)
        e = self.ease(p)
        canvas.save()
        s = 1 + self.amount * e
        canvas.translate(W / 2, H / 2)
        canvas.scale(s, s)
        canvas.translate(-W / 2, -H / 2)
        canvas.saveLayer(None, skia.Paint(Alphaf=1 - e))
        draw_a(canvas)
        canvas.restore()
        canvas.restore()
        canvas.save()
        s = 1 - self.amount * 0.4 * (1 - e)
        canvas.translate(W / 2, H / 2)
        canvas.scale(s, s)
        canvas.translate(-W / 2, -H / 2)
        canvas.saveLayer(None, skia.Paint(Alphaf=e))
        draw_b(canvas)
        canvas.restore()
        canvas.restore()


class BlurDissolve(Transition):
    kind = "blur"

    def __init__(self, dur=0.7, sigma=30, **kw):
        super().__init__(dur, **kw)
        self.sigma = sigma
        self.params["sigma"] = sigma

    def render(self, canvas, draw_a, draw_b, p, ctx):
        e = self.ease(p)
        s = self.sigma * FX_SCALE * math.sin(math.pi * e)
        f = skia.ImageFilters.Blur(s, s) if s > 0.1 else None
        canvas.saveLayer(None, skia.Paint(ImageFilter=f) if f else None)
        draw_a(canvas)
        canvas.saveLayer(None, skia.Paint(Alphaf=e))
        draw_b(canvas)
        canvas.restore()
        canvas.restore()


class ShapeWipe(Transition):
    """A solid band (accent color) sweeps across: covers A, then uncovers B."""
    kind = "shape_wipe"
    default_sound = "swish"

    def __init__(self, dur=0.8, color_="accent", angle=-12.0, direction="right", **kw):
        super().__init__(dur, **kw)
        self.color, self.angle, self.direction = color_, angle, direction
        self.params.update(color=color_, angle=angle, direction=direction)

    def render(self, canvas, draw_a, draw_b, p, ctx):
        W, H = self.W(ctx), self.H(ctx)
        e = self.ease(p)
        (draw_a if e < 0.5 else draw_b)(canvas)
        D = math.hypot(W, H) * 1.2
        band = D
        x = -band + (W + 2 * band) * e if self.direction == "right" else W + band - (W + 2 * band) * e
        canvas.save()
        canvas.translate(x, H / 2)
        canvas.rotate(self.angle)
        canvas.drawRect(skia.Rect.MakeXYWH(-band / 2, -D, band, 2 * D),
                        skia.Paint(AntiAlias=True, Color4f=c4f(color(self.color))))
        canvas.restore()


class Glitch(Transition):
    """Hard switch at the midpoint with a pulse on the global glitch fx track."""
    kind = "glitch"
    default_sound = "glitch"

    def __init__(self, dur=0.24, amount=1.0, **kw):
        super().__init__(dur, **kw)
        self.amount = amount
        self.params["amount"] = amount

    def on_add(self, project, t_mid):
        project.pulse("glitch", t_mid, self.amount, attack=self.dur / 2, release=self.dur / 2)
        if "glitch" not in project.post:
            project.post["glitch"] = {"track_only": True}
        super().on_add(project, t_mid)

    def render(self, canvas, draw_a, draw_b, p, ctx):
        (draw_b if p >= 0.5 else draw_a)(canvas)


class Whip(Transition):
    """Whip pan: both scenes fly past with a directional smear that peaks mid-move.
    Works in any look (no glow needed); the most reliable 'energy' transition."""
    kind = "whip"
    default_sound = "whoosh"

    def __init__(self, dur=0.36, direction="left", blur=90.0, rotate=0.0, zoom=0.0, **kw):
        """rotate: degrees the frame rolls across the move (reference r03 whip-rotate uses
        ~25); zoom: how much the frame pulls back mid-move (0.15 = 15 %). Rotation and zoom are
        engine-only: the AE export keeps the slide + blur."""
        kw.setdefault("ease", "in_out_expo")
        super().__init__(dur, **kw)
        self.direction, self.blur, self.rotate, self.zoom = direction, blur, rotate, zoom
        self.params.update(direction=direction, blur=blur, rotate=rotate, zoom=zoom)

    def render(self, canvas, draw_a, draw_b, p, ctx):
        dx, dy = _DIR[self.direction]
        e = self.ease(p)
        W, H = self.W(ctx), self.H(ctx)
        s = self.blur * FX_SCALE * math.sin(math.pi * p) ** 1.5
        f = skia.ImageFilters.Blur(s if dx else 0.01, s if dy else 0.01, skia.TileMode.kDecal) if s > 0.5 else None
        for draw, off in ((draw_a, e), (draw_b, e - 1)):
            canvas.save()
            if self.rotate or self.zoom:
                k = 1.0 - self.zoom * math.sin(math.pi * p)
                canvas.translate(W / 2, H / 2)
                canvas.rotate(self.rotate * off)
                canvas.scale(k, k)
                canvas.translate(-W / 2, -H / 2)
            canvas.translate(dx * W * off, dy * H * off)
            if f is not None:
                canvas.saveLayer(None, skia.Paint(ImageFilter=f))
                draw(canvas)
                canvas.restore()
            else:
                draw(canvas)
            canvas.restore()


class FlashCut(Transition):
    """Cut hidden inside a full-frame colour flash (white or accent)."""
    kind = "flash"
    default_sound = "impact"

    def __init__(self, dur=0.3, color_="#FFFFFF", **kw):
        super().__init__(dur, **kw)
        self.color = color_
        self.params["color"] = color_

    def render(self, canvas, draw_a, draw_b, p, ctx):
        (draw_a if p < 0.5 else draw_b)(canvas)
        a = 1 - abs(p - 0.5) * 2
        c = color(self.color)
        canvas.drawColor(c4f((c[0], c[1], c[2], a ** 1.5)))


class ScaleThrough(Transition):
    """Punch through: A scales up hard and blurs out, B lands from slightly large."""
    kind = "scale_through"
    default_sound = "whoosh"

    def __init__(self, dur=0.4, amount=2.2, **kw):
        kw.setdefault("ease", "in_expo")
        super().__init__(dur, **kw)
        self.amount = amount
        self.params["amount"] = amount

    def render(self, canvas, draw_a, draw_b, p, ctx):
        W, H = self.W(ctx), self.H(ctx)
        if p < 0.5:
            u = self.ease(p * 2)
            s = 1 + (self.amount - 1) * u
            sig = 30 * FX_SCALE * u
            canvas.save()
            canvas.translate(W / 2, H / 2)
            canvas.scale(s, s)
            canvas.translate(-W / 2, -H / 2)
            canvas.saveLayer(None, skia.Paint(Alphaf=1 - u * 0.6, ImageFilter=skia.ImageFilters.Blur(sig, sig) if sig > 0.5 else None))
            draw_a(canvas)
            canvas.restore()
            canvas.restore()
        else:
            u = (p - 0.5) * 2
            from .easing import ease as _e
            v = _e("out_expo")(u)
            s = 1.25 - 0.25 * v
            canvas.save()
            canvas.translate(W / 2, H / 2)
            canvas.scale(s, s)
            canvas.translate(-W / 2, -H / 2)
            sig = 18 * FX_SCALE * (1 - v)
            canvas.saveLayer(None, skia.Paint(ImageFilter=skia.ImageFilters.Blur(sig, sig) if sig > 0.5 else None))
            draw_b(canvas)
            canvas.restore()
            canvas.restore()


REGISTRY = {c.kind: c for c in (Cut, Fade, Dip, Push, Slide, Wipe, Iris, Zoom, BlurDissolve, ShapeWipe, Glitch,
                                Whip, FlashCut, ScaleThrough)}


def make(kind, **kw):
    return REGISTRY[kind](**kw)
