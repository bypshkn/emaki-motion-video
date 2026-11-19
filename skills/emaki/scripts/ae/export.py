"""After Effects backend: Project timeline + design.yaml -> build_project.jsx (ExtendScript).

Python converts everything into a DATA object (comps, layers, native keyframes with
temporal ease speed/influence computed from the same easing curves the Python renderer
uses), and a static runtime (runtime.jsx) builds the AE project from it.

What maps natively: precomp per scene, text layers (animators via Expression Selectors that
reproduce the per-unit timing exactly), shape layers (rect/ellipse/polystar/paths, trim,
fill/stroke), solids + Gradient Ramp, images, cameras (3D layers), masks and track mattes,
blend modes, per-layer blur/shadow/glow, most transitions, grain/vignette/glow/scanlines,
audio stems + markers, a CONTROLS null with sliders.
What is baked (ProRes 4444 with alpha, labelled [BAKED]): particles, noise/pattern/conic
fills, outline-draw text, glitch windows. Everything baked is listed in README.md.
"""
import json
import math
import os
import shutil
import subprocess

import numpy as np

from engine.core import (Group, Layer, Prop, Scene, color, skia, Blur, DropShadow, Glow, Ctx, CURRENT)
from engine.easing import Ease
from engine.layers.text import Text, TextOnPath, DynamicText, parse_markup
from engine.layers.shape import Shape, Rect, Ellipse, Polygon, Star, Line, Arc, PathShape, Morph
from engine.layers.fill import Solid, Linear, Radial, Conic, Noise, Pattern, Background
from engine.layers.image import Image, Svg
from engine.layers.particles import Particles
from engine.layers.data import Counter
from engine import transitions as TR

HERE = os.path.dirname(os.path.abspath(__file__))
LABEL = {"text": 2, "shape": 8, "solid": 12, "image": 3, "precomp": 15, "fx": 5, "control": 1,
         "audio": 6, "camera": 4, "baked": 11, "matte": 10}
BLEND = {"normal": "NORMAL", "multiply": "MULTIPLY", "screen": "SCREEN", "overlay": "OVERLAY", "add": "ADD",
         "darken": "DARKEN", "lighten": "LIGHTEN", "color_dodge": "COLOR_DODGE", "color_burn": "COLOR_BURN",
         "soft_light": "SOFT_LIGHT", "hard_light": "HARD_LIGHT", "difference": "DIFFERENCE",
         "exclusion": "EXCLUSION", "hue": "HUE", "saturation": "SATURATION", "color": "COLOR",
         "luminosity": "LUMINOSITY"}


# ----------------------------------------------------------------------------- easing -> AE

JS_EASE_LIB = r"""
function mvBez(x1,y1,x2,y2,u){if(u<=0)return 0;if(u>=1)return 1;var cx=3*x1,bx=3*(x2-x1)-cx,ax=1-cx-bx,cy=3*y1,by=3*(y2-y1)-cy,ay=1-cy-by;var s=u;for(var i=0;i<8;i++){var x=((ax*s+bx)*s+cx)*s-u;var d=(3*ax*s+2*bx)*s+cx;if(Math.abs(x)<1e-6||Math.abs(d)<1e-6)break;s-=x/d;}return((ay*s+by)*s+cy)*s;}
function mvSpring(k,c,m,u){if(u<=0)return 0;if(u>=1)return 1;var w0=Math.sqrt(k/m),z=c/(2*Math.sqrt(k*m));var st,x;function f(t){if(z<1){var wd=w0*Math.sqrt(1-z*z);return 1-Math.exp(-z*w0*t)*(Math.cos(wd*t)+(z*w0)/wd*Math.sin(wd*t));}else if(z==1){return 1-Math.exp(-w0*t)*(1+w0*t);}else{var r1=-w0*(z-Math.sqrt(z*z-1)),r2=-w0*(z+Math.sqrt(z*z-1));var c2=(0-r1)/(r2-r1),c1=-1-c2;return 1+c1*Math.exp(r1*t)+c2*Math.exp(r2*t);}}
if(z<1){st=-Math.log(0.001)/(z*w0);}else if(z==1){st=9/w0;}else{st=-Math.log(0.001)/Math.abs(-w0*(z-Math.sqrt(z*z-1)));}var e=f(st);var v=f(u*st)/e;if(u>0.95){var w=(u-0.95)/0.05;v=v*(1-w)+w;}return v;}
function mvElasticOut(a,p,u){if(u<=0)return 0;if(u>=1)return 1;a=Math.max(1,a);var s=p/(2*Math.PI)*Math.asin(1/a);return a*Math.pow(2,-10*u)*Math.sin((u-s)*2*Math.PI/p)+1;}
function mvElastic(mode,a,p,u){if(mode=="out")return mvElasticOut(a,p,u);if(mode=="in")return 1-mvElasticOut(a,p,1-u);return u<0.5?(1-mvElasticOut(a,p,1-2*u))/2:(1+mvElasticOut(a,p,2*u-1))/2;}
function mvBounceOut(u){var n1=7.5625,d1=2.75;if(u<1/d1)return n1*u*u;if(u<2/d1){u-=1.5/d1;return n1*u*u+0.75;}if(u<2.5/d1){u-=2.25/d1;return n1*u*u+0.9375;}u-=2.625/d1;return n1*u*u+0.984375;}
function mvBounce(mode,u){if(mode=="out")return mvBounceOut(u);if(mode=="in")return 1-mvBounceOut(1-u);return u<0.5?(1-mvBounceOut(1-2*u))/2:(1+mvBounceOut(2*u-1))/2;}
"""


def js_ease(e):
    """JS expression (string) computing eased progress of variable `u` for Ease e."""
    if e.kind == "linear":
        return "Math.max(0,Math.min(1,u))"
    if e.kind == "hold":
        return "(u>=1?1:0)"
    if e.bezier is not None:
        x1, y1, x2, y2 = e.bezier
        return f"mvBez({x1:g},{y1:g},{x2:g},{y2:g},u)"
    p = e.params
    t = p.get("type")
    if t == "spring":
        return f"mvSpring({p['stiffness']:g},{p['damping']:g},{p['mass']:g},u)"
    if t == "elastic":
        return f"mvElastic('{p['mode']}',{p['amp']:g},{p['period']:g},u)"
    if t == "bounce":
        return f"mvBounce('{p['mode']}',u)"
    if t == "steps":
        return f"(u>=1?1:Math.floor(u*{p['n']})/{p['n']})"
    return "u"


def _vec(v):
    return list(v) if isinstance(v, (tuple, list)) else [v]


def _numeric(v):
    return isinstance(v, (int, float)) or (isinstance(v, (list, tuple)) and all(isinstance(x, (int, float)) for x in v))


def bez_eases(cp, v0, v1, T, ndim):
    x1, y1, x2, y2 = cp
    x1 = min(max(x1, 0.001), 1.0)
    x2 = min(max(x2, 0.0), 0.999)
    if not (_numeric(v0) and _numeric(v1)):
        # shapes/colors: AE uses one ease; keep the timing (influence), zero speed
        return [[0.0, max(0.1, min(100.0, x1 * 100))]], [[0.0, max(0.1, min(100.0, (1 - x2) * 100))]]
    a, b = _vec(v0), _vec(v1)
    out, inn = [], []
    for d in range(ndim):
        dv = (b[d] - a[d]) if d < len(a) else 0.0
        avg = dv / T if T > 0 else 0.0
        out.append([y1 / x1 * avg, max(0.1, min(100.0, x1 * 100))])
        inn.append([(1 - y2) / (1 - x2) * avg, max(0.1, min(100.0, (1 - x2) * 100))])
    return out, inn


def K(prop, conv=None, t_off=0.0, ndim=None, comp=None, notes=None, name=""):
    """Prop -> AE keyframe data {v} | {k:[...], expr}. Values pass through conv."""
    conv = conv or (lambda v: v)
    if prop is None:
        return None
    if prop.fn is not None:
        if prop.ae_expr:
            return {"v": conv(prop.at(0)), "expr": prop.ae_expr}
        if notes is not None:
            notes.append(f"[APPROX] {name}: procedural driver has no AE expression; static value used")
        return {"v": conv(prop.at(0))}
    if not prop.keys:
        d = {"v": conv(prop.value)}
    else:
        ks = prop.keys
        vals = [conv(k.v) for k in ks]
        nd = ndim or len(_vec(vals[0]))
        rows = []
        for i, k in enumerate(ks):
            rows.append({"t": round(k.t + t_off, 5), "v": vals[i], "in": "LINEAR", "out": "LINEAR",
                         "ie": None, "oe": None})
        segs = []
        for i in range(1, len(ks)):
            e = ks[i].ease
            T = ks[i].t - ks[i - 1].t
            if e.kind == "hold":
                rows[i - 1]["out"] = "HOLD"
            elif e.kind == "linear":
                pass
            elif e.bezier is not None:
                oe, ie = bez_eases(e.bezier, vals[i - 1], vals[i], T, nd)
                rows[i - 1]["out"] = "BEZIER"
                rows[i - 1]["oe"] = oe
                rows[i]["in"] = "BEZIER"
                rows[i]["ie"] = ie
            else:
                segs.append((ks[i - 1].t + t_off, ks[i].t + t_off, i, i + 1, js_ease(e)))
        d = {"k": rows}
        if segs:
            code = ["var u, v = value;"]
            for t0, t1, a, b, fn in segs:
                code.append(f"if (time >= {t0:.5f} && time < {t1:.5f}) {{ u = (time - {t0:.5f}) / {t1 - t0:.5f}; "
                            f"var p = {fn}; v = add(key({a}).value, mul(sub(key({b}).value, key({a}).value), p)); }}")
            code.append("v;")
            d["expr"] = JS_EASE_LIB + "\n".join(code)
    mods = [m for m in prop.mods if hasattr(m, "ae_expression")]
    if mods:
        base = d.get("expr")
        wig = " ".join(f"v = add(v, sub({m.ae_expression()}, value));" for m in mods)
        if base:
            d["expr"] = base[:-2] + "\n" + wig + "\nv;"
        else:
            d["expr"] = "var v = value; " + wig + " v;"
    return d


def rgb(c):
    c = color(c)
    return [round(c[0], 4), round(c[1], 4), round(c[2], 4)]


# ----------------------------------------------------------------------------- path conversion

def ae_shape(path):
    """skia.Path -> list of {v, i, o, c} (AE Shape: vertices, in/out tangents, closed)."""
    shapes = []
    it = skia.Path.Iter(path, False)
    cur = None
    while True:
        verb, pts = it.next()
        if verb == skia.Path.Verb.kDone_Verb:
            break
        if verb == skia.Path.Verb.kMove_Verb:
            if cur and len(cur["v"]) > 0:
                shapes.append(cur)
            p = pts[0]
            cur = {"v": [[p.x(), p.y()]], "i": [[0, 0]], "o": [[0, 0]], "c": False}
        elif verb == skia.Path.Verb.kLine_Verb:
            p = pts[1]
            cur["v"].append([p.x(), p.y()])
            cur["i"].append([0, 0])
            cur["o"].append([0, 0])
        elif verb in (skia.Path.Verb.kQuad_Verb, skia.Path.Verb.kConic_Verb):
            if verb == skia.Path.Verb.kConic_Verb:
                quads = skia.Path.ConvertConicToQuads(pts[0], pts[1], pts[2], it.conicWeight(), 2)
                segs = [(quads[k], quads[k + 1], quads[k + 2]) for k in range(0, len(quads) - 1, 2)]
            else:
                segs = [(pts[0], pts[1], pts[2])]
            for p0, q, p1 in segs:
                c1 = [p0.x() + 2 / 3 * (q.x() - p0.x()), p0.y() + 2 / 3 * (q.y() - p0.y())]
                c2 = [p1.x() + 2 / 3 * (q.x() - p1.x()), p1.y() + 2 / 3 * (q.y() - p1.y())]
                lv = cur["v"][-1]
                cur["o"][-1] = [c1[0] - lv[0], c1[1] - lv[1]]
                cur["v"].append([p1.x(), p1.y()])
                cur["i"].append([c2[0] - p1.x(), c2[1] - p1.y()])
                cur["o"].append([0, 0])
        elif verb == skia.Path.Verb.kCubic_Verb:
            p0, c1, c2, p1 = pts
            lv = cur["v"][-1]
            cur["o"][-1] = [c1.x() - lv[0], c1.y() - lv[1]]
            cur["v"].append([p1.x(), p1.y()])
            cur["i"].append([c2.x() - p1.x(), c2.y() - p1.y()])
            cur["o"].append([0, 0])
        elif verb == skia.Path.Verb.kClose_Verb:
            if cur:
                cur["c"] = True
                if len(cur["v"]) > 1 and abs(cur["v"][0][0] - cur["v"][-1][0]) < 1e-3 and abs(cur["v"][0][1] - cur["v"][-1][1]) < 1e-3:
                    cur["i"][0] = cur["i"][-1]
                    cur["v"].pop()
                    cur["i"].pop()
                    cur["o"].pop()
                shapes.append(cur)
                cur = None
    if cur and len(cur["v"]) > 0:
        shapes.append(cur)
    for s in shapes:
        for k in ("v", "i", "o"):
            s[k] = [[round(a, 3), round(b, 3)] for a, b in s[k]]
    return shapes


# ----------------------------------------------------------------------------- exporter

class Exporter:
    def __init__(self, P, root, version=None, audio=None, log=print, budget=None, t_call=None):
        import time as _t
        self.budget = budget
        self.t_call = t_call or _t.perf_counter()
        self.P = P
        self.root = root
        self.out = os.path.join(root, "out", "ae")
        brief_v = None
        try:
            import yaml
            bp = os.path.join(root, "brief.yaml")
            if os.path.exists(bp):
                brief_v = (yaml.safe_load(open(bp, encoding="utf-8")) or {}).get("ae_version")
        except Exception:
            pass
        self.version = float(version or brief_v or 24.0)
        self.audio = audio
        self.log = log
        self.notes = []
        self.baked = []
        self.fonts = set()
        self.names = {}
        self.exported = {}
        self.main_name = (P.meta.get("name") or os.path.basename(root) or "Main").replace('"', "")[:60]

    # -- helpers
    def uname(self, comp, name):
        k = (comp, name)
        n = self.names.get(k, 0)
        self.names[k] = n + 1
        return name if n == 0 else f"{name} {n + 1}"

    def transform(self, l, t_off=0.0, anchor_shift=(0.0, 0.0), is_text=False):
        pos = l.position
        tr = {}
        px = Prop(0.0)
        py = Prop(0.0)
        if pos.keys:
            for k in pos.keys:
                px.keys.append(type(k)(k.t, k.v[0], k.ease))
                py.keys.append(type(k)(k.t, k.v[1], k.ease))
        else:
            px.value, py.value = pos.value[0], pos.value[1]
        px.fn = (lambda t, _p=pos: _p.at(t)[0]) if pos.fn else None
        py.fn = (lambda t, _p=pos: _p.at(t)[1]) if pos.fn else None
        px.mods = pos.mods
        py.mods = []
        follow = l.ae.get("follow") if isinstance(l.ae, dict) else None
        if follow is not None and follow.uid in self.exported:
            ln = self.exported[follow.uid]
            base = (f'var g = thisComp.layer("{ln}").content("Shape"); '
                    f'var e = Math.max(0.0001, Math.min(1, g.content("Trim Paths 1").end / 100)); '
                    f'var pt = g.content("Path 1").path.pointOnPath(e); ')
            tr["x"] = {"v": 0.0, "expr": base + "pt[0];"}
            tr["y"] = {"v": 0.0, "expr": base + "pt[1];"}
            self.notes.append(f"[APPROX] {l.name}: follows '{ln}' via pointOnPath (AE samples the path parametrically)")
        else:
            tr["x"] = K(px, None, t_off, 1, notes=self.notes, name=f"{l.name}.x")
            tr["y"] = K(py, None, t_off, 1, notes=self.notes, name=f"{l.name}.y")
        ax, ay = l.anchor.rest()
        tr["anchor"] = [ax - anchor_shift[0], ay - anchor_shift[1], 0]
        tr["scale"] = K(l.scale, lambda v: [v[0] * 100, v[1] * 100, 100] if isinstance(v, tuple) else [v * 100, v * 100, 100],
                        t_off, 3, notes=self.notes, name=f"{l.name}.scale")
        tr["rotation"] = K(l.rotation, None, t_off, 1, notes=self.notes, name=f"{l.name}.rotation")
        tr["opacity"] = K(l.opacity, lambda v: max(0.0, min(100.0, v * 100)), t_off, 1, notes=self.notes, name=f"{l.name}.opacity")
        if l.depth.animated or l.depth.rest() != 0:
            tr["z"] = K(l.depth, None, t_off, 1)
        bb = getattr(l, "billboard", False)
        if (l.rx.animated or l.rx.rest() != 0) and bb is not True:
            tr["rx"] = K(l.rx, None, t_off, 1)
        if (l.ry.animated or l.ry.rest() != 0) and not bb:
            tr["ry"] = K(l.ry, None, t_off, 1)
        if l.echo_cfg:
            self.notes.append(f"[NOT EXPORTED] {l.name}: echo trails (AE Echo works on layer pixels, not transforms)")
        if getattr(l, "billboard", False):
            tr["auto_orient"] = True
            if l.billboard == "y":
                self.notes.append(f"[APPROX] {l.name}: faces the camera around the vertical axis only; AE Auto-Orient "
                                  "turns it on both axes")
        return tr

    def common(self, l, comp, t_off, kind, anchor_shift=(0.0, 0.0)):
        nm = self.uname(comp, l.name)
        self.exported[l.uid] = nm
        d = {"name": nm, "kind": kind, "label": LABEL.get(kind, 0),
             "in": l.start + t_off, "out": (l.end + t_off) if l.end is not None else None,
             "blend": BLEND.get(l.blend, "NORMAL"), "tr": self.transform(l, t_off, anchor_shift),
             "fx": [], "motion_blur": bool(l.motion_blur)}
        for f in l.fx:
            if isinstance(f, Blur):
                d["fx"].append({"type": "blur", "sigma": K(f.sigma, lambda v: v * 2.4, t_off, 1)})
            elif isinstance(f, DropShadow):
                dx, dy = f.dx.rest(), f.dy.rest()
                d["fx"].append({"type": "shadow", "color": rgb(f.color), "opacity": f.opacity.rest() * 100,
                                "direction": (math.degrees(math.atan2(dx, -dy)) % 360), "distance": math.hypot(dx, dy),
                                "softness": f.sigma.rest()})
            elif getattr(f, "kind", "") == "soft_shadow":
                e, o = f.elev.rest(), f.opacity.rest()
                for dist, soft, op in ((e * 0.12, e * 0.24 + 2, 0.9), (e * 0.55, e * 1.7, 0.6)):
                    d["fx"].append({"type": "shadow", "color": rgb(f.color), "opacity": o * op * 100,
                                    "direction": 180.0, "distance": dist, "softness": soft})
            elif getattr(f, "kind", "") == "smear":
                d["fx"].append({"type": "smear", "k": f.k, "max": f.max_sigma * 2.4})
            elif isinstance(f, Glow):
                d["fx"].append({"type": "glow", "radius": f.sigma.rest() * 2, "intensity": f.strength.rest() * 2,
                                "color": rgb(f.color) if f.color else None})
        if getattr(l, "sheens", None) or getattr(l, "time_step", None):
            self.notes.append(f"[APPROX] {l.name}: sheen / on_twos are engine-only; add CC Light Sweep / "
                              f"Posterize Time in AE if needed")
        if l.clip is not None:
            def rect_shape(v):
                x, y, w, h = v
                return [{"v": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]], "i": [[0, 0]] * 4, "o": [[0, 0]] * 4, "c": True}]
            d["mask"] = {"mode": "ADD", "path": K(l.clip, rect_shape, t_off, 1)}
            if kind == "text":
                d["mask"]["shift"] = list(anchor_shift)
        return d

    # -- layers
    def layer(self, l, comp, t_off=0.0):
        """Return list of AE layer dicts (bottom-to-top order within this call). A track
        matte (layer.mask) is exported as a hidden layer and linked by name."""
        out = self._layer(l, comp, t_off)
        if l.mask is not None and out:
            mt = self._layer(l.mask, comp, t_off)
            if mt:
                for m in mt:
                    m["hidden_matte"] = True
                    m["label"] = LABEL["matte"]
                kind = {"alpha": "ALPHA", "alpha_inv": "ALPHA_INVERTED", "luma": "LUMA", "luma_inv": "LUMA_INVERTED"}[l.mask_mode]
                out[-1]["matte"] = {"layer": mt[-1]["name"], "type": kind}
                out = mt + out
        return out

    def _layer(self, l, comp, t_off=0.0):
        if isinstance(l, Particles) or not l.exportable:
            if l.kind == "glass":
                self.notes.append(f"[APPROX] {l.name}: the glass is baked without what is behind it; in AE put an "
                                  f"adjustment layer with Fast Box Blur under it, masked to the panel")
            return [self.bake(l, comp, t_off, l.kind)]
        if isinstance(l, Counter):
            return self.counter(l, comp, t_off)
        if isinstance(l, DynamicText):
            if not l.ae_expr:
                return [self.bake(l, comp, t_off, "dynamic text without ae_expr")]
            d = self.text(l, comp, t_off)
            d[0]["source_expr"] = l.ae_expr
            return d
        if isinstance(l, TextOnPath):
            return self.text_path(l, comp, t_off)
        if isinstance(l, Text):
            if l.draw_on is not None or l.fill is not None or getattr(l, "write", None) is not None:
                return [self.bake(l, comp, t_off, "outline/gradient/written text")]
            return self.text(l, comp, t_off)
        if isinstance(l, Background):
            return [self.background(l, comp, t_off)]
        if isinstance(l, Shape):
            f = l.fill
            if isinstance(f, (Noise, Pattern, Conic)):
                return [self.bake(l, comp, t_off, f"{f.kind} fill")]
            if isinstance(f, (Linear, Radial)):
                return self.gradient_shape(l, comp, t_off)
            return [self.shape(l, comp, t_off)]
        if isinstance(l, Image):
            return [self.image(l, comp, t_off)]
        if isinstance(l, Svg):
            return [self.svg(l, comp, t_off)]
        if isinstance(l, Group):
            return [self.group(l, comp, t_off)]
        self.notes.append(f"[SKIPPED] {l.name}: layer type {l.kind} has no AE mapping")
        return []

    def text_payload(self, l):
        L = l.L
        lines = []
        for ln in L.lines:
            gs = L.glyphs[ln["g0"]:ln["g1"]]
            lines.append(L.plain[min((g.ci for g in gs), default=0):max((g.ci for g in gs), default=-1) + 1] if gs else "")
        face0 = L.glyphs[0].face if L.glyphs else None
        var0 = L.glyphs[0].var if L.glyphs else None
        ps = face0.ps_for(var0) if face0 else "DejaVuSans"
        self.fonts.add(ps)
        return lines, ps

    def text(self, l, comp, t_off):
        L = l.L
        lines, ps = self.text_payload(l)
        bx = {"left": 0.0, "center": L.width / 2, "right": L.width}[l.align]
        shift = (bx, L.cap)
        d = self.common(l, comp, t_off, "text", shift)
        st = l.st
        d.update({"text": "\r".join(lines), "font": ps, "size": st["size"], "fill": rgb(st["color"]),
                  "tracking": st.get("tracking", 0.0) * 1000, "leading": st.get("line_height", 1.2) * st["size"],
                  "just": l.align.upper(), "scale_ctrl": True, "animators": []})
        base = st["color"]
        # colored spans -> fill animators with index range selectors
        idx = 0
        for txt, ov in parse_markup(l.content if st.get("case") is None else l.content):
            n = len(txt)
            if ov.get("color") and ov["color"] != base:
                d["animators"].append({"name": f"Span {ov['color']}", "props": {"fill": rgb(ov["color"])},
                                       "range": [idx, idx + n], "accent": ov["color"] == "accent"})
            if ov.get("bold"):
                self.notes.append(f"[APPROX] {l.name}: bold span '{txt}' needs a per-range font (AE 24.3+ characterRange); kept regular")
            idx += n
        # reveal animators via expression selectors
        for a in l.anims:
            n_units = {"char": len(L.plain), "word": max(1, L.n_words), "line": max(1, len(L.lines))}[a.by]
            ranks = a.ranks(n_units, l.uid)
            props = {}
            sz = st["size"]
            dist = a.params.get("dist", 0.45 * sz)
            m = a.mode
            if m == "scramble":
                total = a.params["total"]
                d["animators"].append({"name": "Scramble", "props": {"char_offset": 1},
                                       "char_offset_expr": "seedRandom(Math.floor(time*%g)+textIndex, false); Math.floor(random(1, 26));" % a.params["rate"],
                                       "based_on": 1, "amount_expr": self._sel_expr_scramble(ranks, a.t0 + t_off, total, n_units)})
                self.notes.append(f"[APPROX] {l.name}: scramble uses AE Character Offset (random letters from the same script)")
                continue
            if m in ("fade", "rise", "drop", "left", "right", "scale", "blur", "rotate", "spread", "pop", "mask"):
                props["opacity"] = 0
            if m == "rise":
                props["position"] = [0, dist, 0]
            elif m == "drop":
                props["position"] = [0, -dist, 0]
            elif m == "left":
                props["position"] = [dist, 0, 0]
            elif m == "right":
                props["position"] = [-dist, 0, 0]
            elif m in ("scale", "pop"):
                s0 = a.params.get("s0", 0.0) * 100
                props["scale"] = [s0, s0, 100]
            elif m == "blur":
                sg = a.params.get("sigma", 0.25 * sz)
                props["blur"] = [sg, sg]
            elif m == "rotate":
                props["rotation"] = a.params.get("deg", -25)
                props["position"] = [0, dist * 0.6, 0]
            elif m == "spread":
                props["tracking"] = 300
                self.notes.append(f"[APPROX] {l.name}: 'spread' reveal mapped to tracking")
            elif m == "mask":
                props["position"] = [0, L.lines[0]["h"], 0] if L.lines else [0, sz, 0]
                self.notes.append(f"[APPROX] {l.name}: line 'mask' reveal has no per-line clip in AE; slide+fade used")
            based = {"char": 1, "word": 3, "line": 4}[a.by]
            d["animators"].append({"name": f"Reveal {m}", "props": props, "based_on": based,
                                   "anchor_group": a.by == "char",
                                   "amount_expr": self._sel_expr(ranks, a.t0 + t_off, a.stagger, a.dur, a.ease, a.direction)})
        if l.typer:
            ty = l.typer
            shown = f"Math.floor((time - {ty['t0'] + t_off:.5f}) * {ty['cps']:g} + 1e-6)"
            d["animators"].append({"name": "Typewriter", "props": {"opacity": 0}, "based_on": 1,
                                   "amount_expr": f"var s = {shown}; var a = (textIndex - 1) >= s + {ty['scramble']} || s < 0 ? 100 : 0; [a, a, a];"})
            if ty["scramble"]:
                d["animators"].append({"name": "Typewriter scramble", "props": {"char_offset": 1}, "based_on": 1,
                                       "char_offset_expr": "seedRandom(Math.floor(time*30)+textIndex, false); Math.floor(random(1, 26));",
                                       "amount_expr": f"var s = {shown}; var k = textIndex - 1; var a = (k >= s && k < s + {ty['scramble']}) ? 100 : 0; [a, a, a];"})
            if ty["cursor"]:
                d["cursor"] = self.cursor_track(l, t_off)
        for h in l.highlights:
            self.notes.append(f"[INFO] {l.name}: highlight exported as a shape layer behind the text")
        d["highlights"] = [self.highlight(l, h, t_off) for h in l.highlights]
        if l.color_prop is not None:
            d["fill_k"] = K(l.color_prop, lambda c: rgb(c), t_off, 3)
        if l.stroke:
            d["stroke"] = {"color": rgb(l.stroke.get("color", "text")), "width": l.stroke.get("width", 2)}
        return [d]

    def _sel_expr(self, ranks, t0, stagger, dur, e, direction):
        r = "var R=[" + ",".join(str(x) for x in ranks) + "]; var i = R[Math.min(textIndex, R.length) - 1];" if ranks != list(range(len(ranks))) else "var i = textIndex - 1;"
        if dur <= 1e-6:
            core = f"var p = time >= {t0:.5f} + i*{stagger:g} ? 1 : 0;"
        else:
            core = f"var u = (time - {t0:.5f} - i*{stagger:g}) / {dur:g}; u = Math.max(0, Math.min(1, u)); var p = {js_ease(e)};"
        amt = "100*(1-p)" if direction == "in" else "100*p"
        return JS_EASE_LIB + r + core + f" var a = {amt}; [a, a, a];"

    def _sel_expr_scramble(self, ranks, t0, total, n):
        r = "var R=[" + ",".join(str(x) for x in ranks) + "]; var i = R[Math.min(textIndex, R.length) - 1];"
        return r + f" var settle = {t0:.5f} + {total:g} * (i + 1) / {max(1, n)}; var a = (time >= {t0:.5f} && time < settle) ? 100 : 0; [a, a, a];"

    def cursor_track(self, l, t_off):
        """Hold keyframes for the caret position (one per typed char) + blink expression."""
        L = l.L
        ty = l.typer
        keys = []
        bx = {"left": 0.0, "center": L.width / 2, "right": L.width}[l.align]
        prev = None
        n = len(L.plain)
        for k in range(n + 1):
            t = ty["t0"] + k / ty["cps"]
            vis = [g for g in L.glyphs if g.ci < k and not g.space]
            if vis:
                g = vis[-1]
                x, y = g.x + g.adv + 0.12 * g.size, g.y
            else:
                g = L.glyphs[0]
                x, y = g.x, g.y
            pos = (x - bx, y - L.cap)
            if pos != prev:
                keys.append([round(t + t_off, 5), [round(pos[0], 2), round(pos[1], 2)]])
                prev = pos
        sz = l.st["size"]
        cap = L.glyphs[0].face.cap_height * sz if L.glyphs else 0.7 * sz
        shape = ty["shape"]
        w, h = (max(2.0, 0.06 * sz), cap * 1.25) if shape == "bar" else ((0.5 * sz, 0.07 * sz) if shape == "underscore" else (0.35 * sz, 0.957 * sz))
        until = ty["cursor_until"]
        blink = f"Math.floor(time*{ty['blink']:g}) % 2 == 0 ? 100 : 0"
        if until is not None:
            blink = f"time < {until + t_off:.4f} ? ({blink}) : 0"
        dy = -cap * 1.1 if shape == "bar" else (0.08 * sz if shape == "underscore" else -0.667 * sz)
        return {"keys": keys, "w": w, "h": h, "dy": dy,
                "color": rgb(l.st["color"]), "blink": blink, "t0": ty["t0"] + t_off}

    def highlight(self, l, h, t_off):
        L = l.L
        a, b = h["words"]
        gs = [g for g in L.glyphs if g.wi is not None and a <= g.wi <= b and not g.space]
        rects = []
        bx = {"left": 0.0, "center": L.width / 2, "right": L.width}[l.align]
        for li in sorted({g.li for g in gs}):
            lg = [g for g in gs if g.li == li]
            x0 = min(g.x for g in lg)
            x1 = max(g.x + g.adv for g in lg)
            y = L.lines[li]["y"]
            sz = lg[0].size
            pad = h["pad"] * sz
            top = y - lg[0].face.cap_height * sz - pad
            bot = y + pad * 1.4
            rects.append([x0 - pad - bx, top - L.cap, x1 - x0 + 2 * pad, bot - top])
        e = h["ease"]
        return {"rects": rects, "color": rgb(h["color"]), "opacity": h["opacity"] * 100,
                "k": {"k": [{"t": h["t"] + t_off, "v": [0, 100, 100], "in": "LINEAR", "out": "BEZIER" if e.bezier else "LINEAR",
                             "ie": None, "oe": bez_eases(e.bezier, [0, 100, 100], [100, 100, 100], h["dur"], 3)[0] if e.bezier else None},
                            {"t": h["t"] + h["dur"] + t_off, "v": [100, 100, 100], "in": "BEZIER" if e.bezier else "LINEAR",
                             "out": "LINEAR", "oe": None,
                             "ie": bez_eases(e.bezier, [0, 100, 100], [100, 100, 100], h["dur"], 3)[1] if e.bezier else None}]}}

    def counter(self, l, comp, t_off):
        L = l.L
        lines, ps = self.text_payload(l)
        bx = {"left": 0.0, "center": L.width / 2, "right": L.width}[l.align]
        d = self.common(l, comp, t_off, "text", (bx, L.cap))
        st = l.st
        f = l.fmt
        ks = l.value.keys
        e = ks[-1].ease
        t0, t1 = ks[0].t + t_off, ks[-1].t + t_off
        expr = (JS_EASE_LIB + f"var u = (time - {t0:.5f}) / {max(1e-6, t1 - t0):.5f}; u = Math.max(0, Math.min(1, u)); "
                f"var p = {js_ease(e)}; var v = {ks[0].v!r} + ({ks[-1].v!r} - {ks[0].v!r}) * p; "
                f"var neg = v < 0; v = Math.abs(v); var s = v.toFixed({f['decimals']}); var parts = s.split('.'); "
                f"parts[0] = parts[0].replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, {json.dumps(f['sep'])}); "
                f"(neg ? '-' : '') + {json.dumps(f['prefix'])} + parts.join({json.dumps(f['dec'])}) + {json.dumps(f['suffix'])};")
        d.update({"text": "\r".join(lines), "font": ps, "size": st["size"], "fill": rgb(st["color"]),
                  "tracking": st.get("tracking", 0.0) * 1000, "leading": st.get("line_height", 1.2) * st["size"],
                  "just": l.align.upper(), "source_expr": expr, "animators": [], "scale_ctrl": True})
        self.notes.append(f"[APPROX] {l.name}: counter digits use the font's default figures (tabular 'tnum' is not scriptable)")
        return [d]

    def text_path(self, l, comp, t_off):
        d = self.common(l, comp, t_off, "text")
        lines, ps = self.text_payload(l)
        st = l.st
        d.update({"text": l.L.plain, "font": ps, "size": st["size"], "fill": rgb(st["color"]), "tracking": 0,
                  "leading": st["size"] * 1.2, "just": "LEFT", "animators": [],
                  "text_path": {"shape": ae_shape(l.path), "offset": K(l.offset, None, t_off, 1)}})
        self.notes.append(f"[APPROX] {l.name}: text-on-path offset is exported as a static First Margin; check in AE")
        return [d]

    def shape_contents(self, l, t_off):
        items = []
        if isinstance(l, Rect):
            items.append({"type": "rect", "size": K(l.size, list, t_off, 2), "radius": K(l.radius, None, t_off, 1)})
        elif isinstance(l, Ellipse):
            items.append({"type": "ellipse", "size": K(l.size, list, t_off, 2)})
        elif isinstance(l, (Polygon, Star)):
            if isinstance(l, Polygon):
                items.append({"type": "star", "kind": 2, "points": l.sides, "outer": K(l.radius, None, t_off, 1)})
            else:
                items.append({"type": "star", "kind": 1, "points": l.points, "outer": K(l.outer, None, t_off, 1),
                              "inner": K(l.inner, None, t_off, 1)})
        elif isinstance(l, Arc):
            r = l.radius.rest()
            items.append({"type": "ellipse", "size": {"v": [2 * r, 2 * r]}})
        elif isinstance(l, Line):
            if l.p0.keys or l.p1.keys:
                ts = sorted({k.t for k in l.p0.keys} | {k.t for k in l.p1.keys})
                tmp = Prop(0.0)
                for t in ts:
                    e = next((k.ease for k in (l.p1.keys + l.p0.keys) if abs(k.t - t) < 1e-6), None)
                    tmp.keys.append(type(l.p0.keys[0] if l.p0.keys else l.p1.keys[0])(t, (l.p0.at(t), l.p1.at(t)), e or l.p1.keys[-1].ease))
                items.append({"type": "path", "shapes": [K(tmp, lambda v: [{"v": [list(v[0]), list(v[1])], "i": [[0, 0], [0, 0]], "o": [[0, 0], [0, 0]], "c": False}], t_off, 1)]})
            else:
                items.append({"type": "path", "shapes": [{"v": ae_shape(l.path(0))}]})
        elif isinstance(l, Morph):
            if l.progress.keys:
                tmp = Prop(0.0)
                for k in l.progress.keys:
                    tmp.keys.append(type(k)(k.t, k.v, k.ease))
                items.append({"type": "path", "shapes": [K(tmp, lambda v, _l=l: ae_shape(_morph_path(_l, v)), t_off, 1)]})
            else:
                items.append({"type": "path", "shapes": [{"v": ae_shape(l.path(0))}]})
        elif isinstance(l, PathShape):
            items.append({"type": "path", "shapes": [{"v": ae_shape(l._path)}]})
        return items

    def shape(self, l, comp, t_off):
        d = self.common(l, comp, t_off, "shape")
        geo = self.shape_contents(l, t_off)
        groups = []
        fill = None
        if isinstance(l.fill, Solid):
            c = l.fill.color
            fill = {"color": K(c, lambda v: rgb(v), t_off, 3), "opacity": (color(c.rest())[3] * 100) if not c.keys else 100,
                    "accent": self._is_accent(c)}
        stroke = None
        if l.stroke is not None:
            sc = l.stroke.color
            stroke = {"color": K(sc, lambda v: rgb(v), t_off, 3), "opacity": color(sc.rest())[3] * 100,
                      "width": K(l.stroke_width, None, t_off, 1), "cap": {"butt": 1, "round": 2, "square": 3}[l.cap],
                      "join": {"miter": 1, "round": 2, "bevel": 3}[l.join], "accent": self._is_accent(sc)}
            if l.dash:
                stroke["dash"] = [l.dash[0], l.dash[1]]
        trim = None
        if isinstance(l, Arc):
            trim = {"start": K(l.start_deg, lambda v: v / 3.6, t_off, 1),
                    "end": self._arc_end(l, t_off), "offset": {"v": 0}, "mode": 1}
        elif l.trim_start.animated or l.trim_end.animated or l.trim_start.rest() > 0 or l.trim_end.rest() < 1:
            trim = {"start": K(l.trim_start, lambda v: v * 100, t_off, 1), "end": K(l.trim_end, lambda v: v * 100, t_off, 1),
                    "offset": K(l.trim_offset, lambda v: v * 360, t_off, 1), "mode": 1 if l.trim_mode == "each" else 2}
        if trim and fill:
            groups.append({"name": "Fill", "geo": geo, "fill": fill})
            groups.append({"name": "Stroke", "geo": geo, "trim": trim, "stroke": stroke})
        else:
            groups.append({"name": "Shape", "geo": geo, "fill": fill, "stroke": stroke, "trim": trim})
        d["groups"] = groups
        return d

    def _arc_end(self, l, t_off):
        if l.sweep.keys:
            tmp = Prop(0.0)
            for k in l.sweep.keys:
                tmp.keys.append(type(k)(k.t, (l.start_deg.at(k.t) + k.v) / 3.6, k.ease))
            return K(tmp, None, t_off, 1)
        return {"v": (l.start_deg.rest() + l.sweep.rest()) / 3.6}

    def _is_accent(self, prop):
        d = self.P.design
        acc = d.palette.get("accent")
        return acc is not None and not prop.keys and tuple(round(x, 3) for x in prop.rest()[:3]) == tuple(round(x, 3) for x in acc[:3])

    def gradient_shape(self, l, comp, t_off):
        """Gradient-filled shape -> solid with Gradient Ramp, matted by the shape (alpha)."""
        f = l.fill
        matte = self.shape(l, comp, t_off)
        matte["groups"][0]["fill"] = {"color": {"v": [1, 1, 1]}, "opacity": 100}
        matte["name"] = self.uname(comp, l.name + " Matte")
        matte["kind"] = "matte"
        matte["label"] = LABEL["matte"]
        matte["hidden_matte"] = True
        cols = [color(c) for _, c in f.stops]
        m = l.matrix(0)
        if isinstance(f, Linear):
            p0 = m.mapXY(*f.p0.rest())
            p1 = m.mapXY(*f.p1.rest())
            ramp = {"shape": 1, "start": [p0.x(), p0.y()], "end": [p1.x(), p1.y()]}
        else:
            c = m.mapXY(*f.center.rest())
            ramp = {"shape": 2, "start": [c.x(), c.y()], "end": [c.x() + f.radius.rest(), c.y()]}
        ramp.update(start_color=rgb(cols[0]), end_color=rgb(cols[-1]))
        if len(cols) > 2:
            self.notes.append(f"[APPROX] {l.name}: gradient with {len(cols)} stops -> 2-color Gradient Ramp")
        solid = {"name": self.uname(comp, l.name + " Gradient"), "kind": "solid", "label": LABEL["solid"],
                 "in": l.start + t_off, "out": (l.end + t_off) if l.end is not None else None, "blend": "NORMAL",
                 "color": [1, 1, 1], "tr": None, "fx": [{"type": "ramp", **ramp}], "matte": {"layer": matte["name"], "type": "ALPHA"}}
        if self.P.W:
            solid["size"] = [self.P.W, self.P.H]
        return [matte, solid]

    def background(self, l, comp, t_off):
        f = l.fill
        d = {"name": self.uname(comp, l.name), "kind": "solid", "label": LABEL["solid"], "in": l.start + t_off,
             "out": (l.end + t_off) if l.end is not None else None, "blend": BLEND.get(l.blend, "NORMAL"),
             "tr": None, "fx": [], "size": [self.P.W, self.P.H]}
        if isinstance(f, Solid):
            d["color"] = rgb(f.color.rest())
        elif isinstance(f, (Linear, Radial)):
            cols = [color(c) for _, c in f.stops]
            d["color"] = rgb(cols[0])
            if isinstance(f, Linear):
                ramp = {"shape": 1, "start": list(f.p0.rest()), "end": list(f.p1.rest())}
            else:
                cx, cy = f.center.rest()
                ramp = {"shape": 2, "start": [cx, cy], "end": [cx + f.radius.rest(), cy]}
            ramp.update(start_color=rgb(cols[0]), end_color=rgb(cols[-1]))
            d["fx"].append({"type": "ramp", **ramp})
        else:
            return self.bake(l, comp, t_off, f"{f.kind} background")
        return d

    def image(self, l, comp, t_off):
        d = self.common(l, comp, t_off, "image")
        os.makedirs(os.path.join(self.out, "Assets"), exist_ok=True)
        dst = os.path.join(self.out, "Assets", os.path.basename(l.path))
        if not os.path.exists(dst):
            shutil.copy(l.path, dst)
        w, h = l.size.rest()
        iw, ih = l.img.width(), l.img.height()
        s = (min if l.fit == "contain" else max)(w / iw, h / ih) if l.fit != "stretch" else None
        d["file"] = "Assets/" + os.path.basename(l.path)
        d["native"] = [iw, ih]
        d["fit_scale"] = [s * 100, s * 100] if s else [w / iw * 100, h / ih * 100]
        d["tr"]["anchor"] = [iw / 2 - (0), ih / 2, 0]
        if l.fit == "cover" or l.radius.rest() > 0:
            self.notes.append(f"[APPROX] {l.name}: cover-crop / rounded corners need a mask; check framing")
        return d

    def svg(self, l, comp, t_off):
        try:
            from engine.layers.shape import svg_shapes
            shapes = svg_shapes(l.path)
            g = Group(*shapes, name=l.name, pos=l.position.rest())
            nw, nh = l.native
            w, h = l.size.rest()
            g.scale.set((w / nw * l.scale.rest()[0], h / nh * l.scale.rest()[1]))
            g.anchor.set((nw / 2, nh / 2))
            g.position = l.position
            g.opacity = l.opacity
            g.start, g.end = l.start, l.end
            return self.group(g, comp, t_off)
        except Exception as e:
            self.notes.append(f"[BAKED] {l.name}: SVG could not be converted to shapes ({e})")
            return self.bake(l, comp, t_off, "svg")

    def group(self, g, comp, t_off):
        name = self.uname(comp, g.name)
        sub = {"name": f"{name} [pre]", "w": self.P.W, "h": self.P.H, "dur": self.P.duration, "layers": []}
        for c in g.children:
            sub["layers"] += self.layer(c, sub["name"], 0.0)
        self.precomps.append(sub)
        d = self.common(g, comp, t_off, "precomp")
        d["name"] = name
        d["source"] = sub["name"]
        d["start_time"] = g.offset + t_off
        d["collapse"] = not g.fx
        d["tr"]["anchor"] = [g.anchor.rest()[0], g.anchor.rest()[1], 0]
        if g.fx:
            self.notes.append(f"[APPROX] {g.name}: precomp with effects is not collapsed; content outside the frame is cropped")
        return d

    # -- baking
    def bake(self, l, comp, t_off, why="particles"):
        """Render the layer alone with alpha to ProRes 4444 and import it as footage."""
        from engine.render import out_size
        os.makedirs(os.path.join(self.out, "Assets"), exist_ok=True)
        scene = l.scene if isinstance(l.scene, Scene) else None
        t0 = l.start + t_off + (scene.t0 if scene else 0.0)
        t1 = (l.end + t_off + (scene.t0 if scene else 0.0)) if l.end is not None else ((scene.t1 if scene else self.P.duration))
        fname = f"baked_{len(self.baked) + 1:02d}_{_slug(l.name)}.mov"
        path = os.path.join(self.out, "Assets", fname)
        self._render_cached(path, lambda: render_isolated(self.P, l, path, t0, t1, ss=1))
        self.baked.append({"layer": l.name, "why": why, "file": fname})
        self.notes.append(f"[BAKED] {l.name}: {why} -> Assets/{fname}")
        return {"name": self.uname(comp, l.name + " [BAKED]"), "kind": "baked", "label": LABEL["baked"],
                "file": "Assets/" + fname, "in": l.start + t_off, "out": None, "blend": BLEND.get(l.blend, "NORMAL"),
                "tr": None, "fx": [], "start_time": l.start + t_off, "full_frame": True}

    def _render_cached(self, path, fn):
        """Bakes are reused across calls while the project is unchanged; a call that runs out
        of budget stops with PartialExport so `mv.py ae` can be re-run to continue."""
        import time as _t
        src = [os.path.join(self.root, f) for f in ("video.py", "design.yaml")]
        newest = max((os.path.getmtime(f) for f in src if os.path.exists(f)), default=0)
        if os.path.exists(path) and os.path.getmtime(path) > newest and os.path.getsize(path) > 0:
            return
        if self.budget is not None and _t.perf_counter() - self.t_call > self.budget:
            raise PartialExport(path)
        fn()

    # -- scenes / project
    def _camera_travels(self, s):
        """Comp motion blur on when the camera moves fast somewhere in the scene (the engine
        blurs those frames automatically, AE needs the switches)."""
        cam = s.camera
        if not cam.active or not getattr(self.P, "auto_blur", True):
            return False
        dt = 0.5 / self.P.fps
        n = max(2, int(s.dur * self.P.fps))
        return any(cam.speed_px(i / self.P.fps, dt) > 10 for i in range(n))

    def scene(self, s):
        comp = {"name": f"S{self.P.scenes.index(s) + 1:02d} · {s.name}", "w": self.P.W, "h": self.P.H,
                "dur": s.dur, "layers": [], "camera": None,
                "motion_blur": bool(s.motion_blur) or self._camera_travels(s)}
        bg = s.bg
        if bg is not None and not isinstance(bg, Layer):
            comp["layers"].append({"name": "BG", "kind": "solid", "label": LABEL["solid"], "in": 0, "out": None,
                                   "blend": "NORMAL", "color": rgb(bg), "tr": None, "fx": [], "size": [self.P.W, self.P.H]})
        elif isinstance(bg, Layer):
            comp["layers"] += self.layer(bg, comp["name"], 0.0)
        use3d = s.uses_3d()
        for l in s.children:
            lay = self.layer(l, comp["name"], 0.0)
            if use3d:
                for x in lay:
                    if x.get("kind") != "baked":      # baked clips already carry the camera projection
                        x["three_d"] = True
            comp["layers"] += lay
        if use3d:
            cam = s.camera
            kx, ky = K(_comp(cam.pos, 0, False), None, 0, 1), K(_comp(cam.pos, 1, False), None, 0, 1)
            for i, kk in ((0, kx), (1, ky)):
                exprs = [m.ae_component(i) if hasattr(m, "ae_component") else m.ae_expression() for m in cam.pos.mods
                         if hasattr(m, "ae_component") or hasattr(m, "ae_expression")]
                if exprs:
                    # chain: each modifier adds its offset on top of the keyed value
                    code = "var v = value;" + "".join(f" v = (function(value){{ return {e}; }})(v);" for e in exprs) + " v;"
                    kk["expr"] = code
            comp["camera"] = {"focal": cam.focal, "x": kx, "y": ky, "zoom": K(cam.zoom, None, 0, 1),
                              "rotation": K(cam.rotation, None, 0, 1), "tilt_x": K(cam.rx, None, 0, 1),
                              "tilt_y": K(cam.ry, None, 0, 1),
                              "lens": K(cam.lens, None, 0, 1) if (cam.lens.animated or cam.lens.rest() != 1.0) else None}
            if s.haze_cfg is not None:
                self.notes.append(f"[NOT EXPORTED] {s.name}: haze (atmospheric perspective); in AE add Fill/Tint keyed "
                                  "by layer depth or a fog layer of the background colour")
        # matte bookkeeping: layer.mask -> matte layers
        self._mattes(s, comp)
        return comp

    def _mattes(self, s, comp):
        for l in s.walk():
            if l.mask is not None:
                self.notes.append(f"[INFO] {l.name}: track matte '{l.mask.name}' ({l.mask_mode})")

    def transitions(self):
        out = []
        for i, s in enumerate(self.P.scenes[1:], 1):
            tr = s.transition
            if tr is None:
                continue
            a = self.P.scenes[i - 1]
            item = {"from": i - 1, "to": i, "t0": s.t0, "dur": tr.dur, "type": tr.kind, "params": {}}
            e = tr.ease
            item["ease"] = list(e.bezier) if e.bezier else [0.65, 0, 0.35, 1]
            p = dict(tr.params)
            if tr.kind == "dip":
                p["color"] = rgb(p.get("color", "bg"))
            if tr.kind == "shape_wipe":
                p["color"] = rgb(p.get("color", "accent"))
            if tr.kind == "flash":
                p["color"] = rgb(p.get("color", "#FFFFFF"))
            if tr.kind == "glitch":
                self.bake_window(s.t0, s.t0 + tr.dur, f"glitch transition into {s.name}")
            if tr.kind == "iris" and p.get("center") is None:
                p["center"] = [self.P.W / 2, self.P.H / 2]
            item["params"] = p
            out.append(item)
        return out

    def bake_window(self, t0, t1, why):
        from engine.render import render_video
        os.makedirs(os.path.join(self.out, "Assets"), exist_ok=True)
        fname = f"baked_{len(self.baked) + 1:02d}_window.mov"
        fp = os.path.join(self.out, "Assets", fname)
        self._render_cached(fp, lambda: render_video(self.P, fp, scale=1.0, ss=1, codec="prores4444",
                                                     t_range=(max(0, t0 - 0.05), min(self.P.duration, t1 + 0.05))))
        self.baked.append({"layer": "full frame", "why": why, "file": fname, "t0": max(0, t0 - 0.05)})
        self.notes.append(f"[BAKED] {why}: full-frame clip -> Assets/{fname}")

    def post(self):
        out = []
        for name, p in self.P.post.items():
            p = p or {}
            if p.get("track_only"):
                if name in self.P.fx_tracks:
                    tr = self.P.fx_tracks[name]
                    t_on = [k.t for k in tr.keys if k.v > 0]
                    for t in t_on:
                        if not any(b.get("t0") is not None and abs(b["t0"] - (t - 0.15)) < 0.3 for b in self.baked):
                            self.bake_window(t - 0.12, t + 0.2, f"{name} pulse")
                continue
            if name == "grain":
                out.append({"type": "noise", "amount": p.get("amount", 0.02) * 130})
            elif name == "vignette":
                out.append({"type": "vignette", "amount": p.get("strength", 0.35) * 100})
            elif name == "bloom":
                out.append({"type": "glow", "threshold": p.get("threshold", 0.72) * 100,
                            "radius": p.get("radius", 0.025) * min(self.P.W, self.P.H), "intensity": p.get("intensity", 0.6) * 1.5})
            elif name == "scanlines":
                out.append({"type": "scanlines", "period": p.get("period", 4.5) * min(self.P.W, self.P.H) / 1080,
                            "strength": p.get("strength", 0.18) * 100})
            elif name == "grade":
                out.append({"type": "grade", "saturation": (p.get("saturation", 1.0) - 1) * 100,
                            "contrast": (p.get("contrast", 1.0) - 1) * 100})
            else:
                self.notes.append(f"[NOT EXPORTED] global fx '{name}' has no native AE mapping (preview shows it)")
        return out

    def build(self):
        os.makedirs(self.out, exist_ok=True)
        self.precomps = []
        P = self.P
        scenes = [self.scene(s) for s in P.scenes]
        overlay = []
        for l in P.overlay.children:
            overlay += self.layer(l, "MAIN", 0.0)
        trs = self.transitions()
        post = self.post()
        audio = {}
        if self.audio:
            os.makedirs(os.path.join(self.out, "Audio"), exist_ok=True)
            for k in ("voice", "music", "sfx", "mix"):
                if self.audio.get(k) and os.path.exists(self.audio[k]):
                    shutil.copy(self.audio[k], os.path.join(self.out, "Audio", os.path.basename(self.audio[k])))
                    audio[k] = "Audio/" + os.path.basename(self.audio[k])
        D = P.design
        controls = {"accent": rgb(D.palette.get("accent", (1, 1, 1, 1)))}
        data = {"meta": {"name": self.main_name, "W": P.W, "H": P.H, "fps": P.fps, "dur": P.duration,
                         "bg": rgb(D.palette.get("bg", (0, 0, 0, 1))), "target": self.version,
                         "motion_blur": P.motion_blur},
                "fonts": sorted(self.fonts), "controls": controls,
                "scenes": [{**c, "t0": s.t0} for c, s in zip(scenes, P.scenes)],
                "precomps": self.precomps, "overlay": overlay, "transitions": trs, "post": post,
                "audio": audio, "markers": [{"t": e.t, "kind": e.kind, "accent": e.accent} for e in P.all_events()],
                "baked_windows": [b for b in self.baked if b.get("t0") is not None]}
        runtime = open(os.path.join(HERE, "runtime.jsx"), encoding="utf-8").read()
        js = ("// build_project.jsx - generated by Emaki. Run in After Effects: File > Scripts > Run Script File.\n"
              f"// Target AE version: {self.version:g}. Unverified in AE unless README says otherwise.\n"
              "var DATA = " + json.dumps(data, ensure_ascii=False) + ";\n" + runtime)
        jp = os.path.join(self.out, "build_project.jsx")
        with open(jp, "w", encoding="utf-8") as f:
            f.write(js)
        self.readme(data)
        return {"jsx": jp, "fonts": sorted(self.fonts), "baked": self.baked, "notes": self.notes}

    def readme(self, data):
        lines = [f"# {self.main_name}: After Effects project", "",
                 f"Target version: AE {self.version:g}. Generated by Emaki.", "",
                 "## How to open", "",
                 "1. Install the fonts listed below.",
                 "2. In After Effects: File > Scripts > Run Script File > `build_project.jsx` (keep the Audio/ and Assets/ folders next to it).",
                 "3. The script builds folders Comps / Precomps / Audio / Assets, a main comp, one precomp per scene, and a CONTROLS null.",
                 "", "## Fonts", ""] + [f"- {f}" for f in data["fonts"]] + [
                 "", "## CONTROLS null", "",
                 "- Speed (%): time-remaps every scene precomp.",
                 "- FX Intensity (%): scales grain, vignette, glow, scanlines.",
                 "- Accent Color: drives every fill/stroke that uses the accent role.",
                 "- Text Scale (%): scales all text layers around their anchors.",
                 "", "## Baked elements", ""] + ([f"- {b['layer']}: {b['why']} -> Assets/{b['file']}" for b in self.baked] or ["- none"]) + [
                 "", "## Notes and approximations", ""] + ([f"- {n}" for n in self.notes] or ["- none"]) + [
                 "", "## Verification status", "",
                 "- [UNVERIFIED] The script was validated against an After Effects object-model mock (structure, property names, keyframe/ease ranges), not in real After Effects. Check the main comp against out/preview.mp4.", ""]
        with open(os.path.join(self.out, "README.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))


class PartialExport(Exception):
    pass


def _comp(prop, i, keep_mods=True):
    p = Prop(prop.value[i])
    for k in prop.keys:
        p.keys.append(type(k)(k.t, k.v[i], k.ease))
    p.mods = (prop.mods if i == 0 else []) if keep_mods else []
    return p


def _morph_path(l, v):
    from engine.layers.shape import polyline_path
    import numpy as np
    v = max(0.0, min(len(l.arrs) - 1.0, v))
    i = min(int(v), len(l.arrs) - 2) if len(l.arrs) > 1 else 0
    f = v - i
    a = l.arrs[i] if len(l.arrs) == 1 else l.arrs[i] * (1 - f) + l.arrs[i + 1] * f
    return polyline_path(a.tolist(), closed=l.closed)


def _slug(s):
    import re
    return re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_")[:30] or "layer"


def render_isolated(P, layer, path, t0, t1, ss=2):
    """Render one layer (with its scene camera/ancestors) on transparent -> ProRes 4444."""
    from engine.render import ffmpeg_cmd
    W, H = P.W, P.H
    n = max(1, int(round((t1 - t0) * P.fps)))
    cmd = ffmpeg_cmd(path, W, H, P.fps, None, "prores4444", "final", alpha=True)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    scene = layer.scene if isinstance(layer.scene, Scene) else None
    anc = []
    if scene is not None:
        def find(node, chain):
            for c in node.children:
                if c is layer:
                    return chain
                if isinstance(c, Group):
                    r = find(c, chain + [c])
                    if r is not None:
                        return r
            return None
        anc = find(scene, []) or []
    surf = skia.Surface(W * ss, H * ss)
    for i in range(n):
        t = t0 + i / P.fps
        c = surf.getCanvas()
        c.resetMatrix()
        c.clear(skia.ColorTRANSPARENT)
        c.scale(ss, ss)
        ctx = Ctx(P, px=ss, frame=i, t_abs=t)
        lt = t - (scene.t0 if scene else 0.0)
        top = anc[0] if anc else layer
        ctx.screen_matrix = c.getTotalMatrix()
        if scene is not None and not anc and scene.uses_3d():
            # a top-level layer of a 3D scene: the same path as the render (clipped at the lens,
            # depth of field, haze; screen-space set pieces like motes and reflections)
            scene.draw_layer3d(c, lt, ctx, layer)
        else:
            _bake_draw(c, scene, anc, top, layer, lt, ctx)
        arr = surf.makeImageSnapshot().toarray(colorType=skia.ColorType.kRGBA_8888_ColorType,
                                               alphaType=skia.AlphaType.kUnpremul_AlphaType)
        arr = arr.reshape(H, ss, W, ss, 4).astype(np.float32).mean(axis=(1, 3))
        proc.stdin.write(np.clip(arr + 0.5, 0, 255).astype(np.uint8).tobytes())
    proc.stdin.close()
    proc.wait()


def _bake_draw(c, scene, anc, top, layer, lt, ctx):
        if scene is not None:
            cm = scene.layer_matrix(top, lt)
            if cm is not None:
                c.concat(cm)
        for a in anc:
            c.concat(a.matrix(lt))
            lt -= a.offset
        layer.draw(c, lt, ctx)


def export(P, root, version=None, audio=None, log=print, budget=None, t_call=None):
    ex = Exporter(P, root, version, audio, log, budget, t_call)
    res = ex.build()
    val = os.path.join(HERE, "validate.js")
    if os.path.exists(val) and shutil.which("node") is None:
        res["mock_validation"] = "skipped: Node.js not found (install it to check the .jsx against a mock AE)"
        res["mock_ok"] = None
    elif os.path.exists(val):
        r = subprocess.run(["node", val, res["jsx"], str(ex.version)], capture_output=True, text=True)
        res["mock_validation"] = (r.stdout + r.stderr).strip()[-3000:]
        res["mock_ok"] = r.returncode == 0
    return res
