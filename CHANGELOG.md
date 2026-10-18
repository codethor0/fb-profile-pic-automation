# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

## [1.0.4] - 2026-10-18

Fifth independent audit (three publishing-safety findings); all fixed in this release. The v1.0.3 tag predates the rotation fix and the state-directory hardening; this release restores tag-to-code integrity.

### Security

- Dialog selection is name-first and fail-closed. The old locator matched any dialog whose *body text* mentioned "profile picture" and took the first in DOM order; an independent audit reproduced a "Create post" dialog (suggesting a profile-picture angle) capturing the upload and the synthetic Save. The new `_find_dialog` examines every visible dialog individually, requires a `profile picture` accessible name (unnamed shells still qualify via body text, but a dialog with a *different* name never does), requires exactly one candidate, and re-checks uniqueness immediately before Save. Zero or plural candidates abort the run.
- Publishing now fails closed on an unverified account. `FB_PFP_EXPECTED_NAME` was optional: a run that clicks Save warned and continued without knowing which account it was changing. It is now required for every publishing run (`--dry-run` still only warns), and the refusal message names the fix.
- Publishing now verifies the staged preview before Save. After the upload, the dialog's picture-sized preview is pixel-compared against the selected image inside the page (every pixel of a 32x32 reference, per-channel tolerance 24, at most 10 outlier pixels, mirroring the browser extension). A missing preview, an unreadable comparison, or a mismatch aborts before Save. `--dry-run` never reaches this check.
- The state directory is now created owner-only (`0700`) on every flow, including pick-only runs that never write rotation state (previously the mode was only fixed when state was saved). State and lock files reveal usage patterns.
- The macOS app name derived from a custom `FB_PFP_BRAVE_BINARY` bundle path is validated before it is embedded in the AppleScript quit command; a crafted bundle name falls back to the default instead of reaching the script string.

## [1.0.3] - 2026-10-16

Fourth independent audit (14 findings); one HIGH fixed in this release. Also fixes a rotation repeat bug found during final testing.

### Security

- `ensure_brave` now verifies the identity of the browser answering the debug port before attaching. If the port is answered by anything other than Brave (for example Chrome started with its own debug port), the run aborts with a clear error instead of driving the wrong browser and possibly the wrong account (F1). Applies both when reusing an existing session and after launching Brave.

### Fixed

- `--cycle` no longer starts a new round with the image that was just saved. When the last unused image is saved the round resets but keeps that image marked as used, so with two or more images the next pick always differs (before, it repeated with probability 1/N, for example 33% with three images). A single image still repeats, as it must.

### Tests

- Added identity-check coverage for Brave, Chrome, Chromium, Edge and unknown version strings.
- Added rotation coverage for the round-reset case.

## [1.0.2] - 2026-10-11

Third independent audit (12 findings); all resolved.

### Security

- `FB_PFP_EXPECTED_NAME` verifies the browser's logged-in account before any change; a mismatch refuses the run (F03).
- When the tool starts Brave for a run, it now quits Brave when the run finishes, closing the debug port. A pre-existing browser is never quit. Opt out with `FB_PFP_KEEP_BRAVE_OPEN=1` (F04).
- Screenshots are written mode `0600` and the state/screenshot directories mode `0700` (F10).

### Fixed

- A run now fails when the profile page still shows the previous avatar after Save; dialog closure alone no longer counts as success (F06).
- Overlapping runs are serialized with a whole-run lock, so two runs can no longer pick the same image (F07).

### Changed

- `.gitignore` excludes the default image folder, root-level photos, `.env` and local state; CI rejects media outside `docs/assets/` (F05).
- All six CI jobs (tests, security, text, package, hygiene) are required for merging (F08).
- Dependency monitoring restored via Dependabot, plus a `pip-audit` advisory gate in CI (F09).
- Actions updated to current major versions; PEP 639 license metadata (F11).
- The `ImageSource` docstring no longer overpromises Facebook-hosted photo picking (F12).

## [1.0.1] - 2026-10-11

### Security

- `run.sh` now requires `PICS_DIR`. It used to fall back to `~/Downloads`, which could publish an unrelated image.
- Symbolic links and sub-folders in the image folder are ignored.
- The profile URL is no longer written to the log.
- Screenshots are taken only with `-v` or when a run fails.

### Changed

- Rotation state and screenshots default to `~/.fb_pfp/` instead of the current folder.
- In `--cycle` mode an image is marked as used only after Facebook accepted it. Failed runs and dry runs no longer use one up.
- State writes take a file lock, so two runs at the same time cannot corrupt the file.
- The upload dialog is chosen by its text, and the fallback and Next clicks stay inside it.
- A run succeeds only after the profile picture dialog closes following Save.
- The browser app to quit is derived from the configured Brave path.
- Bad `FB_PFP_*` values and damaged state files give a clear message instead of a traceback.
- Unexpected library errors are reported on one line and exit with status 1.
- `FB_PFP_FILE` selects the file source on its own; setting both `FB_PFP_DIR` and `FB_PFP_FILE` is rejected with a clear message.
- A failure to write rotation state after a successful change logs a warning and still exits 0, so a scheduler does not immediately change the picture again.
- Ctrl-C exits 130, and `--cycle` together with `--file` warns instead of being silently ignored.
- The cover avatar prefers an exact "Profile picture" match, so a feed image belonging to someone else cannot be clicked first.
- Login and checkpoint detection tests the URL path, so a profile name containing "login" is not misread as a logout.
- The DevTools URL uses `127.0.0.1`, immune to resolvers that prefer IPv6 for `localhost`.
- Hidden files such as macOS AppleDouble `._*.jpg` are skipped inside `--dir`.
- State writes fsync before the rename, and no exception is swallowed without a debug log line.

### Added

- `fb-pfp` command, `--version` flag and `pyproject.toml`.
- Documentation: architecture notes, scheduling guide, contributing guide, code of conduct and security policy.
- Issue forms, pull request template, sponsor link and code owners.
- CI jobs for a Bandit scan, a dash check and a package build.
- Meta non-affiliation and trademark disclaimer in the README and security policy.
- More tests: 53, up from 15.

### Removed

- Dependabot configuration.
- Planning documents that were not part of the tool.

## [1.0.0] - 2026-10-11

### Added

- Change a Facebook profile picture through a logged-in Brave browser over the local DevTools Protocol.
- Random, no-repeat rotation and fixed-file image sources.
- `--dry-run`, `--cycle`, `-v`, and configuration through `FB_PFP_*` variables.
- `run.sh` for scheduled runs, and GitHub Actions tests on Python 3.11, 3.12 and 3.13.

### Fixed

- Settings validation checked the Brave path before the port range, which made a test fail on machines without Brave.
