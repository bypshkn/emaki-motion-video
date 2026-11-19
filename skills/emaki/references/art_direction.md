# Art direction: from brief to design.yaml

The engine has no look of its own. Every video gets a design derived from its brief; the style
library is a set of worked examples, not a menu. A finished design.yaml lets someone predict how
any new scene of this video would look and sound.

## Contents
1. Derivation order
2. Palette
3. Type
4. Grid and composition
5. Motion language
5b. Light and material
5c. Space: the set and the camera
6. Effects policy
7. Sound palette
8. Brand input (site, screenshots, design system)
9. References (words, frames, screenshots)
10. Anti-defaults: how to avoid the generic look
10b. What reads as current (2026) and what reads dated
11. design.yaml checklist

## 1. Derivation order

1. Read the brief: goal, audience, platform, duration, tone words, references, brand sources.
2. Write one sentence of **concept**: the metaphor the video borrows from (a printed report, a
   control room, a toy box, a film title sequence, a product UI). Every later decision serves it.
3. Decide in this order: palette -> type -> grid -> light -> space -> motion -> effects (+ forbidden) -> sound.
   Later choices must not contradict earlier ones.
4. For each block write `why:` in one line that points to the brief or a reference
   ("brief: 'calm, premium' -> long decelerations, no overshoot").
5. If a library style is close, start from it and say so in `meta.style_ref`; change what the
   brief requires. If none is close, `style_ref: custom`.

## 2. Palette

- Roles, not swatches: `bg`, `surface`, `text`, `muted`, `accent`, optionally `accent_2..n`,
  `rule`, `grid`, semantic (`warn`, `success`), data series (`data_1..`).
- One dominant accent. A second accent only when the content has two voices (comparison,
  before/after). Saturated colour is spent where attention must go.
- Text on background >= 4.5:1 (QA measures the rendered frame). Check `muted` too.
- A bright accent is often too light for text (tomato on cream is ~2.9:1). Keep it for shapes and
  add `accent_text`, a darker variant: `*word*` markup switches to it automatically.
- Dark vs light follows the concept and platform, not habit: light reads as editorial/print,
  dark as product/tech/cinema. Social feeds are mostly light UI; a dark video stands out there,
  a light one feels native.
- Never pure #000/#FFF unless the concept demands hard contrast (terminal, brutalist).

## 3. Type

- At most two families (display + text) plus an optional mono for data/HUD.
- The fonts cover every glyph of the copy language (QA `glyphs`); for Ukrainian that means
  Ґ Є І Ї and the ’ apostrophe, and `setup_env.sh` lists the system families that have them.
  Prefer fonts in the project's fonts/, then system fonts; otherwise DejaVu as the working
  fallback, and recommend one specific free font to download (references/fonts.md).
- Scale: `base` (fraction of the short side) and `ratio` (1.2 minor third .. 1.5 perfect fifth).
  Bigger ratio = more drama. Video copy is large: body >= 0.03 of the short side on phones.
- Display tracking slightly negative for big sizes, caps labels positive (0.06-0.12 em).
- Use `features: {tnum: true}` for counters and tables.

## 4. Grid and composition

- Margin >= 0.08 of the short side (QA safe area). For 9:16 social, keep key copy out of the
  platform UI zones (top ~13%, bottom ~35% for Reels/TikTok ad specs; QA warns).
- Pick a grid that fits the concept: 12 columns for editorial asymmetry, 6 for bold social,
  a strict centre axis for a keynote feel.
- One lead element per moment, supported by at least two layers of depth (a ground with light
  on it, the lead, a detail or a foreground element). Hierarchy by size and contrast, not by
  adding boxes.
- Hero copy is big: 60-80% of the frame width for the key word or line, at least 3x the size of
  the smallest text on screen. Web-sized type in a video frame is the most common failure.
- Empty space is a choice with light in it (a gradient, a falloff, grain), never a flat field
  around a small object. If a frame looks empty, the camera is too far away.

## 5. Motion language and dynamics (details in motion.md)

The look and the dynamics are separate decisions. Decide the look from the brief's tone; decide
the dynamics from its energy and platform. A light, non-neon brief still gets a living camera,
hits on beats and transitions that move; only the tempo and the intensity change.
Write the `dynamics` block (targets that QA measures) and list the 4-6 moves of the grammar.
With a video reference, run `mv.py analyze-ref` and take its numbers as the starting targets.


- `tempo`: calm / medium / fast. Sets default durations.
- `easing` per role: enter, exit, move, emphasis, transition. Character examples:
  calm/premium -> `out_expo`, `in_out_quart`, no overshoot; energetic/playful -> `spring:wobbly`,
  `out_back`; technical/precise -> `out_quint`, `in_out_cubic`; mechanical/retro -> `linear`,
  `steps(n)`, `hold`.
- Transitions list: 2-4 kinds, used consistently.
- `stagger`: 0.03-0.08 s; smaller for chars, larger for words/lines.

## 5b. Light and material (what makes a frame look finished)

Measured on a 47.5 s product film against the four reference reels (motion.md, top): the motion was close, the
picture was not. Every frame of v4.1 was slate-grey UI on a grey-blue ground, with no light
source, no real white or black and the accent on screen in 2 of 16 sampled frames. Every
reference has a light logic: r04 gradient light inside shapes and rim highlights on edges, r01
glowing light in a dark world, r03 one saturated green with a soft halo on white. The rules:

1. **One light source per shot.** Decide where the light comes from (top-left by default) and
   keep it: a `KeyLight` pool on the ground (dark designs: screen blend; light designs: soft
   light), shadows falling away from it, highlights on the edges that face it. The light may
   travel with the camera; it never flickers.
2. **Real tonal range in every frame.** The darkest 1% near black on a dark design, the
   lightest 1% near white on a light design, and at least one object at the other end. QA
   `look` measures it on the render.
3. **Objects have material.** Cards lift off the ground with `SoftShadow` (contact + ambient), not
   one hard drop shadow; glass panels blur and tint what is behind them (`Glass`); a hero word, a
   logo or the key card catches a `sheen` once, on its key moment.
4. **Depth reads through focus, not through filler.** Layers at different depths with camera depth
   of field (`camera.dof`, `rack_focus`). The background is soft because it is out of focus, not
   because it is a blurred placeholder. Never fill the frame with grey wireframe cards.
5. **The accent is spent where the eye must go**: the moving element, the key word, the light.
   It must be on screen in most of the film (QA `look` warns under 40% of sampled frames).
6. **Texture against banding and plastic**: luma-weighted `grain` 0.012-0.025 on every film with
   gradients or glows. It is also what makes the picture feel made rather than generated.
7. **Brand palettes are not exempt.** A grey-blue B2B palette still gets a light source, a real
   white, a real dark and the accent at full saturation on the key moments; tag what you add
   `[DESIGN DECISION - not in source docs]`.

Write the light plan into design.yaml as a `light` block (key position and colour, ground, shadow
style, grain, where the accent lives) with a `why`.

## 5c. Space: the set and the camera (details in motion.md 2b)

A product film had good layout and good light and was still "fine but ordinary", because everything
lived on one plane and the camera only slid and zoomed. The 3D tests that followed showed the
other edges: seen from the side, or from a near low camera, the same flat layers read as
PowerPoint 3D; and a neon set with a camera shrank the big type until the concept was gone.
Decide first whether the concept has a world:
1. **A set from the concept**, when there is a world: a stage, an auction yard, a desk, a night
   street, a studio cyclorama, a screen in a room. Write it in one line (`space.set`). It gives
   the floor, the light sources and the air.
2. **Three planes in every key frame**: a soft foreground, the sharp subject, a background in the
   haze. The floor counts as a plane; dust and beams make the air visible.
3. **Scale cues**: things standing on the floor with a reflection or a contact shadow, beams that
   come from somewhere, a horizon that dissolves. Without them depth reads as blur, not space.
4. **Shot list in the storyboard**: for every beat the setup (size, small angle) and the move
   inside it. Plan one establishing shot, one hero shot (a close through the lens with a slow
   push in) and the cuts on beats.
5. **Never the PowerPoint 3D look**: no extruded WordArt type, no cards or screenshots rotated
   in space, no photo wall on a tilted plane, no glossy reflection under every element, no
   camera swinging round to the side or coming near enough to bend the letters. Depth comes from
   position, parallax, focus, haze and light; the camera stays within 15 degrees of head-on and
   close-ups come through the lens (QA `oblique`).
6. **Flat is a decision**, not a default: a Swiss poster, an editorial collage or a UI tutorial may
   stay on one plane (`space: {mode: flat, why: ...}`); the camera still moves.
7. **A type-led film keeps its type.** When the concept is big words, the set never shrinks
   them: the word fills 70-90 % of the width in every key frame,
   depth comes from scale contrast, crop and layered words, the camera moves into the word. A
   set is for concepts with a world (QA `type_scale`).

Write the `space` block: mode (flat | 2.5d), planes, shot_sizes, angles, moves, set, why.
QA `space` holds the film to it.

## 6. Effects policy

- `fx.enabled` lists global post effects with parameters; keep them subtle and purposeful
  (grain for analogue warmth, scanlines/glitch only for screen/tech concepts, bloom for light).
- `fx.forbidden` is a contract that QA enforces: name fx, easing families (`bounce`, `elastic`,
  `spring`, `back`, `linear`), transitions (`zoom`, `iris`, ...), layer kinds (`particles`) and
  text modes (`typewriter`, `scramble`) that would break the concept.

## 7. Sound palette (details in sound.md)

`genre` (engine genres: minimal, ambient, electronic, cinematic, lofi, corporate, playful, piano,
terminal), `bpm`, `key`, `timbres`, `sfx` list, `loudness: -14`. BPM ties to tempo: calm 70-90,
medium 95-115, fast 118-128. Scene lengths become whole bars.

## 8. Brand input

When the user gives a site, screenshots or a design system:
- Take colours, fonts, radii, shadows, icon style and component shapes from the source.
  Measure from screenshots (sample pixels) rather than guessing.
- Recreate product UI as vectors with the UI kit (Card, Window, Phone, Button, Input...) at the
  source's proportions. Do not paste screenshots as the UI unless the brief asks.
- Anything not in the sources (a motion curve, a background tint, an icon) gets the tag
  `[DESIGN DECISION - not in source docs]` in its `why`.
- If sources contradict each other (two different accent colours), flag it and ask before
  building.

## 9. References

- Words ("like an Apple keynote", "Swiss style", "retro VHS"): translate into concrete choices and
  write the translation in `why` ("Swiss: grotesk, flush-left, red accent, strict grid, no
  decoration").
- Frames/screenshots: extract palette (dominant + accent), type classification, layout density,
  texture, and implied motion. Read the image; do not invent details you cannot see.
- Video references (mp4/mov/gif in the project's references/ or assets/): run
  `mv.py analyze-ref <file> [--crop W:H:X:Y] [--skip s] [--detail a-b]`. Open the overview and
  detail sheets, then write down separately: the look (palette, type, texture) and the dynamics
  (metrics + the moves you see: how text arrives, what the camera does, how scenes change).
  A screen recording of something else: crop to the part that matters first.
  Links to YouTube/Instagram/Vimeo cannot be downloaded: ask for the file.
- A reference is a direction, not a template: never copy logos, characters or distinctive
  artwork from it.

## 10. Anti-defaults

The generic AI video look: dark gradient background, neon purple-blue accent, glassmorphism
cards, every element sliding up with the same ease, centred copy everywhere, random particles,
lens flares. Avoid it unless the brief literally asks.
- Do not start from the terminal demo or any library style unless the brief points there.
- Before locking design.yaml, check: could this palette+type belong to ten other videos? If yes,
  push one decision further toward the concept (a distinctive accent, an unexpected type pairing,
  a signature transition).
- Give the video one signature move (a highlight marker, a morphing logo shape, a split-screen
  push) and repeat it; consistency reads as design.

## 10b. What reads as current (2026) and what reads dated

Industry roundups for 2026 agree on a few directions (agency and vendor blogs, so treat them as
signals, not data). They fit this engine as follows:

| current | how to do it here |
|---|---|
| Kinetic type as the main character, readable on mute | hero words 60-80% of the width, `KineticWords`, `write_on`, fills and outlines that act; the line carries the story without sound |
| Tactile materials: grain, frosted glass, soft 3D depth | `grain` (luma-weighted), `Glass`, `SoftShadow`, depth + `camera.dof` |
| Cinematic depth: type and products in a lit set, filmed head-on | `Floor`, `haze`, `LightBeam`, `dust`, `Reflection` for the hero, `camera.shot/dolly/crane` (motion.md 2b) |
| Light as design: gradient light, glows, light sweeps | `KeyLight`, `sheen`, `Glow` on the light only, `Radial`/`Conic` gradient fills |
| Bold minimalism: oversized type, one bright unexpected colour, clean space | one accent at full saturation, big type, few elements, generous light-filled space |
| Hand-made accents: a callout or sticker moving on twos | `layer.on_twos(12)` on one element, never on the whole film |
| Ambient UI: a cursor that leaves a soft glow, a ping on the key button | `Cursor` + a small `KeyLight` that follows it; one `punch` on the key action |
| Vertical-first | design 9:16 as the master when the platform is Reels/TikTok/Shorts, not a crop of 16:9 |

Dated: glossy over-produced transition tricks (glitch, spin, zoom-through on every cut), the
neon-purple-on-black "AI" look, flat vector with no light, everything centred, every element
sliding up with the same curve, stock particles and lens flares, PowerPoint 3D (extruded
WordArt, cards rotated in space, mirror floors under everything), a grid floor to the horizon
when the story is not a screen or a plan, glow on every word, HUD clutter around the hero. Use one only when the brief or a
reference asks for it.

Sources: Product Hype, "5 Motion Design Trends Defining B2B SaaS in 2026"; AutoAE, "Motion
Graphics Trends 2026"; Tangence, "Top Motion Graphic Trends in 2026".

## 11. design.yaml checklist

- [ ] concept sentence in `meta`
- [ ] every block has `why` linked to the brief/reference (QA lint warns otherwise)
- [ ] palette roles + contrast plan; one dominant accent
- [ ] fonts that cover the copy language, sizes for every role used in video.py
- [ ] grid margin >= 0.08; platform zones considered
- [ ] easing per role, durations, stagger, transitions list
- [ ] light block: key light position/colour, ground, shadow style, grain, where the accent lives
- [ ] space block: mode, planes, shot sizes, angles, moves, the set in one line; type-led films keep their type
- [ ] fx.enabled subtle; fx.forbidden written
- [ ] sound genre/bpm/key/timbres/sfx; scene lengths in bars
- [ ] brand-derived values cite the source; inventions tagged
