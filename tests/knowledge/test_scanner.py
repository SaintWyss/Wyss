"""Tests del scanner de filesystem."""

from pathlib import Path

import pytest

from core.domain.knowledge import FileStatus
from knowledge.scanner import ScanItem, Scanner


def _scan(root: Path, *, max_file_bytes: int = 1_000_000) -> list[ScanItem]:
    return list(
        Scanner().scan(
            root,
            max_file_bytes=max_file_bytes,
            dir_denylist=frozenset({".git", "node_modules"}),
        )
    )


def test_scanner_skips_denylisted_dirs(tmp_path: Path) -> None:
    allowed = tmp_path / "docs"
    denied = tmp_path / ".git"
    allowed.mkdir()
    denied.mkdir()
    (allowed / "ok.txt").write_text("visible", encoding="utf-8")
    (denied / "secret.txt").write_text("hidden", encoding="utf-8")

    items = _scan(tmp_path)

    paths = {Path(item.path).name for item in items}
    assert "ok.txt" in paths
    assert "secret.txt" not in paths


def test_scanner_reports_symlink_and_does_not_follow_it(tmp_path: Path) -> None:
    root = tmp_path / "root"
    target = tmp_path / "target"
    root.mkdir()
    target.mkdir()
    (target / "outside.txt").write_text("outside", encoding="utf-8")
    (root / "link").symlink_to(target, target_is_directory=True)

    items = _scan(root)

    assert [item.status for item in items] == [FileStatus.skipped_symlink]
    assert all(Path(item.path).name != "outside.txt" for item in items)


def test_scanner_detects_media_type_with_magic_not_extension(tmp_path: Path) -> None:
    disguised = tmp_path / "not_really_text.txt"
    disguised.write_bytes(b"%PDF-1.4\n%not a real text file\n")

    items = _scan(tmp_path)

    sources = [item.source for item in items if item.source is not None]
    assert len(sources) == 1
    assert sources[0].media_type == "application/pdf"


def test_scanner_marks_files_over_size_as_metadata_only(tmp_path: Path) -> None:
    large = tmp_path / "large.txt"
    large.write_text("0123456789", encoding="utf-8")

    items = _scan(tmp_path, max_file_bytes=4)

    assert len(items) == 1
    assert items[0].status == FileStatus.skipped_size
    assert items[0].source is not None
    assert items[0].source.size == 10


def test_scanner_rejects_non_directory_root(tmp_path: Path) -> None:
    root = tmp_path / "file.txt"
    root.write_text("not a dir", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        list(Scanner().scan(root, max_file_bytes=100, dir_denylist=frozenset()))
