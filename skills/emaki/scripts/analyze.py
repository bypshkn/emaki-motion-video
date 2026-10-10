"""Motion analysis for reference videos and our own renders.

  python3 analyze.py <video> [--crop W:H:X:Y] [--out DIR] [--sheet-fps 2] [--detail a-b,c-d]

Writes contact sheets (overview + optional detail strips at 12 fps) and metrics.json:
  static_pct        share of frames with (almost) no change            -> design dynamics.static_max
  longest_still_s   longest run without movement                        -> dynamics.max_still
  hit_interval_s    median gap between visual hits (cuts, slams, flashes, big moves) -> dynamics.hit_interval
  cuts, shot_*      hard cuts and shot lengths
  energy_per_s      mean frame difference per second (the "pulse" of the edit)
  palette           dominant colours (median per second, plus overall top 6)
Measured at 15 fps on a 160 px downscale (grain is not motion; previews compare with finals).
  motion_density_pct  median share of pixels changing per frame (how much of the picture moves)
Crop to the part that matters when the video is a screen recording of something else.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height,codec_type",
                        "-of", "json", path], capture_output=True, text=True)
    j = json.loads(r.stdout)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    return float(j["format"]["duration"]), v["width"], v["height"]


def frames(path, fps, w, crop=None, gray=False, t0=None, dur=None):
    dur_, W, H = probe(path)
    if crop:
        cw, ch = int(crop[0]), int(crop[1])
    else:
        cw, ch = W, H
    h = int(round(w * ch / cw / 2) * 2)
    vf = (f"crop={crop[0]}:{crop[1]}:{crop[2]}:{crop[3]}," if crop else "") + f"fps={fps},scale={w}:{h}"
    cmd = ["ffmpeg", "-v", "error"]
    if t0 is not None:
        cmd += ["-ss", str(t0)]
    if dur is not None:
        cmd += ["-t", str(dur)]
    cmd += ["-i", path, "-vf", vf, "-f", "rawvideo", "-pix_fmt", "gray" if gray else "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    ch_ = 1 if gray else 3
    a = np.frombuffer(raw, np.uint8)
    n = len(a) // (w * h * ch_)
    return a[: n * w * h * ch_].reshape(n, h, w, ch_) if not gray else a[: n * w * h].reshape(n, h, w)


def metrics(path, crop=None, fps=15, skip=0.0, width=160):
    """Measured at 15 fps on a 160 px wide grey downscale (grain averages out, previews and
    finals compare fairly). A pixel 'changes' when it moves by > 0.03; a frame is dead when
    < 0.05% of pixels change. Short dead blips (< 0.33 s, e.g. between typed characters)
    are not counted as stillness."""
    g = frames(path, fps, width, crop, gray=True).astype(np.float32) / 255
    g = g[int(skip * fps):]
    d = np.abs(np.diff(g, axis=0))
    ch = (d > 0.03).mean(axis=(1, 2))             # changed fraction per frame
    dead = ch < 0.0005
    runs = []
    cur = 0
    for x in list(dead) + [False]:
        if x:
            cur += 1
        else:
            if cur:
                runs.append(cur)
            cur = 0
    min_run = int(round(0.33 * fps))
    static_frames = sum(r for r in runs if r >= min_run)
    longest = max(runs) if runs else 0
    # hits: frames where a large part of the picture changes at once (cut, slam, flash, whip, punch)
    hits = [i for i in range(1, len(ch) - 1) if ch[i] > 0.08 and ch[i] >= ch[i - 1] and ch[i] >= ch[i + 1]]
    hits = [h for k, h in enumerate(hits) if k == 0 or h - hits[k - 1] > 2]
    gaps = np.diff(hits) / fps if len(hits) > 1 else np.array([len(ch) / fps])
    mean = d.mean(axis=(1, 2))
    cuts = [i + 1 for i in range(len(mean)) if mean[i] > 0.12]
    cuts = [c for k, c in enumerate(cuts) if k == 0 or c - cuts[k - 1] > 2]
    shots = np.diff([0] + cuts + [len(g)]) / fps
    col = frames(path, 1, 48, crop).reshape(-1, 3) / 255.0
    q = (col * 7).round() / 7
    vals, counts = np.unique(q, axis=0, return_counts=True)
    top = vals[np.argsort(-counts)[:6]]
    return {
        "duration_s": round(len(g) / fps, 2),
        "static_pct": round(static_frames / max(1, len(ch)) * 100, 1),
        "longest_still_s": round(longest / fps, 2),
        "motion_density_pct": round(float(np.median(ch)) * 100, 2),
        "hits": len(hits),
        "hit_interval_s": round(float(np.median(gaps)), 2),
        "cuts": len(cuts),
        "cut_times": [round(c / fps + skip, 2) for c in cuts],
        "hit_times": [round(h / fps + skip, 2) for h in hits],
        "shot_median_s": round(float(np.median(shots)), 2),
        "shot_max_s": round(float(shots.max()), 2),
        "energy_per_s": [round(float(ch[i * fps:(i + 1) * fps].mean()) * 100, 2) for i in range(int(len(ch) / fps))],
        "palette_top": ["#%02x%02x%02x" % tuple((c * 255).astype(int)) for c in top],
    }


def _audio(path, sr=22050, skip=0.0):
    cmd = ["ffmpeg", "-v", "error", "-ss", str(skip), "-i", path, "-vn", "-ac", "1", "-ar", str(sr),
           "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True).stdout
    return np.frombuffer(raw, np.float32).copy()


def _onset_env(x, sr, n=1024, hop=256):
    """Log-magnitude spectral flux, half-wave rectified, one value per hop."""
    if len(x) < n * 2:
        return np.zeros(1), [], hop / sr
    win = np.hanning(n).astype(np.float32)
    m = 1 + (len(x) - n) // hop
    idx = np.arange(n)[None, :] + hop * np.arange(m)[:, None]
    S = np.abs(np.fft.rfft(x[idx] * win, axis=1))
    L = np.log1p(100 * S)
    flux = np.maximum(0, np.diff(L, axis=0)).sum(axis=1)
    flux = np.concatenate([[0], flux])
    flux -= np.convolve(flux, np.ones(16) / 16, "same")       # remove slow loudness drift
    flux = np.maximum(flux, 0)
    return flux / (flux.max() + 1e-9), S, hop / sr


def _peaks(env, dt, k=1.2, min_gap=0.08, floor=0.08):
    w = max(3, int(0.5 / dt))
    pad = np.pad(env, w, mode="edge")
    loc_mean = np.convolve(pad, np.ones(2 * w + 1) / (2 * w + 1), "valid")
    loc_std = np.sqrt(np.maximum(np.convolve(pad ** 2, np.ones(2 * w + 1) / (2 * w + 1), "valid") - loc_mean ** 2, 0))
    thr = np.maximum(loc_mean + k * loc_std, floor)
    out = []
    for i in range(1, len(env) - 1):
        if env[i] > thr[i] and env[i] >= env[i - 1] and env[i] >= env[i + 1]:
            if not out or (i - out[-1]) * dt >= min_gap:
                out.append(i)
            elif env[i] > env[out[-1]]:
                out[-1] = i
    return np.array(out) * dt


def _tempo_beats(env, dt):
    """Autocorrelation tempo (60-180 BPM, mild prior around 110) + dynamic-programming beats."""
    e = env - env.mean()
    ac = np.correlate(e, e, "full")[len(e) - 1:]
    lags = np.arange(len(ac)) * dt
    ok = (lags >= 60 / 180) & (lags <= 1.0)
    if not ok.any():
        return 0.0, np.array([])
    bpm_all = 60 / np.maximum(lags, 1e-9)
    prior = np.exp(-0.5 * (np.log2(bpm_all / 110) / 0.9) ** 2)
    score = np.where(ok, ac * prior, -np.inf)
    lag = int(np.argmax(score))
    bpm = 60 / (lag * dt)
    # DP beat tracker (Ellis 2007)
    period = lag
    cum = env.copy().astype(float)
    back = -np.ones(len(env), int)
    for i in range(len(env)):
        lo, hi = i - 2 * period, i - period // 2
        if hi <= 0:
            continue
        lo = max(lo, 0)
        cand = np.arange(lo, hi)
        pen = -2.0 * np.log((i - cand) / period) ** 2
        j = int(np.argmax(cum[cand] + pen))
        cum[i] = env[i] + cum[cand][j] + pen[j]
        back[i] = cand[j]
    i = int(np.argmax(cum[-period:])) + len(cum) - period
    beats = []
    while i >= 0:
        beats.append(i)
        i = back[i]
    return round(float(bpm), 1), np.array(beats[::-1]) * dt


def _visual_env(path, crop, skip, fps=30, width=120):
    g = frames(path, fps, width, crop, gray=True).astype(np.float32) / 255
    g = g[int(skip * fps):]
    ch = (np.abs(np.diff(g, axis=0)) > 0.03).mean(axis=(1, 2))
    on = np.maximum(0, np.diff(np.concatenate([[0], ch])))      # rise of change = a new visual event
    return on / (on.max() + 1e-9), 1 / fps


def audio_metrics(path, crop=None, skip=0.0):
    """How the soundtrack is built and how tightly the picture follows it.
      tempo_bpm, beats, onsets_per_s     pulse and density of sound events
      centroid_hz, low_pct, high_pct     brightness: where the energy sits (<150 Hz, >5 kHz)
      lufs                               integrated loudness of the source
      sync_hit_pct                       share of visual hits that land within 1 frame (33 ms) of a sound onset
      sync_beat_pct                      share of visual hits within 70 ms of a beat or half-beat
      av_lag_ms, av_corr                 best lag (picture minus sound) and correlation of the two event curves"""
    sr = 22050
    x = _audio(path, sr, skip)
    if len(x) < sr:
        return {"audio": False}
    env, S, dt = _onset_env(x, sr)
    on = _peaks(env, dt)
    bpm, beats = _tempo_beats(env, dt)
    freqs = np.fft.rfftfreq(1024, 1 / sr)
    P = (S ** 2).sum(axis=0)
    M = S.sum(axis=0)
    cen = float((freqs * M).sum() / (M.sum() + 1e-12))          # magnitude-weighted: closer to perceived brightness
    low = float(P[freqs < 150].sum() / P.sum() * 100)
    high = float(P[freqs > 5000].sum() / P.sum() * 100)
    edges = [(0, 60, "sub"), (60, 250, "bass"), (250, 2000, "mid"), (2000, 6000, "presence"), (6000, sr / 2, "air")]
    bands = {n: round(float(10 * np.log10(P[(freqs >= a) & (freqs < b)].sum() / P.sum() + 1e-12)), 1) for a, b, n in edges}
    try:
        from audio.master import ffmpeg_loudness
        ld = ffmpeg_loudness(path)
        loud, lra = ld.get("I"), ld.get("LRA")
    except Exception:
        loud = lra = None
    venv, vdt = _visual_env(path, crop, skip)
    vh = _peaks(venv, vdt, k=2.0, min_gap=0.15, floor=0.03)
    def near(ts, ref, tol):
        if len(ts) == 0 or len(ref) == 0:
            return 0.0
        return float(np.mean([np.min(np.abs(ref - t)) <= tol for t in ts]) * 100)
    grid = np.sort(np.concatenate([beats, (beats[:-1] + beats[1:]) / 2])) if len(beats) > 1 else beats
    # correlate event curves on a common 100 Hz grid
    T = min(len(env) * dt, len(venv) * vdt)
    tt = np.arange(0, T, 0.01)
    a = np.interp(tt, np.arange(len(env)) * dt, env)
    v = np.interp(tt, np.arange(len(venv)) * vdt, venv)
    a = (a - a.mean()) / (a.std() + 1e-9)
    v = (v - v.mean()) / (v.std() + 1e-9)
    best, lag = -1.0, 0
    for L in range(-25, 26):                                   # +-250 ms
        c = float(np.mean(a[max(0, -L):len(a) - max(0, L)] * v[max(0, L):len(v) - max(0, -L)]))
        if c > best:
            best, lag = c, L
    return {
        "audio": True,
        "tempo_bpm": bpm,
        "beat_s": round(60 / bpm, 3) if bpm else None,
        "onsets_per_s": round(len(on) / (len(x) / sr), 2),
        "centroid_hz": int(cen),
        "low_pct": round(low, 1),
        "high_pct": round(high, 1),
        "bands_db": bands,
        "lufs": loud,
        "lra": lra,
        "visual_hits": len(vh),
        "sync_hit_pct": round(near(vh, on, 0.034), 1),
        "sync_beat_pct": round(near(vh, grid, 0.07), 1),
        "av_lag_ms": lag * 10,
        "av_corr": round(best, 3),
        "onset_times": [round(float(t), 2) for t in on],
        "beat_times": [round(float(t), 2) for t in beats],
        "visual_hit_times": [round(float(t), 2) for t in vh],
    }


def spectrogram(path, out, skip=0.0, width=1400, height=260):
    """Log-frequency spectrogram (30 Hz - 11 kHz) with 60/250/2k/6k guide lines. Voice shows up as
    wavy stacked harmonics, pads as long horizontal lines, drums as vertical strokes, sub hits as
    bright blobs at the bottom."""
    from PIL import Image, ImageDraw
    sr = 22050
    x = _audio(path, sr, skip)
    if len(x) < 4096:
        return None
    n = 2048
    hop = max(64, len(x) // width)
    m = 1 + (len(x) - n) // hop
    S = np.empty((m, n // 2 + 1), np.float32)
    win = np.hanning(n).astype(np.float32)
    for i in range(0, m, 512):
        idx = np.arange(n)[None, :] + hop * np.arange(i, min(m, i + 512))[:, None]
        S[i:i + len(idx)] = np.abs(np.fft.rfft(x[idx] * win, axis=1))
    f = np.fft.rfftfreq(n, 1 / sr)
    edges = np.geomspace(30, 11000, height + 1)
    cols = []
    for i in range(height):
        sel = (f >= edges[i]) & (f < edges[i + 1])
        cols.append(S[:, sel].mean(axis=1) if sel.any() else S[:, int(np.argmin(np.abs(f - edges[i])))])
    D = 20 * np.log10(np.stack(cols, 1) + 1e-6)
    D = np.clip((D - D.max() + 70) / 70, 0, 1)
    im = Image.fromarray((D.T[::-1] * 255).astype(np.uint8)).resize((width, height)).convert("RGB")
    d = ImageDraw.Draw(im)
    for hz in (60, 250, 2000, 6000):
        y = int(height - np.log(hz / 30) / np.log(11000 / 30) * height)
        d.line([(0, y), (14, y)], fill=(255, 80, 80), width=2)
        d.text((18, y - 6), f"{hz} Hz", fill=(255, 120, 120))
    dur = len(x) / sr
    for s in range(0, int(dur) + 1):
        xx = int(s / dur * width)
        d.line([(xx, height - 6), (xx, height)], fill=(255, 80, 80))
        if s % 5 == 0:
            d.text((xx + 2, height - 18), f"{s}s", fill=(255, 120, 120))
    im.save(out)
    return out


def timed_sheets(path, out_prefix, crop=None, fps=4.0, tile_w=200, cols=6, per=24, skip=0.0):
    """Analysis sheets with a timestamp on every tile (default 4 fps = one tile per 0.25 s)."""
    from PIL import Image, ImageDraw
    fr = frames(path, fps, tile_w, crop)
    k0 = int(skip * fps)
    fr = fr[k0:]
    th = fr.shape[1] if len(fr) else 0
    outs = []
    for s in range(0, len(fr), per):
        chunk = fr[s:s + per]
        rows = (len(chunk) + cols - 1) // cols
        sh = Image.new("RGB", (cols * (tile_w + 4), rows * (th + 4)), (200, 0, 0))
        for i, f in enumerate(chunk):
            im = Image.fromarray(f)
            d = ImageDraw.Draw(im)
            d.rectangle([0, 0, 46, 13], fill=(200, 0, 0))
            d.text((3, 1), f"{(s + i + k0) / fps:.2f}", fill="white")
            sh.paste(im, ((i % cols) * (tile_w + 4), (i // cols) * (th + 4)))
        p = f"{out_prefix}_{len(outs) + 1:02d}.png"
        sh.save(p)
        outs.append(p)
    return outs


def sheets(path, out_dir, crop=None, fps=2.0, detail=None):
    from engine.contact import sheet
    os.makedirs(out_dir, exist_ok=True)
    _, W, H = probe(path)
    cw = int(crop[0]) if crop else W
    ch = int(crop[1]) if crop else H
    tw = 360 if cw >= ch else 220
    fr = frames(path, fps, tw, crop)
    res = sheet([(i / fps + 0.5 / fps, f) for i, f in enumerate(fr)], os.path.join(out_dir, "overview.png"),
                cols=5 if cw >= ch else 8, per_sheet=35 if cw >= ch else 32, title=f"{os.path.basename(path)} @ {fps:g} fps")
    for span in detail or []:
        a, b = (float(x) for x in span.split("-"))
        f2 = frames(path, 12, tw, crop, t0=a, dur=b - a)
        res += sheet([(a + i / 12, f) for i, f in enumerate(f2)], os.path.join(out_dir, f"detail_{a:g}-{b:g}.png"),
                     cols=6, per_sheet=24, title=f"{a:g}-{b:g}s @ 12 fps")
    return res


def compare(m, target):
    """Plain-language comparison of our metrics against a reference/target dict."""
    rows = []
    for k, label in (("static_pct", "static frames, %"), ("longest_still_s", "longest still, s"),
                     ("hit_interval_s", "median gap between hits, s"), ("shot_median_s", "median shot, s")):
        if k in m and k in target:
            rows.append(f"{label:30s} ours {m[k]:>6}   reference {target[k]:>6}")
    return "\n".join(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--crop", help="W:H:X:Y (ffmpeg crop)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--sheet-fps", type=float, default=2.0)
    ap.add_argument("--detail", default="", help="comma list of a-b spans for 12 fps strips")
    ap.add_argument("--skip", type=float, default=0.0, help="seconds to ignore at the start (intro of a screen recording)")
    ap.add_argument("--no-sheets", action="store_true")
    ap.add_argument("--no-audio", action="store_true")
    a = ap.parse_args()
    crop = a.crop.split(":") if a.crop else None
    out = a.out or os.path.splitext(a.video)[0] + "_analysis"
    m = metrics(a.video, crop, skip=a.skip)
    if not a.no_audio:
        m["sound"] = audio_metrics(a.video, crop, a.skip)
    os.makedirs(out, exist_ok=True)
    json.dump(m, open(os.path.join(out, "metrics.json"), "w"), indent=1)
    if not a.no_sheets:
        paths = sheets(a.video, out, crop, a.sheet_fps, [s for s in a.detail.split(",") if s])
        m["sheets"] = paths
    short = {k: v for k, v in m.items() if k not in ("energy_per_s", "cut_times", "hit_times")}
    if "sound" in m:
        short["sound"] = {k: v for k, v in m["sound"].items() if not k.endswith("_times")}
    print(json.dumps(short, indent=1, ensure_ascii=False))
