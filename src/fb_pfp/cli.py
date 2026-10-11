"""Command-line interface: argument parsing, logging, wiring."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .automator import AutomatorError, FacebookPfpAutomator
from .browser import BrowserError, ensure_brave
from .config import Settings, build_settings
from .sources import DirectorySource, SingleFileSource, SourceError


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fb-change-pfp",
        description="Auto-change your Facebook profile picture via your logged-in Brave browser.",
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--dir", help="Directory of candidate images (picks one at random)")
    src.add_argument("--file", help="Use a specific image file")
    parser.add_argument("--cycle", action="store_true", help="Rotate without repeats until all are used")
    parser.add_argument("--dry-run", action="store_true", help="Upload but stop before Save")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    return parser


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="[%(name)s] %(message)s",
        stream=sys.stdout,
    )


def _build_source(settings: Settings):
    if settings.source_kind == "file":
        assert settings.image_file is not None
        return SingleFileSource(settings.image_file)
    assert settings.image_dir is not None
    return DirectorySource(
        settings.image_dir,
        cycle=settings.cycle,
        state_file=settings.state_file,
    )


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    _configure_logging(args.verbose)

    settings = build_settings(args)
    try:
        settings.validate()
        image = _build_source(settings).pick()
        ensure_brave(settings)
        FacebookPfpAutomator(settings).run(image)
    except (SourceError, BrowserError, AutomatorError, ValueError, OSError) as exc:
        logging.getLogger("fb_pfp").error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
