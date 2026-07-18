"""Tests de PendingStore SQLite y ttl_reaper (ORCH-06 / D-54..D-56)."""

import sqlite3
from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime
from pathlib import Path

from core.domain.audit import AuditEvent, AuditEventType, Span
from core.domain.plan import Action, Plan
from core.domain.policy import PolicyDecision
from core.domain.risk import Outcome, RiskLevel
from orchestrator.pending_store import PendingStore
from orchestrator.ttl_reaper import reap_once


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def log(self, event: AuditEvent) -> None:
        self.events.append(event)

    def span(self, task_id: str, actor: str, event: str) -> AbstractContextManager[Span]:
        return nullcontext(
            Span(task_id=task_id, actor=actor, event=event, started_at=datetime.now(UTC))
        )


def _read_conn(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def _plan(task_id: str = "task-pending") -> Plan:
    return Plan(
        task_id=task_id,
        summary="mover archivo",
        steps=(Action(type="file.move", target="/tmp/origen.txt"),),
        rationale="test",
    )


def _decision(level: RiskLevel = RiskLevel.B) -> PolicyDecision:
    outcome = Outcome.CONFIRM_SIMPLE if level == RiskLevel.B else Outcome.CONFIRM_STRONG
    return PolicyDecision(task_id="task-pending", risk_level=level, outcome=outcome)


def test_wal_active(pending_store: PendingStore, tmp_path: Path) -> None:
    conn = _read_conn(tmp_path / "pending.db")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        indexes = {row[1] for row in conn.execute("PRAGMA index_list('pending_proposals')")}
    finally:
        conn.close()

    assert str(mode).lower() == "wal"
    assert "idx_pending_status" in indexes
    paths = [
        tmp_path / "pending.db",
        tmp_path / "pending.db-wal",
        tmp_path / "pending.db-shm",
    ]
    assert all((item.stat().st_mode & 0o777) == 0o600 for item in paths if item.exists())


def test_existing_schema_migrates_revision_without_data_loss(tmp_path: Path) -> None:
    path = tmp_path / "pending-old.db"
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE pending_proposals ("
        "id TEXT PRIMARY KEY, task_id TEXT NOT NULL, plan_json TEXT NOT NULL, "
        "risk_level TEXT NOT NULL, outcome TEXT NOT NULL, status TEXT NOT NULL, "
        "created_at TEXT NOT NULL, expires_at TEXT NOT NULL, resolved_at TEXT, resolved_by TEXT)"
    )
    conn.execute(
        "INSERT INTO pending_proposals VALUES "
        "('old', 'task-old', '{}', 'B', 'CONFIRM_SIMPLE', 'pending', "
        "'2026-01-01T00:00:00+00:00', '2099-01-01T00:00:00+00:00', NULL, NULL)"
    )
    conn.commit()
    conn.close()

    store = PendingStore(path)
    try:
        loaded = store.load("old")
        assert loaded is not None
        assert loaded.revision == 1
        assert loaded.task_id == "task-old"
    finally:
        store.close()


def test_pending_survives_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "pending.db"
    store = PendingStore(db_path)
    first_id = store.save(_plan("task-1"), _decision(), ttl_seconds=60)
    second_id = store.save(_plan("task-2"), _decision(), ttl_seconds=60)
    store.close()

    reopened = PendingStore(db_path)
    try:
        pending = reopened.load_pending()
    finally:
        reopened.close()

    assert {proposal.id for proposal in pending} == {first_id, second_id}
    assert {proposal.status for proposal in pending} == {"pending"}


def test_expire_old_sets_status_expired(pending_store: PendingStore) -> None:
    pending_id = pending_store.save(_plan(), _decision(), ttl_seconds=-1)

    expired = pending_store.expire_old()
    loaded = pending_store.load(pending_id)

    assert [proposal.id for proposal in expired] == [pending_id]
    assert loaded is not None
    assert loaded.status == "expired"
    assert loaded.resolved_by == "ttl_reaper"
    assert loaded.resolved_at is not None


def test_confirm_rejects_expired_proposal(pending_store: PendingStore) -> None:
    pending_id = pending_store.save(_plan(), _decision(), ttl_seconds=-1)
    pending_store.expire_old()

    resolved = pending_store.resolve(pending_id, resolved_by="owner")
    loaded = pending_store.load(pending_id)

    assert resolved is None
    assert loaded is not None
    assert loaded.status == "expired"
    assert loaded.resolved_by == "ttl_reaper"


def test_resolve_rejects_expired_without_reaper(pending_store: PendingStore) -> None:
    """El TTL forma parte del compare-and-swap, no depende del reaper."""
    pending_id = pending_store.save(_plan(), _decision(), ttl_seconds=-1)

    resolved = pending_store.resolve(pending_id, resolved_by="owner", expected_revision=1)

    assert resolved is None
    loaded = pending_store.load(pending_id)
    assert loaded is not None
    assert loaded.status == "pending"
    assert loaded.revision == 1


def test_resolve_by_id_does_not_affect_other_pending(
    pending_store: PendingStore,
) -> None:
    first_id = pending_store.save(_plan("task-1"), _decision(), ttl_seconds=60)
    second_id = pending_store.save(_plan("task-2"), _decision(), ttl_seconds=60)

    resolved = pending_store.resolve(first_id, resolved_by="owner")
    other = pending_store.load(second_id)

    assert resolved is not None
    assert resolved.status == "confirmed"
    assert resolved.resolved_by == "owner"
    assert other is not None
    assert other.status == "pending"


def test_double_resolve_is_atomic(pending_store: PendingStore) -> None:
    """PR-08 (regresión de carrera): resolve() usa UPDATE ... WHERE status='pending' +
    rowcount, así que de dos confirmaciones concurrentes solo UNA gana; la segunda
    recibe None y no puede disparar ejecución."""
    pending_id = pending_store.save(_plan(), _decision(), ttl_seconds=60)

    first = pending_store.resolve(pending_id, resolved_by="owner")
    second = pending_store.resolve(pending_id, resolved_by="owner")

    assert first is not None
    assert first.status == "confirmed"
    assert first.revision == 2
    assert second is None


def test_double_resolve_across_independent_connections(tmp_path: Path) -> None:
    path = tmp_path / "pending-shared.db"
    first = PendingStore(path)
    second = PendingStore(path)
    try:
        pending_id = first.save(_plan(), _decision(), ttl_seconds=60)

        winner = first.resolve(pending_id, resolved_by="panel", expected_revision=1)
        loser = second.resolve(pending_id, resolved_by="android", expected_revision=1)

        assert winner is not None
        assert winner.revision == 2
        assert loser is None
        current = second.load(pending_id)
        assert current is not None
        assert current.resolved_by == "panel"
    finally:
        first.close()
        second.close()


def test_expected_revision_is_compared_atomically(pending_store: PendingStore) -> None:
    pending_id = pending_store.save(_plan(), _decision(), ttl_seconds=60)

    stale = pending_store.resolve(pending_id, resolved_by="owner", expected_revision=2)
    current = pending_store.load(pending_id)

    assert stale is None
    assert current is not None
    assert current.status == "pending"
    assert current.revision == 1


def test_expire_is_revisioned_compare_and_swap(pending_store: PendingStore) -> None:
    pending_id = pending_store.save(_plan(), _decision(), ttl_seconds=-1)

    stale = pending_store.expire(pending_id, expected_revision=2)
    expired = pending_store.expire(pending_id, expected_revision=1)

    assert stale is None
    assert expired is not None
    assert expired.status == "expired"
    assert expired.revision == 2


def test_explicit_rejection_resolves_without_confirming(pending_store: PendingStore) -> None:
    pending_id = pending_store.save(_plan(), _decision(), ttl_seconds=60)

    rejected = pending_store.resolve(pending_id, resolved_by="panel:living", status="rejected")
    second = pending_store.resolve(pending_id, resolved_by="owner")

    assert rejected is not None
    assert rejected.status == "rejected"
    assert rejected.resolved_by == "panel:living"
    assert second is None


def test_reap_once_expires_and_audits(pending_store: PendingStore) -> None:
    pending_id = pending_store.save(_plan(), _decision(RiskLevel.C), ttl_seconds=-1)
    audit = FakeAudit()

    count = reap_once(pending_store, audit)
    loaded = pending_store.load(pending_id)

    assert count == 1
    assert loaded is not None
    assert loaded.status == "expired"
    assert len(audit.events) == 1
    event = audit.events[0]
    assert event.event_type is AuditEventType.CONFIRMATION_ANSWERED
    assert event.task_id == "task-pending"
    assert event.payload["pending_id"] == pending_id
    assert event.payload["risk_level"] == "C"
