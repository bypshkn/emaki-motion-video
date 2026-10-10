#!/usr/bin/env python3
"""Emaki hero image: konshi kinji. Drawn in code with skia-python.

The scroll is indigo-dyed paper drawn in gold ink, the way 12th-century Japan wrote and
painted its finest scrolls. Read right to left: a gold-line landscape (mist bands, two ridges,
flowing water, a vermilion sun) turns into a motion timeline drawn with the same gold line.
The water becomes a bezier path, the ridge a wireframe, the mist band a clip, and the sun the
keyframed dot the camera follows.

    python3 hero.py OUT_DIR   -> OUT_DIR/hero.jpg (2560x1280), OUT_DIR/social-preview.jpg (1280x640)

Fonts: Nimbus Sans or Helvetica. On headless Linux run scripts/setup_env.sh first and export
LD_LIBRARY_PATH=~/.cache/emaki so skia-python finds its EGL stub.
"""
import math
import os
import sys

import numpy as np
import skia
from scipy.ndimage import gaussian_filter

W, H = 1280, 640
S = 2
rng = np.random.default_rng(21)

BG = (11, 12, 16)
INDIGO = (27, 38, 80)
INDIGO_LIGHT = (44, 60, 116)
GOLD = (214, 177, 98)
GOLD_LIGHT = (236, 210, 150)
SHU = (226, 74, 42)
WHITE = (236, 234, 228)
GREY = (138, 140, 146)

PX0, PX1, PY0, PY1 = 112, 1128, 232, 568


def col(c, a=1.0):
    return skia.Color(int(c[0]), int(c[1]), int(c[2]), int(round(255 * max(0.0, min(1.0, a)))))


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def fill(c, a=1.0):
    return skia.Paint(AntiAlias=True, Color=col(c, a))


def line(c, a=1.0, w=1.0, cap=True):
    p = skia.Paint(AntiAlias=True, Color=col(c, a), Style=skia.Paint.kStroke_Style, StrokeWidth=w)
    if cap:
        p.setStrokeCap(skia.Paint.kRound_Cap)
        p.setStrokeJoin(skia.Paint.kRound_Join)
    return p


def poly(xs, ys, close=False):
    p = skia.Path()
    p.moveTo(float(xs[0]), float(ys[0]))
    for x, y in zip(xs[1:], ys[1:]):
        p.lineTo(float(x), float(y))
    if close:
        p.close()
    return p


FM = skia.FontMgr()


def typeface(families, files=()):
    for f in files:
        if os.path.exists(f):
            t = skia.Typeface.MakeFromFile(f, 0)
            if t:
                return t
    for fam in families:
        t = FM.matchFamilyStyle(fam, skia.FontStyle.Normal())
        if t:
            return t
    return skia.Typeface.MakeDefault()


SANS = typeface(["Nimbus Sans", "Helvetica Neue", "Helvetica", "Arial"],
                ["/usr/share/fonts/opentype/urw-base35/NimbusSans-Regular.otf"])


def text(cv, s, x, y, size, c, a=1.0, align="left", tracking=0.0):
    font = skia.Font(SANS, size)
    font.setSubpixel(True)
    font.setEdging(skia.Font.Edging.kAntiAlias)
    w = sum(font.measureText(ch) + tracking for ch in s) - tracking
    if align == "right":
        x -= w
    for ch in s:
        cv.drawString(ch, x, y, font, fill(c, a))
        x += font.measureText(ch) + tracking


# ---------------------------------------------------------------- shapes
def bump(x, c, w):
    return np.exp(-((x - c) / w) ** 2)


def far_ridge(x):
    return 398 - 58 * bump(x, 872, 70) - 84 * bump(x, 1048, 62) - 22 * bump(x, 760, 50) \
        - 46 * bump(x, 640, 34) + 4 * np.sin(x / 13.0) * bump(x, 960, 160)


def near_ridge(x):
    return 440 - 46 * bump(x, 962, 54) - 30 * bump(x, 1092, 46) - 12 * bump(x, 850, 40) + 2.5 * np.sin(x / 7.0)


def water(i, x):
    base = 476 + 17 * i
    calm = np.clip((x - 150) / 560.0, 0.0, 1.0) * 0.6 + 0.4 if i == 1 else 1.0
    return base + calm * (7 * np.sin((x + 30 * i) / 37.0) + 4 * np.sin(x / 93.0 + i))


def var_stroke(pts, widths):
    pts = np.asarray(pts, float)
    d = np.gradient(pts, axis=0)
    d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-9
    n = np.stack([-d[:, 1], d[:, 0]], 1)
    L = pts + n * (widths[:, None] / 2)
    R = pts - n * (widths[:, None] / 2)
    p = skia.Path()
    p.moveTo(*L[0])
    for q in L[1:]:
        p.lineTo(*q)
    for q in R[::-1]:
        p.lineTo(*q)
    p.close()
    return p


def gold_brush(cv, pts, w0, a=0.95, taper=(0.12, 0.25), seed=0):
    """A gold-ink line: pressure swell, tapered ends."""
    r = np.random.default_rng(seed)
    n = len(pts)
    u = np.linspace(0, 1, n)
    press = np.minimum(np.clip(u / taper[0], 0, 1), np.clip((1 - u) / taper[1], 0, 1)) ** 0.7
    wob = gaussian_filter(r.normal(0, 1, n), 6) * 0.3
    widths = np.maximum(0.3, w0 * press * (1 + wob))
    cv.drawPath(var_stroke(pts, widths), fill(GOLD, a))


def mist_band(x0, x1, y0, y1, seed, right_round=False):
    r = np.random.default_rng(seed)
    xs = np.linspace(x0, x1, 120)
    ph = r.uniform(0, 6)
    top = y0 + 2.2 * np.sin(xs / 31 + ph) + 1.4 * np.sin(xs / 11 + ph * 2)
    bot = y1 + 2.2 * np.sin(xs / 29 + ph * 1.3) + 1.2 * np.sin(xs / 9 + ph)
    p = skia.Path()
    p.moveTo(xs[0], top[0])
    for x, y in zip(xs, top):
        p.lineTo(x, y)
    if right_round:
        h = bot[-1] - top[-1]
        p.cubicTo(x1 + h * 0.75, top[-1], x1 + h * 0.75, bot[-1], x1, bot[-1])
    else:
        p.lineTo(x1 + 40, top[-1])
        p.lineTo(x1 + 40, bot[-1])
    for x, y in zip(xs[::-1], bot[::-1]):
        p.lineTo(x, y)
    h = bot[0] - top[0]
    p.cubicTo(x0 - h * 0.75, bot[0], x0 - h * 0.75, top[0], x0, top[0])
    p.close()
    return p


def gold_mist(cv, path, seed):
    """Gold-paint mist: a thin wash, a gold outline and gold dust inside."""
    cv.drawPath(path, fill(mix(GOLD, INDIGO, 0.22)))
    cv.save()
    cv.clipPath(path, doAntiAlias=True)
    r = np.random.default_rng(seed)
    b = path.getBounds()
    for _ in range(int(b.width() * b.height() / 26)):
        x, y = r.uniform(b.left(), b.right()), r.uniform(b.top(), b.bottom())
        s = r.uniform(0.5, 1.8)
        cv.drawRect(skia.Rect(x, y, x + s, y + s), fill(GOLD_LIGHT, r.uniform(0.35, 0.9)))
    cv.restore()
    cv.drawPath(path, line(GOLD, 0.95, 1.2))


# ---------------------------------------------------------------- scene
def background(cv):
    cv.drawRect(skia.Rect(0, 0, W, H), fill(BG))


def scroll_shadow(cv):
    r = skia.Rect(70, 236, 1182, 578)
    p = fill((0, 0, 0), 0.6)
    p.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, 14))
    cv.save()
    cv.translate(8, 14)
    cv.drawRoundRect(r, 6, 6, p)
    cv.restore()


def paper(cv):
    """Indigo-dyed paper: uneven dye, lighter fibres, and gold dust that thins out to the left."""
    rect = skia.Rect(PX0, PY0, PX1, PY1)
    w, h = int((PX1 - PX0) * S), int((PY1 - PY0) * S)
    cloud = gaussian_filter(rng.normal(0, 1, (h, w)), 30 * S)
    cloud /= np.abs(cloud).max() + 1e-9
    tooth = gaussian_filter(rng.normal(0, 1, (h, w)), 0.8 * S)
    tooth /= np.abs(tooth).max() + 1e-9
    base = np.array(INDIGO, float)
    img = base[None, None, :] * (1 + 0.10 * cloud[..., None] + 0.04 * tooth[..., None])
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., :3] = np.clip(img, 0, 255).astype(np.uint8)
    arr[..., 3] = 255
    im = skia.Image.fromarray(arr, colorType=skia.kRGBA_8888_ColorType)
    cv.drawImageRect(im, rect, skia.SamplingOptions(skia.FilterMode.kLinear))
    cv.save()
    cv.clipRect(rect)
    r = np.random.default_rng(3)
    for _ in range(300):
        x, y = r.uniform(PX0, PX1), r.uniform(PY0, PY1)
        ang, ln = r.uniform(0, math.pi), r.uniform(8, 40)
        cv.drawLine(x, y, x + math.cos(ang) * ln, y + math.sin(ang) * ln,
                    line(INDIGO_LIGHT, r.uniform(0.25, 0.5), r.uniform(0.3, 0.7)))
    # gold dust and cut-gold flakes (sunago, kirihaku), dense in the painting, gone in the timeline
    for _ in range(26):
        x = PX1 - abs(r.normal(0, 200))
        if x < 760:
            continue
        y = r.uniform(PY0 + 10, PY1 - 10)
        s = r.uniform(2.4, 4.2)
        cv.save()
        cv.translate(x, y)
        cv.rotate(r.uniform(0, 90))
        cv.drawRect(skia.Rect(-s / 2, -s / 2, s / 2, s / 2), fill(GOLD_LIGHT, r.uniform(0.3, 0.85)))
        cv.restore()
    cv.restore()


def painting(cv):
    # the sun, behind the far ridge
    cv.drawCircle(1006, 330, 28, fill(SHU))
    # far ridge: gold wash under a gold contour
    xs = np.linspace(700, PX1 + 4, 300)
    ys = far_ridge(xs)
    wash = poly(np.r_[xs, PX1 + 4, 700], np.r_[ys, PY1, PY1], close=True)
    wp = skia.Paint(AntiAlias=True)
    wp.setShader(skia.GradientShader.MakeLinear(
        [skia.Point(0, 300), skia.Point(0, 470)], [col(INDIGO, 1.0), col(INDIGO, 1.0)]))
    cv.drawPath(wash, wp)                                 # the ridge hides the sun's foot
    cv.saveLayer()
    gp = skia.Paint(AntiAlias=True)
    gp.setShader(skia.GradientShader.MakeLinear(
        [skia.Point(0, 300), skia.Point(0, 440)], [col(GOLD, 0.05), col(GOLD, 0.0)]))
    cv.drawPath(wash, gp)
    gold_brush(cv, np.stack([xs[40:], ys[40:]], 1), 2.0, a=1.0, seed=4)
    fade = skia.Paint()
    fade.setBlendMode(skia.BlendMode.kDstIn)
    fade.setShader(skia.GradientShader.MakeLinear([skia.Point(700, 0), skia.Point(800, 0)],
                                                  [skia.Color(0, 0, 0, 0), skia.Color(0, 0, 0, 255)]))
    cv.drawRect(skia.Rect(0, 0, W, H), fade)
    cv.restore()

    xs = np.linspace(780, PX1 + 4, 260)
    ys = near_ridge(xs)
    body = poly(np.r_[xs, PX1 + 4, 780], np.r_[ys, PY1, PY1], close=True)
    cv.saveLayer()
    cv.drawPath(body, fill(INDIGO))
    cv.save()
    cv.clipPath(body, doAntiAlias=True)
    gp = skia.Paint(AntiAlias=True)
    gp.setShader(skia.GradientShader.MakeLinear(
        [skia.Point(0, 390), skia.Point(0, 480)], [col(GOLD, 0.2), col(GOLD, 0.0)]))
    cv.drawRect(skia.Rect(780, 380, PX1, 520), gp)
    for k in range(44):
        x = 806 + k * 8
        y = float(near_ridge(np.array([x]))[0])
        cv.drawLine(x, y + 6, x - 9, y + 26, line(GOLD, 0.4, 0.6))
    cv.restore()
    gold_brush(cv, np.stack([xs, ys], 1), 2.6, seed=5)
    fade = skia.Paint()
    fade.setBlendMode(skia.BlendMode.kDstIn)
    fade.setShader(skia.GradientShader.MakeLinear([skia.Point(780, 0), skia.Point(860, 0)],
                                                  [skia.Color(0, 0, 0, 0), skia.Color(0, 0, 0, 255)]))
    cv.drawRect(skia.Rect(0, 0, W, H), fade)
    cv.restore()
    mid = mist_band(826, 1000, 446, 470, 2, right_round=True)
    cv.drawPath(mid, fill(INDIGO))
    gold_mist(cv, mid, 12)

    for bx, by, s in [(900, 298, 1.0), (922, 309, 0.8), (884, 316, 0.7)]:
        cv.drawPath(poly([bx - 7 * s, bx, bx + 7 * s], [by - 3 * s, by + 1.5 * s, by - 3.5 * s]), line(GOLD, 0.9, 1.2 * s))

    for i in range(3):
        x_end = 720 if i == 1 else 760 + 30 * i
        xs = np.linspace(PX1 + 4, x_end, 220)
        gold_brush(cv, np.stack([xs, water(i, xs)], 1), 2.6 - 0.4 * abs(i - 1),
                   taper=(0.04, 0.3 if i != 1 else 0.6), seed=10 + i)

    top = mist_band(708, PX1, 264, 296, 1)
    cv.drawPath(top, fill(INDIGO))
    gold_mist(cv, top, 11)
    bottom = mist_band(770, PX1, 524, 556, 3)
    cv.drawPath(bottom, fill(INDIGO))
    gold_mist(cv, bottom, 13)


def seam(cv):
    xs = np.arange(756, 548, -17.0)
    ys = far_ridge(xs) + 6
    cv.drawPath(poly(xs, ys), line(GOLD, 0.7, 1.0))
    for x, y in zip(xs, ys):
        cv.drawCircle(float(x), float(y), 2.3, fill(INDIGO))
        cv.drawCircle(float(x), float(y), 2.3, line(GOLD, 0.9, 0.9))
    xs = np.linspace(724, 560, 120)
    cv.drawPath(poly(xs, water(1, xs)), line(GOLD, 1.0, 1.5))
    for ax in (702, 634, 566):
        ay = float(water(1, np.array([ax]))[0])
        dy = float((water(1, np.array([ax + 1.0])) - water(1, np.array([ax - 1.0])))[0] / 2.0)
        t = np.array([1.0, dy])
        t /= np.linalg.norm(t)
        h1, h2 = (ax - t[0] * 24, ay - t[1] * 24), (ax + t[0] * 24, ay + t[1] * 24)
        cv.drawLine(*h1, *h2, line(GOLD, 0.7, 0.9))
        for hx, hy in (h1, h2):
            cv.drawCircle(hx, hy, 2.6, fill(INDIGO))
            cv.drawCircle(hx, hy, 2.6, line(GOLD, 0.95, 0.9))
        r = skia.Rect(ax - 3.4, ay - 3.4, ax + 3.4, ay + 3.4)
        cv.drawRect(r, fill(GOLD if ax == 634 else INDIGO))
        cv.drawRect(r, line(GOLD, 1.0, 1.0, cap=False))


def timeline(cv):
    x0, x1 = 128, 690
    for i, x in enumerate(np.arange(x0, x1, 12.0)):
        major = i % 5 == 0
        a = 0.7 * float(np.clip((x1 - x) / 60.0, 0, 1))
        cv.drawLine(float(x), 252.0 - (6 if major else 3), float(x), 252.0, line(GOLD, a, 0.8, cap=False))
        if major and i % 10 == 0:
            text(cv, f"{i // 10}s", float(x) + 2, 244, 8, GOLD, a)
    cv.drawLine(x0, 252.5, x1, 252.5, line(GOLD, 0.3, 0.7, cap=False))
    for y in (262, 298, 330):
        cv.drawLine(x0, y, x1, y, line(GOLD, 0.14, 0.7, cap=False))
    # the mist band, cut into a clip
    clip = skia.RRect.MakeRectXY(skia.Rect(150, 266, 692, 294), 4, 4)
    cv.drawRRect(clip, fill(GOLD, 0.16))
    cv.drawRRect(clip, line(GOLD, 0.95, 1.0, cap=False))
    cv.drawLine(700, 258, 700, 302, line(GOLD, 0.8, 0.9, cap=False))
    # the ridge, with keyframes
    clip2 = skia.RRect.MakeRectXY(skia.Rect(236, 303, 560, 325), 4, 4)
    cv.drawRRect(clip2, line(GOLD, 0.6, 0.9, cap=False))
    for kx in (236, 404, 560):
        d = skia.Path()
        d.moveTo(kx, 308); d.lineTo(kx + 5, 314); d.lineTo(kx, 320); d.lineTo(kx - 5, 314); d.close()
        cv.drawPath(d, fill(GOLD))
    # playhead
    phx = 420
    head = skia.Path()
    head.moveTo(phx - 6, 238); head.lineTo(phx + 6, 238); head.lineTo(phx + 6, 247)
    head.lineTo(phx, 253); head.lineTo(phx - 6, 247); head.close()
    cv.drawPath(head, fill(GOLD_LIGHT))
    cv.drawLine(phx, 252, phx, 330, line(GOLD_LIGHT, 0.95, 1.2, cap=False))
    dash = line(GOLD, 0.45, 0.9, cap=False)
    dash.setPathEffect(skia.DashPathEffect.Make([3, 4], 0))
    dot_y = float(water(1, np.array([float(phx)]))[0])
    cv.drawLine(phx, 332, phx, dot_y - 12, dash)


def easing_graph(cv):
    bx0, by0, bx1, by1 = 140, 344, 300, 452
    cv.drawRoundRect(skia.Rect(bx0, by0, bx1, by1), 5, 5, line(GOLD, 0.45, 0.8, cap=False))
    pad = 14
    gx0, gy0, gx1, gy1 = bx0 + pad, by1 - pad, bx1 - pad, by0 + pad

    def m(u, v):
        return gx0 + u * (gx1 - gx0), gy0 + v * (gy1 - gy0)

    for k in range(1, 4):
        xx, _ = m(k / 4, 0)
        cv.drawLine(xx, gy1, xx, gy0, line(GOLD, 0.12, 0.7, cap=False))
        _, yy = m(0, k / 4)
        cv.drawLine(gx0, yy, gx1, yy, line(GOLD, 0.12, 0.7, cap=False))
    p0, p1, p2, p3 = m(0, 0), m(0.65, 0), m(0.35, 1), m(1, 1)
    cv.drawLine(*p0, *p1, line(GOLD, 0.6, 0.9))
    cv.drawLine(*p3, *p2, line(GOLD, 0.6, 0.9))
    curve = skia.Path()
    curve.moveTo(*p0)
    curve.cubicTo(*p1, *p2, *p3)
    cv.drawPath(curve, line(GOLD_LIGHT, 1.0, 2.0))
    for q in (p1, p2):
        cv.drawCircle(*q, 3.4, fill(INDIGO))
        cv.drawCircle(*q, 3.4, line(GOLD, 1.0, 1.0))
    for q in (p0, p3):
        cv.drawCircle(*q, 2.4, fill(GOLD))


def motion_path(cv):
    xs = np.linspace(560, 150, 200)
    dash = line(GOLD, 0.6, 1.1, cap=False)
    dash.setPathEffect(skia.DashPathEffect.Make([5, 5], 0))
    cv.drawPath(poly(xs, water(1, xs)), dash)

    def at(x):
        return float(x), float(water(1, np.array([float(x)]))[0])

    for gx, a in [(522, 0.3), (499, 0.45), (474, 0.6), (447, 0.8)]:
        cv.drawCircle(*at(gx), 7.0, line(SHU, a, 1.2))
    cv.drawCircle(*at(420), 7.5, fill(SHU))
    # camera brackets
    x0, y0, x1, y1, k = 358, 452, 482, 516, 9
    p = line(GOLD, 0.7, 1.0, cap=False)
    for (cx, cy, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x1, y1, -1, -1), (x0, y1, 1, -1)):
        cv.drawLine(cx, cy, cx + sx * k, cy, p)
        cv.drawLine(cx, cy, cx, cy + sy * k, p)


def rolls(cv):
    def roll(x0, x1, y0, y1, hi):
        p = skia.Paint(AntiAlias=True)
        p.setShader(skia.GradientShader.MakeLinear(
            [skia.Point(x0, 0), skia.Point(x1, 0)],
            [col(mix(INDIGO, BG, 0.5)), col(INDIGO_LIGHT), col(INDIGO), col(mix(INDIGO, BG, 0.6))],
            [0.0, hi, 0.55, 1.0]))
        cv.drawRoundRect(skia.Rect(x0, y0, x1, y1), 3, 3, p)
        for yy in (y0 + 1.5, y1 - 1.5):
            cv.drawLine(x0 + 2, yy, x1 - 2, yy, line(GOLD, 0.5, 0.8, cap=False))

    rod = skia.Paint(AntiAlias=True)
    rod.setShader(skia.GradientShader.MakeLinear(
        [skia.Point(86, 0), skia.Point(104, 0)], [col((96, 60, 40)), col((58, 34, 22)), col((30, 18, 12))]))
    cv.drawRect(skia.Rect(87, 214, 103, 586), rod)
    for y0, y1 in ((203, 216), (584, 597)):
        cap = skia.Paint(AntiAlias=True)
        cap.setShader(skia.GradientShader.MakeLinear(
            [skia.Point(84, 0), skia.Point(106, 0)], [col(GOLD_LIGHT), col(GOLD), col(mix(GOLD, BG, 0.5))]))
        cv.drawRoundRect(skia.Rect(84, y0, 106, y1), 5, 5, cap)
    roll(76, 114, 228, 572, 0.25)
    roll(1124, 1166, 229, 571, 0.3)
    cord = skia.Path()
    cord.moveTo(1160, 318)
    cord.cubicTo(1200, 330, 1214, 404, 1196, 470)
    cord.cubicTo(1184, 520, 1206, 586, 1238, 604)
    cv.drawPath(cord, line(mix(SHU, BG, 0.25), 1.0, 3.6))


def wordmark(cv, x, base, cap, sw, color, dot_color):
    t, b = base - cap + sw / 2, base - sw / 2
    p = line(color, 1.0, sw)
    gap = cap * 0.2
    ew = cap * 0.5
    e = skia.Path()
    e.moveTo(x + ew, t); e.lineTo(x, t); e.lineTo(x, b); e.lineTo(x + ew, b)
    e.moveTo(x, (t + b) / 2); e.lineTo(x + ew * 0.86, (t + b) / 2)
    cv.drawPath(e, p)
    x += ew + gap + sw
    r = cap * 0.21
    m = skia.Path()
    m.moveTo(x, b); m.lineTo(x, t + r)
    m.arcTo(skia.Rect(x, t, x + 2 * r, t + 2 * r), 180, 180, False)
    m.lineTo(x + 2 * r, b)
    m.moveTo(x + 2 * r, t + r)
    m.arcTo(skia.Rect(x + 2 * r, t, x + 4 * r, t + 2 * r), 180, 180, False)
    m.lineTo(x + 4 * r, b)
    cv.drawPath(m, p)
    x += 4 * r + gap + sw
    ra = cap * 0.28
    a = skia.Path()
    a.moveTo(x, b); a.lineTo(x, t + ra)
    a.arcTo(skia.Rect(x, t, x + 2 * ra, t + 2 * ra), 180, 180, False)
    a.lineTo(x + 2 * ra, b)
    yb = t + (b - t) * 0.6
    a.moveTo(x, yb); a.lineTo(x + 2 * ra, yb)
    cv.drawPath(a, p)
    x += 2 * ra + gap + sw
    kw = cap * 0.48
    k = skia.Path()
    k.moveTo(x, t); k.lineTo(x, b)
    k.moveTo(x + kw, t); k.lineTo(x + sw * 0.4, (t + b) / 2); k.lineTo(x + kw, b)
    cv.drawPath(k, p)
    x += kw + gap + sw
    i = skia.Path()
    i.moveTo(x, t + cap * 0.2); i.lineTo(x, b)
    cv.drawPath(i, p)
    cv.drawCircle(x, base - cap - cap * 0.02, sw * 1.1, fill(dot_color))


def render(out_dir):
    surf = skia.Surface(W * S, H * S)
    cv = surf.getCanvas()
    cv.scale(S, S)
    background(cv)
    wordmark(cv, 114, 150, 60, 7.5, GOLD_LIGHT, SHU)
    text(cv, "Motion video, drawn entirely in code.", 113, 192, 19, WHITE, 0.82)
    text(cv, "A Claude skill", 1166, 128, 14, WHITE, 0.7, align="right")
    text(cv, "mp4 or After Effects", 1166, 150, 12, GREY, align="right", tracking=0.3)
    scroll_shadow(cv)
    paper(cv)
    cv.save()
    cv.clipRect(skia.Rect(PX0, PY0, PX1, PY1))
    painting(cv)
    seam(cv)
    timeline(cv)
    easing_graph(cv)
    motion_path(cv)
    cv.restore()
    rolls(cv)
    img = surf.makeImageSnapshot()
    os.makedirs(out_dir, exist_ok=True)
    small = img.resize(W, H, skia.SamplingOptions(skia.CubicResampler.Mitchell()))
    for im, name in ((img, "hero.jpg"), (small, "social-preview.jpg")):
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(bytes(im.encodeToData(skia.kJPEG, 92)))
    print("wrote", out_dir)


if __name__ == "__main__":
    render(sys.argv[1] if len(sys.argv) > 1 else ".")
