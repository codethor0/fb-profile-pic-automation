"""The Facebook profile-picture automation flow.

The flow was checked by hand against facebook.com in October 2026. Facebook
changes its pages without notice, so expect to adjust the label patterns below
over time. Design constraints:

- Drive the user's *own* browser over CDP: no headless browser, no exported
  cookies, no credential handling at all.
- Scope every DOM lookup as tightly as possible. In particular the file input
  is only ever touched inside the "Choose profile picture" dialog: a
  page-wide ``input[type=file]`` on Facebook can belong to the newsfeed post
  composer, and uploading there would attach the image to a *post draft*.
- Text-pattern selectors, never generated CSS class names, since Facebook A/B
  tests class names constantly; visible labels change far more slowly.
- Randomized pauses between actions instead of fixed delays.

Playwright is imported lazily so the rest of the package (and its unit
tests) work without the browser dependency installed.
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from .config import Settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from playwright.sync_api import Locator, Page

logger = logging.getLogger("fb_pfp")

PROFILE_URL = "https://www.facebook.com/me"

# Visible-label patterns (case-insensitive). Facebook rewrites class names and
# data-* attributes constantly; user-visible text is the stable contract.
AVATAR_NAME_PATTERN = re.compile(r"profile picture", re.IGNORECASE)
MENU_ITEM_PATTERN = r"(choose|update) profile picture"
UPLOAD_FALLBACK_PATTERN = r"upload photo|add photo|choose photo"
# The dialog we drive must mention "profile picture"; unrelated dialogs
# (cookie banners, notifications, the post composer) never match.
DIALOG_TEXT_PATTERN = re.compile(r"profile picture", re.IGNORECASE)
SAVE_BUTTON_PATTERN = r"^save( changes)?$"
NEXT_BUTTON_PATTERNS = [(r"^select photo$", "Select photo"), (r"^next$", "Next")]


class AutomatorError(RuntimeError):
    """Raised when the Facebook flow cannot be completed."""


def _chmod_best_effort(path: Path, mode: int) -> None:
    """Apply private permissions; never fatal (F10 hardening)."""
    try:
        os.chmod(path, mode)
    except OSError as exc:
        logger.debug("chmod %o on %s failed: %s", mode, path, exc)


def _is_login_redirect(url: str) -> bool:
    """True when Facebook redirected the browser to a login or checkpoint page.

    Tests the URL path only, so a profile or photo URL whose name merely
    contains "login" or "checkpoint" is not misclassified.
    """
    path = urlparse(url).path.lower().rstrip("/")
    path = path.removesuffix(".php")
    return path in {"/login", "/checkpoint"} or path.startswith("/checkpoint/")


class FacebookPfpAutomator:
    """Change the profile picture of the logged-in Facebook session."""

    def __init__(
        self,
        settings: Settings,
        *,
        rng: random.Random | None = None,
    ) -> None:
        self._settings = settings
        self._rng = rng or random.Random()
        self._screens = settings.screenshot_dir

    # -- small helpers -----------------------------------------------------

    def _pause(self, page: "Page", base_ms: float, jitter_ms: float = 900.0) -> None:
        """Human-like randomized pause between actions."""
        page.wait_for_timeout(base_ms + self._rng.uniform(0, jitter_ms))

    def _shot(self, page: "Page", name: str, *, force: bool = False) -> None:
        """Save a diagnostic screenshot (only with ``-v``, or when ``force``).

        Screenshots show the user's Facebook page, so they are written only
        for debugging and failures. Never fatal.
        """
        if not (force or self._settings.debug_screenshots):
            return
        try:
            self._screens.mkdir(parents=True, exist_ok=True)
            _chmod_best_effort(self._screens, 0o700)  # screenshots show your Facebook page (F10)
            path = self._screens / name
            page.screenshot(path=str(path), full_page=False)
            _chmod_best_effort(path, 0o600)
        except Exception as exc:  # screenshots are diagnostic, never fatal
            logger.warning("Could not save screenshot %s: %s", name, exc)

    def _find_and_click(
        self,
        page: "Page",
        scope: "Page | Locator",
        pattern: str,
        label: str,
        timeout_ms: int = 12_000,
    ) -> bool:
        """Click the first visible button/menuitem under ``scope`` matching ``pattern``.

        Returns False (after ``timeout_ms``) when nothing matched; never raises
        for lookup failures, which are logged at debug level.
        """
        rx = re.compile(pattern, re.IGNORECASE)
        deadline = time.monotonic() + timeout_ms / 1000

        while time.monotonic() < deadline:
            for locator in (
                scope.get_by_role("button", name=rx),
                scope.get_by_role("menuitem", name=rx),
            ):
                try:
                    first = locator.first
                    if first.is_visible(timeout=500):
                        first.click()
                        logger.info("Clicked '%s'", label)
                        return True
                except Exception as exc:
                    logger.debug("Lookup for '%s' failed, retrying: %s", label, exc)
            page.wait_for_timeout(400)
        logger.warning("No clickable '%s' found within %ds", label, timeout_ms // 1000)
        return False

    def _fail(self, page: "Page", message: str) -> "AutomatorError":
        """Capture a failure screenshot and build the error to raise."""
        self._shot(page, "failure_state.png", force=True)
        return AutomatorError(message)

    @staticmethod
    def _dialog(page: "Page") -> "Locator":
        """The profile-picture dialog (never an unrelated dialog or the composer)."""
        return page.get_by_role("dialog").filter(has_text=DIALOG_TEXT_PATTERN).first

    # -- main flow ----------------------------------------------------------

    def run(self, image: Path) -> None:
        """Execute the full profile-picture change for ``image``.

        Raises:
            AutomatorError: the Facebook flow could not be completed.
            ValueError / OSError: invalid settings (from ``Settings.validate``).
        """
        from playwright.sync_api import sync_playwright

        self._settings.validate()
        logger.info("Chosen image: %s", image)

        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(self._settings.cdp_url)
            # A dedicated tab per run so we never disturb the user's other tabs.
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.new_page()
            try:
                self._open_profile(page)
                self._verify_account(page)
                dialog = self._open_upload_dialog(page)
                self._upload(page, dialog, image)
                if self._settings.dry_run:
                    self._shot(page, "dry_run_state.png")
                    logger.info("--dry-run: stopping before Save")
                    return
                before_src = self._avatar_src(page)
                self._save(page, dialog)
                self._confirm(page, dialog)
                self._verify_picture_changed(page, before_src)
            finally:
                # Only close our own tab. Never browser.close(): on a CDP
                # connection that kills the user's entire Brave session.
                try:
                    page.close()
                except Exception as exc:
                    logger.debug("Could not close automation tab: %s", exc)

    def _open_profile(self, page: "Page") -> None:
        """Open the profile page; raise if Facebook wants a login or checkpoint."""
        logger.info("Opening your profile page...")
        page.goto(PROFILE_URL, wait_until="domcontentloaded")
        self._pause(page, 2800)
        logger.info("Loaded a page on %s", urlparse(page.url).netloc)
        self._shot(page, "step1_loaded.png")

        if _is_login_redirect(page.url):
            self._shot(page, "not_logged_in.png", force=True)
            raise AutomatorError(
                "Facebook is asking to log in (or showing a checkpoint). "
                "log in inside Brave, then rerun."
            )

    def _verify_account(self, page: "Page") -> None:
        """Fail closed unless the connected browser shows the expected account.

        Audit finding F03: an open debug port does not prove *which* browser or
        account we are about to change. When ``FB_PFP_EXPECTED_NAME`` is set,
        the profile page title must contain it (Facebook titles read
        "Name | Facebook"). When unset, we warn and continue.
        """
        expected = self._settings.verify_account_name
        try:
            title = page.title()
        except Exception as exc:
            raise self._fail(page, f"Could not read the profile page title: {exc}") from exc
        if not expected:
            logger.warning(
                "FB_PFP_EXPECTED_NAME is not set; this run cannot verify which "
                "Facebook account the browser is logged into."
            )
            return
        if expected.casefold() not in title.casefold():
            self._shot(page, "wrong_account.png", force=True)
            raise AutomatorError(
                f"The connected browser shows a different account than expected "
                f"({expected!r}; page title: {title!r}). Refusing to change an "
                "unverified account's profile picture."
            )
        logger.info("Verified the profile name matches FB_PFP_EXPECTED_NAME")

    def _avatar_src(self, page: "Page") -> str | None:
        """Current avatar image URL, or None when it cannot be read."""
        try:
            return self._avatar(page).get_attribute("src")
        except Exception as exc:
            logger.debug("Could not read the avatar src: %s", exc)
            return None

    @staticmethod
    def _normalize_src(src: str | None) -> str | None:
        """Drop the query string: CDN parameters vary, the path identifies the image."""
        if not src:
            return None
        return src.split("?", 1)[0]

    def _verify_picture_changed(self, page: "Page", before_src: str | None) -> None:
        """Require the profile to actually show a new avatar after Save.

        Audit finding F06: a closed dialog does not prove the change persisted.
        Skipped when either src is unreadable (better a quiet pass than a false
        failure on a transient read error).
        """
        after_src = self._normalize_src(self._avatar_src(page))
        before = self._normalize_src(before_src)
        if before is None or after_src is None:
            logger.debug("Avatar src unreadable; skipping post-save visual check")
            return
        if after_src == before:
            raise self._fail(
                page,
                "The profile page still shows the previous avatar after Save; "
                "the change did not persist.",
            )
        logger.info("Verified the profile page shows a new avatar after Save")

    def _avatar(self, page: "Page") -> "Locator":
        """The user's own cover avatar.

        Prefers the exact accessible name "Profile picture"; falls back to the
        first page-wide match, which on a profile page is the cover avatar (it
        precedes feed images in DOM order). An exact match can never be a
        "...'s profile picture" image belonging to someone else in the feed.
        """
        exact = page.get_by_role("img", name="Profile picture", exact=True).first
        try:
            if exact.is_visible(timeout=1500):
                return exact
        except Exception as exc:
            logger.debug("Exact avatar match failed, falling back to first match: %s", exc)
        return page.get_by_role("img", name=AVATAR_NAME_PATTERN).first

    def _open_upload_dialog(self, page: "Page") -> "Locator":
        """Click the avatar, choose "profile picture" and return the dialog."""
        # 1. Click the profile-picture avatar on the cover.
        avatar = self._avatar(page)
        try:
            avatar.wait_for(state="visible", timeout=10_000)
            avatar.click()
        except Exception as exc:
            raise self._fail(page, f"Profile-picture avatar not found: {exc}") from exc
        logger.info("Clicked the profile-picture avatar")
        self._pause(page, 1200)

        # 2. The avatar menu offers "Choose/Update profile picture".
        if not self._find_and_click(page, page, MENU_ITEM_PATTERN, "Choose/Update profile picture"):
            raise self._fail(page, "The 'Choose profile picture' menu item did not appear")
        self._pause(page, 2200)
        self._shot(page, "step2_dialog.png")

        dialog = self._dialog(page)
        try:
            dialog.wait_for(state="visible", timeout=10_000)
        except Exception as exc:
            raise self._fail(page, f"The profile-picture dialog did not open: {exc}") from exc
        return dialog

    def _upload(self, page: "Page", dialog: "Locator", image: Path) -> None:
        """Hand ``image`` to the file input inside the dialog (never page-wide)."""
        file_input = dialog.locator("input[type='file']").first  # dialog-scoped, never page-wide
        try:
            file_input.wait_for(state="attached", timeout=10_000)
        except Exception as exc:
            # Some surfaces mount the input only after an explicit click.
            logger.debug("File input not attached yet, trying the upload button: %s", exc)
            if self._find_and_click(page, dialog, UPLOAD_FALLBACK_PATTERN, "Upload photo"):
                self._pause(page, 1800)
            try:
                file_input.wait_for(state="attached", timeout=10_000)
            except Exception as exc2:
                raise self._fail(page, f"Could not hand the image to the dialog: {exc2}") from exc2
        try:
            file_input.set_input_files(str(image))
        except Exception as exc:
            raise self._fail(page, f"Could not hand the image to the dialog: {exc}") from exc
        logger.info("Image handed to the profile-picture dialog")
        self._pause(page, 3800)
        self._shot(page, "step3_uploaded.png")

    def _save(self, page: "Page", dialog: "Locator") -> None:
        """Click Save inside the dialog, passing any intermediate Next step."""
        rx = re.compile(SAVE_BUTTON_PATTERN, re.IGNORECASE)
        save_btn = dialog.get_by_role("button", name=rx).first

        save_visible = False
        try:
            save_visible = save_btn.is_visible(timeout=2000)
        except Exception as exc:
            logger.debug("Save-button visibility check failed, assuming hidden: %s", exc)
            save_visible = False

        if not save_visible:
            # Variant flows insert an intermediate "Select photo"/"Next" step.
            for pattern, label in NEXT_BUTTON_PATTERNS:
                if self._find_and_click(page, dialog, pattern, label):
                    self._pause(page, 2800)
                    save_btn = dialog.get_by_role("button", name=rx).first
                    break

        try:
            save_btn.wait_for(state="visible", timeout=12_000)
            save_btn.click()
        except Exception as exc:
            raise self._fail(
                page, f"Save button never appeared; Facebook's UI may have changed: {exc}"
            ) from exc
        logger.info("Clicked 'Save'")

    def _confirm(self, page: "Page", dialog: "Locator") -> None:
        """Require the dialog to close after Save, then reload the profile."""
        try:
            dialog.wait_for(state="hidden", timeout=30_000)
        except Exception as exc:
            raise self._fail(
                page, f"The profile-picture dialog did not close after Save: {exc}"
            ) from exc
        self._pause(page, 3500)
        page.goto(PROFILE_URL, wait_until="domcontentloaded")
        self._pause(page, 2500)
        self._shot(page, "after_save.png")
        logger.info("Done: profile picture saved and profile reloaded")
