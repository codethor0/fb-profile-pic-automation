"""Attach to Brave via CDP, launching it with a debug port when necessary.

Two platform details are handled here:

1. macOS TCC: a child process of a script inherits the parent's file-access
   restrictions and cannot write Brave's profile directory (SingletonLock
   fails with "Operation not permitted"). Launching through LaunchServices
   (``open -na``) gives Brave its own TCC identity, so the default profile,
   and therefore the Facebook login, works.
2. A running Brave without the debug port: we ask it to quit gracefully
   (osascript, equivalent to Cmd+Q so session restore keeps tabs) and only
   escalate to SIGTERM if it ignores us.
"""

from __future__ import annotations

import logging
import re
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


def _app_name(binary: Path) -> str:
    """Return the macOS app name (e.g. "Brave Browser") that owns ``binary``.

    The name is embedded in an AppleScript string literal by
    ``_quit_brave_gracefully``, so a crafted bundle name must never reach
    that string: anything outside a conservative printable set falls back
    to the default instead of risking AppleScript injection.
    """
    for parent in binary.parents:
        if parent.suffix == ".app":
            name = parent.stem
            return name if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]*", name) else "Brave Browser"
    return "Brave Browser"


def _cdp_probe(cdp_url: str) -> str | None:
    """Return the ``Browser`` version string if a DevTools endpoint answers.

    The string is logged so the user can see *which* browser answered the
    port (audit finding F03: an open port alone does not prove it is Brave).
    """
    try:
        # cdp_url is always http://127.0.0.1:<int port> (Settings.cdp_url).
        with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=1) as resp:  # nosec B310
            if resp.status != 200:
                return None
            import json

            return str(json.loads(resp.read()).get("Browser", "?"))
    except (OSError, ValueError) as exc:
        logger.debug("No DevTools endpoint answering on %s: %s", cdp_url, exc)
        return None


def _is_brave(browser_string: str) -> bool:
    """True if a DevTools ``Browser`` version string identifies Brave."""
    return "brave" in browser_string.lower()


def _cdp_alive(cdp_url: str) -> bool:
    """True if a DevTools endpoint answers on the local ``cdp_url``."""
    return _cdp_probe(cdp_url) is not None


def _brave_running(binary: Path) -> bool:
    """True if a process whose command line contains ``binary`` is running."""
    try:
        out = subprocess.run(
            ["pgrep", "-f", str(binary)],
            capture_output=True,
            text=True,
            check=False,
        )
        return bool(out.stdout.strip())
    except OSError as exc:
        logger.debug("pgrep unavailable: %s", exc)
        return False


def _quit_brave_gracefully(binary: Path) -> None:
    """Ask Brave to quit (Cmd+Q equivalent), escalate only if it ignores us."""
    subprocess.run(
        ["osascript", "-e", f'quit app "{_app_name(binary)}"'],
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
    subprocess.Popen(  # noqa: S603 (fixed argv list, no shell)
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


def ensure_brave(settings: Settings) -> str:
    """Guarantee a Brave instance with a live CDP debug port.

    - If a debug session already answers on the port, reuse it.
    - Otherwise quit Brave if it is running, relaunch it with the debug port,
      and wait for the port to come alive.

    Returns:
        ``"reused"`` when an existing session answered (the tool does not own
        that browser and must not shut it down), or ``"launched"`` when this
        call started Brave (the caller should shut it down after the run,
        unless ``settings.keep_brave_open``).
    """
    answering = _cdp_probe(settings.cdp_url)
    if answering is not None:
        if not _is_brave(answering):
            raise BrowserError(
                f"Port {settings.debug_port} is answered by {answering}, not Brave. "
                "Close that browser or set FB_PFP_PORT to a free port, then retry."
            )
        logger.info("Reusing existing debug session on port %d (%s)", settings.debug_port, answering)
        return "reused"

    if _brave_running(settings.brave_binary):
        logger.info("Brave is open without the debug port; restarting it gracefully")
        _quit_brave_gracefully(settings.brave_binary)

    logger.info("Launching Brave with remote debugging on the default profile")
    _launch_brave(settings)

    deadline = time.monotonic() + _LAUNCH_TIMEOUT_S
    while time.monotonic() < deadline:
        answering = _cdp_probe(settings.cdp_url)
        if answering is not None:
            if not _is_brave(answering):
                raise BrowserError(
                    f"Port {settings.debug_port} is answered by {answering} instead of the "
                    "Brave instance this run launched. Set FB_PFP_PORT to a free port, then retry."
                )
            logger.info("Brave debug port is live")
            return "launched"
        time.sleep(0.5)
    raise BrowserError(
        f"Brave did not open a debug port within {_LAUNCH_TIMEOUT_S:.0f}s "
        "(updating, blocked, or wrong profile path?)"
    )


def shutdown_brave(settings: Settings, mode: str) -> None:
    """Close the debug-enabled browser after a run, but only if we launched it.

    Never touches a browser the user already had running (audit finding F04:
    do not silently kill the user's main browser). Best effort: a failure to
    quit is logged, never raised.
    """
    if mode != "launched" or settings.keep_brave_open:
        return
    try:
        logger.info("Run finished; quitting the Brave instance this run started")
        _quit_brave_gracefully(settings.brave_binary)
    except Exception as exc:  # cleanup must never fail the run
        logger.warning("Could not quit Brave after the run: %s", exc)
