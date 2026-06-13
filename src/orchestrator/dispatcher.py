"""Branching de planes por decisión de política para el daemon."""

import uuid
from collections.abc import Callable
from typing import Any

from core.domain import ActorType, AuditEvent, AuditEventType, Outcome, RiskLevel
from core.domain.plan import Plan
from core.domain.policy import PolicyDecision
from core.ports.audit import AuditPort
from orchestrator.pending_store import PendingStore
from orchestrator.plan_renderer import plan_to_text

DEFAULT_TTL_BY_LEVEL: dict[RiskLevel, int] = {
    RiskLevel.B: 3600,
    RiskLevel.C: 900,
}


def ttl_for_risk(level: RiskLevel) -> int:
    """TTL default para propuestas B/C."""
    return DEFAULT_TTL_BY_LEVEL.get(level, 900)


async def dispatch(
    plan: Plan,
    decision: PolicyDecision,
    *,
    pending_store: PendingStore,
    audit: AuditPort,
    ttl_for: Callable[[RiskLevel], int] = ttl_for_risk,
) -> dict[str, Any]:
    """Despacha por `PolicyDecision.outcome`; tipos corruptos cierran en REJECT.

    El daemon debe llamar `CognitivePolicyEngine.evaluate(plan)` antes de entrar acá.
    Este dispatcher no re-clasifica niveles: solo aplica la decisión determinística.
    """
    risk = decision.risk_level
    outcome = decision.outcome
    if (
        not isinstance(risk, RiskLevel)
        or not isinstance(outcome, Outcome)
        or outcome == Outcome.REJECT
        or risk >= RiskLevel.D
    ):
        _audit_policy_decision(
            audit,
            plan,
            decision,
            "plan rechazado por política",
        )
        return {
            "outcome": "rejected",
            "reasons": list(decision.reasons),
        }

    if outcome in (Outcome.CONFIRM_SIMPLE, Outcome.CONFIRM_STRONG):
        pending_id = pending_store.save(plan, decision, ttl_for(risk))
        audit.log(
            AuditEvent.new(
                task_id=plan.task_id,
                actor_type=ActorType.SYSTEM,
                actor_id="daemon",
                event_type=AuditEventType.CONFIRMATION_REQUESTED,
                message="confirmación requerida por política",
                payload={
                    "pending_id": pending_id,
                    "risk_level": risk.name,
                    "outcome": outcome.name,
                },
            )
        )
        return {
            "outcome": "pending",
            "pending_id": pending_id,
            "plan": plan_to_text(plan, decision),
        }

    execution_id = _enqueue_placeholder(plan)
    _audit_policy_decision(
        audit,
        plan,
        decision,
        "plan encolado por política",
        payload_extra={"execution_id": execution_id},
    )
    return {
        "outcome": "queued",
        "execution_id": execution_id,
    }


def _enqueue_placeholder(plan: Plan) -> str:
    """ID de ejecución durable futuro; Fase 6 implementa la cola real."""
    return f"exec-{plan.task_id}-{uuid.uuid4().hex[:12]}"


def _audit_policy_decision(
    audit: AuditPort,
    plan: Plan,
    decision: PolicyDecision,
    message: str,
    *,
    payload_extra: dict[str, object] | None = None,
) -> None:
    risk = decision.risk_level
    outcome = decision.outcome
    payload: dict[str, object] = {
        "risk_level": risk.name if isinstance(risk, RiskLevel) else repr(risk),
        "outcome": outcome.name if isinstance(outcome, Outcome) else repr(outcome),
        "matched_rules": list(decision.matched_rules),
        "reasons": list(decision.reasons),
    }
    if payload_extra is not None:
        payload.update(payload_extra)
    audit.log(
        AuditEvent.new(
            task_id=plan.task_id,
            actor_type=ActorType.SYSTEM,
            actor_id="daemon",
            event_type=AuditEventType.POLICY_DECISION,
            message=message,
            payload=payload,
        )
    )
