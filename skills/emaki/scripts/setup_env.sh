#!/usr/bin/env bash
# Emaki environment setup. Idempotent: safe to run at the start of every session.
# - installs missing Python deps (versions from requirements.txt) into the active Python:
#   a virtualenv if one is active, otherwise the user site. Packages already present stay as
#   they are. It never overrides the system's "externally managed" Python marker unless
#   EMAKI_ALLOW_SYSTEM_PIP=1 is set (only for disposable sandboxes and containers)
# - on headless Linux without libEGL, builds a tiny EGL stub so skia-python can import
#   (skia links EGL only for GPU contexts; CPU raster never calls it)
# - checks ffmpeg/ffprobe
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQ="$HERE/requirements.txt"
CACHE="${MV_CACHE:-$HOME/.cache/emaki}"
mkdir -p "$CACHE"

# requirement line for a package name, e.g. "numpy>=1.26,<3" (the bare name if the file is missing)
req() { local l; l="$(grep -iE "^$1[<>=!~ ]" "$REQ" 2>/dev/null | head -1 | sed 's/[[:space:]]*#.*//')"; echo "${l:-$1}"; }
need=()
py_has() { python3 -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$1') else 1)" 2>/dev/null; }
py_has numpy     || need+=("$(req numpy)")
py_has scipy     || need+=("$(req scipy)")
py_has yaml      || need+=("$(req pyyaml)")
py_has uharfbuzz || need+=("$(req uharfbuzz)")
py_has PIL       || need+=("$(req pillow)")
py_has fontTools || need+=("$(req fonttools)")
py_has skia      || need+=("$(req skia-python)")
if [ ${#need[@]} -gt 0 ]; then
  echo "[setup] installing: ${need[*]}"
  # plain install (works in a virtualenv) -> user site -> only with an explicit opt-in, a
  # user-site install that ignores the "externally managed" marker
  if ! python3 -m pip install -q "${need[@]}" 2>/dev/null \
     && ! python3 -m pip install -q --user "${need[@]}" 2>/dev/null \
     && ! { [ "${EMAKI_ALLOW_SYSTEM_PIP:-0}" = "1" ] \
            && python3 -m pip install -q --user --break-system-packages "${need[@]}"; }; then
    echo "[setup] ERROR: pip could not install into this Python: ${need[*]}"
    echo "        On your own computer, make a separate environment for Emaki and run setup from it:"
    echo "          python3 -m venv ~/.venvs/emaki"
    echo "          PATH=\"\$HOME/.venvs/emaki/bin:\$PATH\" bash \"$0\""
    echo "        then run mv.py with ~/.venvs/emaki/bin/python in place of python3."
    echo "        In a disposable sandbox or container only: EMAKI_ALLOW_SYSTEM_PIP=1 bash \"$0\""
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
