"""Pure-function tests for browser helpers. Offline."""

from __future__ import annotations

from pathlib import Path

from fb_pfp.browser import _app_name, _cdp_alive


def test_app_name_from_bundle_path() -> None:
    p = Path("/Applications/Brave Browser Beta.app/Contents/MacOS/Brave Browser Beta")
    assert _app_name(p) == "Brave Browser Beta"


def test_app_name_default_for_plain_binary() -> None:
    assert _app_name(Path("/usr/local/bin/brave")) == "Brave Browser"


def test_cdp_alive_false_when_nothing_listens() -> None:
    """A closed loopback port is reported as dead, not as an exception."""
    assert _cdp_alive("http://127.0.0.1:1") is False
