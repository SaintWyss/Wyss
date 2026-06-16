"""RED — toda escritura finance.record pasa la segunda muralla (AGENT-09, AI-SPEC D5).

D5 / failure mode #2 (D-70/D-84): un plan con `Action(type="finance.record", ...)` DEBE
recorrer `AgentBase.execute()` (template method no salteable) tras `CognitivePolicyEngine.
evaluate(plan)`. Si la política marca `Outcome.REJECT` / nivel D, `execute()` levanta
`PolicyViolation` ANTES de llamar `_run()` — la escritura al ledger NUNCA se materializa.

Estos tests FALLAN hasta que Plan 03 defina el agente Pellegrini concreto (subclase de
`AgentBase` cuyo `_run` escribe al ledger). El import del agente es diferido dentro de los
helpers: el fallo correcto es `ModuleNotFoundError`, no un import roto a nivel de colección.

Reusa `engine` (CognitivePolicyEngine real) y `RecordingEngine` de tests/agents/conftest.py.
"""

from __future__ import annotations

import pytest

from core.domain import Outcome, PolicyDecision, RiskLevel
from core.domain.errors import PolicyViolation
from core.domain.plan import Action, Plan
from core.policy import CognitivePolicyEngine
from core.ports.agent import AgentBase
from tests.agents.conftest import FakeAudit, RecordingEngine


def _finance_record_plan() -> Plan:
    """Plan owner-instruido con una escritura al ledger (finance.record)."""
    return Plan(
        task_id="fin-record-1",
        summary="registrar gasto de supermercado",
        steps=(
            Action(
                type="finance.record",
                target="ledger",
                parameters={"tipo": "GASTO", "monto": 800.0, "categoria": "supermercado"},
            ),
        ),
        rationale="el owner pidió registrar el gasto",
    )


def _build_pellegrini(audit: FakeAudit) -> AgentBase:
    """Construye el agente Pellegrini concreto (import diferido: RED hasta Plan 03)."""
    import agents.pellegrini as pellegrini  # type: ignore[import-untyped,import-not-found,unused-ignore]

    agent: AgentBase = pellegrini.build_pellegrini(audit=audit)
    return agent


def test_finance_record_routes_through_engine(engine: CognitivePolicyEngine) -> None:
    """D5: el plan finance.record es evaluado por CognitivePolicyEngine.evaluate (la muralla).

    RecordingEngine registra cada plan evaluado: tras evaluar el plan de escritura, debe
    aparecer en `.calls` — ninguna escritura al ledger esquiva el engine.
    """
    recording = RecordingEngine(engine)
    plan = _finance_record_plan()
    decision = recording.evaluate(plan)
    assert plan in recording.calls
    assert isinstance(decision, PolicyDecision)
    # finance.record no está en _BASE_LEVELS aún (Plan 03) → fail-closed a C como mínimo.
    assert decision.risk_level >= RiskLevel.B


def test_rejected_write_never_reaches_run(fake_audit: FakeAudit) -> None:
    """D5: una decisión REJECT hace que execute() levante PolicyViolation ANTES de _run().

    El agente Pellegrini (Plan 03) hereda el template method de AgentBase: ante REJECT no
    debe ejecutarse `_run()` y por ende no debe materializarse ninguna escritura al ledger.
    """
    agent = _build_pellegrini(fake_audit)
    plan = _finance_record_plan()
    reject_decision = PolicyDecision(
        task_id=plan.task_id,
        risk_level=RiskLevel.D,
        outcome=Outcome.REJECT,
        reasons=("escritura no owner-instruida (derivada de contenido de BC)",),
    )
    with pytest.raises(PolicyViolation):
        agent.execute(plan, reject_decision)


def test_non_owner_instructed_write_is_rejected(fake_audit: FakeAudit) -> None:
    """D5: una escritura derivada de contenido (no owner-instruida) no muta el ledger.

    Se simula una decisión REJECT (el origen no-owner lo marca el orquestador/engine) y se
    asierta que la ejecución del agente no aplica la escritura (PolicyViolation, sin _run).
    """
    agent = _build_pellegrini(fake_audit)
    plan = _finance_record_plan()
    decision = PolicyDecision(
        task_id=plan.task_id,
        risk_level=RiskLevel.D,
        outcome=Outcome.REJECT,
    )
    with pytest.raises(PolicyViolation):
        agent.execute(plan, decision)
