"""Tests de seguridad del gate de costo (GATE-04): veta ANTES de la llamada (pre-autorización).

El presupuesto es enforced, no advisory (Pitfall 2): `authorize()` levanta `BudgetExceeded`
ANTES de cualquier `provider.complete()`. El costo se calcula LOCAL (tokens x precio config,
D-24); el costo reportado por el provider NUNCA gobierna el gate.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.domain.errors import BudgetExceeded, TraceIntegrityError
from gateway.cost import CostTracker
from tests.ports.fakes import FakeAuditPort

_PRICES = {
    "gemini-default": 2.0,  # USD por 1000 tokens (in+out) — valor de test
    "deepseek-default": 1.0,
}


def _tracker(
    db_path: Path,
    *,
    global_budget: float = 100.0,
    agent_budgets: dict[str, float] | None = None,
) -> CostTracker:
    return CostTracker(
        db_path=db_path,
        prices=_PRICES,
        global_budget=global_budget,
        agent_budgets=agent_budgets or {},
        audit=FakeAuditPort(),
    )


def test_estimate_cost_local_formula(traces_db_path: Path) -> None:
    """(1) estimate_cost = (in+out)/1000 * precio del alias (cálculo local, D-24)."""
    ct = _tracker(traces_db_path)
    try:
        # (1000 + 500) / 1000 * 2.0 = 3.0
        assert ct.estimate_cost("gemini-default", 1000, 500) == pytest.approx(3.0)
    finally:
        ct.close()


def test_estimate_cost_unknown_alias_fails_fast(traces_db_path: Path) -> None:
    """(1b) alias sin precio en config -> KeyError (fail-fast, config incompleta)."""
    ct = _tracker(traces_db_path)
    try:
        with pytest.raises(KeyError):
            ct.estimate_cost("no-existe", 100, 100)
    finally:
        ct.close()


def test_authorize_vetoes_when_global_budget_exceeded(traces_db_path: Path) -> None:
    """(2) gasto + estimado > presupuesto global -> BudgetExceeded ANTES de la llamada."""
    ct = _tracker(traces_db_path, global_budget=5.0)
    try:
        # gasto previo 4.0; estimado (1000+500)/1000*2.0 = 3.0 -> 7.0 > 5.0
        ct.record("belgrano", "deepseek-default", 2000, 2000)  # 4000/1000*1.0 = 4.0
        with pytest.raises(BudgetExceeded, match="global"):
            ct.authorize("belgrano", "gemini-default", 1000, 500)
    finally:
        ct.close()


def test_authorize_provider_never_invoked_on_exceed(traces_db_path: Path) -> None:
    """(2b) T-02-budget-bypass: si excede, authorize veta SIN tocar al provider."""
    invoked: list[str] = []

    def fake_provider_complete() -> None:
        invoked.append("called")

    ct = _tracker(traces_db_path, global_budget=1.0)
    try:
        with pytest.raises(BudgetExceeded):
            ct.authorize("belgrano", "gemini-default", 1000, 500)  # 3.0 > 1.0
            fake_provider_complete()  # nunca debe alcanzarse
    finally:
        ct.close()
    assert invoked == []  # el provider jamás se invocó al exceder


def test_authorize_per_agent_cap(traces_db_path: Path) -> None:
    """(3) límite por-agente: gasto del agente + estimado > cap -> BudgetExceeded con su nombre."""
    ct = _tracker(
        traces_db_path, global_budget=1000.0, agent_budgets={"belgrano": 5.0}
    )
    try:
        ct.record("belgrano", "deepseek-default", 2000, 2000)  # 4.0 para belgrano
        with pytest.raises(BudgetExceeded, match="belgrano"):
            ct.authorize("belgrano", "gemini-default", 1000, 500)  # 4.0 + 3.0 > 5.0
    finally:
        ct.close()


def test_authorize_without_cap_only_global(traces_db_path: Path) -> None:
    """(3b) sin cap por-agente solo aplica el global (D-18)."""
    ct = _tracker(
        traces_db_path, global_budget=1000.0, agent_budgets={"otro": 1.0}
    )
    try:
        # belgrano no tiene cap; bajo el global no debe vetar
        ct.authorize("belgrano", "gemini-default", 1000, 500)  # no raise
    finally:
        ct.close()


def test_record_uses_local_cost_not_provider(traces_db_path: Path) -> None:
    """(4) record calcula costo LOCAL (D-24); provider_reported_cost guardado, no gobierna."""
    ct = _tracker(traces_db_path, global_budget=10.0)
    try:
        # local: (1000+500)/1000*2.0 = 3.0; el provider miente diciendo 0.01
        ct.record(
            "belgrano",
            "gemini-default",
            1000,
            500,
            provider_reported_cost=0.01,
        )
        assert ct.month_spend() == pytest.approx(3.0)  # local gobierna, no el 0.01
    finally:
        ct.close()


def test_durable_state_vetoes_after_budget_drained(traces_db_path: Path) -> None:
    """(5) tras agotar presupuesto, el siguiente authorize veta (lee estado durable)."""
    ct = _tracker(traces_db_path, global_budget=3.0)
    try:
        ct.record("belgrano", "gemini-default", 1000, 500)  # 3.0 -> presupuesto al tope
        with pytest.raises(BudgetExceeded):
            ct.authorize("belgrano", "deepseek-default", 100, 100)  # 0.2 -> 3.2 > 3.0
    finally:
        ct.close()


def test_cost_tracker_standalone_fail_fast_when_journal_not_wal(
    traces_db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(7) WR-08: un CostTracker STANDALONE (sin TraceStore previo) también verifica WAL
    fail-fast — la durabilidad del spend_ledger no depende del orden de construcción."""
    import gateway.db as mod

    monkeypatch.setattr(mod, "PRAGMAS", ("PRAGMA journal_mode=DELETE",))
    with pytest.raises(TraceIntegrityError):
        _tracker(traces_db_path)


def test_inflight_reservation_blocks_concurrent_authorize(traces_db_path: Path) -> None:
    """(6) WR-06: una reserva en vuelo cuenta contra el gate global hasta release()."""
    ct = _tracker(traces_db_path, global_budget=5.0)
    try:
        ct.authorize("a", "gemini-default", 1000, 500)  # 3.0 <= 5.0: pasa
        reserved = ct.reserve("a", "gemini-default", 1000, 500)  # 3.0 en vuelo
        # Segunda llamada concurrente: 3.0 (en vuelo) + 3.0 (est) > 5.0 → veta.
        with pytest.raises(BudgetExceeded, match="global"):
            ct.authorize("b", "gemini-default", 1000, 500)
        ct.release("a", reserved)
        # Liberada la reserva (la primera llamada falló), la segunda vuelve a pasar.
        ct.authorize("b", "gemini-default", 1000, 500)
    finally:
        ct.close()


def test_inflight_reservation_counts_against_agent_cap(traces_db_path: Path) -> None:
    """(6b) WR-06: la reserva en vuelo del agente cuenta contra SU cap, no contra otros."""
    ct = _tracker(
        traces_db_path, global_budget=1000.0, agent_budgets={"belgrano": 5.0}
    )
    try:
        reserved = ct.reserve("belgrano", "gemini-default", 1000, 500)  # 3.0 en vuelo
        with pytest.raises(BudgetExceeded, match="belgrano"):
            ct.authorize("belgrano", "gemini-default", 1000, 500)  # 3.0 + 3.0 > 5.0
        ct.authorize("otro", "gemini-default", 1000, 500)  # otro agente: no afectado
        ct.release("belgrano", reserved)
        ct.authorize("belgrano", "gemini-default", 1000, 500)  # liberada: pasa
    finally:
        ct.close()


def test_month_window_excludes_previous_month(traces_db_path: Path) -> None:
    """(5b) el gasto se calcula por ventana de mes calendario sobre created_at."""
    ct = _tracker(traces_db_path, global_budget=10.0)
    try:
        last_month = (datetime.now(UTC).replace(day=1) - timedelta(days=1)).isoformat()
        ct.record(
            "belgrano",
            "gemini-default",
            1000,
            500,
            created_at=last_month,
        )
        # el gasto del mes anterior no cuenta para el mes actual
        assert ct.month_spend() == pytest.approx(0.0)
    finally:
        ct.close()
