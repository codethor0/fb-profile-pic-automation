"""Unit tests for configuration resolution. Fully offline."""

from __future__ import annotations

from pathlib import Path

import pytest

from fb_pfp.config import Settings, build_settings


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
    assert s.image_dir == Path("/env/dir")  # env still recorded, unused


def test_env_overrides_default_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FB_PFP_DEBUG_PORT", "9333")
    s = build_settings(_Args(dir=".", file=None, cycle=False, dry_run=False))
    assert s.debug_port == 9333
    assert s.cdp_url == "http://localhost:9333"


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
