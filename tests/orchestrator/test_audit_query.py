"""Query del subcomando `audit` (AUD-02)."""

from pathlib import Path

from audit.sqlite_logger import SqliteAuditLogger
from bootstrap.cli import query_audit_events
from core.domain import ActorType, AuditEvent, AuditEventType


def test_audit_lista_eventos(tmp_path: Path) -> None:
    """AUD-02: `wyss audit` lista eventos del audit log en orden descendente."""
    db_path = tmp_path / "audit.db"
    logger = SqliteAuditLogger(db_path)
    try:
        for index in range(3):
            logger.log(
                AuditEvent.new(
                    actor_type=ActorType.SYSTEM,
                    actor_id=f"actor-{index}",
                    event_type=AuditEventType.POLICY_DECISION,
                    message=f"evento {index}",
                    task_id=f"task-{index}",
                )
            )
    finally:
        logger.close()

    rows = query_audit_events(db_path, limit=3)

    assert [row.message for row in rows] == ["evento 2", "evento 1", "evento 0"]
    assert [row.actor_id for row in rows] == ["actor-2", "actor-1", "actor-0"]
