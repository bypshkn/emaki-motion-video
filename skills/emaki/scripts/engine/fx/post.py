"""Global post effects, applied at OUTPUT resolution after supersample downscale (so grain
and scanlines stay crisp). Lengths are given at 1080 px short side and scale with output.

Enable in design.yaml -> fx.enabled, e.g.
  fx:
    enabled:
      grain: {amount: 0.02}
      glitch: {track_only: true, split: 14, slices: 4}
Intensity tracks (Project.fx_track / Project.pulse) multiply an effect over time; with
`track_only: true` the effect is active only where its track is > 0.
"""
import math

import numpy as np
from scipy import ndimage

ORDER = ["grade", "bloom", "chroma", "glitch", "vignette", "scanlines", "grain"]
_cache = {}


def _k(img):
    return min(img.shape[0], img.shape[1]) / 1080.0


def grade(img, p, amt, ctx):
    c = p.get("contrast", 1.0)
    s = p.get("saturation", 1.0)
    lift, gamma, gain = p.get("lift", 0.0), p.get("gamma", 1.0), p.get("gain", 1.0)
    temp = p.get("temperature", 0.0)  # -1 cool .. +1 warm
    out = img * gain + lift * (1 - img)
    out = np.clip(out, 0, 1) ** (1.0 / max(1e-3, gamma))
    if c != 1.0:
        out = (out - 0.5) * c + 0.5
    if s != 1.0:
        lum = (out @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
        out = lum + (out - lum) * s
    if temp:
        out = out * np.array([1 + 0.08 * temp, 1.0, 1 - 0.08 * temp], np.float32)
    return img + (out - img) * amt


def bloom(img, p, amt, ctx):
    th = p.get("threshold", 0.72)
    inten = p.get("intensity", 0.6) * amt
    rad = p.get("radius", 0.025)
    lum = img @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    m = np.clip((lum - th) / max(1e-3, 1 - th), 0, 1)[..., None]
    bright = img * m
    h, w = img.shape[:2]
    f = 4
    hh, ww = h // f * f, w // f * f
    small = bright[:hh, :ww].reshape(hh // f, f, ww // f, f, 3).mean((1, 3))
    sig = rad * min(h, w) / f
    acc = np.zeros_like(small)
    for k, wt in ((0.5, 0.5), (1.0, 0.35), (2.0, 0.15)):
        acc += wt * ndimage.gaussian_filter(small, (sig * k, sig * k, 0))
    up = ndimage.zoom(acc, (h / acc.shape[0], w / acc.shape[1], 1), order=1)[:h, :w]
    if up.shape[:2] != (h, w):
        up = np.pad(up, ((0, h - up.shape[0]), (0, w - up.shape[1]), (0, 0)), mode="edge")
    return img + up * inten


def chroma(img, p, amt, ctx):
    """Radial chromatic aberration: R scaled out, B scaled in. amount = px at frame edge."""
    a = p.get("amount", 3.0) * _k(img) * amt
    if a < 0.2:
        return img
    h, w = img.shape[:2]
    out = img.copy()
    for ch, sgn in ((0, 1), (2, -1)):
        s = 1 + sgn * a / (w / 2)
        out[..., ch] = ndimage.affine_transform(img[..., ch], [1 / s, 1 / s],
                                                offset=[(h / 2) * (1 - 1 / s), (w / 2) * (1 - 1 / s)],
                                                order=1, mode="nearest")
    return out


def glitch(img, p, amt, ctx):
    """RGB split + displaced horizontal slices. Deterministic per frame."""
    if amt <= 0.001:
        return img
    k = _k(img)
    h, w = img.shape[:2]
    out = img.copy()
    s = int(round(p.get("split", 14) * k * amt))
    if s:
        lum = img.max(axis=2)
        # split only bright content (text, lines), so dark backgrounds don't get tinted
        th = p.get("split_threshold", 0.12)
        lum = np.where(lum > th, lum, 0.0)
        out[..., 0] = np.maximum(out[..., 0], np.roll(lum, s, axis=1) * p.get("split_mix", 1.0))
        out[..., 2] = np.maximum(out[..., 2], np.roll(lum, -s, axis=1) * p.get("split_mix", 1.0))
    if amt > p.get("slice_threshold", 0.3):
        rng = np.random.default_rng(ctx.project.seed * 1000003 + ctx.frame_key)
        y0r, y1r = p.get("region", (0.0, 1.0))
        n = p.get("slices", 4)
        hmin, hmax = p.get("slice_h", (6, 33))
        smax = p.get("slice_shift", 60)
        for _ in range(n):
            y0 = int(rng.integers(int(h * y0r), max(int(h * y0r) + 1, int(h * y1r))))
            hgt = int(rng.integers(max(1, int(hmin * k)), max(2, int(hmax * k))))
            sh = int(rng.integers(-int(smax * k), int(smax * k) + 1))
            out[y0:y0 + hgt] = np.roll(out[y0:y0 + hgt], sh, axis=1)
    return out


def vignette(img, p, amt, ctx):
    h, w = img.shape[:2]
    key = ("vig", h, w, p.get("softness", 0.6), p.get("roundness", 1.0))
    m = _cache.get(key)
    if m is None:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        nx, ny = (xx / w - 0.5) * 2, (yy / h - 0.5) * 2
        if p.get("roundness", 1.0) >= 1.0:
            nx *= w / max(w, h)
            ny *= h / max(w, h)
        d = np.sqrt(nx ** 2 + ny ** 2) / math.sqrt(2)
        soft = p.get("softness", 0.6)
        m = np.clip((d - (1 - soft)) / soft, 0, 1) ** 2
        _cache[key] = m.astype(np.float32)
    st = p.get("strength", 0.35) * amt
    return img * (1 - st * m)[..., None]


def scanlines(img, p, amt, ctx):
    """Darken every `period`-th row (period in px at 1080 short side)."""
    h = img.shape[0]
    period = p.get("period", 4.5) * _k(img)
    dark = p.get("strength", 0.18) * amt
    rows = (np.floor(np.arange(h) / period * 1.0) != np.floor((np.arange(h) + 1) / period)).astype(np.float32)
    return img * (1 - dark * rows)[:, None, None]


def grain(img, p, amt, ctx):
    a = p.get("amount", 0.02) * amt
    if a <= 0:
        return img
    h, w = img.shape[:2]
    rng = np.random.default_rng(ctx.project.seed * 7919 + ctx.frame_key)
    size = max(1.0, p.get("size", 1.0) * _k(img))
    if size > 1.2:
        sh, sw = int(h / size) + 1, int(w / size) + 1
        n = rng.normal(0, 1, (sh, sw)).astype(np.float32)
        n = ndimage.zoom(n, (h / sh, w / sw), order=1)[:h, :w]
    else:
        n = rng.normal(0, 1, (h, w)).astype(np.float32)
    if p.get("luma_weighted", False):
        lum = img @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        n = n * (0.5 + 2 * lum * (1 - lum))
    return img + a * n[..., None]


FX = {"grade": grade, "bloom": bloom, "chroma": chroma, "glitch": glitch, "vignette": vignette,
      "scanlines": scanlines, "grain": grain}


def apply(img_u8, t, ctx, post, tracks):
    """img_u8: HxWx3 uint8 -> HxWx3 uint8."""
    active = [n for n in ORDER if n in post]
    if not active:
        return img_u8
    img = img_u8.astype(np.float32) / 255.0
    for name in active:
        p = post[name] or {}
        amt = p.get("mix", 1.0)
        if name in tracks:
            tv = tracks[name].at(t)
            amt = tv if p.get("track_only") else amt * (1 + tv)
        elif p.get("track_only"):
            amt = 0.0
        if amt <= 1e-4:
            continue
        img = FX[name](img, p, amt, ctx)
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
