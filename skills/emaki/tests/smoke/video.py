"""Smoke test: touches every primitive, transition and fx once. Not a style example."""
import os
import engine
from engine import *

SKILL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(engine.__file__))))
STYLE = os.path.join(SKILL, "references", "styles", "playful-geometric", "design.yaml")


def build():
    P = Project(STYLE, duration=None, aspect="16:9")
    D = P.design
    W, H = P.W, P.H
    x0, y0, x1, y1 = D.safe()
    P.post["grain"] = {"amount": 0.0}
    # 1: text modes + highlight + shapes + morph
    s = P.scene("text-modes", 3.0, energy=0.3)
    t1 = s.add(Text("Маска по рядках\nі *акцент*", style="display", pos=(x0, y0 + 40), max_width=900))
    t1.reveal(0.1, "mask", by="line")
    t1.highlight((3, 3), 0.9, 0.5, color="accent_3")
    t2 = s.add(Text("Розмиття по словах", style="title", pos=(x0, 560)))
    t2.reveal(0.4, "blur", by="word")
    t3 = s.add(Text("Пружина по літерах", style="title", color="accent_2", pos=(x0, 700)))
    t3.reveal(0.6, "pop", by="char", ease="spring:wobbly", dur=0.6)
    m = s.add(Morph([svg_path("M-100 0 A100 100 0 1 1 100 0 A100 100 0 1 1 -100 0 Z"),
                     polyline_path([(-90, -90), (90, -90), (90, 90), (-90, 90)], closed=True),
                     Star(5, 110, 50).path(0)], fill="accent", pos=(1500, 380)))
    m.morph_to(0.5, 1, 0.6, "spring:snappy").morph_to(1.5, 2, 0.6, "in_out_back")
    st = s.add(Star(5, 60, 28, fill="accent_3", stroke="text", stroke_width=6, pos=(1500, 760)))
    st.pop_in(0.4, 0.6, "spring:wobbly")
    st.rotation.key(0.4, 0).key(2.5, 180, "in_out_cubic")
    # 2: camera parallax + gradient bg + iris
    s2 = P.scene("camera", 3.0, transition=Iris(0.6), energy=0.5,
                 bg=Background(Linear((0, 0), (W, H), [(0, "accent_2"), (1, "accent")])))
    for i, d in enumerate((900, 400, 0, -200)):
        e = s2.add(Ellipse(240 - i * 40, fill=["surface", "accent_3", "text", "accent_4"][i], pos=(500 + i * 300, 540), depth=d))
    s2.add(Text("Паралакс", style="display", color="surface", pos=(x0, 140)))
    s2.camera.pos.key(0, (W / 2, H / 2)).key(3.0, (W / 2 + 300, H / 2), "in_out_cubic")
    s2.camera.zoom.key(0, 1.0).key(3.0, 1.15, "in_out_cubic")
    # 3: UI kit + cursor + toast + phone
    s3 = P.scene("ui", 3.5, transition=ShapeWipe(0.8), energy=0.6)
    win = s3.add(Window(900, 560, url="app.example.com", pos=(x0, 200)))
    card = Card(380, 200, pos=(40, 40))
    card.add(Text("Виторг", style="caption", color="muted", pos=(28, 28), src="invented"))
    card.add(Counter(0, 1284500, 0.6, 1.5, style="title", pos=(28, 80), suffix=" ₴", src="invented"))
    win.body.add(card)
    btn = Button("Надіслати", pos=(250, 340))
    win.body.add(btn)
    btn.press(1.9)
    cur = s3.add(Cursor(pos=(1200, 900)))
    cur.move(0.8, (x0 + 250, 200 + 36 + 340), 0.9, "in_out_cubic").click(1.9)
    ph = s3.add(Phone(360, 740, pos=(1500, 560)))
    ph.screen.add(Toast("Нове повідомлення", "Надійшов звіт за тиждень", w=320, pos=(20, 40), src="invented"))
    ph.screen.children[-1].slide_in(1.2, "down", 80, 0.6)
    tg = s3.add(Toggle(110, pos=(1150, 300)))
    tg.switch(2.4)
    s3.add(Icon("bolt", 90, "accent", pos=(1150, 450)))
    inp = s3.add(Input(500, pos=(x0, 820), placeholder="Пошук…"))
    inp.type(0.5, "моушн-дизайн", src="invented")
    # 4: charts + particles + matte + motion blur + zoom transition
    s4 = P.scene("charts", 4.0, transition=Zoom(0.6), energy=0.8)
    s4.add(LineChart([3, 5, 4, 8, 7, 11, 14], 760, 360, t0=0.3, pos=(x0, 220), labels=["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]))
    s4.add(Donut([40, 30, 20, 10], 150, 40, t0=0.5, pos=(1400, 400)))
    s4.add(Particles(at=(1400, 900), rate=80, direction=-90, spread=50, speed=(300, 500), gravity=(0, 400),
                     colors=("accent", "accent_2", "accent_3"), shape="square", size=(8, 16), life=(1, 1.6), spin=(-200, 200)))
    big = s4.add(Text("МАТТ", style="display", size=260, pos=(x0, 640)))
    stripes = Rect(1400, 400, fill=Linear((-700, 0), (700, 0), [(0, "accent"), (1, "accent_2")]), pos=(x0 + 500, 760))
    stripes.matte(big)
    s4.children.remove(big)
    s4.add(stripes)
    sl = s4.add(Rect(160, 160, fill="text", pos=(200, 980)))
    sl.position.key(2.6, (200, 980)).key(3.2, (1700, 980), "in_out_cubic")
    s4.motion_blur = {"samples": 6, "shutter": 180}
    # 5: transitions sampler
    s5 = P.scene("blur-dip", 2.0, transition=BlurDissolve(0.6), energy=0.4)
    s5.add(Text("Blur dissolve", style="display", pos=(x0, 400)))
    s6 = P.scene("wipe", 2.0, transition=Wipe(0.6, "right", softness=0.2), energy=0.4, bg="accent_3")
    s6.add(Text("Soft wipe", style="display", pos=(x0, 400)))
    s7 = P.scene("dip", 2.0, transition=Dip(0.6, "text"), energy=0.3, bg="accent_2")
    s7.add(Text("Dip to colour", style="display", color="surface", pos=(x0, 400)))
    s7.add(TextOnPath("текст по дузі · текст по дузі", "M 300 900 Q 960 500 1620 900", style="title", color="surface"))
    P.keyframes = [(0.5, "mask lines"), (1.2, "pop chars"), (2.2, "morph star"), (4.5, "parallax"), (7.4, "ui click"),
                   (8.5, "ui toast"), (10.5, "charts"), (12.5, "matte + mb"), (13.0, "blur dissolve"), (15.3, "soft wipe"), (17.2, "dip"), (18.0, "text on path")]
    return P
