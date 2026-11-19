"""Core data model: animatable properties, layers, groups, scenes, camera, project.

Coordinates are in FINAL-resolution pixels (e.g. 1080x1920 for 9:16). The renderer
scales the canvas for previews and supersampling, so a composition never changes
between preview and final. All keyframe times are in SCENE time (seconds from the
scene start), like comp time in After Effects.
"""
import math
import os
import zlib

import numpy as np

from .env import load_skia
from .easing import ease as _ease, lerp

skia = load_skia()

CURRENT = {"project": None, "design": None}


# ----------------------------------------------------------------------------- colors

def _hex(s):
    s = s.lstrip("#")
    if len(s) in (3, 4):
        s = "".join(c * 2 for c in s)
    vals = [int(s[i:i + 2], 16) / 255 for i in range(0, len(s), 2)]
    if len(vals) == 3:
        vals.append(1.0)
    return tuple(vals)


def color(spec, alpha=None):
    """Color spec -> (r, g, b, a) floats 0..1.

    Accepts '#rgb', '#rrggbb', '#rrggbbaa', palette role names ('accent'),
    'role@0.5' (alpha override), (r,g,b[,a]) in 0..1 or 0..255, or None.
    """
    if spec is None:
        return None
    a_override = alpha
    if isinstance(spec, str):
        s = spec.strip()
        if "@" in s:
            s, a = s.split("@", 1)
            a_override = float(a)
        if s.startswith("#"):
            c = _hex(s)
        else:
            d = CURRENT["design"]
            if d is None or s not in d.palette:
                named = {"white": (1, 1, 1, 1), "black": (0, 0, 0, 1), "transparent": (0, 0, 0, 0)}
                if s in named:
                    c = named[s]
                else:
                    raise KeyError(f"Unknown color/palette role: {spec!r}")
            else:
                c = d.palette[s]
    else:
        v = tuple(float(x) for x in spec)
        if any(x > 1.0 for x in v[:3]):
            v = tuple(x / 255 for x in v[:3]) + (v[3] if len(v) == 4 and v[3] <= 1 else (v[3] / 255 if len(v) == 4 else 1.0),)
        c = v if len(v) == 4 else v + (1.0,)
    if a_override is not None:
        c = c[:3] + (c[3] * a_override,)
    return c


def xform(path, m):
    """Transformed copy of a skia.Path."""
    q = skia.Path(path)
    q.transform(m)
    return q


def c4f(c):
    return skia.Color4f(*c)


def skcolor(c):
    r, g, b, a = (max(0, min(255, int(round(x * 255)))) for x in c)
    return skia.Color(r, g, b, a)


def luminance(c):
    def lin(x):
        return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(x) for x in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(c1, c2):
    l1, l2 = luminance(c1), luminance(c2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


# ----------------------------------------------------------------------------- props

class Key:
    __slots__ = ("t", "v", "ease")

    def __init__(self, t, v, ease):
        self.t, self.v, self.ease = float(t), v, ease

    def __repr__(self):
        return f"Key({self.t:.3f}, {self.v}, {self.ease.spec})"


def _norm(v):
    if isinstance(v, (int, float, np.floating, np.integer)):
        return float(v)
    if isinstance(v, (list, tuple, np.ndarray)):
        return tuple(float(x) for x in v)
    return v


class Wiggle:
    """Smooth deterministic noise added on top of a property (AE: wiggle(freq, amp))."""

    def __init__(self, freq=2.0, amp=10.0, seed=0, octaves=1, dims=None):
        self.freq, self.amp, self.seed, self.octaves, self.dims = freq, amp, seed, octaves, dims

    def _n(self, t, k):
        rng = np.random.default_rng(zlib.crc32(f"wig{self.seed}:{k}".encode()))
        ph = rng.uniform(0, 2 * math.pi, 6)
        fr = rng.uniform(0.6, 1.4, 6)
        v = 0.0
        for o in range(self.octaves):
            m = 2 ** o
            v += sum(math.sin(2 * math.pi * self.freq * m * fr[i] * t + ph[i]) for i in range(3)) / (3 * m)
        return v * 1.4

    def eval(self, t, base):
        if isinstance(base, tuple):
            return tuple(b + self.amp * self._n(t, i) for i, b in enumerate(base))
        return base + self.amp * self._n(t, 0)

    def ae_expression(self):
        return f"wiggle({self.freq:g}, {self.amp:g}, {self.octaves})"


class Prop:
    """Animatable property: static rest value, keyframes, optional procedural modifiers."""

    __slots__ = ("name", "value", "keys", "fn", "mods", "ae_expr")

    def __init__(self, value, name=""):
        self.name = name
        self.value = _norm(value)
        self.keys = []
        self.fn = None        # fully procedural driver: fn(t) -> value (exported baked/expr)
        self.mods = []        # additive modifiers (Wiggle)
        self.ae_expr = None   # optional explicit AE expression for procedural drivers

    # -- authoring
    def key(self, t, v, ease=None):
        """Add a keyframe. `ease` shapes the segment ARRIVING at this key."""
        v = _norm(v)
        k = Key(t, v, _ease(ease))
        for i, ex in enumerate(self.keys):
            if abs(ex.t - k.t) < 1e-6:
                self.keys[i] = k
                return self
        self.keys.append(k)
        self.keys.sort(key=lambda x: x.t)
        return self

    def set(self, v):
        self.value = _norm(v)
        return self

    def drive(self, fn, ae_expr=None):
        """Procedural driver fn(t) -> value. AE export uses ae_expr if given, else bakes."""
        self.fn = fn
        self.ae_expr = ae_expr
        return self

    def wiggle(self, freq=2.0, amp=10.0, seed=0, octaves=1):
        self.mods.append(Wiggle(freq, amp, seed, octaves))
        return self

    # -- evaluation
    @property
    def animated(self):
        return bool(self.keys) or self.fn is not None or bool(self.mods)

    def base_at(self, t):
        if self.fn is not None:
            return _norm(self.fn(t))
        ks = self.keys
        if not ks:
            return self.value
        if t <= ks[0].t:
            return ks[0].v
        if t >= ks[-1].t:
            return ks[-1].v
        lo, hi = 0, len(ks) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if ks[mid].t <= t:
                lo = mid
            else:
                hi = mid
        a, b = ks[lo], ks[hi]
        u = (t - a.t) / (b.t - a.t)
        return lerp(a.v, b.v, b.ease(u))

    def at(self, t):
        v = self.base_at(t)
        for m in self.mods:
            v = m.eval(t, v)
        return v

    def __call__(self, t):
        return self.at(t)

    def rest(self):
        return self.value


def P_(v, name=""):
    return v if isinstance(v, Prop) else Prop(v, name)


# ----------------------------------------------------------------------------- render context

class Ctx:
    """Per-frame render context."""

    def __init__(self, project, px=1.0, frame=0, t_abs=0.0, preview=False, hidden=None):
        self.project = project
        self.design = project.design
        self.px = px                  # device pixels per design pixel
        self.frame = frame
        self.t_abs = t_abs
        self.preview = preview
        self.hidden = hidden or set()  # layer ids hidden (QA contrast sampling)
        self.matrix_stack = []
        self.screen_matrix = None
        self.cache = project._cache

    def rng(self, *keys):
        seed = zlib.crc32(repr((self.project.seed,) + keys).encode())
        return np.random.default_rng(seed)


BLEND = {
    "normal": "kSrcOver", "multiply": "kMultiply", "screen": "kScreen", "overlay": "kOverlay",
    "add": "kPlus", "darken": "kDarken", "lighten": "kLighten", "color_dodge": "kColorDodge",
    "color_burn": "kColorBurn", "soft_light": "kSoftLight", "hard_light": "kHardLight",
    "difference": "kDifference", "exclusion": "kExclusion", "hue": "kHue",
    "saturation": "kSaturation", "color": "kColor", "luminosity": "kLuminosity",
}


def blend_mode(name):
    return getattr(skia.BlendMode, BLEND[name])


# ----------------------------------------------------------------------------- layer fx (per layer)

class LayerFx:
    """Per-layer effect expressed as a skia ImageFilter (maps to a native AE effect)."""
    kind = "fx"

    def filter(self, t, ctx):
        raise NotImplementedError


class Blur(LayerFx):
    kind = "blur"

    def __init__(self, sigma=0.0):
        self.sigma = P_(sigma, "sigma")

    def filter(self, t, ctx):
        s = max(0.0, self.sigma.at(t)) * FX_SCALE
        if s < 0.05:
            return None
        return skia.ImageFilters.Blur(s, s, skia.TileMode.kDecal)


class DropShadow(LayerFx):
    kind = "drop_shadow"

    def __init__(self, dx=0, dy=12, sigma=24, color="#000000", opacity=0.35):
        self.dx, self.dy = P_(dx), P_(dy)
        self.sigma, self.opacity = P_(sigma), P_(opacity)
        self.color = color

    def filter(self, t, ctx):
        c = color(self.color)
        c = c[:3] + (c[3] * self.opacity.at(t),)
        return skia.ImageFilters.DropShadow(self.dx.at(t) * FX_SCALE, self.dy.at(t) * FX_SCALE,
                                            self.sigma.at(t) * FX_SCALE / 2, self.sigma.at(t) * FX_SCALE / 2,
                                            skcolor(c))


class SoftShadow(LayerFx):
    """Two-part shadow of a lifted object, in real output px: a tight dark contact shadow plus a
    wide faint ambient one. One hard DropShadow reads as 2015 UI; this reads as an object above
    a surface. `elev` is the height (px): animate it for lift/land moves."""
    kind = "soft_shadow"

    def __init__(self, elev=24, color="#0B1220", opacity=0.28):
        self.elev, self.opacity = P_(elev), P_(opacity)
        self.color = color

    def filter(self, t, ctx):
        e = max(0.0, self.elev.at(t))
        o = max(0.0, self.opacity.at(t))
        if e < 0.5 or o < 0.005:
            return None
        c = color(self.color)
        near = skia.ImageFilters.DropShadowOnly(0, e * 0.12, e * 0.12 + 1, e * 0.12 + 1, skcolor(c[:3] + (c[3] * o * 0.9,)))
        far = skia.ImageFilters.DropShadowOnly(0, e * 0.55, e * 0.85, e * 0.85, skcolor(c[:3] + (c[3] * o * 0.6,)))
        return skia.ImageFilters.Merge([far, near, None])


class Glow(LayerFx):
    """Soft glow behind content: blurred copy, tinted, merged under the source."""
    kind = "glow"

    def __init__(self, sigma=18, color=None, strength=0.8):
        self.sigma, self.strength = P_(sigma), P_(strength)
        self.color = color

    def filter(self, t, ctx):
        s = self.sigma.at(t) * FX_SCALE
        k = self.strength.at(t)
        if k <= 0.001:
            return None
        blur = skia.ImageFilters.Blur(s, s, skia.TileMode.kDecal)
        if self.color is not None:
            c = color(self.color)
            cf = skia.ColorFilters.Blend(skcolor(c), skia.BlendMode.kSrcIn)
            blur = skia.ImageFilters.ColorFilter(cf, blur)
        m = [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, k, 0]
        blur = skia.ImageFilters.ColorFilter(skia.ColorFilters.Matrix(m), blur)
        return skia.ImageFilters.Merge([blur, None])


class Smear(LayerFx):
    """Blur along the direction of motion, sigma = k * speed (px/s). AE: Directional Blur
    driven by transform.position.velocity."""
    kind = "smear"

    def __init__(self, layer, k=0.012, max_sigma=80.0):
        self.layer, self.k, self.max_sigma = layer, k, max_sigma

    def filter(self, t, ctx):
        p = self.layer.position
        h = 1.0 / 120
        a, b = p.at(t - h), p.at(t + h)
        vx, vy = (b[0] - a[0]) / (2 * h), (b[1] - a[1]) / (2 * h)
        sx = min(self.max_sigma, abs(vx) * self.k) * FX_SCALE
        sy = min(self.max_sigma, abs(vy) * self.k) * FX_SCALE
        if sx < 0.3 and sy < 0.3:
            return None
        return skia.ImageFilters.Blur(sx, sy, skia.TileMode.kDecal)


class Sheen:
    """Specular sweep drawn over a layer's own pixels (kSrcATop). See Layer.sheen()."""

    def __init__(self, t, dur, angle, width, strength, col, ease):
        self.t0, self.dur, self.angle, self.width = float(t), float(dur), float(angle), float(width)
        self.strength, self.col, self.ease = strength, col, ease

    def active(self, t):
        return self.t0 <= t <= self.t0 + self.dur

    def draw(self, canvas, t, layer, pic):
        if not self.active(t):
            return
        if pic is not None:
            c = pic.cullRect()
            l, tp, r, b = c.left(), c.top(), c.right(), c.bottom()
        else:
            bb = layer.local_bounds(t)
            if bb is None:
                return
            l, tp, r, b = bb
        w, h = r - l, b - tp
        if w <= 0 or h <= 0:
            return
        u = _ease(self.ease)(max(0.0, min(1.0, (t - self.t0) / max(1e-6, self.dur))))
        a = math.radians(self.angle)
        dx, dy = math.cos(a), math.sin(a)
        span = abs(w * dx) + abs(h * dy)
        cx, cy = (l + r) / 2, (tp + b) / 2
        bw = self.width * span
        pos = -span / 2 - bw + u * (span + 2 * bw)
        p0 = skia.Point(cx + dx * (pos - bw), cy + dy * (pos - bw))
        p1 = skia.Point(cx + dx * (pos + bw), cy + dy * (pos + bw))
        k = color(self.col)
        s = self.strength * math.sin(math.pi * u) ** 0.5
        cols = [skia.Color4f(k[0], k[1], k[2], 0.0), skia.Color4f(k[0], k[1], k[2], s * k[3]),
                skia.Color4f(k[0], k[1], k[2], 0.0)]
        sh = skia.GradientShader.MakeLinear([p0, p1], cols, [0.0, 0.5, 1.0])
        canvas.drawRect(skia.Rect.MakeLTRB(l, tp, r, b), skia.Paint(Shader=sh, BlendMode=skia.BlendMode.kSrcATop))


class Pulse:
    """Additive kick on a property: +amount at t, decaying over dur (ease-out)."""

    def __init__(self, t, amount, dur):
        self.t, self.amount, self.dur = float(t), amount, float(dur)

    def env(self, t):
        u = (t - self.t) / self.dur
        if u < 0 or u > 1:
            return 0.0
        a = min(1.0, u / 0.15)                   # fast attack
        return a * (1 - u) ** 2

    def eval(self, t, base):
        e = self.env(t)
        if e == 0:
            return base
        if isinstance(base, tuple):
            return tuple(b * (1 + self.amount * e) for b in base)
        return base * (1 + self.amount * e)

    def ae_expression(self):
        return (f"(function(){{var u=(time-{self.t:g})/{self.dur:g}; if(u<0||u>1) return value; "
                f"var e=Math.min(1,u/0.15)*Math.pow(1-u,2); var k=1+{self.amount:g}*e; "
                f"return (value instanceof Array) ? mul(value, k) : value*k;}})()")


# ----------------------------------------------------------------------------- layers

_ids = {"n": 0}


def _anchor_point(spec, rect):
    """Named anchor ('tl','tc','tr','cl','center','cr','bl','bc','br') -> point in rect."""
    l, t, r, b = rect
    xs = {"l": l, "c": (l + r) / 2, "r": r}
    ys = {"t": t, "c": (t + b) / 2, "b": b}
    if spec in ("center", "c", "cc", "mm"):
        return ((l + r) / 2, (t + b) / 2)
    if len(spec) == 2:
        return (xs[spec[1]], ys[spec[0]])
    raise ValueError(f"bad anchor {spec!r}")


BOUNDED_LAYERS = {"on": os.environ.get("MV_BOUNDED_LAYERS", "1") != "0"}

# Skia scales filter parameters (blur sigma, shadow offset) by the canvas matrix, which already
# holds the render scale and supersampling. Until 2026-10-09 the engine ALSO multiplied them by
# ctx.px, so a blur was 4x weaker in the half-size preview than in the final and 2x weaker in
# half-size stills: the preview lied. Now they are multiplied by this constant instead: the value ctx.px
# had in the final (1x scale, 2x supersampling), so approved finals keep their look and every
# render size shows the same picture.
FX_SCALE = 2.0


class Layer:
    """Base layer. Subclasses implement render(canvas, t, ctx) in LOCAL coordinates and
    local_bounds(t) -> (l, t, r, b) or None.

    Transform order (same as AE): translate(position) * rotate * scale * translate(-anchor).
    """
    kind = "layer"
    exportable = True      # can be rebuilt natively in After Effects
    text_role = None       # for QA: 'copy' | 'decor' (text layers only)

    def __init__(self, name=None, pos=(0, 0), anchor=(0, 0), scale=1.0, rotation=0.0,
                 opacity=1.0, depth=0.0, blend="normal", start=0.0, end=None, fx=None,
                 mask=None, mask_mode="alpha", clip=None, motion_blur=False, ae=None, rx=0.0, ry=0.0):
        _ids["n"] += 1
        self.uid = _ids["n"]
        self.name = name or f"{self.kind.title()} {self.uid}"
        self.position = P_(pos, "position")
        if not isinstance(scale, Prop) and isinstance(scale, (int, float)):
            scale = (scale, scale)
        self.scale = P_(scale, "scale")
        self.rotation = P_(rotation, "rotation")
        self.opacity = P_(opacity, "opacity")
        self.depth = P_(depth, "depth")
        self._anchor_spec = anchor if isinstance(anchor, str) else None
        self.anchor = P_((0, 0) if isinstance(anchor, str) else anchor, "anchor")
        self.blend = blend
        self.start = float(start)
        self.end = None if end is None else float(end)
        self.fx = list(fx or [])
        self.mask = mask
        self.mask_mode = mask_mode
        self.clip = None if clip is None else P_(clip, "clip")   # (x, y, w, h) local
        self.motion_blur = motion_blur
        self.ae = ae or {}        # exporter hints
        self.scene = None
        self.rx = P_(rx, "rx")      # 3D tilt around x (deg): + tips the top edge away
        self.ry = P_(ry, "ry")      # 3D turn around y (deg): + turns the right edge away
        self.echo_cfg = None        # (n, dt, decay): ghost copies trailing in time
        self.billboard = False      # True: always faces the camera (labels, light beams)

    @property
    def is3d(self):
        return self.rx.animated or self.ry.animated or self.rx.rest() != 0 or self.ry.rest() != 0 or \
            self.billboard or getattr(self, "world_pre", None) is not None

    def face_camera(self, on=True):
        """Billboard: the layer keeps facing the camera while it orbits (a label in a 3D set,
        a light beam). AE: Auto-Orient towards the camera."""
        self.billboard = bool(on)
        return self

    # ---- geometry
    def local_bounds(self, t):
        return None

    def resolve_anchor(self):
        if self._anchor_spec:
            b = self.local_bounds(0.0)
            if b is not None:
                self.anchor.set(_anchor_point(self._anchor_spec, b))

    def matrix(self, t):
        x, y = self.position.at(t)
        ax, ay = self.anchor.at(t)
        sx, sy = self.scale.at(t) if isinstance(self.scale.at(t), tuple) else (self.scale.at(t),) * 2
        m = skia.Matrix()
        m.setTranslate(x, y)
        r = self.rotation.at(t)
        if r:
            m.preRotate(r)
        if sx != 1 or sy != 1:
            m.preScale(sx, sy)
        if ax or ay:
            m.preTranslate(-ax, -ay)
        return m

    def visible(self, t):
        if t < self.start - 1e-9:
            return False
        if self.end is not None and t >= self.end - 1e-9:
            return False
        return True

    def world_bounds(self, t, ctx_matrix=None):
        """Axis-aligned bounds in scene coordinates (QA, safe-zone checks)."""
        b = self.local_bounds(t)
        if b is None:
            return None
        m = self.matrix(t)
        if ctx_matrix is not None:
            m = skia.Matrix.Concat(ctx_matrix, m)
        r = m.mapRect(skia.Rect.MakeLTRB(*b))
        return (r.left(), r.top(), r.right(), r.bottom())

    # ---- drawing
    def render(self, canvas, t, ctx):
        pass

    def _filter(self, t, ctx):
        fs = [f.filter(t, ctx) for f in self.fx]
        fs = [f for f in fs if f is not None]
        if not fs:
            return None
        out = fs[0]
        for f in fs[1:]:
            out = skia.ImageFilters.Compose(f, out)
        return out

    def _content(self, canvas, pic, t, ctx):
        canvas.drawPicture(pic) if pic is not None else self.render(canvas, t, ctx)
        for sh in getattr(self, "sheens", ()):
            sh.draw(canvas, t, self, pic)

    def draw(self, canvas, t, ctx, as_matte=False, m=None, _ghost=1.0, dof=0.0, tint=None, near_clip=None):
        """m overrides the layer's own matrix (the 3D camera passes a homography); dof is the
        depth-of-field blur (local px) the camera asks for; tint (r, g, b, k) pulls the layer's
        colour towards the scene haze by k (atmospheric perspective)."""
        step = getattr(self, "time_step", None)
        if step:
            # posterized time ("on twos"): the layer only updates every `step` seconds
            t = math.floor(t / step + 1e-6) * step
        if not self.visible(t) or self.uid in ctx.hidden:
            return
        if self.echo_cfg and not as_matte and _ghost == 1.0:
            n, dt, decay = self.echo_cfg
            mf = getattr(self, "_echo_matrix", None)
            for k in range(n, 0, -1):
                tk = t - k * dt
                if tk >= self.start:
                    mk = mf(tk) if (m is not None and mf) else None
                    self.draw(canvas, tk, ctx, False, mk if mk is not None else (None if m is None else m), decay ** k)
        op = max(0.0, min(1.0, self.opacity.at(t))) * _ghost
        if op <= 0.001:
            return
        parent = canvas.getTotalMatrix()
        canvas.save()
        canvas.concat(m if m is not None else self.matrix(t))
        if near_clip is not None:
            canvas.clipPath(near_clip, True)
        if self.clip is not None:
            x, y, w, h = self.clip.at(t)
            canvas.clipRect(skia.Rect.MakeXYWH(x, y, w, h), True)
        filt = self._filter(t, ctx)
        if dof > 0.35 and not as_matte:
            b = skia.ImageFilters.Blur(dof, dof, skia.TileMode.kDecal)
            filt = b if filt is None else skia.ImageFilters.Compose(b, filt)
        if tint is not None and tint[3] > 0.004 and not as_matte:
            cf = skia.ColorFilters.Blend(skia.Color4f(*tint).toColor(), skia.BlendMode.kSrcATop)
            tf = skia.ImageFilters.ColorFilter(cf)
            filt = tf if filt is None else skia.ImageFilters.Compose(tf, filt)
        blend = "normal" if as_matte else self.blend
        sheen_on = bool(getattr(self, "sheens", None)) and not as_matte and any(s.active(t) for s in self.sheens)
        need = op < 0.999 or blend != "normal" or self.mask is not None or filt is not None or sheen_on
        if not need:
            self.render(canvas, t, ctx)
        else:
            # Offscreen layers sized to the ink, not to the whole frame. The content is recorded
            # first (an SkPicture with an R-tree trims its cull rect to what was really drawn,
            # including strokes, shadows and nested filters), then replayed into a layer of that
            # size. At 2x supersampling a full-frame layer is 33 MB, and a blur over it costs the
            # whole frame; most layers cover a few percent of it. Same pixels, 2-4x faster frames.
            pic, ink = (None, None) if near_clip is not None else self._record(canvas, t, ctx)
            if pic is not None and ink is not None and ink.isEmpty():
                canvas.restore()
                return
            outer = skia.Paint(Alphaf=op, BlendMode=blend_mode(blend))
            ob = None if ink is None else (filt.computeFastBounds(ink) if filt is not None else ink)
            canvas.saveLayer(ob, outer)
            if filt is not None:
                canvas.saveLayer(ink, skia.Paint(ImageFilter=filt))
                self._content(canvas, pic, t, ctx)
                canvas.restore()
            else:
                self._content(canvas, pic, t, ctx)
            if self.mask is not None:
                inv = self.mask_mode.endswith("_inv")
                mp = skia.Paint(BlendMode=skia.BlendMode.kDstOut if inv else skia.BlendMode.kDstIn)
                if self.mask_mode.startswith("luma"):
                    mp.setColorFilter(skia.LumaColorFilter.Make())
                canvas.save()
                canvas.setMatrix(parent)
                canvas.saveLayer(None, mp)
                self.mask.draw(canvas, t, ctx, as_matte=True)
                canvas.restore()
                canvas.restore()
            canvas.restore()
        canvas.restore()

    def _screen_locked(self):
        """True if this layer or a descendant draws in absolute screen space (Background):
        such content cannot be recorded into a picture and replayed under another matrix."""
        v = getattr(self, "_screen_lock", None)
        if v is None:
            v = self.kind == "background" or bool(getattr(self, "screen_space", False)) or \
                any(c._screen_locked() for c in getattr(self, "children", []))
            self._screen_lock = v
        return v

    def _record(self, canvas, t, ctx):
        """-> (picture, ink rect in local coords) or (None, None) to draw unbounded."""
        if not BOUNDED_LAYERS["on"] or self._screen_locked():
            return None, None
        clip = canvas.getLocalClipBounds()
        if not clip.isFinite() or clip.isEmpty():
            return None, None
        # record a margin beyond the visible area: a blur at the frame edge (here or in a child)
        # needs the content just outside the frame, otherwise the edge fades to transparent
        p = CURRENT.get("project")
        m = 0.3 * max(p.W, p.H) if p is not None else 600.0
        rb = skia.Rect.MakeLTRB(clip.left() - m, clip.top() - m, clip.right() + m, clip.bottom() + m)
        rec = skia.PictureRecorder()
        rc = rec.beginRecording(rb, skia.RTreeFactory()())
        self.render(rc, t, ctx)
        pic = rec.finishRecordingAsPicture()
        c = pic.cullRect()
        ink = skia.Rect.MakeLTRB(c.left(), c.top(), c.right(), c.bottom())
        if ink.isEmpty():
            return pic, ink
        # two pixels of slack for antialiased edges
        k = 2.0 / max(1e-6, ctx.px)
        ink.outset(k, k)
        return pic, ink

    # ---- audio hook
    def audio_events(self):
        """Return [(scene_time, kind, params)] for automatically sounded layers."""
        return []

    # ---- animation helpers (all times in scene seconds) ----------------------
    def _motion(self):
        d = CURRENT["design"]
        return d.motion if d is not None else None

    def _dur(self, dur, kind="medium"):
        if dur is not None:
            return dur
        m = self._motion()
        return m.durations.get(kind, 0.6) if m else 0.6

    def _ez(self, e, kind="enter"):
        if e is not None:
            return e
        m = self._motion()
        return m.easing.get(kind, "out_cubic") if m else "out_cubic"

    def tween(self, prop, t, dur, frm, to, ease=None):
        p = getattr(self, prop) if isinstance(prop, str) else prop
        p.key(t, frm, "linear")
        p.key(t + dur, to, ease or self._ez(None))
        return self

    def fade_in(self, t, dur=None, ease=None):
        dur = self._dur(dur, "short")
        rest = self.opacity.rest()
        self.opacity.key(t, 0.0).key(t + dur, rest, ease or self._ez(None, "enter"))
        return self

    def fade_out(self, t, dur=None, ease=None):
        dur = self._dur(dur, "short")
        rest = self.opacity.rest()
        self.opacity.key(t, rest).key(t + dur, 0.0, ease or self._ez(None, "exit"))
        return self

    def move_from(self, t, offset, dur=None, ease=None):
        dur = self._dur(dur)
        x, y = self.position.rest()
        self.position.key(t, (x + offset[0], y + offset[1])).key(t + dur, (x, y), ease or self._ez(None, "enter"))
        return self

    def move_to(self, t, offset, dur=None, ease=None):
        """Move by `offset` from where the layer is at t (chained moves continue from the last
        one; before 2026-10-08 this started from the rest position and snapped back)."""
        dur = self._dur(dur)
        x, y = self.position.base_at(t)
        self.position.key(t, (x, y)).key(t + dur, (x + offset[0], y + offset[1]), ease or self._ez(None, "move"))
        return self

    def move(self, t, to, dur=None, ease=None, frm=None):
        """Animate to an absolute position (from current value at t, or `frm`)."""
        dur = self._dur(dur)
        a = frm if frm is not None else self.position.at(t)
        self.position.key(t, a).key(t + dur, to, ease or self._ez(None, "move"))
        return self

    _DIRS = {"up": (0, 1), "down": (0, -1), "left": (1, 0), "right": (-1, 0)}

    def slide_in(self, t, direction="up", dist=60, dur=None, ease=None, fade=True):
        """Enter moving in `direction` (content travels up = starts below)."""
        dx, dy = self._DIRS[direction]
        self.move_from(t, (dx * dist, dy * dist), dur, ease)
        if fade:
            self.fade_in(t, min(self._dur(dur), self._dur(None, "short")), "out_quad")
        return self

    def slide_out(self, t, direction="up", dist=60, dur=None, ease=None, fade=True):
        dx, dy = self._DIRS[direction]
        dur = self._dur(dur, "short")
        self.move_to(t, (-dx * dist, -dy * dist), dur, ease or self._ez(None, "exit"))
        if fade:
            self.fade_out(t, dur, "in_quad")
        return self

    def pop_in(self, t, dur=None, ease=None, frm=0.0):
        dur = self._dur(dur)
        rest = self.scale.rest()
        f = (frm * rest[0], frm * rest[1])
        self.scale.key(t, f).key(t + dur, rest, ease or self._ez(None, "emphasis"))
        self.opacity.key(t, 0.0).key(t + min(dur, 0.15), self.opacity.rest(), "out_quad")
        return self

    def pop_out(self, t, dur=None, ease=None):
        dur = self._dur(dur, "short")
        rest = self.scale.rest()
        self.scale.key(t, rest).key(t + dur, (0.0, 0.0), ease or "in_back")
        return self

    def scale_from(self, t, s0, dur=None, ease=None):
        dur = self._dur(dur)
        rest = self.scale.rest()
        s0 = (s0, s0) if isinstance(s0, (int, float)) else s0
        self.scale.key(t, (rest[0] * s0[0], rest[1] * s0[1])).key(t + dur, rest, ease or self._ez(None, "enter"))
        return self

    def scale_to(self, t, s1, dur=None, ease=None):
        dur = self._dur(dur)
        s1 = (s1, s1) if isinstance(s1, (int, float)) else s1
        self.scale.key(t, self.scale.at(t)).key(t + dur, s1, ease or self._ez(None, "move"))
        return self

    def rotate_from(self, t, deg, dur=None, ease=None):
        dur = self._dur(dur)
        rest = self.rotation.rest()
        self.rotation.key(t, rest + deg).key(t + dur, rest, ease or self._ez(None, "enter"))
        return self

    def blur_in(self, t, sigma=24, dur=None, ease=None):
        dur = self._dur(dur)
        b = Blur(0)
        b.sigma.key(t, sigma).key(t + dur, 0.0, ease or self._ez(None, "enter"))
        self.fx.append(b)
        self.fade_in(t, dur * 0.7)
        return self

    def enter(self, t, how="rise", **kw):
        """Generic entrance: rise|drop|left|right|fade|pop|blur|scale."""
        m = {"rise": lambda: self.slide_in(t, "up", **kw), "drop": lambda: self.slide_in(t, "down", **kw),
             "left": lambda: self.slide_in(t, "left", **kw), "right": lambda: self.slide_in(t, "right", **kw),
             "fade": lambda: self.fade_in(t, **kw), "pop": lambda: self.pop_in(t, **kw),
             "blur": lambda: self.blur_in(t, **kw), "scale": lambda: (self.scale_from(t, kw.pop("s0", 0.85), **kw), self.fade_in(t))}
        m[how]()
        return self

    def exit(self, t, how="fade", **kw):
        m = {"fade": lambda: self.fade_out(t, **kw), "rise": lambda: self.slide_out(t, "up", **kw),
             "drop": lambda: self.slide_out(t, "down", **kw), "left": lambda: self.slide_out(t, "left", **kw),
             "right": lambda: self.slide_out(t, "right", **kw), "pop": lambda: self.pop_out(t, **kw)}
        m[how]()
        return self

    def show(self, start=None, end=None):
        """Set visibility window (scene seconds)."""
        if start is not None:
            self.start = float(start)
        if end is not None:
            self.end = float(end)
        return self

    def add_fx(self, *fx):
        self.fx.extend(fx)
        return self

    def smear(self, k=0.012, max_sigma=80.0):
        """Directional blur proportional to the layer's speed (cheap motion streak)."""
        self.fx.append(Smear(self, k, max_sigma))
        return self

    def echo(self, n=4, dt=0.035, decay=0.55):
        """Ghost copies of the layer's own animation trailing behind (AE Echo)."""
        self.echo_cfg = (int(n), float(dt), float(decay))
        return self

    def tilt_in(self, t, rx=0.0, ry=0.0, dur=None, ease=None):
        """Swing in from a 3D tilt to flat (needs the scene camera; works with any layer)."""
        dur = self._dur(dur)
        e = ease or self._ez(None, "enter")
        if rx:
            self.rx.key(t, rx).key(t + dur, self.rx.rest(), e)
        if ry:
            self.ry.key(t, ry).key(t + dur, self.ry.rest(), e)
        return self

    def tilt_out(self, t, rx=0.0, ry=0.0, dur=None, ease=None, fade=True):
        """Swing away in 3D (reference r04 'yaw exit': the card turns ~60 deg and fades)."""
        dur = self._dur(dur)
        e = ease or self._ez(None, "exit")
        if rx:
            self.rx.key(t, self.rx.base_at(t)).key(t + dur, rx, e)
        if ry:
            self.ry.key(t, self.ry.base_at(t)).key(t + dur, ry, e)
        if fade:
            self.fade_out(t + dur * 0.35, dur * 0.65)
        return self

    def sheen(self, t, dur=0.9, angle=20.0, width=0.28, strength=0.55, color_="#FFFFFF", ease="in_out_cubic"):
        """A band of light sweeps across the layer (only over its own pixels): the specular
        glint that makes a card, a logo or a hero word read as a material, not a flat fill.
        One per object, on its key moment; not on every element."""
        if not hasattr(self, "sheens"):
            self.sheens = []
        self.sheens.append(Sheen(t, dur, angle, width, strength, color_, ease))
        return self

    def on_twos(self, fps=12):
        """Posterize this layer's time (AE: Posterize Time): it moves at `fps` while the rest
        of the film runs at full rate. A hand-made, stop-motion accent for one callout or a
        sticker; on everything it reads as lag."""
        self.time_step = 1.0 / float(fps)
        return self

    def punch(self, t, amount=0.08, dur=0.25):
        """Scale kick on a beat: grows by `amount` and settles back."""
        self.scale.mods.append(Pulse(t, amount, dur))
        return self

    def matte(self, layer, mode="alpha"):
        """Use `layer` (scene coords, not drawn itself) as track matte."""
        self.mask = layer
        self.mask_mode = mode
        return self

    def allow(self, *what, why=""):
        """Declare an intentional exception that QA accepts and lists in its report:
        'static'   the element enters and then sits on purpose (a label, an axis, an end card);
        'offframe' copy text may cross the frame edge (a giant word cropped by design);
        'overlap'  copy deliberately sits on or under other layers (overprint, text under stripes):
                   occlusion and contrast are not checked for it;
        'oblique'  a flat layer is held at an angle to the camera on purpose (a floor-like sheet,
                   a quick 3D flip that the brief asks for).
        `why` is required: one line on why the exception serves the design."""
        bad = set(what) - {"static", "offframe", "overlap", "oblique"}
        if bad:
            raise ValueError(f"allow(): unknown exception(s) {sorted(bad)}")
        if not why:
            raise ValueError("allow() needs why=...: say why the exception is intentional")
        self.allowed = set(getattr(self, "allowed", set())) | set(what)
        self.allow_why = why
        return self


class Group(Layer):
    """Container. Children use group-local coordinates. `offset` shifts children's time
    (precomp start). Maps to a precomp in After Effects."""
    kind = "group"

    def __init__(self, *children, offset=0.0, **kw):
        super().__init__(**kw)
        self.children = []
        self.offset = float(offset)
        for c in children:
            self.add(c)

    def add(self, *layers):
        for l in layers:
            l.scene = self.scene
            if l._anchor_spec:
                l.resolve_anchor()
            self.children.append(l)
        return layers[0] if len(layers) == 1 else layers

    def local_bounds(self, t):
        bs = []
        for c in self.children:
            if c.visible(t - self.offset):
                b = c.world_bounds(t - self.offset)
                if b:
                    bs.append(b)
        if not bs:
            return None
        return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))

    def render(self, canvas, t, ctx):
        lt = t - self.offset
        for c in self.children:
            c.draw(canvas, lt, ctx)

    def walk(self):
        for c in self.children:
            yield c
            if isinstance(c, Group):
                yield from c.walk()

    def audio_events(self):
        ev = []
        for c in self.children:
            ev += [(t + self.offset, k, p) for t, k, p in c.audio_events()]
        return ev


class Null(Layer):
    """Invisible transform holder (parent for groups of layers via Group)."""
    kind = "null"


# ----------------------------------------------------------------------------- camera

def _rx(d):
    a = math.radians(d)
    c, s_ = math.cos(a), math.sin(a)
    # + tips the top edge away from the viewer (y down, z into the screen)
    return np.array([[1, 0, 0, 0], [0, c, s_, 0], [0, -s_, c, 0], [0, 0, 0, 1]], float)


def _ry(d):
    a = math.radians(d)
    c, s_ = math.cos(a), math.sin(a)
    # + turns the right edge away
    return np.array([[c, 0, -s_, 0], [0, 1, 0, 0], [s_, 0, c, 0], [0, 0, 0, 1]], float)


def _rz(d):
    a = math.radians(d)
    c, s_ = math.cos(a), math.sin(a)
    return np.array([[c, -s_, 0, 0], [s_, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], float)


def _tr(x, y, z):
    m = np.eye(4)
    m[:3, 3] = (x, y, z)
    return m


def _sc(x, y, z=1.0):
    return np.diag([x, y, z, 1.0])


def layer_model(layer, t, rx=None, ry=None):
    """4x4 model matrix of a layer: T(x, y, depth) Rz Ry Rx S T(-anchor), AE order.
    `rx`/`ry` given: a billboard facing the camera, T Ry Rx Rz S T(-anchor), so its own roll
    stays a roll in the picture plane. A layer may carry `world_pre` (4x4 or fn(t) -> 4x4)
    applied in world space after its own transform: a reflection is its source mirrored about
    the floor plane."""
    x, y = layer.position.at(t)
    ax, ay = layer.anchor.at(t)
    sc = layer.scale.at(t)
    sx, sy = sc if isinstance(sc, tuple) else (sc, sc)
    if rx is None and ry is None:
        M = (_tr(x, y, layer.depth.at(t)) @ _rz(layer.rotation.at(t)) @ _ry(layer.ry.at(t)) @
             _rx(layer.rx.at(t)) @ _sc(sx, sy) @ _tr(-ax, -ay, 0))
    else:
        M = (_tr(x, y, layer.depth.at(t)) @ _ry(layer.ry.at(t) if ry is None else ry) @
             _rx(layer.rx.at(t) if rx is None else rx) @ _rz(layer.rotation.at(t)) @
             _sc(sx, sy) @ _tr(-ax, -ay, 0))
    wp = getattr(layer, "world_pre", None)
    if wp is not None:
        M = (wp(t) if callable(wp) else wp) @ M
    return M


class Camera:
    """Perspective camera. A layer at depth d (px, + is farther) with no tilt scales by
    focal / (focal/zoom + d), the projection of an AE one-node camera with zoom = focal at
    distance focal/zoom. `rx`/`ry` orbit the camera around its target (pos, z=0); layers
    with rx/ry are drawn as true perspective planes (3x3 homographies)."""

    def __init__(self, W, H, focal=None):
        self.W, self.H = W, H
        self.focal = focal or 1.6 * max(W, H)
        self.pos = Prop((W / 2, H / 2), "camera.position")
        self.zoom = Prop(1.0, "camera.zoom")
        self.rotation = Prop(0.0, "camera.rotation")
        self.rx = Prop(0.0, "camera.rx")
        self.ry = Prop(0.0, "camera.ry")
        # lens: focal-length multiplier at a fixed camera distance (zoom moves the camera, lens
        # changes the lens). Animate both against each other for a dolly zoom.
        self.lens = Prop(1.0, "camera.lens")
        # depth of field: layers whose depth differs from `focus` get blurred by
        # aperture px per 1000 px of defocus (screen px at the final size). 0 = everything sharp.
        self.focus = Prop(0.0, "camera.focus")
        self.aperture = Prop(0.0, "camera.aperture")
        self.cuts = []            # scene times of hard cuts between camera setups (cut()/shot())
        self._tilt_blur = False   # orbit()/crane() moves also drive the automatic motion blur

    @property
    def active(self):
        ps = (self.pos, self.zoom, self.rotation, self.rx, self.ry, self.lens)
        return any(p.animated for p in ps) or self.pos.rest() != (self.W / 2, self.H / 2) or \
            self.zoom.rest() != 1.0 or self.rotation.rest() != 0.0 or self.rx.rest() != 0 or \
            self.ry.rest() != 0 or self.lens.rest() != 1.0

    def _view(self, t):
        z = max(0.01, self.zoom.at(t))
        D = self.focal / z
        cx, cy = self.pos.at(t)
        return _tr(0, 0, D) @ _rz(-self.rotation.at(t)) @ _rx(-self.rx.at(t)) @ _ry(-self.ry.at(t)) @ _tr(-cx, -cy, 0)

    def view_proj(self, t):
        """3x4 world -> homogeneous screen."""
        f = self.focal * max(0.01, self.lens.at(t))
        P = np.array([[f, 0, self.W / 2, 0], [0, f, self.H / 2, 0], [0, 0, 1, 0]], float)
        return P @ self._view(t)

    def scale_at(self, t, depth=0.0):
        """On-screen scale of an untilted plane at `depth` (1.0 = drawn at its own size)."""
        D = self.focal / max(0.01, self.zoom.at(t))
        return self.focal * max(0.01, self.lens.at(t)) / max(1.0, D + depth)

    def homography(self, t, layer, lt=None):
        """skia.Matrix mapping the layer's local plane to the screen, or None if the layer
        is behind the camera. Billboards (layer.billboard) turn to face the camera."""
        H = self._homo(t, layer, lt)
        b = layer.local_bounds(t if lt is None else lt)
        if b is not None:
            for x, y in ((b[0], b[1]), (b[2], b[1]), (b[0], b[3]), (b[2], b[3])):
                if H[2, 0] * x + H[2, 1] * y + H[2, 2] <= 1e-3:
                    return None
        return self._skm(H)

    def _homo(self, t, layer, lt=None):
        tt = t if lt is None else lt
        bb = getattr(layer, "billboard", False)
        if bb == "y":
            M = self.view_proj(t) @ layer_model(layer, tt, ry=self.ry.at(t))
        elif bb:
            M = self.view_proj(t) @ layer_model(layer, tt, rx=self.rx.at(t), ry=self.ry.at(t))
        else:
            M = self.view_proj(t) @ layer_model(layer, tt)
        return M[:, [0, 1, 3]]

    @staticmethod
    def _skm(H, k=None):
        if k is None:
            k = H[2, 2] if abs(H[2, 2]) > 1e-12 else 1.0
        H = H / k
        m = skia.Matrix()
        m.setAll(H[0, 0], H[0, 1], H[0, 2], H[1, 0], H[1, 1], H[1, 2], H[2, 0], H[2, 1], H[2, 2])
        return m

    def homography_clip(self, t, layer):
        """Like homography(), but a layer that is only partly behind the camera (a floor under
        a dolly, a card the camera flies through) is kept: -> (matrix, clip path in local
        coords or None). (None, None) when it is entirely behind the near plane."""
        H = self._homo(t, layer)
        b = layer.local_bounds(t)
        if b is None:
            return self._skm(H), None
        near = 0.02 * self.focal
        corners = ((b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3]))
        ws = [H[2, 0] * x + H[2, 1] * y + H[2, 2] for x, y in corners]
        if min(ws) > 1e-3:
            return self._skm(H), None
        if max(ws) <= near:
            return None, None
        # the part of the plane in front of the near plane: a big box around the bounds (glows
        # and shadows reach past them) cut by the line w = near
        w_, h_ = b[2] - b[0], b[3] - b[1]
        m = 2.0 * max(w_, h_, 1.0)
        box = [(b[0] - m, b[1] - m), (b[2] + m, b[1] - m), (b[2] + m, b[3] + m), (b[0] - m, b[3] + m)]
        wf = lambda p: H[2, 0] * p[0] + H[2, 1] * p[1] + H[2, 2]
        poly = []
        for i in range(4):
            a, c = box[i], box[(i + 1) % 4]
            wa, wc = wf(a) - near, wf(c) - near
            if wa >= 0:
                poly.append(a)
            if (wa >= 0) != (wc >= 0):
                u = wa / (wa - wc)
                poly.append((a[0] + (c[0] - a[0]) * u, a[1] + (c[1] - a[1]) * u))
        if len(poly) < 3:
            return None, None
        path = skia.Path()
        path.moveTo(*poly[0])
        for p in poly[1:]:
            path.lineTo(*p)
        path.close()
        # normalise by a positive w so visible points keep w > 0
        k = H[2, 2] if H[2, 2] > 1e-6 else max(ws)
        return self._skm(H, k), path

    def view_depth(self, t, layer):
        """Distance along the view axis of the layer's anchor (draw order, far first)."""
        x, y = layer.position.at(t)
        p = self._view(t) @ np.array([x, y, layer.depth.at(t), 1.0])
        return p[2]

    def project(self, t, x, y, z=0.0):
        """World point -> (screen x, screen y, view distance), or None behind the camera."""
        p = self.view_proj(t) @ np.array([x, y, z, 1.0])
        if p[2] <= 1e-3:
            return None
        return p[0] / p[2], p[1] / p[2], p[2]

    def matrix(self, t, depth=0.0):
        """2.5D camera matrix for an untilted plane at `depth` (kept for QA helpers)."""
        z = max(0.01, self.zoom.at(t))
        lens = max(0.01, self.lens.at(t))
        f = self.focal * lens / (self.focal / z + depth) if (self.focal / z + depth) > 1 else 1000.0
        cx, cy = self.pos.at(t)
        m = skia.Matrix()
        m.setTranslate(self.W / 2, self.H / 2)
        r = self.rotation.at(t)
        if r:
            m.preRotate(-r)
        m.preScale(f, f)
        m.preTranslate(-cx, -cy)
        return m

    def shake(self, t0, t1, amp=8, freq=9, seed=3):
        """Camera shake between t0 and t1 (scene seconds), eased in/out."""
        self.pos.mods.append(_WindowWiggle(t0, t1, freq, amp, seed))
        return self

    def drift(self, amp=(24, 14), zoom=0.04, period=24.0, tilt=0.0, seed=5):
        """Very slow float: one low-frequency sine per axis (period >= 16 s), so inside a scene
        the camera keeps moving one way instead of wobbling. Prefer glide()/travel(): they read
        as a camera operator, a float reads as 'alive'. Never use a short period: anything that
        turns around in under ~8 s reads as shake (user feedback 2026-10-08)."""
        period = max(16.0, float(period))
        self.pos.mods.append(_Drift(amp, period, seed))
        if zoom:
            self.zoom.mods.append(_Drift((zoom, 0), period * 1.3, seed + 1))
        if tilt:
            self.rx.mods.append(_Drift((tilt, 0), period * 1.1, seed + 2))
            self.ry.mods.append(_Drift((tilt, 0), period * 0.9, seed + 3))
        return self

    def dof(self, aperture=14.0, focus=0.0):
        """Turn on depth of field: blur = aperture px per 1000 px of |depth - focus|. Layers on
        the focus plane stay sharp; copy must sit on it while it is read."""
        self.aperture.set(aperture)
        self.focus.set(focus)
        return self

    def rack_focus(self, t, depth, dur=0.6, ease="in_out_cubic"):
        """Pull focus to another depth (the eye follows what turns sharp)."""
        self.focus.key(t, self.focus.at(t)).key(t + dur, depth, ease)
        return self

    def dof_px(self, t, depth):
        """Blur (screen px) for a layer at `depth` at time t."""
        a = self.aperture.at(t)
        if a <= 0:
            return 0.0
        return a * abs(depth - self.focus.at(t)) / 1000.0

    def push(self, t0, t1, zoom=1.12, ease="in_out_sine"):
        """Slow dolly-in over a span (scene seconds); zoom is a multiplier."""
        z0 = self.zoom.base_at(t0)
        self.zoom.key(t0, z0).key(t1, z0 * zoom, ease)
        return self

    def glide(self, t0, t1, dx=0.0, dy=0.0, zoom=1.0, rotate=0.0, ease="in_out_sine"):
        """One-way camera move over a span: pan by (dx, dy) px, zoom multiplier, roll in deg.
        The default way to keep a held shot alive (references r02/r03: 1.00 -> 1.06 push over
        the shot, never back and forth)."""
        x, y = self.pos.base_at(t0)
        self.pos.key(t0, (x, y)).key(t1, (x + dx, y + dy), ease)
        if zoom != 1.0:
            z0 = self.zoom.base_at(t0)
            self.zoom.key(t0, z0).key(t1, z0 * zoom, ease)
        if rotate:
            r0 = self.rotation.base_at(t0)
            self.rotation.key(t0, r0).key(t1, r0 + rotate, ease)
        return self

    def travel(self, t, to, zoom=None, dur=0.45, ease="in_out_expo", rotate=None):
        """Fly to another place on a big canvas (reference r03 'infinite canvas', r04 line
        travel): eased move to absolute scene position `to`, optional zoom/roll. Fast travels
        get real motion blur automatically (render.auto_blur)."""
        x, y = self.pos.base_at(t)
        self.pos.key(t, (x, y)).key(t + dur, tuple(to), ease)
        if zoom is not None:
            z0 = self.zoom.base_at(t)
            self.zoom.key(t, z0).key(t + dur, zoom, ease)
        if rotate is not None:
            r0 = self.rotation.base_at(t)
            self.rotation.key(t, r0).key(t + dur, rotate, ease)
        return self

    def follow(self, target, t0, t1, lag=0.18, offset=(0.0, 0.0), axes="xy", step=1 / 15):
        """Camera follows a moving point with a smooth lag (critically damped): a layer
        (its position) or a function t -> (x, y) in scene coordinates. Baked to keys every
        `step` s so After Effects gets the same path. Used for: caret-following typewriter,
        a travelling dot, a line being drawn."""
        f = target if callable(target) else (lambda tt, _l=target: _l.position.at(tt))
        x0, y0 = self.pos.base_at(t0)
        cx, cy = x0, y0
        vx = vy = 0.0
        w = 2.0 / max(lag, 1e-3)
        t = t0
        keys = [(t0, (cx, cy))]
        sub = step / 4
        while t < t1 - 1e-9:
            for _ in range(4):
                tx, ty = f(t)
                tx, ty = tx + offset[0], ty + offset[1]
                if "x" not in axes:
                    tx = x0
                if "y" not in axes:
                    ty = y0
                # critically damped spring towards the target
                ax = w * w * (tx - cx) - 2 * w * vx
                ay = w * w * (ty - cy) - 2 * w * vy
                vx += ax * sub
                vy += ay * sub
                cx += vx * sub
                cy += vy * sub
                t += sub
            keys.append((min(t, t1), (cx, cy)))
        self.pos.key(*keys[0])
        for tk, v in keys[1:]:
            self.pos.key(tk, v, "linear")
        return self

    def frame_on(self, t, box, margin=0.12, dur=0.6, ease="in_out_cubic", max_zoom=3.0, region=None):
        """Re-frame so the scene-space box (x0, y0, x1, y1) fills the frame with a margin
        (reference r03: the group re-centres as each badge arrives). `region` (screen x0, y0,
        x1, y1) lands the box inside part of the frame instead, e.g. `D.safe(strict=True)` to
        keep it clear of the platform UI."""
        x0, y0, x1, y1 = box
        bw, bh = max(1.0, x1 - x0), max(1.0, y1 - y0)
        if region is None:
            region = (self.W * margin, self.H * margin, self.W * (1 - margin), self.H * (1 - margin))
        rx0, ry0, rx1, ry1 = region
        lens = max(0.01, self.lens.base_at(t + dur))
        k = min((rx1 - rx0) / bw, (ry1 - ry0) / bh, max_zoom)     # on-screen scale of the stage plane
        cx = (x0 + x1) / 2 - ((rx0 + rx1) / 2 - self.W / 2) / k
        cy = (y0 + y1) / 2 - ((ry0 + ry1) / 2 - self.H / 2) / k
        return self.travel(t, (cx, cy), zoom=k / lens, dur=dur, ease=ease)

    def speed_px(self, t, dt):
        """Screen-space displacement (px at project size) of the frame centre and edges between
        t - dt/2 and t + dt/2: drives automatic camera motion blur."""
        a, b = t - dt / 2, t + dt / 2
        if any(a - 1e-6 <= c <= b + 1e-6 for c in self.cuts):
            return 0.0                    # a cut is not a move: never blend two setups
        (xa, ya), (xb, yb) = self.pos.at(a), self.pos.at(b)
        za, zb = self.zoom.at(a), self.zoom.at(b)
        ra, rb = self.rotation.at(a), self.rotation.at(b)
        la, lb = self.lens.at(a), self.lens.at(b)
        pan = math.hypot(xb - xa, yb - ya) * (za * la + zb * lb) / 2
        half_diag = math.hypot(self.W, self.H) / 2
        zoomd = abs(zb * lb - za * la) / max(1e-3, (za * la + zb * lb) / 2) * half_diag
        rot = abs(math.radians(rb - ra)) * half_diag
        # an orbit or a crane tilt sweeps the frame like a pan of the same angle. Only for moves
        # made with orbit()/crane(): older films keyed rx/ry by hand and render as they did
        orb = 0.0
        if self._tilt_blur:
            orb = (abs(math.radians(self.rx.base_at(b) - self.rx.base_at(a))) +
                   abs(math.radians(self.ry.base_at(b) - self.ry.base_at(a)))) * self.focal * (la + lb) / 2
        return pan + zoomd + rot + orb

    # ---- cinematography: setups, cuts and 3D moves (motion.md section 2b) -------------
    SIZES = {"extreme_wide": 0.22, "wide": 0.4, "full": 0.72, "medium": 1.15, "close": 1.9, "extreme_close": 3.4}
    # 2.5D: the camera stays within ~15 degrees of head-on. Beyond that the layers show they
    # are flat (the PowerPoint 3D look); QA `oblique` fails it.
    ANGLES = {"eye": 0.0, "high": 10.0, "low": -8.0}
    SIDES = {"front": 0.0, "slight": 8.0}
    MAX_TILT = 15.0
    MIN_DIST = 0.85          # shot(): the camera stays at least this x focal away; closer = lens

    def _set(self, prop, t, v, dur=0.0, ease="in_out_cubic"):
        """Animate `prop` to v: eased over `dur`, or a hard cut at t when dur <= 0.
        A cut is a 1 ms step between two keys (t - 1 ms holds the old value, t has the new one),
        so a move keyed later from t (dolly, orbit, glide) cannot turn it into a slow drift. A
        cut inside a running move ends that move. Write the camera in time order."""
        cur = prop.base_at(t)
        if dur and dur > 0:
            prop.key(t, cur).key(t + dur, v, ease)
            return
        if t <= 1e-6:
            prop.key(0.0, v)
            return
        ks = prop.keys
        before = [k for k in ks if k.t < t - 1e-6]
        after = [k for k in ks if k.t > t + 1e-6]
        if before and after and _differs_v(before[-1].v, after[0].v):
            ks.remove(after[0])                     # the move running through the cut ends at the cut
            after = after[1:]
        if after:
            import sys
            print(f"[camera] cut at {t:.2f}s: {prop.name} has keys after it that were written before the cut; "
                  "write the camera in time order", file=sys.stderr)
        for k in [k for k in ks if abs(k.t - t) < 1e-6]:
            ks.remove(k)
        prop.key(t - 1e-3, cur, "linear")
        prop.key(t, v, "hold")

    def cut(self, t, pos=None, zoom=None, rx=None, ry=None, rotation=None, lens=None, dur=0.0, ease="in_out_cubic"):
        """Change the camera setup at t: a hard cut (dur=0, the edit lands on a beat) or an eased
        move of every given value over `dur`. Absolute values: pos (x, y) on the stage plane,
        zoom (distance), rx (+ = high angle, camera above looking down), ry (+ = camera swings to
        the subject's right), rotation (roll, dutch angle), lens."""
        for prop, v in ((self.pos, pos), (self.zoom, zoom), (self.rx, rx), (self.ry, ry),
                        (self.rotation, rotation), (self.lens, lens)):
            if v is not None:
                self._set(prop, t, v, dur, ease)
        if (not dur or dur <= 0) and t > 1e-6 and not any(abs(c - t) < 1e-6 for c in self.cuts):
            self.cuts.append(float(t))
            self.cuts.sort()
        return self

    def shot(self, t, subject, size="medium", angle="eye", side=0.0, roll=0.0, dur=0.0, ease="in_out_cubic",
             offset=(0.0, 0.0), lens=None):
        """Frame a subject the way a camera operator names it. `subject`: a box (x0, y0, x1, y1)
        on the stage plane or a top-level layer (its depth is taken into account). `size`:
        extreme_wide | wide | full | medium | close | extreme_close (how much of the frame the
        subject fills; close crops it) or a number. `angle`: eye | high | low or degrees;
        `side`: front | slight ("-slight" for the other side) or degrees. Angles stay within
        15 degrees: this is a 2.5D engine. `roll`: dutch angle in degrees. `lens` resets or sets
        the lens (after a dolly_zoom it stays changed otherwise); without it a close-up that would
        bring the camera nearer than MIN_DIST x focal is made with a longer lens instead, so type
        is never bent by a near camera. dur=0 cuts."""
        d = 0.0
        if isinstance(subject, Layer):
            b = subject.world_bounds(t)
            if b is None:
                raise ValueError(f"shot(): '{subject.name}' has no bounds")
            d = subject.depth.at(t)
        else:
            b = subject
        x0, y0, x1, y1 = b
        bw, bh = max(1.0, x1 - x0), max(1.0, y1 - y0)
        frac = self.SIZES.get(size, size) if isinstance(size, str) else float(size)
        k = float(frac) / max(bw / self.W, bh / self.H)          # wanted on-screen scale at depth d
        if lens is not None:
            ln = float(lens)
            D = max(60.0, self.focal * max(0.01, ln) / k - d)
        else:
            # a close-up comes through the lens, not by putting the camera next to the subject:
            # a near camera bends type and cards (converging verticals,
            # letters that lean). The camera keeps at least MIN_DIST x focal from the subject.
            ln = self.lens.base_at(t + (dur or 0))
            D = self.focal * max(0.01, ln) / k - d
            if D + d < self.MIN_DIST * self.focal:
                D = self.MIN_DIST * self.focal - d
                ln = k * (D + d) / self.focal
                lens = ln
        z = self.focal / max(60.0, D)
        rx = self.ANGLES.get(angle, angle) if isinstance(angle, str) else float(angle)
        if isinstance(side, str):
            sgn = -1.0 if side.startswith("-") else 1.0
            ry = sgn * self.SIDES[side.lstrip("-")]
        else:
            ry = float(side)
        if max(abs(rx), abs(ry)) > self.MAX_TILT:
            import sys
            print(f"[camera] shot at {t:.2f}s: angle {rx:g}/{ry:g} deg is past {self.MAX_TILT:g}: flat layers "
                  "will read as paper (QA oblique)", file=sys.stderr)
        cx, cy = (x0 + x1) / 2 + offset[0], (y0 + y1) / 2 + offset[1]
        return self.cut(t, pos=(cx, cy), zoom=z, rx=float(rx), ry=ry, rotation=float(roll),
                        lens=(ln if lens is not None else None), dur=dur, ease=ease)

    def dolly(self, t0, t1, dz, ease="in_out_sine"):
        """Move the camera forward by dz px (negative = pull back). Unlike a zoom, near layers
        grow faster than far ones: real parallax."""
        D0 = self.focal / max(0.01, self.zoom.base_at(t0))
        D1 = max(60.0, D0 - dz)
        self.zoom.key(t0, self.focal / D0).key(t1, self.focal / D1, ease)
        return self

    def orbit(self, t0, t1, ry=0.0, rx=0.0, ease="in_out_sine"):
        """A small arc around the target on the stage plane: ry degrees around the vertical axis,
        rx over the top. Up to ~12 degrees it reveals parallax between the planes; further round,
        flat layers show they are paper (QA `oblique`)."""
        self._tilt_blur = True
        if ry:
            r0 = self.ry.base_at(t0)
            self.ry.key(t0, r0).key(t1, r0 + ry, ease)
        if rx:
            r0 = self.rx.base_at(t0)
            self.rx.key(t0, r0).key(t1, r0 + rx, ease)
        return self

    def crane(self, t0, t1, dy, tilt=0.0, ease="in_out_sine"):
        """Rise (dy < 0) or descend (dy > 0) while tilting by `tilt` degrees (+ = looks further
        down): a reveal from above or a drop to a low hero angle. Keep the end angle within
        15 degrees of head-on."""
        self._tilt_blur = True
        x, y = self.pos.base_at(t0)
        self.pos.key(t0, (x, y)).key(t1, (x, y + dy), ease)
        if tilt:
            r0 = self.rx.base_at(t0)
            self.rx.key(t0, r0).key(t1, r0 + tilt, ease)
        return self

    def dolly_zoom(self, t0, t1, k=1.6, ease="in_out_sine"):
        """Vertigo: the camera moves back by k while the lens zooms in by k (or the reverse,
        k < 1). The stage plane keeps its size, the world behind it stretches or collapses. Never
        on type or cards in close-up: the near end of the move bends them (QA keystone)."""
        z0, l0 = self.zoom.base_at(t0), self.lens.base_at(t0)
        self.zoom.key(t0, z0).key(t1, z0 / k, ease)
        self.lens.key(t0, l0).key(t1, l0 * k, ease)
        return self

    def snap(self, t, dx=0.0, dy=0.0, zoom=None, dur=0.18, ease="out_expo"):
        """Quick reframe on a beat (reads as a cut inside the shot): the camera jumps by
        (dx, dy) px and/or to `zoom` and stays there."""
        x, y = self.pos.base_at(t)
        self.pos.key(t, (x, y), "linear").key(t + dur, (x + dx, y + dy), ease)
        if zoom is not None:
            z = self.zoom.base_at(t)
            self.zoom.key(t, z, "linear").key(t + dur, zoom, ease)
        return self

    def punch(self, t, amount=0.06, dur=0.3):
        """Zoom kick on a beat."""
        self.zoom.mods.append(Pulse(t, amount, dur))
        return self


class _Drift:
    def __init__(self, amp, period, seed):
        self.amp = amp if isinstance(amp, (tuple, list)) else (amp, amp)
        self.period, self.seed = period, seed
        rng = np.random.default_rng(seed)
        self.ph = rng.uniform(0, 2 * math.pi, 4)

    # one pure sine per axis: no higher harmonic, so the camera never turns around quickly
    def eval(self, t, base):
        w = 2 * math.pi / self.period
        dx = self.amp[0] * math.sin(w * t + self.ph[0])
        if isinstance(base, tuple):
            dy = self.amp[1] * math.sin(0.83 * w * t + self.ph[2])
            return (base[0] + dx, base[1] + dy) + tuple(base[2:])
        return base + dx

    def ae_component(self, i):
        """Expression for one separated dimension (AE camera X/Y position)."""
        w = 2 * math.pi / self.period
        p = self.ph
        if i == 0:
            return f"value + {self.amp[0]:g}*Math.sin({w:.5f}*time+{p[0]:.4f})"
        return f"value + {self.amp[1]:g}*Math.sin(0.83*{w:.5f}*time+{p[2]:.4f})"

    def ae_expression(self):
        w = 2 * math.pi / self.period
        a0, a1 = self.amp
        p = self.ph
        return (f"(function(){{var w={w:.5f}; var dx={a0:g}*Math.sin(w*time+{p[0]:.4f});"
                f" var dy={a1:g}*Math.sin(0.83*w*time+{p[2]:.4f});"
                f" return (value instanceof Array) ? add(value, [dx, dy]) : value + dx;}})()")


class _WindowWiggle(Wiggle):
    def __init__(self, t0, t1, freq, amp, seed):
        super().__init__(freq, amp, seed)
        self.t0, self.t1 = t0, t1

    def eval(self, t, base):
        if not (self.t0 <= t <= self.t1):
            return base
        env = math.sin(math.pi * (t - self.t0) / (self.t1 - self.t0))
        if isinstance(base, tuple):
            return tuple(b + self.amp * env * self._n(t, i) for i, b in enumerate(base))
        return base + self.amp * env * self._n(t, 0)

    def ae_expression(self):
        return (f"(time>={self.t0:g} && time<={self.t1:g}) ? wiggle({self.freq:g}, "
                f"{self.amp:g}*Math.sin(Math.PI*(time-{self.t0:g})/{self.t1 - self.t0:g})) : value")


def _differs_v(a, b):
    if isinstance(a, tuple) and isinstance(b, tuple):
        return any(abs(x - y) > 1e-6 for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) > 1e-6
    return a != b


# ----------------------------------------------------------------------------- scene

def _draw_tier(l, lead_bg=()):
    """3D draw order: the backgrounds added before everything else, then grounds (floors), then
    everything else far to near, then on_top layers (flashes, full-frame hits)."""
    if getattr(l, "on_top", False):
        return 3
    if l.uid in lead_bg:
        return 0
    if getattr(l, "ground", False):
        return 1
    return 2


def _lead_backgrounds(children):
    out = set()
    for c in children:
        if c.kind != "background":
            break
        out.add(c.uid)
    return out


class Scene(Group):
    kind = "scene"

    def __init__(self, project, name, start, dur, transition=None, bg="bg", energy=0.5, notes=""):
        super().__init__(name=name)
        self.project = project
        self.scene = self
        self.start = 0.0
        self.t0 = float(start)       # absolute start (project seconds)
        self.dur = float(dur)
        self.transition = transition
        self.bg = bg
        self.energy = energy
        self.notes = notes
        self.camera = Camera(project.W, project.H)
        self.motion_blur = None      # {'samples': 8, 'shutter': 180} to enable for this scene
        self.haze_cfg = None         # atmospheric perspective (haze())

    @property
    def t1(self):
        return self.t0 + self.dur

    def add(self, *layers):
        for l in layers:
            l.scene = self
            if l._anchor_spec:
                l.resolve_anchor()
            if isinstance(l, Group):
                for c in l.walk():
                    c.scene = self
            before = getattr(l, "insert_before", None)
            if before is not None and before in self.children:
                # proxies (extrusion slices, reflections) go under their source: same draw order
                # at equal depth, and QA reads them as drawn below it
                self.children.insert(self.children.index(before), l)
            else:
                self.children.append(l)
        return layers[0] if len(layers) == 1 else layers

    def haze(self, color_="bg", near=400.0, far=4000.0, amount=0.85):
        """Atmospheric perspective: layers deeper than `near` (px of depth) fade towards
        `color_` (default the background), reaching `amount` at `far`. The cheapest depth cue
        there is: far things are paler and closer to the air colour."""
        self.haze_cfg = (color(color_), float(near), float(far), float(amount))
        return self

    def _haze_tint(self, depth):
        if self.haze_cfg is None:
            return None
        c, near, far, amount = self.haze_cfg
        u = max(0.0, min(1.0, (depth - near) / max(1.0, far - near)))
        k = amount * u * u * (3 - 2 * u)
        return None if k <= 0.004 else (c[0], c[1], c[2], k)

    def sfx(self, t, kind, **params):
        self.project.sfx(self.t0 + t, kind, **params)
        return self

    def beat(self, n):
        """Scene-local time of the project's beat n."""
        return self.project.beat(n) - self.t0

    def uses_3d(self):
        return self.camera.active or any(c.depth.rest() != 0 or c.depth.animated or c.is3d for c in self.children)

    def draw_scene(self, canvas, t, ctx):
        if self.bg is not None:
            bgc = self.bg
            if isinstance(bgc, Layer):
                bgc.draw(canvas, t, ctx)
            else:
                # a rect in scene space (not drawColor) so transitions can move/clip it
                canvas.drawRect(skia.Rect.MakeWH(self.project.W, self.project.H),
                                skia.Paint(Color4f=c4f(color(bgc))))
        cam = self.camera
        ctx.screen_matrix = canvas.getTotalMatrix()      # full-frame fills ignore the camera
        if not self.uses_3d():
            for l in self.children:
                l.draw(canvas, t, ctx)
            return
        # backgrounds first, then grounds (floors), then far to near by depth; equal depths keep
        # the order they were added (predictable)
        lead = _lead_backgrounds(self.children)
        layers = [l for _, l in sorted(enumerate(self.children), key=lambda il: (
            _draw_tier(il[1], lead), -il[1].depth.at(t), il[0]))]
        for l in layers:
            self.draw_layer3d(canvas, t, ctx, l)

    def draw_layer3d(self, canvas, t, ctx, l):
        """Draw one top-level layer through the camera: homography (clipped at the lens), depth
        of field, haze. ctx.screen_matrix must be set (draw_scene does it)."""
        if not l.visible(t):
            return
        cam = self.camera
        H, near_clip = cam.homography_clip(t, l)
        if H is None:
            return
        l._echo_matrix = (lambda tk, _l=l: cam.homography(tk, _l))
        dof = 0.0
        d = l.depth.at(t)
        if (cam.aperture.animated or cam.aperture.rest() > 0) and not getattr(l, "own_dof", False):
            px = cam.dof_px(t, d)
            if px > 0.35:
                # screen px -> the layer's local px (far layers are drawn scaled down)
                k = cam.scale_at(t, d)
                dof = px / max(0.05, k)
        tint = None if (l.kind == "background" or getattr(l, "own_haze", False)) else self._haze_tint(d)
        l.draw(canvas, t, ctx, m=H, dof=dof, tint=tint, near_clip=near_clip)

    def layer_matrix(self, layer, t):
        """Scene->screen matrix for a top-level layer EXCLUDING its own transform (QA)."""
        if self.uses_3d():
            H = self.camera.homography(t, layer)
            if H is None:
                return None
            inv = skia.Matrix()
            if layer.matrix(t).invert(inv):
                return skia.Matrix.Concat(H, inv)
        return None


# ----------------------------------------------------------------------------- project

ASPECTS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350),
           "4:3": (1440, 1080), "21:9": (2520, 1080)}


class Event:
    __slots__ = ("t", "kind", "params", "accent", "source")

    def __init__(self, t, kind, params, accent=False, source="manual"):
        self.t, self.kind, self.params, self.accent, self.source = t, kind, params, accent, source

    def __repr__(self):
        return f"Event({self.t:.3f}, {self.kind}, accent={self.accent})"


class Project:
    def __init__(self, design, duration=None, aspect=None, fps=None, seed=7, short_side=1080):
        from .design import Design
        if isinstance(design, str):
            design = Design.load(design)
        self.design = design
        CURRENT["design"] = design
        CURRENT["project"] = self
        fmt = design.format
        aspect = aspect or fmt.get("aspect", "16:9")
        w, h = ASPECTS[aspect]
        k = short_side / min(w, h)
        self.W, self.H = int(round(w * k)), int(round(h * k))
        design.bind(self.W, self.H)
        self.aspect = aspect
        self.fps = fps or fmt.get("fps", 30)
        self._duration = duration                    # explicit length; else the end of the last scene
        self.target_duration = fmt.get("duration")   # brief target (QA compares)
        self.seed = seed
        self.scenes = []
        self.overlay = Group(name="Overlay")
        self.overlay.scene = None
        self.events = []
        self.post = {}          # global fx config: name -> params (from design.fx.enabled)
        self.fx_tracks = {}     # name -> Prop intensity over project time (e.g. glitch)
        self.motion_blur = None
        self.blur_windows = []  # [(t0, t1, samples, shutter)]: object motion blur, project seconds
        self.meta = {}
        self._cache = {}
        snd = design.sound or {}
        self.bpm = float(snd.get("bpm", 100))
        self.beat_offset = float(snd.get("beat_offset", 0.0))
        self.beats_per_bar = int(snd.get("beats_per_bar", 4))
        for name, params in (design.fx.get("enabled") or {}).items():
            self.post[name] = dict(params or {})

    # ---- time grid
    @property
    def duration(self):
        if self._duration:
            return float(self._duration)
        if self.scenes:
            return max(s.t1 for s in self.scenes)
        return float(self.target_duration or 0.0)

    @duration.setter
    def duration(self, v):
        self._duration = v

    @property
    def frames(self):
        return int(round(self.duration * self.fps))

    def beat(self, n):
        return self.beat_offset + n * 60.0 / self.bpm

    def bar(self, n):
        return self.beat(n * self.beats_per_bar)

    def snap(self, t, div=1):
        """Nearest beat subdivision (div=2 -> eighths at 4/4)."""
        step = 60.0 / self.bpm / div
        return self.beat_offset + round((t - self.beat_offset) / step) * step

    def frame_snap(self, t):
        return round(t * self.fps) / self.fps

    # ---- authoring
    def scene(self, name, dur, transition=None, start=None, bg="bg", energy=0.5, notes="", snap=True):
        """Append a scene. With a transition it overlaps the previous scene; snap=True puts
        the scene start on the nearest half-beat so scene-local beats (s.beat(n), multiples
        of 60/bpm) stay on the music grid."""
        if start is None:
            start = self.scenes[-1].t1 if self.scenes else 0.0
            if transition is not None and self.scenes:
                start -= transition.dur
            if snap and self.scenes:
                start = max(self.scenes[-1].t0 + 0.1, self.snap(start, 2))
        s = Scene(self, name, start, dur, transition, bg, energy, notes)
        self.scenes.append(s)
        if transition is not None and len(self.scenes) > 1:
            transition.on_add(self, start + transition.dur / 2)
        return s

    def add_overlay(self, *layers):
        """Layers drawn above all scenes in PROJECT time (HUD, logo bug, progress)."""
        for l in layers:
            l.scene = None
            if l._anchor_spec:
                l.resolve_anchor()
            self.overlay.children.append(l)
        return layers[0] if len(layers) == 1 else layers

    def sfx(self, t, kind, accent=False, **params):
        self.events.append(Event(self.frame_snap(t), kind, params, accent))
        return self

    def blur_window(self, t0, t1, samples=12, shutter=180.0):
        """Real sub-frame motion blur between t0 and t1 (project seconds) where layers move
        fast without the camera (a logo flying in, a group scaling 6x in 0.5 s, a lockup jump).
        The camera's own moves are blurred automatically. Start a window 0.02-0.04 s after a
        hard colour flip and end it before the next one, or that frame blends two backgrounds.
        12-16 samples for a big pull-back, 6-8 for a short move."""
        self.blur_windows.append((float(t0), float(t1), int(samples), float(shutter)))
        return self

    def fx_track(self, name):
        """Intensity Prop (0..1) over project time for a global fx, e.g. glitch."""
        if name not in self.fx_tracks:
            self.fx_tracks[name] = Prop(0.0, f"fx.{name}")
        return self.fx_tracks[name]

    def pulse(self, name, t, amount=1.0, attack=0.04, release=0.18):
        """Short intensity pulse on a global fx track (glitch hits etc.)."""
        p = self.fx_track(name)
        p.key(t - attack, 0.0, "linear").key(t, amount, "out_quad").key(t + release, 0.0, "in_out_sine")
        return self

    # ---- queries
    def active_scenes(self, t):
        return [s for s in self.scenes if s.t0 - 1e-9 <= t < s.t1 - 1e-9]

    def all_layers(self):
        for s in self.scenes:
            for l in s.walk():
                yield s, l
        for l in self.overlay.walk():
            yield None, l

    def all_events(self):
        ev = list(self.events)
        for s in self.scenes:
            for t, k, p in s.audio_events():
                if 0 <= t <= s.dur:
                    p = dict(p or {})
                    acc = p.pop("accent", False)
                    ev.append(Event(self.frame_snap(s.t0 + t), k, p, acc, "auto"))
        for t, k, p in self.overlay.audio_events():
            ev.append(Event(self.frame_snap(t), k, dict(p or {}), False, "auto"))
        ev.sort(key=lambda e: e.t)
        return ev

    # ---- drawing
    def draw(self, canvas, t, ctx):
        bg = self.design.palette.get("bg", (0, 0, 0, 1))
        canvas.drawColor(c4f(bg))
        act = self.active_scenes(t)
        if len(act) == 1:
            act[0].draw_scene(canvas, t - act[0].t0, ctx)
        elif len(act) >= 2:
            a, b = act[-2], act[-1]
            tr = b.transition
            if tr is None:
                b.draw_scene(canvas, t - b.t0, ctx)
            else:
                p = (t - b.t0) / tr.dur if tr.dur > 0 else 1.0
                tr.render(canvas, lambda c: a.draw_scene(c, t - a.t0, ctx),
                          lambda c: b.draw_scene(c, t - b.t0, ctx), max(0.0, min(1.0, p)), ctx)
        self.overlay.render(canvas, t, ctx)
