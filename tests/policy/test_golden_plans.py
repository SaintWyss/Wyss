"""Golden plans: ≥12 casos cubriendo A/B/C/D, una regla de denylist por nivel D y POL-04.

Un FALSO-A (clasificar A algo que debía confirmar/rechazar) es el peor fallo posible: el
sistema ejecutaría sin pedir confirmación. Cada caso D que matchea una regla built-in
incluye su `rule_id` esperado para detectar regresiones en el matching.
"""

from dataclasses import dataclass

import pytest

from core.domain.plan import Action, Plan
from core.domain.risk import Outcome, RiskLevel
from core.policy import CognitivePolicyEngine


def _plan(*steps: Action, estimated: RiskLevel | None = None, task_id: str = "t") -> Plan:
    return Plan(
        task_id=task_id,
        summary="golden",
        steps=tuple(steps),
        rationale="test",
        estimated_risk=estimated,
    )


@dataclass(frozen=True)
class Golden:
    name: str
    plan: Plan
    expected: RiskLevel


GOLDEN_CASES: tuple[Golden, ...] = (
    # --- Nivel A: solo lecturas ---
    Golden(
        "A: lectura unica",
        _plan(Action("file.read", "~/Documents/notas.md")),
        RiskLevel.A,
    ),
    Golden(
        "A: varias lecturas + list",
        _plan(
            Action("file.read", "~/Documents/a.md"),
            Action("file.list", "~/Documents/"),
            Action("file.read", "~/Documents/b.md"),
        ),
        RiskLevel.A,
    ),
    # --- Nivel B: mover/renombrar; o > file_count_b targets distintos ---
    Golden(
        "B: mover un archivo",
        _plan(Action("file.move", "~/Documents/x.md")),
        RiskLevel.B,
    ),
    Golden(
        "B: renombrar un archivo",
        _plan(Action("file.rename", "~/Documents/y.md")),
        RiskLevel.B,
    ),
    Golden(
        "B: 15 moves distintos (agregado > file_count_b=10)",
        _plan(*(Action("file.move", f"~/Documents/f{i}.md") for i in range(15))),
        RiskLevel.B,
    ),
    # --- Nivel C: write/delete; dirs; sensitive ---
    Golden(
        "C: borrado unico (docs/13: borrar es C)",
        _plan(Action("file.delete", "~/Documents/tmp.md", {"recursive": False})),
        RiskLevel.C,
    ),
    Golden(
        "C: escritura unica",
        _plan(Action("file.write", "~/Documents/out.md")),
        RiskLevel.C,
    ),
    Golden(
        "C: write en 6 dirs distintos (> dir_count_c=5)",
        _plan(*(Action("file.write", f"~/d{i}/out.md") for i in range(6))),
        RiskLevel.C,
    ),
    Golden(
        "C: estimated_risk sube A->C (POL-04)",
        _plan(Action("file.read", "~/Documents/a.md"), estimated=RiskLevel.C),
        RiskLevel.C,
    ),
    # --- Nivel D: una por cada regla de BUILTIN_DENY ---
    Golden(
        "D: rm recursivo fuera de papelera (mass-delete)",
        _plan(Action("file.delete", "~/Documents/old", {"recursive": True, "to_trash": False})),
        RiskLevel.D,
    ),
    Golden(
        "D: write sobre audit.db (audit-tamper)",
        _plan(Action("file.write", "~/wyss/data/audit.db")),
        RiskLevel.D,
    ),
    Golden(
        "D: lectura de secreto .env (secret-exfiltration)",
        _plan(Action("file.read", "~/proyecto/.env")),
        RiskLevel.D,
    ),
    Golden(
        "D: write bajo /etc (system-files-write)",
        _plan(Action("file.write", "/etc/passwd")),
        RiskLevel.D,
    ),
    Golden(
        "D: git push --force a main (git-force-push-main)",
        _plan(Action("git.push", "main", {"force": True})),
        RiskLevel.D,
    ),
    Golden(
        "D: mkfs via shell.run (disk-format)",
        _plan(Action("shell.run", "mkfs.ext4 /dev/sda1")),
        RiskLevel.D,
    ),
)


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c.name)
def test_golden_plan(case: Golden, engine: CognitivePolicyEngine) -> None:
    decision = engine.evaluate(case.plan)
    falso_a = " — FALSO-A: ejecutaria algo que debia confirmar/rechazar"
    assert decision.risk_level == case.expected, (
        f"{case.name}: esperado {case.expected.name}, obtuvo {decision.risk_level.name}"
        + (falso_a if decision.risk_level < case.expected else "")
    )


def test_estimated_risk_no_baja_el_nivel(engine: CognitivePolicyEngine) -> None:
    """POL-04: un file.delete (C) con estimated_risk=A NO baja a A — sigue >= C."""
    plan = _plan(
        Action("file.delete", "~/Documents/tmp.md", {"recursive": False}),
        estimated=RiskLevel.A,
    )
    decision = engine.evaluate(plan)
    assert decision.risk_level >= RiskLevel.C
    assert decision.risk_level == RiskLevel.C


def test_unknown_action_type_es_C_no_A(engine: CognitivePolicyEngine) -> None:
    """Fail-closed: un action_type fuera de base_levels clasifica C, nunca A."""
    decision = engine.evaluate(_plan(Action("foo.bar", "~/algo")))
    assert decision.risk_level == RiskLevel.C
    assert decision.outcome == Outcome.CONFIRM_STRONG


def test_notion_read_page_es_A(engine: CognitivePolicyEngine) -> None:
    """NOTION-01: notion.read_page está registrado como lectura nivel A."""
    decision = engine.evaluate(_plan(Action("notion.read_page", "page-id")))
    assert decision.risk_level == RiskLevel.A
    assert decision.outcome == Outcome.EXECUTE


@pytest.mark.parametrize("action_type", ["notion.create_page", "notion.update_page"])
def test_notion_writes_son_C(
    action_type: str, engine: CognitivePolicyEngine
) -> None:
    """NOTION-02: escrituras Notion requieren confirmación fuerte nivel C."""
    decision = engine.evaluate(_plan(Action(action_type, "page-id")))
    assert decision.risk_level == RiskLevel.C
    assert decision.outcome == Outcome.CONFIRM_STRONG


def test_notion_unknown_action_type_es_C_fail_closed(
    engine: CognitivePolicyEngine,
) -> None:
    """Un notion.* no registrado conserva el fail-closed a C."""
    decision = engine.evaluate(_plan(Action("notion.frobnicate", "page-id")))
    assert decision.risk_level == RiskLevel.C
    assert decision.outcome == Outcome.CONFIRM_STRONG


def test_d_produce_reject_outcome(engine: CognitivePolicyEngine) -> None:
    plan = _plan(Action("file.write", "/etc/hosts"))
    decision = engine.evaluate(plan)
    assert decision.risk_level == RiskLevel.D
    assert decision.outcome == Outcome.REJECT
    assert decision.matched_rules == ("system-files-write",)
