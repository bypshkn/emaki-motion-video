# After Effects backend (output = ae)

`mv.py ae <dir> [--version 24.0]` turns the same timeline and design.yaml into
`out/ae/build_project.jsx` + `Audio/` (music, sfx, mix stems) + `Assets/` (images, baked clips)
+ `README.md`. The user runs it in AE: File > Scripts > Run Script File.

## Project structure

Folders Comps / Precomps / Audio / Assets; main comp (CONTROLS null on top, scene precomps in
order, transitions as native keys/effects, global fx as adjustment layers, music and sfx stems,
a marker for every sound event); one precomp per scene; one precomp per Group (collapsed when it
has no effects). Layers are named after the engine layer names, colour-labelled by type
(text yellow, shape blue, solid brown, precomp sandstone, fx lavender, controls red, audio
peach, camera pink, baked orange).

## Mapping

| engine | After Effects |
|---|---|
| keyframes + bezier easing | native keys; temporal ease speed/influence computed from the same cubic-bezier |
| spring / elastic / bounce / steps | linear keys + expression that applies the same curve between them |
| Wiggle | `wiggle(f, a)` expression |
| Text | point text, same line breaks, tracking, leading, justification; font by PostScript name |
| text reveals (all modes) | text animators with Expression Selectors reproducing per-unit timing and ease |
| typewriter / scramble | expression selectors (+ Character Offset for scramble), caret = shape layer with hold keys |
| `*accent*` spans | Fill Color animator with index range selector, linked to CONTROLS Accent Color |
| Counter | Source Text expression (same ease and number format) |
| Rect / Ellipse / Polygon / Star / Path / Line / Morph / Arc | shape layer: rect/ellipse/polystar/path, trim paths, fill/stroke, path keys |
| Linear / Radial fill | solid + Gradient Ramp, matted by the shape (2 colours) |
| Background | solid (+ Gradient Ramp) |
| clip | layer mask with animated path |
| matte | track matte (`setTrackMatte` on AE 23+, layer above on older) |
| Blur / DropShadow / Glow | Gaussian Blur / Drop Shadow / Glow |
| camera + depth | AE camera; layers 3D with z = depth; zoom via a slider so the projection matches |
| transitions | fade/push/slide/zoom/blur: keys on scene layers; wipe: Linear Wipe; iris: mask; dip: solid; shape wipe: shape layer |
| grain / vignette / bloom / scanlines / grade | Noise / CC Vignette / Glow / shape repeater / Hue-Sat + Brightness-Contrast, scaled by CONTROLS FX Intensity |
| motion blur | layer + comp motion blur switches, shutter angle |
| layer rx / ry (3D tilt) | 3D layer X / Y Rotation keys [UNVERIFIED sign] |
| camera drift / punch / push / tilt | camera X/Y keys + drift expressions; zoom slider (+ punch expression); orbit via Tilt X / Tilt Y sliders on the CAMERA ZOOM null |
| smear | Directional Blur driven by `transform.position.velocity` |
| whip / flash / scale-through transitions | position keys + Directional Blur keys / white solid flash + cut / scale keys + cut |
| KineticWords, Flash | precomp of text layers and colour solids |

## Baked (ProRes 4444 with alpha, label [BAKED])

Particles, noise/pattern/conic fills, outline-draw, written (`write_on`) and gradient text,
DynamicText without `ae_expr`, Comet, GridPlane, Wire3D, Waveform, glitch pulses and glitch
transitions (full-frame clip over the window). Bakes render without supersampling, are cached
between calls, and `mv.py ae` exits with code 3 (PARTIAL) when a call runs out of time: run it
again. Echo trails are not exported (AE Echo works on pixels, not on transforms).
Chromatic aberration as a global effect is not exported (listed in README).

## CONTROLS null

Speed (time-remaps every scene precomp), FX Intensity, Accent Color, Text Scale.

## Versions

Target from brief `ae_version` (default 24.0). Version-gated APIs: `setTrackMatte` (23.0+),
`app.fonts` font check (24.0+). Text per-range fonts (bold spans) need 24.3+ and are left
regular with a note.

## Verification

1. Always: `validate.js` runs the script in Node against a mock of the AE object model (part of
   `mv.py ae`): every property path, value shape, keyframe/ease range, referenced file, and every
   expression is compiled and evaluated at sample times. It cannot prove real AE behaviour; the
   matchName list in the mock is maintained by hand.
2. If `aerender` exists on the machine: render the main comp and run the normal QA on it.
3. Otherwise tell the user plainly: the .jsx was not checked in After Effects; compare the main
   comp with out/preview.mp4.

Known [UNVERIFIED] spots to check first in AE: Linear Wipe angle direction, Drop Shadow opacity
scale, ease arrays on colour properties, text animator anchor grouping, pointOnPath sampling.
