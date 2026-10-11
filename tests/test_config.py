"""Unit tests for configuration resolution. Fully offline."""

from __future__ import annotations

from pathlib import Path

import pytest

from fb_pfp.config import DEFAULT_DATA_DIR, ConfigError, Settings, build_settings


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_defaults_to_directory_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FB_PFP_DIR", raising=False)
    monkeypatch.delenv("FB_PFP_FILE", raising=False)
    s = build_settings(_Args(dir=None, file=None, cycle=False, dry_run=False))
    assert s.source_kind == "directory"
    assert s.image_dir == Path("./profile_pics")


def test_file_arg_wins_over_env_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FB_PFP_DIR", "/env/dir")
    s = build_settings(_Args(dir=None, file="/tmp/me.jpg", cycle=False, dry_run=False))
    assert s.source_kind == "file"
    assert s.image_file == Path("/tmp/me.jpg")
    assert s.image_dir is None  # losing source is dropped, not carried unused


def test_env_file_selects_file_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """F1: FB_PFP_FILE alone must select the file source (regression)."""
    monkeypatch.delenv("FB_PFP_DIR", raising=False)
    monkeypatch.setenv("FB_PFP_FILE", "/tmp/env-me.jpg")
    s = build_settings(_Args(dir=None, file=None, cycle=False, dry_run=False))
    assert s.source_kind == "file"
    assert s.image_file == Path("/tmp/env-me.jpg")
    assert s.image_dir is None


def test_both_env_sources_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FB_PFP_DIR", "/env/dir")
    monkeypatch.setenv("FB_PFP_FILE", "/env/me.jpg")
    with pytest.raises(ConfigError, match="only one of FB_PFP_DIR"):
        build_settings(_Args(dir=None, file=None, cycle=False, dry_run=False))


def test_cli_dir_wins_over_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FB_PFP_FILE", "/env/me.jpg")
    s = build_settings(_Args(dir="/tmp/cli-dir", file=None, cycle=False, dry_run=False))
    assert s.source_kind == "directory"
    assert s.image_dir == Path("/tmp/cli-dir")
    assert s.image_file is None


def test_env_overrides_default_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FB_PFP_DEBUG_PORT", "9333")
    s = build_settings(_Args(dir=".", file=None, cycle=False, dry_run=False))
    assert s.debug_port == 9333
    assert s.cdp_url == "http://127.0.0.1:9333"


def test_validate_rejects_unknown_source_kind() -> None:
    s = Settings(source_kind="mystery")
    with pytest.raises(ValueError, match="Unknown source_kind"):
        s.validate()


def test_validate_rejects_bad_port(tmp_path: Path) -> None:
    fake_brave = tmp_path / "Brave"
    fake_brave.write_text("#!/bin/sh\n")  # so filesystem checks pass; port must still fail
    s = Settings(
        source_kind="directory",
        image_dir=tmp_path,
        brave_binary=fake_brave,
        debug_port=0,
    )
    with pytest.raises(ValueError, match="debug_port"):
        s.validate()


def test_validate_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_brave = tmp_path / "Brave"
    fake_brave.write_text("#!/bin/sh\n")  # must exist as a file
    monkeypatch.setenv("FB_PFP_BRAVE_BINARY", str(fake_brave))
    d = tmp_path / "pics"
    d.mkdir()
    s = build_settings(_Args(dir=str(d), file=None, cycle=True, dry_run=True))
    s.validate()  # should not raise
    assert s.cycle and s.dry_run


def test_non_integer_port_env_is_a_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FB_PFP_DEBUG_PORT", "abc")
    with pytest.raises(ConfigError, match="FB_PFP_DEBUG_PORT"):
        build_settings(_Args(dir=".", file=None, cycle=False, dry_run=False))


def test_verbose_enables_debug_screenshots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FB_PFP_DEBUG_PORT", raising=False)
    quiet = build_settings(_Args(dir=".", file=None))
    loud = build_settings(_Args(dir=".", file=None, verbose=True))
    assert quiet.debug_screenshots is False and loud.debug_screenshots is True


def test_default_state_is_per_user_not_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("FB_PFP_STATE_FILE", "FB_PFP_SCREENSHOT_DIR", "FB_PFP_DEBUG_PORT"):
        monkeypatch.delenv(name, raising=False)
    s = build_settings(_Args(dir=".", file=None))
    assert s.state_file == DEFAULT_DATA_DIR / "state.json"
    assert s.screenshot_dir == DEFAULT_DATA_DIR / "screenshots"


def test_expected_name_env_reaches_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FB_PFP_EXPECTED_NAME", "Ada Lovelace")
    assert build_settings(_Args(dir=".", file=None)).verify_account_name == "Ada Lovelace"
    monkeypatch.delenv("FB_PFP_EXPECTED_NAME")
    assert build_settings(_Args(dir=".", file=None)).verify_account_name is None
