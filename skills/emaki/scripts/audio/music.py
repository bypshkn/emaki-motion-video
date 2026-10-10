"""Generative music bed from design.yaml -> sound, locked to the project's BPM grid.

Arrangement follows scene energy (Scene.energy 0..1): low energy keeps pad/bass, mid adds
arps and light percussion, high adds full drums. Accent events get a crash/kick or a
sub hit; the final bar resolves to the tonic and the tail fades out by the video end.

sound:
  genre: minimal | ambient | electronic | cinematic | lofi | corporate | playful | piano | terminal
  bpm: 110
  key: "A minor"            # any root + major/minor/dorian/lydian/mixolydian/phrygian/pentatonic
  timbres: [warm pad, sub, pluck]   # optional overrides by keyword
  progression: [i, VI, III, VII]    # optional roman numerals
  music_gain_db: 0          # music bed level vs. sfx
  music: true               # false = SFX only
  layers: {bass: -4}        # optional per-layer trims, dB (track names: pad, bass, arp, keys, drums, fx, air)
  low_cut_hz: 45            # optional high-pass on bass and drums: less sub weight
"""
import re

import numpy as np

from .dsp import SR, samples, midi_hz, db, stereo, mix_into, pan, filt, fade
from . import instruments as I
from .fx import reverb, delay, chorus, duck_env, compress

NOTES = {"c": 0, "c#": 1, "db": 1, "d": 2, "d#": 3, "eb": 3, "e": 4, "f": 5, "f#": 6, "gb": 6, "g": 7,
         "g#": 8, "ab": 8, "a": 9, "a#": 10, "bb": 10, "b": 11}
MODES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10], "dorian": [0, 2, 3, 5, 7, 9, 10],
         "lydian": [0, 2, 4, 6, 7, 9, 11], "mixolydian": [0, 2, 4, 5, 7, 9, 10], "phrygian": [0, 1, 3, 5, 7, 8, 10]}

GENRES = {
    "ambient": dict(pad="warm_pad", bass="sub", keys="bell", drums=None, arp=None, melody="sparse",
                    rev=(0.45, 4.0), prog_major=["I", "IV", "vi", "IV"], prog_minor=["i", "VI", "III", "VII"], bars_per_chord=2),
    "minimal": dict(pad="pad", bass="sub", arp="pluck", drums="minimal", rev=(0.25, 2.2), sidechain=0.18,
                    prog_major=["I", "V", "vi", "IV"], prog_minor=["i", "VI", "III", "VII"]),
    "electronic": dict(pad="pad", bass="bass_synth", arp="arp_synth", drums="house", rev=(0.2, 1.8), sidechain=0.3,
                       prog_major=["vi", "IV", "I", "V"], prog_minor=["i", "VII", "VI", "VII"]),
    "cinematic": dict(pad="strings", bass="sub", keys="piano", drums="cinematic", rev=(0.4, 3.5), risers=True,
                      prog_major=["I", "vi", "IV", "V"], prog_minor=["i", "VI", "III", "VII"], bars_per_chord=2),
    "lofi": dict(pad=None, keys="epiano", bass="sub", drums="boombap", swing=0.58, crackle=True, rev=(0.2, 1.5),
                 lowpass=5200, prog_major=["ii7", "V7", "Imaj7", "vi7"], prog_minor=["i7", "iv7", "VII7", "III7"]),
    "corporate": dict(pad="warm_pad", keys="pluck", bass="bass_synth", drums="pop", rev=(0.22, 1.8), melody="motif",
                      prog_major=["I", "V", "vi", "IV"], prog_minor=["i", "VI", "III", "VII"]),
    "playful": dict(pad=None, keys="marimba", bass="bass_pluck", drums="claps", rev=(0.18, 1.4), melody="bouncy",
                    prog_major=["I", "IV", "V", "IV"], prog_minor=["i", "iv", "VII", "III"]),
    "piano": dict(pad="warm_pad", keys="piano", bass=None, drums=None, rev=(0.35, 2.6), melody="sparse",
                  prog_major=["I", "iii", "IV", "V"], prog_minor=["i", "VI", "iv", "V"], bars_per_chord=1),
    "terminal": dict(drone=True, drums=None, pad=None, bass=None, rev=(0.15, 3.0)),
}
ALIASES = [("ambient", "ambient"), ("drone", "terminal"), ("terminal", "terminal"), ("dark", "terminal"),
           ("minimal", "minimal"), ("house", "electronic"), ("synth", "electronic"), ("electro", "electronic"),
           ("techno", "electronic"), ("cinemat", "cinematic"), ("epic", "cinematic"), ("trailer", "cinematic"),
           ("lo-fi", "lofi"), ("lofi", "lofi"), ("chill", "lofi"), ("corporate", "corporate"), ("upbeat", "corporate"),
           ("pop", "corporate"), ("playful", "playful"), ("marimba", "playful"), ("kids", "playful"),
           ("piano", "piano"), ("editorial", "piano"), ("classical", "piano")]
TIMBRE_KEYS = [("felt piano", "keys", "piano"), ("piano", "keys", "piano"), ("rhodes", "keys", "epiano"),
               ("e-piano", "keys", "epiano"), ("epiano", "keys", "epiano"), ("bell", "keys", "bell"),
               ("marimba", "keys", "marimba"), ("pluck", "arp", "pluck"), ("string", "pad", "strings"),
               ("warm pad", "pad", "warm_pad"), ("soft pad", "pad", "warm_pad"), ("pad", "pad", "pad"),
               ("sub", "bass", "sub"), ("synth bass", "bass", "bass_synth"), ("arp", "arp", "arp_synth")]


def parse_key(s):
    s = (s or "A minor").strip().lower()
    m = re.match(r"([a-g][#b]?)\s*(\w+)?", s)
    root = NOTES[m.group(1)]
    mode = m.group(2) or "major"
    if mode in ("min", "m", "moll"):
        mode = "minor"
    if mode in ("maj", "dur"):
        mode = "major"
    if mode.startswith("pent"):
        mode = "major"
    return root, mode if mode in MODES else "minor"


ROMAN = {"i": 0, "ii": 1, "iii": 2, "iv": 3, "v": 4, "vi": 5, "vii": 6}


def chord_notes(sym, root, mode, octave=4):
    """Roman numeral -> MIDI notes in the key (diatonic triads/7ths; case sets quality)."""
    m = re.match(r"(b?)([ivIV]+)(maj7|7)?", sym)
    flat, rn, ext = m.group(1), m.group(2), m.group(3)
    deg = ROMAN[rn.lower()]
    scale = MODES[mode]
    base = 12 * (octave + 1) + root
    r = base + scale[deg] - (1 if flat else 0)
    minor_q = rn.islower()
    third = r + (3 if minor_q else 4)
    fifth = r + 7
    notes = [r, third, fifth]
    if ext == "7":
        notes.append(r + (10 if (minor_q or sym.upper().startswith("V")) else 10))
    elif ext == "maj7":
        notes.append(r + 11)
    return notes


def pick_genre(sound):
    g = str(sound.get("genre", "minimal")).lower()
    for k, v in ALIASES:
        if k in g:
            return v
    return "minimal"


class Composer:
    def __init__(self, P, seed=23, warn=None):
        self.P = P
        self.snd = P.design.sound or {}
        self.genre = pick_genre(self.snd)
        self.cfg = dict(GENRES[self.genre])
        for kw, slot, inst in TIMBRE_KEYS:
            for tb in self.snd.get("timbres", []) or []:
                if kw in str(tb).lower():
                    self.cfg[slot] = inst
        self.root, self.mode = parse_key(self.snd.get("key"))
        self.bpm = P.bpm
        self.spb = 60.0 / self.bpm
        self.rng = np.random.default_rng(seed)
        self.dur = P.duration
        self.n = samples(self.dur) + 1
        self.warn = warn or (lambda m: None)
        prog = self.snd.get("progression")
        if not prog:
            prog = self.cfg.get("prog_minor" if self.mode in ("minor", "dorian", "phrygian") else "prog_major") or ["i"]
        self.prog = prog
        self.tracks = {}

    # ---- grid helpers
    def beat_t(self, b):
        return self.P.beat_offset + b * self.spb

    def energy_at(self, t):
        for s in self.P.scenes:
            if s.t0 <= t < s.t1:
                return float(s.energy)
        return 0.4

    def track(self, name):
        if name not in self.tracks:
            self.tracks[name] = np.zeros((self.n, 2))
        return self.tracks[name]

    def place(self, name, x, t, p=0.0, gain=1.0):
        if t >= self.dur:
            return
        x = pan(x, p) if x.ndim == 1 else x
        mix_into(self.track(name), x * gain, samples(t))

    # ---- compose
    def compose(self):
        c = self.cfg
        if c.get("drone"):
            return self._terminal()
        bpb = self.P.beats_per_bar
        bars = int(np.ceil((self.dur - self.P.beat_offset) / (bpb * self.spb)))
        bpc = c.get("bars_per_chord", 1 if self.bpm < 100 else 2)
        end_bar = max(1, int((self.dur - 1.2 - self.P.beat_offset) // (bpb * self.spb)))
        swing = c.get("swing", 0.5)
        kick_times = []
        for bar in range(bars):
            t_bar = self.beat_t(bar * bpb)
            if t_bar >= self.dur:
                break
            final = bar >= end_bar
            sym = self.prog[0] if final else self.prog[(bar // bpc) % len(self.prog)]
            chord = chord_notes(sym, self.root, self.mode, 4)
            e = self.energy_at(t_bar + 0.01)
            bar_len = bpb * self.spb
            # pad
            if c.get("pad") and (bar % bpc == 0 or final):
                inst = I.TONAL[c["pad"]]
                hold = bar_len * (bpc if not final else 1.5)
                for k, nn in enumerate(chord):
                    self.place("pad", inst(midi_hz(nn), hold, 0.55 + 0.25 * e, self.rng), t_bar, (k - 1) * 0.35, 0.8)
            # bass
            if c.get("bass"):
                inst = I.TONAL[c["bass"]]
                rootn = chord[0] - 24
                if self.genre in ("electronic",) and e >= 0.5 and not final:
                    for b in range(bpb):
                        self.place("bass", inst(midi_hz(rootn), self.spb * 0.45, 0.8), t_bar + (b + 0.5) * self.spb)
                elif e >= 0.45 and not final and self.genre in ("minimal", "corporate", "playful", "lofi"):
                    for b in range(bpb):
                        if self.genre == "playful" or b % 2 == 0 or e > 0.7:
                            self.place("bass", inst(midi_hz(rootn), self.spb * 0.9, 0.75), t_bar + b * self.spb)
                else:
                    if bar % bpc == 0 or final:
                        self.place("bass", inst(midi_hz(rootn), bar_len * (bpc if not final else 1.2), 0.7), t_bar)
            # arp / keys
            if c.get("arp") and e >= 0.35 and not final:
                inst = I.TONAL[c["arp"]]
                steps = 16 if e >= 0.65 else 8
                pattern = chord + [n + 12 for n in chord]
                for s in range(steps):
                    nn = pattern[(s * (1 if (bar % 2 == 0) else 2)) % len(pattern)]
                    ts = t_bar + s * bar_len / steps
                    if steps == 16 and s % 2 == 1:
                        ts += (swing - 0.5) * bar_len / 8
                    self.place("arp", inst(midi_hz(nn + 12), bar_len / steps * 0.9, 0.45 + 0.25 * e, self.rng),
                               ts, 0.3 * np.sin(s), 0.75)
            if c.get("keys"):
                self._keys(c["keys"], chord, t_bar, bar_len, e, final, bar)
            # drums
            if c.get("drums") and not final:
                kick_times += self._drums(c["drums"], t_bar, bar_len, e, swing, bar)
        # final ring-out handled by pad/keys holds; accents
        self._accents()
        if c.get("crackle"):
            nz = self.rng.standard_normal(self.n) * 0.004
            pops = (self.rng.random(self.n) > 0.9997) * self.rng.uniform(0.05, 0.25, self.n)
            cr = filt(nz + pops, "bp", 3000, 0.4)
            self.track("fx")[:] += stereo(cr)
        return self._mixdown(kick_times)

    def _keys(self, inst_name, chord, t_bar, bar_len, e, final, bar):
        inst = I.TONAL[inst_name]
        mel = self.cfg.get("melody")
        scale = [12 * 5 + self.root + s for s in MODES[self.mode]]
        if final:
            for k, nn in enumerate(chord):
                self.place("keys", inst(midi_hz(nn), bar_len * 1.5, 0.6, self.rng), t_bar + k * 0.03, (k - 1) * 0.3)
            return
        if inst_name in ("piano", "epiano") and self.genre in ("piano", "cinematic", "lofi"):
            # broken chord / comping
            if self.genre == "lofi":
                for hit in (0, 1.5, 2.5):
                    tt_ = t_bar + hit * self.spb + (0.02 if hit % 1 else 0)
                    for k, nn in enumerate(chord):
                        self.place("keys", inst(midi_hz(nn), self.spb * 0.9, 0.5, self.rng), tt_ + k * 0.012, (k - 1) * 0.3)
            else:
                order = [0, 2, 1, 2] if e < 0.6 else [0, 1, 2, 1, 2, 1, 0, 2]
                step = bar_len / len(order)
                for s, k in enumerate(order):
                    self.place("keys", inst(midi_hz(chord[k] + (12 if s % 4 == 3 else 0)), step * 1.8, 0.45 + 0.2 * e, self.rng),
                               t_bar + s * step, (k - 1) * 0.25)
        if mel == "sparse" and self.rng.random() < 0.55 + 0.3 * e:
            nn = chord[int(self.rng.integers(0, len(chord)))] + 12
            off = float(self.rng.choice([0, 1, 2, 2.5])) * self.spb
            self.place("lead", inst(midi_hz(nn), self.spb * 1.5, 0.35, self.rng), t_bar + off, 0.2)
        elif mel in ("motif", "bouncy") and e >= 0.45:
            if not hasattr(self, "_motif"):
                r = np.random.default_rng(99)
                steps = [0, 2, 4, 2, 5, 4, 2, 0] if mel == "motif" else [0, 4, 2, 4, 5, 4, 7, 4]
                rhythm = [0, 1, 1.5, 2, 3, 3.5] if mel == "motif" else [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5]
                self._motif = (steps, rhythm)
            steps, rhythm = self._motif
            base = chord[0] - 12 * 4 + 12 * 5
            deg0 = min(range(len(scale)), key=lambda i: abs(scale[i] - base))
            for k, r_ in enumerate(rhythm):
                d = steps[(k + bar) % len(steps)]
                idx = deg0 + d
                nn = scale[idx % 7] + 12 * (idx // 7)
                self.place("lead", inst(midi_hz(nn + 12), self.spb * 0.45, 0.4, self.rng), t_bar + r_ * self.spb, 0.15)
        elif inst_name in ("pluck", "marimba", "bell") and mel not in ("motif", "bouncy"):
            if e >= 0.35:
                for s in range(8):
                    nn = chord[s % len(chord)] + 12
                    self.place("keys", inst(midi_hz(nn), self.spb * 0.5, 0.35, self.rng), t_bar + s * bar_len / 8, 0.25 * np.sin(s))

    def _drums(self, kind, t_bar, bar_len, e, swing, bar):
        D = I.DRUMS
        r = self.rng
        kicks = []
        q = bar_len / 4
        s8 = bar_len / 8

        def sw(i):
            return (swing - 0.5) * s8 * 2 if i % 2 == 1 else 0.0
        if kind in ("minimal", "house", "pop"):
            if e >= 0.5:
                beats = range(4) if (kind != "minimal" or e >= 0.75) else (0, 2)   # minimal: half-time pulse
                for b in beats:
                    self.place("drums", D["kick"](0.9, r), t_bar + b * q)
                    kicks.append(t_bar + b * q)
            if e >= 0.35:
                for i in range(8):
                    if i % 2 == 1 or (kind == "house" and e > 0.7):
                        self.place("drums", D["hat"](0.5 + 0.2 * (i % 2), r), t_bar + i * s8 + sw(i), 0.25, 0.7)
            if e >= 0.65 and kind in ("house", "pop"):
                for b in (1, 3):
                    self.place("drums", D["clap"](0.8, r), t_bar + b * q, 0.0, 0.8)
            if kind == "minimal" and e >= 0.6:
                self.place("drums", D["rim"](0.6, r), t_bar + 3.5 * q, -0.3, 0.6)
        elif kind == "boombap":
            for b, hit in ((0, "kick"), (2.5, "kick"), (1, "snare"), (3, "snare")):
                if hit == "kick" or e >= 0.4:
                    self.place("drums", D[hit](0.85, r), t_bar + b * q, 0.0, 0.85)
                    if hit == "kick":
                        kicks.append(t_bar + b * q)
            for i in range(8):
                self.place("drums", D["hat"](0.35 + 0.15 * (i % 2 == 0), r), t_bar + i * s8 + sw(i), 0.2, 0.6)
        elif kind == "claps":
            if e >= 0.4:
                for b in (1, 3):
                    self.place("drums", D["clap"](0.7, r), t_bar + b * q, 0.0, 0.7)
                for i in range(8):
                    self.place("drums", D["shaker"](0.5, r), t_bar + i * s8, 0.3, 0.6)
            if e >= 0.6:
                for b in (0, 2):
                    self.place("drums", D["kick"](0.7, r, True), t_bar + b * q)
                    kicks.append(t_bar + b * q)
        elif kind == "cinematic":
            if e >= 0.55:
                for b in (0, 1.5, 2, 3.5) if e > 0.75 else (0, 2):
                    self.place("drums", D["tom"](0.8, r, 70 + 30 * (b % 2)), t_bar + b * q, 0.0, 0.9)
                kicks.append(t_bar)
        return kicks

    def _accents(self):
        # Accents are scored by the SFX the timeline asks for; the bed no longer stamps a crash
        # + kick on every accent (user feedback 2026-10-08: sounds force-fitted and dated).
        for ev in self.P.all_events():
            if not ev.accent:
                continue
            if self.cfg.get("risers") or self.genre == "cinematic":
                from .sfx import riser, impact
                rx, _ = riser(self.rng, min(2.0, max(0.6, ev.t - 0.1)))
                mix_into(self.track("fx"), rx * 0.5, samples(ev.t - len(rx) / SR))
                ix, _ = impact(self.rng)
                mix_into(self.track("fx"), ix * 0.6, samples(ev.t))

    def _terminal(self):
        """Drone bed as in the terminal demo; shimmer joins when energy >= 0.5."""
        x = I.drone(self.dur)
        t = np.arange(len(x)) / SR
        x *= np.clip(t / 2.0, 0, 1) * np.clip((self.dur - t) / 1.5, 0, 1)
        sh = I.shimmer(self.dur)
        t_sh = next((s.t0 for s in self.P.scenes if s.energy >= 0.5), None)
        if t_sh is not None:
            x += sh * np.clip((t - t_sh) / 2, 0, 1) * np.clip((self.dur - t) / 1.5, 0, 1)
        self.track("pad")[: len(x)] += stereo(x)[: self.n]
        for ev in self.P.all_events():
            if ev.accent:
                from .sfx import sub_hit
                sx, _ = sub_hit(self.rng)
                mix_into(self.track("fx"), sx, samples(ev.t))
        return self._mixdown([])

    def _mixdown(self, kicks):
        c = self.cfg
        rev_mix, rt = c.get("rev", (0.25, 2.2))
        # mids carry the bed (pad, keys, arp), low end sits under them (2026-10-08 spectral review)
        levels = {"pad": -9, "bass": -16, "arp": -12, "keys": -9, "lead": -12, "drums": -13, "fx": -8, "air": -24}
        sends = {"pad": 1.0, "arp": 0.8, "keys": 0.9, "lead": 1.0, "drums": 0.25, "bass": 0.0, "fx": 0.4}
        if self.genre not in ("terminal", "lofi") and "air" not in self.tracks:
            # air: a faint, slowly breathing high noise layer (modern beds are never dull up top)
            nz = self.rng.standard_normal((self.n, 2)) * 0.25
            nz = filt(filt(nz, "hp", 7000, 0.7), "lp", 15000, 0.7)
            t_ = np.arange(self.n) / SR
            self.track("air")[:] += nz * (0.6 + 0.4 * np.sin(2 * np.pi * t_ / 7.0))[:, None]
        out = np.zeros((self.n, 2))
        bus = np.zeros((self.n, 2))
        sc = duck_env(self.n, kicks, c.get("sidechain", 0.0)) if c.get("sidechain") and kicks else None
        lay = self.snd.get("layers") or {}                 # per-layer trims in dB, e.g. {bass: -4, drums: -2}
        low_cut = float(self.snd.get("low_cut_hz", 0) or 0)  # high-pass on bass and drums (kick/sub weight)
        for name, x in self.tracks.items():
            g = db(levels.get(name, -10) + float(lay.get(name, 0.0)))
            y = x * g
            if low_cut and name in ("bass", "drums"):
                y = filt(y, "hp", low_cut)
            if name == "pad":
                y = chorus(y, mix=0.3)
            if name == "arp" or (name == "keys" and self.genre in ("corporate", "minimal")):
                y = delay(y, self.spb * 0.75, 0.3, 0.22)
            if sc is not None and name in ("pad", "bass", "arp"):
                y = y * sc[:, None]
            if name == "bass":
                y = filt(y, "lp", 900)
            out += y
            bus += y * sends.get(name, 0.3)
        out += reverb(bus, 1.0, rt) * rev_mix
        out = filt(out, "hp", 28)
        if c.get("lowpass"):
            out = filt(out, "lp", c["lowpass"], 0.6)
        out = compress(out, -20, 2.0, 0.02, 0.2)
        t = np.arange(self.n) / SR
        fade_out = np.clip((self.dur - t) / 0.9, 0, 1)
        out *= np.clip(t / 0.05, 0, 1)[:, None] * fade_out[:, None]
        return out
