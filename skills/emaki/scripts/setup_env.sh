#!/usr/bin/env bash
# Emaki environment setup. Idempotent: safe to run at the start of every session.
# - installs missing Python deps (skia-python, numpy, scipy, pyyaml, uharfbuzz, pillow)
#   into the active Python: a virtualenv if one is active, otherwise the user site
# - on headless Linux without libEGL, builds a tiny EGL stub so skia-python can import
#   (skia links EGL only for GPU contexts; CPU raster never calls it)
# - checks ffmpeg/ffprobe
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CACHE="${MV_CACHE:-$HOME/.cache/emaki}"
mkdir -p "$CACHE"

need=()
py_has() { python3 -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$1') else 1)" 2>/dev/null; }
py_has numpy     || need+=(numpy)
py_has scipy     || need+=(scipy)
py_has yaml      || need+=(pyyaml)
py_has uharfbuzz || need+=(uharfbuzz)
py_has PIL       || need+=(pillow)
py_has skia      || need+=(skia-python)
if [ ${#need[@]} -gt 0 ]; then
  echo "[setup] installing: ${need[*]}"
  # plain install (works in a virtualenv) -> user site -> on Linux, a user-site install that
  # ignores the distro's "externally managed" marker (fine in disposable sandboxes)
  if ! python3 -m pip install -q "${need[@]}" 2>/dev/null \
     && ! python3 -m pip install -q --user "${need[@]}" 2>/dev/null \
     && ! { [ "$(uname -s)" = "Linux" ] && python3 -m pip install -q --user --break-system-packages "${need[@]}"; }; then
    echo "[setup] ERROR: pip could not install ${need[*]}."
    echo "        Make a virtualenv and run this script from it:"
    echo "        python3 -m venv ~/.venvs/emaki && . ~/.venvs/emaki/bin/activate && bash \"$0\""
    exit 1
  fi
fi

if [ "$(uname -s)" = "Linux" ]; then
  if ! ldconfig -p 2>/dev/null | grep -q "libEGL.so.1"; then
    if [ ! -f "$CACHE/libEGL.so.1" ]; then
      cat > "$CACHE/egl_stub.c" <<'EOF'
/* Minimal libEGL stub for skia-python CPU raster. */
void* eglGetCurrentDisplay(void){return 0;}
void* eglGetProcAddress(const char* n){(void)n;return 0;}
const char* eglQueryString(void* d,int n){(void)d;(void)n;return 0;}
EOF
      gcc -shared -fPIC -Wl,-soname,libEGL.so.1 -o "$CACHE/libEGL.so.1" "$CACHE/egl_stub.c" \
        && echo "[setup] built EGL stub at $CACHE/libEGL.so.1" \
        || echo "[setup] ERROR: gcc failed; skia-python will not import"
    fi
  fi
fi

command -v ffmpeg  >/dev/null || echo "[setup] ERROR: ffmpeg not found"
command -v ffprobe >/dev/null || echo "[setup] ERROR: ffprobe not found"
command -v aerender >/dev/null && echo "[setup] aerender found: AE renders can be verified"

python3 "$HERE/engine/env.py" --check
