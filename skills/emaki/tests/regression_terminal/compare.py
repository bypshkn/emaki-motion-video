"""Regression: original demo (make_reference.py) vs engine port (video.py).

Renders both at 720x1280 without grain for the sampled frames, reports SSIM per frame
(luminance, 7x7 gaussian) and writes a side-by-side contact sheet.
Usage: python3 compare.py <out_dir>
"""
import os
import subprocess
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "..", "scripts")
sys.path.insert(0, SCRIPTS)

# frames: typing, hold, glitch edges, fades, every line
FRAMES = [10, 30, 60, 90, 105, 108, 125, 150, 200, 225, 240, 270, 310, 335, 360, 395, 405, 415]


def ssim(a, b):
    a, b = a.astype(np.float64), b.astype(np.float64)
    C1, C2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    g = lambda x: ndimage.gaussian_filter(x, 1.5)
    ma, mb = g(a), g(b)
    va, vb, cov = g(a * a) - ma * ma, g(b * b) - mb * mb, g(a * b) - ma * mb
    s = ((2 * ma * mb + C1) * (2 * cov + C2)) / ((ma * ma + mb * mb + C1) * (va + vb + C2))
    return float(s.mean())


def lum(img):
    return img[..., :3] @ np.array([0.2126, 0.7152, 0.0722])


def main(out):
    os.makedirs(out, exist_ok=True)
    env = dict(os.environ, NO_GRAIN="1", FRAMES=",".join(map(str, FRAMES)))
    subprocess.run([sys.executable, os.path.join(HERE, "make_reference.py"), os.path.join(out, "ref")], env=env, check=True)
    from engine.render import load_project, frame
    P = load_project(os.path.join(HERE, "video.py"), no_grain=True)
    rows = []
    scores = []
    for i in FRAMES:
        t = i / 30.0
        ref = np.array(Image.open(os.path.join(out, "ref", "frames", f"{i:05d}.png")).convert("RGB"))
        got = frame(P, t, scale=720 / 1080, ss=2)
        s = ssim(lum(ref), lum(got))
        # glitch frames use different random slices by design; report separately
        g = P.fx_tracks["glitch"].at(t)
        scores.append((i, t, s, g))
        rows.append(np.concatenate([ref, got], axis=1))
    for i, t, s, g in scores:
        print(f"frame {i:3d}  t={t:5.2f}s  SSIM={s:.3f}{'  (glitch)' if g > 0.05 else ''}")
    clean = [s for _, _, s, g in scores if g <= 0.05]
    print(f"mean SSIM (no-glitch frames): {np.mean(clean):.3f}   min: {np.min(clean):.3f}")
    from engine.contact import sheet
    sheet([(t, r) for (i, t, s, g), r in zip(scores, rows)], os.path.join(out, "compare.png"), cols=6,
          captions=[f"SSIM {s:.3f}" for _, _, s, _ in scores], title="left: make.py   right: engine port")
    return np.mean(clean)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out"))
