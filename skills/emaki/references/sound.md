# Sound design

Decide first what carries the edit, and whether the film needs a voice to be understood (promos
and explainers usually do: first-time viewers of a silent explainer could not say what it was
about; ask at stage 0). The voice, in order of quality:
1. **The user's voice-over** (`sound.voice: assets/voice.wav`): what 3 of 4 analysed reference
   reels do. Words on screen are the spoken words, timed to the voice. A soft bed sits under it.
2. **A generated library voice** (brief `voice: tts`, `mv.py tts`, section below): Google Cloud
   Text-to-Speech, Chirp 3 HD voices only, with the user's own API key. Quality differs between
   languages and voices: in testing English was good and Ukrainian sounded robotic, so outside
   English offer the user's recording first, and the user listens before committing.
The music: the user's licensed track (`sound.track: assets/music.mp3`, the picture follows its
beats: `mv.py beats <file>` -> `sound.bpm`, `beat_offset`), a licensed stock track
(licensing.md), or a synthesized bed (`audio/music.py`): always available, never as good. Say
so, and say it has not been heard (you cannot listen). No other generated sound or voice.

`mv.py preview/final` renders the audio automatically (`audio/`), writes stems and the master.

## Pipeline

1. **Voice** (`audio/voice.py`): loaded from `sound.voice` at `voice_offset`, high-passed at
   80 Hz, normalised to lead the mix. A generated voice gets its words from `mv.py tts`; for the
   user's recording `mv.py voice <dir>` writes `data/words.json` (word start
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

## Generated voice (`voice: tts`)

Google Cloud Text-to-Speech, Chirp 3 HD library voices (`audio/tts.py`). Google's free tier
covers the first 1M characters a month, then US$30 per 1M (checked 2026-11-19; a 60 s film is
about 1,000 characters). 30 voices, the same names in every supported language (50+ locales,
English and Ukrainian among them).

**The user picks the voice.** There is no default: point the user to Google's list with a sample
of every voice (https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd) and write the name
they choose to brief.yaml `tts_voice` (e.g. `Kore`). `$MV tts` stops until a voice is set.
Trying another voice costs only the script's characters again; the old takes are kept, so
going back is free. For a language other than en or uk, set `tts_lang` to its locale (`de-DE`).

**Setup, once** (the user does it in the Google Cloud console; the skill never logs in):
1. A Google Cloud project with the Cloud Text-to-Speech API enabled.
2. A billing account with a card: Google requires billing even for the free tier and charges
   automatically above it.
3. A budget on the project (e.g. $1) with email alerts at 50, 90 and 100 %. A budget only sends
   emails, it does not stop charges: the skill's own monthly counter is what stops a run.
4. An API key restricted to the Cloud Text-to-Speech API, saved as one line in
   `secrets/google-tts-key.txt` in a folder above the projects (or `$MV_TTS_SECRETS` pointing at
   its folder). Keep `secrets/` out of git and out of shared folders.

1. **Script first** (stage 1): brief.yaml `voice_script`, one item per phrase, `at` = the second
   where the speech starts, on the beat list. `text` is the line, `say` how it is spoken when it
   differs. What the ear test showed: spell letters with hyphens ("A-C-H"), use an ellipsis for
   a longer pause ("Paste the request... the app builds the work order."); for "48 hours" the
   take read from digits beat the one from "forty-eight". SSML, pause tags, IPA pronunciations and a whole-script take were tried and all
   lost to plain text, so only plain text is sent. Pace: `tts_rate` 1.0; in testing the
   approved two-sentence lines ran at 0.92 (`rate` per phrase). Lines we wrote are `[DEMO COPY]` and go to
   `licenses/copy-for-approval.md`.
2. `$MV tts <dir> --dry-run` shows what will be sent and the characters; `$MV tts <dir>` sends
   only the phrases with no take yet, then writes `assets/voice.wav` (each phrase trimmed of
   Google's silence and breath, levelled, placed at its `at`), `data/words.json` (the aligner
   per phrase: every phrase start is exact) and `data/voice_phrases.json` (times, syllables
   per second, takes). It points design.yaml `sound.voice` at `assets/voice.wav` and adds the
   ledger row (`license: google-tts`).
3. **Takes.** A request usually gives a different take (the same line came back 1.12 s and
   1.52 s long), but a retake can also come back byte-identical to an earlier one: `tts.py`
   does not save it and says so; an ellipsis or a comma in `say` gets a really new take. The
   user approves takes by ear; you cannot. Takes live in `data/voice_takes/` and are
   never requested again. `--retake 3` asks for a new take of phrase 3 and writes
   `out/audio/takes_p3.wav` with every take in a row; `--take 3=1` goes back. A changed `say`,
   voice or pace is a new phrase: it needs a new take and a new listen.
4. QA `voice`: the voice matches the current script, the mix uses it, no phrase runs into the
   next one, past its scene or past the end, speech rate per phrase (WARN above 7.5 syllables/s;
   the fastest approved line ran 6.6), takes Google clipped, the monthly counter.

Rights (terms read 2026-10-19, licensing.md): the audio is ours to use in client films and ads,
no credit to Google. Not in a film for children or teenagers, never passed off as a real person,
not in unsolicited mass mailings, never used to train another voice. The voice is not exclusive
and Google gives no indemnity for it: say so in the rights pack (the ledger row does).

Limits and safety: Chirp 3 HD returns no word times and has no custom pronunciations for
`uk-UA`. Gemini-TTS has no free tier: `tts.py` sends Chirp 3 HD only and refuses every other
model. Characters per calendar month are counted in `secrets/tts-usage.json`; a run above 900,000
is refused; the counter sees only this skill's requests, not other use of the same billing
account. The key is read only from `secrets/google-tts-key.txt` (`$MV_TTS_SECRETS`, else the
first `secrets/` walking up from the project, never above the home folder) and sent as a header
through curl's stdin: never print it, never copy it into a project, a log, the skill or a git
repository. On a restricted network (a sandbox, a proxy, an allowlist)
`texttospeech.googleapis.com` must be allowed.

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
- Sounds of the film's world beat abstract ones: one product film used a car passing and a soft
  dash chime on its key moments and it fit; a beep under every event read as a toy. Keep a
  designed sound track; drop the generic UI clicks. Recorded or library sounds from the user
  (assets/sfx/) are welcome.

## Limits

The synthesis is deliberately simple and cannot be judged from numbers. Listen to the preview
before the final, and tell the user plainly when you could not listen. For anything that
matters, ask for the user's voice-over or a licensed track. A generated voice is the same:
numbers show its timing, not whether it sounds right; the user approves every take by ear.
