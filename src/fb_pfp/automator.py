"""The Facebook profile-picture automation flow.

This is a faithful port of a flow verified live against facebook.com
(2026-10-11, Brave 1.97 / Chromium 155). Design constraints:

- Drive the user's *own* browser over CDP — no headless browser, no exported
  cookies, no credential handling at all.
- Scope every DOM lookup as tightly as possible. In particular the file input
  is only ever touched inside the "Choose profile picture" dialog: a
  page-wide ``input[type=file]`` on Facebook can belong to the newsfeed post
  composer, and uploading there would attach the image to a *post draft*.
- Text-pattern selectors, never generated CSS class names — Facebook A/B
  tests class names constantly; visible labels change far more slowly.
- Randomized pacing between actions so the run does not look like a fixed
  500ms robot loop.

Playwright is imported lazily so the rest of the package (and its unit
tests) work without the browser dependency installed.
"""

from __future__ import annotations

import logging
import random
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .config import Settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from playwright.sync_api import Page

logger = logging.getLogger("fb_pfp")

PROFILE_URL = "https://www.facebook.com/me"

# Visible-label patterns (case-insensitive). Facebook rewrites class names and
# data-* attributes constantly; user-visible text is the stable contract.
AVATAR_NAME_PATTERN = re.compile(r"profile picture", re.IGNORECASE)
MENU_ITEM_PATTERN = r"(choose|update) profile picture"
UPLOAD_FALLBACK_PATTERN = r"upload photo|add photo|choose photo"
SAVE_BUTTON_PATTERN = r"^save( changes)?$"
NEXT_BUTTON_PATTERNS = [(r"^select photo$", "Select photo"), (r"^next$", "Next")]


class AutomatorError(RuntimeError):
    """Raised when the Facebook flow cannot be completed."""


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

    def _shot(self, page: "Page", name: str) -> None:
        try:
            page.screenshot(path=str(self._screens / name), full_page=False)
        except Exception as exc:  # screenshots are diagnostic, never fatal
            logger.warning("Could not save screenshot %s: %s", name, exc)

    def _find_and_click(self, page: "Page", pattern: str, label: str, timeout_ms: int = 12_000) -> bool:
        """Click the first visible button/menuitem whose text matches."""
        import time

        rx = re.compile(pattern, re.IGNORECASE)
        deadline = time.monotonic() + timeout_ms / 1000

        while time.monotonic() < deadline:
            for locator in (
                page.get_by_role("button", name=rx),
                page.get_by_role("menuitem", name=rx),
            ):
                try:
                    first = locator.first
                    if first.is_visible(timeout=500):
                        first.click()
                        logger.info("Clicked '%s'", label)
                        return True
                except Exception:
                    pass
            page.wait_for_timeout(400)
        logger.warning("No clickable '%s' found within %ds", label, timeout_ms // 1000)
        return False

    def _fail(self, page: "Page", message: str) -> "AutomatorError":
        self._shot(page, "failure_state.png")
        return AutomatorError(message)

    # -- main flow ----------------------------------------------------------

    def run(self, image: Path) -> None:
        """Execute the full profile-picture change for ``image``."""
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
                dialog = self._open_upload_dialog(page)
                self._upload(page, dialog, image)
                if self._settings.dry_run:
                    self._shot(page, "dry_run_state.png")
                    logger.info("--dry-run: stopping before Save")
                    return
                self._save(page, dialog)
                self._confirm(page)
            finally:
                # Only close our own tab. Never browser.close(): on a CDP
                # connection that kills the user's entire Brave session.
                try:
                    page.close()
                except Exception:
                    pass

    def _open_profile(self, page: "Page") -> None:
        logger.info("Opening your profile page...")
        page.goto(PROFILE_URL, wait_until="domcontentloaded")
        self._pause(page, 2800)
        logger.info("Loaded: %s", page.url)
        self._shot(page, "step1_loaded.png")

        if "login" in page.url or "checkpoint" in page.url:
            self._shot(page, "not_logged_in.png")
            raise AutomatorError(
                "Facebook is asking to log in (or showing a checkpoint) — "
                "log in inside Brave, then rerun."
            )

    def _open_upload_dialog(self, page: "Page") -> "object":
        # 1. Click the profile-picture avatar on the cover.
        avatar = page.get_by_role("img", name=AVATAR_NAME_PATTERN).first
        try:
            avatar.wait_for(state="visible", timeout=10_000)
            avatar.click()
        except Exception as exc:
            raise self._fail(page, f"Profile-picture avatar not found: {exc}") from exc
        logger.info("Clicked the profile-picture avatar")
        self._pause(page, 1200)

        # 2. The avatar menu offers "Choose/Update profile picture".
        if not self._find_and_click(page, MENU_ITEM_PATTERN, "Choose/Update profile picture"):
            raise self._fail(page, "The 'Choose profile picture' menu item did not appear")
        self._pause(page, 2200)
        self._shot(page, "step2_dialog.png")

        dialog = page.get_by_role("dialog").first
        try:
            dialog.wait_for(state="visible", timeout=10_000)
        except Exception as exc:
            raise self._fail(page, f"The profile-picture dialog did not open: {exc}") from exc
        return dialog

    def _upload(self, page: "Page", dialog: "object", image: Path) -> None:
        file_input = dialog.locator("input[type='file']").first  # dialog-scoped, never page-wide
        try:
            file_input.wait_for(state="attached", timeout=10_000)
        except Exception:
            # Some surfaces mount the input only after an explicit click.
            if self._find_and_click(page, UPLOAD_FALLBACK_PATTERN, "Upload photo"):
                self._pause(page, 1800)
            file_input.wait_for(state="attached", timeout=10_000)
        file_input.set_input_files(str(image))
        logger.info("Image handed to the profile-picture dialog")
        self._pause(page, 3800)
        self._shot(page, "step3_uploaded.png")

    def _save(self, page: "Page", dialog: "object") -> None:
        rx = re.compile(SAVE_BUTTON_PATTERN, re.IGNORECASE)
        save_btn = dialog.get_by_role("button", name=rx).first

        save_visible = False
        try:
            save_visible = save_btn.is_visible(timeout=2000)
        except Exception:
            save_visible = False

        if not save_visible:
            # Variant flows insert an intermediate "Select photo"/"Next" step.
            for pattern, label in NEXT_BUTTON_PATTERNS:
                if self._find_and_click(page, pattern, label):
                    self._pause(page, 2800)
                    save_btn = dialog.get_by_role("button", name=rx).first
                    break

        try:
            save_btn.wait_for(state="visible", timeout=12_000)
            save_btn.click()
        except Exception as exc:
            raise self._fail(
                page, f"Save button never appeared — Facebook's UI may have changed: {exc}"
            ) from exc
        logger.info("Clicked 'Save'")

    def _confirm(self, page: "Page") -> None:
        self._pause(page, 3500)
        page.goto(PROFILE_URL, wait_until="domcontentloaded")
        self._pause(page, 2500)
        self._shot(page, "after_save.png")
        logger.info("Done — profile reloaded; see after_save.png")
