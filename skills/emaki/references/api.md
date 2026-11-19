# Engine API (for writing video.py)

`from engine import *` gives everything below. `build()` must return a `Project`.
Units: final-resolution pixels (1080 on the short side). Times: seconds from the scene start
(overlay layers use project time). Colors: palette role (`"accent"`), `"role@0.5"` (alpha),
`"#RRGGBB"`, or RGB tuples.

## Contents
1. Project, scenes, time grid
2. Layers: common transform + animation helpers
3. Text (reveals, typewriter, scramble, highlight, counters, dynamic text, text on path)
4. Shapes, fills, masks, blend modes
5. Groups, repeaters, grids, layout
6. Data: CSV/JSON, Counter, BarChart, LineChart, Donut
7. UI kit (product interfaces as vectors)
8. Camera and parallax
8b. Space: the set (floor, haze, beams, dust, reflection) and camera setups
9. Transitions
10. Effects (per layer and global), motion blur
10b. Light, material, focus
11. Sound events
12. Particles, images, SVG
13. Writing a new primitive (engine_ext)

---

## 1. Project, scenes, time grid

```python
P = Project("design.yaml")             # size/fps from design.format (aspect, fps); duration = end of last scene
D = P.design                           # palette, type scale, grid, motion, fx, sound
W, H = P.W, P.H
x0, y0, x1, y1 = D.safe()              # 8% safe area (QA FAIL outside); D.safe(strict=True) adds platform UI zones
s = P.scene("hook", dur=3.2, transition=None, energy=0.4, notes="", bg="bg")   # bg: role/hex or a Background layer
P.scene("next", dur=4.0, transition=Push(0.6, "left"))   # starts at prev.end - transition.dur (overlap)
P.add_overlay(layer)                   # above all scenes, PROJECT time (HUD, logo bug, progress bar)
P.keyframes = [(abs_t, "caption"), ...]   # storyboard contact sheet moments
P.meta["name"] = "Client promo"
```
Beat grid (from `sound.bpm`, `sound.beat_offset`): `P.beat(n)`, `P.bar(n)` (absolute seconds),
`P.snap(t, div=2)` (nearest 8th), `s.beat(n)` (scene-local). Make scene durations whole bars
(`dur=P.bar(2)`) and put accents on beats; QA fails accents off the grid by more than one frame.
`scene.energy` (0..1) drives the music arrangement for that scene.

Design helpers: `D.size("display")` px for a type role, `D.col(i, span)` -> (x, width) on the grid,
`D.x(i)`, `D.rows(n)`, `D.margin`, `D.gutter`, `D.radius`, `D.stroke`, `D.center`,
`D.motion.durations["medium"]`, `D.motion.easing["enter"]`, `D.motion.stagger`.

## 2. Layers: transform + helpers

Every layer accepts: `name, pos=(x,y), anchor=(ax,ay) or "tl|tc|tr|cl|center|cr|bl|bc|br", scale,
rotation (deg), opacity (0..1), depth (px, camera parallax), blend ("normal", "multiply", "screen",
"overlay", "add", "difference", ...), start, end (visibility, scene s), fx=[...], clip=(x,y,w,h)`.
Transform order is After Effects': translate(pos) * rotate * scale * translate(-anchor).

Animatable properties are `Prop`s: `layer.position`, `.scale` (sx, sy), `.rotation`, `.opacity`,
`.anchor`, `.depth`, and type-specific ones (`rect.size`, `shape.trim_end`, ...).
```python
p.key(t, value, ease=None)     # ease shapes the segment ARRIVING at this key
p.wiggle(freq=2, amp=10)       # additive smooth noise (AE: wiggle)
p.drive(lambda t: ..., ae_expr=None)   # procedural; AE uses ae_expr or bakes
```
Easing specs: `linear`, `hold`, `in_/out_/in_out_` + `sine|quad|cubic|quart|quint|expo|circ|back`,
`back_out(2.2)`, `bezier(.2,.8,.2,1)`, `spring`, `spring:gentle|wobbly|stiff|slow|snappy`,
`spring(170,26)`, `elastic_out(1,.3)`, `bounce_out`, `steps(4)`. Defaults come from
`design.motion.easing` (enter / exit / move / emphasis / transition). Animation is never linear by
default.

Helpers (return the layer, chainable; dur/ease default from design.motion):
`fade_in(t)`, `fade_out(t)`, `slide_in(t, "up|down|left|right", dist)`, `slide_out(...)`,
`move_from(t, (dx,dy))`, `move_to(t, (dx,dy))`, `move(t, (x,y))`, `pop_in(t)`, `pop_out(t)`,
`scale_from(t, s0)`, `scale_to(t, s1)`, `rotate_from(t, deg)`, `blur_in(t, sigma)`,
`enter(t, "rise|drop|left|right|fade|pop|blur|scale")`, `exit(t, "fade|rise|drop|left|right|pop")`,
`show(start, end)`, `add_fx(...)`, `matte(layer, "alpha|alpha_inv|luma|luma_inv")`,
`tween("opacity", t, dur, a, b, ease)`.
`allow("static" | "offframe" | "overlap", why="...")` declares an intentional exception QA accepts
and lists: an element that enters and sits on purpose, copy cropped by the frame on purpose,
copy that overprints or sits under other layers on purpose. `why` is required.

## 3. Text

```python
t = s.add(Text("Кожна *розмова*\nпочинається з нуля.", style="display", pos=(x0, 600),
               max_width=x1 - x0, align="left", anchor="tl", role="copy", src="brief"))
```
- `style` = type role from design.yaml (family, weight, size/step, tracking, line_height, case,
  features). Override per layer: `size, color, font, weight, italic, tracking, line_height, case`.
- Markup: `*accent*`, `**bold**`, `[word](role_or_hex)`, `\n`. Markup is stripped for QA.
- `anchor` uses the optical box: top = cap height of line 1, bottom = last baseline.
- `t.width`, `t.height`, `t.plain`, `t.L.lines` for layout math. Words wider than `max_width`
  fail QA (overflow). Missing glyphs fail QA.
- `role="copy"` gets reading-time, contrast, safe-area and occlusion checks; `role="decor"` (HUD,
  timecodes, watermarks) only safe-area of the frame. `src="brief"` must match brief.yaml texts
  verbatim; anything you write yourself is `src="invented"` and is listed as [DEMO COPY].

Per-unit reveals (unit = `by="char"|"word"|"line"`, `order="forward|reverse|center|edges|random"`):
```python
t.reveal(0.3, "rise", by="word", dur=None, stagger=None, ease=None, dist=40)
# modes: fade | rise | drop | left | right | scale | pop (s0=0) | blur (sigma) | rotate (deg)
#        | spread (k) | mask (lines slide up from under a clip, depth)
t.unreveal(2.6, "fade", by="line")        # same modes, reversed
t.typewriter(0.5, cps=22, scramble=3, cursor=True, cursor_until=3.0, cursor_shape="block|bar|underscore", sound="type")
t.scramble(0.2, dur=0.8, order="random")  # chars cycle random glyphs and settle
t.draw_outline(0.2, dur=1.2)              # outlines draw on, then fill (AE: baked)
t.highlight((2, 3), 1.0, dur=0.45, color="accent")   # marker behind words 2..3
t.animate_color(1.5, "accent")
```
Other text layers: `Counter(a, b, t0, dur, ease, decimals, sep, dec, prefix, suffix, style, sound="tick")` (sep/dec default to the project language: "1,284.5" in English, "1 284,5" otherwise)
(tabular figures on); `DynamicText(fn, sample, style=..., ae_expr=None)` for clocks/timecodes;
`TextOnPath("text", "M 0 0 Q ...", style, offset=Prop)`.

## 4. Shapes, fills, masks

Shapes are centred on their position like AE shape layers (except PathShape: raw coords).
```python
Rect(w, h, radius=None, fill="accent", stroke=None, stroke_width=None, cap="round", join="round", dash=(on, off))
Ellipse(w, h=None, ...); Polygon(sides, radius); Star(points, outer, inner); Arc(radius, start, sweep)  # 0deg = 12 o'clock
Line(p0, p1, stroke="text"); PathShape("M10 10 C ...", fill=None, stroke="accent")  # or points list + smooth=0..1
Morph([path_a, path_b, ...]).morph_to(t, index, dur, ease)
rect.grow(t, axis="x", origin="start")         # bar growth
shape.draw_on(t, dur) / shape.draw_off(t)      # stroke trim (trim_start/trim_end/trim_offset Props)
```
Fills: colour spec, `Linear(p0, p1, [(0, "accent"), (1, "bg")])`, `Radial(center, r, stops)`,
`Conic(center, stops, angle)`, `Noise(freq, octaves, c0, c1, drift)`, `Pattern("dots|lines|grid|checker|diagonal", spacing, size, c, move)`.
Full-frame: `Background(fill)` (use as `scene(bg=Background(...))` or add as first layer).
Masks: `layer.clip = Prop((x, y, w, h))` (animatable rect clip in local coords);
`target.matte(matte_layer, "alpha")` - the matte is drawn only as a matte (AE track matte).

## 5. Groups, repeaters, layout

`Group(*children, pos, offset=0.0)` - children in group-local coords; `offset` delays all child
animation (AE precomp). `g.add(...)`, `g.walk()`.
`Repeater(factory(i) -> Layer, count, offset=(dx,dy), rotate, scale, opacity_end, stagger)`.
`Grid(rows, cols, (cw, ch), factory(i, j, k, delay, (x, y)) -> Layer, gap, order="row|col|diagonal|center|edges|random", step)`.
`vstack([layers], x, y, gap, align)` / `hstack(...)` set positions from measured bounds.

## 6. Data

```python
rows = load_csv("data/metrics.csv")        # numbers converted; ; , or tab delimiters
data = [(r["month"], r["revenue"]) for r in rows]
s.add(BarChart(data, w=800, h=520, t0=0.4, pos=(x0, 300), highlight=[len(data) - 1], suffix=" %",
               orientation="v", values=True, labels=True, stagger=None, ease=None))
s.add(LineChart([v for _, v in data], 800, 420, t0=0.3, labels=[m for m, _ in data], area=True, tip=True, dots=False))
s.add(Donut([40, 30, 30], radius=180, thickness=44, t0=0.5, colors=["accent", "accent_2", "muted"]))
s.add(Counter(0, 1284500, t0=0.5, dur=1.6, style="display", suffix=" ₴", sound="tick"))
nice_max(v); fmt_number(v, decimals=0, sep=" ", dec=",")
```
Charts are groups of plain shapes/text, so they export natively to AE. Always show the source
of the numbers on screen (caption) when the brief provides it.

## 7. UI kit

`Card(w, h, fill="surface", radius, shadow="soft")` (children: top-left origin; `shadow="soft"` =
SoftShadow, `True` = the old single drop shadow, `False` = none),
`Window(w, h, url)` (put content into `.body`), `Phone(w, h)` (content into `.screen`),
`Button(label).press(t)`, `Chip(label)`, `Toggle(w).switch(t)`, `Input(w, placeholder).type(t, "text")`,
`Toast(title, body, w, icon)`, `Avatar("AB")`, `Icon(name, size, color)` with names in `ICONS`
(check, plus, arrow_right, play, search, bell, heart, star, user, lock, bolt, chart, calendar, chat,
mail, home, gear, pin, globe, sparkle, ...), `Cursor().move(t, (x, y)).click(t)`.
Take sizes, radii and colours from the brand source; anything invented is a
[DESIGN DECISION - not in source docs].

## 8. Camera

Each scene has `s.camera` with `pos` (x, y), `zoom`, `rotation`, `rx`, `ry` Props. Move it like an
operator (motion.md section 2): `glide(t0, t1, dx, dy, zoom, rotate, ease)` one-way move inside a
shot; `travel(t, to=(x, y), zoom, dur, ease)` to another place on a big canvas; `follow(layer_or_fn,
t0, t1, lag, offset, axes)` smooth tracking (baked to keys); `frame_on(t, (x0, y0, x1, y1), margin)`
re-frame to a box. Effects for a specific beat only: `punch(t)`, `snap(t, dx, dy)`, `shake(t0, t1)`.
`drift()` is a very slow float (period clamped to >= 16 s). QA `camera` warns on wobble.
Give layers `depth` (px; + is farther) for parallax: scale = focal * lens / (focal/zoom + depth), the
same projection as an AE one-node camera. With a camera, layers draw back-to-front by depth
(backgrounds first, then floors, then far to near). A layer partly behind the lens is clipped at
the near plane, not dropped, so the camera can fly past or through it.
Cinematography (motion.md 2b): `zoom` is the camera distance (a change of zoom is a dolly with
real parallax), `lens` the focal-length multiplier at that distance, `rx` the tilt (+ = high
angle, the camera above looking down), `ry` the arc (+ = the camera swings to the subject's
right), `rotation` the roll. The camera orbits a point on the stage plane (depth 0). Keep `rx`
and `ry` within 15 degrees (head-on): flat layers seen from the side read as PowerPoint 3D and
QA `oblique` fails them.
```python
cam = s.camera
cam.shot(0.0, box_or_layer, "wide", angle="high")                  # a setup: size, angle, side (dur=0: cut)
cam.shot(4.4, hero, "close", angle="low", side="slight")           # hard cut on the beat
cam.shot(6.0, hero, "medium", dur=0.8, lens=1.0)                   # the same as an eased move; reset the lens
cam.cut(t, pos=(x, y), zoom=1.4, rx=8, ry=-6, rotation=0, lens=1.0)     # absolute setup values
cam.dolly(t0, t1, 600)            # move 600 px closer (negative: pull back)
cam.orbit(t0, t1, ry=10)          # a small arc (<= 12 deg): the planes slide against each other
cam.crane(t0, t1, dy=-200, tilt=8)    # rise and look down a little; dy > 0, tilt < 0: drop lower
cam.dolly_zoom(t0, t1, k=1.6)     # vertigo: the subject keeps its size, the set stretches
cam.project(t, x, y, z)           # world point -> (screen x, screen y, distance)
layer.face_camera()               # billboard: keeps facing the camera
```
Sizes: extreme_wide, wide, full, medium, close, extreme_close (or a number: how much of the
frame the subject fills; a layer subject's depth is taken into account). Angles: eye, high (10),
low (-8). Sides: front, slight (8), "-slight". Cuts are recorded in `cam.cuts`: motion blur
never blends two setups, QA counts them as hits. Write the camera in time order: a cut ends the
move that runs through it.

## 8b. Space: the set

```python
FY = 700                                                     # world height of the floor (y grows down)
s.add(Background(Radial((W/2, H*0.38), W*0.9, [(0, "#141821"), (1, "bg")])))
s.haze("bg", near=700, far=7000, amount=0.85)                # far layers fade into the air
fl = s.add(Floor(FY, near="surface", bays=520))              # default: 20000 px, near edge behind the camera
fl.pool(560, 900, 900, "accent", 0.4, squash=0.8)            # pool of light at world (x, z); returns a Prop
s.add(LightBeam(length=FY + 420, width=1100, color_="accent", intensity=0.18, pos=(560, -420), depth=900))
hero = s.add(Text("ГЛИБИНА", style="display", size=430, anchor="bc", pos=(W/2, FY)))   # stands on the floor
s.add(Reflection(hero, FY, opacity=0.2, blur=5))             # the hero only
dust(s, (W/2, 360, 1200), size=(4200, 1500, 5200), n=110)   # motes behind and in front of the subject
cam.dof(aperture=9, focus=0)                                 # dust and the foreground open into bokeh
```
- `Floor(y, z=3000, size=(20000, 20000), near, far=None, horizon, lines, bays, line_color)`:
  ground plane at world height y; fades out towards the horizon and dissolves at the projected
  horizon line (`soft_horizon`), so it never ends on a hard edge. Drawn after the backgrounds,
  clipped at the lens. `pool(x, z, r, color_, intensity, squash)`.
- `s.haze(color_, near, far, amount)`: atmospheric perspective by layer depth.
- `LightBeam(length, width, top, color_, intensity, softness, source)`: a lamp at `pos`, the beam
  down its local y.
- `Reflection(layer, floor_y, opacity, blur, fade)`: a top-level layer mirrored in the floor.
- `Motes(center, size, n, radius, color_, alpha, drift, twinkle)` / `dust(s, ...)`: dust in screen
  space through the camera, each mote at its own depth (bokeh with dof).
- Draw order in a camera scene: the backgrounds added first, then floors, then far to near,
  then `on_top` layers (`Flash` sets it).
The full example: `tests/space_demo/video.py`.

## 9. Transitions (scene-to-scene, `transition=` on the incoming scene)

`Cut()`, `Fade(dur)`, `Dip(dur, color_)`, `Push(dur, direction)`, `Slide(dur, direction, parallax)`,
`Wipe(dur, direction, softness)`, `Iris(dur, center)`, `Zoom(dur, amount)`, `BlurDissolve(dur, sigma)`,
`ShapeWipe(dur, color_, angle, direction)`, `Glitch(dur, amount)`. All take `ease=` and `sound=`
(default whoosh/swish/glitch where it fits; `sound=None` to mute). Glitch pulses the global glitch
fx track.

## 10. Effects

Per layer (native in AE): `Blur(sigma)`, `DropShadow(dx, dy, sigma, color, opacity)`,
`Glow(sigma, color, strength)`; their params are Props (animatable). Units: these four (and
`Smear`, the blur transitions, text `blur` reveals) take legacy half-px values: the result at the
final size is 2x the number (`Blur(10)` = 20 px). Since 2026-10-09 every render size shows the
same picture (before that the preview showed these blurs 4x weaker than the final).
`SoftShadow(elev, color, opacity)`: contact + ambient shadow of a lifted object, real px; animate
`elev` for lift and land. `layer.sheen(t, dur, angle, width, strength, color_)`: a band of light
sweeps across the layer's own pixels (one per object, on its key moment).
`layer.on_twos(fps=12)`: the layer animates at 12 fps (hand-made accent; one element, not the film).
Global post fx come from `design.yaml fx.enabled` and run after downscale:
`grade` (contrast, saturation, lift, gamma, gain, temperature), `bloom` (threshold, intensity, radius),
`chroma` (amount px), `glitch` (split, slices, region, track_only), `vignette` (strength, softness),
`scanlines` (period px@1080, strength), `grain` (amount, size, luma_weighted).
Time-varying intensity: `P.fx_track("glitch").key(t, 1.0)` or `P.pulse("glitch", t, amount)`.
Motion blur: automatic for fast camera moves (`P.auto_blur`, on by default: 3-10 sub-frames only
on frames where the camera travels or orbits, nothing extra on held shots, never across a cut).
Fast moves of layers without a camera move (a logo flying in, a group scaling 6x in 0.5 s):
`P.blur_window(t0, t1, samples=12)` in project seconds renders real motion blur there (6-8
samples for a short move, 12-16 for a big pull-back; keep the window clear of hard colour
flips). A window renders samples x 4 (full supersampling), so keep windows short. QA `easing`
stops warning about strobing inside it. Sub-frames render without
supersampling (`P.mb_ss = 1`): their average already smooths the moving edges, so a blurred frame
costs about n x 1 instead of n x 4. Forced for a scene: `scene.motion_blur = {"samples": 8,
"shutter": 180}` (or `P.motion_blur`), costs samples x render time. Per-layer streak without
sub-frames: `layer.smear(k)`.

## 10b. Light, material, focus (art_direction.md 5b)

```python
kl = s.add(KeyLight(radius=1100, color_="#9DB8FF", intensity=0.3, squash=0.7, pos=(300, 160)))
kl.position.key(0, (300, 160)).key(6.0, (1500, 260), "in_out_sine")   # the light may travel
# blend: "screen" (dark grounds, default) | "soft_light" (light grounds) | "multiply" + dark colour = shadow pool
g = s.add(Glass(760, 420, radius=36, blur=26, tint="#FFFFFF", tint_alpha=0.1, rim=0.55, pos=(x, y)))
g.amount.key(0.3, 0.0).key(1.2, 1.0, "out_cubic")       # appear via amount, not opacity
card.bg.fx.append(SoftShadow(elev=36, opacity=0.4))     # Card(..., shadow=False) + SoftShadow
card.sheen(2.0, 0.9, angle=25, strength=0.6)
s.camera.dof(aperture=16, focus=0)                      # blur = 16 px per 1000 px of depth from focus
s.camera.rack_focus(3.4, 600, 0.7)                      # pull focus to depth 600
```
All values in real px at the final size. `Glass` blurs what was drawn before it in the same
layer: keep it at the top level of the scene or in groups without opacity, blend, mask or fx.
Depth of field needs layers with `depth` (the 3D path); copy sits on the focus plane while it is
read. Cost: a blurred layer costs its own area, not the frame (bounded layers), so DOF on 5-10
layers is cheap.

## 11. Sound events

```python
P.sfx(t_abs, "whoosh"); s.sfx(t_local, "impact", accent=True)    # accents must sit on the beat grid
```
Voice-over and music track come from design.yaml (`sound.voice`, `sound.track`, see sound.md).
Word times: `json.load(open(root + "/data/words.json"))` after `mv.py voice <dir>` (the user's
recording) or `mv.py tts <dir>` (generated voice: each word also has `phrase`, the phrase number;
phrase times are in `data/voice_phrases.json`), e.g.
`KineticWords([w["word"] for w in W], [w["t0"] - s.t0 for w in W], ...)`.
Kinds: whoosh, swish, riser (ends at t), downlifter, impact/hit, sub_hit, click, type, tick, blip,
pop, chime/notify, glitch, shimmer, beep, crash, kick. Params: `gain_db`, `pan`, kind-specific
(`dur`, `freq`, `size`). Layers emit events automatically: `typewriter(sound="type")`,
`Counter(sound="tick")`, `Cursor.click()`, transitions. Events are snapped to frames.

## 12. Particles, images, SVG

`Particles(emitter="point|line|rect|circle|ring", at, size_of_emitter, rate, bursts=[(t, n)], life,
speed, direction, spread, gravity, drag, size, size_end, colors, opacity=(1, 0), shape="circle|square|line|glyph:★",
turbulence, spin, seed)` - stateless, deterministic. AE: baked.
`Image("assets/logo.png", w, h, fit="contain|cover|stretch", radius)`, `Svg("assets/logo.svg", w)`.
Only the user's files from assets/ and fonts/.

## 12b. Dynamics primitives (see motion.md for when to use them)

```python
s.camera.glide(0, s.dur, dx=-40, zoom=1.06)                # held shot: one-way push/pan
s.camera.travel(t, to=(x, y), zoom=1.0, dur=0.45)          # fly to the next idea on the canvas
s.camera.follow(dot, t0, t1, lag=0.18)                     # track a moving layer or fn(t)->(x, y)
s.camera.frame_on(t, (x0, y0, x1, y1), margin=0.12)        # re-frame to a group
s.camera.push(t0, t1, 1.08); s.camera.punch(t, 0.05)       # punch/snap/shake: one beat, by brief
s.camera.rx / .ry                                          # orbit tilt Props (deg)
layer = Card(..., rx=0, ry=-20)                            # any layer can tilt in 3D (true perspective)
layer.tilt_in(t, ry=-60); layer.tilt_out(t, ry=60); layer.punch(t, 0.06); layer.echo(4, 0.03, 0.5)
layer.smear(0.01)
Text(..., fit=x1 - x0)                                     # shrink a one-liner to fit a width
txt.write_on(t, cps=10, head=True, head_color="accent", glow=1.0)   # glow=0 -> ink pen
Comet(path, t0, dur, ease, tail=0.22, head=9, stroke="accent", glow=1.0, keep=True)
GridPlane(w, h, step, stroke, scroll=(0, 140), fade=0.4, pos=(W/2, H*0.8), rx=74)   # floor
Wire3D("icosa"|"cube"|"octa"|"tetra", size, spin=(20, 35, 0), stroke)
Waveform(w, h, bars=64, mode="mirror"|"bars"|"line", stroke)      # reads out/audio/mix.wav
KineticWords(words, times, style="display", colors=[..], flashes=[..], mode="replace"|"stack",
             enter="pop"|"rise"|"mask", hold_zoom=0.06)           # group at (0, 0), scene coords
Flash(t, color_, dur=0.16)                                         # full-frame hit layer
transitions: Whip(dur, direction, blur, rotate=0, zoom=0), FlashCut(dur, color_), ScaleThrough(dur, amount)
```
With a camera active (glide, travel, follow, push, tilt, or any layer with depth/rx/ry), top-level layers are
projected through the camera and drawn far-to-near. Children of a Group stay in their parent's
plane (like a non-collapsed AE precomp).

## 13. New primitive (engine_ext)

When the brief needs something the engine lacks, write `<project>/engine_ext/<name>.py`; mv.py
imports it before video.py. Same interface as built-ins:
```python
from engine import Layer, Prop, color, skia
class Ribbon(Layer):
    kind = "ribbon"
    exportable = False          # True only if ae/export.py knows how to rebuild it natively
    def __init__(self, length, **kw):
        super().__init__(**kw); self.length = Prop(length, "length")
    def local_bounds(self, t):  # (l, t, r, b) in local coords, for QA and mattes
        return (0, -20, self.length.at(t), 20)
    def render(self, canvas, t, ctx):   # skia canvas in local coords; ctx.px = device px per unit
        ...
```
Then `from ribbon import Ribbon` in video.py (engine_ext is on sys.path). `render()` may be recorded
into a picture and replayed inside a layer sized to its ink: draw relative to the canvas you get,
never read `canvas.getTotalMatrix()` for absolute decisions (use `ctx.px`), and return honest
`local_bounds`. Non-exportable layers are
baked to ProRes 4444 for AE. A post fx: add a function `(img, params, amount, ctx) -> img` to
`engine.fx.post.FX` and its name to `ORDER` from the extension module.
