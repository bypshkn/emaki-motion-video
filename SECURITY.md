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
- Emaki makes no network requests while it renders. Music and sound effects are synthesized
  locally.
- The one exception is optional: the generated voice-over (`mv.py tts`) sends the voice-over
  script text to Google Cloud Text-to-Speech through curl, with your own API key. Nothing is sent
  unless you run that command with a key in place.
- The key is read only from `secrets/google-tts-key.txt`: the folder in `MV_TTS_SECRETS`, else
  the first `secrets/` walking up from the project, which stops at your home folder (outside
  home, two levels above the project). It reaches curl through stdin, never in a command line,
  a URL or a log. This repository's .gitignore excludes `secrets/`. Restrict the key to the
  Text-to-Speech API in the Google Cloud console.
