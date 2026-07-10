"""Tests de RoutineStore SQLite (SCHED-03)."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.domain.errors import AuditIntegrityError
from orchestrator.routine_store import RoutineStore


@pytest.fixture
def routine_store(tmp_path: Path) -> Iterator[RoutineStore]:
    store = RoutineStore(tmp_path / "routines.db")
    try:
        yield store
    finally:
        store.close()


def _read_conn(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def test_wal_active_and_schema_created(
    routine_store: RoutineStore, tmp_path: Path
) -> None:
    conn = _read_conn(tmp_path / "routines.db")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        indexes = {row[1] for row in conn.execute("PRAGMA index_list('routines')")}
    finally:
        conn.close()

    assert routine_store.list_all() == []
    assert str(mode).lower() == "wal"
    assert "routines" in tables
    assert "idx_routines_status" in indexes


def test_add_returns_id_and_get_round_trips_fields(
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        name="daily summary",
        schedule_kind="cron",
        schedule_expr="0 8 * * *",
        plan_json='{"task": "summary"}',
        catch_up=True,
    )

    loaded = routine_store.get(routine_id)

    assert len(routine_id) == 32
    assert loaded is not None
    assert loaded.id == routine_id
    assert loaded.name == "daily summary"
    assert loaded.schedule_kind == "cron"
    assert loaded.schedule_expr == "0 8 * * *"
    assert loaded.plan_json == '{"task": "summary"}'
    assert loaded.catch_up is True
    assert loaded.status == "active"
    assert loaded.created_at
    assert loaded.last_fired_at is None
    assert loaded.last_outcome is None


def test_list_all_and_list_active_filter_status(routine_store: RoutineStore) -> None:
    first_id = routine_store.add("first", "interval", "300", "{}", catch_up=True)
    second_id = routine_store.add("second", "cron", "0 9 * * *", "{}", catch_up=True)
    assert routine_store.pause(second_id) is True

    all_routines = routine_store.list_all()
    active = routine_store.list_active()

    assert [routine.id for routine in all_routines] == [first_id, second_id]
    assert [routine.id for routine in active] == [first_id]


def test_catch_up_persists_as_integer_and_reads_as_bool(
    routine_store: RoutineStore, tmp_path: Path
) -> None:
    routine_id = routine_store.add("no catchup", "interval", "60", "{}", catch_up=False)
    loaded = routine_store.get(routine_id)
    conn = _read_conn(tmp_path / "routines.db")
    try:
        stored = conn.execute(
            "SELECT catch_up FROM routines WHERE id=?", (routine_id,)
        ).fetchone()[0]
    finally:
        conn.close()

    assert stored == 0
    assert loaded is not None
    assert loaded.catch_up is False


def test_wal_guard_fails_closed_when_pragma_does_not_return_wal() -> None:
    with pytest.raises(AuditIntegrityError):
        RoutineStore(Path(":memory:"))


def test_pause_and_resume_are_durable(routine_store: RoutineStore) -> None:
    routine_id = routine_store.add("daily", "cron", "0 8 * * *", "{}", catch_up=True)

    assert routine_store.pause(routine_id) is True
    paused = routine_store.get(routine_id)
    assert paused is not None
    assert paused.status == "paused"

    assert routine_store.resume(routine_id) is True
    resumed = routine_store.get(routine_id)
    assert resumed is not None
    assert resumed.status == "active"


def test_pause_resume_missing_id_return_false(routine_store: RoutineStore) -> None:
    assert routine_store.pause("missing") is False
    assert routine_store.resume("missing") is False


def test_delete_removes_row_and_missing_id_is_false(
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add("daily", "cron", "0 8 * * *", "{}", catch_up=True)

    assert routine_store.delete(routine_id) is True
    assert routine_store.get(routine_id) is None
    assert routine_store.delete(routine_id) is False


def test_mark_fired_sets_timestamp_and_outcome(
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add("daily", "cron", "0 8 * * *", "{}", catch_up=True)
    fired_at = datetime.now(UTC).isoformat()

    assert routine_store.mark_fired(routine_id, fired_at, "ok") is True
    loaded = routine_store.get(routine_id)

    assert loaded is not None
    assert loaded.last_fired_at == fired_at
    assert loaded.last_outcome == "ok"


def test_mark_fired_missing_id_returns_false(routine_store: RoutineStore) -> None:
    fired_at = datetime.now(UTC).isoformat()

    assert routine_store.mark_fired("missing", fired_at, "ok") is False
