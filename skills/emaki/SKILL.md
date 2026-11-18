---
name: "emaki"
description: "Emaki makes short motion videos entirely in code (Python, numpy, skia, ffmpeg): promo and explainer clips, product videos with recreated UI, social reels, kinetic typography, animated data. Output: a finished mp4 or an editable After Effects project. Works in gates: style frames, then an animatic with sound, then the final. Sketch mode for quick style tests. Use it whenever the user asks for a video, reel, promo or animation made by code, even without the word 'motion'. TRIGGER: «make a video», «motion video», «animate this», «explainer video», «promo video», «product video», «reel», «kinetic typography», «After Effects project», «quick style test», «зроби ролик», «моушн», «відео кодом», «промо-ролик», «рілс», «анімуй», «ескіз ролика». NOT: AI image or video generation, editing existing footage, slide decks, real-time web animation (React, GSAP, scroll, hover)."
---

# Emaki (絵巻)

Short videos (10-120 s) where every frame is drawn by code (`scripts/engine`) and the sound is the
user's track or voice-over from `assets/`, otherwise synthesized (`scripts/audio`). No stock, no
generative models. External files only from the user.

This file is the priority. If a reference file contradicts it, follow this file.

## How this skill has failed before (read first)

- **Slideshow** (the first test films): elements enter and sit, the camera glides
  over finished layouts, ideas joined by fades and wipes. The user: "it looks like a slide deck".
- **Grey film** (a later product film): the motion was close to the references, the picture was not.
  Slate UI on a grey-blue ground, no light source, no real white or black, the accent on screen
  in 2 of 16 frames. The references all have a light logic. Now: art_direction.md 5b, QA `look`.
- **Preview lied** (fixed): blurs, glows and shadows rendered 4x weaker in the preview than in
  the final, so the final "looked different". The engine now scales them the same at any size.
- **Two-three hours to a final** (one product film: 13 previews and 3 critic rounds in one round
  of edits, three 10-minute finals in another, an 18-minute final in the last), then the picture
  or the sound was wrong. Now:
  gates with cheap renders before the final, and finals that re-render only what changed.
- **Clipped slams, web-sized type, filler decoration** (rotating wireframes, blurred grey cards)
  to cover empty space.

## The core idea: one continuous shot

1. **A carrier.** One object lives through the whole video and turns into each next idea (a dot
   writes a word, becomes a target, stretches into a line, unfolds into a grid; a chat message
   becomes a task, splits into steps, the steps fill a progress bar, the bar closes into a "done"
   badge). Choose it from the story, not from decoration.
2. **Transitions are transformations**: morph, split, unfold, zoom through a detail, match cut on
   shape, whip with motion blur. Never fade out then in, never cut to an empty frame.
3. **The camera is operated**: it pushes into the detail that matters, follows the carrier, pulls
   back to reveal. A locked frame only as an accent under one second.
4. **No holds.** While a phrase is read, something keeps happening: letters fill, an underline
   draws, a counter runs, labels build around it.
5. **Type is an actor**: hero words 60-80% of the frame width, and they act.
6. **UI is shown big and partial**: two or three fields large, the camera follows the cursor.
7. **Every frame has light and material** (art_direction.md 5b): one light source, a real dark
   and a real light, soft shadows, depth of field, the accent where the eye must go, grain.

The look and the dynamics are separate decisions. A calm, light B2B brand still gets a moving
camera, transformations, rhythm and light. Calm means softer easing and fewer hits, not slides.

## Workflow: three stages, two gates

Every stage ends with something the user can judge in under a minute, before the next, more
expensive stage starts. Stop at both gates and wait for "ok" or edits. Skip the stops only if the
request says so ("no stops", "approved in advance", "autopilot", «без зупинок»); write
`approved: true` with the quote in brief.yaml and still run the critic at both gates.

**Sketch mode** for a quick style test ("sketch", "draft", "quick test", "style test", «ескіз»,
«чернетка», «проба стилю»): no gates, no critic, one preview, then the final; FAILs are still
fixed, WARNs are listed. Client work and output = ae stay in the full mode unless the user asks
for a sketch. Offer to finish it properly afterwards: it continues at gate 2 on the same project.

### Setup

```bash
SKILL_DIR="<the folder this SKILL.md is in>"   # set in every shell call; keep paths in quotes
bash "$SKILL_DIR/scripts/setup_env.sh"
python3 "$SKILL_DIR/scripts/mv.py" -h          # the CLI, written $MV below
```
If setup stops because pip cannot install into this Python, follow its hint. On the user's
computer: make the venv it names and use that venv's python in place of `python3` in `$MV`. In a
disposable sandbox or container only: re-run setup with `EMAKI_ALLOW_SYSTEM_PIP=1`.
`$MV init <dir> --aspect 9:16 --duration 30` creates the project in the folder the user names
(otherwise `<working folder>/videos/<YYYY-MM-DD>-<slug>/`). Long renders stop at a time budget
(`--budget`, default 140 s, below most shell command timeouts), exit with code 3 and `PARTIAL`;
run the same command again and it continues where it stopped.

### Stage 0: Brief and references -> brief.yaml

Collect topic, goal, platform, duration, format, language, output (mp4 | ae), texts, brand
sources, sound source. Ask ONE question only if something critical is missing; mark the rest
`[ASSUMPTION]`. Copy the user's texts verbatim: never rewritten, only split into lines. Your own
text is `[DEMO COPY]`. `language` is the language of the on-screen copy (default `en`); the fonts
must cover it.

For every video reference run `$MV analyze-ref <file> --crop W:H:X:Y --skip s` (with a library,
add `--id <name>` to file it there), open the sheets and write the breakdown **motion first**
(carrier, how one idea turns into the next, camera, how long anything stays still, rhythm of
hits), then **light** (where it comes from, what glows, darkest and lightest areas, materials),
palette and fonts last. If the user keeps a library (`motion-lib/`, found by walking up from the
project but never above the home folder, or `$MV --lib DIR <command>` / `$MV_LIB`), read its
`README.md` and `references/INDEX.md`: the user's taste. Commands print `[lib]` lines with the
library and the engine_ext modules they ran; if a path there is not the user's, stop and ask.

### Stage 1: Concept, look, style frames -> GATE 1

1. Motion concept, five lines at the top of storyboard.md: carrier; chain of transformations
   (one arrow per idea); camera path; two or three signature moments with times; rhythm (BPM, how
   often something hits). If the chain needs a fade or a cut to empty, it is a slideshow: rework.
2. design.yaml (`assets/templates/design.yaml`, guidance `references/art_direction.md`): palette
   with roles, fonts that cover the copy language, **light block**, easing per role, `dynamics`,
   `forbidden`, sound palette, a `why` on every block. Brand input: colours, fonts, radii and
   components from the source, UI recreated as vectors, the rest `[DESIGN DECISION - not in
   source docs]`.
3. Beat list in storyboard.md: one row per beat along the shot (time, what the carrier becomes,
   camera move, text, sound), on the BPM grid, reading time >= max(1.2 s, 0.3 s per word),
   at most 8-10 beats per minute.
4. **Style frames.** Build in video.py only what the 3-5 key moments need (the hero composition
   of each, with its light, materials and type at final size) and set `P.keyframes` to them.
   `$MV styleframes <dir>` renders them at final quality in seconds (`--ref <id>` puts a library
   reference next to them). Open them next to the reference sheets. They must hold up as
   posters; push them until they do.
5. Critic on the frames (`references/critic.md`, gate 1 items). Fix what it finds.
6. Check the plan against the brief (what must not be shown, the end card, vocabulary).
7. **GATE 1, STOP.** Send: the motion concept, the beat list, the look in three lines, the style
   frames image (`out/styleframes.png`), conflicts and assumptions. Wait for "ok".

### Stage 2: Animate, animatic with sound -> GATE 2

1. Animate the whole film in video.py as one long scene on a big canvas (`references/motion.md`
   section 00, read it before the code; API in `references/api.md`). If the engine lacks a
   primitive, write it in `<project>/engine_ext/`; do not simplify the concept to fit the engine.
2. `$MV timeline <dir>`: no red holds, every lead element acts after it enters. Fix on the map,
   before any render.
3. `$MV preview <dir>` is the animatic: half size, 15 fps, the real sound mix, contact sheets, QA.
   About 20-50 s for a 45 s film. Fix every QA FAIL, fix or justify every WARN (read the `look`
   lines). Re-runs only re-render the 2 s chunks that changed.
4. Sound: with the user's voice, `$MV voice <dir>` (word times in data/words.json, `--cues` for an
   .srt); with the user's track, `$MV beats <file>`. A synthesized bed: render 2-3 bed variants
   as separate mp3 files for the user to pick by ear (you cannot listen).
5. Watch it as a viewer: `$MV strips <dir>` (`--ref <id>` with a library), then the critic (full
   rubric) as a subagent. Any NO on items 1-4 goes back to stage 1, not to patching.
6. **GATE 2, STOP.** Send: `out/preview.mp4`, the sound variants, the QA summary, the critic
   verdict and what changed, the final render estimate printed by the preview. Wait for "ok".

### Stage 3: Final

`$MV final <dir>`: 1080 px on the short side, 30 fps (`--fps 60` on request), 2x supersampling,
-14 LUFS / -1 dBTP, QA on the file. A 45-50 s film renders in about 2 minutes. After any edit,
run it again: only the chunks whose picture changed are rendered (a local fix: ~25 s), a
sound-only change just re-mixes. Never deliver a final with a known QA FAIL. User edits after
delivery go straight to stage 3 unless they change the concept or the look.

Output = After Effects: stages 0-2 the same, then `$MV ae <dir>`; read `references/ae_backend.md`.

## Speed budget

Rendering is not the bottleneck (measured on a 47.5 s product film at 1080p: 92 s for the
final, 20 s for the animatic, 3 s for four style frames). The time goes into loops.
- Gates decide the look on stills and the motion on the animatic; the final is for finish.
- At most two animatic cycles before gate 2. If the second still fails critic items 1-4, stop and
  show the user what is wrong.
- Look at fewer images: style frames, the timeline, the preview strips; a contact sheet only
  where QA points.
- Single moments: `$MV still <dir> <t>` (final quality) instead of a new preview.
- Motion blur stays automatic (`P.auto_blur`); never force `scene.motion_blur` on a whole scene.
- Give layers `start`/`end` around the moments the camera can see them.
- Over 0.2 s per final frame (the preview prints it) means an effect or a layer is too costly:
  find it before the final.

## Quality: sharp picture, smooth motion, clean sound

The animatic is for timing and composition; the style frames and `still` are for the look; all
three show the same picture as the final.

Picture:
- One light source per shot, a real dark and a real light in every frame, soft shadows, the
  accent at full saturation where the eye must go, luma-weighted grain (art_direction.md 5b).
- Blur means "out of focus": it lives on background layers and through camera depth of field.
  Text, UI and the element being read are always sharp.
- Grain, bloom, glow and sheen are seasoning: one sheen per object, glow only on light.

Motion:
- Every move eases in and out; nothing starts or stops at full speed.
- No wiggle, drift or back-and-forth on the camera or on cards. A thing moves once, with intent.
- Big moves take at least 0.3 s; nothing jumps between two frames unless it is a deliberate cut.
- Check `$MV strips` around every camera move for stutter before the final.

Sound:
- Never let hits come out of silence: a quiet bed under the whole film, hits 6-10 dB above it.
- Loudness range under 8 LU; a loud hit once or twice.
- Each kind of event has its own sound, repeats vary in pitch and filter: a soft high click for
  UI, a short low thump when a card lands, an airy whoosh for camera travel, a tonal chime for
  money and approval, a riser before the payoff. Cut the harsh 3-5 kHz area.
- Sound only on transitions and key moments, not on every event.
- "The voice leads" needs a voice file in `assets/`. Without one, time the text to the bed.

## Hard rules

- On-screen copy is in the brief's `language`; every glyph exists in the chosen font (QA
  `glyphs`). Ukrainian copy also passes QA `language` (no letters Ukrainian does not use).
- Brief copy is never rewritten (QA `brief_copy`).
- Every animation is eased; linear only where the style asks for it.
- The camera glides, travels or follows; shake only where the brief asks.
- Exceptions are declared, never silent: `layer.allow("static" | "offframe" | "overlap", why=...)`.
- Never change a scene's length to hide a defect.
- You cannot listen: say the sound is generated and must be checked by ear; ask for the user's
  voice or licensed track when the piece matters.
- Don't fill empty space with decoration. Empty space means the camera is too far away or the
  frame has no light.

## Delivery

Links, duration, format; the motion concept in two lines; the look in one line; QA result,
critic verdict and what they changed; measured render times; `[ASSUMPTION]` and `[DEMO COPY]`
items. Once the user approves, offer `$MV save-style` and `$MV promote` (they create the
library if there is none).

## Reference files

| file | read when |
|---|---|
| references/motion.md | stage 1-2; section 00 before any code |
| references/art_direction.md | stage 1 look; section 5b light and material, 10b current vs dated |
| references/api.md | writing video.py or engine_ext |
| references/critic.md | both gates |
| references/qa.md | stage 2-3 |
| references/sound.md | sound block, voice-over or track sync |
| references/platforms.md, fonts.md | platform specs, fonts |
| references/ae_backend.md | output = ae |
| motion-lib/ (optional) | the user's analysed references, techniques and styles, stage 0-1 |

CLI: `init`, `styleframes`, `timeline`, `preview`, `strips`, `still`, `final`, `qa`, `estimate`,
`storyboard`, `contact`, `voice`, `beats`, `analyze-ref`, `ae`, `styles`, `save-style`, `promote`
(`$MV -h`). Engine regression after engine changes:
`python3 "$SKILL_DIR/tests/regression_terminal/compare.py" <out>` (needs DejaVu fonts in
/usr/share/fonts, as on most Linux); light and material demo: copy
`tests/light_demo` to a scratch folder (the skill folder may be read-only) and run
`$MV styleframes` on it.
