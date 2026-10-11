"""Command-line interface: argument parsing, logging, wiring."""

from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
from .automator import AutomatorError, FacebookPfpAutomator
from .browser import BrowserError, ensure_brave
from .config import ConfigError, Settings, build_settings
from .sources import (
    DirectorySource,
    ImageSource,
    RecordsSuccess,
    SingleFileSource,
    SourceError,
)

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
        image = source.pick()
        ensure_brave(settings)
        FacebookPfpAutomator(settings).run(image)
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
