"""Light and material: what separates a designed frame from a flat UI screenshot.

KeyLight  a soft pool of light (radial falloff) that sits over or under the content and can
          travel: gives the frame a light source, real highlights and a falloff to dark.
Glass     a frosted panel: blurs what is behind it, tints it, catches light on its rim.

All values are in real output px (unlike Blur/DropShadow/Glow, see api.md section 10).
"""
import math

from ..core import Layer, Prop, color, skia, CURRENT, P_


class KeyLight(Layer):
    """Soft light pool. `pos` = centre, `radius` = where it fades out (px), `intensity` 0..1.
    blend: "screen" (light over dark grounds, default), "soft_light" (shapes the tones of a light
    ground without washing it out), "multiply" with a dark colour for a shadow pool.
    `squash` < 1 flattens the pool into an ellipse (a light raking across a surface)."""
    kind = "key_light"
    exportable = False

    def __init__(self, radius=900, color_="#FFFFFF", intensity=0.35, squash=1.0, falloff=0.45,
                 blend="screen", screen_space=False, **kw):
        kw.setdefault("blend", blend)
        super().__init__(**kw)
        self.radius = P_(radius, "radius")
        self.intensity = P_(intensity, "intensity")
        self.col = color_
        self.squash = float(squash)
        self.falloff = float(falloff)
        # screen_space=True: pos is in frame pixels and the pool ignores the camera (a light on
        # the ground of a travelling shot). Add it right after the background, with a depth
        # larger than every other layer, so it lights the ground and not the objects.
        self.screen_space = screen_space

    def local_bounds(self, t):
        r = self.radius.at(t)
        return (-r, -r * self.squash, r, r * self.squash)

    def render(self, canvas, t, ctx):
        r = max(1.0, self.radius.at(t))
        k = max(0.0, self.intensity.at(t))
        if k <= 0.002:
            return
        c = color(self.col)
        cols = [skia.Color4f(c[0], c[1], c[2], k), skia.Color4f(c[0], c[1], c[2], k * 0.42),
                skia.Color4f(c[0], c[1], c[2], k * 0.12), skia.Color4f(c[0], c[1], c[2], 0.0)]
        sh = skia.GradientShader.MakeRadial(skia.Point(0, 0), r, cols, [0.0, self.falloff * 0.6, self.falloff * 1.4, 1.0])
        canvas.save()
        sm = getattr(ctx, "screen_matrix", None)
        if self.screen_space and sm is not None:
            canvas.setMatrix(sm)
            x, y = self.position.at(t)
            canvas.translate(x, y)
        canvas.scale(1.0, self.squash)
        canvas.drawCircle(0, 0, r, skia.Paint(AntiAlias=True, Shader=sh, Dither=True))
        canvas.restore()


class Glass(Layer):
    """Frosted glass panel (w x h, centred on pos like a Rect).

    What sits behind it is blurred (`blur` px) and tinted; a light gradient runs top to
    bottom; the rim catches light at the top-left and fades. `amount` (0..1, animatable) drives
    all of it: animate `amount` to make the glass appear, not `opacity`.

    The backdrop is whatever was drawn before it IN THE SAME LAYER: keep a Glass at the top
    level of its scene (or in groups without opacity, blend, mask or fx), otherwise it only
    blurs its own group."""
    kind = "glass"
    exportable = False

    def __init__(self, w, h, radius=28, blur=28, tint="#FFFFFF", tint_alpha=0.10, rim=0.55,
                 light=0.10, amount=1.0, **kw):
        super().__init__(**kw)
        self.size = P_((w, h), "size")
        self.radius = float(radius)
        self.blur = P_(blur, "blur")
        self.tint, self.tint_alpha = tint, float(tint_alpha)
        self.rim, self.light = float(rim), float(light)
        self.amount = P_(amount, "amount")

    def local_bounds(self, t):
        w, h = self.size.at(t)
        return (-w / 2, -h / 2, w / 2, h / 2)

    def render(self, canvas, t, ctx):
        a = max(0.0, min(1.0, self.amount.at(t)))
        if a <= 0.002:
            return
        w, h = self.size.at(t)
        rect = skia.Rect.MakeXYWH(-w / 2, -h / 2, w, h)
        rr = skia.RRect.MakeRectXY(rect, self.radius, self.radius)
        canvas.save()
        canvas.clipRRect(rr, skia.ClipOp.kIntersect, True)
        s = max(0.0, self.blur.at(t)) * a
        if s > 0.3:
            # skia-python's SaveLayerRec keeps raw pointers: the filter and paint must stay
            # referenced until saveLayer returns (a temporary here segfaults)
            bf = skia.ImageFilters.Blur(s, s, skia.TileMode.kClamp)
            bp = skia.Paint()
            rec = skia.Canvas.SaveLayerRec(rect, bp, bf, 0)
            canvas.saveLayer(rec)
            canvas.restore()
            del rec, bf, bp
        c = color(self.tint)
        canvas.drawRect(rect, skia.Paint(Color4f=skia.Color4f(c[0], c[1], c[2], self.tint_alpha * a)))
        if self.light > 0:
            sh = skia.GradientShader.MakeLinear(
                [skia.Point(0, -h / 2), skia.Point(0, h / 2)],
                [skia.Color4f(1, 1, 1, self.light * a), skia.Color4f(1, 1, 1, 0.0)], [0.0, 0.6])
            canvas.drawRect(rect, skia.Paint(Shader=sh, Dither=True))
        canvas.restore()
        if self.rim > 0:
            sh = skia.GradientShader.MakeLinear(
                [skia.Point(-w / 2, -h / 2), skia.Point(w / 2, h / 2)],
                [skia.Color4f(1, 1, 1, self.rim * a), skia.Color4f(1, 1, 1, 0.06 * a),
                 skia.Color4f(1, 1, 1, 0.22 * a)], [0.0, 0.55, 1.0])
            p = skia.Paint(AntiAlias=True, Shader=sh, Style=skia.Paint.kStroke_Style, StrokeWidth=1.5)
            inner = skia.RRect.MakeRectXY(rect.makeInset(0.75, 0.75), self.radius - 0.75, self.radius - 0.75)
            canvas.drawRRect(inner, p)
