"""Audio for a Project: voice-over / music track / generative bed + timeline SFX -> stems + mix.

render_audio(P, out_dir) writes music.wav, sfx.wav, (voice.wav), mix.wav (48 kHz / 24-bit
stereo) and returns (paths, report). Loudness: -14 LUFS integrated, true peak <= -1 dBTP unless
design.yaml sound.loudness / sound.true_peak say otherwise.

design.yaml sound keys used here:
  voice: assets/voice.wav        the user's voice-over (any format ffmpeg reads); leads the mix
  voice_offset: 0.0              seconds into the video where the recording starts
  track: assets/music.mp3        the user's licensed music; replaces the synthesized bed
  track_start: 0.0               seconds into the track to start from
  music: true|false              bed on/off;  music_gain_db / sfx_gain_db / voice_gain_db trims
  duck_db: 8                     how far the bed dips under the voice
  bed_eq: true                   clean the bed: high-pass, less sub and mud, a little air
"""
import json
import os

import numpy as np

from .dsp import SR, samples, write_wav, db, filt
from . import music as M
from . import sfx as S
from .master import master, lufs, ffmpeg_loudness


def _fit(x, n, at=0):
    out = np.zeros((n, 2))
    if at < 0:
        x = x[int(-at):]
        at = 0
    m = max(0, min(len(x), n - at))
    out[at:at + m] = x[:m]
    return out


def bed_eq(x):
    """Spectral clean-up for synthesized beds (iteration-2 beds had the sub as the loudest band
    and the mids 14 dB under the references): HPF 32 Hz, -5 dB shelf under 90 Hz, -2 dB at
    300 Hz (mud), +2.5 dB presence at 3.5 kHz, +3 dB air shelf from 9 kHz."""
    y = filt(x, "hp", 32, 0.7)
    y = filt(y, "lowshelf", 90, 0.7, -5.0)
    y = filt(y, "peak", 300, 0.9, -2.0)
    y = filt(y, "peak", 3500, 0.8, 2.5)
    y = filt(y, "highshelf", 9000, 0.7, 3.0)
    return y


def _norm(x, target):
    l = lufs(x) if np.any(x) else -70
    return x * db(target - l) if l > -60 else x


def render_audio(P, out_dir, log=print):
    os.makedirs(out_dir, exist_ok=True)
    snd = P.design.sound or {}
    root = getattr(P, "root", ".")
    target = float(snd.get("loudness", -14.0))
    ceiling = float(snd.get("true_peak", -1.0))
    n = samples(P.duration) + 1
    warns = []
    events = P.all_events()

    voice = None
    if snd.get("voice"):
        from .voice import load
        vp = os.path.join(root, snd["voice"])
        if os.path.exists(vp):
            voice = _fit(load(vp), n, samples(float(snd.get("voice_offset", 0.0))))
            voice = filt(voice, "hp", 80, 0.7)                      # rumble and plosives
            voice = _norm(voice, -16.0 + float(snd.get("voice_gain_db", 0.0)))
        else:
            warns.append(f"voice file not found: {snd['voice']}")

    mus = np.zeros((n, 2))
    genre = None
    if snd.get("track"):
        from .voice import load
        tp = os.path.join(root, snd["track"])
        if os.path.exists(tp):
            tr = load(tp)
            mus = _fit(tr, n, -samples(float(snd.get("track_start", 0.0))))
            fo = samples(1.2)                                       # fade out with the video
            if n > fo:
                mus[-fo:] *= np.linspace(1, 0, fo)[:, None]
            genre = "user track"
        else:
            warns.append(f"music track not found: {snd['track']}")
    elif snd.get("music", True):
        comp = M.Composer(P, warn=warns.append)
        genre = comp.genre
        mus = comp.compose()[:n]
        if len(mus) < n:
            mus = np.pad(mus, ((0, n - len(mus)), (0, 0)))
        if snd.get("bed_eq", True):
            mus = bed_eq(mus)
    if np.any(mus):
        bed_level = -26.0 if voice is not None else -20.0           # a bed sits ~10 dB under a voice
        if snd.get("track") and voice is None:
            bed_level = -16.0                                       # the user's track is the soundtrack
        mus = _norm(mus, bed_level + float(snd.get("music_gain_db", 0.0)))
        if voice is not None:
            from .voice import voice_env
            mus *= voice_env(voice, n, depth_db=float(snd.get("duck_db", 8.0)))[:, None]

    fx = S.render(events, n, gain_db=float(snd.get("sfx_gain_db", 0.0)), warn=warns.append)
    if voice is not None and np.any(fx):
        fx *= db(-4.0)                                              # effects step back behind a voice
    mix = mus + fx + (voice if voice is not None else 0.0)
    # 0.5 dB of headroom: AAC encoding adds inter-sample overshoot, so a WAV mastered to
    # -1.0 dBTP measures about -0.9 dBTP inside the final mp4
    mixed, rep = master(mix, target, ceiling - 0.5)
    g = db(rep["gain_db"])
    paths = {"music": os.path.join(out_dir, "music.wav"), "sfx": os.path.join(out_dir, "sfx.wav"),
             "mix": os.path.join(out_dir, "mix.wav")}
    write_wav(paths["music"], np.clip(mus * g, -1, 1))
    write_wav(paths["sfx"], np.clip(fx * g, -1, 1))
    if voice is not None:
        paths["voice"] = os.path.join(out_dir, "voice.wav")
        write_wav(paths["voice"], np.clip(voice * g, -1, 1))
    write_wav(paths["mix"], mixed)
    chk = ffmpeg_loudness(paths["mix"])
    rep.update({"ffmpeg_I": chk.get("I"), "ffmpeg_TP": chk.get("TP"), "genre": genre, "events": len(events),
                "bpm": P.bpm, "voice": voice is not None, "warnings": warns})
    with open(os.path.join(out_dir, "audio_report.json"), "w") as f:
        json.dump(rep, f, indent=2)
    with open(os.path.join(out_dir, "markers.json"), "w") as f:
        json.dump([{"t": e.t, "kind": e.kind, "accent": e.accent} for e in events], f, indent=1)
    return paths, rep
