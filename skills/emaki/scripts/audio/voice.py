"""The user's own audio: voice-over and music tracks from assets/.

  load(path)                      -> float stereo 48 kHz array (any format ffmpeg reads)
  speech_segments(x)              -> [(t0, t1)] voiced stretches (pauses >= 0.18 s split them)
  align(path_or_x, text, cues=)   -> [{"word", "t0", "t1"}] word timings for on-screen words
  parse_cues(path)                -> [(t0, t1, text)] from an .srt / .vtt subtitle file
  voice_env(x, depth)             -> gain curve that ducks a music bed under the voice
  track_tempo(path)               -> (bpm, first_beat_s) to set sound.bpm / beat_offset

Word alignment is acoustic only (energy, pauses, syllable onsets; no speech recognition): words
are spread over the voiced stretches in proportion to their syllables, phrase punctuation is
matched to the longest pauses, and every word start is snapped to the nearest syllable onset.
It is good to about one syllable. Always check `out/audio/words.json` against the preview and
correct a time by hand if a word lands early or late (the file is the source of truth once
edited: `align()` keeps an existing file unless `force=True`).
"""
import json
import os
import re
import subprocess

import numpy as np

from .dsp import SR

VOWELS = set("аеєиіїоуюяaeiouy")       # Ukrainian + English vowel letters (syllable nuclei)
PUNCT_PAUSE = {",": 0.5, ";": 0.7, ":": 0.7, "—": 0.7, "-": 0.3, ".": 1.0, "!": 1.0, "?": 1.0, "…": 1.0}


def load(path, sr=SR):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.float32).reshape(-1, 2).astype(np.float64)
    return x


def _mono(x):
    return x.mean(axis=1) if x.ndim == 2 else x


def _env(x, hop=0.01):
    m = _mono(x)
    h = int(SR * hop)
    n = len(m) // h
    e = np.sqrt((m[: n * h].reshape(n, h) ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(e), hop


def _band(x):
    """Speech band (300-3400 Hz): removes sub/bass of a music bed and hiss above."""
    from .dsp import filt
    return filt(filt(_mono(x), "hp", 300), "lp", 3400)


def speech_segments(x, min_pause=0.18, min_len=0.08):
    """Voiced stretches: speech-band frames above an adaptive threshold (between the noise
    floor and the speech level), gaps shorter than min_pause merged."""
    e, hop = _env(_band(x)[:, None])
    e = np.convolve(e, np.ones(3) / 3, "same")
    floor, loud = np.percentile(e, 10), np.percentile(e, 95)
    thr = floor + 0.45 * (loud - floor)
    on = e > thr
    segs = []
    i = 0
    n = len(on)
    while i < n:
        if on[i]:
            j = i
            while j < n and on[j]:
                j += 1
            segs.append([i * hop, j * hop])
            i = j
        else:
            i += 1
    merged = []
    for s in segs:
        if merged and s[0] - merged[-1][1] < min_pause:
            merged[-1][1] = s[1]
        else:
            merged.append(s)
    return [(a, b) for a, b in merged if b - a >= min_len]


def _nuclei(x):
    """Syllable nuclei: peaks of the smoothed speech-band envelope (>= 0.09 s apart, >= 3 dB
    above the dip before them). Returns (peak_times, rise_start_times)."""
    e, hop = _env(_band(x)[:, None])
    e = np.convolve(e, np.hanning(7) / np.hanning(7).sum(), "same")
    floor, loud = np.percentile(e, 10), np.percentile(e, 95)
    gate = floor + 0.35 * (loud - floor)
    pk, rise = [], []
    last_min = 0
    for i in range(1, len(e) - 1):
        if e[i] < e[i - 1] and e[i] <= e[i + 1]:
            last_min = i
        if e[i] > gate and e[i] >= e[i - 1] and e[i] > e[i + 1] and e[i] - e[last_min] >= 3.0:
            if pk and (i - pk[-1]) * hop < 0.09:
                if e[i] > e[pk[-1]]:
                    pk[-1], rise[-1] = i, last_min
                continue
            pk.append(i)
            rise.append(last_min)
    return np.array(pk) * hop, np.array(rise) * hop


def _onsets(x):
    return _nuclei(x)[1]


def _syllables(word):
    w = word.lower()
    n = 0
    prev = False
    for ch in w:
        v = ch in VOWELS
        if v and not prev:
            n += 1
        prev = v
    return max(1, n)


def _tokens(text):
    out = []
    for raw in text.split():
        core = re.sub(r"^[«\"'(\[]+|[»\"')\]]+$", "", raw)
        if not core:
            continue
        p = raw.rstrip("»\"')]")[-1:] if raw else ""
        out.append({"word": raw, "syl": _syllables(core), "pause": PUNCT_PAUSE.get(p, 0.0)})
    return out


def parse_cues(path):
    """Subtitle cues from an .srt or .vtt (CapCut, Premiere, YouTube and phone apps export
    them): [(t0, t1, text)]. Phrase timings from a cue file anchor the word alignment."""
    txt = open(path, encoding="utf-8-sig").read()
    cues = []
    ts = r"(\d+:)?\d{1,2}:\d{2}[,.]\d{1,3}"
    for m in re.finditer(rf"({ts})\s*-->\s*({ts})[^\n]*\n(.*?)(?:\n\s*\n|\Z)", txt, re.S):
        def sec(v):
            v = v.replace(",", ".")
            parts = [float(p) for p in v.split(":")]
            while len(parts) < 3:
                parts.insert(0, 0.0)
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        body = re.sub(r"<[^>]+>", "", m.group(5)).strip().replace("\n", " ")
        if body:
            cues.append((sec(m.group(1)), sec(m.group(3)), body))
    return cues


def align(src, text=None, out_json=None, force=False, offset=0.0, cues=None):
    """Word timings for `text` spoken in `src` (path or array). Returns a list of dicts and
    writes `out_json` when given. An existing out_json is returned as-is unless force=True
    (hand corrections survive re-runs). `cues` (list or .srt/.vtt path) gives phrase timings:
    words are then aligned inside each cue window, which is far more robust than text alone.

    Method: the text becomes a sequence of expected syllables (pauses after punctuation); the
    audio becomes a sequence of detected syllable nuclei. A DTW with skips aligns the two,
    rewarding punctuation that lands on long gaps between nuclei. A word starts at the rise
    before the nucleus matched to its first syllable. Accuracy on the analysed reels (voice over
    a music bed, text only): median 0.3 s, worst about 1 s; always review words.json."""
    if out_json and os.path.exists(out_json) and not force:
        with open(out_json, encoding="utf-8") as f:
            return json.load(f)
    x = load(src) if isinstance(src, str) else src
    pk, rs = _nuclei(x)
    if isinstance(cues, str):
        cues = parse_cues(cues)
    res = []
    if cues:
        for c0, c1, body in cues:
            sel = (pk >= c0 - 0.05) & (pk <= c1 + 0.05)
            part = _align_core(_tokens(body), pk[sel], rs[sel])
            if not part:                                   # no nuclei found: spread evenly
                tk = _tokens(body)
                tot = sum(t["syl"] for t in tk)
                c = 0
                for t in tk:
                    part.append({"word": t["word"], "t0": round(c0 + (c1 - c0) * c / tot, 3),
                                 "t1": round(c0 + (c1 - c0) * (c + t["syl"]) / tot, 3)})
                    c += t["syl"]
            if part:
                part[0]["t0"] = round(max(c0, min(part[0]["t0"], c0 + 0.15)), 3)
                for k in range(1, len(part)):
                    if part[k]["t0"] <= part[k - 1]["t0"]:
                        part[k]["t0"] = round(part[k - 1]["t0"] + 0.06, 3)
                    part[k - 1]["t1"] = round(min(part[k - 1]["t1"], part[k]["t0"]), 3)
            res += part
    else:
        res = _align_core(_tokens(text or ""), pk, rs)
    for w in res:
        w["t0"] = round(w["t0"] + offset, 3)
        w["t1"] = round(w["t1"] + offset, 3)
    if out_json:
        os.makedirs(os.path.dirname(out_json) or ".", exist_ok=True)
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    return res


def _align_core(toks, pk, rs):
    if not toks or len(pk) == 0:
        return []
    syl_word, syl_pause = [], []
    for wi, t in enumerate(toks):
        for k in range(t["syl"]):
            syl_word.append(wi)
            # pause expected BEFORE this syllable (after the previous word's punctuation)
            syl_pause.append(toks[wi - 1]["pause"] if (k == 0 and wi > 0) else 0.0)
    S, K = len(syl_word), len(pk)
    gaps = np.concatenate([[0.0], np.diff(pk)])
    med = float(np.median(gaps[1:])) if K > 1 else 0.2
    INF = 1e18
    D = np.full((S + 1, K + 1), INF)
    B = np.zeros((S + 1, K + 1, 2), int)
    D[0, :] = 0.15 * np.arange(K + 1)          # leading nuclei (breath, music) cost little
    C_SKIP_SYL, C_SKIP_NUC = 0.7, 0.45
    for i in range(1, S + 1):
        p = syl_pause[i - 1]
        for j in range(0, K + 1):
            best, arg = INF, (0, 0)
            if j >= 1 and D[i - 1, j - 1] < INF:
                g = gaps[j - 1] if j - 1 > 0 else 0.0
                long_gap = max(0.0, g - 1.6 * med)
                c = D[i - 1, j - 1]
                if p > 0:
                    c -= 1.2 * p * min(long_gap, 0.5) / 0.5      # punctuation on a pause: reward
                else:
                    c += 0.8 * min(long_gap, 0.6)                # a pause inside a phrase: penalty
                if c < best:
                    best, arg = c, (i - 1, j - 1)
            if j >= 1 and D[i, j - 1] + C_SKIP_NUC < best:       # extra nucleus (noise, music)
                best, arg = D[i, j - 1] + C_SKIP_NUC, (i, j - 1)
            if D[i - 1, j] + C_SKIP_SYL < best:                  # syllable without a nucleus
                best, arg = D[i - 1, j] + C_SKIP_SYL, (i - 1, j)
            D[i, j], B[i, j] = best, arg
    j = int(np.argmin(D[S, :] + 0.15 * (K - np.arange(K + 1))))
    i = S
    match = [None] * S
    while i > 0:
        pi, pj = B[i, j]
        if pi == i - 1 and pj == j - 1:
            match[i - 1] = j - 1
        i, j = pi, pj
    # syllables without a nucleus: interpolate between neighbours
    known = [(k, m) for k, m in enumerate(match) if m is not None]
    t_syl = np.zeros(S)
    if known:
        ks = np.array([k for k, _ in known], float)
        ts = np.array([rs[m] for _, m in known], float)
        t_syl = np.interp(np.arange(S), ks, ts)
    res = []
    for wi, t in enumerate(toks):
        first = syl_word.index(wi)
        last = first + t["syl"] - 1
        t0 = float(t_syl[first])
        m_last = match[last]
        t1 = float(pk[m_last] + 0.12) if m_last is not None else t0 + 0.2 * t["syl"]
        res.append({"word": t["word"], "t0": round(t0, 3), "t1": round(max(t1, t0 + 0.08), 3)})
    for k in range(len(res) - 1):
        if res[k + 1]["t0"] < res[k]["t0"]:
            res[k + 1]["t0"] = res[k]["t0"] + 0.05
        res[k]["t1"] = min(res[k]["t1"], max(res[k + 1]["t0"], res[k]["t0"] + 0.05))
    return res


def voice_env(x, n=None, depth_db=9.0, attack=0.06, release=0.35):
    """Gain curve for the music bed: down by depth_db while the voice speaks, smooth attack and
    release so the bed breathes between phrases instead of pumping."""
    n = n or len(x)
    segs = speech_segments(x)
    g = np.ones(n)
    lo = 10 ** (-depth_db / 20)
    for a, b in segs:
        s0, s1 = int((a - attack) * SR), int((b + release) * SR)
        g[max(0, s0):min(n, s1)] = lo
    k = int(SR * 0.08)
    if k > 1:
        g = np.convolve(g, np.ones(k) / k, "same")
    return g


def track_tempo(path):
    """Tempo and first beat of the user's music track (onset autocorrelation + DP beats)."""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import analyze
    sr = 22050
    x = analyze._audio(path, sr)
    env, _, dt = analyze._onset_env(x, sr)
    bpm, beats = analyze._tempo_beats(env, dt)
    return bpm, (float(beats[0]) if len(beats) else 0.0)
