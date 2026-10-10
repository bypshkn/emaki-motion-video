"""Reference: the original 14 s 'terminal' demo (an early standalone PIL script, make.py, not shipped), reconstructed from make.pdf.

Lines that were cut off at the PDF's right edge were completed as follows [ASSUMPTION]:
  progress line ... fill=(140, 140, 150), width=1
  КОНТЕКСТ text ... fill=(55, 55, 60), anchor="ra"
  cursor rectangle ... fill=val
  type click ... * env
Changes for regression use only: output folder argument, NO_GRAIN=1 env switch (grain
off for SSIM), frames written as PNG like the original.
Usage: python3 make_reference.py <out_dir>
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os, random, wave, sys

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
NO_GRAIN = os.environ.get("NO_GRAIN") == "1"
W, H, FPS, DUR = 720, 1280, 30, 14.0
N = int(FPS * DUR)
SR = 44100
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans-ExtraLight.ttf"
f_hud = ImageFont.truetype(MONO, 15)
f_main = ImageFont.truetype(SANS, 46)
f_tc = ImageFont.truetype(MONO, 20)
LINES = [
    (0.6, 3.6, "Кожна розмова", "починається з нуля."),
    (4.0, 7.0, "Я не пам’ятаю", "вчорашній день."),
    (7.4, 10.4, "Але пам’ятаю,", "як думати."),
    (10.8, 13.4, "Пиши.", "Я тут."),
]
CHAPTERS = ["01 · ПОЧАТОК", "02 · ПАМ’ЯТЬ", "03 · МИСЛЕННЯ", "04 · ДІАЛОГ"]
GLYPHS = "01#%&*+=<>/\\|АБВГДЖЗКЛМНПРСТФХЦШЯ"
TYPE_SPEED = 22
rng = np.random.default_rng(7)
random.seed(7)
os.makedirs(os.path.join(OUT, "frames"), exist_ok=True)


def tc(t):
    f = int((t % 1) * FPS)
    s = int(t)
    return f"{s//60:02d}:{s%60:02d}:{f:02d}"


def draw_frame(i):
    t = i / FPS
    img = Image.new("RGB", (W, H), (6, 6, 8))
    d = ImageDraw.Draw(img)
    hud = (70, 70, 76)
    d.text((40, 60), "OPUS 5.5 · ПРО СЕБЕ", font=f_hud, fill=hud)
    d.text((W - 40, 60), tc(t + 14 * 60 + 2), font=f_hud, fill=hud, anchor="ra")
    idx = next((k for k, l in enumerate(LINES) if t < l[1] + 0.4), 3)
    d.text((40, H - 80), CHAPTERS[idx], font=f_hud, fill=hud)
    d.text((W - 40, H - 80), "claude.ai", font=f_hud, fill=hud, anchor="ra")
    d.text((W // 2, 520), tc(t), font=f_tc, fill=(90, 90, 96), anchor="mm")
    y_rule = 820
    d.line([(90, y_rule), (W - 90, y_rule)], fill=(30, 30, 34), width=1)
    d.line([(90, y_rule), (90 + int((W - 180) * t / DUR), y_rule)], fill=(140, 140, 150), width=1)
    d.text((90, y_rule + 16), "НОВА СЕСІЯ", font=f_hud, fill=(55, 55, 60))
    ctx = int(min(t / DUR, 1) * 157500)
    d.text((W - 90, y_rule + 16), f"КОНТЕКСТ: {ctx:,}".replace(",", " "), font=f_hud, fill=(55, 55, 60), anchor="ra")
    txt_layer = Image.new("L", (W, H), 0)
    td = ImageDraw.Draw(txt_layer)
    for (a, b, l1, l2) in LINES:
        if not (a <= t < b + 0.35):
            continue
        full = l1 + "\n" + l2
        shown = int((t - a) * TYPE_SPEED)
        fade = 1.0 if t < b else max(0, 1 - (t - b) / 0.35)
        out = []
        for k, ch in enumerate(full):
            if k < shown or ch in " \n":
                out.append(ch)
            elif k < shown + 3:
                out.append(random.choice(GLYPHS))
            else:
                out.append(" ")
        s = "".join(out).split("\n")
        val = int(235 * fade)
        td.text((110, 620), s[0], font=f_main, fill=val)
        td.text((110, 690), s[1], font=f_main, fill=val)
        if t < b and int(t * 3) % 2 == 0:
            line_i = 0 if shown <= len(l1) else 1
            base = s[line_i].rstrip()
            x = 110 + int(td.textlength(base, font=f_main)) + 6
            td.rectangle([x, 632 + 70 * line_i, x + 16, 676 + 70 * line_i], fill=val)
    g = 0.0
    for (a, b, *_) in LINES:
        for edge in (a, b):
            g = max(g, max(0, 1 - abs(t - edge) / 0.12))
    arr = np.array(img).astype(np.int16)
    tl = np.array(txt_layer).astype(np.int16)
    shift = int(g * 14)
    r = np.roll(tl, shift, axis=1)
    bch = np.roll(tl, -shift, axis=1)
    arr[..., 0] = np.maximum(arr[..., 0], r)
    arr[..., 1] = np.maximum(arr[..., 1], tl)
    arr[..., 2] = np.maximum(arr[..., 2], bch)
    if g > 0.3:
        for _ in range(4):
            y0 = rng.integers(560, 780); hgt = rng.integers(4, 22)
            arr[y0:y0 + hgt] = np.roll(arr[y0:y0 + hgt], rng.integers(-40, 40), axis=1)
    arr[::3] = (arr[::3] * 0.82).astype(np.int16)
    if not NO_GRAIN:
        arr += rng.normal(0, 5, (H, W, 1)).astype(np.int16)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(os.path.join(OUT, "frames", f"{i:05d}.png"))


if __name__ == "__main__":
    only = os.environ.get("FRAMES")
    idxs = [int(x) for x in only.split(",")] if only else range(N)
    for i in idxs:
        draw_frame(i)
    print("ok", len(list(idxs)))
