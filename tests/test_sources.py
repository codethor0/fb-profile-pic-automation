"""Unit tests for image sources. Fully offline — no browser required."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from fb_pfp.sources import DirectorySource, SingleFileSource, SourceError


@pytest.fixture()
def img_dir(tmp_path: Path) -> Path:
    for name in ("a.jpg", "b.png", "c.webp"):
        (tmp_path / name).write_bytes(b"\xff\xd8\xff")  # bytes don't matter
    (tmp_path / "notes.txt").write_text("not an image")
    (tmp_path / "noext").write_bytes(b"x")
    return tmp_path


class TestSingleFileSource:
    def test_returns_resolved_file(self, tmp_path: Path) -> None:
        f = tmp_path / "me.jpg"
        f.write_bytes(b"x")
        assert SingleFileSource(f).pick() == f.resolve()

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SourceError):
            SingleFileSource(tmp_path / "nope.jpg").pick()


class TestDirectorySourceRandom:
    def test_only_picks_images(self, img_dir: Path) -> None:
        src = DirectorySource(img_dir, rng=random.Random(0))
        for _ in range(25):
            assert src.pick().suffix in {".jpg", ".png", ".webp"}

    def test_random_mode_never_writes_state(self, img_dir: Path, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        DirectorySource(img_dir, state_file=state, rng=random.Random(1)).pick()
        assert not state.exists()

    def test_empty_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(SourceError, match="No images"):
            DirectorySource(tmp_path).pick()


class TestDirectorySourceCycle:
    def test_no_repeats_until_all_used(self, img_dir: Path, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        rng = random.Random(42)
        src = DirectorySource(img_dir, cycle=True, state_file=state, rng=rng)
        picks = {src.pick().name for _ in range(3)}
        assert picks == {"a.jpg", "b.png", "c.webp"}

    def test_rotation_resets_after_full_cycle(self, img_dir: Path, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        rng = random.Random(7)
        src = DirectorySource(img_dir, cycle=True, state_file=state, rng=rng)
        first_round = [src.pick().name for _ in range(3)]
        second_round = [src.pick().name for _ in range(3)]
        assert sorted(first_round) == sorted(second_round) == ["a.jpg", "b.png", "c.webp"]

    def test_state_persists_across_instances(self, img_dir: Path, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        a = DirectorySource(img_dir, cycle=True, state_file=state, rng=random.Random(3))
        b = DirectorySource(img_dir, cycle=True, state_file=state, rng=random.Random(3))
        assert a.pick().name != b.pick().name  # b avoids a's pick via state

    def test_corrupt_state_is_ignored(self, img_dir: Path, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        state.write_text("{not json")
        src = DirectorySource(img_dir, cycle=True, state_file=state, rng=random.Random(0))
        assert src.pick().suffix in {".jpg", ".png", ".webp"}
