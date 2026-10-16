"""Image sources.

An image source answers one question: "which local picture should become the
profile picture right now?" Implement :class:`ImageSource` to add new picking
strategies for local files. Sources that keep rotation state may additionally
implement :class:`RecordsSuccess`; the CLI calls it only after Facebook
accepted the picture, so a failed run never consumes an image.

Note: picking photos already hosted on Facebook is *not* just another
ImageSource; it needs a different automation action (clicking existing photos
in the dialog) and a richer interface. The built-in sources are local files.
"""

from __future__ import annotations

import json
import logging
import os
import random
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Protocol, runtime_checkable

from .config import DEFAULT_DATA_DIR, IMAGE_EXTENSIONS

try:  # POSIX only; the tool targets macOS, other platforms skip locking
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore[assignment]

logger = logging.getLogger("fb_pfp")


def ensure_private_dir(path: Path) -> None:
    """Create ``path`` and keep it owner-only.

    State files and lock files reveal usage patterns, so the directory must
    be private even on flows that only pick an image and never write state
    (audit finding CLI-1: the mode was only fixed inside ``_save_used``).
    """
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


class SourceError(RuntimeError):
    """Raised when an image source cannot produce an image."""


@runtime_checkable
class ImageSource(Protocol):
    """Strategy protocol: produce the next image to upload."""

    def pick(self) -> Path:
        """Return the absolute path of the image to use next."""
        ...


@runtime_checkable
class RecordsSuccess(Protocol):
    """Optional protocol: sources with rotation state learn the outcome."""

    def record_success(self, image: Path) -> None:
        """Called once ``image`` has been saved as the profile picture."""
        ...


class SingleFileSource:
    """Always returns the same file."""

    def __init__(self, path: Path) -> None:
        self._path = path.expanduser().resolve()

    def pick(self) -> Path:
        """Return the configured file; raise :class:`SourceError` if missing."""
        if not self._path.is_file():
            raise SourceError(f"Image file not found: {self._path}")
        return self._path


class DirectorySource:
    """Picks an image from a directory.

    Modes:
        random: uniform random choice every time (repeats allowed)
        cycle:  no repeats until every image has been used, then rotation
                 resets. ``pick`` never writes state; call
                 :meth:`record_success` after a successful change. State is
                 written atomically under an exclusive lock, so interrupted
                 or concurrent runs cannot corrupt it.

    Only regular files with a known image extension are candidates; symlinks
    are skipped so a link cannot smuggle in a file from elsewhere.
    """

    def __init__(
        self,
        directory: Path,
        *,
        cycle: bool = False,
        state_file: Path = DEFAULT_DATA_DIR / "state.json",
        rng: random.Random | None = None,
    ) -> None:
        self._directory = directory.expanduser().resolve()
        self._cycle = cycle
        self._state_file = state_file
        self._rng = rng or random.Random()

    def _images(self) -> list[Path]:
        try:
            entries = list(self._directory.iterdir())
        except OSError as exc:
            raise SourceError(f"Cannot read image directory {self._directory}: {exc}") from exc
        images = sorted(
            p
            for p in entries
            if p.suffix.lower() in IMAGE_EXTENSIONS
            and p.is_file()
            and not p.is_symlink()
            and not p.name.startswith(".")  # skip dotfiles, e.g. macOS AppleDouble "._*.jpg"
        )
        if not images:
            raise SourceError(
                f"No images ({', '.join(sorted(IMAGE_EXTENSIONS))}) in {self._directory}"
            )
        return images

    def _load_used(self) -> set[str]:
        """Return used file names; any unreadable or malformed state counts as empty."""
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            if not isinstance(exc, FileNotFoundError):
                logger.warning("Ignoring unreadable rotation state %s: %s", self._state_file, exc)
            return set()
        used = data.get("used") if isinstance(data, dict) else None
        if not isinstance(used, list) or not all(isinstance(n, str) for n in used):
            logger.warning("Ignoring malformed rotation state %s", self._state_file)
            return set()
        return set(used)

    def _save_used(self, used: set[str]) -> None:
        """Write state atomically (temp file + fsync + rename) so a crash
        mid-write, or a power loss, cannot leave a torn JSON file behind."""
        parent = self._state_file.parent
        ensure_private_dir(parent)
        payload = json.dumps({"used": sorted(used)}).encode("utf-8")
        fd, tmp_name = tempfile.mkstemp(dir=str(parent), prefix=".fb_pfp_")
        try:
            with open(fd, "wb") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())  # flush to disk before the rename publishes it
            Path(tmp_name).replace(self._state_file)
        except OSError:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    @contextmanager
    def _locked(self) -> Iterator[None]:
        """Exclusive advisory lock around state read-modify-write."""
        if fcntl is None:  # pragma: no cover - non-POSIX
            yield
            return
        ensure_private_dir(self._state_file.parent)
        lock_path = self._state_file.with_name(self._state_file.name + ".lock")
        fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)  # closing releases the lock

    def pick(self) -> Path:
        """Return the next image. Read-only: never modifies rotation state."""
        images = self._images()
        if not self._cycle:
            return self._rng.choice(images)
        used = self._load_used()
        fresh = [p for p in images if p.name not in used] or images
        return self._rng.choice(fresh)

    def record_success(self, image: Path) -> None:
        """Mark ``image`` used (cycle mode only); resets once all are used."""
        if not self._cycle:
            return
        names = {p.name for p in self._images()}
        with self._locked():
            used = self._load_used() & names
            used.add(image.name)
            if used >= names:
                # Round complete: start a new one, but keep the image just
                # saved marked as used so the new round cannot open by
                # repeating it. With a single image there is no alternative.
                used = {image.name} if len(names) > 1 else set()
            self._save_used(used)
