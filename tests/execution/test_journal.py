"""Tests de UndoJournal SQLite-WAL (EXEC-03 / D-65).

Mirrors tests/orchestrator/test_pending_store.py structure.
"""

import shutil
import sqlite3
from pathlib import Path

import pytest

from core.domain.errors import AuditIntegrityError
from execution.journal import UndoJournal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _action_dict(action_type: str = "file.move") -> dict[str, object]:
    """Builds a minimal inverse_op dict for test records."""
    if action_type == "file.move":
        return {
            "type": "file.move",
            "target": "/tmp/dest.txt",
            "parameters": {"destination": "/tmp/origin.txt"},
        }
    if action_type == "file.delete":
        return {"type": "file.delete", "target": "/tmp/written.txt", "parameters": {}}
    if action_type == "file.write":
        return {
            "type": "file.write",
            "target": "/tmp/origin.txt",
            "parameters": {"backup_path": "data/undo_backups/placeholder"},
        }
    return {"type": action_type, "target": "/tmp/x.txt", "parameters": {}}


# ---------------------------------------------------------------------------
# Task 1: WAL active, schema, record/load/mark round-trip
# ---------------------------------------------------------------------------


def test_wal_active(journal: UndoJournal, tmp_path: Path) -> None:
    """journal_mode is 'wal' after construction."""
    conn = sqlite3.connect(tmp_path / "journal.db")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()

    assert str(mode).lower() == "wal"


def test_record_returns_hex_string(journal: UndoJournal) -> None:
    """record() returns a non-empty hex string."""
    entry_id = journal.record(
        task_id="t-1",
        step_index=0,
        action_type="file.move",
        origin="/tmp/a.txt",
        destination="/tmp/b.txt",
        inverse_op=_action_dict("file.move"),
    )
    assert isinstance(entry_id, str)
    assert len(entry_id) == 32  # uuid4().hex is 32 hex chars
    int(entry_id, 16)  # must be valid hex


def test_load_returns_pending_entry(journal: UndoJournal) -> None:
    """load() returns the recorded entry with status='pending'."""
    entry_id = journal.record(
        task_id="t-1",
        step_index=0,
        action_type="file.move",
        origin="/tmp/a.txt",
        destination="/tmp/b.txt",
        inverse_op=_action_dict("file.move"),
    )
    entry = journal.load(entry_id)

    assert entry is not None
    assert entry.id == entry_id
    assert entry.task_id == "t-1"
    assert entry.step_index == 0
    assert entry.action_type == "file.move"
    assert entry.origin == "/tmp/a.txt"
    assert entry.destination == "/tmp/b.txt"
    assert entry.status == "pending"
    assert entry.resolved_at is None


def test_load_missing_returns_none(journal: UndoJournal) -> None:
    """load() returns None for an unknown entry_id."""
    assert journal.load("0" * 32) is None


def test_mark_applied_changes_status(journal: UndoJournal) -> None:
    """mark_applied() flips status to 'applied' and sets resolved_at."""
    entry_id = journal.record(
        task_id="t-2",
        step_index=1,
        action_type="file.move",
        origin="/tmp/a.txt",
        destination="/tmp/b.txt",
        inverse_op=_action_dict("file.move"),
    )
    journal.mark_applied(entry_id)
    entry = journal.load(entry_id)

    assert entry is not None
    assert entry.status == "applied"
    assert entry.resolved_at is not None


def test_mark_rolled_back_changes_status(journal: UndoJournal) -> None:
    """mark_rolled_back() flips status to 'rolled_back' and sets resolved_at."""
    entry_id = journal.record(
        task_id="t-3",
        step_index=2,
        action_type="file.delete",
        origin="/tmp/c.txt",
        destination=None,
        inverse_op=_action_dict("file.delete"),
    )
    journal.mark_rolled_back(entry_id)
    entry = journal.load(entry_id)

    assert entry is not None
    assert entry.status == "rolled_back"
    assert entry.resolved_at is not None


def test_constructor_raises_on_non_wal_fs(tmp_path: Path) -> None:
    """AuditIntegrityError raised when WAL cannot be activated."""
    db_path = tmp_path / "no_wal.db"

    # Patch: force journal_mode to MEMORY (read-only FS simulation is complex);
    # use monkeypatching approach instead — we subclass to inject a fake connection.
    # Strategy: create a DB and then set PRAGMA journal_mode=DELETE via raw sqlite3,
    # then attempt construction on that path via a subclass that skips pragma enforcement.
    # Simplest reproducible test: monkeypatch via test that checks the error message.
    # We cannot easily force WAL to fail on ext4, so we test via mock/patch.

    # Import patch
    import unittest.mock as mock

    # Patch sqlite3.connect to return a connection that returns 'delete' for WAL pragma
    fake_row = mock.MagicMock()
    fake_row.__getitem__ = mock.Mock(return_value="delete")

    fake_conn = mock.MagicMock(spec=sqlite3.Connection)
    fake_conn.execute.return_value.fetchone.return_value = fake_row

    with (
        mock.patch("execution.journal.sqlite3.connect", return_value=fake_conn),
        pytest.raises(AuditIntegrityError, match="wal"),
    ):
        UndoJournal(db_path)


def test_journal_context_manager(tmp_path: Path) -> None:
    """UndoJournal works as a context manager."""
    db_path = tmp_path / "ctx.db"
    with UndoJournal(db_path) as j:
        entry_id = j.record(
            task_id="ctx-task",
            step_index=0,
            action_type="file.move",
            origin="/tmp/x.txt",
            destination="/tmp/y.txt",
            inverse_op=_action_dict("file.move"),
        )
    # After exiting, connection is closed — further reads would error.
    assert entry_id is not None


# ---------------------------------------------------------------------------
# Task 2: restore() + overwrite backup + durability across reopen
# ---------------------------------------------------------------------------


def test_entry_survives_reopen(tmp_path: Path) -> None:
    """Entry persists across close/reopen (WAL durability)."""
    db_path = tmp_path / "journal.db"
    journal = UndoJournal(db_path)
    entry_id = journal.record(
        task_id="t-1",
        step_index=0,
        action_type="file.move",
        origin="/tmp/a.txt",
        destination="/tmp/b.txt",
        inverse_op=_action_dict("file.move"),
    )
    journal.close()

    reopened = UndoJournal(db_path)
    try:
        entry = reopened.load(entry_id)
    finally:
        reopened.close()

    assert entry is not None
    assert entry.status == "pending"
    assert entry.id == entry_id


def test_record_then_restore_move(tmp_path: Path) -> None:
    """restore() reverses a file.move (moves dest back to origin)."""
    db_path = tmp_path / "journal.db"

    # Create files on tmp_path
    origin = tmp_path / "origin.txt"
    dest = tmp_path / "dest.txt"
    origin.write_text("hello")
    # Simulate: move origin→dest already happened
    shutil.move(str(origin), str(dest))
    assert dest.exists()
    assert not origin.exists()

    inverse_op: dict[str, object] = {
        "type": "file.move",
        "target": str(dest),
        "parameters": {"destination": str(origin)},
    }

    journal = UndoJournal(db_path)
    try:
        entry_id = journal.record(
            task_id="t-move",
            step_index=0,
            action_type="file.move",
            origin=str(origin),
            destination=str(dest),
            inverse_op=inverse_op,
        )
        result = journal.restore(entry_id)
        entry = journal.load(entry_id)
    finally:
        journal.close()

    assert result is True
    assert origin.exists()
    assert not dest.exists()
    assert entry is not None
    assert entry.status == "rolled_back"


def test_restore_overwrite_from_backup(tmp_path: Path) -> None:
    """restore() rewrites original bytes from data/undo_backups/{entry_id}."""
    db_path = tmp_path / "journal.db"

    # Set up: a file with original content that will be overwritten
    target_file = tmp_path / "target.txt"
    original_content = b"original content"
    new_content = b"new overwritten content"

    # The backup dir in journal convention lives at data/undo_backups/
    # For this test we patch the backup_base_dir to tmp_path / "undo_backups"
    backup_dir = tmp_path / "undo_backups"
    backup_dir.mkdir()

    journal = UndoJournal(db_path, backup_base_dir=backup_dir)
    try:
        # Step 1: file exists with original content
        target_file.write_bytes(original_content)

        # Step 2: record BEFORE mutation (pre-capture)
        entry_id = journal.record(
            task_id="t-write",
            step_index=0,
            action_type="file.write",
            origin=str(target_file),
            destination=None,
            inverse_op={
                "type": "file.write",
                "target": str(target_file),
                "parameters": {},
            },
        )
        # Step 3: capture backup while file still has original content
        journal.capture_overwrite_backup(entry_id, target_file)

        # Step 4: mutation happens (overwrite with new content)
        target_file.write_bytes(new_content)
        assert target_file.read_bytes() == new_content

        # Step 5: restore should revert to original_content
        result = journal.restore(entry_id)
        entry = journal.load(entry_id)
    finally:
        journal.close()

    assert result is True
    assert target_file.read_bytes() == original_content
    assert entry is not None
    assert entry.status == "rolled_back"


def test_restore_missing_returns_false(tmp_path: Path) -> None:
    """restore() returns False for missing/unknown entry_id — no exception."""
    db_path = tmp_path / "journal.db"
    journal = UndoJournal(db_path)
    try:
        result = journal.restore("0" * 32)
    finally:
        journal.close()

    assert result is False


def test_restore_already_rolled_back_returns_false(tmp_path: Path) -> None:
    """restore() returns False if status != 'pending' (already rolled back)."""
    db_path = tmp_path / "journal.db"
    origin = tmp_path / "origin.txt"
    dest = tmp_path / "dest.txt"
    origin.write_text("hello")
    shutil.move(str(origin), str(dest))

    inverse_op: dict[str, object] = {
        "type": "file.move",
        "target": str(dest),
        "parameters": {"destination": str(origin)},
    }

    journal = UndoJournal(db_path)
    try:
        entry_id = journal.record(
            task_id="t-double",
            step_index=0,
            action_type="file.move",
            origin=str(origin),
            destination=str(dest),
            inverse_op=inverse_op,
        )
        first = journal.restore(entry_id)  # should succeed
        second = journal.restore(entry_id)  # should return False (already rolled back)
    finally:
        journal.close()

    assert first is True
    assert second is False
