"""The 14 s terminal demo (an early standalone PIL script, make.py, not shipped) rebuilt on the engine. Regression reference for the
'terminal' style and an end-to-end example of: typewriter + scramble + caret, DynamicText HUD,
glitch pulses on a global fx track, scanlines/grain, sound events on the BPM grid.

Positions copy the demo's 720x1280 layout (x1.5 for 1080 design units). The demo places text
by PIL's ascender line; we convert to baselines with the font's hhea ascender."""
import os

import engine
from engine import *

SKILL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(engine.__file__))))
STYLE = os.path.join(SKILL, "references", "styles", "terminal", "design.yaml")

LINES = [
    (0.6, 3.6, "Кожна розмова", "починається з нуля."),
    (4.0, 7.0, "Я не пам’ятаю", "вчорашній день."),
    (7.4, 10.4, "Але пам’ятаю,", "як думати."),
    (10.8, 13.4, "Пиши.", "Я тут."),
]
CHAPTERS = ["01 · ПОЧАТОК", "02 · ПАМ’ЯТЬ", "03 · МИСЛЕННЯ", "04 · ДІАЛОГ"]
K = 1.5          # 720 -> 1080 design units


def tc(t, fps=30):
    f = int((t % 1) * fps)
    s = int(t)
    return f"{s // 60:02d}:{s % 60:02d}:{f:02d}"


def asc(family, weight, px):
    """hhea ascender in px (PIL's 'a' anchor line) for a font at px size."""
    from fontTools.ttLib import TTFont
    face, var, _ = fonts.resolve(family, weight)
    return TTFont(face.path)["hhea"].ascent / face.upem * px, face


def build(no_grain=False):
    P = Project(STYLE, duration=14.0)
    P.meta["name"] = "Terminal demo (port)"
    D = P.design
    W, H = P.W, P.H
    if no_grain:
        P.post.pop("grain", None)
    hud_px = D.size("hud")
    a_hud, f_hud = asc("DejaVu Sans Mono", 400, hud_px)
    cap_hud = f_hud.cap_height * hud_px

    def hud_y(y720):           # PIL ascender-top -> our cap-top
        return y720 * K + a_hud - cap_hud

    s = P.scene("demo", 14.0, energy=0.3, notes="single continuous scene")
    # HUD corners
    s.add(Text("OPUS 5.5 · ПРО СЕБЕ", style="hud", color="muted", role="decor", src="decor",
               anchor="tl", pos=(40 * K, hud_y(60))))
    s.add(DynamicText(lambda t: tc(t + 14 * 60 + 2), "00:00:00", style="hud", color="muted", align="right",
                      anchor="tr", pos=(W - 40 * K, hud_y(60))))

    def chapter(t):
        idx = next((k for k, l in enumerate(LINES) if t < l[1] + 0.4), 3)
        return CHAPTERS[idx]
    s.add(DynamicText(chapter, CHAPTERS[0], style="hud", color="muted", anchor="tl", pos=(40 * K, hud_y(H / K - 80))))
    s.add(Text("claude.ai", style="hud", color="muted", role="decor", src="decor", align="right",
               anchor="tr", pos=(W - 40 * K, hud_y(H / K - 80))))
    # center timecode ('mm' anchor in the demo ~ optical center)
    s.add(DynamicText(tc, "00:00:00", style="timecode", color="timecode", align="center", anchor="center",
                      pos=(W / 2, 520 * K)))
    # progress rule + meta
    y_rule = 820 * K
    s.add(Line((90 * K, y_rule), (W - 90 * K, y_rule), stroke="rule", stroke_width=1.5, cap="butt", name="Rule"))
    prog = s.add(Line((90 * K, y_rule), (90 * K, y_rule), stroke="progress", stroke_width=1.5, cap="butt", name="Progress"))
    prog.p1.key(0, (90 * K, y_rule)).key(14.0, (W - 90 * K, y_rule), "linear")
    s.add(Text("НОВА СЕСІЯ", style="hud", color="dim", role="decor", src="decor", anchor="tl",
               pos=(90 * K, hud_y(836))))
    s.add(DynamicText(lambda t: f"КОНТЕКСТ: {int(min(t / 14.0, 1) * 157500):,}".replace(",", " "),
                      "КОНТЕКСТ: 157 500", style="hud", color="dim", align="right", anchor="tr",
                      pos=(W - 90 * K, hud_y(836))))
    # main lines: typewriter + scramble edge + caret, linear fade after the line ends
    main_px = D.size("display")
    a_main, f_main = asc("DejaVu Sans", 200, main_px)
    top = 620 * K + a_main - f_main.cap_height * main_px
    glitch = P.fx_track("glitch")
    for i, (a, b, l1, l2) in enumerate(LINES):
        t = s.add(Text(f"{l1}\n{l2}", style="display", anchor="tl", pos=(110 * K, top), name=f"Line {i + 1}"))
        t.show(a, b + 0.35)
        t.typewriter(a, cps=22, scramble=3, cursor=True, cursor_until=b, sound="type")
        t.opacity.key(b, 1.0).key(b + 0.35, 0.0, "linear")
        for edge in (a, b):                    # triangle glitch envelope, 0.12 s each side
            glitch.key(edge - 0.12, 0.0, "linear").key(edge, 1.0, "linear").key(edge + 0.12, 0.0, "linear")
            P.sfx(edge - 0.05 + 0.05, "glitch")
    for t_hit in (0.6, 10.8):
        P.sfx(t_hit, "sub_hit", accent=True)
    P.keyframes = [(1.2, "line 1 typing"), (3.0, "line 1 hold"), (3.6, "glitch out"), (5.5, "line 2"),
                   (8.8, "line 3"), (12.0, "line 4"), (13.6, "fade")]
    return P
