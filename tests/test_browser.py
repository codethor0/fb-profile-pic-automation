"""Pure-function tests for browser helpers. Offline."""

from __future__ import annotations

from pathlib import Path

from fb_pfp.browser import _app_name, _cdp_alive, _is_brave


def test_app_name_from_bundle_path() -> None:
    p = Path("/Applications/Brave Browser Beta.app/Contents/MacOS/Brave Browser Beta")
    assert _app_name(p) == "Brave Browser Beta"


def test_app_name_default_for_plain_binary() -> None:
    assert _app_name(Path("/usr/local/bin/brave")) == "Brave Browser"


def test_app_name_rejects_crafted_bundle_name() -> None:
    """Audit finding CLI-2: a crafted .app name must not reach the AppleScript literal."""
    assert _app_name(Path('/Applications/Evil"Name.app/Contents/MacOS/x')) == "Brave Browser"
    assert _app_name(Path("/Applications/Evil\\Name.app/Contents/MacOS/x")) == "Brave Browser"
    assert _app_name(Path("/Applications/Evil;Name.app/Contents/MacOS/x")) == "Brave Browser"


def test_cdp_alive_false_when_nothing_listens() -> None:
    """A closed loopback port is reported as dead, not as an exception."""
    assert _cdp_alive("http://127.0.0.1:1") is False


def test_is_brave_accepts_brave_variants() -> None:
    assert _is_brave("Brave Browser 155.1.97.56") is True
    assert _is_brave("Brave Browser Beta 156.1.2.3") is True
    assert _is_brave("brave 1.0") is True


def test_is_brave_rejects_other_browsers() -> None:
    """Audit finding F1: the answering browser must be verified as Brave."""
    assert _is_brave("Chrome/155.0.8059.40") is False
    assert _is_brave("Chromium/155.0.8059.40") is False
    assert _is_brave("Microsoft Edge 155.0.0.0") is False
    assert _is_brave("?") is False
