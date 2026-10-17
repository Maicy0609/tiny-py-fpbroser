"""Minimal fingerprint browser launcher (Windows x64 only, Python 3.14+).

Run:      python src/fpbrowser.py
Requires: pip install playwright
          (no `playwright install` needed, the installed Chrome/Chromium is used)

Modules, all in src/ (flat, no package):
    config.py       paths and fingerprint constants
    console.py      console colours, key input and termination handling
    fingerprint.py  injected init script, media devices, voices, font hiding
    profiles.py     profile creation, upgrade, storage and selection
    browser.py      Chrome discovery, network policy, Playwright session
    fpbrowser.py    entry point

Layout relative to the repository root:
    profiles/<name>.json   browser parameters (reusable)
    data/<name>/           Chrome user-data-dir (cookies, local storage, ...)
"""

import platform
import sys

from browser import find_browser, run_browser
from console import error, info, mark_shutdown_done, setup_console
from profiles import choose_profile, upgrade_profile


def main() -> int:
    if sys.platform != "win32" or platform.machine().upper() not in {"AMD64", "X86_64"}:
        print("ERROR: this tool supports Windows x64 only.", file=sys.stderr)
        return 1
    try:
        restore = setup_console()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    try:
        path, profile = choose_profile()
        upgrade_profile(path, profile)
        exe = find_browser()
        info(f"Using browser: {exe}")
        run_browser(profile, exe)
    except RuntimeError as exc:
        error(str(exc))
        return 1
    finally:
        restore()
        mark_shutdown_done()
    return 0


if __name__ == "__main__":
    sys.exit(main())
