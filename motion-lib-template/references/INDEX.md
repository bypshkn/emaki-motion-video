# References

Each folder: `breakdown.md` (what it is, timecoded timeline with technique ids, type, colour,
camera, transitions, sound, take / don't take), `metrics.json` (motion + sound numbers),
`sheet_*.png` (every 0.25 s), `spectrogram.png`. `mv.py analyze-ref --id` creates the folder;
you add the row below after viewing the sheets. Columns: "carried by" is voice-over, music or
both; "frozen / longest still" are `static_pct` and `longest_still_s` from metrics.json; "hit gap"
is `hit_interval_s`; tempo is `sound.tempo_bpm`.

| id | source | length | look | carried by | frozen / longest still | hit gap | tempo | style card |
|---|---|---|---|---|---|---|---|---|

## What they have in common (your taste so far)

Write this list once three or more references are in: what every frame does, how the camera
behaves, how one idea turns into the next, how type and sound behave. Stage 1 of every video
reads it.

## Sound numbers (analyze.py, power share per band, dB)

| id | sub <60 | bass 60-250 | mid 250-2k | presence 2-6k | air >6k | LUFS | LRA | visual hits on a sound onset |
|---|---|---|---|---|---|---|---|---|
