"""Space: a set the camera films head-on, not a slide it slides over (motion.md section 2b).

The engine is 2.5D: flat layers placed at depths (px, + is farther), projected by the scene
camera with true perspective. Depth reads through parallax, focus, haze, light and scale while
the camera looks at the layers nearly head-on (within ~15 degrees). Seen from the side, a flat
layer shows it is paper: that is the PowerPoint 3D look, so there is no
extruded type here and QA `oblique` fails flat layers held at an angle.

Floor       the ground everything stands on: gradient to the horizon, painted lines, pools of
            light. Drawn first, clipped at the lens.
Reflection  a layer mirrored in a glossy floor, fading away from the contact line.
LightBeam   a volumetric beam from a lamp above the set.
Motes       dust in the air at many depths: depth of field turns near and far motes into bokeh.
            dust() adds one layer behind the subject and one in front of it.

Values are real output px. World y grows down; the stage plane is depth 0.
"""
import math

import numpy as np

from ..core import Layer, Prop, Blur, color, skia, CURRENT, P_

__all__ = ["Floor", "Reflection", "LightBeam", "Motes", "dust", "mirror_y"]


def _c4(spec, a=None):
    c = color(spec)
    return skia.Color4f(c[0], c[1], c[2], c[3] if a is None else a)


def _mix(a, b, k):
    ca, cb = color(a), color(b)
    return tuple(ca[i] * (1 - k) + cb[i] * k for i in range(3)) + (ca[3],)


# ----------------------------------------------------------------------------- floor

class Floor(Layer):
    """Ground plane at world height `y` (px, y grows down), centred at depth `z`, `size` =
    (width, depth extent). Shaded from `near` (the colour under the subject) towards the horizon,
    where it fades out over the far `horizon` share of its extent and dissolves into whatever is
    behind it (the background, a sky gradient). `far` = a colour instead of the fade. `lines`
    paints a grid (step px; 0 = none), `bays` only the lines running into the distance (a car
    park, a stage, a runway). `pool(x, z, r, ...)` adds a pool of light on the floor; its
    intensity is a Prop.

    The floor is drawn right after the background (layer.ground) and is clipped at the camera,
    so a dolly over it never makes it vanish. Its near edge (z - depth/2) must lie behind the
    camera (the camera sits focal/zoom in front of the stage plane, ~3000-6000 px in a wide shot),
    or the edge shows as a line across the bottom of the frame: the default reaches -7000."""
    kind = "floor"
    exportable = False

    def __init__(self, y, z=3000.0, size=(20000, 20000), near="surface", far=None, horizon=0.35,
                 lines=0, bays=0, line_color="text@0.08", line_width=3.0, x=None, **kw):
        p = CURRENT.get("project")
        x = (p.W / 2 if p is not None else 0.0) if x is None else x
        kw.setdefault("rx", 90.0)
        kw.setdefault("name", "Floor")
        super().__init__(pos=(x, y), depth=z, **kw)
        self.w, self.d = float(size[0]), float(size[1])
        self.near_c, self.far_c = near, far
        self.horizon = float(horizon)
        self.lines, self.bays = float(lines), float(bays)
        self.line_color, self.line_width = line_color, float(line_width)
        self.pools = []
        self.ground = True          # draw order: after the background, before everything else
        self.own_haze = True        # it fades into the air by itself
        self.own_dof = True         # one blur for a plane that runs from the lens to the horizon is wrong
        self.soft_horizon = 1.0     # the floor fades out over this x 9 % of the frame height above the horizon line (0 = hard edge)

    def pool(self, x, z, r=700.0, color_="#FFFFFF", intensity=0.25, squash=1.0):
        """Pool of light on the floor at world (x, z). Returns its intensity Prop (animate it)."""
        k = Prop(intensity, "pool.intensity")
        self.pools.append((float(x), float(z), float(r), color_, k, float(squash)))
        return k

    def local_bounds(self, t):
        return (-self.w / 2, -self.d / 2, self.w / 2, self.d / 2)

    def _local(self, x, z, t):
        """World (x, z) on the floor -> local coords (rx = 90: local -y runs into the distance)."""
        px, _ = self.position.at(t)
        return x - px, self.depth.at(t) - z

    def _screen_fade(self, canvas, t, ctx):
        """Alpha shader in screen space: 0 on the projected horizon, 1 a band below it. Near eye
        level the far floor squeezes into a few pixels; without this it ends on a hard line and
        its lines turn into moire. In local coords, so no offscreen layer is needed."""
        s, sm = self.scene, getattr(ctx, "screen_matrix", None)
        if s is None or sm is None or not self.soft_horizon:
            return None
        cam = s.camera
        _, fy = self.position.at(t)
        far = self.depth.at(t) + self.d / 2
        cx, _ = cam.pos.at(t)
        pa, pb = cam.project(t, cx - 2000.0, fy, far), cam.project(t, cx + 2000.0, fy, far)
        if pa is None or pb is None:
            return None
        (xa, ya), (xb, yb) = pa[:2], pb[:2]
        dx, dy = xb - xa, yb - ya
        ln = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln, dx / ln               # normal of the horizon line, pointing down the screen
        if ny < 0:
            nx, ny = -nx, -ny
        band = 0.09 * cam.H * self.soft_horizon
        xm, ym = (xa + xb) / 2, (ya + yb) / 2
        inv = skia.Matrix()
        if not canvas.getTotalMatrix().invert(inv):
            return None
        lm = skia.Matrix.Concat(inv, sm)         # project-screen px -> the floor's local coords
        return skia.GradientShader.MakeLinear(
            [skia.Point(xm, ym), skia.Point(xm + nx * band, ym + ny * band)],
            [skia.Color4f(0, 0, 0, 0), skia.Color4f(0, 0, 0, 1)], [0.0, 1.0],
            skia.TileMode.kClamp, 0, lm)

    def render(self, canvas, t, ctx):
        # no offscreen layer: the horizon fade lives in the shaders' alpha (a full-frame layer
        # under perspective costs as much as the rest of the set)
        hw, hd = self.w / 2, self.d / 2
        h = max(0.02, min(0.9, self.horizon))
        near = color(self.near_c)
        far = color(self.far_c) if self.far_c is not None else _mix(self.near_c, "#000000", 0.35)
        mid = tuple(far[i] * 0.45 + near[i] * 0.55 for i in range(3))
        fade = self.far_c is None
        a_far = 0.0 if fade else 1.0
        pts = [skia.Point(0, -hd), skia.Point(0, hd)]
        sfade = self._screen_fade(canvas, t, ctx)

        def faded(sh):
            return sh if sfade is None else skia.Shaders.Blend(skia.BlendMode.kDstIn, sh, sfade)

        sh = skia.GradientShader.MakeLinear(
            pts, [skia.Color4f(far[0], far[1], far[2], a_far), skia.Color4f(mid[0], mid[1], mid[2], 1.0),
                  skia.Color4f(near[0], near[1], near[2], 1.0)], [0.0, h, 1.0])
        rect = skia.Rect.MakeLTRB(-hw, -hd, hw, hd)
        canvas.drawRect(rect, skia.Paint(Shader=faded(sh), Dither=True))
        for (x, z, r, col, k, sq) in self.pools:
            a = max(0.0, k.at(t))
            if a <= 0.002:
                continue
            lx, ly = self._local(x, z, t)
            if fade:
                # pools fade with the floor towards the horizon
                u = (ly + hd) / (2 * hd)
                a *= max(0.0, min(1.0, u / h)) if u < h else 1.0
            c = color(col)
            g = skia.GradientShader.MakeRadial(
                skia.Point(0, 0), r, [skia.Color4f(c[0], c[1], c[2], a), skia.Color4f(c[0], c[1], c[2], a * 0.35),
                                      skia.Color4f(c[0], c[1], c[2], 0.0)], [0.0, 0.45, 1.0])
            canvas.save()
            canvas.translate(lx, ly)
            canvas.scale(1.0, sq)
            canvas.drawCircle(0, 0, r, skia.Paint(AntiAlias=True, Shader=g, BlendMode=skia.BlendMode.kScreen, Dither=True))
            canvas.restore()
        if self.lines or self.bays:
            lc = color(self.line_color)
            ls = skia.GradientShader.MakeLinear(
                pts, [skia.Color4f(lc[0], lc[1], lc[2], 0.0), skia.Color4f(lc[0], lc[1], lc[2], lc[3]),
                      skia.Color4f(lc[0], lc[1], lc[2], lc[3])], [0.0, min(0.95, h * 1.4), 1.0])
            paint = skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=self.line_width,
                               Shader=faded(ls))
            step = self.lines or self.bays
            path = skia.Path()
            x = -math.floor(hw / step) * step
            while x <= hw:
                path.moveTo(x, -hd)
                path.lineTo(x, hd)
                x += step
            if self.lines:
                y = -math.floor(hd / step) * step
                while y <= hd:
                    path.moveTo(-hw, y)
                    path.lineTo(hw, y)
                    y += step
            canvas.drawPath(path, paint)


# ----------------------------------------------------------------------------- proxies

class _Proxy(Layer):
    """A layer that shares its source's transform Props and draws the source's content: it
    moves, reveals and fades with it, whatever is keyed on the source later."""
    exportable = False

    def __init__(self, src, name=None, opacity=1.0):
        super().__init__(name=name)
        self.src = src
        for pn in ("position", "anchor", "scale", "rotation", "rx", "ry", "clip"):
            setattr(self, pn, getattr(src, pn))
        self.mask, self.mask_mode = src.mask, src.mask_mode
        k = float(opacity)
        self.opacity = Prop(1.0, "opacity").drive(lambda t, _s=src, _k=k: _s.opacity.at(t) * _k)
        self.insert_before = src
        self.start, self.end = src.start, src.end

    @property
    def billboard(self):
        return getattr(self.__dict__.get("src"), "billboard", False)

    @billboard.setter
    def billboard(self, v):
        pass

    @property
    def time_step(self):
        return getattr(self.src, "time_step", None)

    def visible(self, t):
        return self.src.visible(t)

    def local_bounds(self, t):
        return self.src.local_bounds(t)

    def render(self, canvas, t, ctx):
        self.src.render(canvas, t, ctx)


def mirror_y(y):
    """4x4 world matrix mirroring about the horizontal plane at world height y."""
    m = np.eye(4)
    m[1, 1] = -1.0
    m[1, 3] = 2.0 * y
    return m


class Reflection(_Proxy):
    """The source mirrored in a glossy floor at world height `floor_y`: same depth, flipped about
    the floor plane, `opacity` of the source, softened by `blur` px, fading out over `fade` of
    the source's height away from the contact line. The source must be a top-level layer of the
    scene; add the reflection after it, it is drawn under it."""
    kind = "reflection"

    def __init__(self, src, floor_y, opacity=0.22, blur=4.0, fade=0.75, name=None):
        if src.scene is not None and src not in src.scene.children:
            raise ValueError(f"Reflection: '{src.name}' sits inside a group; reflect a top-level layer")
        super().__init__(src, name=name or f"{src.name} reflection", opacity=opacity)
        self.depth = src.depth
        self.floor_y = float(floor_y)
        self.world_pre = mirror_y(self.floor_y)
        self.fade = float(fade)
        self.fx = [Blur(blur / 2.0)] if blur else []     # Blur takes legacy half-px

    def _foot(self, t, b):
        """Local y of the source edge that touches the floor (closest to floor_y)."""
        from ..core import layer_model
        M = layer_model(self.src, t)
        cx = (b[0] + b[2]) / 2
        ys = []
        for ly in (b[1], b[3]):
            p = M @ np.array([cx, ly, 0.0, 1.0])
            ys.append(abs(p[1] - self.floor_y))
        return (b[1], b[3]) if ys[0] < ys[1] else (b[3], b[1])

    def render(self, canvas, t, ctx):
        b = self.src.local_bounds(t)
        if b is None or self.fade <= 0:
            self.src.render(canvas, t, ctx)
            return
        foot, head = self._foot(t, b)
        end = foot + (head - foot) * min(1.0, self.fade)
        canvas.saveLayer(None, None)
        self.src.render(canvas, t, ctx)
        sh = skia.GradientShader.MakeLinear([skia.Point(0, foot), skia.Point(0, end)],
                                            [skia.Color4f(0, 0, 0, 1), skia.Color4f(0, 0, 0, 0)], [0.0, 1.0])
        m = 2 * max(abs(b[2] - b[0]), abs(b[3] - b[1]), 1.0)
        canvas.drawRect(skia.Rect.MakeLTRB(b[0] - m, b[1] - m, b[2] + m, b[3] + m),
                        skia.Paint(Shader=sh, BlendMode=skia.BlendMode.kDstIn))
        canvas.restore()


# ----------------------------------------------------------------------------- light beam

class LightBeam(Layer):
    """A volumetric beam from a lamp at `pos` (the source), `length` px down (rotate it to aim),
    `width` at the far end (`top` at the lamp). Screen-blended, soft-edged (`softness` = share of
    the width that falls off at each side), brightest at the lamp. It turns around its vertical
    axis to face the camera (billboard "y"), so an orbit never shows it as a flat card.
    `intensity` is a Prop; `source=True` draws the lamp itself."""
    kind = "light_beam"
    exportable = False

    def __init__(self, length=1800, width=1300, top=120, color_="#FFFFFF", intensity=0.22, softness=0.35,
                 source=True, **kw):
        kw.setdefault("blend", "screen")
        super().__init__(**kw)
        self.length, self.width, self.top = float(length), float(width), float(top)
        self.col = color_
        self.intensity = P_(intensity, "intensity")
        self.softness = max(0.02, min(0.5, float(softness)))
        self.source = source
        self.billboard = "y"

    def local_bounds(self, t):
        hw = max(self.width, self.top) / 2
        return (-hw, -20, hw, self.length)

    def render(self, canvas, t, ctx):
        k = max(0.0, self.intensity.at(t))
        if k <= 0.002:
            return
        c = color(self.col)
        L, w2, t2 = self.length, self.width / 2, self.top / 2
        # a unit rectangle mapped onto the trapezoid: the soft sides follow the slanted edges
        m = skia.Matrix()
        m.setPolyToPoly([skia.Point(-1, 0), skia.Point(1, 0), skia.Point(1, 1), skia.Point(-1, 1)],
                        [skia.Point(-t2, 0), skia.Point(t2, 0), skia.Point(w2, L), skia.Point(-w2, L)])
        sft = self.softness
        across = skia.GradientShader.MakeLinear(
            [skia.Point(-1, 0), skia.Point(1, 0)],
            [skia.Color4f(1, 1, 1, 0), skia.Color4f(1, 1, 1, 0.55), skia.Color4f(1, 1, 1, 1), skia.Color4f(1, 1, 1, 0.55),
             skia.Color4f(1, 1, 1, 0)], [0.0, sft, 0.5, 1 - sft, 1.0])
        along = skia.GradientShader.MakeLinear(
            [skia.Point(0, 0), skia.Point(0, 1)],
            [skia.Color4f(c[0], c[1], c[2], k), skia.Color4f(c[0], c[1], c[2], k * 0.5),
             skia.Color4f(c[0], c[1], c[2], k * 0.14), skia.Color4f(c[0], c[1], c[2], 0.0)], [0.0, 0.22, 0.62, 1.0])
        sh = skia.Shaders.Blend(skia.BlendMode.kModulate, across, along)
        canvas.save()
        canvas.concat(m)
        canvas.drawRect(skia.Rect.MakeLTRB(-1, 0, 1, 1), skia.Paint(Shader=sh, Dither=True))
        canvas.restore()
        if self.source:
            canvas.drawRoundRect(skia.Rect.MakeLTRB(-t2 * 0.9, -9, t2 * 0.9, 5), 7, 7,
                                 skia.Paint(AntiAlias=True, Color4f=skia.Color4f(min(1, c[0] + 0.2), min(1, c[1] + 0.2),
                                                                                 min(1, c[2] + 0.2), min(1.0, k * 4))))


# ----------------------------------------------------------------------------- motes

class Motes(Layer):
    """Dust in the air: `n` motes in a box centred at (x, y, z) of `size` (w, h, d) px, drifting
    by `drift` (vx, vy, vz px/s). Drawn in screen space through the scene camera, each at its own
    depth: with camera.dof() the ones off the focus plane open into bokeh discs, so this is the
    cheapest way to put air between the lens and the subject. Use dust() to get one layer behind
    the subject and one in front of it (draw order needs both)."""
    kind = "motes"
    exportable = False

    def __init__(self, center=(0, 0, 0), size=(1600, 1600, 2400), n=60, radius=(1.5, 4.5), color_="#FFFFFF",
                 alpha=(0.25, 0.7), drift=(0.0, -18.0, 0.0), twinkle=0.25, seed=7, zrange=None, **kw):
        super().__init__(**kw)
        rng = np.random.default_rng(seed)
        cx, cy, cz = center
        w, h, d = size
        p = np.stack([cx + rng.uniform(-w / 2, w / 2, n), cy + rng.uniform(-h / 2, h / 2, n),
                      cz + rng.uniform(-d / 2, d / 2, n)], 1)
        if zrange is not None:
            keep = (p[:, 2] >= zrange[0]) & (p[:, 2] < zrange[1])
            p = p[keep]
        m = len(p)
        self.p0 = p
        self.r = rng.uniform(radius[0], radius[1], n)[:m]
        self.a = rng.uniform(alpha[0], alpha[1], n)[:m]
        self.ph = rng.uniform(0, 2 * math.pi, n)[:m]
        self.v = np.array(drift, float) * rng.uniform(0.6, 1.4, (n, 1))[:m]
        self.col = color_
        self.twinkle = float(twinkle)
        self.screen_space = True
        self.own_dof = True
        if m and "depth" not in kw:
            self.depth.set(float(np.median(p[:, 2])))

    def render(self, canvas, t, ctx):
        s = self.scene
        sm = getattr(ctx, "screen_matrix", None)
        if s is None or sm is None or not len(self.p0):
            return
        cam = s.camera
        P = cam.view_proj(t)
        pts = self.p0 + self.v * t
        hom = np.c_[pts, np.ones(len(pts))] @ P.T
        c = color(self.col)
        f = cam.focal * max(0.01, cam.lens.at(t))
        W, H = cam.W, cam.H
        canvas.save()
        canvas.setMatrix(sm)
        paint = skia.Paint(AntiAlias=True)
        for i in range(len(pts)):
            w = hom[i, 2]
            if w <= 0.05 * cam.focal:
                continue
            x, y = hom[i, 0] / w, hom[i, 1] / w
            r = self.r[i] * f / w
            blur = cam.dof_px(t, pts[i, 2])
            R = max(r, 0.9 * blur)
            if x < -R or x > W + R or y < -R or y > H + R:
                continue
            a = self.a[i] * (1 - self.twinkle + self.twinkle * (0.5 + 0.5 * math.sin(1.7 * t + self.ph[i])))
            a *= max(0.12, min(1.0, (r / R) ** 1.4))
            paint.setColor4f(skia.Color4f(c[0], c[1], c[2], a))
            paint.setMaskFilter(skia.MaskFilter.MakeBlur(skia.BlurStyle.kNormal_BlurStyle, 0.18 * R + 0.4))
            canvas.drawCircle(x, y, R, paint)
        canvas.restore()


def dust(s, center, size=(1800, 1800, 3000), n=70, split=0.0, **kw):
    """Add motes to scene `s` as two layers: behind depth `split` and in front of it (the
    subject's plane). Returns (back, front)."""
    seed = kw.pop("seed", 7)
    back = Motes(center, size, n, seed=seed, zrange=(split, 1e9), name="Motes back", **kw)
    front = Motes(center, size, n, seed=seed, zrange=(-1e9, split), name="Motes front", **kw)
    s.add(back)
    s.add(front)
    return back, front
