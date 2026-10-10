"""Bitmap and SVG assets from the project's assets/ folder (the user's files only)."""
import os

from ..core import Layer, P_, skia, CURRENT


def asset_path(p):
    if os.path.isabs(p) and os.path.exists(p):
        return p
    proj = CURRENT["project"]
    base = getattr(proj, "root", None) or os.getcwd()
    for cand in (os.path.join(base, p), os.path.join(base, "assets", p)):
        if os.path.exists(cand):
            return cand
    raise FileNotFoundError(f"asset not found: {p} (looked in {base} and {base}/assets)")


class Image(Layer):
    """Bitmap centered on the origin. fit: contain | cover | stretch. radius rounds corners."""
    kind = "image"

    def __init__(self, path, w=None, h=None, fit="contain", radius=0.0, **kw):
        super().__init__(**kw)
        self.path = asset_path(path)
        data = skia.Data.MakeFromFileName(self.path)
        self.img = skia.Image.MakeFromEncoded(data)
        if self.img is None:
            raise ValueError(f"cannot decode image {path}")
        iw, ih = self.img.width(), self.img.height()
        if w is None and h is None:
            w, h = iw, ih
        elif w is None:
            w = h * iw / ih
        elif h is None:
            h = w * ih / iw
        self.size = P_((w, h), "size")
        self.fit = fit
        self.radius = P_(radius, "radius")

    def local_bounds(self, t):
        w, h = self.size.at(t)
        return (-w / 2, -h / 2, w / 2, h / 2)

    def render(self, canvas, t, ctx):
        w, h = self.size.at(t)
        iw, ih = self.img.width(), self.img.height()
        dst = skia.Rect.MakeXYWH(-w / 2, -h / 2, w, h)
        src = skia.Rect.MakeWH(iw, ih)
        if self.fit in ("contain", "cover"):
            s = (min if self.fit == "contain" else max)(w / iw, h / ih)
            if self.fit == "contain":
                dw, dh = iw * s, ih * s
                dst = skia.Rect.MakeXYWH(-dw / 2, -dh / 2, dw, dh)
            else:
                sw, sh = w / s, h / s
                src = skia.Rect.MakeXYWH((iw - sw) / 2, (ih - sh) / 2, sw, sh)
        r = self.radius.at(t)
        canvas.save()
        if r > 0:
            canvas.clipRRect(skia.RRect.MakeRectXY(dst, r, r), True)
        canvas.drawImageRect(self.img, src, dst, skia.SamplingOptions(skia.CubicResampler.Mitchell()),
                             skia.Paint(AntiAlias=True))
        canvas.restore()


class Svg(Layer):
    """SVG rendered through skia's SVG module, centered on the origin and scaled to w x h.
    For After Effects the exporter converts simple SVGs to shape layers (see svg_shapes)."""
    kind = "svg"

    def __init__(self, path, w, h=None, **kw):
        super().__init__(**kw)
        self.path = asset_path(path)
        stream = skia.FILEStream.Make(self.path)
        self.dom = skia.SVGDOM.MakeFromStream(stream)
        cs = self.dom.containerSize()
        self.native = (cs.width() or w, cs.height() or (h or w))
        if h is None:
            h = w * self.native[1] / self.native[0]
        self.size = P_((w, h), "size")

    def local_bounds(self, t):
        w, h = self.size.at(t)
        return (-w / 2, -h / 2, w / 2, h / 2)

    def render(self, canvas, t, ctx):
        w, h = self.size.at(t)
        nw, nh = self.native
        canvas.save()
        canvas.translate(-w / 2, -h / 2)
        canvas.scale(w / nw, h / nh)
        self.dom.setContainerSize(skia.Size(nw, nh))
        self.dom.render(canvas)
        canvas.restore()
