"""Open a link in whatever the desktop uses.

Terminal hyperlinks (OSC 8) are not an option here: curses owns the screen and
escape sequences written through it are not reliably passed on. Shelling out
to the platform opener is what career-ops' TUI does too, and it works the same
in every terminal.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def opener() -> list[str] | None:
    if sys.platform == "darwin":
        return ["open"]
    if sys.platform.startswith("win"):
        return ["cmd", "/c", "start", ""]
    for candidate in ("xdg-open", "gio", "wslview"):
        if shutil.which(candidate):
            return [candidate, "open"] if candidate == "gio" else [candidate]
    return None


def open_url(url: str) -> str:
    """Returns what to tell the user; never raises."""
    if not url:
        return "no link on this one"
    command = opener()
    if command is None:
        return f"no way to open links here — {url}"
    try:
        subprocess.run([*command, url], check=True, capture_output=True,
                       timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"could not open it: {exc}"
    return "opened in the browser"


def open_path(path) -> str:
    """Open a local file in whatever the desktop uses for it.

    Same mechanism as a link, different message: "opened in the browser" is
    wrong and briefly confusing when what opened was a PDF viewer.
    """
    if not path or not Path(path).exists():
        return "not there to open"
    result = open_url(str(path))
    return "opened" if result == "opened in the browser" else result
