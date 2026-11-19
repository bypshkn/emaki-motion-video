"""Space demo (test fixture): a 2.5D set filmed head-on. Floor, Reflection, LightBeam, dust,
haze, depth of field; camera setups (shot) cut on beats, crane, a small orbit, dolly, truck, a
close-up through the lens (never a near camera: it bends the type), a blur window. Every angle stays within 15 degrees of head-on (QA oblique): seen from the side,
flat layers read as PowerPoint 3D. One world, four setups, 8 s.
Run: mv.py styleframes tests/space_demo (copy it out first)."""
from engine import *

FLOOR_Y = 700          # world height of the floor (y grows down)


def build():
    P = Project("design.yaml")
    W, H = P.W, P.H
    s = P.scene("set", 8.0, energy=0.6)
    cam = s.camera
    s.add(Background(Radial((W / 2, H * 0.38), W * 0.9, [(0, "#141821"), (0.55, "#0A0C11"), (1, "bg")]), name="air"))
    s.haze("bg", near=700, far=7000, amount=0.85)

    # the set: a floor with bay lines, pools of light under two lamps
    fl = s.add(Floor(FLOOR_Y, z=3000, size=(20000, 20000), near="surface", bays=520, line_color="text@0.08",
                     horizon=0.5))
    fl.pool(560, 900, 900, "accent", 0.45, squash=0.8)
    fl.pool(1500, 1700, 1000, "accent", 0.40, squash=0.8)
    under = fl.pool(960, 0, 1300, "accent", 0.12)
    under.key(6.2, 0.12).key(6.5, 0.3, "out_cubic")      # the stage light comes up on the last setup
    for x, z, t_on in ((560, 900, 0.1), (1500, 1700, 5.3)):
        b = s.add(LightBeam(length=FLOOR_Y + 420, width=1100, top=150, color_="accent", intensity=0.18,
                            pos=(x, -420), depth=z, name=f"lamp {x}"))
        b.intensity.key(t_on, 0.0).key(t_on + 0.12, 0.26, "out_quad").key(t_on + 0.7, 0.18, "out_cubic")

    # the hero: one word standing on the floor, with thickness and a reflection
    hero = s.add(Text("DEPTH", style="display", size=430, color="text", anchor="bc", pos=(W / 2, FLOOR_Y),
                      src="invented", name="hero"))
    hero.reveal(0.25, "rise", by="char", dur=0.5, stagger=0.06)
    hero.sheen(2.3, 0.9, angle=20, strength=0.7, color_="accent_2")
    hero.punch(4.4, 0.1)
    hero.allow("offframe", why="the close-up crops the word on purpose")
    s.add(Reflection(hero, FLOOR_Y, opacity=0.22, blur=5))

    # depth planes: a far monolith, a near caption, a foreground bar that the camera passes
    mono = s.add(Rect(260, 1400, radius=6, fill="#141822", anchor="bc", pos=(1640, FLOOR_Y), depth=2600, name="monolith"))
    mono.position.key(0, (1640, FLOOR_Y)).key(8.0, (1580, FLOOR_Y), "in_out_sine")
    for txt, t0, t1 in (("ONE WORLD", 1.0, 4.2), ("FOUR SETUPS", 5.6, None)):
        cap = s.add(Text(txt, style="caption", color="accent_2", anchor="bc", pos=(W / 2, FLOOR_Y - 470), depth=-160,
                         src="invented", name=f"caption {txt}", start=t0, end=t1))
        cap.reveal(t0, "fade", by="char", dur=0.6)
        if t1:
            cap.fade_out(t1 - 0.4, 0.35)
        cap.face_camera()
    fg = s.add(Rect(70, 1600, radius=35, fill="#0E1118", anchor="bc", pos=(300, FLOOR_Y + 40), depth=-1300,
                    name="foreground pillar"))
    fg.allow("static", why="set dressing in the foreground: sells the depth as the camera moves")
    mono.allow("static", why="set dressing at the back of the stage")
    dust(s, (W / 2, 360, 1200), size=(4200, 1500, 5200), n=110, split=0.0, radius=(1.6, 4.2), color_="accent_2")

    # camera: focus on the word, four setups cut on the beat
    cam.dof(aperture=9, focus=0)
    box = (W / 2 - 700, FLOOR_Y - 430, W / 2 + 700, FLOOR_Y)
    # 1. establishing: wide and a little high; crane down to eye level while the camera dollies in
    cam.shot(0.0, box, "wide", angle="high", side=-6)
    cam.crane(0.0, 2.6, dy=40, tilt=-12, ease="in_out_cubic")
    cam.dolly(0.0, 2.6, 900, ease="in_out_cubic")
    # 2. a small arc at eye level: the planes slide against each other
    cam.orbit(2.6, 4.4, ry=12, ease="in_out_sine")
    # 3. cut: close through a long lens at eye level (the camera keeps its distance, so the letters
    #    stay straight), then it pushes slowly into the word
    cam.shot(4.4, box, 1.45, angle="eye", offset=(-200, -40))
    cam.dolly(4.5, 6.2, 260, ease="in_out_sine")
    # 4. cut: full shot, normal lens; the camera trucks right, the foreground pillar slides past
    cam.shot(6.2, box, "full", lens=1.0)
    cam.glide(6.2, 8.0, dx=240)
    cam.rack_focus(7.2, -1300, 0.6)
    P.blur_window(0.25, 0.75, 6)            # the letters rise fast while the camera barely moves
    for t, k in ((0.0, "whoosh"), (4.4, "impact"), (6.2, "impact")):
        s.sfx(t, k)
    P.keyframes = [(1.2, "establishing: wide, crane down"), (3.6, "small arc at eye level"),
                   (5.6, "cut: close through the lens, push in"), (7.6, "cut: full, truck, focus forward")]
    return P
