"""RED/E2E — las 3 tareas de aceptación de Pellegrini (AGENT-09, D-87, AI-SPEC D3).

D-87 / AGENT-09: Pellegrini completa ≥3 tareas reales E2E reportando al orquestador:
  1. "¿dónde se me va la plata?"   → gastos por categoría
  2. "armá mi presupuesto mensual" → propuesta desde ingresos vs gastos históricos
  3. "¿cuánto puedo ahorrar?"      → superávit/déficit + sugerencia

Camino determinístico (D-86, Hermes real diferido por 05-05): hechos del ledger computados →
agente reporta vía `orchestrator.dispatcher.dispatch(...)` → resultado al `FakeOrchestrator`
→ `FakeAudit` registró la acción. La calidad advisory (D3) es un check opcional `@llm_judge`
(opt-in, fuera del run por defecto — consume budget del agente económico).

Estos tests FALLAN hasta que Plan 03 implemente `agents.pellegrini` (advise/handle_task) y
Plan 02 el ledger. Imports diferidos dentro de helpers: el fallo es `ModuleNotFoundError`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.domain import Outcome, PolicyDecision, RiskLevel
from core.domain.plan import Plan
from tests.agents.conftest import FakeAudit
from tests.ledger.conftest import HECHOS_VERIFICADOS

# Las 3 tareas de aceptación D-87 (instrucciones del owner).
TAREAS_D87 = (
    "¿dónde se me va la plata?",
    "armá mi presupuesto mensual",
    "¿cuánto puedo ahorrar?",
)


async def _handle_task(instruccion: str, hechos: object) -> Plan:
    """Pellegrini procesa una instrucción y produce un Plan de reporte (import diferido: RED)."""
    import agents.pellegrini as pellegrini  # type: ignore[import-untyped,import-not-found,unused-ignore]

    plan: Plan = await pellegrini.handle_task(instruccion=instruccion, hechos=hechos)
    return plan


@pytest.mark.parametrize("instruccion", TAREAS_D87)
async def test_d87_task_reports_via_dispatcher(
    instruccion: str, fake_audit: FakeAudit, tmp_path: Path
) -> None:
    """Camino determinístico: hechos → plan de reporte → dispatch → audit registró la acción.

    Cada tarea produce un Plan de SOLO LECTURA (finance.query → nivel A → EXECUTE) que el
    dispatcher encola y audita; el `FakeOrchestrator` recibe el reporte. Sin escritura ni IA.
    """
    from orchestrator.dispatcher import dispatch
    from orchestrator.pending_store import PendingStore

    plan = await _handle_task(instruccion, HECHOS_VERIFICADOS)
    # las tareas D-87 son consultivas: solo lectura (finance.query), nivel A → EXECUTE
    decision = PolicyDecision(
        task_id=plan.task_id,
        risk_level=RiskLevel.A,
        outcome=Outcome.EXECUTE,
    )
    store = PendingStore(tmp_path / "pending.db")
    try:
        resultado = await dispatch(
            plan, decision, pending_store=store, audit=fake_audit
        )
    finally:
        store.close()

    assert resultado["outcome"] == "queued"
    # FakeAudit (del fixture) registró el POLICY_DECISION de la acción reportada
    assert fake_audit.events, "el dispatcher debe auditar la decisión de política"


async def test_donde_se_va_la_plata_uses_category_breakdown() -> None:
    """Tarea 1 (D-87): el plan de "¿dónde se me va la plata?" referencia gastos por categoría."""
    plan = await _handle_task(TAREAS_D87[0], HECHOS_VERIFICADOS)
    # el plan consulta el ledger por categoría (finance.query), no escribe
    assert any(step.type == "finance.query" for step in plan.steps)
    assert all(not step.type.startswith("finance.record") for step in plan.steps)


async def test_presupuesto_no_excede_ingresos() -> None:
    """Tarea 2 (D-87/D3): el presupuesto propuesto ≤ ingresos reales (sensatez)."""
    plan = await _handle_task(TAREAS_D87[1], HECHOS_VERIFICADOS)
    # el resumen del plan debe declarar un presupuesto que no exceda los ingresos del ledger
    import agents.pellegrini as pellegrini  # type: ignore[import-untyped,import-not-found,unused-ignore]

    presupuesto: float = pellegrini.propuesta_presupuesto(HECHOS_VERIFICADOS)
    assert presupuesto <= HECHOS_VERIFICADOS["ingresos_total"]
    assert plan.steps  # el plan no está vacío


@pytest.mark.llm_judge
async def test_advisory_quality_llm_judge() -> None:
    """D3 (opt-in): calidad/accionabilidad del consejo evaluada por LLM-judge.

    Corre SOLO con `pytest -m llm_judge` (consume budget del agente económico). No entra al
    run de CI por defecto. La rúbrica (AI-SPEC D3): consejo concreto, presupuesto ≤ ingresos,
    declara cobertura escasa. El owner es el calibrador final.
    """
    import agents.pellegrini as pellegrini  # type: ignore[import-untyped,import-not-found,unused-ignore]

    veredicto = await pellegrini.judge_advisory_quality(TAREAS_D87, HECHOS_VERIFICADOS)
    assert veredicto.passed, veredicto.reason
