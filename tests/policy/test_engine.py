"""Tests directos del CognitivePolicyEngine."""

from core.domain.plan import Action, Plan
from core.domain.risk import Outcome, RiskLevel
from core.policy import CognitivePolicyEngine


def _plan(*steps: Action) -> Plan:
    return Plan(
        task_id="t",
        summary="policy",
        steps=tuple(steps),
        rationale="test",
    )


def test_memory_remember_es_B_confirmacion_simple(
    engine: CognitivePolicyEngine,
) -> None:
    """MEM-01: recordar memoria owner-instruida queda en bandeja B."""
    decision = engine.evaluate(
        _plan(
            Action(
                "memory.remember",
                "preferencias",
                {"value": "cafe sin azucar"},
            )
        )
    )

    assert decision.risk_level == RiskLevel.B
    assert decision.outcome == Outcome.CONFIRM_SIMPLE


def test_memory_unknown_action_type_es_C_fail_closed(
    engine: CognitivePolicyEngine,
) -> None:
    """Un memory.* no registrado conserva el fail-closed a C."""
    decision = engine.evaluate(_plan(Action("memory.frobnicate", "preferencias")))

    assert decision.risk_level == RiskLevel.C
    assert decision.outcome == Outcome.CONFIRM_STRONG
