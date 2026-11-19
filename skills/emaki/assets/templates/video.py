"""Composition for this video. `build()` returns the Project.

One continuous shot (references/motion.md section 00): ONE scene on a big canvas, a carrier
layer that becomes each next idea, a camera that travels between ideas and glides while they are
read, one light source (art_direction.md 5b), layers staged in depth and filmed from more than
one setup (motion.md 2b). A list of short scenes joined by transitions is the slideshow this
skill must not make; one plane with a camera sliding over it is the flat film.

- Units are final-resolution pixels; scene times are seconds from the scene start.
- Beats on the grid: P.bar(n), P.beat(n), P.snap(t).
- Brief copy verbatim (src="brief"); anything you write is src="invented"; HUD/labels role="decor".
- P.keyframes = the 3-5 moments that explain the film: gate 1 renders them as style frames.
"""
from engine import *


def build():
    P = Project("design.yaml")
    D = P.design
    P.meta["name"] = "Untitled"
    W, H = P.W, P.H
    x0, y0, x1, y1 = D.safe()

    s = P.scene("shot", dur=P.bar(__BARS__), energy=0.5)
    cam = s.camera

    # light: one key light on the ground, travelling with the story
    key = s.add(KeyLight(radius=max(W, H) * 0.7, color_="#FFFFFF", intensity=0.25, squash=0.7,
                         pos=(W * 0.2, H * 0.1), name="key light"))
    key.position.key(0, (W * 0.2, H * 0.1)).key(s.dur, (W * 1.6, H * 0.2), "in_out_sine")

    # idea 1 at the origin: the hero line, big
    title = s.add(Text("Title from the brief", style="display", max_width=x1 - x0, pos=(x0, H * 0.42),
                       name="hero line"))
    title.reveal(0.3, "rise", by="word")

    # the carrier: an accent bar that underlines idea 1, then stretches into idea 2
    bar = s.add(Rect(x1 - x0, 12, radius=6, fill="accent", pos=((x0 + x1) / 2, H * 0.42 + 40), name="carrier"))
    bar.grow(0.9, "x", dur=0.6, ease="out_expo")
    t2 = P.beat(6) - s.t0                     # the camera leaves for idea 2 on beat 6
    bar.move(t2, (W + x0, H * 0.5), dur=0.7, ease="in_out_expo")
    cam.glide(0, t2, dx=-30, zoom=1.04)       # read idea 1 while the frame keeps moving
    cam.travel(t2, to=(W * 1.5, H / 2), dur=0.7)

    # idea 2, one frame width to the right, already alive when the camera lands
    # ...

    # space (motion.md 2b): stage the ideas at three depths and film them in setups, e.g.
    #   s.add(Floor(H * 0.8)); s.haze("bg", 700, 7000); cam.dof(aperture=9, focus=0)
    #   dust(s, (W / 2, H / 3, 1200)); cam.shot(t, title, "close", angle="low"); cam.dolly(t, t + 2, 400)
    #   head-on only: within 15 deg, no extruded type, no cards turned in space (QA oblique)
    # full example: tests/space_demo/video.py

    P.keyframes = [(1.2, "idea 1: hero line"), (s.t0 + t2 + 1.0, "idea 2")]
    return P
