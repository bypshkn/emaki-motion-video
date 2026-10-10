"""Renderer: supersampling, motion blur by subframe accumulation, global post fx,
multiprocessing (fork) and ffmpeg via stdin. Also stills, contact sheets, timing and
final-render time estimates.
"""
import importlib.util
import json
import math
import multiprocessing as mp
import os
import subprocess
import sys
import time

import numpy as np

from .core import Ctx, CURRENT, skia
from .fx import post as POST
from . import fonts as F

_G = {}


# ----------------------------------------------------------------------------- loading

def _brief_language(root):
    """`language` from the project's brief.yaml; English when there is no brief."""
    p = os.path.join(root, "brief.yaml")
    if not os.path.exists(p):
        return "en"
    try:
        import yaml
        return (yaml.safe_load(open(p, encoding="utf-8")) or {}).get("language") or "en"
    except Exception:
        return "en"


def load_project(video_py, **build_kw):
    """Import video.py (must define build(**kw) -> Project) from a project folder."""
    video_py = os.path.abspath(video_py)
    root = os.path.dirname(video_py)
    F.set_project_dir(root)
    F.set_language(_brief_language(root))
    if root not in sys.path:
        sys.path.insert(0, root)
    spec = importlib.util.spec_from_file_location("mv_video", video_py)
    mod = importlib.util.module_from_spec(spec)
    cwd = os.getcwd()
    os.chdir(root)
    try:
        spec.loader.exec_module(mod)
        P = mod.build(**build_kw)
    finally:
        os.chdir(cwd)
    P.root = root
    P.video_py = video_py
    return P


# ----------------------------------------------------------------------------- frames

def out_size(P, scale):
    W = int(round(P.W * scale / 2)) * 2
    H = int(round(P.H * scale / 2)) * 2
    return W, H


def _mb_settings(P, t):
    for s in P.active_scenes(t):
        if s.motion_blur:
            return s.motion_blur
    if P.motion_blur:
        return P.motion_blur
    return _auto_blur(P, t)


def _auto_blur(P, t, shutter_deg=180.0, px_per_sample=5.0, max_samples=10):
    """Real motion blur only where the camera moves fast (travel, whip-like moves): the
    number of sub-frames grows with the on-screen displacement during the shutter, so held
    shots cost nothing extra. Off with P.auto_blur = False."""
    if not getattr(P, "auto_blur", True):
        return None
    dt = shutter_deg / 360.0 / P.fps
    disp = 0.0
    for s in P.active_scenes(t):
        cam = s.camera
        if cam.active:
            disp = max(disp, cam.speed_px(t - s.t0, dt))
    if disp < 2 * px_per_sample:
        return None
    return {"samples": int(min(max_samples, max(3, math.ceil(disp / px_per_sample) + 1))), "shutter": shutter_deg,
            "auto": True}


def raw_frame(P, t, scale=1.0, ss=2, hidden=None, preview=False):
    """Render one frame without post fx -> float32 HxWx3 (0..1) at output size."""
    W, H = out_size(P, scale)
    sw, sh = W * ss, H * ss
    key = ("surf", sw, sh)
    surf = P._cache.get(key)
    if surf is None:
        surf = skia.Surface(sw, sh)
        P._cache[key] = surf
    c = surf.getCanvas()
    c.resetMatrix()
    c.clear(skia.ColorBLACK)
    c.save()
    c.scale(sw / P.W, sh / P.H)
    ctx = Ctx(P, px=sw / P.W, frame=int(round(t * P.fps)), t_abs=t, preview=preview, hidden=hidden)
    P.draw(c, t, ctx)
    c.restore()
    snap = surf.makeImageSnapshot()
    if ss == 2:
        # 2x -> 1x in skia: bilinear sampling at the centre of every 2x2 block is exactly the box
        # filter, ~15x faster than summing in numpy (0.26 s -> 0.02 s per 1080p frame)
        dkey = ("down", W, H)
        dst = P._cache.get(dkey)
        if dst is None:
            dst = skia.Surface(W, H)
            P._cache[dkey] = dst
        dc = dst.getCanvas()
        dc.clear(skia.ColorBLACK)
        dc.drawImageRect(snap, skia.Rect.MakeWH(W, H), skia.SamplingOptions(skia.FilterMode.kLinear))
        arr = dst.makeImageSnapshot().toarray(colorType=skia.ColorType.kRGBA_8888_ColorType)
        return arr[..., :3].astype(np.float32) * (1.0 / 255.0)
    arr = snap.toarray(colorType=skia.ColorType.kRGBA_8888_ColorType)
    if ss > 1:
        # box filter in integer space (smaller peak memory than float32 at 4K)
        acc = arr.reshape(H, ss, W, ss, 4)[..., :3].sum(axis=(1, 3), dtype=np.uint16)
        return acc.astype(np.float32) * (1.0 / (255.0 * ss * ss))
    return arr[..., :3].astype(np.float32) * (1.0 / 255.0)


def _camera_pan_px(P, t, dt, scale):
    """Screen-space pan of the active camera over dt (px at output scale)."""
    best = (0.0, 0.0)
    for s in P.active_scenes(t):
        cam = s.camera
        if cam.active:
            a, b = t - s.t0 - dt / 2, t - s.t0 + dt / 2
            (xa, ya), (xb, yb) = cam.pos.at(a), cam.pos.at(b)
            z = (cam.zoom.at(a) + cam.zoom.at(b)) / 2
            d = (-(xb - xa) * z * scale, -(yb - ya) * z * scale)
            if abs(d[0]) + abs(d[1]) > abs(best[0]) + abs(best[1]):
                best = d
    return best


def frame(P, t, scale=1.0, ss=2, hidden=None, preview=False, post=True):
    """Final pixels for time t: uint8 HxWx3."""
    mb = _mb_settings(P, t)
    if mb and mb.get("samples", 0) > 1:
        n = int(mb["samples"])
        shutter = mb.get("shutter", 180) / 360.0 / P.fps
        # on camera travel (automatic blur) the sub-frames already average many positions of
        # every edge, so they skip supersampling (P.mb_ss, default 1): n x 1 instead of n x 4.
        # Blur forced on a scene keeps full supersampling (static mattes would show seams).
        sub_ss = min(ss, int(getattr(P, "mb_ss", 1) or 1)) if mb.get("auto") else ss
        acc = None
        for i in range(n):
            ti = t + (i / (n - 1) - 0.5) * shutter
            f = raw_frame(P, ti, scale, sub_ss, hidden, preview)
            acc = f if acc is None else acc + f
        img = acc / n
        # bridge the gaps between sub-frames on fast camera pans (otherwise the streak shows as
        # a comb of ghost copies): box blur along the pan, one sample spacing long
        dx, dy = _camera_pan_px(P, t, shutter, scale)
        gx, gy = abs(dx) / (n - 1), abs(dy) / (n - 1)
        if max(gx, gy) > 2.5:
            from scipy.ndimage import uniform_filter1d
            if gx > 2.5:
                img = uniform_filter1d(img, size=int(gx) + 1, axis=1, mode="nearest")
            if gy > 2.5:
                img = uniform_filter1d(img, size=int(gy) + 1, axis=0, mode="nearest")
    else:
        img = raw_frame(P, t, scale, ss, hidden, preview)
    u8 = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
    if post and P.post:
        ctx = Ctx(P, px=1.0, frame=int(round(t * P.fps)), t_abs=t, preview=preview)
        ctx.frame_key = int(round(t * 120))
        u8 = POST.apply(u8, t, ctx, P.post, P.fx_tracks)
    return u8


# ----------------------------------------------------------------------------- workers

def _work(args):
    i, t = args
    P = _G["P"]
    t0 = time.perf_counter()
    img = frame(P, t, _G["scale"], _G["ss"], preview=_G["preview"])
    return i, img.tobytes(), time.perf_counter() - t0


def _pool(P, scale, ss, preview, workers):
    _G.update(P=P, scale=scale, ss=ss, preview=preview)
    ctx = mp.get_context("fork")
    return ctx.Pool(workers)


def ffmpeg_cmd(out, W, H, fps, audio=None, codec="h264", quality="final", alpha=False):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba" if alpha else "rgb24",
           "-s", f"{W}x{H}", "-r", str(fps), "-i", "-"]
    if audio:
        cmd += ["-i", audio]
    if codec == "h264":
        crf = "18" if quality == "final" else "23"
        preset = "medium" if quality == "final" else "veryfast"
        rate = []
        if quality == "final":
            # cap the bitrate: grain at CRF 17 alone can reach 80+ Mbit/s, too heavy to send
            mbps = max(8, int(20 * W * H / (1920 * 1080)))
            rate = ["-maxrate", f"{mbps}M", "-bufsize", f"{mbps}M"]
        cmd += ["-vf", "scale=out_color_matrix=bt709:out_range=tv", "-c:v", "libx264", "-preset", preset,
                "-crf", crf] + rate + ["-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
                "-color_trc", "bt709", "-movflags", "+faststart"]
    elif codec == "vp9":
        cmd += ["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30", "-row-mt", "1", "-pix_fmt", "yuv420p"]
    elif codec == "prores4444":
        cmd += ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le" if alpha else "yuv444p10le"]
    if audio:
        cmd += ["-c:a", "aac" if codec == "h264" else ("libopus" if codec == "vp9" else "pcm_s24le"),
                "-b:a", "256k", "-shortest"] if codec != "prores4444" else ["-c:a", "pcm_s24le"]
    cmd += [out]
    return cmd


def render_video(P, out, scale=1.0, fps=None, ss=2, audio=None, workers=None, preview=False,
                 codec="h264", t_range=None, log=None, sample_times=None):
    """Render to a video file. Returns timing stats dict. `sample_times` renders only those
    times (used by the estimator to time the real pipeline: workers + encoder)."""
    fps = fps or P.fps
    W, H = out_size(P, scale)
    t0, t1 = t_range or (0.0, P.duration)
    if sample_times is not None:
        times = list(enumerate(sample_times))
        n = len(times)
    else:
        n = int(round((t1 - t0) * fps))
        times = [(i, t0 + i / fps) for i in range(n)]
    workers = workers or max(1, min(os.cpu_count() or 2, 8))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    cmd = ffmpeg_cmd(out, W, H, fps, audio, codec, "preview" if preview else "final")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    per = []
    start = time.perf_counter()
    from collections import deque
    # bounded in-flight frames: if the encoder is slower than the renderers, finished frames
    # must not pile up in memory (a 1080p frame is 6 MB; an unbounded queue gets OOM-killed)
    max_inflight = workers * 2
    with _pool(P, scale, ss, preview, workers) as pool:
        it = iter(times)
        pending = deque()

        def submit():
            nxt = next(it, None)
            if nxt is not None:
                pending.append(pool.apply_async(_work, (nxt,)))
        for _ in range(max_inflight):
            submit()
        while pending:
            i, data, dt = pending.popleft().get()
            proc.stdin.write(data)
            per.append(dt)
            submit()
            if log and (i % max(1, n // 10) == 0):
                el = time.perf_counter() - start
                log(f"  frame {i + 1}/{n}  {el:5.1f}s elapsed, ~{el / (i + 1) * (n - i - 1):5.1f}s left")
    proc.stdin.close()
    rc = proc.wait()
    wall = time.perf_counter() - start
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed ({rc}): {' '.join(cmd)}")
    stats = {"out": out, "frames": n, "fps": fps, "size": [W, H], "ss": ss, "workers": workers,
             "wall_s": round(wall, 2), "frame_avg_s": round(float(np.mean(per)), 4) if per else 0,
             "frame_p95_s": round(float(np.percentile(per, 95)), 4) if per else 0,
             "slowest_t": round(times[int(np.argmax(per))][1], 2) if per else 0}
    return stats


# ----------------------------------------------------------------------------- fingerprints

def fingerprint(P, t, scale=0.25):
    """Cheap identity of the picture at time t: a quarter-size raster (a 1 px change in the
    final still moves anti-aliased edges here), the motion-blur sample count, and the post fx
    settings with their track values. Used to skip re-rendering chunks whose frames did not
    change after an edit (~6 ms per frame)."""
    import hashlib
    h = hashlib.sha1()
    img = raw_frame(P, t, scale, 1)
    h.update((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
    mb = _mb_settings(P, t)
    h.update(repr((mb or {}).get("samples", 1)).encode())
    if P.post:
        h.update(repr(sorted((k, sorted((v or {}).items())) for k, v in P.post.items())).encode())
        h.update(repr([(k, round(float(p.at(t)), 5)) for k, p in sorted(P.fx_tracks.items())]).encode())
    return h.hexdigest()[:16]


def _fp_work(args):
    i, t = args
    return i, fingerprint(_G["P"], t, _G["scale"])


def fingerprints(P, times, scale=0.25, workers=None):
    """Fingerprints for many times, in parallel. Returns a list in the order of `times`."""
    workers = workers or max(1, min(os.cpu_count() or 2, 8))
    _G.update(P=P, scale=scale, ss=1, preview=False)
    out = [None] * len(times)
    with _pool(P, scale, 1, False, workers) as pool:
        for i, h in pool.imap_unordered(_fp_work, list(enumerate(times)), chunksize=16):
            out[i] = h
    return out


def render_stills(P, ts, scale=0.5, ss=2, workers=None, post=True):
    workers = workers or max(1, min(os.cpu_count() or 2, 8))
    _G.update(P=P, scale=scale, ss=ss, preview=True)
    if len(ts) <= 2:
        return [frame(P, t, scale, ss, preview=True, post=post) for t in ts]
    W, H = out_size(P, scale)
    with _pool(P, scale, ss, True, workers) as pool:
        res = list(pool.imap(_work, list(enumerate(ts)), chunksize=1))
    return [np.frombuffer(d, np.uint8).reshape(H, W, 3) for _, d, _ in res]


def estimate_final(P, scale=1.0, fps=None, ss=2, samples=None, workers=None):
    """Time a sample of frames through the real pipeline (worker pool + encoder) at final
    settings, spread over the whole timeline, and extrapolate to the full render."""
    import tempfile
    fps = fps or P.fps
    n = int(round(P.duration * fps))
    workers = workers or max(1, min(os.cpu_count() or 2, 8))
    k = samples or min(n, max(24, workers * 6))
    ts = [P.duration * (j + 0.5) / k for j in range(k)]
    with tempfile.TemporaryDirectory() as d:
        st = render_video(P, os.path.join(d, "est.mp4"), scale=scale, fps=fps, ss=ss, workers=workers,
                          sample_times=ts)
    per = st["wall_s"] / k
    return {"frames": n, "sample_frames": k, "wall_per_frame_s": round(per, 3), "workers": workers,
            "estimate_s": round(per * n * 1.05, 1)}
