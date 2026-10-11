"""Command-line interface: argument parsing, logging, wiring."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import __version__
from .automator import AutomatorError, FacebookPfpAutomator
from .browser import BrowserError, ensure_brave, shutdown_brave
from .config import ConfigError, Settings, build_settings
from .sources import (
    DirectorySource,
    ImageSource,
    RecordsSuccess,
    SingleFileSource,
    SourceError,
)

try:  # POSIX only; the tool targets macOS, other platforms skip locking
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore[assignment]

logger = logging.getLogger("fb_pfp")


def make_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="fb-pfp",
        description="Auto-change your Facebook profile picture via your logged-in Brave browser.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--dir", help="Directory of candidate images (picks one at random)")
    src.add_argument("--file", help="Use a specific image file")
    parser.add_argument("--cycle", action="store_true", help="Rotate without repeats until all are used")
    parser.add_argument("--dry-run", action="store_true", help="Upload but stop before Save")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Debug logging and diagnostic screenshots"
    )
    return parser


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="[%(name)s] %(message)s",
        stream=sys.stdout,
    )


def _build_source(settings: Settings) -> ImageSource:
    """Create the image source selected by ``settings``.

    Raises:
        ConfigError: the selected source has no path configured.
    """
    if settings.source_kind == "file":
        if settings.image_file is None:
            raise ConfigError("source_kind='file' requires image_file")
        return SingleFileSource(settings.image_file)
    if settings.image_dir is None:
        raise ConfigError("source_kind='directory' requires image_dir")
    return DirectorySource(
        settings.image_dir,
        cycle=settings.cycle,
        state_file=settings.state_file,
    )


@contextmanager
def _run_lock(state_file: Path) -> Iterator[None]:
    """Serialize whole runs so overlapping runs cannot pick the same image.

    Audit finding F07: the state-file lock in DirectorySource protects state
    integrity, but pick() itself was unlocked; two overlapping runs could pick
    the same fresh image before either recorded success. A single exclusive
    lock around the entire run (selection, upload, state commit) is the simple
    correct fix. Second concurrent run exits with a clear message.
    """
    if fcntl is None:  # pragma: no cover - non-POSIX
        yield
        return
    state_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(state_file.with_name("run.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SourceError("another fb-pfp run is already in progress") from None
        yield
    finally:
        os.close(fd)  # closing releases the lock


def main(argv: list[str] | None = None) -> int:
    """Run the tool.

    Returns 0 on success, 1 on any reported failure, 130 on Ctrl-C.
    (argparse rejects bad invocations with exit 2 before this runs.)
    """
    args = make_parser().parse_args(argv)
    _configure_logging(args.verbose)

    try:
        settings = build_settings(args)
        settings.validate()
        if settings.source_kind == "file" and settings.cycle:
            logger.warning("--cycle has no effect with --file; ignoring it")
        source = _build_source(settings)
        with _run_lock(settings.state_file):
            image = source.pick()
            mode = ensure_brave(settings)
            try:
                FacebookPfpAutomator(settings).run(image)
            finally:
                # Close the debug-enabled browser only when this run started it
                # (F04); a pre-existing browser is never killed.
                shutdown_brave(settings, mode)
            if isinstance(source, RecordsSuccess) and not settings.dry_run:
                try:
                    source.record_success(image)
                except Exception as exc:
                    # The picture IS changed; only the rotation note failed. Exit 0
                    # on purpose: exit 1 would make a scheduler rerun and change
                    # the public picture a second time.
                    logger.warning("Picture changed, but rotation state was not saved: %s", exc)
    except KeyboardInterrupt:
        logger.error("Interrupted")
        return 130
    except (SourceError, BrowserError, AutomatorError, ValueError, OSError) as exc:
        logger.error("%s", exc)
        return 1
    except Exception as exc:  # last resort: Playwright and other library errors
        logger.error("Unexpected %s: %s (run with -v for details)", type(exc).__name__, exc)
        logger.debug("Traceback", exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
