"""Vocabulario de auditoría: actores, taxonomía de eventos, AuditEvent y Span (D-07, AUD-01)."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class ActorType(StrEnum):
    """Quién origina un evento auditado."""

    OWNER = "owner"
    ORCHESTRATOR = "orchestrator"
    AGENT = "agent"
    WORKER = "worker"
    SYSTEM = "system"


class AuditEventType(StrEnum):
    """Taxonomía cerrada que cubre los 8 campos D-07 vía eventos correlacionados por task_id."""

    COMMAND_RECEIVED = "command.received"
    PLAN_CREATED = "plan.created"
    POLICY_DECISION = "policy.decision"
    CONFIRMATION_REQUESTED = "confirmation.requested"
    CONFIRMATION_ANSWERED = "confirmation.answered"
    ACTION_STARTED = "action.started"
    ACTION_COMPLETED = "action.completed"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    COST_RECORDED = "cost.recorded"
    SPAN_STARTED = "span.started"
    SPAN_COMPLETED = "span.completed"
    SPAN_FAILED = "span.failed"
    # SCHED-05: disparo de rutina, distinguible de command.received en la traza
    ROUTINE_TRIGGERED = "routine.triggered"
    DIGEST_GENERATED = "digest.generated"


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """Un evento append-only del log de auditoría.

    Usar la factory `new()` para generar `event_id` y `created_at` correctos —
    jamás `datetime.utcnow()` (naive), siempre `datetime.now(timezone.utc)`.
    """

    event_id: str
    task_id: str | None
    actor_type: ActorType
    actor_id: str
    event_type: AuditEventType
    message: str
    payload: Mapping[str, object]
    created_at: datetime

    @classmethod
    def new(
        cls,
        *,
        actor_type: ActorType,
        actor_id: str,
        event_type: AuditEventType,
        message: str,
        task_id: str | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> "AuditEvent":
        """Crea un evento con `event_id` uuid4 hex y timestamp UTC timezone-aware."""
        return cls(
            event_id=uuid.uuid4().hex,
            task_id=task_id,
            actor_type=actor_type,
            actor_id=actor_id,
            event_type=event_type,
            message=message,
            payload=payload if payload is not None else {},
            created_at=datetime.now(UTC),
        )


@dataclass(frozen=True, slots=True)
class Span:
    """Una operación temporizada (start/end/exception) auditada vía context manager."""

    task_id: str
    actor: str
    event: str
    started_at: datetime
