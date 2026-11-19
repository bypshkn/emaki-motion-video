---
name: "emaki"
description: "Emaki makes short motion videos entirely in code (Python, skia, ffmpeg): promo and explainer clips, product videos with recreated UI, social reels, kinetic typography, animated data. Output: a finished mp4 or an editable After Effects project. Works in gates: style frames, then an animatic with sound, then the final. Sketch mode for quick style tests. Commercial by default: every external file gets a license record, the film ships with a rights pack. Use it whenever the user asks for a video, reel, promo or animation made by code, even without the word 'motion', or asks what Emaki does and how to start. TRIGGER: «make a video», «motion video», «animate this», «explainer video», «promo video», «reel», «kinetic typography», «After Effects project», «quick style test», «licenses for the video», «зроби ролик», «моушн», «відео кодом», «промо-ролик», «рілс», «анімуй», «ескіз ролика». NOT: AI image or video generation, editing existing footage, slide decks, real-time web animation (React, GSAP, scroll, hover)."
---

# Emaki (絵巻)

Short videos (10-120 s) where every frame is drawn by code (`scripts/engine`) and the sound is the
user's track or voice-over from `assets/`, otherwise synthesized (`scripts/audio`). No generative
models for the picture or the music; the one exception is a library voice-over from Google
Chirp 3 HD with the user's own API key (`$MV tts`, references/sound.md). Films are often made for
clients, so an external file comes only from the user, the client or a stock site whose license
allows client work, and it gets a row in `licenses/assets.yaml` the
moment it enters the project (references/licensing.md).

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
- **Flat film** (a type-led product film): good layout and light, still "fine but ordinary".
  Everything lived on one plane, the camera only slid and zoomed, one size, one angle. The user:
  "it's all flat: no depth, no cinema, no camera, no angles". Now: a set in depth and camera
  setups (motion.md 2b), design.yaml `space`, QA `space`, critic items 16-17.
- **PowerPoint 3D** (its first 3D test): the head-on opening worked, the side views did not:
  "from the side it already looks like a PowerPoint presentation". Extruded letters with flat
  sides, cards turned in space, photo walls on tilted planes; then a close-up from a low, near
  camera that bent the letters ("don't bend them"). The engine is 2.5D: film it head-on (within
  15 degrees), close-ups through the lens, no extruded type; QA `oblique` fails both.
- **The space ate the type** (the same film's hook): camera and depth arrived, the big-type
  concept left: numbers at 45 % of the width on a neon grid, glow on every word, HUD clutter.
  "We lost the original concept with the big type, and it still feels clumsy." In a type-led
  film the word stays the frame; QA `type_scale` warns.
- **Nobody understood it** (first-time viewers of the same film): "it needs a voice-over,
  otherwise it's not clear what it's about"; "the amount of text on screen needs calibrating,
  you don't have time to understand what's going on". Now: the voice question at stage 0,
  `text_pace`, reading time by pace, the lead element as the eye's guide, the first-time viewer
  check.
- **Pictures nobody licensed** (a client ad, found after approval, before publishing): 86 photos
  of 41 lots from two auction websites and both sites' logos, collected "for the mockup", went
  into the film. One of the sites allows its content for personal, non-commercial use only. The
  music was licensed, but no proof was saved. Now: the rights ledger, QA `rights` fails the
  final, `$MV licenses` writes the pack that goes to the client.

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
5. **Type is an actor**: hero words 60-80% of the frame width, and they act. In a type-led film
   the word is the frame in every key frame, also in the shots with depth: the camera moves into
   the word or along it, never away from it to show the set.
6. **UI is shown big and partial**: two or three fields large, the camera follows the cursor.
7. **Every frame has light and material** (art_direction.md 5b): one light source, a real dark
   and a real light, soft shadows, depth of field, the accent where the eye must go, grain.
8. **Depth when the concept has a world, filmed head-on** (motion.md 2b): a soft foreground, a
   sharp subject and a background in the haze; a floor, air and lamps when the concept allows a
   set; the shot size changes every 2-4 s, cuts between setups land on beats, inside a setup the
   camera dollies, cranes or arcs a little. The camera stays within 15 degrees of head-on and
   never comes near enough to bend type. A type-led film gets its depth from scale contrast,
   crop, layered words and cuts, not from a 3D set.
9. **A first-time viewer understands it** (motion.md 6b): what the film is about, who it is from
   and what to do, from the picture and the voice alone. The eye always knows where to look:
   the lead element (a dot, a line, a cursor, the carrier) takes it to the next thing to read,
   and the next thing appears where the eye already is. Text is calibrated to the pace.

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

### First contact

New users often install the skill without reading the README. Two cases, both in
`assets/welcome.md`, said in the user's language:
- The user asks what Emaki does, how to start or what to prepare, or asks for a video with
  nothing to build on ("make a video"): send the full version and stop. No setup and no stage 0
  questions in that message.
- The user's first Emaki video (no earlier project in this conversation or in `videos/`) comes
  with a real request: open stage 0 with the short version, then go on as usual.

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
sources, sound source. **Voice**: for a promo or an explainer ask whether there will be a
voice-over: the user's recording (`user` / `file`), a generated library voice (`tts`: Google
Cloud Text-to-Speech, Chirp 3 HD voices, with the user's own Google Cloud API key; setup in
references/sound.md), or none. With `tts` the user picks the voice: there is no default. Point
them to Google's Chirp 3 HD voice list, ask which one, and write it to `tts_voice`; quality
differs between languages, so the user listens before committing. Not for an audience under 18:
Google's terms forbid it. Without a voice the text carries the story alone and the pace must
allow reading: first-time viewers of a silent explainer often cannot say what it was about.
Write the answer to `voice` in brief.yaml. Ask ONE question only if something critical is
missing; mark the rest `[ASSUMPTION]`. Copy the user's texts verbatim: never rewritten, only
split into lines. Your own text is `[DEMO COPY]`. `language` is the language of the on-screen
copy (default `en`); the fonts must cover it.

**Rights** (references/licensing.md). `use: commercial` is the default: the film is sold,
published or shown to a client; `internal` only for a test that never leaves the team. Write
whose account publishes it (`publisher`): Content ID claims go there. Every file the client sends
goes to `client_materials` and into the ledger as `license: client`; their written OK on logos,
fonts, photos and product screens is the proof. A file from another website (an auction, a
marketplace, a social network, search results, a competitor) is a reference: it goes to `refs/`,
never to `assets/`, and the look is rebuilt in code. A stock track: Pixabay or a source with a
license for client work, preferably without the Content ID shield; its row goes in at download.

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
   Above them, the film in one sentence (what a first-time viewer must get), and with a voice the
   voice-over script first: the screen text is its key words. With `voice: tts` the script goes
   into brief.yaml `voice_script` with an `at` per phrase from the beat list; `$MV tts <dir>`
   makes the takes now, so the user hears the voice at gate 1 and the beats are timed to it.
2. design.yaml (`assets/templates/design.yaml`, guidance `references/art_direction.md`): palette
   with roles, fonts that cover the copy language, **light block**, **space block** (the set,
   planes, sizes, angles, moves), easing per role, `dynamics`,
   `forbidden`, sound palette, a `why` on every block. Brand input: colours, fonts, radii and
   components from the source, UI recreated as vectors, the rest `[DESIGN DECISION - not in
   source docs]`.
3. Beat list in storyboard.md: one row per beat along the shot (time, what the viewer must get,
   what the carrier becomes, camera setup and move, text, sound), on the BPM grid. Reading time
   by `dynamics.text_pace` (motion.md 6b): `read` (default) 1 s + 0.4 s per word and up to 7
   words per screen; `kinetic` (a film built on speed) one or two words a beat. At most 8-10
   beats per minute in `read`.
4. **Style frames.** Build in video.py only what the 3-5 key moments need (the hero composition
   of each, with its light, materials, depth and type at final size, seen from its planned
   camera setup, head-on; at least one frame is the hero shot) and set `P.keyframes` to them.
   `$MV styleframes <dir>` renders them at final quality in seconds (`--ref <id>` puts a library
   reference next to them). Open them next to the reference sheets. They must hold up as
   posters; push them until they do.
5. Critic on the frames (`references/critic.md`, gate 1 items). Fix what it finds.
6. Check the plan against the brief (what must not be shown, the end card, vocabulary).
7. **GATE 1, STOP.** Send: the motion concept, the beat list, the look in three lines, the style
   frames image (`out/styleframes.png`), conflicts and assumptions, and every external file the
   frames use with its license (blocked ones first: replace them now, not after approval). With
   a generated voice also `assets/voice.wav` and the script: the user approves the voice and the
   takes by ear (`--retake N` for a phrase they reject). Wait for "ok".

### Stage 2: Animate, animatic with sound -> GATE 2

1. Animate the whole film in video.py as one long scene on a big canvas (`references/motion.md`
   sections 00 and 2b, read them before the code; API in `references/api.md`, the set and the
   camera setups in section 8; worked example `tests/space_demo/video.py`). If the engine lacks a
   primitive, write it in `<project>/engine_ext/`; do not simplify the concept to fit the engine.
2. `$MV timeline <dir>`: no red holds, every lead element acts after it enters. Fix on the map,
   before any render.
3. `$MV preview <dir>` is the animatic: half size, 15 fps, the real sound mix, contact sheets, QA.
   About 20-50 s for a 45 s film. Fix every QA FAIL, fix or justify every WARN (read the `look`
   lines). Re-runs only re-render the 2 s chunks that changed.
4. Sound: with the user's voice, `$MV voice <dir>` (word times in data/words.json, `--cues` for an
   .srt); with a generated voice, `$MV tts <dir>` after every script change (only new phrases
   are sent; approved takes are kept); with the user's track, `$MV beats <file>`. A synthesized bed: render 2-3 bed variants
   as separate mp3 files for the user to pick by ear (you cannot listen).
5. Watch it as a viewer: `$MV strips <dir>` (`--ref <id>` with a library), then the critic (full
   rubric) as a subagent, and a second subagent as the first-time viewer (critic.md, item 18):
   only the preview frames and the sound plan, no brief. Any NO on items 1-4 or 18 goes back to
   stage 1, not to patching.
6. **GATE 2, STOP.** Send: `out/preview.mp4`, the sound variants, the QA summary, the critic
   verdict and what changed, the final render estimate printed by the preview, the `rights` lines
   of the QA (a blocked file now WARNs, at the final it FAILs). Wait for "ok".

### Stage 3: Final

`$MV final <dir>`: 1080 px on the short side, 30 fps (`--fps 60` on request), 2x supersampling,
-14 LUFS / -1 dBTP, QA on the file. A 45-50 s film renders in about 2 minutes. After any edit,
run it again: only the chunks whose picture changed are rendered (a local fix: ~25 s), a
sound-only change just re-mixes. Never deliver a final with a known QA FAIL. User edits after
delivery go straight to stage 3 unless they change the concept or the look.

Before the handover, `$MV licenses <dir>`: stubs for files with no row, the license snapshots,
`licenses/README.md` (English, for the client) and `licenses/copy-for-approval.md` (every line we
wrote, prices and quotes included). On a commercial film QA `rights` FAILs the final for a file
with no row or a blocked row, so the film is not delivered for publication until they are
cleared. Proofs behind a login (the Pixabay License Certificate, page screenshots) and the
client's written OK are the user's to collect: list them.

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
  find it before the final. A set is the exception within reason: a frame with a floor, haze,
  beams, dust and a reflection costs 2-3x a flat one, and arcs and cranes add motion-blur
  sub-frames (the 8 s `tests/space_demo` final: 1-2 minutes on 4 cores). Budget it at gate 2
  from the printed estimate.

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
- The camera blurs its own moves; fast moves of layers without a camera move get real motion
  blur through `P.blur_window(t0, t1, samples)`.
- Check `$MV strips` around every camera move for stutter before the final.

Sound:
- Never let hits come out of silence: a quiet bed under the whole film, hits 6-10 dB above it.
- Loudness range under 8 LU; a loud hit once or twice.
- Sounds of the film's world, not abstract beeps: a car passing, a door, an engine, a dash
  chime, paper, a camera shutter, as long as the story lives there. Viewers mocked a beep on
  every event as a toy sound; an earlier cut of the same film, with car sounds on the key
  moments, worked.
  Keep the sound design, cut the generic UI clicks. Each kind of event has its own sound,
  repeats vary in pitch and filter. Cut the harsh 3-5 kHz area.
- Sound on transitions and key moments, not on every event.
- "The voice leads" needs a voice file in `assets/`: the user's recording or `$MV tts`. Without
  one, time the text to the bed.

## Hard rules

- On-screen copy is in the brief's `language`; every glyph exists in the chosen font (QA
  `glyphs`). Ukrainian copy also passes QA `language` (no letters Ukrainian does not use).
- Brief copy is never rewritten (QA `brief_copy`).
- Every animation is eased; linear only where the style asks for it.
- The camera glides, travels or follows; shake only where the brief asks.
- Exceptions are declared, never silent: `layer.allow("static" | "offframe" | "overlap", why=...)`.
- Never change a scene's length to hide a defect.
- You cannot listen: say the sound is generated and must be checked by ear; ask for the user's
  voice or licensed track when the piece matters. A generated voice is never approved by you:
  the user hears every take.
- Generated voice: the user's own Google Cloud key and the voice the user picked by ear;
  Chirp 3 HD voices only (the model with a free tier), never Gemini-TTS or another paid model.
  The key lives in `secrets/google-tts-key.txt`: never print it or copy it anywhere. Google's
  terms (licensing.md): no generated voice in a film for children or teenagers, never present it
  as a real person or a human recording, never in unsolicited mass mailings.
- Don't fill empty space with decoration. Empty space means the camera is too far away or the
  frame has no light.
- Every external file has a row in `licenses/assets.yaml` from the moment it enters the project:
  source page, author, license, date. Allowed: the user's and the client's own files (the client's
  with their written OK), Pixabay and Unsplash files under their licenses, fonts under OFL or
  Apache, sound and pictures made in code. Pictures, video and logos from any other website stay
  in `refs/`; QA `rights` blocks them on screen. "Just for the mockup" files go to `refs/` too:
  mockups get approved and become the film.
- Third-party logos and trademarks (auctions, platforms, partners) only with written permission;
  otherwise name them in the copy.
- Product screens show demo data only, never a real user; features not yet released need the
  client's OK.

## Delivery

Links, duration, format; the motion concept in two lines; the look in one line; QA result,
critic verdict and what they changed; measured render times; `[ASSUMPTION]` and `[DEMO COPY]`
items; the rights status from `$MV licenses` (cleared, or what blocks publication and what the
user must still collect) and the `licenses/` folder to send with the film. Once the user
approves, offer `$MV save-style` and `$MV promote` (they create the library if there is none).
When the film goes into an email, also run `$MV email <dir>` without being asked: video never
plays in an email body, so it writes an inline GIF (grain-free, the end card as the first frame
for Outlook) and a 720p mp4 under Gmail's 25 MB for the attachment.

## Reference files

| file | read when |
|---|---|
| references/motion.md | stage 1-2; sections 00 and 2b before any code |
| references/art_direction.md | stage 1 look; 5b light and material, 5c space, 10b current vs dated |
| references/api.md | writing video.py or engine_ext |
| references/critic.md | both gates |
| references/qa.md | stage 2-3 |
| references/sound.md | sound block, voice-over (recorded or generated) or track sync |
| references/platforms.md, fonts.md | platform specs, fonts |
| references/ae_backend.md | output = ae |
| references/licensing.md | stage 0 (sources), whenever a file enters the project, before the handover |
| motion-lib/ (optional) | the user's analysed references, techniques and styles, stage 0-1 |

CLI: `init`, `styleframes`, `timeline`, `preview`, `strips`, `still`, `final`, `email`, `licenses`,
`qa`, `estimate`, `storyboard`, `contact`, `voice`, `tts`, `beats`, `analyze-ref`, `ae`, `styles`,
`save-style`, `promote` (`$MV -h`). Engine regression after engine changes:
`python3 "$SKILL_DIR/tests/regression_terminal/compare.py" <out>` (needs DejaVu fonts in
/usr/share/fonts, as on most Linux); demos (copy to a scratch folder first, the skill folder may
be read-only, then run `$MV styleframes` or `$MV preview`): `tests/light_demo` (light and
material), `tests/space_demo` (the set, reflection, camera setups head-on, cuts, a small arc,
crane, dolly zoom, a blur window).
