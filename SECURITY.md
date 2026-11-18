# Security

## Reporting a vulnerability

Please report it privately: open the **Security** tab of this repository and click
**Report a vulnerability**. Do not open a public issue for it.

Fixes ship in the latest release.

## What Emaki runs on your computer

Knowing this helps you judge what counts as a vulnerability here.

- Emaki renders video with Python code. Claude writes part of that code for every video
  (`video.py`, `engine_ext/*.py`) and runs it. Your protection against harmful code is the
  sandbox and the permissions of the Claude app or Claude Code, not Emaki itself.
- Every command also runs `engine_ext/*.py` from your `motion-lib/` library, if one is found.
  The search walks up from the project folder and stops at your home folder. Each command prints
  the library path and the modules it loaded. Keep only your own code there.
- `scripts/setup_env.sh` installs Python packages from PyPI within the versions in
  `scripts/requirements.txt`. It does not override an "externally managed" system Python unless
  you set `EMAKI_ALLOW_SYSTEM_PIP=1`.
- Emaki makes no network requests while it renders and needs no API keys. Sound is synthesized
  locally.
