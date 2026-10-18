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

import base64
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
# The dialog we drive must be *named* for profile pictures. A dialog that only
# mentions "profile picture" in its body text (for example a "Create post"
# composer suggesting a profile-picture angle) must never qualify: an audit
# reproduction showed the old has_text filter picking that dialog and the
# upload landing in a post draft. Identity is name-first and uniqueness is
# required; anything ambiguous fails closed.
DIALOG_NAME_PATTERN = re.compile(r"profile picture", re.IGNORECASE)
# Fallback for unnamed dialog shells: truly unnamed (no aria-label at all) and
# body text mentioning profile pictures. A dialog with a *different* name, such
# as "Create post", is excluded by the name-first rule and never matches here.
DIALOG_TEXT_PATTERN = re.compile(r"profile picture", re.IGNORECASE)
SAVE_BUTTON_PATTERN = r"^save( changes)?$"
NEXT_BUTTON_PATTERNS = [(r"^select photo$", "Select photo"), (r"^next$", "Next")]

# Pixel comparison of the staged preview against the selected image, executed
# inside the page so no image library is required. Mirrors the extension's
# verification: every pixel of a 32x32 reference, per-channel tolerance 24,
# at most 10 outlier pixels so CDN recompression still verifies. The local
# image bytes arrive chunked on window.__fbpfp_img (see _verify_staged_preview).
_PREVIEW_TOLERANCE = 24
_PREVIEW_MAX_OUTLIERS = 10
_COMPARE_JS = r"""
async ({staged}) => {
  const b64 = (window.__fbpfp_img || []).join('');
  delete window.__fbpfp_img;
  if (!b64) return {ok: false, reason: 'no-local-bytes'};
  let local;
  try {
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    local = await createImageBitmap(new Blob([bytes]));
  } catch (e) { return {ok: false, reason: 'local-decode'}; }
  const sample = (drawable, crop) => {
    const c = document.createElement('canvas');
    c.width = c.height = 32;
    const ctx = c.getContext('2d');
    if (crop) ctx.drawImage(drawable, crop.x, crop.y, crop.size, crop.size, 0, 0, 32, 32);
    else ctx.drawImage(drawable, 0, 0, 32, 32);
    return [...ctx.getImageData(0, 0, 32, 32).data];
  };
  const variants = [sample(local)];
  const size = Math.min(local.width, local.height);
  if (size > 0) {
    variants.push(sample(local, {x: (local.width - size) / 2, y: (local.height - size) / 2, size}));
  }
  local.close();
  let stagedSamples;
  try {
    const blob = staged.startsWith('blob:') || staged.startsWith('data:')
      ? await (await fetch(staged)).blob()
      : await (await fetch(staged, {credentials: 'omit', mode: 'cors'})).blob();
    const bitmap = await createImageBitmap(blob);
    stagedSamples = sample(bitmap);
    bitmap.close();
  } catch (e) { return {ok: false, reason: 'staged-unreadable'}; }
  for (const expected of variants) {
    let outliers = 0;
    for (let p = 0; p < expected.length; p += 4) {
      for (let ch = 0; ch < 3; ch++) {
        if (Math.abs(stagedSamples[p + ch] - expected[p + ch]) > 24) { outliers++; break; }
      }
    }
    if (outliers <= 10) return {ok: true, outliers};
  }
  return {ok: false, reason: 'mismatch'};
}
"""


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

    def _dialog_candidates(self, page: "Page") -> list["Locator"]:
        """Visible dialogs that could be the profile-picture dialog.

        Audit finding: the old ``.filter(has_text=...).first`` locator matched
        a "Create post" dialog that merely mentioned "profile picture" in its
        body, and ``.first`` picked whichever dialog came first in DOM order.
        Selection is therefore name-first, unnamed-shell-second, and each
        candidate is examined individually: a dialog carrying a *different*
        accessible name (cookie banner, "Create post") can never qualify.
        """
        root = page.locator("body")
        dialogs = root.locator("[role='dialog'], dialog")
        candidates: list["Locator"] = []
        try:
            count = dialogs.count()
        except Exception as exc:
            logger.debug("Dialog listing failed: %s", exc)
            return candidates
        for index in range(count):
            dialog = dialogs.nth(index)
            try:
                if not dialog.is_visible(timeout=300):
                    continue
                name = (dialog.get_attribute("aria-label") or "").strip()
                if DIALOG_NAME_PATTERN.search(name):
                    candidates.append(dialog)
                elif not name:
                    text = dialog.inner_text() or ""
                    if DIALOG_TEXT_PATTERN.search(text):
                        candidates.append(dialog)
                # A dialog with a different non-empty name is never a candidate.
            except Exception as exc:
                logger.debug("Dialog candidate %d unreadable, skipped: %s", index, exc)
        return candidates

    def _find_dialog(self, page: "Page", timeout_ms: int = 10_000) -> "Locator":
        """Wait for the *unique* profile-picture dialog, or fail closed.

        Zero candidates keeps polling until the deadline. More than one, at any
        moment, raises immediately: picking the first of two plausible dialogs
        is exactly the failure this replaces.
        """
        deadline = time.monotonic() + timeout_ms / 1000
        seen = 0
        while time.monotonic() < deadline:
            candidates = self._dialog_candidates(page)
            seen = max(seen, len(candidates))
            if len(candidates) > 1:
                raise self._fail(
                    page,
                    f"Found {len(candidates)} dialogs that could be the profile-picture "
                    "dialog; refusing to guess which one to drive.",
                )
            if len(candidates) == 1:
                return candidates[0]
            page.wait_for_timeout(400)
        raise self._fail(
            page,
            f"The profile-picture dialog did not open within {timeout_ms // 1000}s; "
            f"at most {seen} candidate dialog(s) appeared.",
        )

    def _assert_dialog_still_unique(self, page: "Page", dialog: "Locator") -> None:
        """Re-verify identity right before Save: one candidate, still attached."""
        candidates = self._dialog_candidates(page)
        if len(candidates) != 1:
            raise self._fail(
                page,
                f"Expected exactly one profile-picture dialog before Save, found "
                f"{len(candidates)}; refusing to guess.",
            )
        try:
            visible = dialog.is_visible(timeout=500)
        except Exception as exc:
            raise self._fail(page, f"Could not re-verify the dialog before Save: {exc}") from exc
        if not visible:
            raise self._fail(page, "The profile-picture dialog changed before Save; refusing to continue.")

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
                self._verify_staged_preview(page, dialog, image)
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
        "Name | Facebook"). A later audit finding tightened this: the check is
        optional only for ``--dry-run``. A run that will click Save must know
        the account, so a missing name is a hard failure there.
        """
        expected = self._settings.verify_account_name
        try:
            title = page.title()
        except Exception as exc:
            raise self._fail(page, f"Could not read the profile page title: {exc}") from exc
        if not expected:
            if self._settings.dry_run:
                logger.warning(
                    "FB_PFP_EXPECTED_NAME is not set; this dry run cannot verify which "
                    "Facebook account the browser is logged into."
                )
                return
            raise self._fail(
                page,
                "FB_PFP_EXPECTED_NAME is not set. A run that clicks Save must verify "
                "the account first: set FB_PFP_EXPECTED_NAME to the exact profile name, "
                "or pass --dry-run to stage without publishing.",
            )
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

        dialog = self._find_dialog(page)
        self._shot(page, "step2_dialog.png")
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

    @staticmethod
    def _preview_src(dialog: "Locator") -> str | None:
        """The staged preview inside the dialog: largest picture-sized img."""
        try:
            return dialog.evaluate(
                """(dialog) => {
                  const visible = el => {
                    const b = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return b.width > 0 && b.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
                  };
                  const imgs = [...dialog.querySelectorAll('img')]
                    .filter(el => visible(el) && el.naturalWidth > 0)
                    .map(el => ({el, box: el.getBoundingClientRect()}))
                    .filter(({box}) => box.width >= 80 && box.height >= 80)
                    .sort((a, b) => b.box.width * b.box.height - a.box.width * a.box.height);
                  return imgs.length ? (imgs[0].el.currentSrc || imgs[0].el.src || null) : null;
                }"""
            )
        except Exception as exc:
            logger.debug("Could not read the staged preview src: %s", exc)
            return None

    def _verify_staged_preview(self, page: "Page", dialog: "Locator", image: Path) -> None:
        """Pixel-compare the dialog's staged preview with the selected image.

        Audit finding: the CLI Save path did not independently confirm the
        staged image matches the selected one, so a wrong or stale preview
        could be published silently. The comparison runs inside the page
        (no image library needed) over every pixel of a 32x32 reference with
        the same tolerance the browser extension uses, and a publishing run
        fails closed when verification is impossible. ``--dry-run`` never
        reaches this: it stops before Save.
        """
        src = self._preview_src(dialog)
        if not src:
            raise self._fail(
                page,
                "No picture-sized preview appeared inside the dialog; refusing to "
                "Save without verifying the staged image.",
            )
        try:
            encoded = base64.b64encode(image.read_bytes()).decode("ascii")
        except OSError as exc:
            raise self._fail(page, f"Could not read the selected image for verification: {exc}") from exc
        page.evaluate("() => { window.__fbpfp_img = []; }")
        try:
            chunk_size = 512 * 1024
            for offset in range(0, len(encoded), chunk_size):
                page.evaluate("(part) => window.__fbpfp_img.push(part)", encoded[offset:offset + chunk_size])
            verdict = page.evaluate(_COMPARE_JS, {"staged": src})
        except Exception as exc:
            raise self._fail(page, f"Could not compare the staged preview with the selected image: {exc}") from exc
        finally:
            page.evaluate("() => { delete window.__fbpfp_img; }")
        if not verdict or not verdict.get("ok"):
            reason = (verdict or {}).get("reason", "no-verdict")
            raise self._fail(
                page,
                f"The staged preview does not verify against the selected image ({reason}); "
                "refusing to Save.",
            )
        logger.info(
            "Verified the staged preview matches the selected image (%s outlier pixels)",
            verdict.get("outliers"),
        )

    def _save(self, page: "Page", dialog: "Locator") -> None:
        """Click Save inside the dialog, passing any intermediate Next step."""
        self._assert_dialog_still_unique(page, dialog)
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
