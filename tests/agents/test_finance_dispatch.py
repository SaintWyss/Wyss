"""Integracion de planes financieros de solo lectura con el dispatcher (D-87)."""

from __future__ import annotations

from pathlib import Path

from core.domain import Outcome, PolicyDecision, RiskLevel
from core.domain.plan import Action, Plan
from tests.agents.conftest import FakeAudit


async def test_d87_task_reports_via_dispatcher(fake_audit: FakeAudit, tmp_path: Path) -> None:
    """Un Plan finance.query de solo lectura se encola y audita via dispatcher."""
    from orchestrator.dispatcher import dispatch
    from orchestrator.pending_store import PendingStore

    plan = Plan(
        task_id="d87-finance-query",
        summary="Consultar gastos por categoria en el ledger",
        steps=(
            Action(
                type="finance.query",
                target="ledger",
                parameters={"consulta": "gastos_por_categoria"},
            ),
        ),
        rationale="La consulta es solo lectura y sirve para reportar el estado financiero.",
    )
    decision = PolicyDecision(
        task_id=plan.task_id,
        risk_level=RiskLevel.A,
        outcome=Outcome.EXECUTE,
    )
    store = PendingStore(tmp_path / "pending.db")
    try:
        resultado = await dispatch(plan, decision, pending_store=store, audit=fake_audit)
    finally:
        store.close()

    assert resultado["outcome"] == "queued"
    assert fake_audit.events, "el dispatcher debe auditar la decision de politica"
