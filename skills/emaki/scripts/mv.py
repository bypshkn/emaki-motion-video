#!/usr/bin/env python3
"""Emaki CLI (mv.py, "motion video").

  mv.py init <dir> [--style NAME] [--aspect 9:16] [--duration 20] [--fps 30]
  mv.py storyboard <dir> [--times 0.5,2.0,...] [--scale 0.3]
  mv.py preview <dir> [--no-audio] [--ss 1] [--estimate]  half res, 15 fps, no supersampling, contact sheets, QA
  mv.py final <dir> [--fps 60] [--webm-loop] [--no-qa]
  mv.py styleframes <dir> [--times a,b] [--ref ID]  gate 1: key moments at final quality, PNGs + sheet
  mv.py still <dir> <t> [--scale 1.0]
  mv.py timeline <dir>                        choreography map: entrances, later actions, holds, camera
  mv.py strips <dir> [--at a,b] [--ref ID]    12 fps strips around the keyframes
  mv.py contact <dir> [--every 0.5] [--scale 0.5]
  mv.py qa <dir> [--video out/preview.mp4] [--final]
  mv.py estimate <dir>
  mv.py ae <dir> [--version 24.0]             After Effects ExtendScript project + stems
  mv.py [--lib DIR] styles                    list library styles
  mv.py [--lib DIR] save-style <dir> <name>   save an approved design.yaml as a library style
  mv.py [--lib DIR] promote <dir> <module.py> keep a project engine_ext module for future videos
  mv.py voice <dir> [--cues f.srt] [--force]  word timings of the voice-over -> data/words.json
  mv.py beats <music file>                    tempo + first beat of the user's track
  mv.py analyze-ref <video> [--crop W:H:X:Y] [--skip s] [--detail a-b,c-d] [--id NAME]
                                              reference metrics (motion + sound) + sheets; --id files it in motion-lib

Project layout: brief.yaml, design.yaml, storyboard.md, video.py (build() -> Project),
fonts/, assets/, data/, engine_ext/, out/.
User library (styles + engine extensions that proved useful): --lib / $MV_LIB, otherwise the
first `motion-lib/` found walking up from the project folder. The walk stops at the home folder;
for a project outside home it goes at most two levels up. Every command logs the library it used.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import time

# Frames render in parallel processes (one per core). Multi-threaded BLAS inside each of them
# oversubscribes the cores: measured 1.65x slower finals. One BLAS thread per process.
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, HERE)


def log(msg):
    print(msg, flush=True)


LIB_MAX_UP_OUTSIDE_HOME = 2   # <root>/motion-lib next to <root>/projects/<video>


def find_lib(start, explicit=None):
    """The user library: --lib, then $MV_LIB, then the first `motion-lib/` walking up from `start`.
    The walk never leaves the home folder (it checks home itself last). For a project outside home
    it checks only the project folder and two levels above it. The library's engine_ext/*.py runs
    on every command, so the walk must not pick up a folder the user does not own."""
    if explicit:
        return os.path.abspath(explicit)
    if os.environ.get("MV_LIB"):
        return os.path.abspath(os.environ["MV_LIB"])
    d = os.path.realpath(start)
    home = os.path.realpath(os.path.expanduser("~"))
    inside_home = d == home or d.startswith(home.rstrip(os.sep) + os.sep)
    up = 0
    while True:
        cand = os.path.join(d, "motion-lib")
        if os.path.isdir(cand):
            return cand
        nd = os.path.dirname(d)
        if nd == d or d == home or (not inside_home and up >= LIB_MAX_UP_OUTSIDE_HOME):
            return None
        d = nd
        up += 1


def style_dirs(lib):
    dirs = [os.path.join(SKILL, "references", "styles")]
    if lib and os.path.isdir(os.path.join(lib, "styles")):
        dirs.append(os.path.join(lib, "styles"))
    return dirs


def load(dirp, lib=None):
    from engine import load_extensions, fonts
    from engine.render import load_project
    lib = find_lib(dirp, lib)
    if lib:
        log(f"[lib] user library: {lib}")
    for base in (lib, dirp):
        if base and os.path.isdir(os.path.join(base, "engine_ext")):
            sys.path.insert(0, os.path.join(base, "engine_ext"))   # `from my_layer import X` in video.py
            mods = load_extensions(base)
            if mods:
                names = ", ".join(os.path.basename(m.__file__) for m in mods)
                log(f"[lib] engine_ext loaded from {os.path.join(base, 'engine_ext')}: {names}")
    if lib and os.path.isdir(os.path.join(lib, "fonts")):
        fonts.PROJECT_FONT_DIRS.append(os.path.join(lib, "fonts"))
    return load_project(os.path.join(dirp, "video.py"))


def timing_log(dirp, entry):
    p = os.path.join(dirp, "out", "render_log.json")
    data = []
    if os.path.exists(p):
        try:
            data = json.load(open(p))
        except Exception:
            data = []
    entry["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data.append(entry)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(data, open(p, "w"), indent=1)


# ----------------------------------------------------------------------------- commands

def cmd_init(a):
    d = os.path.abspath(a.dir)
    for sub in ("fonts", "assets", "data", "engine_ext", "out"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    tpl = os.path.join(SKILL, "assets", "templates")
    if not os.path.exists(os.path.join(d, "brief.yaml")):
        s = open(os.path.join(tpl, "brief.yaml"), encoding="utf-8").read()
        s = s.replace("__ASPECT__", a.aspect).replace("__DURATION__", str(a.duration))
        open(os.path.join(d, "brief.yaml"), "w", encoding="utf-8").write(s)
    if not os.path.exists(os.path.join(d, "design.yaml")):
        src = os.path.join(tpl, "design.yaml")
        if a.style:
            for sd in style_dirs(find_lib(d, a.lib)):
                cand = os.path.join(sd, a.style, "design.yaml")
                if os.path.exists(cand):
                    src = cand
        s = open(src, encoding="utf-8").read()
        import re
        s = re.sub(r'aspect:\s*"[^"]*"', f'aspect: "{a.aspect}"', s, 1)
        s = re.sub(r"duration:\s*[\d.]+", f"duration: {a.duration}", s, 1)
        s = re.sub(r"fps:\s*\d+", f"fps: {a.fps}", s, 1)
        open(os.path.join(d, "design.yaml"), "w", encoding="utf-8").write(s)
    for f in ("video.py", "storyboard.md"):
        if not os.path.exists(os.path.join(d, f)):
            txt = open(os.path.join(tpl, f), encoding="utf-8").read()
            txt = txt.replace("__ASPECT__", a.aspect).replace("__DURATION__", f"{a.duration:g}").replace("__FPS__", str(a.fps))
            try:
                import yaml
                snd = (yaml.safe_load(open(os.path.join(d, "design.yaml"), encoding="utf-8")) or {}).get("sound") or {}
                bpm = float(snd.get("bpm", 100))
                txt = txt.replace("__BPM__", f"{bpm:g}").replace("__BAR__", f"{240 / bpm:.2f}")
                txt = txt.replace("__BARS__", str(max(1, int(round(a.duration / (240 / bpm))))))
            except Exception:
                pass
            txt = txt.replace("__BARS__", "8")
            open(os.path.join(d, f), "w", encoding="utf-8").write(txt)
    log(f"[init] {d}")
    lib = find_lib(d, a.lib)
    log(f"[init] user library: {lib or 'none (optional: a motion-lib/ folder above the project keeps styles and references)'}")


def scene_table(P):
    rows = ["| # | Scene | Time | Energy | Transition in | Sound events | Notes |", "|---|---|---|---|---|---|---|"]
    ev = P.all_events()
    for i, s in enumerate(P.scenes):
        se = [e for e in ev if s.t0 <= e.t < s.t1 and e.source != "auto"]
        kinds = {}
        for e in se:
            kinds[e.kind] = kinds.get(e.kind, 0) + 1
        auto = len([e for e in ev if s.t0 <= e.t < s.t1 and e.source == "auto"])
        evs = ", ".join(f"{k}x{v}" if v > 1 else k for k, v in kinds.items())
        if auto:
            evs += f"{', ' if evs else ''}auto x{auto}"
        tr = s.transition.kind if s.transition else "cut"
        rows.append(f"| {i + 1} | {s.name} | {s.t0:.2f}–{s.t1:.2f} | {s.energy:.1f} | {tr} | {evs} | {s.notes} |")
    return "\n".join(rows)


def cmd_storyboard(a):
    from engine.render import render_stills
    from engine.contact import sheet
    P = load(a.dir, a.lib)
    if a.times:
        ts = [float(x) for x in a.times.split(",")]
        caps = ["" for _ in ts]
    else:
        ts, caps = [], []
        kf = getattr(P, "keyframes", None)
        if kf:
            for t, cap in kf:
                ts.append(float(t))
                caps.append(cap)
        else:
            for s in P.scenes:
                for f, lab in ((0.35, "in"), (0.7, "hold"), (0.97, "out")):
                    t = s.t0 + s.dur * f
                    if t < P.duration:
                        ts.append(t)
                        caps.append(f"{s.name} · {lab}")
    t0 = time.perf_counter()
    frames = render_stills(P, ts, scale=a.scale)
    name = "check.png" if a.times else "storyboard.png"     # spot checks never overwrite the storyboard
    out = os.path.join(a.dir, "out", name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    paths = sheet(list(zip(ts, frames)), out, captions=caps, title="Storyboard keyframes" if not a.times else "Spot check")
    tbl = scene_table(P)
    open(os.path.join(a.dir, "out", "scene_table.md"), "w", encoding="utf-8").write(tbl + "\n")
    log(tbl)
    log(f"[storyboard] {len(ts)} keyframes in {time.perf_counter() - t0:.1f}s -> " + ", ".join(paths))


def _audio(P, dirp, enabled=True):
    if not enabled:
        return None, None
    from audio import render_audio
    t0 = time.perf_counter()
    paths, rep = render_audio(P, os.path.join(dirp, "out", "audio"))
    log(f"[audio] {rep['lufs']} LUFS / {rep['true_peak_db']} dBTP (ffmpeg: {rep.get('ffmpeg_I')} / {rep.get('ffmpeg_TP')}),"
        f" genre={rep.get('genre')}, events={rep['events']}, {time.perf_counter() - t0:.1f}s")
    return paths, rep


def _fix_true_peak(P, video, dirp=None):
    """AAC adds inter-sample overshoot. If the muxed file exceeds the true-peak ceiling,
    re-master the mix WAV with a lower limiter ceiling (loudness kept at target) and re-mux
    the audio (video stream copied)."""
    import subprocess
    from audio.master import ffmpeg_loudness, master
    from audio.dsp import read_wav, write_wav
    snd = P.design.sound or {}
    ceiling = float(snd.get("true_peak", -1.0))
    target = float(snd.get("loudness", -14.0))
    m = ffmpeg_loudness(video)
    mix = os.path.join(dirp or P.root, "out", "audio", "mix.wav")
    for _ in range(3):
        if m.get("TP") is None or m["TP"] <= ceiling or not os.path.exists(mix):
            return m
        x, _sr = read_wav(mix)
        y, rep = master(x, target, ceiling - (m["TP"] - ceiling) - 0.7)
        write_wav(mix, y)
        tmp = video + ".tp.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", mix, "-map", "0:v", "-map", "1:a",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart", tmp], check=True)
        os.replace(tmp, video)
        m2 = ffmpeg_loudness(video)
        log(f"[audio] true peak {m['TP']} dBTP after AAC -> re-mastered -> {m2.get('I')} LUFS / {m2.get('TP')} dBTP")
        m = m2
    return m


def _project_sig(dirp, fps, extra=""):
    import hashlib
    h = hashlib.sha1(f"{os.path.abspath(dirp)}|{fps}|{extra}".encode())
    files = ["video.py", "design.yaml"]
    ext = os.path.join(dirp, "engine_ext")
    if os.path.isdir(ext):
        files += [os.path.join("engine_ext", f) for f in sorted(os.listdir(ext)) if f.endswith(".py")]
    for f in files:
        p = os.path.join(dirp, f)
        if os.path.exists(p):
            h.update(open(p, "rb").read())
    eng = os.path.join(HERE, "engine")
    for r_, _d, fs in os.walk(eng):
        for f in sorted(fs):
            if f.endswith(".py"):
                h.update(f"{f}:{int(os.stat(os.path.join(r_, f)).st_mtime)}".encode())
    for root in (os.path.join(dirp, "assets"), os.path.join(dirp, "data"), os.path.join(dirp, "fonts")):
        if os.path.isdir(root):
            for f in sorted(os.listdir(root)):
                st = os.stat(os.path.join(root, f))
                h.update(f"{f}:{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()[:12]


CHUNK_ROOT = os.path.join(os.environ.get("MV_CACHE", os.path.expanduser("~/.cache/emaki")), "chunks")


def _prune_chunk_cache(keep, max_age_h=48):
    """Drop chunk caches of other renders not touched for `max_age_h` hours."""
    import shutil as _sh
    if not os.path.isdir(CHUNK_ROOT):
        return
    now = time.time()
    for d in os.listdir(CHUNK_ROOT):
        p = os.path.join(CHUNK_ROOT, d)
        if p != keep and os.path.isdir(p) and now - os.path.getmtime(p) > max_age_h * 3600:
            _sh.rmtree(p, ignore_errors=True)


def _render_chunked(P, a, tag, scale, fps, t_call, chunk_s=2.0, preview=False, ss=2):
    """Render the video stream in chunks kept OUTSIDE the project (no clutter, no delete
    problems in mounted folders). Resumable across calls AND incremental across edits: every
    chunk stores a fingerprint of its frames (engine.render.fingerprint), and after a change to
    video.py only the chunks whose picture changed are rendered again. A fix at 12 s of a 48 s
    film re-renders one or two 2 s chunks, not the film. Returns (list_file, render_s, n, cdir)."""
    import hashlib
    from engine.render import render_video, fingerprints
    n = int(round(P.duration * fps))
    key = hashlib.sha1(f"{os.path.abspath(a.dir)}|{tag}|{fps}|{scale}|ss{ss}|{P.W}x{P.H}".encode()).hexdigest()[:12]
    cdir = os.path.join(CHUNK_ROOT, key)
    os.makedirs(cdir, exist_ok=True)
    _prune_chunk_cache(cdir)
    per_chunk = max(1, int(round(chunk_s * fps)))
    chunks = [(k, k * per_chunk, min(n, (k + 1) * per_chunk)) for k in range((n + per_chunk - 1) // per_chunk)]
    man_p = os.path.join(cdir, "manifest.json")
    man = json.load(open(man_p)) if os.path.exists(man_p) else {}
    if man.get("n") != n or man.get("per_chunk") != per_chunk:
        man = {"n": n, "per_chunk": per_chunk, "chunks": {}}
    # fingerprints of the current version (computed once per version of the sources)
    sig = _project_sig(a.dir, fps, f"{tag}|{scale}|ss{ss}")
    if man.get("sig") != sig or len(man.get("fp_now", [])) != len(chunks):
        t_fp = time.perf_counter()
        fps_frames = fingerprints(P, [i / fps for i in range(n)], scale=scale / 4)
        man["fp_now"] = [hashlib.sha1("".join(fps_frames[f0:f1]).encode()).hexdigest()[:16] for _, f0, f1 in chunks]
        man["sig"] = sig
        json.dump(man, open(man_p, "w"))
        log(f"[{tag}] fingerprints of {n} frames in {time.perf_counter() - t_fp:.1f}s")
    fp_now = man["fp_now"]

    def done(k):
        c = man["chunks"].get(str(k))
        return bool(c) and c.get("fp") == fp_now[k] and os.path.exists(os.path.join(cdir, f"c{k:04d}.mp4"))
    todo = [c for c in chunks if not done(c[0])]
    if man["chunks"] and todo and len(todo) < len(chunks):
        changed = ", ".join(f"{f0 / fps:.1f}-{f1 / fps:.1f}s" for _, f0, f1 in todo[:12]) + (" ..." if len(todo) > 12 else "")
        log(f"[{tag}] {len(chunks) - len(todo)} of {len(chunks)} chunks unchanged since the last render; re-rendering {changed}")
    log(f"[{tag}] {P.duration:.1f}s @ {fps} fps, scale {scale:g}, {ss}x supersampling; {len(chunks)} chunks of "
        f"{chunk_s:g}s, {len(chunks) - len(todo)} ready, {len(todo)} to render")
    rendered = []
    for k, f0, f1 in todo:
        spent = time.perf_counter() - t_call
        walls = [c["s"] for c in man["chunks"].values() if "s" in c]
        avg = (sum(walls) / len(walls)) if walls else (6.0 if preview else 12.0)
        if spent + avg * 1.3 > a.budget:
            left = len([c for c in chunks if not done(c[0])])
            log(f"[{tag}] PARTIAL {len(chunks) - left}/{len(chunks)} chunks after {spent:.0f}s (call budget {a.budget:g}s). "
                f"Run the same command again to continue.")
            sys.exit(3)
        st = render_video(P, os.path.join(cdir, f"c{k:04d}.mp4"), scale=scale, fps=fps, ss=ss,
                          t_range=(f0 / fps, f1 / fps), preview=preview)
        man["chunks"][str(k)] = {"fp": fp_now[k], "s": st["wall_s"], "frame_avg_s": st["frame_avg_s"],
                                 "slowest_t": st["slowest_t"]}
        json.dump(man, open(man_p, "w"))
        rendered.append(st)
        log(f"  chunk {k + 1}/{len(chunks)}: {f1 - f0} frames in {st['wall_s']}s")
    lst = os.path.join(cdir, "list.txt")
    with open(lst, "w") as f:
        for k, _, _ in chunks:
            f.write(f"file '{os.path.join(cdir, f'c{k:04d}.mp4')}'\n")
    # leave room for assembly and QA in a fresh call when this one is already busy
    if todo and time.perf_counter() - t_call > a.budget * 0.7:
        log(f"[{tag}] PARTIAL {len(chunks)}/{len(chunks)} chunks rendered; run the same command again to assemble and QA.")
        sys.exit(3)
    render_s = round(sum(c.get("s", 0) for c in man["chunks"].values()), 1)
    return lst, render_s, len(chunks), cdir, len(todo)


def _assemble(lst, audio, out):
    import subprocess
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst]
    if audio:
        cmd += ["-i", audio, "-c:a", "aac", "-b:a", "256k", "-shortest"]
    cmd += ["-c:v", "copy", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)


def _frames_from_video(path, ts, w, h):
    """Decode the frames at times ts from a rendered video as RGB uint8 arrays (w x h)."""
    import subprocess
    import numpy as np
    frames = []
    for t in ts:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", path, "-frames:v", "1",
                              "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        if len(raw) != w * h * 3:
            raise ValueError(f"frame at {t}s: got {len(raw)} bytes")
        frames.append(np.frombuffer(raw, np.uint8).reshape(h, w, 3).copy())
    return frames


def cmd_preview(a):
    """Half resolution, 15 fps, resumable chunks; then contact sheets, final estimate, QA."""
    from engine.render import render_stills, estimate_final
    from engine.contact import sheet
    import shutil as _sh
    import qa
    t_call = time.perf_counter()
    P = load(a.dir, a.lib)
    lst, render_s, nch, cdir, n_new = _render_chunked(P, a, "preview", 0.5, 15, t_call, chunk_s=2.0, preview=True, ss=a.ss)
    paths, rep = _audio(P, a.dir, not a.no_audio)
    out = os.path.join(a.dir, "out", "preview.mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    _assemble(lst, paths["mix"] if paths else None, out)
    if paths:
        _fix_true_peak(P, out, a.dir)
    n = int(round(P.duration * 15))
    log(f"[preview] {n} frames rendered in {render_s}s ({nch} chunks) -> {out}")
    every = a.every
    ts = [round(k * every, 3) for k in range(int(P.duration / every) + 1) if k * every < P.duration]
    t0 = time.perf_counter()
    try:
        # the frames already exist in preview.mp4: read them back instead of rendering them again
        frames = _frames_from_video(out, ts, P.W // 2, P.H // 2)
    except Exception as e:
        log(f"[contact] reading preview.mp4 failed ({e}); rendering stills instead")
        frames = render_stills(P, ts, scale=0.5)
    cs = sheet(list(zip(ts, frames)), os.path.join(a.dir, "out", "preview_contact.png"),
               title=f"Preview contact sheet, every {every}s")
    log(f"[contact] {len(ts)} frames in {time.perf_counter() - t0:.1f}s -> " + ", ".join(cs))
    ffps = a.final_fps or P.fps
    per_frame = render_s / max(1, n)
    if a.estimate:
        est = estimate_final(P, scale=1.0, fps=ffps)
        log(f"[estimate] final {est['frames']} frames at 1080p: ~{est['estimate_s']:.0f}s "
            f"({est['wall_per_frame_s']}s/frame wall, measured on {est['sample_frames']} sample frames, {est['workers']} workers)")
    else:
        # rough: a final frame (4x the pixels, 2x supersampling, bounded layers) costs ~2.5x a
        # preview frame (measured on a 47.5 s product film: 0.028 s vs 0.064 s per frame)
        rough = per_frame * (2.5 if a.ss <= 1 else 1.3) * P.duration * ffps
        est = {"rough_s": round(rough), "preview_s_per_frame": round(per_frame, 3)}
        log(f"[estimate] preview {per_frame:.2f}s/frame; final roughly ~{rough:.0f}s "
            f"(run `mv.py estimate <dir>` for a measured number before the final)")
    status, items, md = qa.run(a.dir, out, final=False, P=P)
    log(open(md, encoding="utf-8").read())
    timing_log(a.dir, {"kind": "preview", "frames": n, "fps": 15, "size": [P.W // 2, P.H // 2], "ss": a.ss,
                       "wall_s": render_s, "chunks": nch, "chunks_rendered": n_new, "estimate_final": est, "qa": status})


def cmd_final(a):
    """Final render in chunks that each fit one shell call. Re-run the same command until it
    prints the QA report: finished chunks are kept and skipped (resumable)."""
    from engine.render import render_video
    import shutil as _sh
    import qa
    t_call = time.perf_counter()
    P = load(a.dir, a.lib)
    fps = a.fps or P.fps
    lst, render_s, nch, cdir, n_new = _render_chunked(P, a, "final", 1.0, fps, t_call, chunk_s=a.chunk, ss=a.ss)
    t_as = time.perf_counter()
    paths, rep = _audio(P, a.dir, not a.no_audio)
    out = os.path.join(a.dir, "out", "final.mp4")
    _assemble(lst, paths["mix"] if paths else None, out)
    if paths:
        _fix_true_peak(P, out, a.dir)
    n = int(round(P.duration * fps))
    log(f"[final] {n} frames, render time {render_s}s over {nch} chunks ({n_new} rendered in this call), "
        f"{render_s / max(1, n):.3f}s/frame; assembled in {time.perf_counter() - t_as:.1f}s -> {out}")
    if a.webm_loop:
        w = os.path.join(a.dir, "out", "loop.webm")
        st2 = render_video(P, w, scale=1.0, fps=fps, ss=a.ss, audio=None, codec="vp9", log=log)
        log(f"[final] webm loop -> {w} ({st2['wall_s']}s)")
    status = "SKIPPED"
    if not a.no_qa:
        status, items, md = qa.run(a.dir, out, final=True, P=P)
        log(open(md, encoding="utf-8").read())
    timing_log(a.dir, {"kind": "final", "frames": n, "fps": fps, "size": [P.W, P.H], "ss": a.ss,
                       "render_s": render_s, "s_per_frame": round(render_s / max(1, n), 3), "chunks": nch,
                       "chunks_rendered": n_new, "qa": status})


def cmd_styleframes(a):
    """Gate 1: the key moments (P.keyframes or --times) at FINAL quality (full size, 2x
    supersampling, post fx) as separate PNGs plus one sheet. The look is approved on these
    before the rest of the film is animated; they are also the critic's input."""
    from engine.render import render_stills
    from engine.contact import sheet
    from PIL import Image
    P = load(a.dir, a.lib)
    if a.times:
        moments = [(float(x), "") for x in a.times.split(",")]
    else:
        moments = [(float(t), cap) for t, cap in (getattr(P, "keyframes", None) or [])]
    if not moments:
        sys.exit("[styleframes] no P.keyframes in video.py and no --times")
    t0 = time.perf_counter()
    frames = render_stills(P, [t for t, _ in moments], scale=1.0, ss=2)
    od = os.path.join(a.dir, "out", "frames")
    os.makedirs(od, exist_ok=True)
    paths = []
    for (t, cap), img in zip(moments, frames):
        p = os.path.join(od, f"frame_{t:06.2f}.png")
        Image.fromarray(img).save(p)
        paths.append(p)
    sh = sheet(list(zip([t for t, _ in moments], frames)), os.path.join(a.dir, "out", "styleframes.png"),
               captions=[c for _, c in moments], title="Style frames (final quality)", cols=min(2, len(frames)))
    log(f"[styleframes] {len(frames)} frames in {time.perf_counter() - t0:.1f}s -> {od}/ and " + ", ".join(sh))
    if a.ref:
        lib = find_lib(a.dir, a.lib)
        rdir = os.path.join(lib or "", "references", a.ref)
        refs = sorted(glob.glob(os.path.join(rdir, "sheet_*.png")))
        log("[styleframes] reference sheets to compare: " + (", ".join(refs[:4]) if refs else f"none in {rdir}"))


def cmd_still(a):
    from engine.render import frame
    from PIL import Image
    P = load(a.dir, a.lib)
    img = frame(P, float(a.t), a.scale, 2)
    out = os.path.join(a.dir, "out", f"still_{float(a.t):06.2f}.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    Image.fromarray(img).save(out)
    log(out)


def cmd_contact(a):
    from engine.render import render_stills
    from engine.contact import sheet
    P = load(a.dir, a.lib)
    ts = [round(k * a.every, 3) for k in range(int(P.duration / a.every) + 1) if k * a.every < P.duration]
    frames = render_stills(P, ts, scale=a.scale)
    log("\n".join(sheet(list(zip(ts, frames)), os.path.join(a.dir, "out", "contact.png"), title=f"every {a.every}s")))


def cmd_strips(a):
    """Motion strips: 12 fps around the key moments, one row per moment. A 0.5 s contact sheet
    shows layouts; motion (anticipation, overlap, easing, hand-offs) is only visible here.
    With --ref, prints the reference strips to open next to ours."""
    from engine.render import render_stills
    from engine.contact import sheet
    P = load(a.dir, a.lib)
    if a.at:
        moments = [(float(x), "") for x in a.at.split(",")]
    else:
        moments = [(float(t), cap) for t, cap in (getattr(P, "keyframes", None) or [])]
        if not moments:
            moments = [(s.t0 + s.dur * 0.3, s.name) for s in P.scenes]
    n = max(2, int(round(a.span * a.fps)))
    frames, caps = [], []
    for t, cap in moments:
        t0 = max(0.0, min(P.duration - a.span, t - a.span / 2))
        ts = [round(t0 + k / a.fps, 4) for k in range(n)]
        imgs = render_stills(P, ts, scale=a.scale)
        frames += list(zip(ts, imgs))
        caps += [cap if k == 0 else "" for k in range(n)]
    out = os.path.join(a.dir, "out", "strips.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    paths = sheet(frames, out, cols=n, max_width=min(3000, 190 * n), captions=caps,
                  title=f"Motion strips, {a.fps:g} fps, {a.span:g}s per row", per_sheet=n * 4)
    log("[strips] " + ", ".join(paths))
    if a.ref:
        lib = find_lib(a.dir, a.lib)
        rdir = os.path.join(lib or "", "references", a.ref)
        refs = sorted(glob.glob(os.path.join(rdir, "strips*.png")) + glob.glob(os.path.join(rdir, "d_*.png")))
        log("[strips] reference strips to compare: " + (", ".join(refs) if refs else f"none in {rdir}"))


def cmd_timeline(a):
    """Choreography map (the animation-map of HyperFrames): one row per element, a bar per thing it
    does (entrance, later actions, ambient), camera moves, and the holds where nothing animates."""
    from PIL import Image, ImageDraw
    from engine.contact import _font
    import qa
    P = load(a.dir, a.lib)
    rows = []
    for s in P.scenes:
        for el in s.children:
            acts, amb = qa.element_actions(el)
            cl = [c for c in qa._clusters(acts) if not qa._is_drift(c)]
            if not cl and not amb:
                continue
            rows.append((f"{s.name}/{el.name}", [(s.t0 + c["t0"], s.t0 + c["t1"], qa._signature(c)) for c in cl], amb,
                         qa._is_element(el, P)))
    cam = []
    for s in P.scenes:
        for pn, p in vars(s.camera).items():
            if isinstance(p, qa.core.Prop):
                for i in range(1, len(p.keys)):
                    k0, k1 = p.keys[i - 1], p.keys[i]
                    if qa._differs(k1.v, k0.v):
                        cam.append((s.t0 + k0.t, s.t0 + k1.t, k1.t - k0.t < 1.0))
    R = qa.Report()
    qa.check_choreography(P, R)
    holds = [(i["t"], float(i["msg"].split("(")[1].split("s)")[0])) for i in R.items
             if i["check"] == "choreography" and i["msg"].startswith("hold")]
    W, lab_w, row_h = 1800, 360, 22
    px = (W - lab_w - 20) / max(0.1, P.duration)
    H = 60 + (len(rows) + 2) * row_h + 30
    img = Image.new("RGB", (W, H), (24, 24, 26))
    d = ImageDraw.Draw(img)
    f = _font(13)
    d.text((10, 10), f"Choreography map: {P.meta.get('name', '')}  (green = entrance, blue = later action, "
                     f"grey = ambient, red = hold)", font=_font(15), fill=(230, 230, 230))
    x0 = lab_w
    for t in range(int(P.duration) + 1):
        x = x0 + t * px
        d.line([(x, 40), (x, H - 20)], fill=(50, 50, 55))
        d.text((x + 2, H - 18), f"{t}s", font=f, fill=(140, 140, 140))
    for t, dur in holds:
        d.rectangle([x0 + t * px, 40, x0 + (t + dur) * px, H - 22], fill=(90, 30, 30))
    y = 44
    for name, cl, amb, counted in rows:
        d.text((10, y + 3), name[:44], font=f, fill=(220, 220, 220) if counted else (120, 120, 120))
        if amb:
            d.rectangle([x0, y + 9, W - 20, y + 12], fill=(90, 90, 95))
        for k, (a_, b_, sig) in enumerate(cl):
            c = (70, 170, 90) if k == 0 else (80, 140, 230)
            d.rectangle([x0 + a_ * px, y + 4, max(x0 + a_ * px + 3, x0 + b_ * px), y + row_h - 4], fill=c)
            d.text((x0 + b_ * px + 3, y + 4), sig[:18], font=_font(11), fill=(170, 170, 170))
        y += row_h
    d.text((10, y + 3), "camera", font=f, fill=(220, 200, 120))
    for a_, b_, short_move in cam:
        c = (230, 190, 80) if short_move else (110, 100, 70)
        d.rectangle([x0 + a_ * px, y + 6, max(x0 + a_ * px + 2, x0 + b_ * px), y + row_h - 6], fill=c)
    out = os.path.join(a.dir, "out", "timeline.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    for i in R.items:
        if i["check"] == "choreography":
            log(f"[{i['level']}] {i['msg']}")
    log(f"[timeline] {out}")


def cmd_qa(a):
    import qa
    P = load(a.dir, a.lib)            # engine_ext and the library loaded, like every other command
    st, items, md = qa.run(a.dir, a.video, a.final, P=P)
    log(open(md, encoding="utf-8").read())
    sys.exit(1 if st == "FAIL" else 0)


def cmd_estimate(a):
    from engine.render import estimate_final
    P = load(a.dir, a.lib)
    log(json.dumps(estimate_final(P, 1.0, a.fps or P.fps), indent=1))


def cmd_ae(a):
    """AE export. Baked clips are cached; when the call budget runs out it exits with code 3
    (PARTIAL): run the same command again to continue."""
    from ae.export import export, PartialExport
    t_call = time.perf_counter()
    P = load(a.dir, a.lib)
    mix = os.path.join(a.dir, "out", "audio", "mix.wav")
    if os.path.exists(mix) and os.path.getmtime(mix) > os.path.getmtime(os.path.join(a.dir, "video.py")):
        ad = os.path.join(a.dir, "out", "audio")
        paths = {k: os.path.join(ad, f"{k}.wav") for k in ("music", "sfx", "mix")}
    else:
        paths, rep = _audio(P, a.dir, True)
    try:
        res = export(P, a.dir, version=a.version, audio=paths, log=log, budget=a.budget * 0.8, t_call=t_call)
    except PartialExport as e:
        log(f"[ae] PARTIAL: baking clips ({os.path.basename(str(e))} next). Run the same command again to continue.")
        sys.exit(3)
    log(json.dumps(res, indent=1, ensure_ascii=False))


BREAKDOWN_TEMPLATE = """# {rid}

Source: {src} ({dur:.1f} s). Analysed {date}. Techniques only: never copy the content, images,
logos or copy of a reference.

## What it is
(one paragraph: genre, mood, who it is for, what makes it feel professional)

## Timeline
| t, s | what happens | technique id |
|---|---|---|

## Typography
## Colour and light
## Camera
## Transitions
## Sound
(voice-over / music / sound design; tempo {bpm} BPM; spectrum {bands}; how tightly picture follows sound)

## Take / don't take
"""


def cmd_analyze_ref(a):
    """Reference intake. With --id the result goes to <motion-lib>/references/<id>/ (metrics with sound,
    timed sheets every 0.25 s, spectrogram, breakdown.md template to fill in after viewing)."""
    import analyze
    crop = a.crop.split(":") if a.crop else None
    if a.id:
        lib = find_lib(os.getcwd(), a.lib) or find_lib(os.path.dirname(os.path.abspath(a.video)), a.lib)
        if not lib:
            sys.exit("[analyze-ref] no motion-lib found: pass --lib DIR or set MV_LIB")
        out = os.path.join(lib, "references", a.id)
    else:
        out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.video)),
                                    os.path.splitext(os.path.basename(a.video))[0] + "_analysis")
    os.makedirs(out, exist_ok=True)
    m = analyze.metrics(a.video, crop, skip=a.skip)
    m["sound"] = analyze.audio_metrics(a.video, crop, a.skip)
    m["crop"] = a.crop
    m["skip"] = a.skip
    json.dump(m, open(os.path.join(out, "metrics.json"), "w"), indent=1)
    if a.id:
        sheets = analyze.timed_sheets(a.video, os.path.join(out, "sheet"), crop, a.sheet_fps or 4.0, skip=a.skip)
        spec = analyze.spectrogram(a.video, os.path.join(out, "spectrogram.png"), a.skip)
        sheets += [spec] if spec else []
        bd = os.path.join(out, "breakdown.md")
        if not os.path.exists(bd):
            s = m["sound"]
            open(bd, "w", encoding="utf-8").write(BREAKDOWN_TEMPLATE.format(
                rid=a.id, src=os.path.basename(a.video), dur=m["duration_s"], date=time.strftime("%Y-%m-%d"),
                bpm=s.get("tempo_bpm"), bands=s.get("bands_db")))
    else:
        sheets = analyze.sheets(a.video, out, crop, a.sheet_fps or 2.0, [x for x in (a.detail or "").split(",") if x])
    short = {k: v for k, v in m.items() if k not in ("energy_per_s", "cut_times", "hit_times", "sound")}
    short["sound"] = {k: v for k, v in m["sound"].items() if not k.endswith("_times")}
    log(json.dumps(short, indent=1, ensure_ascii=False))
    log("[analyze-ref] sheets: " + ", ".join(sheets))
    log("[analyze-ref] put static_pct/100 -> dynamics.static_max, longest_still_s -> max_still, "
        "hit_interval_s -> hit_interval in design.yaml (loosen them for calmer briefs)")
    if a.id:
        log(f"[analyze-ref] now view every sheet, fill {out}/breakdown.md, add new techniques to "
            "motion-lib/techniques.md and a row to motion-lib/references/INDEX.md")


def cmd_voice(a):
    """Word timings for the voice-over: sound.voice from design.yaml (or --file), text from
    --text, --cues (.srt/.vtt) or the brief texts joined. Writes data/words.json (hand edits
    survive unless --force) and prints the table to check against the preview."""
    import yaml
    from audio import voice as V
    design = yaml.safe_load(open(os.path.join(a.dir, "design.yaml"), encoding="utf-8")) or {}
    snd = design.get("sound") or {}
    src = a.file or snd.get("voice")
    if not src:
        sys.exit("[voice] no voice file: set sound.voice in design.yaml or pass --file")
    src = src if os.path.isabs(src) else os.path.join(a.dir, src)
    text = a.text
    if not text and not a.cues:
        bp = os.path.join(a.dir, "brief.yaml")
        brief = yaml.safe_load(open(bp, encoding="utf-8")) if os.path.exists(bp) else {}
        text = " ".join(brief.get("texts") or [])
    out = os.path.join(a.dir, "data", "words.json")
    words = V.align(src, text, out_json=out, force=a.force, cues=a.cues,
                    offset=float(snd.get("voice_offset", 0.0)))
    for w in words:
        log(f"{w['t0']:7.2f} {w['t1']:7.2f}  {w['word']}")
    log(f"[voice] {len(words)} words -> {out}. Check them against the preview; fix a time by hand "
        "if a word lands early or late (re-runs keep the file unless --force).")


def cmd_beats(a):
    from audio.voice import track_tempo
    bpm, first = track_tempo(a.file)
    log(f"[beats] {a.file}: {bpm} BPM, first beat at {first:.3f}s -> design.yaml sound.bpm: {bpm}, "
        f"sound.beat_offset: {first:.3f} (if the tempo reads double or half, use x2 or /2)")


def cmd_styles(a):
    lib = find_lib(os.getcwd(), a.lib)
    import yaml
    for sd in style_dirs(lib):
        for name in sorted(os.listdir(sd)):
            p = os.path.join(sd, name, "README.md")
            desc = open(p, encoding="utf-8").read().strip().splitlines()[0] if os.path.exists(p) else ""
            log(f"{name:22s} {desc}  [{sd}]")


def cmd_save_style(a):
    lib = find_lib(a.dir, a.lib)
    if not lib:
        lib = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(a.dir))), "motion-lib")
    dst = os.path.join(lib, "styles", a.name)
    os.makedirs(dst, exist_ok=True)
    shutil.copy(os.path.join(a.dir, "design.yaml"), os.path.join(dst, "design.yaml"))
    readme = os.path.join(dst, "README.md")
    if not os.path.exists(readme):
        open(readme, "w", encoding="utf-8").write(f"{a.name}: saved from {os.path.basename(os.path.abspath(a.dir))}. "
                                                  "Describe when to use it in one line.\n")
    log(f"[style] saved -> {dst}")


def cmd_promote(a):
    lib = find_lib(a.dir, a.lib)
    if not lib:
        lib = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(a.dir))), "motion-lib")
    dst = os.path.join(lib, "engine_ext")
    os.makedirs(dst, exist_ok=True)
    shutil.copy(os.path.join(a.dir, "engine_ext", a.module), os.path.join(dst, a.module))
    log(f"[promote] {a.module} -> {dst}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lib", help="user library folder (styles, engine_ext, fonts)")
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("init"); p.add_argument("dir"); p.add_argument("--style"); p.add_argument("--aspect", default="16:9")
    p.add_argument("--duration", type=float, default=20); p.add_argument("--fps", type=int, default=30)
    p = sp.add_parser("storyboard"); p.add_argument("dir"); p.add_argument("--times"); p.add_argument("--scale", type=float, default=0.3)
    p = sp.add_parser("preview"); p.add_argument("dir"); p.add_argument("--no-audio", action="store_true")
    p.add_argument("--budget", type=float, default=float(os.environ.get("MV_CALL_BUDGET", 140)))
    p.add_argument("--every", type=float, default=0.5); p.add_argument("--final-fps", type=int)
    p.add_argument("--ss", type=int, default=1, help="supersampling for the preview (1 = off; the final uses 2)")
    p.add_argument("--estimate", action="store_true", help="measure the final render time (renders sample frames at 1080p)")
    p = sp.add_parser("final"); p.add_argument("dir"); p.add_argument("--fps", type=int); p.add_argument("--webm-loop", action="store_true")
    p.add_argument("--budget", type=float, default=float(os.environ.get("MV_CALL_BUDGET", 140)),
                   help="seconds of work per call; keep it under the shell command timeout")
    p.add_argument("--chunk", type=float, default=2.0, help="chunk length in seconds")
    p.add_argument("--ss", type=int, default=2, help="supersampling for the final")
    p.add_argument("--no-qa", action="store_true"); p.add_argument("--no-audio", action="store_true")
    p = sp.add_parser("styleframes"); p.add_argument("dir"); p.add_argument("--times", help="comma list of moments (s); default P.keyframes")
    p.add_argument("--ref", help="motion-lib reference id to compare with")
    p = sp.add_parser("still"); p.add_argument("dir"); p.add_argument("t"); p.add_argument("--scale", type=float, default=1.0)
    p = sp.add_parser("contact"); p.add_argument("dir"); p.add_argument("--every", type=float, default=0.5); p.add_argument("--scale", type=float, default=0.5)
    p = sp.add_parser("strips"); p.add_argument("dir"); p.add_argument("--at", help="comma list of moments (s); default P.keyframes")
    p.add_argument("--span", type=float, default=1.0); p.add_argument("--fps", type=float, default=12.0)
    p.add_argument("--scale", type=float, default=0.25); p.add_argument("--ref", help="motion-lib reference id to compare with")
    p = sp.add_parser("timeline"); p.add_argument("dir")
    p = sp.add_parser("qa"); p.add_argument("dir"); p.add_argument("--video"); p.add_argument("--final", action="store_true")
    p = sp.add_parser("estimate"); p.add_argument("dir"); p.add_argument("--fps", type=int)
    p = sp.add_parser("ae"); p.add_argument("dir"); p.add_argument("--version", default=None)
    p.add_argument("--budget", type=float, default=float(os.environ.get("MV_CALL_BUDGET", 140)))
    p = sp.add_parser("analyze-ref"); p.add_argument("video"); p.add_argument("--crop", help="W:H:X:Y")
    p.add_argument("--skip", type=float, default=0.0); p.add_argument("--detail", default="")
    p.add_argument("--sheet-fps", type=float, default=None); p.add_argument("--out")
    p.add_argument("--id", help="save into <motion-lib>/references/<id>/ (library intake)")
    p = sp.add_parser("voice"); p.add_argument("dir"); p.add_argument("--file"); p.add_argument("--text")
    p.add_argument("--cues", help=".srt/.vtt with phrase timings"); p.add_argument("--force", action="store_true")
    p = sp.add_parser("beats"); p.add_argument("file")
    p = sp.add_parser("styles")
    p = sp.add_parser("save-style"); p.add_argument("dir"); p.add_argument("name")
    p = sp.add_parser("promote"); p.add_argument("dir"); p.add_argument("module")
    a = ap.parse_args()
    for k in ("dir",):
        if hasattr(a, k) and getattr(a, k):
            setattr(a, k, os.path.abspath(getattr(a, k)))
    {"init": cmd_init, "storyboard": cmd_storyboard, "preview": cmd_preview, "final": cmd_final,
     "styleframes": cmd_styleframes, "still": cmd_still, "contact": cmd_contact, "strips": cmd_strips, "timeline": cmd_timeline, "qa": cmd_qa, "estimate": cmd_estimate, "ae": cmd_ae,
     "styles": cmd_styles, "save-style": cmd_save_style, "promote": cmd_promote,
     "analyze-ref": cmd_analyze_ref, "voice": cmd_voice, "beats": cmd_beats}[a.cmd](a)


if __name__ == "__main__":
    main()
