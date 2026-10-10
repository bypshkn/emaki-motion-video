"""Contact sheets: grids of frames with timestamps (and optional captions) for review."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

LABEL_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def _font(sz):
    try:
        return ImageFont.truetype(LABEL_FONT, sz)
    except OSError:
        return ImageFont.load_default()


def tc(t):
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:04.1f}"


def sheet(frames, out, cols=None, max_width=1800, captions=None, title=None, per_sheet=None):
    """frames: list of (t, HxWx3 uint8). Writes one or more PNGs; returns their paths.
    Sized so each sheet stays readable when viewed as an image (<= ~1800 px wide)."""
    if not frames:
        return []
    h, w = frames[0][1].shape[:2]
    portrait = h > w
    if cols is None:
        cols = 8 if portrait else 5
        if h == w:
            cols = 6
    per_sheet = per_sheet or cols * (3 if portrait else 5)
    tw = max_width // cols
    th = int(tw * h / w)
    lab = max(14, tw // 14)
    cap_h = lab + 8
    if captions:
        cap_h += lab * 2 + 4
    paths = []
    for si in range(0, len(frames), per_sheet):
        chunk = frames[si:si + per_sheet]
        rows = math.ceil(len(chunk) / cols)
        head = lab * 2 + 10 if title else 0
        img = Image.new("RGB", (cols * tw, head + rows * (th + cap_h)), (24, 24, 26))
        d = ImageDraw.Draw(img)
        f = _font(lab)
        if title:
            d.text((8, 6), title + (f"  [{si // per_sheet + 1}/{math.ceil(len(frames) / per_sheet)}]" if len(frames) > per_sheet else ""),
                   font=_font(int(lab * 1.2)), fill=(230, 230, 230))
        for k, (t, fr) in enumerate(chunk):
            r, c = divmod(k, cols)
            x, y = c * tw, head + r * (th + cap_h)
            thumb = Image.fromarray(fr).resize((tw - 4, th - 4), Image.LANCZOS)
            img.paste(thumb, (x + 2, y + 2))
            d.text((x + 4, y + th + 2), tc(t), font=f, fill=(200, 200, 200))
            if captions:
                cap = captions[si + k] or ""
                d.text((x + 4, y + th + lab + 6), cap[:int(tw / (lab * 0.62))], font=f, fill=(150, 150, 150))
        p = out if len(frames) <= per_sheet else out.replace(".png", f"_{si // per_sheet + 1}.png")
        img.save(p)
        paths.append(p)
    return paths
