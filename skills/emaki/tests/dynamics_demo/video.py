"""Dynamics demo (neon-tech): every new primitive once, beat-locked at 120 BPM."""
import os
import engine
from engine import *

SKILL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(engine.__file__))))
STYLE = os.path.join(SKILL, "references", "styles", "neon-tech", "design.yaml")


def floor(W, H):
    return GridPlane(w=3600, h=3000, step=110, stroke="grid", width=2.0, scroll=(0, 140), fade=0.45,
                     pos=(W / 2, H * 0.80), rx=74, name="Floor")


def build():
    P = Project(STYLE)
    P.target_duration = None          # demo: the length is whatever the scenes add up to
    D = P.design
    W, H = P.W, P.H
    x0, y0, x1, y1 = D.safe_for_camera(drift=(30, 20), zoom=1.1)   # copy stays safe under the moving camera
    b = 60 / P.bpm                          # 0.5 s beat
    # 1 -- light writes the greeting ---------------------------------------------------
    s1 = P.scene("write", 4 * b * 2, energy=0.4)
    s1.camera.glide(0, 8 * b, dx=-30, dy=-20, zoom=1.06)        # one-way push, never back and forth
    s1.add(floor(W, H))
    hi = s1.add(Text("Привіт,", style="light", size=200, pos=(x0 + 30, 640), src="invented", name="Hello"))
    hi.write_on(0.0, cps=9, head_color="accent", glow=1.2)
    sub = s1.add(Text("це *рух*", style="title", pos=(x0 + 30, 900), src="invented", name="Sub"))
    sub.reveal(4 * b - 0.05, "mask", by="word", dur=0.35)
    sub.punch(4 * b + 0.3, 0.06)
    s1.add(Comet([(x0, 1080), (x1, 1080)], t0=4 * b, dur=0.7, ease="out_expo", width=3, head=10, name="Underline"))
    s1.add(Text("01 · HELLO", style="label", color="muted", pos=(x0, 560), role="decor", src="decor"))
    s1.sfx(4 * b, "impact", accent=True)
    # 2 -- word slams with flash frames ------------------------------------------------
    s2 = P.scene("slams", 6 * b, transition=FlashCut(0.2), energy=0.8)
    s2.camera.zoom.set(1.08)
    s2.camera.glide(0, 6 * b, zoom=1.05)
    kw = s2.add(KineticWords(["КОЖЕН", "КАДР", "ЖИВИЙ"], [0.0, 2 * b, 4 * b], style="display",
                             colors=["ink", "ink", "ink"], flashes=["flash", "accent_2", "flash"], src="invented"))
    for w in kw.children:
        if isinstance(w, Text):
            w.echo(3, 0.03, 0.45)
    for k in range(3):
        s2.sfx(2 * k * b, "impact", accent=True)
    # 3 -- perspective panels, comet connector, wireframe, waveform -------------------
    s3 = P.scene("system", 8 * b, transition=Whip(0.36, "left"), energy=0.7)
    s3.camera.glide(0, 2 * b, zoom=1.04)
    s3.camera.travel(2 * b, to=(W / 2 + 60, H / 2 + 140), zoom=1.1, dur=0.45)   # fly to card B, auto motion blur
    s3.camera.glide(2 * b + 0.45, 8 * b, dx=-20, zoom=1.03)
    s3.add(floor(W, H))
    a = s3.add(Card(380, 220, fill="surface", stroke="accent@0.6", pos=(x0, 520), ry=-24, name="Card A"))
    a.add(Text("PROMPT", style="label", color="muted", pos=(28, 28), role="decor", src="decor"))
    a.add(Text("Опиши", style="title", pos=(28, 80), src="invented"))
    a.tilt_in(0.0, ry=-70, dur=0.5).fade_in(0.0, 0.2)
    c = s3.add(Card(380, 220, fill="surface", stroke="accent@0.6", pos=(x1 - 380, 1000), ry=24, name="Card B"))
    c.add(Text("RENDER", style="label", color="muted", pos=(28, 28), role="decor", src="decor"))
    c.add(Text("Відео", style="title", pos=(28, 80), src="invented"))
    c.tilt_in(2 * b, ry=70, dur=0.5).fade_in(2 * b, 0.2)
    s3.add(Comet("M %d 740 C %d 900, %d 840, %d 1000" % (x0 + 190, x0 + 190, x1 - 190, x1 - 190), t0=b, dur=1.2,
                 ease="in_out_expo", width=3, head=11, name="Connector"))
    s3.add(Wire3D("icosa", 200, spin=(25, 40, 0), stroke="accent_2", pos=(W * 0.72, 380), name="Ico"))
    s3.add(Wire3D("cube", 150, spin=(-30, 20, 10), stroke="muted", pos=(W * 0.25, 1320), name="Cube"))
    wf = s3.add(Waveform(w=x1 - x0, h=160, bars=48, stroke="accent", pos=(x0, 1500), name="Wave"))
    wf.fade_in(3 * b, 0.3)
    s3.sfx(b, "whoosh")
    s3.sfx(2 * b, "impact", accent=True)
    # 4 -- big word with echo, smear move, glitch out ---------------------------------
    s4 = P.scene("motion", 8 * b, transition=ScaleThrough(0.4), energy=0.9)
    s4.camera.glide(0, 8 * b, zoom=1.06)
    s4.add(floor(W, H))
    big = s4.add(Text("МОУШН", style="display", size=330, fit=(x1 - x0) * 0.86, color="text", align="center", anchor="center",
                      pos=(W / 2, 820), src="invented", name="Big"))
    big.echo(5, 0.03, 0.5).smear(0.01)
    big.show(0, 5 * b + 0.45)                 # gone once it has flown out
    big.position.key(0, (W / 2 - 700, 820)).key(0.45, (W / 2, 820), "out_expo") \
        .key(5 * b, (W / 2, 820)).key(5 * b + 0.4, (W / 2 + 900, 820), "in_expo")
    big.punch(0.45, 0.05)
    ln = s4.add(Text("графіка, що *тримає* погляд", style="body", align="center", anchor="center",
                     pos=(W / 2, 1060), src="invented", name="Line"))
    ln.reveal(b, "rise", by="word", dur=0.35)
    ln.unreveal(5 * b, "fade", by="word")
    P.pulse("glitch", s4.t0 + 7 * b, 1.0, attack=0.1, release=0.25)
    s4.sfx(7 * b, "glitch")
    s4.sfx(0.45, "impact", accent=False)
    P.keyframes = [(1.0, "nib writes"), (2.3, "sub + underline"), (4.1, "slam 1"), (5.1, "slam 2"), (6.1, "slam 3"),
                   (7.6, "panels tilt in"), (8.6, "connector"), (9.8, "system"), (11.0, "big word"), (12.6, "hold, push"),
                   (13.0, "smear out"), (13.6, "glitch")]
    return P
