"""Typed configuration for fb_pfp.

Precedence (lowest to highest):
    1. Built-in defaults
    2. Environment variables (FB_PFP_*)
    3. Command-line arguments

Nothing secret lives here — the only sensitive input is the browser profile
path, which stays on the local machine and is never transmitted anywhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PORT = 9222
DEFAULT_LOCALE = "en-US"
DEFAULT_BRAVE_BINARY = Path("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")
DEFAULT_BRAVE_PROFILE = (
    Path.home() / "Library/Application Support/BraveSoftware/Brave-Browser"
)
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})


@dataclass(frozen=True)
class Settings:
    """Resolved runtime configuration."""

    source_kind: str  # "directory" | "file"
    image_dir: Path | None = None
    image_file: Path | None = None
    cycle: bool = False
    dry_run: bool = False
    brave_binary: Path = DEFAULT_BRAVE_BINARY
    brave_profile: Path = DEFAULT_BRAVE_PROFILE
    debug_port: int = DEFAULT_PORT
    locale: str = DEFAULT_LOCALE
    state_file: Path = field(default_factory=lambda: Path(".fb_pfp_state.json"))
    screenshot_dir: Path = field(default_factory=lambda: Path("."))

    @property
    def cdp_url(self) -> str:
        return f"http://localhost:{self.debug_port}"

    def validate(self) -> None:
        """Fail fast on unusable configuration."""
        if self.source_kind == "file":
            if self.image_file is None:
                raise ValueError("source_kind='file' requires image_file")
            if not self.image_file.is_file():
                raise FileNotFoundError(f"Image file not found: {self.image_file}")
        elif self.source_kind == "directory":
            if self.image_dir is None:
                raise ValueError("source_kind='directory' requires image_dir")
            if not self.image_dir.is_dir():
                raise NotADirectoryError(f"Image directory not found: {self.image_dir}")
        else:
            raise ValueError(f"Unknown source_kind: {self.source_kind!r}")
        if not self.brave_binary.is_file():
            raise FileNotFoundError(f"Brave binary not found: {self.brave_binary}")
        if not (1 <= self.debug_port <= 65535):
            raise ValueError(f"debug_port out of range: {self.debug_port}")


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else None


def build_settings(args: object) -> Settings:
    """Merge defaults, environment variables, and parsed CLI args."""
    source_kind = "file" if getattr(args, "file", None) else "directory"

    image_dir = Path(args.dir).expanduser() if getattr(args, "dir", None) else _env_path("FB_PFP_DIR")
    image_file = (
        Path(args.file).expanduser() if getattr(args, "file", None) else _env_path("FB_PFP_FILE")
    )
    if image_dir is None and image_file is None:
        image_dir = Path("./profile_pics")

    return Settings(
        source_kind=source_kind,
        image_dir=image_dir,
        image_file=image_file,
        cycle=bool(getattr(args, "cycle", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
        brave_binary=_env_path("FB_PFP_BRAVE_BINARY") or DEFAULT_BRAVE_BINARY,
        brave_profile=_env_path("FB_PFP_BRAVE_PROFILE") or DEFAULT_BRAVE_PROFILE,
        debug_port=int(os.environ.get("FB_PFP_DEBUG_PORT", DEFAULT_PORT)),
        locale=os.environ.get("FB_PFP_LOCALE", DEFAULT_LOCALE),
        state_file=_env_path("FB_PFP_STATE_FILE") or Path(".fb_pfp_state.json"),
        screenshot_dir=_env_path("FB_PFP_SCREENSHOT_DIR") or Path("."),
    )
