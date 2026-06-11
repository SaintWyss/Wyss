"""Fixtures de los tests del SqliteAuditLogger."""

from collections.abc import Callable, Iterator, Mapping
from pathlib import Path

import pytest

from audit import SqliteAuditLogger
from core.domain.audit import ActorType, AuditEvent, AuditEventType


@pytest.fixture
def logger(tmp_path: Path) -> Iterator[SqliteAuditLogger]:
    """SqliteAuditLogger sobre tmp_path (ext4/tmpfs — WAL funciona)."""
    log = SqliteAuditLogger(tmp_path / "audit.db")
    try:
        yield log
    finally:
        log.close()


@pytest.fixture
def make_event() -> Callable[..., AuditEvent]:
    """Factory de AuditEvent.new con defaults razonables."""

    def _make(
        *,
        task_id: str | None = "task-1",
        actor_type: ActorType = ActorType.OWNER,
        actor_id: str = "santiago",
        event_type: AuditEventType = AuditEventType.COMMAND_RECEIVED,
        message: str = "evento de prueba",
        payload: Mapping[str, object] | None = None,
    ) -> AuditEvent:
        return AuditEvent.new(
            task_id=task_id,
            actor_type=actor_type,
            actor_id=actor_id,
            event_type=event_type,
            message=message,
            payload=payload,
        )

    return _make
