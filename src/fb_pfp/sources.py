"""Image sources.

An image source answers one question: "which picture should become the profile
picture right now?" Implement :class:`ImageSource` to add new strategies — for
example, picking from photos already uploaded to Facebook instead of local
files. The automator does not care where the image came from.
"""

from __future__ import annotations

import json
import random
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

from .config import IMAGE_EXTENSIONS


class SourceError(RuntimeError):
    """Raised when an image source cannot produce an image."""


@runtime_checkable
class ImageSource(Protocol):
    """Strategy protocol: produce the next image to upload."""

    def pick(self) -> Path:
        """Return the absolute path of the image to use next."""
        ...


class SingleFileSource:
    """Always returns the same file."""

    def __init__(self, path: Path) -> None:
        self._path = path.expanduser().resolve()

    def pick(self) -> Path:
        if not self._path.is_file():
            raise SourceError(f"Image file not found: {self._path}")
        return self._path


class DirectorySource:
    """Picks an image from a directory.

    Modes:
        random — uniform random choice every time (repeats allowed)
        cycle  — no repeats until every image has been used, then rotation
                 resets. State is persisted atomically so an interrupted run
                 never corrupts it.
    """

    def __init__(
        self,
        directory: Path,
        *,
        cycle: bool = False,
        state_file: Path = Path(".fb_pfp_state.json"),
        rng: random.Random | None = None,
    ) -> None:
        self._directory = directory.expanduser().resolve()
        self._cycle = cycle
        self._state_file = state_file
        self._rng = rng or random.Random()

    def _images(self) -> list[Path]:
        images = sorted(
            p for p in self._directory.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS
        )
        if not images:
            raise SourceError(
                f"No images ({', '.join(sorted(IMAGE_EXTENSIONS))}) in {self._directory}"
            )
        return images

    def _load_used(self) -> set[str]:
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            return set(data.get("used", []))
        except (OSError, json.JSONDecodeError, AttributeError):
            return set()

    def _save_used(self, used: set[str]) -> None:
        """Write state atomically (temp file + rename) so a crash mid-write
        cannot leave a torn JSON file behind."""
        payload = json.dumps({"used": sorted(used)}).encode("utf-8")
        fd, tmp_name = tempfile.mkstemp(dir=str(self._state_file.parent), prefix=".fb_pfp_")
        try:
            with open(fd, "wb") as fh:
                fh.write(payload)
            Path(tmp_name).replace(self._state_file)
        except OSError:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def pick(self) -> Path:
        images = self._images()
        if not self._cycle:
            return self._rng.choice(images)

        used = self._load_used()
        fresh = [p for p in images if p.name not in used]
        if not fresh:  # everything used — start a new rotation
            fresh = images
            used = set()
        choice = self._rng.choice(fresh)
        used.add(choice.name)
        self._save_used(used)
        return choice
