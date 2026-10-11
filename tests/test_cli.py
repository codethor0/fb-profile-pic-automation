"""CLI wiring tests. Fully offline: browser and automator are stubbed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fb_pfp import cli
from fb_pfp.automator import AutomatorError
from fb_pfp.config import Settings


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    brave = tmp_path / "Brave"
    brave.write_text("#!/bin/sh\n")
    pics = tmp_path / "pics"
    pics.mkdir()
    for n in ("a.jpg", "b.jpg"):
        (pics / n).write_bytes(b"x")
    state = tmp_path / "state.json"
    monkeypatch.setenv("FB_PFP_BRAVE_BINARY", str(brave))
    monkeypatch.setenv("FB_PFP_STATE_FILE", str(state))
    monkeypatch.setenv("FB_PFP_SCREENSHOT_DIR", str(tmp_path / "shots"))
    monkeypatch.delenv("FB_PFP_DEBUG_PORT", raising=False)
    monkeypatch.setattr(cli, "ensure_brave", lambda settings: None)
    return pics, state


class _OkAutomator:
    def __init__(self, settings) -> None: ...
    def run(self, image: Path) -> None: ...


class _FailAutomator:
    def __init__(self, settings) -> None: ...
    def run(self, image: Path) -> None:
        raise AutomatorError("boom")


class _CrashAutomator:
    def __init__(self, settings) -> None: ...
    def run(self, image: Path) -> None:
        raise RuntimeError("playwright exploded")


class _InterruptingAutomator:
    def __init__(self, settings) -> None: ...
    def run(self, image: Path) -> None:
        raise KeyboardInterrupt


class _StateCrashSource:
    """DirectorySource stand-in whose rotation-state write fails after Save."""

    def __init__(self, directory, **kw) -> None: ...
    def pick(self) -> Path:
        return Path("/tmp/x.jpg")
    def record_success(self, image: Path) -> None:
        raise OSError("disk full")


def test_success_records_rotation(env, monkeypatch: pytest.MonkeyPatch) -> None:
    pics, state = env
    monkeypatch.setattr(cli, "FacebookPfpAutomator", _OkAutomator)
    assert cli.main(["--dir", str(pics), "--cycle"]) == 0
    assert len(json.loads(state.read_text())["used"]) == 1


def test_failure_does_not_consume_image(env, monkeypatch: pytest.MonkeyPatch) -> None:
    pics, state = env
    monkeypatch.setattr(cli, "FacebookPfpAutomator", _FailAutomator)
    assert cli.main(["--dir", str(pics), "--cycle"]) == 1
    assert not state.exists()


def test_dry_run_does_not_consume_image(env, monkeypatch: pytest.MonkeyPatch) -> None:
    pics, state = env
    monkeypatch.setattr(cli, "FacebookPfpAutomator", _OkAutomator)
    assert cli.main(["--dir", str(pics), "--cycle", "--dry-run"]) == 0
    assert not state.exists()


def test_unexpected_library_error_exits_one_without_traceback(
    env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pics, _ = env
    monkeypatch.setattr(cli, "FacebookPfpAutomator", _CrashAutomator)
    assert cli.main(["--dir", str(pics)]) == 1
    assert "Unexpected RuntimeError" in caplog.text
    assert all(r.exc_info is None for r in caplog.records)  # no traceback unless -v


def test_bad_port_env_exits_one_with_message(
    env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pics, _ = env
    monkeypatch.setenv("FB_PFP_DEBUG_PORT", "abc")
    assert cli.main(["--dir", str(pics)]) == 1
    assert "FB_PFP_DEBUG_PORT" in caplog.text


def test_missing_directory_exits_one(env) -> None:
    assert cli.main(["--dir", "/definitely/not/here"]) == 1


def test_version_flag_prints_version_and_exits(capsys: pytest.CaptureFixture[str]) -> None:
    from fb_pfp import __version__

    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_state_write_failure_still_exits_zero(
    env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """F5: picture IS changed when only the rotation note fails; exit 0 on
    purpose so a scheduler does not immediately change it again."""
    pics, _ = env
    monkeypatch.setattr(cli, "DirectorySource", _StateCrashSource)
    monkeypatch.setattr(cli, "FacebookPfpAutomator", _OkAutomator)
    assert cli.main(["--dir", str(pics), "--cycle"]) == 0
    assert "rotation state was not saved" in caplog.text


def test_ctrl_c_exits_130(env, monkeypatch: pytest.MonkeyPatch) -> None:
    pics, _ = env
    monkeypatch.setattr(cli, "FacebookPfpAutomator", _InterruptingAutomator)
    assert cli.main(["--dir", str(pics)]) == 130


def test_cycle_with_file_warns_and_ignores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture[str]
) -> None:
    img = tmp_path / "me.jpg"
    img.write_bytes(b"x")
    brave = tmp_path / "Brave"
    brave.write_text("#!/bin/sh\n")
    monkeypatch.setenv("FB_PFP_BRAVE_BINARY", str(brave))
    monkeypatch.delenv("FB_PFP_DEBUG_PORT", raising=False)
    monkeypatch.setattr(cli, "ensure_brave", lambda settings: None)
    monkeypatch.setattr(cli, "FacebookPfpAutomator", _OkAutomator)
    assert cli.main(["--file", str(img), "--cycle"]) == 0
    assert "--cycle has no effect with --file" in caplog.text


def test_overlapping_run_rejected_with_lock_held(
    env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture[str]
) -> None:
    """F07: a second run while the run lock is held exits 1 with a message."""
    import fcntl
    import os

    pics, state = env
    state.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(state.with_name("run.lock"), os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        assert cli.main(["--dir", str(pics)]) == 1
        assert "already in progress" in caplog.text
    finally:
        os.close(fd)


def test_ensure_brave_shuts_down_only_what_it_launched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F04: shutdown is a no-op for reused sessions and opted-in keeps."""
    from fb_pfp import browser

    calls: list[str] = []
    monkeypatch.setattr(browser, "_quit_brave_gracefully", lambda binary: calls.append("quit"))
    settings = Settings(source_kind="directory", image_dir=tmp_path)

    browser.shutdown_brave(settings, "reused")
    assert calls == []  # never kill the user's own browser

    browser.shutdown_brave(settings, "launched")
    assert calls == ["quit"]  # we started it, we close it

    settings_keep = Settings(source_kind="directory", image_dir=tmp_path, keep_brave_open=True)
    browser.shutdown_brave(settings_keep, "launched")
    assert calls == ["quit"]  # opt-out honored, no second quit
