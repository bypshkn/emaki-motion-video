# motion-lib: your taste library for Emaki

Optional. Emaki works without it. With it, every video starts from what you already like: the
references you analysed, the techniques you collected, the styles you approved and the engine
extensions that proved useful.

Copy this folder as `motion-lib/` somewhere above your video projects, for example:

```
my-videos/
├── motion-lib/          <- this folder, renamed
└── videos/
    └── 2026-10-10-launch/
```

Emaki finds it by walking up from the project folder (`analyze-ref --id` walks up from the
current folder or the video's folder). You can also put `--lib DIR` before the command
(`mv.py --lib DIR styles`) or set `$MV_LIB`.

## Layout

| path | what |
|---|---|
| `references/INDEX.md` | one row per analysed reference, and what they have in common (your taste so far) |
| `references/<id>/` | `breakdown.md` (timecoded, technique ids), `metrics.json` (motion + sound), `sheet_*.png` every 0.25 s, `spectrogram.png` |
| `techniques.md` | catalogue: technique -> references with timecodes -> engine call -> status |
| `styles/<name>/` | style cards: `design.yaml` (palette, type, motion, dynamics, fx, sound, each with a `why`) + `README.md` |
| `engine_ext/` | engine extensions promoted from projects (`mv.py promote`) |
| `fonts/` | fonts you want in every project |

## Adding a reference

1. Give Claude the video file (links to Instagram or YouTube cannot be downloaded).
2. `mv.py analyze-ref <file> --id rNN-short-name --crop W:H:X:Y --skip s`. For a screen
   recording of a reel, crop to the video first; check one frame before the full run.
3. View every sheet and the spectrogram, fill `breakdown.md`, add new techniques to
   `techniques.md`, add a row to `references/INDEX.md`, and update the "in common" list when
   the new reference changes the picture.
4. If the reference defines a new look, write a style card in `styles/<name>/`.

## Saving what worked

- `mv.py save-style <project> <name>` copies an approved design.yaml into `styles/<name>/`.
- `mv.py promote <project> <module.py>` copies a project's `engine_ext` module into
  `engine_ext/`, so `from module import X` works in every later video.

## Rules

Techniques only: never copy a reference's content, images, logos, characters or copy. Keep the
reference files and sheets private unless you own them: they are someone else's work.
