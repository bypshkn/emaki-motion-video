"""Text layer: HarfBuzz layout + per-unit (char/word/line) animators.

Markup inside content (stripped for QA comparison with the brief):
  *word*          accent color (palette role 'accent')
  **word**        bold (weight 700, or the role's `bold_weight`)
  [word](role)    any palette role or #hex color
  \\n             line break
"""
import math
import re

from ..core import Layer, Prop, color, skcolor, CURRENT, skia, P_, xform, FX_SCALE
from ..easing import ease as _ease
from .. import fonts as F
from .shape import trim_path, path_point, glow_dot

SCRAMBLE_GLYPHS = "01#%&*+=<>/\\|АБВГДЖЗКЛМНПРСТФХЦШЯ"


# ----------------------------------------------------------------------------- markup

_tok = re.compile(r"(\*\*.+?\*\*|\*.+?\*|\[.+?\]\([^)]+\))", re.S)


def parse_markup(s):
    """-> list of (text, overrides dict)."""
    out = []
    pos = 0
    for m in _tok.finditer(s):
        if m.start() > pos:
            out.append((s[pos:m.start()], {}))
        g = m.group(0)
        if g.startswith("**"):
            out.append((g[2:-2], {"bold": True}))
        elif g.startswith("*"):
            out.append((g[1:-1], {"color": "accent"}))
        else:
            mm = re.match(r"\[(.+?)\]\(([^)]+)\)", g, re.S)
            out.append((mm.group(1), {"color": mm.group(2)}))
        pos = m.end()
    if pos < len(s):
        out.append((s[pos:], {}))
    return [(t.replace("\\n", "\n"), o) for t, o in out if t]


def plain(s):
    return "".join(t for t, _ in parse_markup(s))


# ----------------------------------------------------------------------------- layout

class Glyph:
    __slots__ = ("gid", "face", "var", "size", "x", "y", "adv", "ch", "ci", "wi", "li", "color", "path", "space")

    def __init__(self, **k):
        for a in self.__slots__:
            setattr(self, a, k.get(a))


class Layout:
    def __init__(self):
        self.glyphs = []
        self.lines = []           # dicts: y, x0, x1, h, g0, g1
        self.width = self.height = 0.0
        self.ink = (0, 0, 0, 0)
        self.plain = ""
        self.n_words = 0
        self.overflow = False
        self.missing = []
        self.font_sources = set()


def _style_for(base, ov, design):
    st = dict(base)
    if ov.get("bold"):
        st["weight"] = st.get("bold_weight", 700)
    if ov.get("color"):
        c = ov["color"]
        # *accent* words use the text-safe variant when the palette defines one
        if c == "accent" and design is not None and "accent_text" in design.palette:
            c = "accent_text"
        st["color"] = c
    return st


def layout_text(content, st, max_width=None, align="left", design=None):
    """st: dict(family, weight, italic, size, color, tracking(em), line_height(x size),
    case, features). Returns Layout in block coordinates: x from 0, first baseline at
    cap height (so y=0 is the cap top of line 1)."""
    L = Layout()
    runs = parse_markup(content)
    if st.get("case") == "upper":
        runs = [(t.upper(), o) for t, o in runs]
    elif st.get("case") == "lower":
        runs = [(t.lower(), o) for t, o in runs]
    L.plain = "".join(t for t, _ in runs)

    # atoms: words, spaces, newlines with styles
    atoms = []
    ci = 0
    wi = -1
    prev_space = True
    for text, ov in runs:
        s2 = _style_for(st, ov, design)
        for part in re.split(r"(\n| +)", text):
            if part == "":
                continue
            if part == "\n":
                atoms.append(("nl", part, s2, ci, wi))
                prev_space = True
            elif part.strip() == "":
                atoms.append(("sp", part, s2, ci, wi))
                prev_space = True
            else:
                if prev_space:
                    wi += 1
                atoms.append(("w", part, s2, ci, wi))
                prev_space = False
            ci += len(part)
    L.n_words = wi + 1

    size = st["size"]
    lh = st.get("line_height", 1.2) * size

    shaped = []
    for kind, txt, s2, c0, w in atoms:
        if kind == "nl":
            shaped.append((kind, [], 0.0, s2, c0, w))
            continue
        face, var, src = F.resolve(s2.get("family"), s2.get("weight", 400), s2.get("italic", False))
        L.font_sources.add((face.family, src))
        miss = face.missing(txt)
        if miss:
            L.missing += miss
        feats = s2.get("features") or {}
        gl = face.shape(txt, feats, var)
        trk = s2.get("tracking", 0.0) * s2["size"]
        x = 0.0
        out = []
        for gid, cl, xa, ya, xo, yo in gl:
            g = Glyph(gid=gid, face=face, var=var, size=s2["size"], x=x + xo * s2["size"], y=-yo * s2["size"],
                      adv=xa * s2["size"] + trk, ch=txt[cl] if cl < len(txt) else "", ci=c0 + cl, wi=w,
                      color=s2.get("color", "text"), space=(kind == "sp"))
            out.append(g)
            x += xa * s2["size"] + trk
        shaped.append((kind, out, x, s2, c0, w))

    # greedy line breaking
    lines = [[]]
    widths = [0.0]
    pending_space = []
    for kind, gl, w, s2, c0, wi_ in shaped:
        if kind == "nl":
            lines.append([])
            widths.append(0.0)
            pending_space = []
            continue
        if kind == "sp":
            if lines[-1]:
                pending_space = (gl, w)
            continue
        sp_gl, sp_w = pending_space if pending_space else ([], 0.0)
        if max_width and lines[-1] and widths[-1] + sp_w + w > max_width:
            lines.append([])
            widths.append(0.0)
            sp_gl, sp_w = [], 0.0
        if max_width and w > max_width:
            L.overflow = True
        x0 = widths[-1]
        for g in sp_gl:
            g2 = Glyph(**{a: getattr(g, a) for a in Glyph.__slots__})
            g2.x = g.x + x0
            lines[-1].append(g2)
        x0 += sp_w
        for g in gl:
            g2 = Glyph(**{a: getattr(g, a) for a in Glyph.__slots__})
            g2.x = g.x + x0
            lines[-1].append(g2)
        widths[-1] = x0 + w
        pending_space = []

    # metrics and alignment
    face0, _, _ = F.resolve(st.get("family"), st.get("weight", 400), st.get("italic", False))
    cap = face0.cap_height * size
    block_w = max(widths) if widths else 0.0
    if max_width and align != "left":
        block_w = max(block_w, max_width) if st.get("fill_box") else block_w
    y = cap
    gi = 0
    for li, (gl, w) in enumerate(zip(lines, widths)):
        dx = {"left": 0.0, "center": (block_w - w) / 2, "right": block_w - w}[align]
        for g in gl:
            g.x += dx
            g.y += y
            g.li = li
        L.glyphs += gl
        L.lines.append({"y": y, "x0": dx, "x1": dx + w, "h": lh, "g0": gi, "g1": gi + len(gl)})
        gi += len(gl)
        y += lh
    last_base = L.lines[-1]["y"] if L.lines else cap
    L.width = block_w
    L.height = last_base
    asc = max((g.face.ascender * g.size for g in L.glyphs), default=face0.ascender * size)
    desc = min((g.face.descender * g.size for g in L.glyphs), default=face0.descender * size)
    L.ink = (0.0, cap - asc, block_w, last_base - desc)
    L.cap = cap
    for g in L.glyphs:
        g.path = g.face.glyph_path(g.gid, g.var)
    return L


# ----------------------------------------------------------------------------- animators

class UnitAnim:
    """Per-unit animator. direction 'in' animates hidden->rest, 'out' rest->hidden."""

    def __init__(self, mode, t0, by="char", dur=0.5, stagger=0.03, ease=None, order="forward",
                 direction="in", **params):
        self.mode, self.t0, self.by, self.dur, self.stagger = mode, float(t0), by, float(dur), float(stagger)
        self.ease = _ease(ease)
        self.order, self.direction, self.params = order, direction, params

    def ranks(self, n, seed):
        idx = list(range(n))
        if self.order == "reverse":
            return [n - 1 - i for i in idx]
        if self.order == "center":
            c = (n - 1) / 2
            r = sorted(idx, key=lambda i: abs(i - c))
            out = [0] * n
            for k, i in enumerate(r):
                out[i] = k
            return out
        if self.order == "edges":
            c = (n - 1) / 2
            r = sorted(idx, key=lambda i: -abs(i - c))
            out = [0] * n
            for k, i in enumerate(r):
                out[i] = k
            return out
        if self.order == "random":
            import random
            rr = random.Random(seed)
            perm = idx[:]
            rr.shuffle(perm)
            out = [0] * n
            for k, i in enumerate(perm):
                out[i] = k
            return out
        return idx

    def end_time(self, n):
        return self.t0 + max(0, n - 1) * self.stagger + self.dur

    def progress(self, rank, t):
        s = self.t0 + rank * self.stagger
        if self.dur <= 1e-6:
            p = 1.0 if t >= s else 0.0
        else:
            u = (t - s) / self.dur
            p = 0.0 if u <= 0 else 1.0 if u >= 1 else self.ease(u)
        return p if self.direction == "in" else 1.0 - p


class Text(Layer):
    kind = "text"

    def __init__(self, content, style="body", size=None, color=None, font=None, weight=None, italic=None,
                 tracking=None, line_height=None, align="left", max_width=None, case=None, features=None,
                 role="copy", src="brief", stroke=None, fill=None, anchor="tl", fit=None, **kw):
        super().__init__(anchor=anchor, **kw)
        d = CURRENT["design"]
        spec = d.font(style) if d else {}
        self.style = style
        self.content = content
        st = {"family": font or spec.get("family", "DejaVu Sans"),
              "weight": weight or spec.get("weight", 400),
              "italic": italic if italic is not None else spec.get("italic", False),
              "size": size or (d.size(style) if d else 48),
              "color": color or spec.get("color", "text"),
              "tracking": tracking if tracking is not None else spec.get("tracking", 0.0),
              "line_height": line_height or spec.get("line_height", 1.2),
              "case": case or spec.get("case"),
              "features": features or spec.get("features"),
              "bold_weight": spec.get("bold_weight", 700)}
        self.st = st
        self.align = align
        self.max_width = max_width
        self.text_role = role           # 'copy' (QA: reading time + contrast) | 'decor'
        self.src = src                  # 'brief' | 'invented' | 'decor'
        self.stroke = stroke            # {'width': px, 'color': role}
        self.fill = fill                # skia shader factory or None
        self.anims = []
        self.typer = None
        self.highlights = []
        self.color_prop = None
        self.L = layout_text(content, st, max_width, align, d)
        if fit and self.L.width > fit:
            # shrink to fit a width (one-line slams that must fill but never clip)
            st["size"] *= fit / self.L.width
            self.L = layout_text(content, st, max_width, align, d)
        self.draw_on = None             # (t0, dur, ease) outline draw-on
        self.write = None               # sequential hand-written reveal with a lead nib
        self.resolve_anchor()

    # ---- geometry
    @property
    def width(self):
        return self.L.width

    @property
    def height(self):
        return self.L.height

    @property
    def plain(self):
        return self.L.plain

    def local_bounds(self, t):
        return (self.L.ink[0], self.L.ink[1], self.L.ink[2], self.L.ink[3])

    def resolve_anchor(self):
        if self._anchor_spec:
            from ..core import _anchor_point
            self.anchor.set(_anchor_point(self._anchor_spec, (0, 0, self.L.width, self.L.height)))

    # ---- authoring
    def reveal(self, t, mode="rise", by="char", dur=None, stagger=None, ease=None, order="forward", **params):
        """Units enter: fade|rise|drop|left|right|scale|blur|rotate|mask|spread."""
        d = CURRENT["design"]
        if dur is None:
            dur = d.motion.durations["medium"] if d else 0.5
        if stagger is None:
            base = d.motion.stagger if d else 0.04
            stagger = {"char": base * 0.6, "word": base * 2, "line": base * 3}[by]
        if ease is None:
            ease = d.motion.easing["enter"] if d else "out_expo"
        self.anims.append(UnitAnim(mode, t, by, dur, stagger, ease, order, "in", **params))
        return self

    def unreveal(self, t, mode="fade", by="line", dur=None, stagger=None, ease=None, order="forward", **params):
        d = CURRENT["design"]
        if dur is None:
            dur = d.motion.durations["short"] if d else 0.35
        if stagger is None:
            base = d.motion.stagger if d else 0.04
            stagger = {"char": base * 0.4, "word": base, "line": base * 2}[by]
        if ease is None:
            ease = d.motion.easing["exit"] if d else "in_cubic"
        self.anims.append(UnitAnim(mode, t, by, dur, stagger, ease, order, "out", **params))
        return self

    def typewriter(self, t, cps=22, cursor=True, scramble=0, glyphs=SCRAMBLE_GLYPHS, blink=3.0,
                   cursor_until=None, cursor_shape="block", sound=None):
        """Characters appear at `cps`; `scramble` random glyphs run ahead of the caret."""
        self.typer = {"t0": float(t), "cps": float(cps), "cursor": cursor, "scramble": int(scramble),
                      "glyphs": glyphs, "blink": blink, "cursor_until": cursor_until,
                      "shape": cursor_shape, "sound": sound}
        return self

    def type_end(self):
        if not self.typer:
            return None
        # the renderer and the sound advance over every character, spaces and line breaks included
        return self.typer["t0"] + len(self.L.plain) / self.typer["cps"]

    def scramble(self, t, dur=0.8, order="random", glyphs=SCRAMBLE_GLYPHS, rate=24, by="char"):
        """Each char cycles random glyphs, settling at its own time within [t, t+dur]."""
        self.anims.append(UnitAnim("scramble", t, by, 0.0, dur / max(1, len(self.L.glyphs)), "linear",
                                   order, "in", glyphs=glyphs, rate=rate, total=dur))
        return self

    def draw_outline(self, t, dur=1.2, ease="in_out_cubic", fill_after=0.3):
        """Glyph outlines draw on (stroke trim), then fill fades in."""
        self.draw_on = (float(t), float(dur), _ease(ease), fill_after)
        return self

    def write_on(self, t, cps=14, overlap=2.2, ease="in_out_sine", head=True, head_color="accent", glow=1.0,
                 head_size=0.09, width=0.022, fill_at=0.7, fill_dur=0.25):
        """Letters are written one after another: each outline draws on, a lead nib (glowing
        or flat with glow=0) rides the stroke tip, then the fill comes in."""
        order = {}
        k = 0
        for g in self.L.glyphs:
            if not g.space:
                order[g.ci] = k
                k += 1
        per = 1.0 / cps
        self.write = {"t0": float(t), "per": per, "slot": per * overlap, "ease": _ease(ease), "order": order,
                      "head": head, "head_color": head_color, "glow": glow, "head_size": head_size,
                      "width": width, "fill_at": fill_at, "fill_dur": fill_dur, "n": k}
        return self

    def write_end(self):
        w = self.write
        return w["t0"] + max(0, w["n"] - 1) * w["per"] + w["slot"] * w["fill_at"] + w["fill_dur"] if w else None

    def highlight(self, words, t, dur=0.45, color="accent", pad=0.12, ease=None, opacity=1.0):
        """Marker highlight behind word indices (a, b) inclusive, wiping left->right."""
        self.highlights.append({"words": words, "t": float(t), "dur": dur, "color": color,
                                "pad": pad, "ease": _ease(ease or "out_cubic"), "opacity": opacity})
        return self

    def animate_color(self, t, to, dur=0.4, ease="in_out_sine"):
        if self.color_prop is None:
            self.color_prop = Prop(color(self.st["color"]), "fill")
        self.color_prop.key(t, self.color_prop.at(t)).key(t + dur, color(to), ease)
        return self

    # ---- timing info for QA
    def reveal_window(self):
        """(fully_revealed_time, exit_start_time or None)."""
        n_units = {"char": len(self.L.glyphs), "word": max(1, self.L.n_words), "line": max(1, len(self.L.lines))}
        t_in = self.start
        ins = [a for a in self.anims if a.direction == "in"]
        for a in ins:
            if a.mode == "scramble":
                t_in = max(t_in, a.t0 + a.params["total"])
            else:
                t_in = max(t_in, a.end_time(n_units[a.by]))
        if self.typer:
            t_in = max(t_in, self.type_end())
        if self.write:
            t_in = max(t_in, self.write_end())
        op = self.opacity
        if op.keys:
            for k in op.keys:
                if k.v >= 0.9 * op.rest() and k.t > t_in and op.base_at(k.t - 1e-3) < 0.9 * op.rest():
                    t_in = max(t_in, k.t)
        outs = [a.t0 for a in self.anims if a.direction == "out"]
        if op.keys:
            for i in range(1, len(op.keys)):
                if op.keys[i].v < op.keys[i - 1].v and op.keys[i - 1].t >= t_in - 1e-6:
                    outs.append(op.keys[i - 1].t)
                    break
        if self.end is not None:
            outs.append(self.end)
        sc = self.scene
        if sc is not None and hasattr(sc, "dur"):
            outs.append(sc.dur)
        t_out = min(outs) if outs else None
        return t_in, t_out

    def reveal_start(self):
        ts = [a.t0 for a in self.anims if a.direction == "in"]
        if self.typer:
            ts.append(self.typer["t0"])
        if self.write:
            ts.append(self.write["t0"])
        op = self.opacity
        if op.keys and op.keys[0].v < 0.5 * op.rest():
            ts.append(op.keys[0].t)
        return min(ts) if ts else self.start

    def audio_events(self):
        ev = []
        if self.typer and self.typer.get("sound"):
            k = 0
            for ch in self.L.plain:
                if ch in " \n":
                    k += 1
                    continue
                ev.append((self.typer["t0"] + k / self.typer["cps"], self.typer["sound"], {"i": k}))
                k += 1
        return ev

    # ---- rendering
    def _unit_index(self, g, by):
        return {"char": g.ci, "word": g.wi, "line": g.li}[by]

    def render(self, canvas, t, ctx):
        L = self.L
        if not L.glyphs:
            return
        base_col = self.color_prop.at(t) if self.color_prop is not None else None
        px = ctx.px
        # highlights behind text
        for h in self.highlights:
            a, b = h["words"]
            gs = [g for g in L.glyphs if g.wi is not None and a <= g.wi <= b and not g.space]
            if not gs:
                continue
            u = (t - h["t"]) / h["dur"] if h["dur"] > 0 else 1
            if u <= 0:
                continue
            p = h["ease"](min(1.0, u))
            by_line = {}
            for g in gs:
                by_line.setdefault(g.li, []).append(g)
            c = color(h["color"])
            paint = skia.Paint(AntiAlias=True, Color4f=skia.Color4f(c[0], c[1], c[2], c[3] * h["opacity"]))
            for li, lg in sorted(by_line.items()):
                x0 = min(g.x for g in lg)
                x1 = max(g.x + g.adv for g in lg)
                y = L.lines[li]["y"]
                sz = lg[0].size
                pad = h["pad"] * sz
                top = y - lg[0].face.cap_height * sz - pad
                bot = y + pad * 1.4
                canvas.drawRect(skia.Rect.MakeLTRB(x0 - pad, top, x0 - pad + (x1 - x0 + 2 * pad) * p, bot), paint)

        # typewriter state
        shown_n = None
        typ = self.typer
        if typ:
            shown_n = int(math.floor((t - typ["t0"]) * typ["cps"] + 1e-6)) if t >= typ["t0"] else -1

        units = {}
        for a in self.anims:
            if a.by not in units:
                n = {"char": len(L.plain), "word": max(1, L.n_words), "line": max(1, len(L.lines))}[a.by]
                units[a.by] = n
        ranks = {id(a): a.ranks(units[a.by], self.uid) for a in self.anims}

        line_clip = any(a.mode == "mask" for a in self.anims)
        head = None
        cursor_x = cursor_y = None
        last_drawn = None
        for g in L.glyphs:
            if g.space:
                continue
            op = 1.0
            dx = dy = 0.0
            sc = 1.0
            rot = 0.0
            blur = 0.0
            gid, path = g.gid, g.path
            # typewriter
            if typ:
                k = g.ci
                if shown_n < 0 or k >= shown_n + typ["scramble"]:
                    continue
                if g.space or g.ch == "\n":
                    continue
                if k >= shown_n:
                    # random glyph running ahead of the caret; changes 30x per second
                    rr = ctx.rng("tw", self.uid, k, int(t * 30))
                    rc = typ["glyphs"][int(rr.integers(0, len(typ["glyphs"])))]
                    rg = g.face.gid(rc)
                    if rg is None:
                        continue
                    gid, path = rg, g.face.glyph_path(rg, g.var)
            mask_dy = None
            for a in self.anims:
                ui = self._unit_index(g, a.by)
                r = ranks[id(a)][min(ui, len(ranks[id(a)]) - 1)] if ranks[id(a)] else 0
                if a.mode == "scramble":
                    settle = a.t0 + (a.params["total"] * (r + 1) / max(1, units[a.by]))
                    if t < a.t0:
                        op = 0.0
                    elif t < settle:
                        rr = ctx.rng("sc", self.uid, g.ci, int(t * a.params["rate"]))
                        gl = a.params["glyphs"]
                        rc = gl[int(rr.integers(0, len(gl)))]
                        rg = g.face.gid(rc)
                        if rg is not None:
                            gid, path = rg, g.face.glyph_path(rg, g.var)
                    continue
                p = a.progress(r, t)
                q = 1.0 - p
                if q <= 1e-6:
                    continue
                prm = a.params
                dist = prm.get("dist", 0.45 * g.size)
                m = a.mode
                if m in ("fade", "rise", "drop", "left", "right", "scale", "blur", "rotate", "spread", "pop"):
                    op *= p if m != "pop" else min(1.0, p * 3)
                if m == "rise":
                    dy += dist * q
                elif m == "drop":
                    dy -= dist * q
                elif m == "left":
                    dx += dist * q
                elif m == "right":
                    dx -= dist * q
                elif m in ("scale", "pop"):
                    sc *= prm.get("s0", 0.0) + (1 - prm.get("s0", 0.0)) * p
                elif m == "blur":
                    blur = max(blur, prm.get("sigma", 0.25 * g.size) * q)
                elif m == "rotate":
                    rot += prm.get("deg", -25) * q
                    dy += dist * 0.6 * q
                elif m == "spread":
                    ln = L.lines[g.li]
                    cxl = (ln["x0"] + ln["x1"]) / 2
                    dx += (g.x + g.adv / 2 - cxl) * prm.get("k", 0.6) * q
                elif m == "mask":
                    mask_dy = (mask_dy or 0.0) + L.lines[g.li]["h"] * q * prm.get("depth", 1.05)
            if op <= 0.002:
                continue
            col = base_col if (base_col is not None and g.color == self.st["color"]) else color(g.color)
            col = (col[0], col[1], col[2], col[3] * op)
            m = skia.Matrix()
            cxg, cyg = g.x + g.adv / 2, g.y - g.face.cap_height * g.size / 2
            m.setTranslate(g.x + dx, g.y + dy + (mask_dy or 0.0))
            if sc != 1.0 or rot:
                m2 = skia.Matrix()
                m2.setTranslate(cxg - g.x, cyg - g.y)
                if rot:
                    m2.preRotate(rot)
                m2.preScale(sc, sc)
                m2.preTranslate(-(cxg - g.x), -(cyg - g.y))
                m.preConcat(m2)
            m.preScale(g.size, g.size)
            gp = xform(path, m)
            paint = skia.Paint(AntiAlias=True, Color4f=skia.Color4f(*col))
            if blur > 0.05:
                paint.setMaskFilter(skia.MaskFilter.MakeBlur(skia.BlurStyle.kNormal_BlurStyle, blur * FX_SCALE))
            if self.fill is not None:
                paint.setShader(self.fill(self, t))
                paint.setAlphaf(col[3])
            if line_clip:
                ln = L.lines[g.li]
                canvas.save()
                top = ln["y"] - ln["h"] * 0.95
                canvas.clipRect(skia.Rect.MakeLTRB(-1e5, top, 1e5, ln["y"] + ln["h"] * 0.32), True)
            if self.write is not None:
                w = self.write
                k = w["order"].get(g.ci, 0)
                s0 = w["t0"] + k * w["per"]
                u = (t - s0) / w["slot"]
                if u > 0:
                    pr = w["ease"](min(1.0, u))
                    sw = max(1.0, g.size * w["width"])
                    if pr < 1:
                        seg = trim_path(gp, 0.0, pr, 0.0, "whole")
                        canvas.drawPath(seg, skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=sw,
                                                        StrokeCap=skia.Paint.kRound_Cap, Color4f=skia.Color4f(*col)))
                        pt = path_point(gp, pr)
                        if pt and (head is None or k >= head[2]):
                            head = (pt[0], pt[1], k, g.size)
                    fa = (t - (s0 + w["slot"] * w["fill_at"])) / max(1e-3, w["fill_dur"])
                    if fa > 0:
                        paint.setAlphaf(col[3] * min(1.0, fa))
                        canvas.drawPath(gp, paint)
                    if pr >= 1 and fa < 1:
                        canvas.drawPath(gp, skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=sw,
                                                       Color4f=skia.Color4f(col[0], col[1], col[2], col[3] * (1 - max(0.0, fa)))))
            elif self.draw_on is not None:
                t0, dd, ez, fill_after = self.draw_on
                u = (t - t0) / dd if dd > 0 else 1.0
                pr = ez(max(0.0, min(1.0, u)))
                if pr > 0:
                    sp = skia.Paint(AntiAlias=True, Color4f=skia.Color4f(*col), Style=skia.Paint.kStroke_Style,
                                    StrokeWidth=max(1.0, g.size * 0.025))
                    if pr < 1:
                        sp.setPathEffect(skia.TrimPathEffect.Make(0.0, pr))
                    canvas.drawPath(gp, sp)
                fa = (t - (t0 + dd * (1 - fill_after))) / (dd * fill_after + 1e-6)
                if fa > 0:
                    paint.setAlphaf(col[3] * min(1.0, fa))
                    canvas.drawPath(gp, paint)
            else:
                canvas.drawPath(gp, paint)
            if self.stroke:
                sc_ = color(self.stroke.get("color", "text"))
                sp = skia.Paint(AntiAlias=True, Color4f=skia.Color4f(sc_[0], sc_[1], sc_[2], sc_[3] * op),
                                Style=skia.Paint.kStroke_Style, StrokeWidth=self.stroke.get("width", 2))
                canvas.drawPath(gp, sp)
            if line_clip:
                canvas.restore()
            last_drawn = g
        if self.write is not None and self.write["head"] and head is not None:
            w = self.write
            glow_dot(canvas, head[0], head[1], head[3] * w["head_size"], w["head_color"], w["glow"])
        # cursor
        if typ and typ["cursor"] and shown_n is not None and shown_n >= 0:
            until = typ["cursor_until"]
            if until is None or t < until:
                if int(t * typ["blink"]) % 2 == 0:
                    if last_drawn is not None:
                        g = last_drawn
                        x = g.x + g.adv + 0.12 * g.size
                        y = g.y
                    else:
                        g = L.glyphs[0]
                        x, y = g.x, g.y
                    sz = g.size
                    c = color(self.st["color"])
                    if typ["shape"] == "bar":
                        r = skia.Rect.MakeXYWH(x, y - g.face.cap_height * sz * 1.1, max(2.0, 0.06 * sz), g.face.cap_height * sz * 1.25)
                    elif typ["shape"] == "underscore":
                        r = skia.Rect.MakeXYWH(x, y + 0.08 * sz, 0.5 * sz, 0.07 * sz)
                    else:
                        # terminal block caret: from ~2/3 em above the baseline to just below it
                        r = skia.Rect.MakeXYWH(x, y - 0.667 * sz, 0.35 * sz, 0.957 * sz)
                    canvas.drawRect(r, skia.Paint(AntiAlias=True, Color4f=skia.Color4f(*c)))


class DynamicText(Text):
    """Text whose content is a function of scene time (timecodes, clocks, live labels).
    `sample` is a representative string used for layout/anchoring. For After Effects pass
    `ae_expr` (a Source Text expression); otherwise the exporter bakes the layer."""
    kind = "dynamic_text"

    def __init__(self, fn, sample, ae_expr=None, **kw):
        kw.setdefault("role", "decor")
        kw.setdefault("src", "decor")
        super().__init__(sample, **kw)
        self.fn = fn
        self.ae_expr = ae_expr
        self._cache = {}

    def render(self, canvas, t, ctx):
        s = str(self.fn(t))
        L = self._cache.get(s)
        if L is None:
            L = layout_text(s, self.st, self.max_width, self.align, CURRENT["design"])
            dx = {"left": 0.0, "center": (self.L.width - L.width) / 2, "right": self.L.width - L.width}[self.align]
            for g in L.glyphs:
                g.x += dx
            if len(self._cache) > 512:
                self._cache.clear()
            self._cache[s] = L
        keep = self.L
        self.L = L
        try:
            super().render(canvas, t, ctx)
        finally:
            self.L = keep


class TextOnPath(Layer):
    """Glyphs flow along a path. `offset` (0..1) slides the text along the path."""
    kind = "text_path"

    def __init__(self, content, path, style="body", size=None, color=None, offset=0.0, align="start", **kw):
        super().__init__(**kw)
        from .shape import to_path
        self.path = to_path(path)
        d = CURRENT["design"]
        spec = d.font(style) if d else {}
        self.st = {"family": spec.get("family", "DejaVu Sans"), "weight": spec.get("weight", 400),
                   "size": size or (d.size(style) if d else 40), "color": color or "text",
                   "tracking": spec.get("tracking", 0.0), "line_height": 1.2, "features": spec.get("features")}
        self.content = content
        self.L = layout_text(content.replace("\n", " "), self.st, None, "left", d)
        self.offset = P_(offset, "offset")
        self.align = align
        self.text_role = "decor"
        self.src = kw.get("src", "brief")

    @property
    def plain(self):
        return self.L.plain

    def local_bounds(self, t):
        r = self.path.computeTightBounds()
        pad = self.st["size"]
        return (r.left() - pad, r.top() - pad, r.right() + pad, r.bottom() + pad)

    def render(self, canvas, t, ctx):
        pm = skia.PathMeasure(self.path, False)
        total = pm.getLength()
        off = self.offset.at(t) * total
        if self.align == "center":
            off += (total - self.L.width) / 2
        c = color(self.st["color"])
        paint = skia.Paint(AntiAlias=True, Color4f=skia.Color4f(*c))
        for g in self.L.glyphs:
            if g.space:
                continue
            d = off + g.x + g.adv / 2
            if d < 0 or d > total:
                continue
            pos, tan = pm.getPosTan(d)
            ang = math.degrees(math.atan2(tan.y(), tan.x()))
            m = skia.Matrix()
            m.setTranslate(pos.x(), pos.y())
            m.preRotate(ang)
            m.preTranslate(-g.adv / 2, g.y - self.L.cap * 0.5 + self.L.cap * 0.5)
            m.preScale(g.size, g.size)
            canvas.drawPath(xform(g.path, m), paint)
