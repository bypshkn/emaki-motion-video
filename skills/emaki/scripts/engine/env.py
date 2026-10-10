"""Environment bootstrap: makes `import skia` work in headless Linux sandboxes.

skia-python links libEGL.so.1 even for CPU raster. Sandboxes often lack it, so
setup_env.sh builds a stub into ~/.cache/emaki. We preload that stub with
RTLD_GLOBAL before importing skia; the dynamic linker then resolves the NEEDED
entry by soname.
"""
import ctypes
import os
import sys

CACHE = os.environ.get("MV_CACHE", os.path.expanduser("~/.cache/emaki"))
_skia = None


def load_skia():
    global _skia
    if _skia is not None:
        return _skia
    try:
        import skia  # noqa
        _skia = skia
        return skia
    except ImportError as e:
        if "libEGL" not in str(e):
            raise ImportError(
                "skia-python is missing. Run scripts/setup_env.sh first.") from e
    stub = os.path.join(CACHE, "libEGL.so.1")
    if not os.path.exists(stub):
        raise ImportError(
            "libEGL.so.1 not found and no stub built. Run scripts/setup_env.sh first.")
    ctypes.CDLL(stub, mode=ctypes.RTLD_GLOBAL)
    import skia  # noqa
    _skia = skia
    return skia


def check():
    skia = load_skia()
    import numpy, scipy, yaml, uharfbuzz  # noqa
    import subprocess
    print(f"[env] skia {skia.__version__} | numpy {numpy.__version__} | scipy {scipy.__version__}"
          f" | uharfbuzz {uharfbuzz.__version__}")
    try:
        out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        enc = [e for e in ("libx264", "libvpx-vp9", "prores_ks", "aac") if e in out]
        print(f"[env] ffmpeg encoders: {', '.join(enc)}")
    except FileNotFoundError:
        print("[env] ffmpeg: MISSING")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine import fonts
    fams = fonts.cyrillic_families()
    print(f"[env] system fonts with full Ukrainian coverage: {len(fams)}")
    print("      " + ", ".join(sorted(fams)[:40]))
    print("[env] OK")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
