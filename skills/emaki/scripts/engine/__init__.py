"""Emaki engine: everything a video.py needs via `from engine import *`."""
import glob
import importlib.util
import os

from .env import load_skia

skia = load_skia()

from .easing import ease, tween, progress, lerp, spring_curve, BEZIERS, SPRINGS  # noqa: E402
from .core import (Project, Scene, Layer, Group, Null, Prop, Wiggle, Camera, Event, Ctx,  # noqa: E402
                   Blur, DropShadow, SoftShadow, Glow, LayerFx, Smear, Pulse, Sheen, color, contrast_ratio, luminance,
                   ASPECTS, CURRENT, FX_SCALE)
from .design import Design, PLATFORM_ZONES  # noqa: E402
from .layers import *  # noqa: E402,F401,F403
from .transitions import (Transition, Cut, Fade, Dip, Push, Slide, Wipe, Iris, Zoom,  # noqa: E402
                          BlurDissolve, ShapeWipe, Glitch, Whip, FlashCut, ScaleThrough, REGISTRY as TRANSITIONS)
from . import fonts  # noqa: E402


def load_extensions(project_dir):
    """Import every module in <project_dir>/engine_ext/*.py (new layers/fx written for
    this video). Returns the loaded modules."""
    mods = []
    for p in sorted(glob.glob(os.path.join(project_dir, "engine_ext", "*.py"))):
        name = "engine_ext_" + os.path.splitext(os.path.basename(p))[0]
        spec = importlib.util.spec_from_file_location(name, p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        mods.append(m)
    return mods
