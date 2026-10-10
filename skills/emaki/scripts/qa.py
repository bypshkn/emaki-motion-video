"""Automated QA for an Emaki project. Run after every preview and before the final.

Checks (FAIL blocks delivery, WARN needs a look, INFO is for the storyboard):
  safe_zone      copy text inside the 8% margin (FAIL) and platform UI zones (WARN)
  overflow       a word wider than its text box (FAIL), missing glyphs (FAIL)
  reading_time   >= max(1.2 s, 0.3 s per word) of readable time per phrase (FAIL)
  contrast       text vs. actual rendered background >= 4.5:1 (FAIL)
  forbidden      nothing from design.yaml fx.forbidden is used (FAIL)
  brief_copy     copy marked src='brief' matches brief.yaml texts verbatim (FAIL);
                 invented copy is listed as [DEMO COPY] (INFO)
  sync           accents on the BPM grid (+-1 frame) (FAIL); SFX transients land on
                 their frames in the mix (WARN)
  loudness       -14 LUFS +-0.5 and true peak <= -1 dBTP (ffmpeg ebur128) (FAIL)
  flicker        frame-to-frame luminance jumps / oscillating tiles outside cuts (WARN)
  aliasing       supersampling < 2, sub-pixel strokes, tiny copy text (WARN/FAIL)
  easing         linear transform keys, velocity jumps at keys, strobing speed (WARN)
  in_frame       copy text cut by the frame edge for >= 0.2 s, kinetic words included (FAIL)
  choreography   slideshow detector from the scene graph: elements that only enter and sit,
                 holds where only the camera glides, uniform entrances, one easing everywhere,
                 one speed everywhere (FAIL / WARN)
  allowed        exceptions declared with layer.allow(...) and their reasons (INFO)
  look           light and colour on the rendered frames: flat grey-on-grey, lifted blacks, no
                 real white, the accent missing from most of the film (WARN)
  format         duration vs brief, output resolution / fps / audio stream (FAIL)
  lint           design.yaml decisions without `why`, font fallbacks (WARN)

Usage: python3 qa.py <project_dir> [--video out/preview.mp4] [--final] [--no-render]
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from engine.env import load_skia  # noqa: E402

skia = load_skia()

from engine import core  # noqa: E402
from engine.core import Group, color, contrast_ratio, luminance  # noqa: E402
from engine.layers.text import Text, TextOnPath, plain as strip_markup  # noqa: E402
from engine.render import load_project, raw_frame, out_size  # noqa: E402
from engine import fonts as F  # noqa: E402


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, check, msg, t=None, layer=None):
        self.items.append({"level": level, "check": check, "msg": msg,
                           "t": None if t is None else round(float(t), 2), "layer": layer})

    @property
    def status(self):
        lv = {i["level"] for i in self.items}
        return "FAIL" if "FAIL" in lv else "WARN" if "WARN" in lv else "PASS"


# ----------------------------------------------------------------------------- traversal

def chains(P):
    """Yield (scene, [ancestors...], layer) for every layer."""
    def rec(scene, anc, node):
        for c in node.children:
            yield scene, anc, c
            if isinstance(c, Group):
                yield from rec(scene, anc + [c], c)
    for s in P.scenes:
        yield from rec(s, [], s)
    yield from rec(None, [], P.overlay)


def world(P, scene, anc, layer, t_abs):
    """(matrix scene->screen, local time, effective opacity, visible) at absolute time."""
    if scene is None:
        ts = t_abs
    else:
        ts = t_abs - scene.t0
        if not (0 <= ts < scene.dur):
            return None, ts, 0.0, False
    m = skia.Matrix()
    top = anc[0] if anc else layer
    if scene is not None:
        cm = scene.layer_matrix(top, ts)
        if cm is not None:
            m = cm
    lt = ts
    op = 1.0
    for a in anc:
        if not a.visible(lt):
            return m, lt, 0.0, False
        op *= max(0.0, min(1.0, a.opacity.at(lt)))
        m = skia.Matrix.Concat(m, a.matrix(lt))
        lt = lt - a.offset
    if not layer.visible(lt):
        return m, lt, 0.0, False
    op *= max(0.0, min(1.0, layer.opacity.at(lt)))
    return m, lt, op, True


def group_offset(anc):
    return sum(a.offset for a in anc)


def text_layers(P):
    for s, anc, l in chains(P):
        if isinstance(l, (Text, TextOnPath)):
            yield s, anc, l


def in_transition(P, t):
    for s in P.scenes[1:]:
        if s.transition is not None and s.t0 <= t < s.t0 + s.transition.dur:
            return True
    return False


def _allowed(layer, anc=()):
    """Exceptions declared with layer.allow(...) on the layer or any of its parents."""
    out = set(getattr(layer, "allowed", set()))
    for a in anc:
        out |= set(getattr(a, "allowed", set()))
    return out


def _check_text_box(P, R, s, anc, L, txt, name, t0, t1, safe, strict):
    """Sample the text box every 0.1 s between t0 and t1 (absolute). FAIL when it is cut by the
    frame edge or leaves the 8% safe area for >= 0.2 s; WARN for the platform UI zones."""
    l, tp, r, b = safe
    ls, ts_, rs, bs = strict
    runs = {"edge": [], "safe": [], "ui": []}
    cur = {"edge": [], "safe": [], "ui": []}
    n = max(1, int((t1 - t0) / 0.1))
    for k in range(n + 1):
        t = t0 + 0.02 + k * (t1 - t0 - 0.04) / max(1, n)
        flags = set()
        ok = 0 <= t < P.duration and not in_transition(P, t)
        if ok and s is not None and s.camera.active and s.camera.speed_px(t - s.t0, 0.5 / P.fps) > 6:
            ok = False                         # mid-travel: a motion-blurred pass, not a layout
        box = None
        if ok:
            m, lt, op, vis = world(P, s, anc, L, t)
            if vis and op >= 0.5:
                bb = L.local_bounds(lt)
                rr = skia.Matrix.Concat(m, L.matrix(lt)).mapRect(skia.Rect.MakeLTRB(*bb))
                box = (rr.left(), rr.top(), rr.right(), rr.bottom())
                if box[2] <= 0 or box[0] >= P.W or box[3] <= 0 or box[1] >= P.H:
                    box = None                 # wholly off screen: the camera is elsewhere on the canvas
        if box is not None:
            if box[0] < -2 or box[1] < -2 or box[2] > P.W + 2 or box[3] > P.H + 2:
                flags.add("edge")
            if box[0] < l - 1 or box[1] < tp - 1 or box[2] > r + 1 or box[3] > b + 1:
                flags.add("safe")
            if (ls, ts_, rs, bs) != (l, tp, r, b) and (box[0] < ls or box[1] < ts_ or box[2] > rs or box[3] > bs):
                flags.add("ui")
        for kind in runs:
            if kind in flags:
                cur[kind].append((t, box))
            elif cur[kind]:
                runs[kind].append(cur[kind])
                cur[kind] = []
    for kind in runs:
        if cur[kind]:
            runs[kind].append(cur[kind])
    held = {k: [r_ for r_ in v if r_[-1][0] - r_[0][0] >= 0.15] for k, v in runs.items()}
    if held["edge"]:
        r_ = max(held["edge"], key=len)
        R.add("FAIL", "in_frame", f"'{short(txt)}' is cut off by the frame edge for {r_[-1][0] - r_[0][0] + 0.1:.1f}s "
              f"(box {fmt_box(r_[len(r_) // 2][1])}); shrink it, move it, or declare allow('offframe', why=...)",
              t=r_[0][0], layer=name)
    elif held["safe"]:
        r_ = max(held["safe"], key=len)
        R.add("FAIL", "safe_zone", f"'{short(txt)}' box {fmt_box(r_[len(r_) // 2][1])} outside 8% safe area "
              f"{fmt_box((l, tp, r, b))} for {r_[-1][0] - r_[0][0] + 0.1:.1f}s", t=r_[0][0], layer=name)
    elif held["ui"]:
        r_ = max(held["ui"], key=len)
        R.add("WARN", "safe_zone", f"'{short(txt)}' enters {P.design.format.get('platform')} UI zone "
              f"{fmt_box((ls, ts_, rs, bs))}", t=r_[0][0], layer=name)


def check_allowances(P, R):
    for s, anc, l in chains(P):
        if getattr(l, "allowed", None):
            R.add("INFO", "allowed", f"{', '.join(sorted(l.allowed))}: {l.allow_why}",
                  layer=f"{s.name if s else 'overlay'}/{l.name}")


# ----------------------------------------------------------------------------- choreography

AMBIENT_KINDS = {"particles", "grid_plane", "waveform", "wire3d"}
BACKDROP_KINDS = {"background", "fill", "solid", "linear", "radial", "conic", "noise", "pattern"}
SIG = {"position": "move", "opacity": "fade", "scale": "scale", "rotation": "rotate", "trim_end": "draw",
       "trim_start": "draw", "trim_offset": "draw", "progress": "morph", "size": "grow", "clip": "wipe",
       "rx": "tilt", "ry": "tilt", "depth": "depth", "anchor": "move", "color_prop": "colour", "value": "count",
       "radius": "grow", "sweep": "draw", "p1": "draw", "p0": "draw"}


def _differs(a, b):
    if isinstance(a, tuple) and isinstance(b, tuple):
        return any(abs(x - y) > 1e-6 for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) > 1e-6
    return a != b


def element_actions(el):
    """Animated intervals of an element (a layer added to a scene) and all its children, in the
    element's parent time: ([(t0, t1, what, ease_spec)], ambient: bool). Procedural drivers,
    wiggles and hold zooms are ambient (alive, but not an action)."""
    acts, amb = [], []

    def rec(l, off):
        for pn, p in vars(l).items():
            if not isinstance(p, core.Prop):
                continue
            if p.fn is not None:
                amb.append(pn)
            for m in p.mods:
                if isinstance(m, core.Pulse):
                    # a punch under ~8 % is invisible on a phone (critic, clean test v2): not an action
                    if abs(m.amount) >= 0.08:
                        acts.append((m.t + off, m.t + m.dur + off, "punch", "pulse"))
                else:
                    amb.append(pn)
            ks = p.keys
            for i in range(1, len(ks)):
                if ks[i].ease.kind != "hold" and _differs(ks[i].v, ks[i - 1].v):
                    acts.append((ks[i - 1].t + off, ks[i].t + off, pn, ks[i].ease.spec))
        if isinstance(l, Text):
            n = {"char": len(l.L.glyphs), "word": max(1, l.L.n_words), "line": max(1, len(l.L.lines))}
            for a in l.anims:
                t1 = a.t0 + a.params.get("total", 0.8) if a.mode == "scramble" else a.end_time(n[a.by])
                acts.append((a.t0 + off, t1 + off, f"{a.direction}:{a.mode}/{a.by}", a.ease.spec))
            if l.typer:
                acts.append((l.typer["t0"] + off, l.type_end() + off, "in:typewriter", "linear"))
            if l.write:
                acts.append((l.write["t0"] + off, l.write_end() + off, "in:write_on", l.write["ease"].spec))
            if l.draw_on:
                t0, d, e, _ = l.draw_on
                acts.append((t0 + off, t0 + d + off, "in:outline", e.spec))
            for h in l.highlights:
                acts.append((h["t"] + off, h["t"] + h["dur"] + off, "highlight", h["ease"].spec))
        if l.kind in AMBIENT_KINDS:
            amb.append(l.kind)
        if isinstance(l, Group):
            for c in l.children:
                rec(c, off + l.offset)

    rec(el, 0.0)
    return acts, bool(amb)


def _clusters(acts, gap=0.15):
    """Merge overlapping or nearly touching actions into clusters (one 'thing the element does')."""
    out = []
    for a in sorted(acts, key=lambda x: x[0]):
        if out and a[0] <= out[-1]["t1"] + gap:
            c = out[-1]
            c["t1"] = max(c["t1"], a[1])
            c["acts"].append(a)
        else:
            out.append({"t0": a[0], "t1": a[1], "acts": [a]})
    return out


def _is_drift(c):
    """A long, gentle one-way move (a slow rotation of a decor ring, a background pan)."""
    return c["t1"] - c["t0"] >= 2.5 and all(str(a[3]).replace("in_out_", "").replace("out_", "").replace("in_", "")
                                            in ("linear", "sine", "quad") for a in c["acts"])


def _signature(c):
    parts = set()
    for a in c["acts"]:
        w = a[2]
        if w.startswith("in:") or w.startswith("out:"):
            parts.add(w.split(":", 1)[1])
        elif w in ("punch", "highlight"):
            parts.add(w)
        else:
            parts.add(SIG.get(w, w))
    return "+".join(sorted(parts))


def _is_element(el, P):
    if el.kind in BACKDROP_KINDS or el.kind in AMBIENT_KINDS:
        return False
    if isinstance(el, Text) and getattr(el, "text_role", "copy") != "copy":
        return False
    try:
        if el.opacity.rest() < 0.25 and not el.opacity.keys:
            return False
    except Exception:
        pass
    return True


def check_choreography(P, R):
    """Is this motion design or a slideshow? Read from the scene graph (what the code animates),
    not from pixels: a camera gliding over elements that only fade in and sit still passes the
    pixel `dynamics` check but reads as a presentation (user feedback 2026-10-08).
      enter-only   share of elements whose only action is their entrance (no transform, no hand-off,
                   no exit). FAIL >= 75 %, WARN >= 50 %.
      holds        stretches where nothing on screen animates and the camera only glides
                   (dynamics.max_hold; the closing hold may run to 1.5 s). FAIL > 2x, WARN > 1x.
      entrances    the same entrance on >= 4 elements of one scene (WARN).
      ease         one easing on >= 60 % of all actions (WARN).
      speed        slowest/fastest action ratio < 2.5 (everything at one speed) (WARN)."""
    D = P.design
    tgt = dict(DYN_DEFAULTS.get(D.motion.tempo, DYN_DEFAULTS["medium"]))
    tgt.update({k: v for k, v in (D.dynamics or {}).items() if k in tgt})
    max_hold = float(tgt["max_hold"])
    elements, activity, eases, durs = [], [], [], []
    roots = [(s, s.t0, el) for s in P.scenes for el in s.children] + [(None, 0.0, el) for el in P.overlay.children]
    for s, t0s, el in roots:
        acts, amb = element_actions(el)
        cl = [c for c in _clusters(acts) if not _is_drift(c)]
        for c in cl:
            activity.append((t0s + c["t0"], t0s + c["t1"]))
        if not _is_element(el, P):
            continue
        for c in cl:
            durs.append(c["t1"] - c["t0"])
            for a in c["acts"]:
                eases.append(str(a[3]))
        if not cl and not amb:
            if isinstance(el, Text):
                elements.append({"el": el, "s": s, "kind": "static", "sig": "cut", "t": t0s})
            continue
        if not cl:
            continue
        kind = "enter_only" if len(cl) == 1 and not amb else "alive"
        if "static" in _allowed(el):
            kind = "allowed"
        elements.append({"el": el, "s": s, "kind": kind, "sig": _signature(cl[0]), "t": t0s + cl[0]["t0"]})
    # camera: short moves (travel, snap, punch, whip) are actions; long glides are not
    for s in P.scenes:
        for pn, p in vars(s.camera).items():
            if not isinstance(p, core.Prop):
                continue
            ks = p.keys
            for i in range(1, len(ks)):
                if ks[i].t - ks[i - 1].t < 1.0 and _differs(ks[i].v, ks[i - 1].v):
                    activity.append((s.t0 + ks[i - 1].t, s.t0 + ks[i].t))
        if s.transition is not None and s.transition.dur > 0:
            activity.append((s.t0, s.t0 + s.transition.dur))
    # global fx hits (glitch pulses, flashes driven by fx tracks) are actions too
    for name, p in getattr(P, "fx_tracks", {}).items():
        ks = p.keys
        for i in range(1, len(ks)):
            if _differs(ks[i].v, ks[i - 1].v):
                activity.append((ks[i - 1].t, ks[i].t))
    # --- enter-only share
    counted = [e for e in elements if e["kind"] in ("enter_only", "static", "alive")]
    lazy = [e for e in counted if e["kind"] in ("enter_only", "static")]
    share = len(lazy) / max(1, len(counted))
    names = ", ".join(f"'{e['el'].name}'" for e in lazy[:6]) + (" ..." if len(lazy) > 6 else "")
    if len(counted) >= 4 and share >= 0.75:
        R.add("FAIL", "choreography", f"slideshow: {len(lazy)} of {len(counted)} elements only enter and then sit "
              f"({names}). Give the hero elements a second action: transform into the next shape, hand off "
              "to the next idea, react to a beat, exit with intent. Labels that must sit: allow('static', why=...)")
    elif len(counted) >= 4 and share >= 0.5:
        R.add("WARN", "choreography", f"{len(lazy)} of {len(counted)} elements only enter and then sit ({names})")
    # --- holds: nothing on screen animates, the camera only glides
    acts = sorted((max(0.0, a), min(P.duration, b)) for a, b in activity if b > 0 and a < P.duration)
    holds, cur = [], 0.0
    for a, b in acts:
        if a > cur:
            holds.append((cur, a))
        cur = max(cur, b)
    if cur < P.duration:
        holds.append((cur, P.duration))
    bad = []
    for a, b in holds:
        lim = max(1.5, max_hold) if b >= P.duration - 1e-3 else max_hold
        if b - a > lim:
            bad.append((a, b, lim))
    for a, b, lim in sorted(bad, key=lambda x: x[0] - x[1])[:5]:
        lvl = "FAIL" if b - a > 2 * lim else "WARN"
        R.add(lvl, "choreography", f"hold {a:.2f}-{b:.2f}s ({b - a:.2f}s): nothing on screen animates, the camera at "
              f"most glides (target <= {lim:.1f}s). Start the next action earlier or let an element transform during it",
              t=a)
    # --- entrance variety per scene
    by_scene = {}
    for e in elements:
        if e["kind"] in ("enter_only", "alive", "static"):
            by_scene.setdefault(e["s"].name if e["s"] else "overlay", []).append(e["sig"])
    for sn, sigs in by_scene.items():
        top = max(set(sigs), key=sigs.count)
        if sigs.count(top) >= 4 and sigs.count(top) / len(sigs) >= 0.5:
            R.add("WARN", "choreography", f"scene '{sn}': {sigs.count(top)} of {len(sigs)} elements enter the same way "
                  f"({top}); vary entrances by role (lead, support, detail)")
    kinds = sorted({e["sig"] for e in elements if e["kind"] != "allowed"})
    n_allowed = sum(1 for e in elements if e["kind"] == "allowed")
    if n_allowed >= 3 and n_allowed / max(1, len(elements)) > 0.3:
        R.add("WARN", "choreography", f"{n_allowed} of {len(elements)} elements are declared allow('static'): exceptions "
              "are for labels and end cards, not a way around the slideshow check")
    # --- easing monopoly and speed contrast
    if len(eases) >= 6:
        top = max(set(eases), key=eases.count)
        style_linear = "linear" in [str(v) for v in D.motion.easing.values()]
        if eases.count(top) / len(eases) >= 0.6 and not (top == "linear" and style_linear):
            R.add("WARN", "choreography", f"'{top}' shapes {eases.count(top)} of {len(eases)} moves: one curve everywhere "
                  "reads mechanical; give lead, support and exits their own curves")
    ratio = None
    if len(durs) >= 5:
        p10, p90 = np.percentile(durs, 10), np.percentile(durs, 90)
        ratio = p90 / max(1e-3, p10)
        if ratio < 2.5:
            R.add("WARN", "choreography", f"everything moves at one speed ({p10:.2f}-{p90:.2f}s, x{ratio:.1f}); "
                  "contrast fast hits (0.15-0.3 s) with slow builds (0.8 s+)")
    longest = max((b - a for a, b in holds), default=0.0)
    R.add("INFO", "choreography", f"{len(lazy)} of {len(counted)} elements only enter; longest hold {longest:.2f}s "
          f"(target {max_hold:.1f}s); {len(kinds)} kinds of entrance; action durations x{ratio or 0:.1f} slowest/fastest")


# ----------------------------------------------------------------------------- checks

NOT_UKRAINIAN = re.compile(r"[ЁёЫыЭэЪъ]")


def check_language(P, R, brief):
    """Ukrainian copy (`language: uk`): letters the Ukrainian alphabet does not have (Ё Ы Э Ъ) are
    typos or copy in another language. Other languages rely on the `glyphs` check."""
    lang = str(brief.get("language", "en")).lower()
    if not lang.startswith("uk"):
        return
    for s, anc, L in text_layers(P):
        txt = getattr(L, "plain", "") or ""
        m = NOT_UKRAINIAN.search(txt)
        if m:
            R.add("FAIL", "language", f"'{short(txt)}' has '{m.group(0)}', a letter Ukrainian does not use: "
                  "check the copy against the brief", layer=f"{s.name if s else 'overlay'}/{L.name}")


def check_text(P, R, brief, render=True, qa_scale=0.4):
    D = P.design
    l, tp, r, b = D.safe()
    ls, ts_, rs, bs = D.safe(strict=True)
    brief_texts = [norm(x) for x in (brief.get("texts") or [])]
    brief_lines = set()
    for bt in brief.get("texts") or []:
        for ln in re.split(r"\n|(?<=[.!?])\s+", bt):
            if ln.strip():
                brief_lines.add(norm(ln))
    seen = set()
    min_px = 0.018 * min(P.W, P.H)
    for s, anc, L in text_layers(P):
        name = f"{s.name if s else 'overlay'}/{L.name}"
        txt = L.plain
        if L.L.missing:
            R.add("FAIL", "glyphs", f"missing glyphs {''.join(sorted(set(L.L.missing)))} in font for '{short(txt)}'", layer=name)
        if getattr(L.L, "overflow", False):
            R.add("FAIL", "overflow", f"a word is wider than max_width in '{short(txt)}'", layer=name)
        role = getattr(L, "text_role", "copy")
        src = getattr(L, "src", "brief")
        off = group_offset(anc)
        base = s.t0 if s else 0.0
        # --- copy vs brief
        if role == "copy" and isinstance(L, Text) and not getattr(L, "kind", "") == "counter":
            nt = norm(txt)
            if src == "brief" and brief_texts:
                if not (nt in brief_texts or nt in brief_lines or any(nt and nt in bt for bt in brief_texts)):
                    R.add("FAIL", "brief_copy", f"text not found verbatim in brief: '{short(txt)}'", layer=name)
                seen.add(nt)
            elif src == "invented":
                R.add("INFO", "brief_copy", f"[DEMO COPY] '{short(txt)}'", layer=name)
            # src="data": values and labels generated from the user's data files
        if role != "copy" or not isinstance(L, Text):
            continue
        allowed = _allowed(L, anc)
        # words of a kinetic phrase are read as one phrase (checked below), but each word still gets
        # the size, safe-area and contrast checks: slams are the biggest copy on screen and their
        # punch / hold zoom grows them after they were fitted to the frame
        in_phrase = getattr(L, "phrase_of", None) is not None
        t_in, t_out = L.reveal_window()
        t_st = L.reveal_start()
        if s is None and t_out is None:
            t_out = P.duration
        if t_out is None:
            t_out = s.dur - off
        # an exit by motion (the text flies out of frame) ends the readable window where it starts
        pk = L.position.keys
        if len(pk) >= 2:
            a_, b_ = pk[-2], pk[-1]
            if b_.t >= t_out - 0.2 and a_.t > t_in and math.hypot(b_.v[0] - a_.v[0], b_.v[1] - a_.v[1]) > 0.2 * P.W:
                t_out = min(t_out, a_.t)
        # convert to scene/abs time
        t_in_abs, t_out_abs, t_st_abs = base + off + t_in, base + off + t_out, base + off + t_st
        if s is not None:
            t_out_abs = min(t_out_abs, s.t1)
        words = max(1, len(txt.split()))
        need = max(1.2, 0.3 * words)
        readable = t_out_abs - (t_in_abs - 0.5 * max(0.0, t_in_abs - t_st_abs))
        if not in_phrase and readable + 1e-3 < need:
            R.add("FAIL", "reading_time", f"'{short(txt)}': {readable:.2f}s readable, needs {need:.2f}s ({words} words)",
                  t=t_in_abs, layer=name)
        # --- size
        sz = L.st["size"]
        sx = abs(L.scale.rest()[0])
        if sz * sx < min_px:
            R.add("WARN", "aliasing", f"copy text {sz * sx:.0f}px is small for mobile (< {min_px:.0f}px)", layer=name)
        # --- frame edge and safe zone, every 0.1 s of the readable window (persistence-aware:
        # a one-sample blip is ignored, anything held for >= 0.2 s is reported)
        if "offframe" not in allowed:
            _check_text_box(P, R, s, anc, L, txt, name, t_in_abs, t_out_abs, (l, tp, r, b), (ls, ts_, rs, bs))
        # --- contrast against the real background
        if render and "overlap" not in allowed:
            t = (t_in_abs + t_out_abs) / 2
            if 0 <= t < P.duration and not in_transition(P, t):
                m, lt, op, vis = world(P, s, anc, L, t)
                if vis and op > 0.5:
                    cr = measure_contrast(P, L, t, qa_scale)
                    if cr is not None and cr < 4.5:
                        R.add("FAIL", "contrast", f"'{short(txt)}' contrast {cr:.2f}:1 (< 4.5:1)", t=t, layer=name)
    for s_, anc, G in chains(P):
        if G.kind == "kinetic_words":
            base = (s_.t0 if s_ else 0.0) + group_offset(anc) + G.offset
            words = len(G.words)
            need = max(1.2, 0.3 * words)
            span = (G.end or G.times[-1]) - G.times[0]
            if span + 1e-3 < need:
                R.add("FAIL", "reading_time", f"kinetic phrase '{short(' '.join(G.words))}': {span:.2f}s on screen, needs "
                      f"{need:.2f}s", t=base + G.times[0], layer=G.name)
    check_occlusion(P, R)
    if brief_texts:
        for bt in brief.get("texts") or []:
            nb = norm(bt)
            if not any(nb == x or x in nb for x in seen if x):
                R.add("WARN", "brief_copy", f"brief text not used on screen: '{short(bt)}'")


def draw_order(P):
    """Flatten layers in draw order per scene: list of (order, scene, anc, layer)."""
    out = []
    k = 0
    for s, anc, l in chains(P):
        out.append((k, s, anc, l))
        k += 1
    return out


def _box(P, s, anc, l, t):
    m, lt, op, vis = world(P, s, anc, l, t)
    if not vis or op < 0.3:
        return None
    bb = l.local_bounds(lt)
    if bb is None:
        return None
    rr = skia.Matrix.Concat(m, l.matrix(lt)).mapRect(skia.Rect.MakeLTRB(*bb))
    return (rr.left(), rr.top(), rr.right(), rr.bottom())


def check_occlusion(P, R):
    """Copy text covered by a layer drawn above it (shape, image, other text)."""
    order = draw_order(P)
    reported = set()
    for k, s, anc, L in order:
        if not isinstance(L, Text) or getattr(L, "text_role", "copy") != "copy" or "overlap" in _allowed(L, anc):
            continue
        t_in, t_out = L.reveal_window()
        base = (s.t0 if s else 0.0) + group_offset(anc)
        t_out = t_out if t_out is not None else ((s.dur if s else P.duration) - group_offset(anc))
        for t in (base + t_in + 0.05, base + (t_in + t_out) / 2):
            if t >= P.duration or in_transition(P, t):
                continue
            tb = _box(P, s, anc, L, t)
            if tb is None:
                continue
            ta = max(1.0, (tb[2] - tb[0]) * (tb[3] - tb[1]))
            for k2, s2, anc2, X in order:
                if k2 <= k or s2 is not s or isinstance(X, Group) or X in anc or X.kind in (
                        "background", "comet", "line", "grid_plane", "particles", "waveform", "wire3d"):
                    continue
                if X.mask is not None and X.mask is L:
                    continue
                if getattr(X, "fill", None) is None and getattr(X, "stroke", None) is not None:
                    continue                   # an outline (ellipse around a word, frame) does not cover it
                xb = _box(P, s2, anc2, X, t)
                if xb is None:
                    continue
                ix = max(0.0, min(tb[2], xb[2]) - max(tb[0], xb[0])) * max(0.0, min(tb[3], xb[3]) - max(tb[1], xb[1]))
                if ix / ta > 0.12 and (L.uid, X.uid) not in reported:
                    reported.add((L.uid, X.uid))
                    R.add("WARN", "occlusion", f"'{short(L.plain)}' is covered {ix / ta:.0%} by '{X.name}' drawn above it",
                          t=t, layer=f"{s.name if s else 'overlay'}/{L.name}")


def measure_contrast(P, L, t, scale):
    """Worst-case contrast of a text layer against the background actually rendered under
    it. Text colour comes from the layer's declared colours (antialiased edge pixels would
    under-report contrast); the background is measured with the layer hidden."""
    vis = raw_frame(P, t, scale, 2)
    hid = raw_frame(P, t, scale, 2, hidden={L.uid})
    diff = np.abs(vis - hid).max(axis=2)
    if diff.max() < 0.05:
        return None
    mask = diff > max(0.03, 0.25 * diff.max())
    if mask.sum() < 6:
        return None
    from scipy import ndimage
    under = ndimage.binary_dilation(mask, iterations=2)
    bl = lin_lum(hid[under])
    cols = set()
    solid = L.fill is None and getattr(L, "color_prop", None) is None
    if solid:
        for g in L.L.glyphs:
            if not g.space:
                cols.add(tuple(color(g.color)))
    worst = None
    if cols:
        for c in cols:
            tl = luminance(c)
            # alpha < 1: composite over the median background
            if c[3] < 0.999:
                bm = float(np.median(bl))
                tl = tl * c[3] + bm * (1 - c[3])
            b_w = np.percentile(bl, 90) if tl < np.median(bl) else np.percentile(bl, 10)
            hi, lo = max(tl, b_w), min(tl, b_w)
            cr = (hi + 0.05) / (lo + 0.05)
            worst = cr if worst is None else min(worst, cr)
        return worst
    core = diff > np.percentile(diff[mask], 75)
    t_med = float(np.median(lin_lum(vis[core & mask]))) if (core & mask).any() else float(np.median(lin_lum(vis[mask])))
    b_w = np.percentile(bl, 90) if t_med < np.median(bl) else np.percentile(bl, 10)
    hi, lo = max(t_med, b_w), min(t_med, b_w)
    return (hi + 0.05) / (lo + 0.05)


def lin_lum(a):
    a = np.asarray(a, np.float64)
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    return lin @ np.array([0.2126, 0.7152, 0.0722])


def check_forbidden(P, R):
    D = P.design
    forb = set(D.forbidden())
    if not forb:
        return
    used = {}
    for k in P.post:
        if k in P.fx_tracks or not (P.post[k] or {}).get("track_only"):
            used.setdefault(k, "global fx")
    for s in P.scenes[1:]:
        if s.transition is not None:
            used.setdefault(s.transition.kind, f"transition into {s.name}")
            used.setdefault(s.transition.ease.spec.split("(")[0].split("_")[-1], f"transition ease into {s.name}")
    for s, anc, l in chains(P):
        nm = f"{s.name if s else 'overlay'}/{l.name}"
        used.setdefault(l.kind, nm)
        for f in l.fx:
            used.setdefault(f.kind, nm)
        if getattr(l, "motion_blur", False):
            used.setdefault("motion_blur", nm)
        if isinstance(l, Text):
            if l.typer:
                used.setdefault("typewriter", nm)
            for a in l.anims:
                used.setdefault(f"text_{a.mode}", nm)
                used.setdefault(family(a.ease.spec), nm + " text ease")
        for pn in ("position", "scale", "rotation", "opacity"):
            p = getattr(l, pn)
            for k in p.keys[1:]:
                used.setdefault(family(k.ease.spec), f"{nm}.{pn}")
    if P.motion_blur or any(s.motion_blur for s in P.scenes):
        used.setdefault("motion_blur", "render")
    for f in forb:
        for u, where in used.items():
            if u.startswith("text_") and not f.startswith("text_") and f not in ("typewriter", "scramble"):
                continue          # forbidding the 'fade' transition does not forbid text fades
            if u == f or (len(f) > 3 and f in u):
                R.add("FAIL", "forbidden", f"'{u}' is forbidden by design.yaml (used: {where})")


def family(spec):
    s = spec.lower()
    for fam in ("elastic", "bounce", "spring", "back", "linear", "hold", "steps", "expo", "cubic", "quad",
                "quart", "quint", "sine", "circ", "bezier"):
        if fam in s:
            return fam
    return s


def check_easing(P, R):
    lin = 0
    jerks = []
    fast = []
    lim = 0.12 * min(P.W, P.H)
    for s, anc, l in chains(P):
        nm = f"{s.name if s else 'overlay'}/{l.name}"
        for pn in ("position", "scale", "rotation", "opacity"):
            p = getattr(l, pn)
            ks = p.keys
            for i in range(1, len(ks)):
                # long linear drifts (progress bars, slow pans) are legitimate; short ones look mechanical
                if ks[i].ease.kind == "linear" and ks[i].v != ks[i - 1].v and 0.12 < ks[i].t - ks[i - 1].t < 2.0:
                    lin += 1
            if pn == "position" and len(ks) >= 2:
                h = 1 / 120
                for i in range(1, len(ks) - 1):
                    k = ks[i]
                    v_in = np.subtract(p.base_at(k.t), p.base_at(k.t - h)) / h
                    v_out = np.subtract(p.base_at(k.t + h), p.base_at(k.t)) / h
                    a, b = np.linalg.norm(v_in), np.linalg.norm(v_out)
                    if max(a, b) > 250 and np.linalg.norm(v_in - v_out) > 0.6 * max(a, b) and k.ease.kind != "hold":
                        jerks.append((nm, k.t + (s.t0 if s else 0)))
                for i in range(1, len(ks)):
                    t0, t1 = ks[i - 1].t, ks[i].t
                    for j in range(1, 9):
                        ta, tb = t0 + (t1 - t0) * (j - 1) / 8, t0 + (t1 - t0) * j / 8
                        d = np.linalg.norm(np.subtract(p.base_at(tb), p.base_at(ta))) / max(1e-6, tb - ta) / P.fps
                        if d > lim:
                            fast.append((nm, ta + (s.t0 if s else 0), d))
                            break
    style_linear = "linear" in [str(v) for v in P.design.motion.easing.values()]
    if lin and not style_linear:
        R.add("WARN", "easing", f"{lin} linear transform keyframe segment(s); default should be eased")
    for nm, t in jerks[:8]:
        R.add("WARN", "easing", "velocity jump at keyframe (motion hitch)", t=t, layer=nm)
    mb = P.motion_blur or any(s.motion_blur for s in P.scenes)
    smeared = {f"{s.name if s else 'overlay'}/{l.name}" for s, anc, l in chains(P) if any(f.kind == "smear" for f in l.fx)}
    for nm, t, d in fast[:8]:
        if not mb and nm not in smeared:
            R.add("WARN", "easing", f"moves {d:.0f}px/frame without motion blur (strobing risk)", t=t, layer=nm)


def check_strokes(P, R, scale=1.0):
    for s, anc, l in chains(P):
        if hasattr(l, "stroke_width") and getattr(l, "stroke", None) is not None:
            w = l.stroke_width.rest() * abs(l.scale.rest()[0])
            if 0 < w < 1.0:
                R.add("WARN", "aliasing", f"stroke {w:.2f}px is sub-pixel at final resolution (shimmer)",
                      layer=f"{s.name if s else 'overlay'}/{l.name}")


def check_camera(P, R):
    """The camera should glide, travel or follow, never wobble (user feedback 2026-10-08:
    'the camera shakes instead of moving smoothly'). Counts direction reversals of the
    on-screen camera motion and frequent zoom punches / shakes."""
    from engine.core import Pulse, _WindowWiggle
    for s in P.scenes:
        cam = s.camera
        if not cam.active:
            continue
        n = max(2, int(s.dur * P.fps))
        ts = np.linspace(0, s.dur, n)
        pos = np.array([cam.pos.at(t) for t in ts], float)
        z = np.array([cam.zoom.at(t) for t in ts], float)
        rot = np.array([cam.rotation.at(t) for t in ts], float)
        half = math.hypot(P.W, P.H) / 2
        vel = {"pan x": np.diff(pos[:, 0]) * z[1:], "pan y": np.diff(pos[:, 1]) * z[1:],
               "zoom": np.diff(z) / z[1:] * half, "roll": np.radians(np.diff(rot)) * half}
        rev = 0
        gap = max(1, int(0.25 * P.fps))
        for ax, v in vel.items():
            idx = np.where(np.abs(v) > 0.25)[0]       # px per frame: below this the camera is at rest
            sgn = np.sign(v[idx])
            # a turn-around without coming to rest (opposite moves < 0.25 s apart) reads as wobble;
            # a designed move after a settle (zoom in, hold, zoom out) does not
            rev += int(np.sum((sgn[1:] != sgn[:-1]) & (np.diff(idx) <= gap)))
        rate = rev / max(s.dur, 1e-6)
        if rate > 0.25 and rev >= 2:
            R.add("WARN", "camera", f"camera turns around {rev} times in {s.dur:.1f}s (reads as wobble/shake); "
                  "use glide/travel/follow, drift only with period >= 16 s", t=s.t0)
        shakes = [m for m in cam.pos.mods if isinstance(m, _WindowWiggle)]
        punches = [m for m in cam.zoom.mods if isinstance(m, Pulse)]
        if shakes:
            R.add("WARN", "camera", f"{len(shakes)} camera shake(s): only for impacts the brief asks for", t=s.t0)
        if len(punches) > max(2, s.dur / 4):
            R.add("WARN", "camera", f"{len(punches)} zoom punches in {s.dur:.1f}s: frequent punches read as shake", t=s.t0)


def check_spectrum(P, R, mix_path):
    """Spectral balance of the mix against the analysed references (motion-lib INDEX):
    references keep the sub (< 60 Hz) at -6..-37 dB of total power and the mids (250 Hz-2 kHz)
    at -2..-5 dB; our iteration-2 beds had sub -3 dB and mids -17 dB (muddy, dated)."""
    if not mix_path or not os.path.exists(mix_path):
        return
    import analyze
    sr = 22050
    x = analyze._audio(mix_path, sr)
    if len(x) < sr:
        return
    _, S, _ = analyze._onset_env(x, sr)
    f = np.fft.rfftfreq(1024, 1 / sr)
    Pw = (S ** 2).sum(axis=0)
    band = lambda a, b: 10 * np.log10(Pw[(f >= a) & (f < b)].sum() / Pw.sum() + 1e-12)
    sub, mid, pres = band(0, 60), band(250, 2000), band(2000, 6000)
    bass, air = band(60, 250), band(6000, 11025)
    R.add("INFO", "spectrum", f"power share, dB: sub {sub:.0f} / bass {bass:.0f} / mids {mid:.0f} / presence {pres:.0f} / "
          f"air {air:.0f} (references: sub -6..-37, mids -2..-5, presence -15..-18, air -17..-24); judge by ear")
    if sub > -6:
        R.add("WARN", "spectrum", f"sub (< 60 Hz) is {sub:.1f} dB of the mix (references -6..-37): muddy; "
              "lower bass/kick/impacts or keep sound.bed_eq on")
    if mid < -12:
        R.add("WARN", "spectrum", f"mids (250 Hz-2 kHz) at {mid:.1f} dB (references -2..-5): the bed sounds hollow")
    if pres < -24:
        R.add("WARN", "spectrum", f"presence (2-6 kHz) at {pres:.1f} dB (references -15..-18): dull")


def check_sound_density(P, R):
    """Sound should follow the pulse, not every visual event: references put a sound under
    20-55 % of visual hits; ours had ~70 % and read as 'force-fitted' (feedback 2026-10-08)."""
    snd = P.design.sound or {}
    ev = [e for e in P.all_events() if e.kind not in ("music", "marker")]
    if not ev or P.duration <= 0:
        return
    rate = len(ev) / P.duration
    cap = float(snd.get("max_sfx_per_s", 1.0))
    manual = [e for e in ev if getattr(e, "source", "") != "auto"]
    R.add("INFO", "sound", "sound effects: " + ", ".join(f"{e.kind} {e.t:.2f}s" + (" (accent)" if e.accent else "")
                                                       for e in sorted(manual, key=lambda e: e.t)[:24])
          + (f" + {len(ev) - len(manual)} automatic" if len(ev) > len(manual) else ""))
    if rate > cap:
        R.add("WARN", "sound", f"{len(ev)} sound effects in {P.duration:.1f}s ({rate:.1f}/s > {cap:g}/s): keep SFX "
              "for transitions and key moments, let small moves ride the music")


def check_sync(P, R, mix_path=None):
    fr = 1.0 / P.fps
    snd = P.design.sound or {}
    events = P.all_events()
    if snd.get("music", True):
        for e in events:
            if e.accent:
                d = abs(e.t - P.snap(e.t, 2))
                if d > fr + 1e-6:
                    R.add("FAIL", "sync", f"accent '{e.kind}' {d * 1000:.0f} ms off the beat grid ({P.bpm:g} BPM)", t=e.t)
        for s in P.scenes[1:]:
            st = s.t0
            d = abs(st - P.snap(st, 2))
            if d > 2 * fr:
                R.add("WARN", "sync", f"scene '{s.name}' change is {d * 1000:.0f} ms off the beat grid", t=st)
    if mix_path and os.path.exists(mix_path):
        sys.path.insert(0, HERE)
        from audio.dsp import read_wav
        x, sr = read_wav(mix_path)
        m = np.abs(x).mean(axis=1)
        hop = int(sr / 200)
        env = np.array([m[i:i + hop].max() for i in range(0, len(m) - hop, hop)])
        perc = {"click", "type", "tick", "impact", "hit", "pop", "blip", "glitch", "kick", "crash", "sub_hit", "sub"}
        cands = [e for e in events if e.kind in perc]
        if len(cands) > 40:
            idx = np.linspace(0, len(cands) - 1, 40).astype(int)
            cands = [cands[i] for i in idx]
        miss = 0
        for e in cands:
            i = int(e.t * 200)
            pre = env[max(0, i - 6):max(1, i - 1)].mean() if i > 1 else 0
            post = env[i:i + 7].max() if i < len(env) else 0
            if post < pre * 1.15 + 1e-4:
                miss += 1
        if cands and miss / len(cands) > 0.25:
            R.add("WARN", "sync", f"{miss}/{len(cands)} percussive SFX have no clear transient at their frame")


def check_loudness(P, R, audio_dir, video=None):
    """Measured on the delivered file when there is one (AAC can raise the true peak)."""
    snd = P.design.sound or {}
    if video and os.path.exists(video):
        sys.path.insert(0, HERE)
        from audio.master import ffmpeg_loudness
        m = ffmpeg_loudness(video)
        if m.get("I") is not None:
            tgt = float(snd.get("loudness", -14))
            tp = float(snd.get("true_peak", -1))
            if abs(m["I"] - tgt) > 0.5:
                R.add("FAIL", "loudness", f"{os.path.basename(video)}: integrated {m['I']} LUFS, target {tgt}")
            if m.get("TP") is not None and m["TP"] > tp + 0.05:
                R.add("FAIL", "loudness", f"{os.path.basename(video)}: true peak {m['TP']} dBTP > {tp}")
            R.add("INFO", "loudness", f"{os.path.basename(video)}: {m['I']} LUFS, true peak {m.get('TP')} dBTP "
                  f"(target {tgt} / {tp})")
            return
    rp = os.path.join(audio_dir, "audio_report.json")
    if not os.path.exists(rp):
        R.add("WARN", "loudness", "no audio report (audio not rendered)")
        return
    rep = json.load(open(rp))
    snd = P.design.sound or {}
    tgt = float(snd.get("loudness", -14))
    tp = float(snd.get("true_peak", -1))
    I_ = rep.get("ffmpeg_I", rep.get("lufs"))
    TP = rep.get("ffmpeg_TP", rep.get("true_peak_db"))
    if I_ is None or abs(I_ - tgt) > 0.5:
        R.add("FAIL", "loudness", f"integrated {I_} LUFS, target {tgt}")
    if TP is None or TP > tp + 0.05:
        R.add("FAIL", "loudness", f"true peak {TP} dBTP > {tp}")
    for w in rep.get("warnings", []):
        R.add("WARN", "audio", w)


def check_flicker(P, R, video):
    if not video or not os.path.exists(video):
        return
    W = 96
    info = probe(video)
    vs = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), None)
    if not vs:
        return
    H = int(round(W * vs["height"] / vs["width"] / 2) * 2)
    fps = eval(vs["r_frame_rate"])
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", f"scale={W}:{H}", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, H, W).astype(np.float32) / 255
    if len(fr) < 4:
        return
    mean = fr.mean(axis=(1, 2))
    d = np.abs(np.diff(mean))
    cuts = set()
    for s in P.scenes:
        cuts.add(int(round(s.t0 * fps)))
        if s.transition:
            for k in range(int(s.t0 * fps) - 1, int((s.t0 + s.transition.dur) * fps) + 2):
                cuts.add(k)
    for name, tr in P.fx_tracks.items():
        for k in range(len(fr)):
            if tr.at(k / fps) > 0.05:
                cuts.update({k - 1, k, k + 1})
    # designed hits (sounded events, flash frames, word slams) are not flicker
    for e in P.all_events():
        k = int(round(e.t * fps))
        cuts.update(range(k - 2, k + 3))
    for s_, anc, l in chains(P):
        if l.kind in ("background", "kinetic_words") or l.name.startswith(("Flash", "Word")):
            base = (s_.t0 if s_ else 0.0) + group_offset(anc)
            for tt in (l.start, l.end):
                if tt is not None:
                    k = int(round((base + tt) * fps))
                    cuts.update(range(k - 2, k + 3))
    jumps = [i for i in np.nonzero(d > 0.12)[0] if i + 1 not in cuts and i not in cuts]
    for i in jumps[:5]:
        R.add("WARN", "flicker", f"global brightness jump {d[i]:.2f} between frames", t=(i + 1) / fps)
    gy, gx = 6, 6
    th, tw = H // gy, W // gx
    tiles = fr[:, :th * gy, :tw * gx].reshape(len(fr), gy, th, gx, tw).mean(axis=(2, 4))
    dd = np.diff(tiles, axis=0)
    osc = (np.sign(dd[1:]) * np.sign(dd[:-1]) < 0) & (np.abs(dd[1:]) > 0.06) & (np.abs(dd[:-1]) > 0.06)
    hits = np.nonzero(osc.reshape(len(osc), -1).any(axis=1))[0]
    hits = [i for i in hits if (i + 1) not in cuts and (i + 2) not in cuts]
    if len(hits) > 2:
        R.add("WARN", "flicker", f"{len(hits)} frames with oscillating tile brightness (flicker), first at {(hits[0] + 1) / fps:.2f}s",
              t=(hits[0] + 1) / fps)


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                       capture_output=True, text=True)
    return json.loads(r.stdout or "{}")


def check_format(P, R, brief, video, final):
    end = max((sc.t1 for sc in P.scenes), default=0.0)
    if P.scenes and P.duration - end > 1.0 / P.fps + 1e-6:
        R.add("FAIL", "format", f"scenes end at {end:.2f}s but the video runs {P.duration:.2f}s: empty frames at the end")
    gaps = [(a.t1, b.t0) for a, b in zip(P.scenes, P.scenes[1:]) if b.t0 - a.t1 > 1.0 / P.fps + 1e-6]
    for a, b in gaps:
        R.add("FAIL", "format", f"gap between scenes {a:.2f}-{b:.2f}s (background only)", t=a)
    bd = brief.get("duration") or getattr(P, "target_duration", None)
    if bd and abs(float(bd) - P.duration) > 0.5:
        R.add("FAIL", "format", f"duration {P.duration:.1f}s vs brief {bd}s")
    if brief.get("aspect") and brief["aspect"] != P.aspect:
        R.add("FAIL", "format", f"aspect {P.aspect} vs brief {brief['aspect']}")
    if video and os.path.exists(video):
        info = probe(video)
        vs = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), None)
        a = next((s for s in info.get("streams", []) if s["codec_type"] == "audio"), None)
        if vs is None:
            R.add("FAIL", "format", "no video stream")
            return
        if final:
            if min(vs["width"], vs["height"]) != 1080:
                R.add("FAIL", "format", f"final short side {min(vs['width'], vs['height'])}, expected 1080")
            if abs(eval(vs["r_frame_rate"]) - P.fps) > 0.01:
                R.add("FAIL", "format", f"final fps {vs['r_frame_rate']}, expected {P.fps}")
        if a is None:
            R.add("FAIL", "format", "no audio stream")
        elif int(a.get("sample_rate", 0)) != 48000 or int(a.get("channels", 0)) != 2:
            R.add("FAIL", "format", f"audio {a.get('sample_rate')} Hz x{a.get('channels')}, expected 48000 x2")
        dur = float(info.get("format", {}).get("duration", 0))
        if abs(dur - P.duration) > 0.15:
            R.add("WARN", "format", f"file duration {dur:.2f}s vs project {P.duration:.2f}s")


DYN_DEFAULTS = {"calm": {"hit_interval": 1.6, "max_still": 2.0, "static_max": 0.25, "max_hold": 1.4},
                "medium": {"hit_interval": 1.0, "max_still": 1.2, "static_max": 0.12, "max_hold": 0.9},
                "fast": {"hit_interval": 0.7, "max_still": 0.8, "static_max": 0.06, "max_hold": 0.6}}


def check_dynamics(P, R, video):
    """Is the video alive? Measured on the rendered file (analyze.metrics), compared with
    design.yaml `dynamics` (or tempo defaults). Frozen time FAILs; too few big hits WARNs
    (what counts as a hit depends on the look, so it stays advisory)."""
    if not video or not os.path.exists(video):
        return
    from analyze import metrics
    m = metrics(video)
    D = P.design
    tgt = dict(DYN_DEFAULTS.get(D.motion.tempo, DYN_DEFAULTS["medium"]))
    tgt.update({k: v for k, v in (D.dynamics or {}).items() if k in tgt})
    R.add("INFO", "dynamics", f"frozen {m['static_pct']}% of the time (target <= {tgt['static_max'] * 100:.0f}%), longest "
          f"freeze {m['longest_still_s']}s (<= {tgt['max_still']}s), {m['hits']} big hits in {m['duration_s']}s "
          f"(median gap {m['hit_interval_s']}s, target ~{tgt['hit_interval']}s), motion density {m['motion_density_pct']}%")
    st = m["static_pct"] / 100
    if st > tgt["static_max"] * 1.6 + 0.03:
        R.add("FAIL", "dynamics", f"the picture is frozen {m['static_pct']}% of the time (target <= {tgt['static_max'] * 100:.0f}%): "
              "add continuous motion (camera drift/push, hold zoom, a moving secondary element)")
    elif st > tgt["static_max"]:
        R.add("WARN", "dynamics", f"frozen {m['static_pct']}% of the time, target <= {tgt['static_max'] * 100:.0f}%")
    if m["longest_still_s"] > tgt["max_still"] * 2:
        R.add("FAIL", "dynamics", f"the picture freezes for {m['longest_still_s']}s (target <= {tgt['max_still']}s)")
    elif m["longest_still_s"] > tgt["max_still"]:
        R.add("WARN", "dynamics", f"longest freeze {m['longest_still_s']}s > {tgt['max_still']}s")
    expected = m["duration_s"] / tgt["hit_interval"]
    if m["hits"] < expected * 0.5:
        R.add("WARN", "dynamics", f"{m['hits']} big hits in {m['duration_s']}s, ~{expected:.0f} expected at one per "
              f"{tgt['hit_interval']}s: slams, cuts, flashes, punches, whips land the beats")


def check_look(P, R, video, n=16):
    """Does the picture have light and colour, or is it grey-on-grey? Measured on frames of
    the rendered file: the darkest and lightest 1% of pixels (a designed frame has real darks
    and real lights) and how often the saturated accent is on screen. WARN only: a deliberately
    soft, low-contrast look exists, but it must be a decision, not an accident."""
    if not video or not os.path.exists(video):
        return
    try:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                                   capture_output=True, text=True).stdout.strip() or 0)
    except Exception:
        return
    if dur <= 0:
        return
    w = 480
    h = int(round(w * P.H / P.W / 2)) * 2
    ts = [dur * (k + 0.5) / n for k in range(n)]
    flat, lifted, dull, accent_frames = [], [], [], 0
    dark_design = luminance(color("bg")) < 0.5
    has_accent = "accent" in P.design.palette
    for t in ts:
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
                              "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        if len(raw) != w * h * 3:
            continue
        img = np.frombuffer(raw, np.uint8).reshape(h, w, 3).astype(np.float32) / 255.0
        lum = img @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        p1, p99 = np.percentile(lum, 1), np.percentile(lum, 99)
        if p99 - p1 < 0.55:
            flat.append((t, p1, p99))
        if dark_design and p1 > 0.09:
            lifted.append((t, p1))
        if not dark_design and p99 < 0.86:
            dull.append((t, p99))
        mx, mn = img.max(-1), img.min(-1)
        sat = (mx - mn) / np.maximum(mx, 1e-3)
        if ((sat > 0.45) & (mx > 0.35)).mean() > 0.002:
            accent_frames += 1
    if len(flat) >= max(2, n // 4):
        ex = ", ".join(f"{t:.1f}s ({a:.2f}-{b:.2f})" for t, a, b in flat[:4])
        R.add("WARN", "look", f"{len(flat)} of {n} sampled frames are flat: the darkest and lightest 1% of pixels are less "
              f"than 0.55 apart in luminance, e.g. {ex}. Give the frame a light source and a real dark: KeyLight, "
              f"a darker ground, a white object, a soft shadow (references/art_direction.md, Light and material)", t=flat[0][0])
    if len(lifted) >= max(2, n // 4):
        R.add("WARN", "look", f"lifted blacks in {len(lifted)} of {n} frames (darkest 1% at {lifted[0][1]:.2f}, near-black is "
              f"< 0.06): a dark design without a real black looks washed out", t=lifted[0][0])
    if len(dull) >= max(2, n // 4):
        R.add("WARN", "look", f"no real white in {len(dull)} of {n} frames (lightest 1% at {dull[0][1]:.2f}): a light design "
              f"still needs one bright object or highlight", t=dull[0][0])
    if has_accent and accent_frames < n * 0.4:
        R.add("WARN", "look", f"the saturated accent is on screen in {accent_frames} of {n} sampled frames: the film reads "
              f"grey. Spend the accent on the moving element, the key word or the light")
    R.add("INFO", "look", f"{n} frames: {len(flat)} flat, {len(lifted) if dark_design else len(dull)} without a real "
          f"{'black' if dark_design else 'white'}, accent visible in {accent_frames}")


def check_lint(P, R, final):
    for m in P.design.lint():
        R.add("WARN", "lint", f"design.yaml: {m}")
    for w in sorted(set(F.WARNINGS)):
        R.add("WARN", "fonts", w)
    if final and getattr(P, "render_ss", 2) < 2:
        R.add("FAIL", "aliasing", "final render without 2x supersampling")


# ----------------------------------------------------------------------------- helpers

def norm(s):
    s = strip_markup(str(s)).replace(" ", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def short(s, n=48):
    s = s.replace("\n", " / ")
    return s if len(s) <= n else s[: n - 1] + "…"


def fmt_box(b):
    return "(" + ", ".join(f"{v:.0f}" for v in b) + ")"


def load_brief(root):
    import yaml
    p = os.path.join(root, "brief.yaml")
    if os.path.exists(p):
        return yaml.safe_load(open(p, encoding="utf-8")) or {}
    return {}


def run(root, video=None, final=False, render=True, P=None, out_md=None):
    root = os.path.abspath(root)
    if P is None:
        P = load_project(os.path.join(root, "video.py"))
    brief = load_brief(root)
    R = Report()
    check_lint(P, R, final)
    check_language(P, R, brief)
    check_text(P, R, brief, render=render)
    check_forbidden(P, R)
    check_easing(P, R)
    check_choreography(P, R)
    check_allowances(P, R)
    check_camera(P, R)
    check_strokes(P, R)
    check_sound_density(P, R)
    audio_dir = os.path.join(root, "out", "audio")
    check_sync(P, R, os.path.join(audio_dir, "mix.wav"))
    check_spectrum(P, R, os.path.join(audio_dir, "mix.wav"))
    check_loudness(P, R, audio_dir, video)
    check_flicker(P, R, video)
    check_dynamics(P, R, video)
    check_look(P, R, video)
    check_format(P, R, brief, video, final)
    out_md = out_md or os.path.join(root, "out", "qa_final.md" if final else "qa_preview.md")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    order = {"FAIL": 0, "WARN": 1, "INFO": 2}
    items = sorted(R.items, key=lambda i: (order[i["level"]], i["check"], i["t"] or 0))
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(f"# QA {'final' if final else 'preview'}: {R.status}\n\n")
        if not items:
            f.write("- [PASS] all checks\n")
        for i in items:
            tt = f" @{i['t']:.2f}s" if i["t"] is not None else ""
            ly = f" [{i['layer']}]" if i["layer"] else ""
            f.write(f"- [{i['level']}] {i['check']}{tt}{ly}: {i['msg']}\n")
    with open(out_md.replace(".md", ".json"), "w", encoding="utf-8") as f:
        json.dump({"status": R.status, "items": items}, f, ensure_ascii=False, indent=1)
    return R.status, items, out_md


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--video")
    ap.add_argument("--final", action="store_true")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()
    st, items, path = run(a.project, a.video, a.final, not a.no_render)
    print(open(path, encoding="utf-8").read())
    sys.exit(1 if st == "FAIL" else 0)
