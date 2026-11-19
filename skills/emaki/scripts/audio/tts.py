"""Generated voice-over: Google Cloud Text-to-Speech, Chirp 3 HD library voices only.

  plan(root)                         -> phrases of the voice-over script with their take keys
  build(root, ...)                   -> requests what is missing, writes assets/voice.wav,
                                        data/words.json, data/voice_phrases.json; returns the report
  usage(root)                        -> (characters sent this month, monthly limit)

The script is brief.yaml `voice_script` (or data/vo_script.md). Each phrase is one request.
Each take comes back with its own silence and level: the edges are trimmed, every phrase is
brought to the same loudness, and the phrase is placed on the film's timeline at its `at`
(the moment the speech starts) or after the previous one. The aligner (voice.align) then runs
on each clean phrase, so every phrase start in data/words.json is exact.

Takes. Chirp 3 HD is not deterministic: the same text, voice and pace usually give a different
take (measured 2026-10-19: one line came back 1.12 s and 1.52 s long), but a retake can also
return a take it gave before, byte for byte; such a duplicate is not saved. The user approves
a take by ear, so every take is kept in data/voice_takes/ and re-runs reuse it. A new take is
requested only for a new phrase (other text, voice or pace) or on `retake`.

Voice and language: the user picks the voice by ear (brief.yaml `tts_voice`, a Chirp 3 HD
name such as Kore or Charon); there is no default voice. The locale comes from `tts_lang`, else
from `language` (en -> en-US, uk -> uk-UA); any other language needs `tts_lang`.

Cost and safety:
  - the user's own Google Cloud API key; nothing is sent without it;
  - only Chirp 3 HD voices (Google's free tier covers the first 1M characters a month; checked
    2026-11-19). Gemini-TTS and the other models are refused: they have no free tier;
  - characters sent per calendar month are counted in secrets/tts-usage.json; a run that would
    pass 900,000 is refused before anything is sent. The counter sees only this skill's
    requests, not other use of the same Google billing account;
  - the key is read only from secrets/google-tts-key.txt ($MV_TTS_SECRETS, else the first
    `secrets/` folder walking up from the project, never above the home folder) and goes to
    curl as the X-Goog-Api-Key header through stdin: never in argv, a URL, a log or a project
    file.

Script text: write it the way it is spoken (`say`), keep the screen words in `text`. What
worked in testing: letters spelled with hyphens ("A-C-H"), an ellipsis for a longer pause
("Paste the request... the app builds the work order."). SSML, pause tags and IPA
pronunciations were tried and lost, so only plain text is sent.
"""
import base64
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import wave

import numpy as np

from .dsp import SR, write_wav

ENDPOINT = "https://texttospeech.googleapis.com/v1/text:synthesize"
MONTH_LIMIT = 900_000
KEY_NAME = "google-tts-key.txt"
USAGE_NAME = "tts-usage.json"
LANG_CODES = {"en": "en-US", "uk": "uk-UA"}
_LANG_ALIASES = {"ua": "uk", "ukr": "uk", "ukrainian": "uk", "eng": "en", "english": "en"}
VOICE_LIST = "https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd"   # voices with samples, locales
SECRETS_MAX_UP_OUTSIDE_HOME = 2   # like motion-lib: outside home, the project and two levels above
KEY_RE = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
PAD_IN, PAD_OUT = 0.03, 0.12      # silence kept before and after the speech of a phrase
FADE_IN, FADE_OUT = 0.005, 0.03
PHRASE_LUFS = -20.0               # every phrase at the same loudness; the mix sets the final level
PEAK_CEILING_DB = -1.0
MIN_GAP = 0.15                    # phrases never closer than this
TAKES_DIR = os.path.join("data", "voice_takes")


class TTSError(RuntimeError):
    pass


# ----------------------------------------------------------------------------- secrets and usage

def find_secrets(start):
    """The folder with google-tts-key.txt: $MV_TTS_SECRETS, else the first secrets/ walking up
    from the project folder. The walk never leaves the home folder (it checks home itself last);
    for a project outside home it checks only the project folder and two levels above it, so a
    key in a folder the user does not own is never picked up."""
    env = os.environ.get("MV_TTS_SECRETS")
    if env:
        return os.path.abspath(env)
    d = os.path.realpath(start)
    home = os.path.realpath(os.path.expanduser("~"))
    inside_home = d == home or d.startswith(home.rstrip(os.sep) + os.sep)
    up = 0
    while True:
        cand = os.path.join(d, "secrets")
        if os.path.isfile(os.path.join(cand, KEY_NAME)):
            return cand
        nd = os.path.dirname(d)
        if nd == d or d == home or (not inside_home and up >= SECRETS_MAX_UP_OUTSIDE_HOME):
            return None
        d = nd
        up += 1


def _month():
    return datetime.date.today().strftime("%Y-%m")


def _load_usage(sdir):
    p = os.path.join(sdir, USAGE_NAME)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            u = json.load(f)
        if not isinstance(u, dict) or not all(isinstance(v, dict) and isinstance(v.get("chars", 0), int)
                                              for v in u.values()):
            raise ValueError("unexpected structure")
        return u
    except (OSError, ValueError) as e:
        raise TTSError(f"{USAGE_NAME} in {sdir} could not be read ({e}). It is the monthly character "
                       "counter: fix it by hand rather than delete it, or the limit starts again from 0")


def _add_usage(sdir, chars):
    u = _load_usage(sdir)
    m = u.setdefault(_month(), {"chars": 0, "requests": 0})
    m["chars"] += int(chars)
    m["requests"] += 1
    p = os.path.join(sdir, USAGE_NAME)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(u, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)
    return m["chars"]


def usage(root):
    """(characters sent this calendar month, MONTH_LIMIT); (None, limit) without a secrets/ folder."""
    sdir = find_secrets(root)
    if not sdir:
        return None, MONTH_LIMIT
    return _load_usage(sdir).get(_month(), {}).get("chars", 0), MONTH_LIMIT


def _read_key(sdir):
    with open(os.path.join(sdir, KEY_NAME), encoding="utf-8") as f:
        key = f.read().strip()
    if not KEY_RE.fullmatch(key):
        raise TTSError(f"{KEY_NAME} does not look like a Google API key (one line, 39 characters, "
                       "starting with AIza)")
    return key


# ----------------------------------------------------------------------------- script

def _brief(root):
    p = os.path.join(root, "brief.yaml")
    if not os.path.exists(p):
        return {}
    import yaml
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def lang_code(brief):
    """Locale of the voice: brief.yaml `tts_lang` (any Chirp 3 HD locale, e.g. de-DE), else from
    `language` (default en): en -> en-US, uk -> uk-UA."""
    lc = str(brief.get("tts_lang") or "").strip()
    if lc:
        return lc
    lang = str(brief.get("language") or "en").strip().lower()
    lang = _LANG_ALIASES.get(lang, lang)[:2]
    if lang not in LANG_CODES:
        raise TTSError(f"brief language '{lang}': set brief.yaml `tts_lang` to its Chirp 3 HD locale "
                       f"(e.g. de-DE, fr-FR, es-ES; the list is at {VOICE_LIST})")
    return LANG_CODES[lang]


def voice_name(lang, voice):
    """'Kore' -> 'en-US-Chirp3-HD-Kore'. The user picks the voice (brief.yaml `tts_voice`); there
    is no default. Anything but a Chirp 3 HD voice is refused."""
    v = str(voice or "").strip()
    if not v:
        raise TTSError(f"no voice chosen: listen to the Chirp 3 HD voices at {VOICE_LIST} and write "
                       "the one you like to brief.yaml `tts_voice` (a name such as Kore or Charon)")
    if "-" not in v:
        v = f"{lang}-Chirp3-HD-{v}"
    if "-Chirp3-HD-" not in v:
        raise TTSError(f"voice '{v}' is not a Chirp 3 HD voice. Emaki calls Chirp 3 HD only (free up to 1M "
                       "characters a month); Gemini-TTS has no free tier and the other models are never called")
    if not v.startswith(lang + "-"):
        raise TTSError(f"voice '{v}' does not match the language {lang} (brief language / tts_lang)")
    return v


def _parse_md(path):
    """data/vo_script.md: one phrase per '- ' line, optional fields after ' | ':
    - Sign in with SSO. Your team is ready. | say=Sign in with S-S-O. Your team is ready. | rate=0.92 | at=31.5"""
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("- "):
                continue
            parts = [p.strip() for p in line[2:].split(" | ")]
            ph = {"text": parts[0]}
            for p in parts[1:]:
                k, _, v = p.partition("=")
                ph[k.strip()] = v.strip()
            out.append(ph)
    return out


def _norm(s):
    return " ".join(re.sub(r"[«»\"“”]", "", str(s)).replace("—", "-").split()).lower()


def plan(root):
    """The script as a list of phrases: {n, text, say, rate, at, gap, take, key, voice, lang, chars,
    from_brief}. No network. Raises TTSError on a broken script."""
    brief = _brief(root)
    raw = brief.get("voice_script")
    if not raw:
        md = os.path.join(root, "data", "vo_script.md")
        raw = _parse_md(md) if os.path.exists(md) else []
    if not raw:
        raise TTSError("no voice-over script: add brief.yaml `voice_script` (one phrase per item) "
                       "or data/vo_script.md")
    lang = lang_code(brief)
    vname = voice_name(lang, brief.get("tts_voice"))
    base_rate = float(brief.get("tts_rate", 1.0))
    texts = [_norm(t) for t in (brief.get("texts") or [])]
    out = []
    for n, ph in enumerate(raw, 1):
        ph = {"text": ph} if isinstance(ph, str) else dict(ph or {})
        text = str(ph.get("text") or "").strip()
        if not text:
            raise TTSError(f"voice_script phrase {n} has no text")
        say = str(ph.get("say") or text).strip()
        rate = float(ph.get("rate", base_rate))
        if not 0.25 <= rate <= 2.0:
            raise TTSError(f"phrase {n}: rate {rate} is outside 0.25-2.0")
        at = ph.get("at")
        h = hashlib.sha1(json.dumps([vname, lang, round(rate, 3), say, SR], ensure_ascii=False).encode("utf-8"))
        out.append({"n": n, "text": text, "say": say, "rate": round(rate, 3),
                    "at": None if at in (None, "") else float(at),
                    "gap": float(ph.get("gap", brief.get("tts_gap", 0.6))),
                    "take": None if ph.get("take") in (None, "") else int(ph["take"]),
                    "key": h.hexdigest()[:12], "voice": vname, "lang": lang, "chars": len(say),
                    "from_brief": any(_norm(text) in t for t in texts if t)})
    return out


# ----------------------------------------------------------------------------- takes

def _takes_dir(root):
    return os.path.join(root, TAKES_DIR)


def takes(root, key):
    """Take files of one phrase key, oldest first."""
    d = _takes_dir(root)
    if not os.path.isdir(d):
        return []
    found = []
    for f in os.listdir(d):
        m = re.fullmatch(re.escape(key) + r"-t(\d+)\.wav", f)
        if m:
            found.append((int(m.group(1)), os.path.join(d, f)))
    return [p for _, p in sorted(found)]


def _chosen(root):
    p = os.path.join(_takes_dir(root), "chosen.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _set_chosen(root, key, take):
    c = _chosen(root)
    c[key] = int(take)
    os.makedirs(_takes_dir(root), exist_ok=True)
    with open(os.path.join(_takes_dir(root), "chosen.json"), "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1)


def chosen_take(root, ph):
    """1-based take number used for a phrase: brief `take`, else chosen.json, else the first."""
    n = len(takes(root, ph["key"]))
    t = ph.get("take") or _chosen(root).get(ph["key"]) or 1
    return min(max(1, int(t)), n) if n else None


def select_take(root, ph, take):
    n = len(takes(root, ph["key"]))
    if not 1 <= take <= n:
        raise TTSError(f"phrase {ph['n']} has {n} take(s), not {take}")
    _set_chosen(root, ph["key"], take)


# ----------------------------------------------------------------------------- request

def _post(key, body):
    """One text:synthesize request -> mono int16 PCM bytes. The key reaches curl through stdin
    and is redacted from every message."""
    config = (f'header = "X-Goog-Api-Key: {key}"\n'
              'header = "Content-Type: application/json; charset=utf-8"\n')
    fd, body_path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False)
        p = subprocess.run(["curl", "-sS", "-m", "60", "-X", "POST", "--config", "-",
                            "--data-binary", f"@{body_path}", "-w", "\n%{http_code}", ENDPOINT],
                           input=config.encode("utf-8"), capture_output=True)
    except FileNotFoundError:
        raise TTSError("curl not found: the generated voice needs curl (install it, then run again)")
    finally:
        os.unlink(body_path)
    out = p.stdout.decode("utf-8", errors="replace").replace(key, "<KEY>")
    err = p.stderr.decode("utf-8", errors="replace").replace(key, "<KEY>")
    if p.returncode != 0:
        raise TTSError(f"curl failed ({p.returncode}): {err.strip()[:300]}. If the network is restricted "
                       "(a sandbox, a proxy, an allowlist), allow texttospeech.googleapis.com and run again")
    payload, _, code = out.rpartition("\n")
    if code.strip() != "200":
        raise TTSError(f"Google TTS answered HTTP {code.strip()}: {payload.strip()[:400]}")
    try:
        audio = base64.b64decode(json.loads(payload)["audioContent"])
    except (ValueError, KeyError, TypeError):
        raise TTSError(f"Google TTS answered without audio: {payload.strip()[:300]}")
    if audio[:4] == b"RIFF":
        with wave.open(io.BytesIO(audio)) as w:
            if w.getsampwidth() != 2 or w.getnchannels() != 1 or w.getframerate() != SR:
                raise TTSError(f"unexpected audio: {w.getnchannels()} ch, {w.getsampwidth() * 8} bit, {w.getframerate()} Hz")
            return w.readframes(w.getnframes())
    return audio


def _body(ph):
    return {"input": {"text": ph["say"]},
            "voice": {"languageCode": ph["lang"], "name": ph["voice"]},
            "audioConfig": {"audioEncoding": "LINEAR16", "sampleRateHertz": SR, "speakingRate": ph["rate"]}}


def _same_take(root, key, pcm):
    """Number of an existing take that is byte-identical to pcm, else None. Google sometimes
    answers a repeated request with the take it gave before (2026-10-19: a retake came back
    identical to take 1)."""
    for n, p in enumerate(takes(root, key), 1):
        with wave.open(p) as w:
            if w.getnframes() * 2 == len(pcm) and w.readframes(w.getnframes()) == pcm:
                return n
    return None


def _write_take(root, key, pcm):
    os.makedirs(_takes_dir(root), exist_ok=True)
    n = len(takes(root, key)) + 1
    p = os.path.join(_takes_dir(root), f"{key}-t{n}.wav")
    with wave.open(p, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return n


def _read_take(path):
    with wave.open(path) as w:
        pcm = w.readframes(w.getnframes())
    i = np.frombuffer(pcm, np.int16)
    return i.astype(np.float64) / 32768.0, int(np.sum((i >= 32767) | (i <= -32768)))


# ----------------------------------------------------------------------------- clean-up

START_DB, END_DB = -30.0, -38.0   # speech vs the loudest 10 ms frame of the take


def _speech_bounds(x):
    """(first, last) sample of the speech in 10 ms frames. Google starts many takes with up to
    0.6 s of a quiet breath about 40 dB under the speech (measured on 35 takes, 2026-10-19), so the
    start needs a frame within 30 dB of the loudest one; the end keeps decays down to -38 dB."""
    h = int(SR * 0.01)
    n = len(x) // h
    if n == 0:
        return 0, len(x)
    e = 20 * np.log10(np.sqrt((x[: n * h].reshape(n, h) ** 2).mean(axis=1)) + 1e-9)
    top = e.max()
    on = np.where(e > max(top + START_DB, -70.0))[0]
    tail = np.where(e > max(top + END_DB, -70.0))[0]
    if len(on) == 0:
        return 0, len(x)
    return on[0] * h, min(len(x), (tail[-1] + 1) * h)


def clean(x):
    """Trim the take to PAD_IN / PAD_OUT around the speech, short fades, level it to PHRASE_LUFS
    (peaks under PEAK_CEILING_DB). Returns (clip, speech_len_s, lufs_google, gain_db)."""
    from .master import lufs
    a, b = _speech_bounds(x)
    s0, s1 = max(0, a - int(PAD_IN * SR)), min(len(x), b + int(PAD_OUT * SR))
    y = x[s0:s1].copy()
    pad = int(PAD_IN * SR) - (a - s0)          # Google gave less lead than PAD_IN: add silence
    if pad > 0:
        y = np.concatenate([np.zeros(pad), y])
    fi, fo = int(FADE_IN * SR), int(FADE_OUT * SR)
    y[:fi] *= np.linspace(0, 1, fi)
    y[-fo:] *= np.linspace(1, 0, fo)
    before = float(lufs(np.stack([y, y], axis=1)))
    peak = 20 * np.log10(np.abs(y).max() + 1e-12)
    gain = min(PHRASE_LUFS - before, PEAK_CEILING_DB - peak)
    return y * 10 ** (gain / 20), (b - a) / SR, round(before, 1), round(gain, 1)


# ----------------------------------------------------------------------------- words

def _phrase_words(clip, ph, start):
    """Aligner on one clean phrase; words of `say` mapped back to the screen words of `text`
    when both have the same number of words ("A-C-H" -> "ACH")."""
    from .voice import align
    ws = align(clip, ph["say"])
    shown = ph["text"].split()
    mapped = len(shown) == len(ws)
    out = []
    onset = start + PAD_IN
    end = start + len(clip) / SR - PAD_OUT + 0.05
    for k, w in enumerate(ws):
        t0 = onset if k == 0 else max(onset, start + w["t0"])
        t1 = min(end, start + w["t1"])
        out.append({"word": shown[k] if mapped else w["word"], "t0": round(t0, 3), "t1": round(max(t1, t0 + 0.08), 3),
                    "phrase": ph["n"]})
    for k in range(1, len(out)):                  # every word starts after the previous one
        out[k]["t0"] = round(max(out[k]["t0"], out[k - 1]["t0"] + 0.05), 3)
        out[k - 1]["t1"] = round(max(out[k - 1]["t0"] + 0.05, min(out[k - 1]["t1"], out[k]["t0"])), 3)
        out[k]["t1"] = round(max(out[k]["t1"], out[k]["t0"] + 0.05), 3)
    if out:
        out[-1]["t1"] = round(max(out[-1]["t1"], end - 0.05), 3)
    return out, mapped


def speech_rate(text, seconds):
    """Syllables per second of speech (the voice aligner's syllable count)."""
    from .voice import _tokens
    syl = sum(t["syl"] for t in _tokens(text))
    return round(syl / max(seconds, 1e-3), 2), syl


# ----------------------------------------------------------------------------- build

def _signature(rows):
    h = hashlib.sha1()
    for r in rows:
        h.update(f"{r['key']}|{r['take']}|{r['start']:.3f}|{r['end']:.3f}|{r['text']}\n".encode("utf-8"))
    return h.hexdigest()[:12]


def _set_design_voice(root):
    """Point design.yaml sound.voice at assets/voice.wav when it is still empty. Returns a note."""
    p = os.path.join(root, "design.yaml")
    if not os.path.exists(p):
        return "design.yaml not found: set sound.voice: assets/voice.wav when it exists"
    import yaml
    with open(p, encoding="utf-8") as f:
        txt = f.read()
    snd = (yaml.safe_load(txt) or {}).get("sound") or {}
    cur = snd.get("voice")
    if float(snd.get("voice_offset") or 0.0) != 0.0:
        return (f"design.yaml sound.voice_offset is {snd['voice_offset']}: set it to 0, assets/voice.wav "
                "already starts at the film's 0 s and the phrases sit at their `at` times")
    if cur == "assets/voice.wav":
        return None
    if cur:
        return f"design.yaml sound.voice is '{cur}', not assets/voice.wav: the mix uses that file, not the generated voice"
    m = re.search(r"(?m)^sound:\s*\n((?:[ \t]+.*\n|\s*\n)*)", txt)
    if m:
        block = m.group(1)
        nb, k = re.subn(r"(?m)^([ \t]+)voice:[ \t]*(?:null|~|\"\"|'')?[ \t]*(#.*)?$",
                        r"\1voice: assets/voice.wav   # mv.py tts: generated voice (brief.yaml voice: tts)", block, count=1)
        if k:
            with open(p, "w", encoding="utf-8") as f:
                f.write(txt[:m.start(1)] + nb + txt[m.end(1):])
            return "design.yaml sound.voice set to assets/voice.wav"
    return "set design.yaml sound.voice: assets/voice.wav (the mix reads the voice from there)"


def build(root, retake=(), count=1, force=False, dry=False, log=print):
    """Request every phrase that has no take yet (and `count` new takes for the phrase numbers in
    `retake`), then assemble assets/voice.wav, data/words.json and data/voice_phrases.json.
    words.json is kept as it is (hand edits survive) while no phrase, take or placement changed,
    unless force=True; otherwise the old one is saved as data/words.prev.json."""
    root = os.path.abspath(root)
    phrases = plan(root)
    retake = set(int(r) for r in retake)
    bad = sorted(r for r in retake if not 1 <= r <= len(phrases))
    if bad:
        raise TTSError(f"retake: the script has phrases 1-{len(phrases)}, not {bad}")
    todo, notes = [], []
    for ph in phrases:
        need = (0 if takes(root, ph["key"]) else 1) + (count if ph["n"] in retake else 0)
        todo += [ph] * need
    chars = sum(ph["chars"] for ph in todo)
    sdir = find_secrets(root)
    used = _load_usage(sdir).get(_month(), {}).get("chars", 0) if sdir else 0
    log(f"[tts] {len(phrases)} phrase(s), voice {phrases[0]['voice']}; requests to send: {len(todo)}, "
        f"{chars} characters; this month before the run: {used:,} of {MONTH_LIMIT:,}")
    if dry:
        for ph in todo:
            log(f"  {ph['n']:>2}  rate {ph['rate']}: {ph['say']}")
        return None
    if todo:
        if not sdir:
            raise TTSError(f"no secrets/{KEY_NAME} found above {root} (or set $MV_TTS_SECRETS)")
        if used + chars > MONTH_LIMIT:
            raise TTSError(f"refused: this run would pass the monthly limit of {MONTH_LIMIT:,} characters")
        key = _read_key(sdir)
        for k, ph in enumerate(todo, 1):
            pcm = _post(key, _body(ph))
            total = _add_usage(sdir, ph["chars"])
            dup = _same_take(root, ph["key"], pcm)
            if dup:
                notes.append(f"phrase {ph['n']}: Google returned take {dup} again, not saved as a new take. "
                             "Retry later, or change `say` a little (an ellipsis, a comma) for a really new take")
                log(f"  [{k}/{len(todo)}] phrase {ph['n']}: same as take {dup}, not saved (month: {total:,} chars)")
                continue
            n = _write_take(root, ph["key"], pcm)
            if ph["n"] in retake and n > 1:
                _set_chosen(root, ph["key"], n)
            log(f"  [{k}/{len(todo)}] phrase {ph['n']} take {n}: {len(pcm) / 2 / SR:.2f} s (month: {total:,} chars)")

    rows, clips = [], []
    t = None
    for ph in phrases:
        tk = chosen_take(root, ph)
        x, clipped = _read_take(takes(root, ph["key"])[tk - 1])
        clip, speech_s, lufs_g, gain = clean(x)
        if ph["at"] is not None:
            onset = ph["at"]
        elif t is None:
            onset = float(_brief(root).get("tts_start", 0.5))
        else:
            onset = t + ph["gap"]
        pushed = 0.0
        if t is not None and onset < t + MIN_GAP:
            pushed = round(t + MIN_GAP - onset, 3)
            notes.append(f"phrase {ph['n']} would start at {onset:.2f} s, the previous one ends at {t:.2f} s: "
                         f"moved by {pushed:.2f} s. Move its `at` or shorten a line")
            onset = t + MIN_GAP
        start = onset - PAD_IN
        t = onset + speech_s
        rate, syl = speech_rate(ph["say"], speech_s)
        rows.append({"n": ph["n"], "text": ph["text"], "say": ph["say"], "from_brief": ph["from_brief"],
                     "rate": ph["rate"], "at": ph["at"], "start": round(onset, 3), "end": round(t, 3),
                     "speech_s": round(speech_s, 3), "syllables": syl, "syl_per_s": rate,
                     "words": len(ph["text"].split()), "take": tk, "takes": len(takes(root, ph["key"])),
                     "key": ph["key"], "chars": ph["chars"], "clipped": clipped, "lufs_google": lufs_g,
                     "gain_db": gain, "pushed": pushed})
        clips.append((start, clip))

    length = rows[-1]["end"] + 0.5
    track = np.zeros(int(length * SR) + 1)
    for start, clip in clips:
        i = int(round(start * SR))
        if i < 0:                                 # `at` inside the first PAD_IN: drop that much lead
            clip, i = clip[-i:], 0
        j = min(len(track), i + len(clip))
        track[i:j] += clip[: j - i]
    os.makedirs(os.path.join(root, "assets"), exist_ok=True)
    write_wav(os.path.join(root, "assets", "voice.wav"), np.stack([track, track], axis=1))

    sig = _signature(rows)
    rep_path = os.path.join(root, "data", "voice_phrases.json")
    wj = os.path.join(root, "data", "words.json")
    old_sig = None
    if os.path.exists(rep_path):
        with open(rep_path, encoding="utf-8") as f:
            old_sig = (json.load(f) or {}).get("signature")
    keep_words = os.path.exists(wj) and old_sig == sig and not force
    if not keep_words:
        words, unmapped = [], []
        for (start, clip), ph in zip(clips, phrases):
            w, mapped = _phrase_words(clip, ph, start)
            words += w
            if not mapped:
                unmapped.append(ph["n"])
        if os.path.exists(wj):
            shutil.copy(wj, os.path.join(root, "data", "words.prev.json"))
            notes.append("data/words.json rewritten (a phrase, a take or a placement changed); "
                         "the old one is data/words.prev.json")
        with open(wj, "w", encoding="utf-8") as f:
            json.dump(words, f, ensure_ascii=False, indent=1)
        if unmapped:
            notes.append(f"phrase(s) {unmapped}: `say` and `text` have different word counts, words.json "
                         "shows the spoken words; fix them by hand if the screen needs the written ones")
    rep = {"voice": phrases[0]["voice"], "lang": phrases[0]["lang"], "signature": sig,
           "length_s": round(length, 3), "made": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
           "phrases": rows, "notes": notes}
    with open(rep_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    note = _set_design_voice(root)
    if note:
        notes.append(note)
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import rights
        if rights.add_tts_row(root, phrases[0]["voice"]):
            notes.append("licenses/assets.yaml: a row for assets/voice.wav added (license google-tts)")
    except Exception as e:                       # the ledger must not stop the voice
        notes.append(f"licenses/assets.yaml not updated: {e}")
    return rep


def takes_reel(root, n, out_path, gap=1.0):
    """All takes of phrase n in a row, levelled, `gap` s apart, for choosing by ear.
    Returns [(take, start_s, length_s)]."""
    ph = next((p for p in plan(root) if p["n"] == int(n)), None)
    if ph is None:
        raise TTSError(f"no phrase {n} in the script")
    parts, marks, t = [], [], 0.5
    parts.append(np.zeros(int(0.5 * SR)))
    for k, p in enumerate(takes(root, ph["key"]), 1):
        clip = clean(_read_take(p)[0])[0]
        marks.append((k, round(t, 2), round(len(clip) / SR, 2)))
        parts += [clip, np.zeros(int(gap * SR))]
        t += len(clip) / SR + gap
    x = np.concatenate(parts)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    write_wav(out_path, np.stack([x, x], axis=1))
    return marks
