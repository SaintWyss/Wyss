"""Tests de index.db y StateStore: WAL, incremental y reanudabilidad."""

import sqlite3
from pathlib import Path

import pytest

from core.domain.errors import IndexIntegrityError
from core.domain.knowledge import FileStatus
from knowledge.db import open_index_db
from knowledge.index_schema import apply_index_schema
from knowledge.state_store import StateStore


def _read_conn(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def _write(path: Path, text: str) -> tuple[int, float]:
    path.write_text(text, encoding="utf-8")
    stat = path.stat()
    return stat.st_size, stat.st_mtime


def test_wal_active(index_db_path: Path) -> None:
    conn = open_index_db(index_db_path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        conn.close()


def test_fail_fast_when_journal_not_wal(
    index_db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import knowledge.db as mod

    monkeypatch.setattr(mod, "PRAGMAS", ("PRAGMA journal_mode=DELETE",))
    with pytest.raises(IndexIntegrityError) as excinfo:
        open_index_db(index_db_path)
    assert str(index_db_path) in str(excinfo.value)


def test_schema_idempotent(index_db_path: Path) -> None:
    conn = open_index_db(index_db_path)
    try:
        apply_index_schema(conn)
        apply_index_schema(conn)
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        indexes = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        }
    finally:
        conn.close()

    assert {"file_state", "chunks"} <= tables
    assert {"idx_file_state_status", "idx_file_state_kb"} <= indexes


def test_incremental_skip_fast_path_without_hash(
    index_db_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "note.md"
    size, mtime = _write(source, "same content")
    calls = 0

    def spy(path: Path) -> str:
        nonlocal calls
        calls += 1
        return StateStore.compute_sha256(path)

    with StateStore(index_db_path) as store:
        store.mark_embedded(source, "personal", size=size, mtime=mtime)
        monkeypatch.setattr(StateStore, "compute_sha256", staticmethod(spy))

        assert store.needs_reindex(source, "personal", size, mtime) is False

    assert calls == 0


def test_incremental_rehash_on_mtime_change(index_db_path: Path, tmp_path: Path) -> None:
    source = tmp_path / "note.md"
    size, mtime = _write(source, "same content")

    with StateStore(index_db_path) as store:
        store.mark_embedded(source, "personal", size=size, mtime=mtime)
        new_mtime = mtime + 10
        assert store.needs_reindex(source, "personal", size, new_mtime) is False

        size_changed, _ = _write(source, "different content")
        assert store.needs_reindex(source, "personal", size_changed, new_mtime + 10) is True


def test_needs_reindex_new_and_unfinished_statuses(index_db_path: Path, tmp_path: Path) -> None:
    source = tmp_path / "note.md"
    size, mtime = _write(source, "content")

    with StateStore(index_db_path) as store:
        assert store.needs_reindex(source, "personal", size, mtime) is True

        store.mark_pending(source, "personal", size=size, mtime=mtime)
        assert store.needs_reindex(source, "personal", size, mtime) is True

        store.mark_extracted(source, "personal", size=size, mtime=mtime)
        assert store.needs_reindex(source, "personal", size, mtime) is True

        store.mark_failed(source, "personal", "ExtractorError: boom")
        assert store.needs_reindex(source, "personal", size, mtime) is True


def test_crash_resume(index_db_path: Path, tmp_path: Path) -> None:
    source = tmp_path / "resume.md"
    size, mtime = _write(source, "content")

    store = StateStore(index_db_path)
    store.mark_extracted(source, "personal", size=size, mtime=mtime)
    store.close()

    reopened = StateStore(index_db_path)
    try:
        record = reopened.get(source, "personal")
        assert record is not None
        assert record.status == FileStatus.extracted
        assert [r.path for r in reopened.list_resumable("personal")] == [str(source)]
    finally:
        reopened.close()


def test_failed_attempts_cap(index_db_path: Path, tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    _write(source, "not a pdf")

    with StateStore(index_db_path, max_attempts=3) as store:
        store.mark_failed(source, "personal", "ExtractionError")
        assert [r.path for r in store.list_resumable("personal")] == [str(source)]

        store.mark_failed(source, "personal", "ExtractionError")
        store.mark_failed(source, "personal", "ExtractionError")

        assert store.list_resumable("personal") == []
        record = store.get(source, "personal")
        assert record is not None
        assert record.attempts == 3
        assert record.status == FileStatus.failed


def test_path_kb_independence(index_db_path: Path, tmp_path: Path) -> None:
    source = tmp_path / "shared.md"
    size, mtime = _write(source, "content")

    with StateStore(index_db_path) as store:
        store.mark_embedded(source, "personal", size=size, mtime=mtime)
        store.mark_pending(source, "beca", size=size, mtime=mtime)

        personal = store.get(source, "personal")
        beca = store.get(source, "beca")

    assert personal is not None
    assert beca is not None
    assert personal.status == FileStatus.embedded
    assert beca.status == FileStatus.pending


def test_mark_skipped_and_counts(index_db_path: Path, tmp_path: Path) -> None:
    skipped = tmp_path / "huge.bin"
    excluded = tmp_path / ".env"

    with StateStore(index_db_path) as store:
        store.mark_skipped(skipped, "personal", FileStatus.skipped_size)
        store.mark_excluded_secret(excluded, "personal")

        counts = store.counts_by_status("personal")

    assert counts[FileStatus.skipped_size] == 1
    assert counts[FileStatus.excluded_secret] == 1


def test_state_persists_after_reopen(index_db_path: Path, tmp_path: Path) -> None:
    source = tmp_path / "embedded.md"
    size, mtime = _write(source, "content")

    with StateStore(index_db_path) as store:
        store.mark_embedded(source, "personal", size=size, mtime=mtime)

    conn = _read_conn(index_db_path)
    try:
        row = conn.execute(
            "SELECT status FROM file_state WHERE path=? AND kb_id=?",
            (str(source), "personal"),
        ).fetchone()
    finally:
        conn.close()

    assert row == (FileStatus.embedded.value,)
