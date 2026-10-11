"""Automator tests that need neither a browser nor playwright installed."""

from __future__ import annotations

import random
from pathlib import Path

from fb_pfp.automator import (
    DIALOG_TEXT_PATTERN,
    SAVE_BUTTON_PATTERN,
    FacebookPfpAutomator,
    _is_login_redirect,
)
from fb_pfp.config import Settings


class _Page:
    """Records pauses and screenshots; no real browser."""

    def __init__(self) -> None:
        self.waits: list[float] = []
        self.shots: list[str] = []

    def wait_for_timeout(self, ms: float) -> None:
        self.waits.append(ms)

    def screenshot(self, path: str, full_page: bool = False) -> None:
        self.shots.append(Path(path).name)


def _settings(tmp_path: Path, **kw) -> Settings:
    return Settings(source_kind="directory", image_dir=tmp_path, screenshot_dir=tmp_path / "s", **kw)


def test_pause_is_randomized_and_injectable(tmp_path: Path) -> None:
    page = _Page()
    a = FacebookPfpAutomator(_settings(tmp_path), rng=random.Random(1))
    for _ in range(5):
        a._pause(page, 1000)  # type: ignore[arg-type]
    assert len(set(page.waits)) == 5 and all(1000 <= w <= 1900 for w in page.waits)


def test_screenshots_only_when_debugging_or_failing(tmp_path: Path) -> None:
    page = _Page()
    quiet = FacebookPfpAutomator(_settings(tmp_path))
    quiet._shot(page, "step1.png")  # type: ignore[arg-type]
    assert page.shots == []
    quiet._shot(page, "failure_state.png", force=True)  # type: ignore[arg-type]
    assert page.shots == ["failure_state.png"]
    loud = FacebookPfpAutomator(_settings(tmp_path, debug_screenshots=True))
    loud._shot(page, "step1.png")  # type: ignore[arg-type]
    assert page.shots[-1] == "step1.png"


def test_dialog_pattern_ignores_unrelated_dialogs() -> None:
    assert DIALOG_TEXT_PATTERN.search("Choose profile picture")
    assert DIALOG_TEXT_PATTERN.search("Update profile picture")
    assert not DIALOG_TEXT_PATTERN.search("Create post")
    assert not DIALOG_TEXT_PATTERN.search("Accept cookies")


def test_save_pattern_is_exact() -> None:
    import re

    rx = re.compile(SAVE_BUTTON_PATTERN, re.IGNORECASE)
    assert rx.match("Save") and rx.match("Save changes")
    assert not rx.match("Save to drafts") and not rx.match("Don't save")


class TestLoginRedirect:
    """F7: only a real login/checkpoint path triggers the not-logged-in error."""

    def test_login_paths(self) -> None:
        assert _is_login_redirect("https://www.facebook.com/login")
        assert _is_login_redirect("https://www.facebook.com/login.php")
        assert _is_login_redirect("https://www.facebook.com/checkpoint/15072123")

    def test_profile_and_photo_urls_do_not_match(self) -> None:
        assert not _is_login_redirect("https://www.facebook.com/login.smith")
        assert not _is_login_redirect("https://www.facebook.com/photo.php?fbid=1")
        assert not _is_login_redirect("https://www.facebook.com/me")


class _FakeLocator:
    def __init__(self, visible: bool = True, raises: bool = False) -> None:
        self._visible = visible
        self._raises = raises

    @property
    def first(self) -> "_FakeLocator":
        return self  # playwright Locator.first; identity keeps the test simple

    def is_visible(self, timeout: float = 0) -> bool:
        if self._raises:
            raise RuntimeError("detached")
        return self._visible


class _FakeAvatarPage:
    """Records which get_by_role variants the avatar lookup tries."""

    def __init__(self, exact: _FakeLocator, loose: _FakeLocator) -> None:
        self._exact = exact
        self._loose = loose
        self.exact_calls = 0
        self.loose_calls = 0

    def get_by_role(self, role, name=None, exact=False):
        if exact:
            self.exact_calls += 1
            return self._exact
        self.loose_calls += 1
        return self._loose


def test_avatar_prefers_exact_name(tmp_path: Path) -> None:
    """F6: an exact "Profile picture" match wins over a page-wide regex."""
    page = _FakeAvatarPage(exact=_FakeLocator(visible=True), loose=_FakeLocator())
    a = FacebookPfpAutomator(_settings(tmp_path))
    avatar = a._avatar(page)  # type: ignore[arg-type]
    assert avatar is page._exact
    assert page.exact_calls == 1 and page.loose_calls == 0


def test_avatar_falls_back_to_first_match(tmp_path: Path) -> None:
    page = _FakeAvatarPage(exact=_FakeLocator(visible=False), loose=_FakeLocator())
    a = FacebookPfpAutomator(_settings(tmp_path))
    assert a._avatar(page) is page._loose  # type: ignore[arg-type]

    page2 = _FakeAvatarPage(exact=_FakeLocator(raises=True), loose=_FakeLocator())
    assert a._avatar(page2) is page2._loose  # type: ignore[arg-type]


class _TitledPage(_Page):
    """Adds title() and url for account-verification tests."""

    def __init__(self, title: str, url: str = "https://www.facebook.com/me") -> None:
        super().__init__()
        self._title = title
        self.url = url

    def title(self) -> str:
        return self._title


def test_account_verified_when_expected_name_matches(tmp_path: Path) -> None:
    a = FacebookPfpAutomator(_settings(tmp_path, verify_account_name="Ada Lovelace"))
    page = _TitledPage("Ada Lovelace | Facebook")
    a._verify_account(page)  # type: ignore[arg-type] - must not raise


def test_account_refused_when_title_shows_other_account(tmp_path: Path) -> None:
    import pytest

    from fb_pfp.automator import AutomatorError

    a = FacebookPfpAutomator(_settings(tmp_path, verify_account_name="Ada Lovelace"))
    page = _TitledPage("Someone Else | Facebook")
    with pytest.raises(AutomatorError, match="different account"):
        a._verify_account(page)  # type: ignore[arg-type]


def test_account_check_skipped_without_expected_name(
    tmp_path: Path, caplog: pytest.LogCaptureFixture[str]
) -> None:
    a = FacebookPfpAutomator(_settings(tmp_path))
    a._verify_account(_TitledPage("Anyone | Facebook"))  # type: ignore[arg-type]
    assert "cannot verify" in caplog.text


def test_normalize_src_strips_query_string() -> None:
    assert FacebookPfpAutomator._normalize_src("https://cdn.example.com/a.jpg?x=1") == (
        "https://cdn.example.com/a.jpg"
    )
    assert FacebookPfpAutomator._normalize_src(None) is None
    assert FacebookPfpAutomator._normalize_src("") is None


def test_picture_changed_refused_when_avatar_unchanged(tmp_path: Path) -> None:
    """F06: a closed dialog with the same avatar is a failure, not a success."""
    import pytest

    from fb_pfp.automator import AutomatorError

    a = FacebookPfpAutomator(_settings(tmp_path))
    a._avatar_src = lambda page: "https://cdn.example.com/old.jpg?v=2"  # type: ignore[method-assign]
    page = _Page()
    with pytest.raises(AutomatorError, match="previous avatar"):
        a._verify_picture_changed(page, "https://cdn.example.com/old.jpg?v=1")


def test_picture_changed_passes_when_avatar_differs(tmp_path: Path) -> None:
    a = FacebookPfpAutomator(_settings(tmp_path))
    a._avatar_src = lambda page: "https://cdn.example.com/new.jpg"  # type: ignore[method-assign]
    a._verify_picture_changed(_Page(), "https://cdn.example.com/old.jpg")  # must not raise


def test_picture_changed_skipped_when_src_unreadable(tmp_path: Path) -> None:
    a = FacebookPfpAutomator(_settings(tmp_path))
    a._avatar_src = lambda page: None  # type: ignore[method-assign]
    a._verify_picture_changed(_Page(), "https://cdn.example.com/old.jpg")  # must not raise
