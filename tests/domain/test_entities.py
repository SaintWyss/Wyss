"""Tests de inmutabilidad y semántica del vocabulario de dominio (Pitfall 2, POL-02/04, D-07)."""

import dataclasses
from datetime import UTC

import pytest

from core.domain import (
    Action,
    ActorType,
    AuditEvent,
    AuditEventType,
    Outcome,
    Plan,
    RiskLevel,
    outcome_for,
)


def _sample_plan() -> Plan:
    return Plan(
        task_id="t-1",
        summary="resumen original",
        steps=(Action(type="file.read", target="/tmp/a.txt"),),
        rationale="porque sí",
    )


def test_plan_is_frozen() -> None:
    """Mutar un Plan evaluado falla con FrozenInstanceError (T-1-T: tampering imposible)."""
    plan = _sample_plan()
    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.summary = "mutado"  # type: ignore[misc]


def test_plan_steps_is_tuple() -> None:
    """`Plan.steps` es tuple inmutable, nunca list (Pitfall 2)."""
    plan = _sample_plan()
    assert isinstance(plan.steps, tuple)


def test_risk_level_total_order() -> None:
    """Orden total A<B<C<D habilita max() — 'subir sí, bajar jamás' (POL-04, T2)."""
    assert max(RiskLevel.A, RiskLevel.C) == RiskLevel.C
    assert RiskLevel.B < RiskLevel.D
    assert RiskLevel.A < RiskLevel.B < RiskLevel.C < RiskLevel.D


def test_outcome_for_maps_all_levels() -> None:
    """outcome_for mapea los 4 niveles a los 4 outcomes (D-03/POL-02)."""
    assert outcome_for(RiskLevel.A) is Outcome.EXECUTE
    assert outcome_for(RiskLevel.B) is Outcome.CONFIRM_SIMPLE
    assert outcome_for(RiskLevel.C) is Outcome.CONFIRM_STRONG
    assert outcome_for(RiskLevel.D) is Outcome.REJECT


def test_audit_event_new_is_utc_aware_with_hex_id() -> None:
    """AuditEvent.new() produce created_at UTC tz-aware y event_id hex de 32 chars (Pitfall 5)."""
    event = AuditEvent.new(
        actor_type=ActorType.SYSTEM,
        actor_id="boot",
        event_type=AuditEventType.SPAN_STARTED,
        message="arranque",
    )
    assert event.created_at.tzinfo is UTC
    assert len(event.event_id) == 32
    assert int(event.event_id, 16) >= 0  # hex válido
    assert event.payload == {}


def test_audit_event_is_frozen() -> None:
    """El evento de auditoría también es inmutable."""
    event = AuditEvent.new(
        actor_type=ActorType.OWNER,
        actor_id="santiago",
        event_type=AuditEventType.COMMAND_RECEIVED,
        message="hola",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.message = "otro"  # type: ignore[misc]
