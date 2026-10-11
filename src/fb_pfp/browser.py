"""Attach to Brave via CDP, launching it with a debug port when necessary.

Two hard-won platform details are handled here:

1. macOS TCC: a child process of a script inherits the parent's file-access
   restrictions and cannot write Brave's profile directory (SingletonLock
   fails with "Operation not permitted"). Launching through LaunchServices
   (``open -na``) gives Brave its own TCC identity, so the default profile —
   and therefore the Facebook login — works.
2. A running Brave without the debug port: we ask it to quit gracefully
   (osascript, equivalent to Cmd+Q so session restore keeps tabs) and only
   escalate to SIGTERM if it ignores us.
"""

from __future__ import annotations

import logging
import subprocess
import time
import urllib.request
from pathlib import Path

from .config import Settings

logger = logging.getLogger("fb_pfp")

_LAUNCH_TIMEOUT_S = 20.0
_QUIT_TIMEOUT_S = 15.0


class BrowserError(RuntimeError):
    """Raised when Brave cannot be made ready for automation."""


def _cdp_alive(cdp_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=1) as resp:
            return resp.status == 200
    except (OSError, ValueError):
        return False


def _brave_running(binary: Path) -> bool:
    try:
        out = subprocess.run(
            ["pgrep", "-f", str(binary)],
            capture_output=True,
            text=True,
            check=False,
        )
        return bool(out.stdout.strip())
    except OSError:
        return False


def _quit_brave_gracefully(binary: Path) -> None:
    """Ask Brave to quit (Cmd+Q equivalent), escalate only if it ignores us."""
    subprocess.run(
        ["osascript", "-e", 'quit app "Brave Browser"'],
        capture_output=True,
        check=False,
    )
    deadline = time.monotonic() + _QUIT_TIMEOUT_S
    while time.monotonic() < deadline and _brave_running(binary):
        time.sleep(0.5)
    if _brave_running(binary):
        logger.warning("Graceful quit timed out; sending SIGTERM")
        subprocess.run(["pkill", "-TERM", "-f", str(binary)], check=False)
        time.sleep(3)
    if _brave_running(binary):
        raise BrowserError("Could not quit Brave. Quit it manually (Cmd+Q) and retry.")


def _launch_brave(settings: Settings) -> None:
    """Launch Brave with the debug port via LaunchServices (see module docstring)."""
    subprocess.Popen(  # noqa: S603 — fixed argv list, no shell
        [
            "open",
            "-na",
            str(settings.brave_binary),
            "--args",
            f"--remote-debugging-port={settings.debug_port}",
            f"--user-data-dir={settings.brave_profile}",
            f"--lang={settings.locale}",
            "--no-first-run",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def ensure_brave(settings: Settings) -> None:
    """Guarantee a Brave instance with a live CDP debug port.

    - If a debug session already answers on the port, reuse it.
    - Otherwise quit Brave if it is running, relaunch it with the debug port,
      and wait for the port to come alive.
    """
    if _cdp_alive(settings.cdp_url):
        logger.info("Reusing existing Brave debug session on port %d", settings.debug_port)
        return

    if _brave_running(settings.brave_binary):
        logger.info("Brave is open without the debug port; restarting it gracefully")
        _quit_brave_gracefully(settings.brave_binary)

    logger.info("Launching Brave with remote debugging on the default profile")
    _launch_brave(settings)

    deadline = time.monotonic() + _LAUNCH_TIMEOUT_S
    while time.monotonic() < deadline:
        if _cdp_alive(settings.cdp_url):
            logger.info("Brave debug port is live")
            return
        time.sleep(0.5)
    raise BrowserError(
        f"Brave did not open a debug port within {_LAUNCH_TIMEOUT_S:.0f}s "
        "(updating, blocked, or wrong profile path?)"
    )
