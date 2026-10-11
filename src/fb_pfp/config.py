"""Typed configuration for fb_pfp.

Precedence (lowest to highest):
    1. Built-in defaults
    2. Environment variables (FB_PFP_*)
    3. Command-line arguments

Nothing secret lives here. The only sensitive input is the browser profile
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
DEFAULT_DATA_DIR = Path.home() / ".fb_pfp"


class ConfigError(ValueError):
    """Raised when configuration (CLI args or FB_PFP_* variables) is unusable."""


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
    # Expected Facebook display name, verified before any change is made
    # (audit finding F03: never act on an unverified account). Set
    # FB_PFP_EXPECTED_NAME to enforce; unset logs a warning and continues.
    verify_account_name: str | None = None
    keep_brave_open: bool = False
    state_file: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "state.json")
    screenshot_dir: Path = field(default_factory=lambda: DEFAULT_DATA_DIR / "screenshots")
    debug_screenshots: bool = False

    @property
    def cdp_url(self) -> str:
        """Local DevTools endpoint derived from ``debug_port`` (loopback only).

        Uses 127.0.0.1 rather than ``localhost`` so a resolver preferring IPv6
        cannot turn the connection into a refused ``::1`` connect.
        """
        return f"http://127.0.0.1:{self.debug_port}"

    def validate(self) -> None:
        """Fail fast on unusable configuration.

        Raises:
            ValueError: bad port or source_kind.
            FileNotFoundError / NotADirectoryError: missing paths.
        """
        # Cheap, machine-independent checks first: port range and source_kind
        # must be rejected even where the Brave paths below don't exist
        # (e.g. Linux CI runners).
        if not (1 <= self.debug_port <= 65535):
            raise ValueError(f"debug_port out of range: {self.debug_port}")
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


def _env_path(name: str) -> Path | None:
    """Read an optional path from the environment, expanding ``~``."""
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else None


def _env_port() -> int:
    """Read ``FB_PFP_DEBUG_PORT``; raise :class:`ConfigError` if not an integer."""
    raw = os.environ.get("FB_PFP_DEBUG_PORT", str(DEFAULT_PORT))
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"FB_PFP_DEBUG_PORT must be an integer, got {raw!r}") from None


def build_settings(args: object) -> Settings:
    """Merge defaults, environment variables, and parsed CLI args.

    Raises:
        ConfigError: a ``FB_PFP_*`` variable has an unusable value.
    """
    env_dir = _env_path("FB_PFP_DIR")
    env_file = _env_path("FB_PFP_FILE")
    if env_dir is not None and env_file is not None:
        raise ConfigError("set only one of FB_PFP_DIR and FB_PFP_FILE")

    cli_dir = Path(args.dir).expanduser() if getattr(args, "dir", None) else None
    cli_file = Path(args.file).expanduser() if getattr(args, "file", None) else None

    # Source selection order: CLI --file, CLI --dir, env FB_PFP_FILE,
    # env FB_PFP_DIR, built-in default. Without this, FB_PFP_FILE alone
    # left source_kind="directory" and the env file was silently ignored.
    if cli_file is not None:
        source_kind, image_dir, image_file = "file", None, cli_file
    elif cli_dir is not None:
        source_kind, image_dir, image_file = "directory", cli_dir, None
    elif env_file is not None:
        source_kind, image_dir, image_file = "file", None, env_file
    elif env_dir is not None:
        source_kind, image_dir, image_file = "directory", env_dir, None
    else:
        source_kind, image_dir, image_file = "directory", Path("./profile_pics"), None

    return Settings(
        source_kind=source_kind,
        image_dir=image_dir,
        image_file=image_file,
        cycle=bool(getattr(args, "cycle", False)),
        dry_run=bool(getattr(args, "dry_run", False)),
        brave_binary=_env_path("FB_PFP_BRAVE_BINARY") or DEFAULT_BRAVE_BINARY,
        brave_profile=_env_path("FB_PFP_BRAVE_PROFILE") or DEFAULT_BRAVE_PROFILE,
        debug_port=_env_port(),
        locale=os.environ.get("FB_PFP_LOCALE", DEFAULT_LOCALE),
        verify_account_name=os.environ.get("FB_PFP_EXPECTED_NAME") or None,
        keep_brave_open=os.environ.get("FB_PFP_KEEP_BRAVE_OPEN", "") not in ("", "0", "false"),
        state_file=_env_path("FB_PFP_STATE_FILE") or DEFAULT_DATA_DIR / "state.json",
        screenshot_dir=_env_path("FB_PFP_SCREENSHOT_DIR") or DEFAULT_DATA_DIR / "screenshots",
        debug_screenshots=bool(getattr(args, "verbose", False)),
    )
