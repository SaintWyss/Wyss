"""Semántica de seguridad de AgentBase: D absoluto + audit obligatorio (D-08, D-12, T1, T4)."""

import inspect

import pytest

from core.domain import (
    Action,
    AgentDefinition,
    AuditEventType,
    Outcome,
    Plan,
    PolicyDecision,
    PolicyViolation,
    RiskLevel,
)
from core.ports.agent import AgentBase
from tests.ports.fakes import (
    FakeAgent,
    FakeAuditPort,
    FakeModelGatewayPort,
    FakeRetrieval,
)


def _definition() -> AgentDefinition:
    return AgentDefinition(
        agent_id="belgrano",
        name="Belgrano",
        domain="estudio",
        kb_ids=frozenset(),
        model_alias="cheap",
        budget_usd=1.0,
    )


def _agent(audit: FakeAuditPort) -> FakeAgent:
    return FakeAgent(_definition(), FakeRetrieval(), FakeModelGatewayPort(), {}, audit)


def _plan() -> Plan:
    return Plan(
        task_id="t-1",
        summary="borrar todo",
        steps=(Action(type="file.delete", target="~/Documents/x"),),
        rationale="el owner lo pidió",
    )


def test_init_requires_audit_with_no_default() -> None:
    """`inspect.signature(AgentBase.__init__)` tiene `audit` sin default (D-08, T4)."""
    sig = inspect.signature(AgentBase.__init__)
    assert "audit" in sig.parameters
    assert sig.parameters["audit"].default is inspect.Parameter.empty


def test_agent_not_constructible_without_audit() -> None:
    """Construir un agente sin `audit` falla con TypeError (D-08)."""
    with pytest.raises(TypeError):
        FakeAgent(  # type: ignore[call-arg]
            _definition(),
            FakeRetrieval(),
            FakeModelGatewayPort(),
            {},
        )


def test_reject_outcome_raises_and_does_not_run() -> None:
    """Decisión REJECT → PolicyViolation, `_run` NUNCA se invoca, rechazo auditado (T1, POL-03)."""
    audit = FakeAuditPort()
    agent = _agent(audit)
    decision = PolicyDecision(
        task_id="t-1",
        risk_level=RiskLevel.D,
        outcome=Outcome.REJECT,
        matched_rules=("mass-delete",),
    )
    with pytest.raises(PolicyViolation):
        agent.execute(_plan(), decision)
    assert agent.run_called is False
    types = [e.event_type for e in audit.events]
    assert AuditEventType.POLICY_DECISION in types
    assert AuditEventType.ACTION_STARTED not in types


def test_level_d_with_non_reject_outcome_also_rejected() -> None:
    """Belt-and-suspenders: nivel D rechaza aunque el outcome no fuera REJECT explícito (T1)."""
    audit = FakeAuditPort()
    agent = _agent(audit)
    decision = PolicyDecision(
        task_id="t-1",
        risk_level=RiskLevel.D,
        outcome=Outcome.CONFIRM_STRONG,
    )
    with pytest.raises(PolicyViolation):
        agent.execute(_plan(), decision)
    assert agent.run_called is False


def test_raw_int_level_d_does_not_bypass_rejection() -> None:
    """CR-01: PolicyDecision con ints crudos (risk=4, outcome=3) NO saltea el rechazo D (T-01-04-EoP).

    `4 == RiskLevel.D` pero `4 is RiskLevel.D` es False: la guarda por identidad (`is`)
    dejaba correr `_run`. La guarda por valor/orden + isinstance debe rechazar fail-closed.
    """
    audit = FakeAuditPort()
    agent = _agent(audit)
    decision = PolicyDecision(
        task_id="t-1",
        risk_level=4,  # type: ignore[arg-type]
        outcome=3,  # type: ignore[arg-type]
    )
    with pytest.raises(PolicyViolation):
        agent.execute(_plan(), decision)
    assert agent.run_called is False
    types = [e.event_type for e in audit.events]
    assert AuditEventType.POLICY_DECISION in types
    assert AuditEventType.ACTION_STARTED not in types


def test_raw_int_corrupt_types_fail_closed() -> None:
    """CR-01 fail-closed: tipos no-enum (risk=4, outcome=1 ints crudos) rechazan, nunca ejecutan.

    outcome=1 (EXECUTE int crudo) + risk=4 (D int crudo): aunque el outcome int no sea REJECT,
    el isinstance guard rechaza por tipo corrupto antes de cualquier ejecución (T-01-04-EoP).
    """
    audit = FakeAuditPort()
    agent = _agent(audit)
    decision = PolicyDecision(
        task_id="t-1",
        risk_level=4,  # type: ignore[arg-type]
        outcome=1,  # type: ignore[arg-type]
    )
    with pytest.raises(PolicyViolation):
        agent.execute(_plan(), decision)
    assert agent.run_called is False


def test_allowed_decision_runs_and_audits() -> None:
    """Decisión A → `_run` se invoca; events contiene inicio y completado (flujo normal)."""
    audit = FakeAuditPort()
    agent = _agent(audit)
    decision = PolicyDecision(
        task_id="t-1",
        risk_level=RiskLevel.A,
        outcome=Outcome.EXECUTE,
    )
    report = agent.execute(_plan(), decision)
    assert agent.run_called is True
    assert report.success is True
    types = [e.event_type for e in audit.events]
    assert AuditEventType.ACTION_STARTED in types
    assert AuditEventType.TASK_COMPLETED in types
