# Motion: the grammar of dynamics

A modern motion piece is alive in every frame, and every movement has a reason. The look
(palette, type, texture) and the dynamics (rhythm, camera, transitions, how information arrives)
are separate decisions: a light explainer and a neon tech reel share the grammar at different
tempos. Two failures to avoid, both seen in our own early tests:
- the slideshow: elements arrive, then stand still; the video is cut into short scenes joined by
  fades, pushes and slides, so every scene reads as a new slide;
- the junior reel: busy but cheap. The camera wobbles back and forth,
  every small event gets a sound, the music is a dated loop, nothing is designed as a finished
  frame. Movement without taste.

What the references do instead. Four reference reels were analysed frame by frame while the
engine was built: r01 neon tech, r02 editorial collage, r03 clean explainer, r04 dark gradient
light. Their frames are not shipped; the numbers and r-ids below point to them.
- every frame is a finished layout: grid, margins, one accent, small print at the edges;
- each idea is ONE transformation of the previous shape (a dot becomes a ring, the ring a star,
  the star a card); nothing just pops in from nowhere;
- the camera behaves like an operator: slow one-way push inside a shot, fast eased travel with
  real motion blur between ideas, follows the thing that moves; it never shakes;
- 3 of 4 references are narrated: the words on screen are the spoken words, timed to the voice;
  the music sits under the voice, sound effects only on transitions and key moments.

## 00. One shot: how to build it with the engine

The scene is the engine's unit, so the easiest video to write is a list of short scenes joined by
transitions. That is exactly the slideshow. Build the video the other way round:

1. **One scene for the whole video.** `s = P.scene("shot", dur=P.bar(n))`. Add a second scene only
   for a change of world (light to dark, the end card), joined by `Whip`, `ScaleThrough` or
   `FlashCut`. Not by `Fade`, `Dip`, `Push`, `Slide`, `Wipe` or `Iris`.
2. **A big canvas.** Lay the ideas out in scene coordinates far beyond 0..W, in the order the
   camera will visit them. The next idea is already alive when the camera arrives.
3. **A carrier layer.** One layer (a dot, a line, a card, a cursor) runs through the scene and
   becomes each next idea: `Morph`, `Rect.grow`, `move`, `Comet` drawing the next outline. The
   camera `follow`s it or `travel`s along with it.
4. **Camera paths, and cuts between setups of the same world.** `travel` between ideas, `glide`
   while reading, `frame_on` when a group grows, `follow` on a moving carrier. A hard cut to a new
   camera setup (`camera.shot`, section 2b) is allowed on a beat: the world stays, only the
   camera changes. A cut to an empty frame or to a new layout is still the slideshow.
5. **UI big and partial.** A `Card` or `Window` is larger than the frame; the camera
   `frame_on`s two or three fields at a time and follows the `Cursor`.
6. **Visibility windows.** Give every layer `start`/`end` around the moments it can be seen, so
   layers far from the camera are not drawn on every frame.
7. **A space, not a plane, filmed head-on.** Stage the layers at three depths, give the world a
   floor, air and light, and film it with changing sizes, dolly and cuts (section 2b). One plane
   with a camera sliding over it reads as a screen recording; the same planes seen from the side
   read as PowerPoint 3D.

## 0. Choreography: the rules QA enforces

These rules are binary and measured from the scene graph (`qa.py check_choreography`,
`mv.py timeline` draws the map).

What you will do by default, and must not:
- every element enters (rise or fade) and then sits; the camera glides over finished layouts;
- the next idea is a new set of elements that appear where the camera lands;
- one curve (`out_expo`) and one speed (0.4-0.6 s) for everything;
- strict sequence: A finishes, then B starts ("after previous" in PowerPoint).

The rules:
1. **Action chains.** Every lead element does at least two things: enter -> transform or react ->
   hand off or exit. Write the chain per element in the storyboard. QA FAILs when 75 % of the
   elements only enter and sit (WARN at 50 %). Labels that must sit: `layer.allow("static",
   why=...)`, never more than a third of the elements.
2. **Hand-offs between ideas.** Each new idea grows out of the previous one: a shape morphs into
   the next, a line becomes the next outline, an element flies to its new role, the lead dot the
   camera follows turns into the next thing. New elements appearing at the camera's landing spot
   are the slideshow signature.
3. **No dead holds.** Something on screen animates at least every `dynamics.max_hold` seconds
   (calm 1.4, medium 0.9, fast 0.6); a camera glide or zoom alone does not count, a cut to a new
   setup, an arc, a crane or a dolly zoom does (they change the perspective of everything in
   frame). The closing hold may run to 1.5 s. QA WARNs above the target and FAILs above twice the target.
4. **Overlap, not sequence.** The next action starts while the previous one is still moving
   (30-60 % into it). Children trail their parent by 0.05-0.15 s. Total stagger of a group stays
   under 0.5 s whatever the count.
5. **Entrances by role.** Lead, support and detail enter differently; no more than three
   elements of a scene share one entrance (QA WARNs at four). Starts at scale >= 0.6, never 0.
6. **Speed contrast.** Fast hits 0.15-0.3 s, standard 0.4-0.6 s, slow builds 0.8-1.5 s. The
   slowest action is at least 3x the fastest (QA WARNs under 2.5x).
7. **Curves by job.** Enter `out_*`, exit `in_*`, moves between two rests `in_out_*`. Exits take
   65-75 % of the entrance time. One curve on at most 60 % of the moves (QA WARNs above).
8. **Exits with intent.** Things leave by doing something: fly to the next position, collapse
   into a dot that becomes the next lead, get pushed by the incoming element, wipe off. Leaving
   them behind while the camera travels away is allowed for the background only.
9. **Anticipation and settle** (energetic and playful looks): a 10-20 % counter-move 0.1-0.2 s
   before a big move; a small overshoot (5-15 %) on landing. Premium and calm looks: no overshoot.

Sources: HyperFrames motion principles (ease and speed variety, exits faster than entrances,
total stagger under 0.5 s), LottieFiles motion-design (layers, stagger totals, anticipation
10-20 %), design-motion-principles (uniform entrances flagged at four, never scale from 0).

## Contents
00. One shot: how to build it with the engine
0. Choreography: the rules QA enforces
1. Dynamics targets (design.yaml `dynamics`)
2. Camera language
2b. Space and cinematography: depth, the set, shots, angles, cuts
3. The seven moves that keep a frame alive
4. Technique catalogue -> engine calls
5. Tempo: calm is not static
6. Structure, reading time and hooks
6b. A first-time viewer must understand it: voice, text by pace, where to look
7. Easing character
8. Sound and picture
9. Data and explanation
10. Checklist before preview

## 1. Dynamics targets

Write them in design.yaml (QA measures the rendered video against them):
```yaml
dynamics:
  hit_interval: 0.75   # median seconds between visual hits (cut, slam, flash, travel, big move)
  max_still: 0.8       # longest stretch with no movement, seconds
  static_max: 0.06     # share of frames with no movement
  max_hold: 0.6        # longest stretch where no element animates (camera glide alone does not count)
  camera: {mode: glide, push: 1.06, travel: 0.45}   # see section 2
  grammar: [...]       # the 4-6 moves this video is built from
```
Defaults by tempo when absent: calm 1.6 s / 2.0 s / 25% / hold 1.4 s; medium 1.0 / 1.2 / 12% /
0.9 s; fast 0.7 / 0.8 / 6% / 0.6 s.
From a video reference, take the numbers from `mv.py analyze-ref` and loosen them for calmer
briefs. Reference values: r01 neon tech 1.2% frozen, longest 1.3 s; r02 editorial 0%; r03 clean
explainer 5%, 0.5 s; r04 dark gradient 3%, 0.9 s.
How QA measures (analyze.py, 15 fps, 160 px): a frame is frozen when under 0.05% of its pixels
change; only freezes of 0.33 s or more count. Frozen share and longest freeze FAIL when far off
target; big hits only WARN. Do not game it: the contact-sheet review judges whether the motion
means something.

## 2. Camera language

The camera is an operator, not a vibrator. Four moves, in this order of preference:

| move | call | when |
|---|---|---|
| glide | `s.camera.glide(t0, t1, dx, dy, zoom=1.06)` | inside a held shot: slow one-way push or pan over the whole shot (r02, r03) |
| travel | `s.camera.travel(t, to=(x, y), zoom, dur=0.35-0.6, ease="in_out_expo")` | between ideas laid out on one big canvas; fast moves get real motion blur automatically (r03, r04) |
| follow | `s.camera.follow(layer_or_fn, t0, t1, lag=0.18)` | track a travelling dot, a caret, a line tip (r03 typewriter, r04 dot dive) |
| frame_on | `s.camera.frame_on(t, box, margin=0.12)` | re-frame as a group grows (r03 hexagon badges) |
| setups and moves in depth | `dolly`, `crane`, small `orbit`, `dolly_zoom`, `shot`, `cut` | section 2b: depth, sizes, cuts between setups, head-on only |

Rules:
- Never move the camera back and forth inside a shot. `drift()` exists only as a very slow float
  (period >= 16 s, clamped) for long holds; QA warns when the camera turns around more than once
  per 4 s.
- `punch`, `snap`, `shake` are effects for a specific beat the brief asks for (an impact, a drop),
  not a default. Frequent punches read as shake (QA warns).
- Big moves go through the camera, not through every layer: lay ideas out on a canvas (scene
  coordinates can go far outside 0..W) and travel between them. The next idea is already alive
  when the camera arrives.
- Ease long and soft for premium looks (in_out_sine / in_out_cubic, 0.6-1.0 s), short and steep
  for energetic ones (in_out_expo, 0.3-0.45 s). Never linear camera moves under 2 s.
- Rendering: `P.auto_blur` (on by default) adds 3-10 sub-frames only where the camera moves fast,
  so travels look shot, not slid. Per-layer streaks: `.smear()`.
- Focus is part of the camera: with layers at several depths, `dof()` keeps the reading plane
  sharp and the rest soft, and `rack_focus` moves attention without moving the frame (a calm
  alternative to a travel).

## 2b. Space and cinematography (2.5D, head-on)

User feedback on a product film: "it's all flat: no depth, no cinema, no camera, no angles; no
wow, it looks good but ordinary". In motion design terms: a single-plane composition in screen
space, a camera that only pans and zooms, one shot size. Presentational, not cinematic. Then the
first 3D test the same day: "the opening looks fine, but from the side it already looks like a
PowerPoint presentation". Both lessons together:

**First: does the concept have a world?** A product in a place, a story in a setting, a screen
in a room: then build the set below. A film carried by type (one huge word per beat, colour
fields flipping) does not need a set: its depth
is scale contrast (a small word over a huge one), crop by the frame edge, two layers of type at
different depths with parallax, a push into a letter, cuts on the beat. When a type-led film
does get a camera, the word stays the frame (70-90 % of the width in every key frame) and the
camera moves into it or along it, never away from it to show the space (one film's hook: the
type shrank to 45 % on a neon grid and the concept was lost; QA `type_scale`).

**The engine is 2.5D. Film it head-on.** Layers are flat sheets placed at depths. Depth reads
through parallax, focus, haze, light and scale while the camera looks at them within about 15
degrees of head-on. From the side a sheet shows that it is paper, and the film turns into
PowerPoint 3D: extruded WordArt with flat sides, cards rotated in space, a photo wall on a tilted
plane, a glossy "gallery" floor under everything. A camera brought near the type bends it the
same way: the verticals converge, the letters lean ("don't bend them"). Close-ups come
through the lens: `camera.shot` keeps the camera at least 0.85 x focal away and lengthens the
lens instead; no dolly zoom on type. QA `oblique` fails any flat layer held more than 15
degrees away from the camera or bent by perspective (opposite edges more than 1.15x apart);
there is no extruded type in the engine.

**Stage in depth.** Every key frame has three planes and something that says where they stand:
- foreground, depth -600 to -1500: out of focus, slides past as the camera moves (a pillar, a
  blurred shape, the edge of a card, near dust in bokeh);
- subject, depth 0 (the stage plane): sharp, where the copy is read;
- background, depth 800 to 3000: far cards, old prices, a monolith, lamp light, the horizon;
- the set when the concept allows one: a `Floor`, `s.haze()` so far things fade into the air,
  `LightBeam` + `floor.pool()` as lamps, `dust()` in the air, a `Reflection` on a glossy floor
  (for the hero only, not under every element). One world for the whole film.

**Shots** (`camera.shot(t, subject, size, angle, side, roll)`):

| size | the subject fills | use |
|---|---|---|
| extreme_wide | ~0.2 of the frame | the world; opening, scale |
| wide | ~0.4 | establishing: where we are |
| full | ~0.7 | the subject whole, with air around |
| medium | ~1.15 (edges cropped) | reading distance |
| close | ~1.9 | detail, the hit |
| extreme_close | ~3.4 | texture, a single letter or digit |

Angles stay small: `eye` (0), `high` (+10), `low` (-8), `side` `front` or `slight` (8, or
"-slight"); a dutch `roll` of 8-15 degrees once per film at most. The drama comes from size,
depth, focus and cutting, not from turning the world.

**Moves inside a setup** (the camera never stands still in a setup):

| move | call | what it does |
|---|---|---|
| dolly in/out | `camera.dolly(t0, t1, dz)` | moves the camera: near layers grow faster than far ones (parallax). Not a zoom |
| truck / pedestal | `camera.glide(t0, t1, dx, dy)` | slides sideways or up: the planes slide against each other |
| small arc | `camera.orbit(t0, t1, ry=10)` | up to ~12 degrees: reveals parallax. Never round to the side |
| crane | `camera.crane(t0, t1, dy, tilt)` | rises or drops by a few degrees: a reveal over the foreground |
| dolly zoom | `camera.dolly_zoom(t0, t1, k=1.6)` | the subject keeps its size, the set behind stretches. Once per film, never on type or cards |
| rack focus | `camera.rack_focus(t, depth, 0.6)` | moves attention between planes without moving the frame |

**Editing: one world, several setups.** `camera.shot(..., dur=0)` (or `camera.cut`) is a hard
cut inside the scene; with `dur > 0` the same call is an eased move to the new setup.
- Cut on a beat or on action (a hit, a landing, a word), with a sound accent. Change the size by
  at least x1.4, otherwise it is a jump cut.
- 2-4 s per setup, and every setup moves (dolly, glide, crane). A static setup is a slide.
- Write the camera in time order: a cut ends the move that runs through it.
- Open with an establishing wide (or a close mystery, then the reveal); keep one hero shot for
  the payoff: a close through the lens with a slow push into the word or the product.

**Numbers.** Per 15-20 s: at least 3 setups and 2 sizes. Dolly 10-30 % of the camera distance,
arc and crane tilt up to 12 degrees, dolly zoom k 1.4-1.9 on a set without type in close-up.

**Clichés of this kit:** a grid floor running to the horizon (Tron, synthwave) and glow on every
word. Use a grid only when the story is a screen, a game, a plan or a blueprint; glow only on
what is a light. Never HUD clutter around the hero word. Depth of field 6-14 with the subject
on the focus plane; haze `near` just behind the subject, `far` at the back of the set. The floor
reaches behind the camera (default -7000) and dissolves at the horizon by itself.

**design.yaml `space`** declares the intent and QA `space` measures it on the scene graph:
```yaml
space:
  mode: 2.5d            # flat | 2.5d (layers in depth, filmed head-on with parallax)
  planes: 3             # depth planes in a typical frame (a floor counts as one)
  shot_sizes: 3         # distinct sizes over the film (x1.4 apart)
  angles: 1             # distinct camera angles; small ones only (eye, high, low)
  moves: [dolly, crane]           # dolly | truck | orbit | crane | dolly_zoom; each must happen
  set: "night yard: floor with bay lines, haze, one lamp, dust"
  why: ""
```
A declared move that never happens, too few planes, or a camera that only pans and zooms FAILs.
Without a `space` block a film that is flat in every sense WARNs. `flat` is allowed as a decision
(Swiss poster, editorial collage, a UI tutorial), with a why.

**Cost.** A frame with a set costs 2-3x a flat frame; orbits and cranes add motion-blur
sub-frames. The 8 s `tests/space_demo` renders its final in about 1-2 minutes on 4 cores.

## 3. The seven moves that keep a frame alive

1. **Operated camera.** Every held shot glides one way (push 1.04-1.08 or a small pan); ideas
   are connected by travel; moving leads are followed (section 2).
2. **Continuity of form.** The next element is made from the previous one: `Morph` a circle into
   a star, grow a card out of an icon (`Rect.grow(origin="center")`), a line that draws becomes the
   outline of the next pill. Avoid "pop in from nothing" for anything but small labels.
3. **Something always in motion.** While copy holds, a secondary element moves: a counter
   ticks, a comet draws a connector, a label types, a blurred accent ring floats, the held word
   keeps growing (`hold_zoom`). Never a fully frozen hold longer than `max_still`.
4. **Hits on the pulse.** Every 0.5-1.5 s something lands: a word, a travel, a cut, a flash, a
   panel. With a voice-over, words land on the voice; with music only, on the beat grid.
5. **Transitions are moves.** Camera travel with blur, `Whip(rotate=, zoom=)`, morph, light sweep,
   bloom to white (`FlashCut`), zoom-through (`ScaleThrough`), 3D yaw exit (`layer.tilt_out(t, ry=60)`),
   hard cut on a word. `Fade`/`Dip` only as an exception (one black frame between a light and a
   dark scene is fine).
6. **A lead element guides the eye.** A light nib, an ink pen, a cursor or a dot travels
   (`Comet`, `Text.write_on`) and the information appears where it goes. It is how a stranger
   follows the film (section 6b), not decoration.
7. **Type as graphics, with restraint.** One big word or a light/bold pair per beat, contrasted
   with tiny labels at the edges (role="decor"). One accent colour, one accent typeface (an
   italic serif inside a sans line works in light looks).

## 4. Technique catalogue -> engine calls

Your own catalogue with reference timecodes can live in your library (`motion-lib/techniques.md`).
The most used:

| technique | call |
|---|---|
| light/pen writes a word | `Text(...).write_on(t, cps=10, head=True, glow=1.0)` (glow=0: ink pen) |
| line/connector drawn by a travelling head | `Comet(path, t0, dur, keep=True, glow=..)` |
| words on the voice, ghost-then-solid | `KineticWords(words, times, enter="rise")` or `Text.reveal(t, "fade", by="word")` |
| light + bold pair | two `Text` with roles `light` and `title`, the light line 45% of the bold size |
| italic serif accent word | `[every second](accent_serif)` markup with an italic serif role |
| word slams on beats, flash frames | `KineticWords(words, beats, flashes=[...], hold_zoom=0.06)` |
| typewriter with the camera on the caret | `Text.typewriter(t, cps)` + `camera.follow(fn_caret, t0, t1)` |
| hand-drawn ellipse around a word | `Ellipse(w, h, stroke=...).draw_on(t, 0.4)` + `Glow` |
| decoding logo text | `Text.scramble(t, dur)` |
| shape to shape | `Morph([path_a, path_b]).morph_to(t, 1, dur)` |
| grow a card from an icon | `Rect(...).grow(t, "x", origin="center")` |
| whip pan / roll between ideas | `Whip(0.35, direction, rotate=25, zoom=0.15)` or `camera.travel` |
| zoom through to the next scene | `ScaleThrough(0.4)` |
| bloom to white | `Flash(t, "#FFFFFF")` / `FlashCut` |
| perspective panels and floors | `GridPlane(..., rx=70-78)`, layer `rx/ry`, `tilt_in` |
| a set to film in: floor, air, lamps, dust | `Floor`, `s.haze()`, `LightBeam`, `floor.pool()`, `dust()` (section 2b) |
| the hero on a glossy floor | `Reflection(layer, floor_y)` (the hero only) |
| new camera setup on the beat | `camera.shot(t, subject, "close", angle="low")` |
| dolly with parallax, crane reveal, vertigo | `camera.dolly`, `camera.crane`, `camera.dolly_zoom` (small angles only) |
| fast object moves without a camera move | `P.blur_window(t0, t1, samples)`: real motion blur there |
| ghost trails, speed streak | `layer.echo(...)`, `layer.smear(0.01)` |
| rotating 3D wireframe | `Wire3D(...)` (decor only with a reason; never as filler) |
| rack focus: the eye follows what turns sharp | layers with `depth` + `s.camera.dof(16)` + `s.camera.rack_focus(t, depth, 0.6)` |
| light sweep over a card, logo or hero word | `layer.sheen(t, 0.9, angle=20)` |
| a light that travels with the story | `KeyLight(...)` with keyed `position` |
| frosted panel over the content | `Glass(w, h, blur=26)` with keyed `amount` |
| lift and land of a card | `SoftShadow(elev)` with keyed `elev` + a small scale move |
| hand-made sticker or callout | `layer.on_twos(12)` on that one element |

## 5. Tempo: calm is not static

A calm, premium or light brief changes the numbers, not the principle:
- glide 1.03-1.05 per shot, travel 0.6-0.9 s with in_out_cubic;
- hits every 1.2-1.8 s, eased with `out_expo`/`in_out_quart`, no overshoot, no flashes;
- lead element = thin ink line or a soft dot (`glow=0`), connectors and underlines drawn;
- transitions: morphs, mask wipes, light sweeps, travel, `ScaleThrough` with small amount;
- still never frozen: the held headline breathes (hold zoom 2-3%), a hairline draws, a number
  ticks, a soft blob drifts.

## 6b. A first-time viewer must understand it

Viewer feedback on a product film: "it needs a voice-over, otherwise it's not clear what it's
about"; "the amount of text on screen needs calibrating, you don't have time to understand
what's going on". The builder knows the story; the viewer sees it once, on a phone, often muted.

1. **The film in one sentence** at the top of the storyboard: what a stranger must get (what it
   is, who it is from, what to do). Every beat row says what the viewer must understand there.
2. **Voice for promos and explainers.** Ask at stage 0 (`brief.voice`): the user's recording, or
   a voice file the user provides. With a voice, write the voice-over script first; the screen
   shows its key words, timed to it (`$MV voice`). Without a voice, the text carries the story
   alone: say so in the storyboard and keep `text_pace: read`.
3. **Text by pace** (`dynamics.text_pace`):
   - `read` (default): one thought per screen, up to 7 words, on screen 1 s + 0.4 s per word
     (at least 1.4 s); while it is read, the phrase itself holds still (the camera and the world
     may move slowly).
   - `kinetic`: a film built on speed: one or two words per beat,
     0.35 s each is fine, because each screen is one word. A sentence split over beats needs
     0.3 s per word in total. The key line (the offer, the brand, the call to action) still holds
     1.2 s or more.
   Mixed films declare the pace by the part that carries the message; QA `reading_time` follows it.
4. **The eye always knows where to look.** One focal point per moment. A lead element (a dot, a
   line drawing on, a cursor, the carrier itself) travels to the next thing to read, and the next
   thing appears where the eye already is: never at the other side of the frame while something
   else moves. Hard cuts land the new word where the old one was.
5. **Sound tells the story too**: sounds of the film's world on key moments (sound.md), not a
   beep on every event. A synthesized bed cannot explain anything; a voice can.
6. **The first-time viewer check** (critic.md item 18): a separate subagent sees only the preview
   frames and the sound plan, no brief, and writes what the film is about, who it is from and
   what it asks. A mismatch with `brief.goal` is a NO and goes back to the storyboard.

## 6. Structure, reading time and hooks

- Hook in the first 0.3 s: the first frame already moves and says what this is.
- Reading time follows `dynamics.text_pace` (section 6b). A kinetic phrase (one word per beat or
  per spoken word) is checked as one phrase across its words.
- One idea per beat of the continuous shot, 2-4 s each, joined by camera travel or a
  transformation of the carrier. Not one idea per scene.
- Payoff: the last 1.5-2 s may calm down (a final word, a logo, a CTA): logo from the previous
  shapes (blobs converge, a line closes into the mark), then a held, gently gliding end frame.

## 7. Easing character

| feeling | enter | move | emphasis |
|---|---|---|---|
| premium, calm | out_expo / out_quart | in_out_quart | out_quint |
| precise, technical | out_quint | in_out_cubic | out_back(1.2) |
| energetic, creator | out_expo (short) | in_out_expo | out_back(1.6) |
| playful | spring:wobbly | in_out_back | spring(260,14) |
| mechanical / retro | linear / steps(n) | hold | linear |

## 8. Sound and picture

- Decide what carries the edit: a voice-over (user's recording in assets/), a music track (user's
  licensed file in assets/), or a synthesized bed. A voice-over is what most reference reels use.
- The picture follows the pulse, not the other way round: words on the voice, big moves on beats
  or phrase ends. Do NOT put a sound on every visual event. References put a sound under 20-55%
  of their visual hits; ours had ~70% and read as force-fitted. Keep SFX for transitions, the
  hook, the payoff and one or two key moments (QA `sound` warns above 1 SFX per second).
- See `references/sound.md` for the modern palette and the spectral balance target.

## 9. Data and explanation

- Build the explanation live: the lead element draws the axis, bars rise one after another,
  the value counter ticks while the camera glides, the highlight lands on a beat.
- Diagrams: nodes appear where a `Comet` arrives; the camera travels along the connectors
  (r04 line travel) instead of showing the whole diagram at once.
- Never leave a finished chart frozen: glide, tick a secondary value, or travel to the next point.

## 10. Checklist before preview

- [ ] the video is one scene (two at most, for a change of world); ideas sit on one canvas
- [ ] `mv.py timeline` shows a second (blue) bar on every lead element and no red holds
- [ ] each idea change is a hand-off: name the element that carries over or transforms
- [ ] entrances differ by role; speeds contrast (slowest >= 3x fastest); curves by job
- [ ] every held shot glides one way; ideas are joined by travel or a morph; no wobble
- [ ] something moves during every hold
- [ ] what carries the edit is decided (voice / music / bed); hits follow it
- [ ] SFX only on transitions and key moments
- [ ] transitions are moves (travel, whip, morph, sweep, bloom, zoom-through), not fades
- [ ] a lead element guides the eye
- [ ] every frame works as a finished layout (grid, one accent, small print at the edges)
- [ ] every frame has a light logic (art_direction.md 5b): key light, real dark and light, soft shadows
- [ ] key frames have three depth planes and a set (floor, haze, light, dust); the camera changes
      size every 2-4 s and stays within 15 degrees of head-on, cuts land on beats (section 2b);
      QA `space` and `oblique` pass
- [ ] dynamics targets set; QA `dynamics` and `camera` pass
