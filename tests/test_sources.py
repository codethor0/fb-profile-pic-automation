"""Unit tests for image sources. Fully offline, no browser required."""

from __future__ import annotations

import json
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


def _next(src: DirectorySource) -> Path:
    """Pick, then record success, like a completed CLI run."""
    image = src.pick()
    src.record_success(image)
    return image


class TestDirectorySourceCycle:
    def test_no_repeats_until_all_used(self, img_dir: Path, tmp_path: Path) -> None:
        src = DirectorySource(
            img_dir, cycle=True, state_file=tmp_path / "state.json", rng=random.Random(42)
        )
        assert {_next(src).name for _ in range(3)} == {"a.jpg", "b.png", "c.webp"}

    def test_rotation_resets_after_full_cycle(self, img_dir: Path, tmp_path: Path) -> None:
        src = DirectorySource(
            img_dir, cycle=True, state_file=tmp_path / "state.json", rng=random.Random(7)
        )
        first = [_next(src).name for _ in range(3)]
        assert sorted(first) == ["a.jpg", "b.png", "c.webp"]
        # Later rounds keep rotating through every image without ever
        # repeating the image just saved.
        later = [_next(src).name for _ in range(9)]
        assert set(later) == {"a.jpg", "b.png", "c.webp"}
        sequence = first + later
        assert all(x != y for x, y in zip(sequence, sequence[1:]))

    def test_new_round_never_opens_with_the_image_just_saved(
        self, img_dir: Path, tmp_path: Path
    ) -> None:
        for seed in range(40):
            state = tmp_path / f"state-{seed}.json"
            src = DirectorySource(
                img_dir, cycle=True, state_file=state, rng=random.Random(seed)
            )
            last_of_round = [_next(src).name for _ in range(3)][-1]
            assert src.pick().name != last_of_round

    def test_single_image_still_repeats_and_resets(self, tmp_path: Path) -> None:
        only = tmp_path / "pics"
        only.mkdir()
        (only / "one.jpg").write_bytes(b"\xff\xd8\xff")
        src = DirectorySource(
            only, cycle=True, state_file=tmp_path / "state.json", rng=random.Random(0)
        )
        assert _next(src).name == "one.jpg"
        assert src.pick().name == "one.jpg"

    def test_state_persists_across_instances(self, img_dir: Path, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        a = DirectorySource(img_dir, cycle=True, state_file=state, rng=random.Random(3))
        b = DirectorySource(img_dir, cycle=True, state_file=state, rng=random.Random(3))
        assert _next(a).name != b.pick().name  # b avoids a's recorded pick

    def test_pick_alone_does_not_consume_an_image(self, img_dir: Path, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        src = DirectorySource(img_dir, cycle=True, state_file=state, rng=random.Random(1))
        src.pick()
        assert not state.exists()  # failed run => nothing recorded

    def test_record_success_is_noop_in_random_mode(self, img_dir: Path, tmp_path: Path) -> None:
        state = tmp_path / "state.json"
        src = DirectorySource(img_dir, state_file=state, rng=random.Random(1))
        src.record_success(src.pick())
        assert not state.exists()

    def test_state_directory_is_created(self, img_dir: Path, tmp_path: Path) -> None:
        state = tmp_path / "nested" / "dir" / "state.json"
        src = DirectorySource(img_dir, cycle=True, state_file=state, rng=random.Random(1))
        _next(src)
        assert state.is_file()

    @pytest.mark.parametrize(
        "content", ["{not json", "[1, 2]", '{"used": 5}', '{"used": [1, 2]}', '"x"', ""]
    )
    def test_corrupt_or_malformed_state_is_ignored(
        self, img_dir: Path, tmp_path: Path, content: str
    ) -> None:
        state = tmp_path / "state.json"
        state.write_text(content)
        src = DirectorySource(img_dir, cycle=True, state_file=state, rng=random.Random(0))
        assert _next(src).suffix in {".jpg", ".png", ".webp"}
        assert json.loads(state.read_text())["used"]  # rewritten as valid state


class TestDirectoryFiltering:
    def test_skips_symlinks_and_directories(self, tmp_path: Path) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")
        pics = tmp_path / "pics"
        pics.mkdir()
        (pics / "real.jpg").write_bytes(b"x")
        (pics / "link.jpg").symlink_to(outside)
        (pics / "folder.png").mkdir()
        for seed in range(30):
            assert DirectorySource(pics, rng=random.Random(seed)).pick().name == "real.jpg"

    def test_unreadable_directory_raises_source_error(self, tmp_path: Path) -> None:
        with pytest.raises(SourceError, match="Cannot read"):
            DirectorySource(tmp_path / "missing").pick()

    def test_hidden_appledouble_files_are_skipped(self, tmp_path: Path) -> None:
        """F14: macOS AppleDouble "._*.jpg" files must never be picked."""
        (tmp_path / "real.jpg").write_bytes(b"x")
        (tmp_path / "._real.jpg").write_bytes(b"appledouble")
        (tmp_path / ".hidden.png").write_bytes(b"x")
        for seed in range(20):
            assert DirectorySource(tmp_path, rng=random.Random(seed)).pick().name == "real.jpg"
