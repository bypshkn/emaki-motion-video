# QA: automated checks + your own frame review

Run automatically by `mv.py preview` and `mv.py final`; reports go to out/qa_preview.md and
out/qa_final.md. FAIL blocks delivery. WARN must be fixed or explained to the user. INFO lists
[DEMO COPY] for the storyboard.

## Automated (scripts/qa.py)

| check | rule | level |
|---|---|---|
| safe_zone | copy text inside 8% margins of the frame | FAIL |
| safe_zone | copy outside platform UI zones (Reels/TikTok/Shorts ad specs) | WARN |
| overflow / glyphs | no word wider than max_width; every glyph exists in the font | FAIL |
| reading_time | between reveal and exit (half the reveal counts), by `dynamics.text_pace`: `read` (default) 1 s + 0.4 s/word, at least 1.4 s, and over 7 words on one screen WARNs; `kinetic` 0.35 s for one or two words, 0.3 s/word for longer lines | FAIL / WARN |
| contrast | median text luminance vs real rendered background (worst decile) >= 4.5:1 | FAIL |
| occlusion | copy covered >12% by a layer drawn above it | WARN |
| forbidden | nothing from design.yaml fx.forbidden: fx, easing families, transitions, layer kinds, text modes | FAIL |
| brief_copy | src="brief" text equals a brief.yaml text (or its line); unused brief texts | FAIL / WARN |
| sync | accents on the BPM grid within one frame; scene changes near beats; SFX transients present | FAIL / WARN |
| loudness | integrated -14 +-0.5 LUFS, true peak <= -1 dBTP (ffmpeg ebur128) | FAIL |
| flicker | global brightness jumps or oscillating tiles outside cuts/glitch pulses | WARN |
| aliasing | final without 2x supersampling; sub-pixel strokes; copy smaller than 0.018 x short side | FAIL / WARN |
| easing | short linear transform segments (unless the style is linear), velocity jumps at keys, > 0.12 x short side per frame without motion blur (`P.blur_window` covers it) | WARN |
| format | duration vs brief, empty tail or gaps between scenes, final 1080 short side / fps, 48 kHz stereo audio | FAIL |
| lint | design.yaml blocks without `why`; font fallbacks | WARN |
| voice | generated voice (`brief.yaml voice: tts`): `assets/voice.wav` and `data/voice_phrases.json` exist and match the current `voice_script` (text, take key, `at`), design.yaml `sound.voice` points at it; a phrase past the film end FAILs; a phrase pushed by the previous one, running past its scene, faster than 7.5 syllables/s, or with samples Google clipped WARNs; the monthly character counter (WARN above 80 % of 900,000) | FAIL / WARN |
| dynamics | frozen share and longest freeze vs design `dynamics` (FAIL when far off), big hits per second (WARN); measured on the video at 15 fps / 160 px so grain is not motion | FAIL / WARN |
| in_frame | copy text (kinetic words included) cut by the frame edge for >= 0.2 s; safe area checked every 0.1 s, a one-sample blip is ignored | FAIL |
| choreography | from the scene graph: >= 75 % of elements only enter and sit (FAIL, 50 % WARN); holds where nothing animates and the camera at most glides (a cut, an orbit, a crane or a dolly zoom counts as action), vs `dynamics.max_hold` (FAIL > 2x, WARN > 1x); >= 4 elements of a scene with the same entrance; one easing on >= 60 % of moves; slowest/fastest action < 2.5x (WARN) | FAIL / WARN |
| allowed | exceptions declared with `layer.allow(...)` and their reasons; > 1/3 of elements `static` is a WARN | INFO / WARN |
| language | Ukrainian copy (`language: uk`): no letters the Ukrainian alphabet does not have | FAIL |
| camera | the camera turns around more than once per 4 s, shakes, frequent zoom punches | WARN |
| sound | more sound effects per second than `sound.max_sfx_per_s` (default 1.0) | WARN |
| spectrum | power share of the mix: sub above -6 dB, mids below -12 dB, presence below -24 dB | WARN |
| fonts | a requested font was not found or skipped and a fallback was used | WARN |
| look | 16 frames of the render: flat frames (darkest and lightest 1% less than 0.55 apart), lifted blacks on a dark design, no real white on a light one, the saturated accent on screen in < 40% of frames | WARN |
| space | from the scene graph at 10 fps: depth planes on screen (on-screen scales > 8 % apart; a floor counts), camera moves per setup from keyed values (dolly with parallax, small orbit, crane, truck, dolly zoom; a zoom on one plane or a lens change alone is "zoom"), cuts, shot sizes (x1.4 apart) and angles (12 deg apart) at the start and end of every setup. Against design.yaml `space`: a declared move that never happens, too few planes, or a camera that only pans and zooms FAIL; too few sizes/angles WARN. Without a `space` block a film that is flat in every sense WARNs | FAIL / WARN |
| type_scale | in more than half of P.keyframes the biggest copy line spans under half the frame width: in a type-led film the space ate the type | WARN |
| rights | every external file (everything in assets/ and fonts/, each image or SVG drawn, each font used, the track and the voice) is covered by a row in licenses/assets.yaml (references/licensing.md). Commercial film (`brief.yaml use`, default): no row, `license: unknown`, a stock license with a source from another site, `status: blocked`, or a file from refs/ on screen FAIL the final and WARN the preview; open gaps (no page screenshot, no certificate for a Content ID track, no written OK from the client) WARN the final; a README older than the ledger WARNs. Internal film: WARN only. Fonts that declare OFL, Apache, Ubuntu or DejaVu licenses inside the file pass without a row | FAIL / WARN |
| oblique | a flat layer (text, card, photo, panel) turned more than 15 deg away from the camera, by its own rx/ry or the camera angle, or bent by a near camera (opposite edges > 1.15x), for >= 0.4 s: PowerPoint 3D. FAIL on the subject and foreground planes (depth < 800, in focus), WARN for far or soft background sheets. Floors, backgrounds, beams, dust and `allow("oblique", why=...)` are skipped | FAIL / WARN |

## Choreography map and motion strips

- `mv.py timeline <dir>` -> `out/timeline.png`: one row per element, green = entrance, blue = later
  actions, grey = ambient, yellow = camera moves, red = holds. A staircase of green bars with no
  blue is a slideshow.
- `mv.py strips <dir> [--at a,b] [--ref <id>]` -> `out/strips.png`: 12 fps, 1 s per row around the
  keyframes. Motion (overlap, easing, hand-offs) is only visible here, not on 0.5 s sheets.
- Then the independent review: `references/critic.md`.

## Your frame review (contact sheets every 0.5 s)

Open every contact sheet image and check, scene by scene:
- Composition: focal point clear, nothing accidentally touching edges, consistent margins.
- Text: no typos vs brief, no orphan words on a line, no broken words, no text over busy areas.
- Hierarchy and order: things appear in the storyboard's order; nothing appears before its
  context.
- Transitions: no empty or doubled frames, direction consistent.
- Style: matches design.yaml (palette, fonts, radius, fx, light). Nothing from `forbidden`.
- Light: you can point at the light source; there is a real dark and a real light; the accent
  is on the thing that matters. A frame that looks like a UI screenshot is a defect, not a style.
- Motion between samples: if two consecutive thumbnails differ wildly where nothing should
  move, render stills at 0.1 s steps there (`mv.py still <dir> <t>`).
- Data: values and labels match the CSV; axis starts at zero for bars; units present.
Write what you found and fixed in one or two lines per issue. Do not deliver a final with a
known bug.

## Re-render loop

Fix -> `mv.py preview` again (it re-runs QA). Previews and finals are incremental: only the 2 s
chunks whose picture changed are rendered again, the rest is reused, and a sound-only change just
re-mixes and re-muxes. So fix and re-run instead of reasoning about whether a re-render is
affordable. For one moment use `mv.py still <dir> <t>` (final quality) or
`mv.py styleframes <dir> --times a,b`.
