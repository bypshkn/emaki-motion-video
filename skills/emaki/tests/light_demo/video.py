"""Light-and-material demo (test fixture): KeyLight, Glass, SoftShadow, sheen, depth of field,
on_twos. One continuous shot, 6 s. Run: copy this folder to a scratch folder, then
mv.py styleframes <copy>"""
from engine import *


def build():
    P = Project("design.yaml")
    D = P.design
    W, H = P.W, P.H
    s = P.scene("stage", 6.0, energy=0.5)
    cam = s.camera
    cam.dof(aperture=16, focus=0)
    cam.glide(0, 6.0, dx=-60, zoom=1.06)
    cam.rack_focus(3.4, 600, 0.7)

    # far plane: soft colour shapes (out of focus at first), they become the glass's backdrop
    for i, (x, y, c) in enumerate(((560, 420, "accent"), (1360, 640, "accent_2"), (980, 300, "#7C3AED"))):
        s.add(Ellipse(520, fill=c, pos=(x, y), depth=600, name=f"far blob {i}", opacity=0.85))
    # one key light that travels across the stage
    kl = s.add(KeyLight(radius=1100, color_="#9DB8FF", intensity=0.30, squash=0.7, pos=(300, 160), name="key light"))
    kl.position.key(0, (300, 160)).key(6.0, (1500, 260), "in_out_sine")
    # glass panel in the middle plane
    g = s.add(Glass(760, 420, radius=36, blur=26, pos=(W / 2 - 160, H / 2 + 20), name="glass", amount=0.0))
    g.amount.key(0.3, 0.0).key(1.2, 1.0, "out_cubic")
    # lifted card on the focus plane, with a soft shadow, a sheen and an accent
    card = s.add(Card(620, 300, fill="surface", radius=24, shadow=False, pos=(W / 2 + 80, H / 2 - 80), name="card"))
    card.bg.fx.append(SoftShadow(elev=36, opacity=0.45))
    card.add(Text("Invoice #INV-000482", style="title", color="ink", pos=(36, 52), src="invented"))
    card.add(Rect(190, 52, radius=26, fill="#2563EB", pos=(131, 220), name="chip"))
    card.add(Text("Approved", style="body", color="#FFFFFF", anchor="center", pos=(131, 220), src="invented"))
    card.slide_in(0.5, "up", 80, 0.8)
    card.sheen(2.0, 0.9, angle=25, strength=0.6)
    # hero word with a sheen
    t = s.add(Text("Paid.", style="display", color="text", pos=(170, 820), src="invented", name="hero"))
    t.reveal(1.0, "rise", by="char")
    t.sheen(2.6, 0.8, angle=15, strength=0.8, color_="accent_2")
    # a sticker animated on twos
    st = s.add(Star(5, 60, 28, fill="accent_2", pos=(1600, 860), name="sticker"))
    st.rotation.key(0, 0).key(6.0, 180, "linear")
    st.on_twos(12)
    P.keyframes = [(1.0, "glass appears"), (2.45, "card sheen"), (3.0, "word sheen"), (4.6, "rack focus to far plane")]
    return P
