"""Tests de MemoryStore SQLite (MEM-01 / MEM-03)."""

import sqlite3
from pathlib import Path
from time import sleep

import pytest

from core.domain.errors import AuditIntegrityError
from memory.store import MemoryStore


def _read_conn(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def test_wal_active_and_schema_created(
    memory_store: MemoryStore, tmp_path: Path
) -> None:
    conn = _read_conn(tmp_path / "memory.db")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        indexes = {
            row[1] for row in conn.execute("PRAGMA index_list('memory_facts')")
        }
        columns = {
            row[1]: row[4] for row in conn.execute("PRAGMA table_info('memory_facts')")
        }
    finally:
        conn.close()

    assert memory_store.list_all() == []
    assert str(mode).lower() == "wal"
    assert "memory_facts" in tables
    assert "idx_memory_facts_category_updated" in indexes
    assert columns["tier"] == "'owner'"


def test_remember_and_recall_round_trip_including_tier(
    memory_store: MemoryStore,
) -> None:
    fact_id = memory_store.remember(
        category="profile",
        value="Prefiere respuestas concisas",
        tier="owner",
        source="owner",
    )

    facts = memory_store.recall("profile")

    assert len(fact_id) == 32
    assert len(facts) == 1
    fact = facts[0]
    assert fact.id == fact_id
    assert fact.category == "profile"
    assert fact.value == "Prefiere respuestas concisas"
    assert fact.tier == "owner"
    assert fact.source == "owner"
    assert fact.created_at
    assert fact.updated_at == fact.created_at


def test_recall_filters_category(memory_store: MemoryStore) -> None:
    profile_id = memory_store.remember("profile", "timezone America/Argentina", "owner", "owner")
    memory_store.remember("project", "usa uv", "external", "repo")

    facts = memory_store.recall("profile")

    assert [fact.id for fact in facts] == [profile_id]


def test_list_all_orders_by_updated_at_desc(memory_store: MemoryStore) -> None:
    first_id = memory_store.remember("profile", "primero", "owner", "owner")
    second_id = memory_store.remember("project", "segundo", "external", "repo")
    sleep(0.001)
    assert memory_store.edit(first_id, "primero actualizado") is True

    facts = memory_store.list_all()

    assert [fact.id for fact in facts] == [first_id, second_id]


def test_recall_respects_limit_and_updated_order(memory_store: MemoryStore) -> None:
    old_id = memory_store.remember("profile", "viejo", "owner", "owner")
    new_id = memory_store.remember("profile", "nuevo", "external", "repo")
    sleep(0.001)
    assert memory_store.edit(old_id, "viejo actualizado") is True

    facts = memory_store.recall("profile", limit=1)

    assert [fact.id for fact in facts] == [old_id]
    assert new_id not in {fact.id for fact in facts}


def test_edit_returns_true_and_changes_value(memory_store: MemoryStore) -> None:
    fact_id = memory_store.remember("profile", "antes", "owner", "owner")

    assert memory_store.edit(fact_id, "despues") is True
    loaded = memory_store.recall("profile")

    assert loaded[0].value == "despues"
    assert loaded[0].updated_at >= loaded[0].created_at


def test_forget_returns_true_and_removes_fact(memory_store: MemoryStore) -> None:
    fact_id = memory_store.remember("profile", "temporal", "owner", "owner")

    assert memory_store.forget(fact_id) is True
    assert memory_store.recall("profile") == []
    assert memory_store.forget(fact_id) is False


def test_edit_missing_id_returns_false(memory_store: MemoryStore) -> None:
    assert memory_store.edit("missing", "value") is False


def test_forget_missing_id_returns_false(memory_store: MemoryStore) -> None:
    assert memory_store.forget("missing") is False


def test_wal_guard_fails_closed_when_pragma_does_not_return_wal() -> None:
    with pytest.raises(AuditIntegrityError):
        MemoryStore(Path(":memory:"))


def test_context_manager_closes_connection(tmp_path: Path) -> None:
    with MemoryStore(tmp_path / "memory.db") as store:
        store.remember("profile", "temporal", "owner", "owner")

    with pytest.raises(sqlite3.ProgrammingError):
        store.list_all()
