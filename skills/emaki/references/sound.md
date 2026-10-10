# Sound design

Decide first what carries the edit. In order of quality:
1. **The user's voice-over** (`sound.voice: assets/voice.wav`): what 3 of 4 analysed reference
   reels do. Words on screen are the spoken words, timed to the voice. A soft bed sits under it.
2. **The user's licensed music track** (`sound.track: assets/music.mp3`): real production
   quality. The picture follows its beats (`mv.py beats <file>` -> `sound.bpm`, `beat_offset`).
3. **A synthesized bed** (`audio/music.py`): always available, never as good as 1-2. Say so,
   and say it has not been heard (you cannot listen).
Never stock music, never generated voices; only code and the user's files.

`mv.py preview/final` renders the audio automatically (`audio/`), writes stems and the master.

## Pipeline

1. **Voice** (`audio/voice.py`): loaded from `sound.voice` at `voice_offset`, high-passed at
   80 Hz, normalised to lead the mix. `mv.py voice <dir>` writes `data/words.json` (word start
   and end times) from the brief texts, or from `--cues subtitles.srt` when the user has
   subtitles (CapCut, Premiere and phone apps export them; far more robust). Acoustic alignment
   only: median error ~0.3 s on voice over music, better on a clean recording. Review in the
   preview; hand edits in words.json survive re-runs.
2. **Music**: the user's `sound.track` (from `track_start`, faded out with the video) or the
   synthesized bed from design.yaml `sound` + scene energies. Bars follow `P.bpm` and
   `P.beat_offset`. The bed is cleaned by `bed_eq` (high-pass, less sub and mud, a little
   presence and air) unless `sound.bed_eq: false`.
   Finer control: `sound.layers: {bass: -4}` trims a layer in dB, `sound.low_cut_hz: 45`
   high-passes bass and drums when the sub still reads heavy (QA `spectrum` line, r03 sub -14 dB).
3. **Ducking**: under a voice the bed sits ~10 dB lower and dips another `duck_db` (default 8)
   while the voice speaks, with slow attack/release so it breathes between phrases.
4. **SFX** (`audio/sfx.py`): timeline events at their frame, aligned to their perceptual hit,
   through `sfx_eq` (no sub flood). Under a voice they step back 4 dB.
5. **Mix and master** (`audio/master.py`): EBU R128 to `sound.loudness` (default -14 LUFS),
   true-peak limiter at `sound.true_peak` (default -1 dBTP), checked with ffmpeg ebur128.
6. **Outputs**: out/audio/voice.wav (if any), music.wav, sfx.wav (stems at master gain),
   mix.wav, markers.json, audio_report.json.

## Spectral balance (what "modern, not dated" means in numbers)

Power share per band of the mix, measured on the four reference reels (motion.md, top):

| band | references | our iteration-2 beds | after the 2026-10-08 fix |
|---|---|---|---|
| sub < 60 Hz | -6 .. -37 dB | -3 dB (the loudest band: muddy) | -8 dB |
| bass 60-250 Hz | -2 .. -11 | -3 | -2 |
| mids 250 Hz-2 kHz | -2 .. -5 | -16 .. -19 (hollow) | -7 |
| presence 2-6 kHz | -15 .. -18 | -24 .. -27 (dull) | -17 |
| air > 6 kHz | -17 .. -24 | -28 | -20 |

QA `spectrum` warns when the sub goes above -6 dB, the mids below -12 dB or presence below -24 dB.
`mv.py analyze-ref` measures the same bands for any reference.

## Genres for the synthesized bed (sound.genre keywords)

| genre | instruments | drums | use for |
|---|---|---|---|
| minimal | detuned pad, sub, pluck arps, air | half-time soft kick, offbeat hats from energy 0.5 | tech, data, product, under a voice |
| ambient | warm pad, sub drone, sparse bells, air | none | calm, premium, dark gradient looks |
| electronic | saw pad, synth bass, arp synth | house kick/clap/hats | launches, energy |
| cinematic | strings, piano, sub | toms from 0.55, risers + impacts on accents | trailers, big reveals |
| lofi | e-piano comping, sub, crackle | swung boom-bap | casual, lifestyle |
| corporate | warm pad, plucks, synth bass, motif | pop beat | explainers, B2B |
| playful | marimba, pluck bass, motif | claps, shakers | kids, consumer apps |
| piano | felt piano, warm pad, sparse melody | none | editorial, stories |
| terminal | sine drone at A1, 880 Hz shimmer | none | AI/system voice |

`timbres` keywords override instruments ("felt piano", "rhodes", "bell", "marimba", "pluck",
"strings", "warm pad", "sub", "synth bass", "arp"). `progression: [i, VI, III, VII]` overrides
chords. `music: false` = SFX only. `music_gain_db`, `sfx_gain_db`, `voice_gain_db` trim.
Sidechain pumping is kept light (it dates a track fast); the bed no longer stamps a crash and a
kick on every accent.

## Energy and arrangement

`scene.energy` 0..1: < 0.35 pad and bass only; 0.35-0.5 adds arps/keys; >= 0.5 adds the pulse;
>= 0.65 adds claps/denser arps. Shape the energy curve like a story: intro 0.3, build 0.5-0.6,
peak 0.8-1.0 on the key message, outro 0.3-0.4.

## Sync rules

- With a voice: words and cuts follow the voice (data/words.json); big moves land on phrase
  ends. With music: scene boundaries on bar lines, accents (`accent=True`) on beats; QA fails
  accents more than one frame off the grid.
- Sound follows the pulse, not every event. References put a sound under 20-55 % of their visual
  hits. SFX on transitions, the hook, the payoff and one or two key moments; type clicks and
  counter ticks stay quiet. QA `sound` warns above `sound.max_sfx_per_s` (default 1.0).
- A modern palette for SFX: soft swishes for camera travel, short airy risers into a payoff, a
  deep but short sub boom for one big transformation, glassy ticks for small dots. Avoid stacked
  impacts, crashes and laser blips.

## Limits

The synthesis is deliberately simple and cannot be judged from numbers. Listen to the preview
before the final, and tell the user plainly when you could not listen. For anything that
matters, ask for the user's voice-over or a licensed track.
