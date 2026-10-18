"""Browser-backed regressions for dialog identity (audit finding).

These need a real Chromium via Playwright. In environments without Playwright
or its browsers (the default CI job installs neither) every test here skips;
locally a full Chromium run executes them for real.
"""

from __future__ import annotations

import pytest

from fb_pfp.automator import AutomatorError, FacebookPfpAutomator
from fb_pfp.config import Settings

playwright = pytest.importorskip("playwright.sync_api", reason="playwright not installed")
from playwright.sync_api import sync_playwright  # noqa: E402



# Two tiny solid JPEGs (120x120, q92): the selected photo and a wrong photo.
# Embedded so the tests need no image library.
RED = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAB4AHgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDwSiiivz8/uAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA//2Q=="
BLUE = "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkKDA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAB4AHgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDwqiiiv7NPwQKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA//2Q=="

def _settings(tmp_path) -> Settings:
    return Settings(source_kind="directory", image_dir=tmp_path, screenshot_dir=tmp_path / "s")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        try:
            instance = pw.chromium.launch(headless=True)
        except Exception as exc:  # browsers not downloaded in this environment
            pytest.skip(f"chromium unavailable: {exc}")
        yield instance
        instance.close()


REAL_DIALOG = (
    '<div role="dialog" aria-label="Choose profile picture" id="real">'
    "<h2>Choose profile picture</h2>"
    "<input type='file' accept='image/*'>"
    "<button>Save</button></div>"
)
POST_DIALOG = (
    '<div role="dialog" aria-label="Create post" id="post">'
    "<h2>Create post</h2>"
    "<p>Pick a profile picture angle for this post</p>"
    "<input type='file' accept='image/*,video/*'>"
    "<button>Post</button></div>"
)


def _page(browser, html: str):
    page = browser.new_page()
    page.set_content(f"<!doctype html><html><body>{html}</body></html>")
    return page


def test_named_dialog_wins_over_post_composer_that_mentions_pictures(browser, tmp_path) -> None:
    """Audit reproduction: has_text+.first used to pick the Create post dialog."""
    a = FacebookPfpAutomator(_settings(tmp_path))
    page = _page(browser, POST_DIALOG + REAL_DIALOG)
    try:
        dialog = a._find_dialog(page)
        assert dialog.get_attribute("id") == "real"
    finally:
        page.close()


def test_post_composer_alone_is_rejected(browser, tmp_path) -> None:
    """A dialog with a different name never qualifies, even with matching text."""
    a = FacebookPfpAutomator(_settings(tmp_path))
    page = _page(browser, POST_DIALOG)
    try:
        with pytest.raises(AutomatorError, match="refusing to guess|did not open"):
            a._find_dialog(page, timeout_ms=1500)
    finally:
        page.close()


def test_two_plausible_dialogs_fail_closed(browser, tmp_path) -> None:
    a = FacebookPfpAutomator(_settings(tmp_path))
    page = _page(browser, REAL_DIALOG + REAL_DIALOG.replace('id="real"', 'id="also-real"'))
    try:
        with pytest.raises(AutomatorError, match="refusing to guess"):
            a._find_dialog(page, timeout_ms=1500)
    finally:
        page.close()


def test_unnamed_shell_with_profile_picture_text_qualifies(browser, tmp_path) -> None:
    """Facebook sometimes renders the dialog without an aria-label."""
    shell = (
        '<div role="dialog" id="shell"><h2>Choose profile picture</h2>'
        "<input type='file' accept='image/*'></div>"
    )
    a = FacebookPfpAutomator(_settings(tmp_path))
    page = _page(browser, shell)
    try:
        dialog = a._find_dialog(page)
        assert dialog.get_attribute("id") == "shell"
    finally:
        page.close()


def test_differently_named_shell_with_matching_text_is_rejected(browser, tmp_path) -> None:
    """Name-first rule: 'Create post' body text must not sneak in via the shell path."""
    named_other = (
        '<div role="dialog" aria-label="Create post" id="post">'
        "<h2>Create post</h2><p>Set your profile picture here</p></div>"
    )
    a = FacebookPfpAutomator(_settings(tmp_path))
    page = _page(browser, named_other)
    try:
        with pytest.raises(AutomatorError, match="refusing to guess|did not open"):
            a._find_dialog(page, timeout_ms=1500)
    finally:
        page.close()


def test_save_rechecks_dialog_uniqueness(browser, tmp_path) -> None:
    """A second plausible dialog appearing before Save fails closed."""
    a = FacebookPfpAutomator(_settings(tmp_path))
    page = _page(browser, REAL_DIALOG)
    try:
        dialog = a._find_dialog(page)
        page.evaluate(
            """() => document.body.insertAdjacentHTML('beforeend', `
              <div role="dialog" aria-label="Update profile picture" id="second">
                <h2>Update profile picture</h2></div>`)"""
        )
        with pytest.raises(AutomatorError, match="exactly one"):
            a._assert_dialog_still_unique(page, dialog)
    finally:
        page.close()


def test_preview_verification_accepts_matching_staged_image(browser, tmp_path) -> None:
    """The staged preview showing the selected image verifies and passes."""
    page = _page(browser, REAL_DIALOG)
    try:
        page.evaluate(
            f"""() => {{
              const img = document.createElement('img');
              img.src = 'data:image/jpeg;base64,{RED}';
              img.width = img.height = 168;
              document.getElementById('real').appendChild(img);
            }}"""
        )
        dialog = page.locator("#real")
        image = tmp_path / "selected.jpg"
        import base64

        image.write_bytes(base64.b64decode(RED))
        FacebookPfpAutomator(_settings(tmp_path))._verify_staged_preview(page, dialog, image)
    finally:
        page.close()


def test_preview_verification_refuses_wrong_staged_image(browser, tmp_path) -> None:
    """A staged preview of a different image blocks Save (audit finding 3)."""
    page = _page(browser, REAL_DIALOG)
    try:
        page.evaluate(
            f"""() => {{
              const img = document.createElement('img');
              img.src = 'data:image/jpeg;base64,{BLUE}';
              img.width = img.height = 168;
              document.getElementById('real').appendChild(img);
            }}"""
        )
        dialog = page.locator("#real")
        image = tmp_path / "selected.jpg"
        import base64

        image.write_bytes(base64.b64decode(RED))
        with pytest.raises(AutomatorError, match="does not verify"):
            FacebookPfpAutomator(_settings(tmp_path))._verify_staged_preview(page, dialog, image)
    finally:
        page.close()


def test_preview_verification_refuses_missing_preview(browser, tmp_path) -> None:
    """No picture-sized preview in the dialog means no Save (fail closed)."""
    page = _page(browser, REAL_DIALOG)
    try:
        dialog = page.locator("#real")
        image = tmp_path / "selected.jpg"
        image.write_bytes(b"\xff\xd8\xff")  # content never read: no preview found first
        with pytest.raises(AutomatorError, match="No picture-sized preview"):
            FacebookPfpAutomator(_settings(tmp_path))._verify_staged_preview(page, dialog, image)
    finally:
        page.close()
