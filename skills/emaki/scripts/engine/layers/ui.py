"""UI kit for recreating product interfaces as vectors: Card, Button, Chip, Window, Phone,
Cursor, Toggle, Input, Toast, Avatar, Icon. Every component is a Group of primitives, so
it exports to After Effects as shape + text layers.

Take sizes, radii and colors from the brand source (screenshots / design system). Values
here are only defaults; anything not in the source is a [DESIGN DECISION].
"""
from ..core import Group, Prop, P_, color, CURRENT, DropShadow, SoftShadow
from .shape import Rect, Ellipse, PathShape, svg_path
from .text import Text

# 24x24 icon outlines (stroke-based, original simple geometry)
ICONS = {
    "check": "M5 12.5 L10 17.5 L19 7",
    "plus": "M12 5 V19 M5 12 H19",
    "minus": "M5 12 H19",
    "close": "M6 6 L18 18 M18 6 L6 18",
    "arrow_right": "M5 12 H19 M13 6 L19 12 L13 18",
    "arrow_left": "M19 12 H5 M11 6 L5 12 L11 18",
    "arrow_up": "M12 19 V5 M6 11 L12 5 L18 11",
    "chevron_right": "M9 6 L15 12 L9 18",
    "play": "M8 5 L19 12 L8 19 Z",
    "search": "M10.5 4 A6.5 6.5 0 1 1 10.49 4 Z M15.5 15.5 L20 20",
    "menu": "M4 7 H20 M4 12 H20 M4 17 H20",
    "bell": "M6 16 V11 A6 6 0 0 1 18 11 V16 L19.5 18 H4.5 Z M10 20.5 H14",
    "heart": "M12 20 C5 15 3 11.5 3 8.5 A4.5 4.5 0 0 1 12 6.5 A4.5 4.5 0 0 1 21 8.5 C21 11.5 19 15 12 20 Z",
    "star": "M12 3.5 L14.6 9 L20.5 9.6 L16 13.6 L17.3 19.5 L12 16.5 L6.7 19.5 L8 13.6 L3.5 9.6 L9.4 9 Z",
    "user": "M12 12 A4 4 0 1 1 12.01 12 Z M4.5 20.5 C5.5 16.5 8.5 15 12 15 C15.5 15 18.5 16.5 19.5 20.5",
    "lock": "M6 11 H18 V20 H6 Z M8.5 11 V8 A3.5 3.5 0 0 1 15.5 8 V11",
    "bolt": "M13 3 L5 13.5 H11.5 L10.5 21 L19 10 H12.5 Z",
    "chart": "M5 19 V11 M10 19 V6 M15 19 V13 M20 19 V8",
    "calendar": "M4 6.5 H20 V20 H4 Z M4 10.5 H20 M8.5 4 V8 M15.5 4 V8",
    "chat": "M4 5.5 H20 V16 H11 L7 19.5 V16 H4 Z",
    "mail": "M3.5 6 H20.5 V18 H3.5 Z M3.5 6.5 L12 13 L20.5 6.5",
    "home": "M4 11 L12 4 L20 11 V20 H14.5 V14.5 H9.5 V20 H4 Z",
    "gear": "M12 8.5 A3.5 3.5 0 1 1 11.99 8.5 Z M12 2.5 V5 M12 19 V21.5 M2.5 12 H5 M19 12 H21.5 M5.3 5.3 L7.1 7.1 M16.9 16.9 L18.7 18.7 M5.3 18.7 L7.1 16.9 M16.9 7.1 L18.7 5.3",
    "pin": "M12 21 C7 15.5 5.5 12.5 5.5 9.5 A6.5 6.5 0 0 1 18.5 9.5 C18.5 12.5 17 15.5 12 21 Z M12 7.5 A2 2 0 1 1 11.99 7.5 Z",
    "globe": "M12 3 A9 9 0 1 1 11.99 3 Z M3 12 H21 M12 3 C9 6 9 18 12 21 C15 18 15 6 12 3",
    "sparkle": "M12 3 L13.8 10.2 L21 12 L13.8 13.8 L12 21 L10.2 13.8 L3 12 L10.2 10.2 Z",
}
CURSOR = "M0 0 L0 22 L6 16.5 L10 25 L13.5 23.5 L9.6 15.2 L17 15.2 Z"


def _d():
    return CURRENT["design"]


class Icon(Group):
    kind = "icon"

    def __init__(self, name, size=48, color_="text", stroke_width=None, filled=False, **kw):
        super().__init__(**kw)
        s = size / 24.0
        sw = stroke_width or 1.8
        p = svg_path(ICONS[name])
        from ..core import skia
        m = skia.Matrix()
        m.setScale(s, s)
        m.preTranslate(-12, -12)
        p.transform(m)
        shp = PathShape(p, fill=color_ if filled else None, stroke=None if filled else color_,
                        stroke_width=sw * s, name=f"Icon {name}")
        self.add(shp)
        self.shape = shp


class Card(Group):
    """Rounded surface with optional soft shadow. Children go in card-local coords where
    (0, 0) is the card's top-left corner."""
    kind = "card"

    def __init__(self, w, h, fill="surface", radius=None, shadow=True, stroke=None, **kw):
        super().__init__(**kw)
        d = _d()
        r = radius if radius is not None else (d.radius if d else 16)
        bg = Rect(w, h, radius=r, fill=fill, stroke=stroke, stroke_width=1.5 if stroke else None,
                  pos=(w / 2, h / 2), name=f"{self.name} BG")
        if shadow == "soft":
            bg.fx.append(SoftShadow(elev=h * 0.1 + 12, opacity=0.3))
        elif shadow:
            bg.fx.append(DropShadow(0, h * 0.04 + 6, sigma=h * 0.08 + 12, color="#000000",
                                    opacity=0.18 if shadow is True else shadow))
        self.add(bg)
        self.bg = bg
        self.w, self.h = w, h


class Button(Group):
    kind = "button"

    def __init__(self, label, w=None, h=None, fill="accent", text_color="bg", radius=None, style="body",
                 weight=None, src="brief", **kw):
        super().__init__(**kw)
        d = _d()
        t = Text(label, style=style, color=text_color, weight=weight or 600, anchor="center", src=src)
        h = h or t.height * 2.6
        w = w or t.width + h * 1.2
        r = radius if radius is not None else h / 2
        self.bg = Rect(w, h, radius=r, fill=fill, name=f"{self.name} BG")
        self.label = t
        self.add(self.bg, t)
        self.w, self.h = w, h

    def press(self, t, depth=0.94):
        """Tap feedback: quick scale dip and release."""
        rest = self.scale.rest()
        self.scale.key(t, rest).key(t + 0.08, (rest[0] * depth, rest[1] * depth), "out_quad") \
            .key(t + 0.3, rest, "out_back")
        return self


class Chip(Group):
    kind = "chip"

    def __init__(self, label, fill="accent@0.14", text_color="accent", style="caption", src="brief", **kw):
        super().__init__(**kw)
        t = Text(label, style=style, color=text_color, anchor="center", src=src)
        h = t.height * 2.2
        w = t.width + h
        self.add(Rect(w, h, radius=h / 2, fill=fill, name=f"{self.name} BG"), t)
        self.w, self.h = w, h


class Window(Group):
    """Desktop/browser window: title bar with three dots and optional URL pill.
    Put content into `.body` (coords from the body's top-left)."""
    kind = "window"

    def __init__(self, w, h, url=None, fill="surface", bar="bg", radius=None, shadow=True, **kw):
        super().__init__(**kw)
        d = _d()
        r = radius if radius is not None else (d.radius if d else 14)
        bar_h = max(36.0, h * 0.075)
        frame = Rect(w, h, radius=r, fill=fill, pos=(w / 2, h / 2), name="Window Frame")
        if shadow:
            frame.fx.append(DropShadow(0, 18, 50, "#000000", 0.22))
        self.add(frame)
        topbar = Rect(w, bar_h, radius=0, fill=bar, pos=(w / 2, bar_h / 2), name="Window Bar")
        topbar.clip = Prop((-w / 2, -bar_h / 2, w, bar_h), "clip")
        self.add(topbar)
        for i, c in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
            self.add(Ellipse(bar_h * 0.3, fill=c, pos=(bar_h * 0.6 + i * bar_h * 0.45, bar_h / 2), name=f"Dot {i + 1}"))
        if url:
            pill_w = w * 0.45
            self.add(Rect(pill_w, bar_h * 0.6, radius=bar_h * 0.3, fill="surface", pos=(w / 2, bar_h / 2), name="URL Pill"))
            self.add(Text(url, style="caption", color="muted", anchor="center", pos=(w / 2, bar_h / 2), role="decor", src="decor"))
        self.body = Group(pos=(0, bar_h), name="Window Body")
        self.body.clip = Prop((0, 0, w, h - bar_h), "clip")
        self.add(self.body)
        self.w, self.h, self.bar_h = w, h, bar_h


class Phone(Group):
    """Phone frame centered on origin. Content goes into `.screen` (screen top-left = 0,0)."""
    kind = "phone"

    def __init__(self, w=420, h=880, body="#0E0E10", screen_fill="bg", radius=None, notch=True, shadow=True, **kw):
        super().__init__(**kw)
        r = radius if radius is not None else w * 0.14
        bezel = w * 0.035
        fr = Rect(w, h, radius=r, fill=body, name="Phone Body")
        if shadow:
            fr.fx.append(DropShadow(0, 24, 60, "#000000", 0.3))
        self.add(fr)
        sw_, sh_ = w - 2 * bezel, h - 2 * bezel
        self.add(Rect(sw_, sh_, radius=r - bezel, fill=screen_fill, name="Phone Screen BG"))
        self.screen = Group(pos=(-sw_ / 2, -sh_ / 2), name="Phone Screen")
        self.screen.clip = Prop((0, 0, sw_, sh_), "clip")
        self.add(self.screen)
        if notch:
            self.add(Rect(w * 0.3, h * 0.032, radius=h * 0.016, fill=body, pos=(0, -sh_ / 2 + h * 0.03), name="Notch"))
        self.w, self.h, self.sw, self.sh = w, h, sw_, sh_


class Cursor(Group):
    """Mouse pointer. Tip is at the layer origin. click(t) adds press + ripple (+ sound)."""
    kind = "cursor"

    def __init__(self, size=1.0, fill="#FFFFFF", outline="#111111", ripple="accent", **kw):
        super().__init__(**kw)
        from ..core import skia
        p = svg_path(CURSOR)
        m = skia.Matrix()
        m.setScale(1.6 * size, 1.6 * size)
        p.transform(m)
        self.ripple_color = ripple
        self.size = size
        self.arrow = PathShape(p, fill=fill, stroke=outline, stroke_width=2.2 * size, name="Cursor Arrow")
        self.arrow.fx.append(DropShadow(0, 3, 8, "#000000", 0.3))
        self.add(self.arrow)
        self.clicks = []

    def click(self, t, sound="click"):
        r = Ellipse(10, fill=None, stroke=self.ripple_color, stroke_width=3 * self.size, name=f"Ripple {len(self.clicks) + 1}")
        r.size.key(t, (6.0, 6.0)).key(t + 0.45, (90.0 * self.size, 90.0 * self.size), "out_cubic")
        r.opacity.key(t, 0.9).key(t + 0.45, 0.0, "in_quad")
        r.show(t, t + 0.5)
        r.scene = self.scene
        self.children.insert(0, r)          # ripple under the arrow
        rest = self.arrow.scale.rest()
        self.arrow.scale.key(t - 0.02, rest).key(t + 0.06, (rest[0] * 0.86, rest[1] * 0.86), "out_quad") \
            .key(t + 0.25, rest, "out_back")
        self.clicks.append((t, sound))
        return self

    def audio_events(self):
        return [(t, s, {}) for t, s in self.clicks if s]


class Toggle(Group):
    kind = "toggle"

    def __init__(self, w=96, on=False, on_color="accent", off_color="muted@0.4", knob="#FFFFFF", **kw):
        super().__init__(**kw)
        h = w * 0.58
        self.track = Rect(w, h, radius=h / 2, fill=off_color if not on else on_color, name="Toggle Track")
        self.knob = Ellipse(h * 0.8, fill=knob, pos=((w - h) / 2 * (1 if on else -1), 0), name="Toggle Knob")
        self.knob.fx.append(DropShadow(0, 2, 6, "#000000", 0.25))
        self.add(self.track, self.knob)
        self.w, self.h, self.on_color, self.off_color, self.on = w, h, on_color, off_color, on

    def switch(self, t, dur=0.3):
        x = (self.w - self.h) / 2
        a, b = (-x, x) if not self.on else (x, -x)
        self.knob.position.key(t, (a, 0.0)).key(t + dur, (b, 0.0), "in_out_cubic")
        c0, c1 = (self.off_color, self.on_color) if not self.on else (self.on_color, self.off_color)
        self.track.fill.color.key(t, color(c0)).key(t + dur, color(c1), "in_out_sine")
        self.on = not self.on
        return self


class Input(Group):
    """Text field. type(t, text) types into it with a caret."""
    kind = "input"

    def __init__(self, w, h=None, placeholder="", fill="surface", stroke="muted@0.5", style="body", **kw):
        super().__init__(**kw)
        d = _d()
        h = h or (d.size(style) * 2.4 if d else 64)
        r = d.radius if d else 12
        self.bg = Rect(w, h, radius=r, fill=fill, stroke=stroke, stroke_width=2, pos=(w / 2, h / 2), name="Input BG")
        self.add(self.bg)
        self.style, self.w, self.h = style, w, h
        self.ph = None
        if placeholder:
            self.ph = Text(placeholder, style=style, color="muted", anchor="cl", pos=(h * 0.4, h / 2), role="decor", src="decor")
            self.add(self.ph)

    def type(self, t, text, cps=14, sound="type", src="brief"):
        tx = Text(text, style=self.style, anchor="cl", pos=(self.h * 0.4, self.h / 2), src=src)
        tx.typewriter(t, cps=cps, cursor=True, cursor_shape="bar", sound=sound)
        self.add(tx)
        if self.ph is not None:
            self.ph.opacity.key(t - 0.01, 1.0).key(t, 0.0, "hold")
        return tx


class Toast(Group):
    """Notification card that slides in from `edge` and leaves after `hold` seconds."""
    kind = "toast"

    def __init__(self, title, body=None, w=640, icon="bell", fill="surface", src="brief", **kw):
        super().__init__(**kw)
        d = _d()
        pad0 = 0.04 * w
        tx0 = pad0 * 2 + 0.14 * w if icon else pad0
        th = Text(title, style="body", weight=700, anchor="tl", src=src, max_width=w - tx0 - pad0)
        bh = Text(body, style="body", color="muted", anchor="tl", max_width=w - tx0 - pad0, src=src) if body else None
        pad = 0.04 * w
        icon_s = 0.1 * w
        lh = th.st["size"] * th.st.get("line_height", 1.2)
        h = pad * 2 + th.height + lh * 0.35 + ((bh.height + bh.st["size"] * 0.9) if bh else 0)
        card = Card(w, h, fill=fill, shadow=True, name="Toast Card")
        self.add(card)
        if icon:
            self.add(Ellipse(icon_s * 1.4, fill="accent@0.15", pos=(pad + icon_s * 0.7, h / 2), name="Toast Icon BG"))
            self.add(Icon(icon, icon_s, "accent", pos=(pad + icon_s * 0.7, h / 2)))
        tx = pad * 2 + icon_s * 1.4 if icon else pad
        th.position.set((tx, pad))
        self.add(th)
        if bh:
            bh.position.set((tx, pad + th.height + lh * 0.55))
            self.add(bh)
        self.w, self.h = w, h


class Avatar(Group):
    kind = "avatar"

    def __init__(self, initials, size=96, fill="accent", text_color="bg", **kw):
        super().__init__(**kw)
        self.add(Ellipse(size, fill=fill, name="Avatar BG"))
        self.add(Text(initials, size=size * 0.38, weight=700, color=text_color, anchor="center", role="decor", src="decor"))
