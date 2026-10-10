"""design.yaml loader: palette roles, type scale, grid, motion language, fx policy, sound palette.

Lengths below 1.0 are fractions of the frame's SHORT side; values >= 1 are pixels.
Every decision block may carry `why:` — `Design.lint()` lists blocks without it.
"""
import yaml

from .core import _hex

# Platform UI overlays (px at 1080x1920). Source: Upload-Post safe-zone checker, based on
# each platform's ad specs (checked 2026-09-23). Organic UI is usually smaller, so the QA
# reports these as WARN, while the 8% frame margin is a hard FAIL.
PLATFORM_ZONES = {
    "tiktok": {"top": 240, "bottom": 660, "left": 120, "right": 120},
    "reels": {"top": 269, "bottom": 672, "left": 65, "right": 65},
    "instagram": {"top": 269, "bottom": 672, "left": 65, "right": 65},
    "shorts": {"top": 288, "bottom": 672, "left": 48, "right": 192},
}
SAFE_MARGIN = 0.08


class Motion:
    def __init__(self, d):
        d = d or {}
        self.tempo = d.get("tempo", "medium")
        e = d.get("easing") or {}
        self.easing = {"enter": e.get("enter", "out_expo"), "exit": e.get("exit", "in_cubic"),
                       "move": e.get("move", "in_out_cubic"), "emphasis": e.get("emphasis", "out_back"),
                       "default": e.get("default", "in_out_cubic")}
        self.easing.update({k: v for k, v in e.items() if k not in self.easing})
        dur = d.get("durations") or {}
        base = {"calm": 1.25, "medium": 1.0, "fast": 0.75}.get(self.tempo, 1.0)
        self.durations = {"micro": 0.18 * base, "short": 0.35 * base, "medium": 0.6 * base, "long": 1.1 * base}
        self.durations.update(dur)
        self.stagger = d.get("stagger", 0.04 * base)
        self.transitions = d.get("transitions", ["cut", "fade"])
        self.raw = d


class Design:
    def __init__(self, raw, path=None):
        self.raw = raw or {}
        self.path = path
        r = self.raw
        self.meta = r.get("meta", {})
        self.format = r.get("format", {})
        self.palette = {}
        for role, v in (r.get("palette") or {}).items():
            if role == "why":
                continue
            hexv = v.get("value") if isinstance(v, dict) else v
            self.palette[role] = _hex(str(hexv))
        self.palette.setdefault("bg", (0, 0, 0, 1))
        self.palette.setdefault("text", (1, 1, 1, 1))
        t = r.get("type") or {}
        sc = t.get("scale") or {}
        self.type_base = sc.get("base", 0.032)
        self.type_ratio = sc.get("ratio", 1.25)
        self.type_roles = {k: v for k, v in (t.get("roles") or {}).items() if k != "why"}
        self.grid_raw = r.get("grid") or {}
        self.shape = r.get("shape") or {}
        self.motion = Motion(r.get("motion"))
        self.fx = r.get("fx") or {}
        self.sound = r.get("sound") or {}
        self.dynamics = r.get("dynamics") or {}
        self.W = self.H = None

    @classmethod
    def load(cls, path):
        with open(path, encoding="utf-8") as f:
            return cls(yaml.safe_load(f), path)

    # ---- binding to frame size
    def bind(self, W, H):
        self.W, self.H = W, H
        return self

    @property
    def short(self):
        return min(self.W, self.H)

    def L(self, v):
        """Length: fraction of the short side if < 1, else px."""
        return v * self.short if abs(v) < 1 else float(v)

    # ---- type
    def size(self, role_or_step):
        if isinstance(role_or_step, (int, float)):
            step = role_or_step
        else:
            spec = self.type_roles.get(role_or_step, {})
            if "size" in spec:
                return self.L(spec["size"])
            step = spec.get("step", 0)
        return self.L(self.type_base) * (self.type_ratio ** step)

    def font(self, role):
        spec = dict(self.type_roles.get(role) or self.type_roles.get("body") or {})
        spec.setdefault("family", "DejaVu Sans")
        spec.setdefault("weight", 400)
        return spec

    # ---- grid
    @property
    def margin(self):
        return self.L(self.grid_raw.get("margin", SAFE_MARGIN))

    @property
    def gutter(self):
        return self.L(self.grid_raw.get("gutter", 0.02))

    @property
    def columns(self):
        return int(self.grid_raw.get("columns", 6))

    def col(self, i, span=1):
        """(x, width) of column i (0-based) spanning `span` columns inside margins."""
        n, m, g = self.columns, self.margin, self.gutter
        cw = (self.W - 2 * m - (n - 1) * g) / n
        x = m + i * (cw + g)
        return x, span * cw + (span - 1) * g

    def x(self, i):
        return self.col(i)[0]

    def rows(self, n):
        """y of n equal rows inside vertical margins: list of (y, h)."""
        m, g = self.margin, self.gutter
        rh = (self.H - 2 * m - (n - 1) * g) / n
        return [(m + j * (rh + g), rh) for j in range(n)]

    @property
    def center(self):
        return (self.W / 2, self.H / 2)

    @property
    def radius(self):
        return self.L(self.shape.get("radius", 0.0))

    @property
    def stroke(self):
        return self.L(self.shape.get("stroke", 0.003))

    def safe(self, platform=None, strict=False):
        """Safe rect (l, t, r, b). strict=True adds platform UI zones (scaled to frame)."""
        m = SAFE_MARGIN * self.short
        l, t, r, b = m, m, self.W - m, self.H - m
        platform = platform or self.format.get("platform")
        if strict and platform in PLATFORM_ZONES and self.W < self.H:
            z = PLATFORM_ZONES[platform]
            k = self.W / 1080
            l, t = max(l, z["left"] * k), max(t, z["top"] * k)
            r, b = min(r, self.W - z["right"] * k), min(b, self.H - z["bottom"] * k)
        return (l, t, r, b)

    def safe_for_camera(self, drift=(24, 14), zoom=1.08, platform=None, strict=False):
        """Safe rect for copy in a scene whose camera drifts by `drift` px and zooms up to
        `zoom`: content near the edges is pushed out by both, so inset the 8% rect."""
        l, t, r, b = self.safe(platform, strict)
        cx, cy = self.W / 2, self.H / 2
        k = max(1.0, zoom)
        # a point at x maps to cx + (x - cx) * k + drift: keep that inside [l, r]
        l2 = cx - (cx - l - drift[0]) / k
        r2 = cx + (r - cx - drift[0]) / k
        t2 = cy - (cy - t - drift[1]) / k
        b2 = cy + (b - cy - drift[1]) / k
        return (l2, t2, r2, b2)

    # ---- policy
    def forbidden(self):
        return [str(x).lower() for x in (self.fx.get("forbidden") or [])]

    def lint(self):
        """Decision blocks without a `why` (each art-direction decision must cite the brief)."""
        missing = []
        for block in ("palette", "type", "grid", "motion", "fx", "sound"):
            b = self.raw.get(block)
            if b is None:
                missing.append(f"{block}: block missing")
                continue
            if isinstance(b, dict) and "why" not in b:
                if block == "palette":
                    for role, v in b.items():
                        if not (isinstance(v, dict) and v.get("why")):
                            missing.append(f"palette.{role}: no why")
                elif block == "type":
                    for role, v in (b.get("roles") or {}).items():
                        if not (isinstance(v, dict) and v.get("why")):
                            missing.append(f"type.roles.{role}: no why")
                else:
                    missing.append(f"{block}: no why")
        lt = self.raw.get("light")
        if lt is None:
            missing.append("light: block missing (key light, ground, shadows, grain, where the accent lives; "
                           "art_direction.md 5b)")
        elif isinstance(lt, dict) and "why" not in lt:
            missing.append("light: no why")
        return missing
