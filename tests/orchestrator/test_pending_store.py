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
