"""Fonts: index, resolution with Cyrillic coverage, HarfBuzz shaping, glyph outlines.

Text is shaped by HarfBuzz (kerning, features like 'tnum', variable axes) and drawn as
glyph outlines (skia.Path). This keeps variable fonts, per-glyph animation, text on a
path and outline drawing on one code path.

Font lookup order: project fonts/ -> system fonts -> DejaVu fallback (with a warning
that names a concrete free font to download).
"""
import json
import os
import glob

import uharfbuzz as hb

from .env import load_skia

skia = load_skia()

CACHE = os.environ.get("MV_CACHE", os.path.expanduser("~/.cache/emaki"))
SYSTEM_DIRS = ["/usr/share/fonts", "/usr/local/share/fonts", "~/.fonts", "~/.local/share/fonts",
               "/Library/Fonts", "/System/Library/Fonts", "~/Library/Fonts"]
# Glyphs a font must have before it is picked, per on-screen language (brief.yaml `language`).
# Other languages are not pre-filtered: QA `glyphs` fails any character the chosen font lacks.
# Ukrainian: the full alphabet (Ґ Є І Ї) and the typographic apostrophe, the usual gaps.
CYRILLIC = ("АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯабвгґдеєжзиіїйклмнопрстуфхцчшщьюя’")
STRICT_LANGUAGES = {"uk": CYRILLIC}
_ALIASES = {"ua": "uk", "ukr": "uk", "ukrainian": "uk", "українська": "uk", "eng": "en", "english": "en"}


def norm_language(lang):
    """ISO 639-1 code from what a brief may say (en, en-US, English, uk, ua, Ukrainian ...); "en" when empty."""
    s = str(lang or "en").strip().lower()
    s = _ALIASES.get(s, s)
    return _ALIASES.get(s[:2], s[:2])


LANGUAGE = norm_language(os.environ.get("MV_LANGUAGE", "en"))


def set_language(lang):
    """On-screen language of the project (ISO 639-1, e.g. "en", "uk"); set by load_project."""
    global LANGUAGE
    LANGUAGE = norm_language(lang)
FALLBACK = {"sans": "DejaVu Sans", "serif": "DejaVu Serif", "mono": "DejaVu Sans Mono"}
EXTS = (".ttf", ".otf", ".ttc", ".otc")

_index = {}          # dir -> list[dict]
_faces = {}          # (path, idx) -> FontFace
WARNINGS = []


def _scan_file(path):
    from fontTools.ttLib import TTFont, TTCollection
    out = []
    try:
        fonts = TTCollection(path, lazy=True).fonts if path.lower().endswith((".ttc", ".otc")) else [TTFont(path, lazy=True)]
    except Exception:
        return out
    for i, f in enumerate(fonts):
        try:
            name = f["name"]
            fam = (name.getDebugName(16) or name.getDebugName(1) or "").strip()
            sub = (name.getDebugName(17) or name.getDebugName(2) or "").strip()
            os2 = f["OS/2"] if "OS/2" in f else None
            weight = os2.usWeightClass if os2 else 400
            italic = bool(os2.fsSelection & 1) if os2 else ("italic" in sub.lower())
            cmap = f.getBestCmap() or {}
            cyr = all(ord(c) in cmap for c in CYRILLIC)
            axes = {}
            if "fvar" in f:
                for a in f["fvar"].axes:
                    axes[a.axisTag] = [a.minValue, a.defaultValue, a.maxValue]
            out.append({"path": path, "index": i, "family": fam, "style": sub, "weight": weight,
                        "italic": italic, "cyrillic": cyr, "axes": axes,
                        "mono": bool(os2 and os2.panose and os2.panose.bProportion == 9)})
        except Exception:
            continue
    return out


def index_dir(d):
    d = os.path.expanduser(d)
    if d in _index:
        return _index[d]
    if not os.path.isdir(d):
        _index[d] = []
        return []
    files = [p for p in glob.glob(os.path.join(d, "**", "*"), recursive=True) if p.lower().endswith(EXTS)]
    sig = str(sorted((p, int(os.path.getmtime(p))) for p in files)) + "|" + CYRILLIC
    os.makedirs(CACHE, exist_ok=True)
    cfile = os.path.join(CACHE, "fontindex_" + str(abs(hash(d)) % 10 ** 10) + ".json")
    if os.path.exists(cfile):
        try:
            with open(cfile) as f:
                c = json.load(f)
            if c.get("sig") == sig:
                _index[d] = c["faces"]
                return c["faces"]
        except Exception:
            pass
    faces = []
    for p in files:
        faces += _scan_file(p)
    with open(cfile, "w") as f:
        json.dump({"sig": sig, "faces": faces}, f)
    _index[d] = faces
    return faces


def system_faces():
    out = []
    for d in SYSTEM_DIRS:
        out += index_dir(d)
    return out


def cyrillic_families():
    return {f["family"] for f in system_faces() if f["cyrillic"]}


class FontFace:
    def __init__(self, rec):
        self.rec = rec
        self.path, self.index = rec["path"], rec["index"]
        self.family = rec["family"]
        self.axes = rec.get("axes", {})
        blob = hb.Blob.from_file_path(self.path)
        self.hb_face = hb.Face(blob, self.index)
        self.upem = self.hb_face.upem
        self._fonts = {}
        self._paths = {}
        from fontTools.ttLib import TTFont, TTCollection
        tt = TTCollection(self.path, lazy=True).fonts[self.index] if self.path.lower().endswith((".ttc", ".otc")) else TTFont(self.path, lazy=True)
        os2 = tt["OS/2"] if "OS/2" in tt else None
        hhea = tt["hhea"]
        self.ascender = (os2.sTypoAscender if os2 and os2.sTypoAscender else hhea.ascent) / self.upem
        self.descender = (os2.sTypoDescender if os2 and os2.sTypoDescender else hhea.descent) / self.upem
        self.cap_height = (getattr(os2, "sCapHeight", 0) or 0.7 * self.upem) / self.upem if os2 else 0.7
        self.x_height = (getattr(os2, "sxHeight", 0) or 0.5 * self.upem) / self.upem if os2 else 0.5
        self.cmap = tt.getBestCmap() or {}
        name = tt["name"]
        self.psname = (name.getDebugName(6) or self.family.replace(" ", "")).strip()
        self.instances = []
        if "fvar" in tt:
            for inst in tt["fvar"].instances:
                ps = name.getDebugName(inst.postscriptNameID) if inst.postscriptNameID not in (None, 0xFFFF) else None
                sub = name.getDebugName(inst.subfamilyNameID) or ""
                ps = ps or (self.family.replace(" ", "") + "-" + sub.replace(" ", ""))
                self.instances.append((dict(inst.coordinates), ps))

    def ps_for(self, variations=None):
        """PostScript name for After Effects (closest named instance for variable fonts)."""
        if not self.instances or not variations:
            return self.psname
        w = variations.get("wght")
        if w is None:
            return self.psname
        best = min(self.instances, key=lambda it: abs(it[0].get("wght", 400) - w))
        return best[1]

    def hb_font(self, variations=None):
        key = tuple(sorted((variations or {}).items()))
        f = self._fonts.get(key)
        if f is None:
            f = hb.Font(self.hb_face)
            if variations:
                f.set_variations(dict(variations))
            self._fonts[key] = f
        return f

    def shape(self, text, features=None, variations=None, direction=None):
        """Return list of (gid, cluster, x_advance, y_advance, x_offset, y_offset) in em units."""
        font = self.hb_font(variations)
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        if direction:
            buf.direction = direction
        hb.shape(font, buf, features or {})
        u = float(self.upem)
        return [(i.codepoint, i.cluster, p.x_advance / u, p.y_advance / u, p.x_offset / u, p.y_offset / u)
                for i, p in zip(buf.glyph_infos, buf.glyph_positions)]

    def glyph_path(self, gid, variations=None):
        """Glyph outline in em units, y DOWN (ready to draw at baseline origin)."""
        key = (gid, tuple(sorted((variations or {}).items())))
        p = self._paths.get(key)
        if p is None:
            pen = _Pen()
            self.hb_font(variations).draw_glyph_with_pen(gid, pen)
            p = pen.path
            m = skia.Matrix()
            m.setScale(1.0 / self.upem, -1.0 / self.upem)
            p.transform(m)
            self._paths[key] = p
        return p

    def gid(self, ch, variations=None):
        """Nominal glyph id for a character (None if the font lacks it)."""
        if ord(ch) not in self.cmap:
            return None
        g = self.hb_font(variations).get_nominal_glyph(ord(ch))
        return g if g else None

    def missing(self, text):
        return sorted({c for c in text if not c.isspace() and ord(c) not in self.cmap})


class _Pen:
    def __init__(self):
        self.path = skia.Path()

    def moveTo(self, p):
        self.path.moveTo(*p)

    def lineTo(self, p):
        self.path.lineTo(*p)

    def curveTo(self, a, b, c):
        self.path.cubicTo(a[0], a[1], b[0], b[1], c[0], c[1])

    def qCurveTo(self, *pts):
        if len(pts) == 2:
            self.path.quadTo(pts[0][0], pts[0][1], pts[1][0], pts[1][1])
            return
        for i in range(len(pts) - 1):
            c = pts[i]
            e = pts[-1] if i == len(pts) - 2 else ((c[0] + pts[i + 1][0]) / 2, (c[1] + pts[i + 1][1]) / 2)
            self.path.quadTo(c[0], c[1], e[0], e[1])

    def closePath(self):
        self.path.close()

    def endPath(self):
        pass


def _face(rec):
    k = (rec["path"], rec["index"])
    if k not in _faces:
        _faces[k] = FontFace(rec)
    return _faces[k]


def _pick(cands, weight, italic):
    if not cands:
        return None

    def score(r):
        w = r["weight"]
        if "wght" in r["axes"]:
            lo, _, hi = r["axes"]["wght"]
            w = min(max(weight, lo), hi)
        return (abs(w - weight) + (0 if r["italic"] == italic else 500))
    return min(cands, key=score)


PROJECT_FONT_DIRS = []


def set_project_dir(d):
    fd = os.path.join(d, "fonts")
    if fd not in PROJECT_FONT_DIRS:
        PROJECT_FONT_DIRS.insert(0, fd)


def resolve(family, weight=400, italic=False, need_cyrillic=None, kind=None):
    """Return (FontFace, variations dict, source) for a family request. `need_cyrillic` defaults
    to the project language: Ukrainian copy skips fonts without the full Ukrainian alphabet."""
    if need_cyrillic is None:
        need_cyrillic = LANGUAGE in STRICT_LANGUAGES
    fam = (family or "").lower()
    pools = [("project", f) for d in PROJECT_FONT_DIRS for f in index_dir(d)] + [("system", f) for f in system_faces()]
    for src in ("project", "system"):
        cands = [r for s, r in pools if s == src and r["family"].lower() == fam]
        if not cands:
            cands = [r for s, r in pools if s == src and fam and fam.replace(" ", "") in
                     os.path.basename(r["path"]).lower().replace("-", "").replace("_", "")]
        if need_cyrillic:
            cyr = [r for r in cands if r["cyrillic"]]
            if cands and not cyr:
                WARNINGS.append(f"font '{family}' ({src}) has no full Cyrillic; skipped")
            cands = cyr
        r = _pick(cands, weight, italic)
        if r:
            var = {}
            if "wght" in r["axes"]:
                lo, _, hi = r["axes"]["wght"]
                var["wght"] = float(min(max(weight, lo), hi))
            return _face(r), var, src
    kind = kind or ("mono" if "mono" in fam else "serif" if "serif" in fam else "sans")
    fb = FALLBACK[kind]
    WARNINGS.append(f"font '{family}' not found -> fallback {fb}")
    cands = [r for s, r in pools if r["family"].lower() == fb.lower()]
    r = _pick(cands, weight, italic)
    if r is None:
        raise RuntimeError(f"Fallback font {fb} missing; install DejaVu fonts")
    return _face(r), {}, "fallback"
