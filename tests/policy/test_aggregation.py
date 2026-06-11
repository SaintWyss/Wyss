"""Anti-bypass por composición (POL-05) + denylist-sin-config (Pitfall 3 de RESEARCH).

El test estrella: 200 `file.delete` individuales (cada uno C por sí solo) agregan a D por
el umbral `delete_count_d`. Sin esta evaluación a nivel-plan, un planner podría descomponer
un borrado masivo en pasos C y saltear el rechazo absoluto.
"""

from core.domain.plan import Action, Plan
from core.domain.risk import Outcome, RiskLevel
from core.policy import CognitivePolicyEngine


def _delete_plan(n: int) -> Plan:
    return Plan(
        task_id="mass",
        summary=f"{n} deletes",
        steps=tuple(
            Action("file.delete", f"~/Documents/old/file_{i:04d}.txt", {"recursive": False})
            for i in range(n)
        ),
        rationale="bypass attempt",
    )


def test_composition_bypass_200_deletes_es_D(engine: CognitivePolicyEngine) -> None:
    """200 borrados individuales (cada uno C) → D por agregado (delete_count_d=50)."""
    decision = engine.evaluate(_delete_plan(200))
    assert decision.risk_level == RiskLevel.D
    assert decision.outcome == Outcome.REJECT
    assert "mass-delete" in decision.matched_rules


def test_60_writes_distintos_es_al_menos_C(engine: CognitivePolicyEngine) -> None:
    plan = Plan(
        task_id="w",
        summary="60 writes",
        steps=tuple(Action("file.write", f"~/Documents/out_{i:03d}.md") for i in range(60)),
        rationale="bulk write",
    )
    decision = engine.evaluate(plan)
    assert decision.risk_level >= RiskLevel.C


def test_6_dirs_distintos_es_al_menos_C(engine: CognitivePolicyEngine) -> None:
    plan = Plan(
        task_id="dirs",
        summary="6 dirs",
        steps=tuple(Action("file.write", f"~/dir{i}/out.md") for i in range(6)),
        rationale="spread write",
    )
    decision = engine.evaluate(plan)
    assert decision.risk_level >= RiskLevel.C


def test_empty_config_still_denies_D(engine_sin_config: CognitivePolicyEngine) -> None:
    """Pitfall 3: con base_levels vacío la denylist built-in sigue clasificando D."""
    plan = Plan(
        task_id="secret",
        summary="leer secreto sin config",
        steps=(Action("file.read", "~/proyecto/.env"),),
        rationale="exfil",
    )
    decision = engine_sin_config.evaluate(plan)
    assert decision.risk_level == RiskLevel.D
    assert decision.outcome == Outcome.REJECT
    assert "secret-exfiltration" in decision.matched_rules


def test_empty_config_mass_delete_aggregate_still_D(
    engine_sin_config: CognitivePolicyEngine,
) -> None:
    """Aun sin config, el agregado de 200 deletes es D (built-in, no vaciable)."""
    decision = engine_sin_config.evaluate(_delete_plan(200))
    assert decision.risk_level == RiskLevel.D
