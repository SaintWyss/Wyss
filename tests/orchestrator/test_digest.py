"""Tests del composer puro del Daily Assistant."""

import ast
from collections.abc import Mapping
from datetime import date
from pathlib import Path

from core.domain.ledger import Transaccion
from core.domain.memory import MemoryFact
from orchestrator.digest import compose_digest, write_digest_file
from orchestrator.pending_store import PendingProposal
from orchestrator.routine_store import Routine


class FakeLedger:
    def __init__(
        self,
        *,
        ingresos: float = 0.0,
        gastos: float = 0.0,
        surplus: float = 0.0,
        categories: Mapping[str, float] | None = None,
        coverage_days: int = 0,
    ) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self._ingresos = ingresos
        self._gastos = gastos
        self._surplus = surplus
        self._categories = categories or {}
        self._coverage_days = coverage_days

    def record(self, transaccion: Transaccion) -> None:
        del transaccion

    def balance(self, desde: str, hasta: str) -> tuple[float, float]:
        self.calls.append(("balance", desde, hasta))
        return self._ingresos, self._gastos

    def surplus(self, desde: str, hasta: str) -> float:
        self.calls.append(("surplus", desde, hasta))
        return self._surplus

    def query_by_category(self, desde: str, hasta: str) -> Mapping[str, float]:
        self.calls.append(("query_by_category", desde, hasta))
        return self._categories

    def coverage_days(self, desde: str, hasta: str) -> int:
        self.calls.append(("coverage_days", desde, hasta))
        return self._coverage_days


def test_pending_section_lists_count_and_fields() -> None:
    markdown = compose_digest(
        today=date(2026, 7, 11),
        pending=[
            _pending("b", "task-b", "C", "CONFIRM", "2026-07-11T09:00:00+00:00"),
            _pending("a", "task-a", "B", "REVIEW", "2026-07-11T08:00:00+00:00"),
        ],
        ledger=FakeLedger(),
        window=("2026-07-01", "2026-07-11"),
        routines=[],
    )

    assert "## Pendientes de bandeja\nTotal: 2" in markdown
    assert "task-a | riesgo=B | outcome=REVIEW | creado=2026-07-11T08:00:00+00:00" in markdown
    assert "task-b | riesgo=C | outcome=CONFIRM | creado=2026-07-11T09:00:00+00:00" in markdown
    assert markdown.index("task-a") < markdown.index("task-b")


def test_empty_states_are_explicit() -> None:
    markdown = compose_digest(
        today=date(2026, 7, 11),
        pending=[],
        ledger=FakeLedger(),
        window=("2026-07-01", "2026-07-11"),
        routines=[],
    )

    assert "Sin pendientes" in markdown
    assert "Sin movimientos en la ventana" in markdown
    assert "Sin rutinas" in markdown
    assert "## Pendientes de bandeja" in markdown
    assert "## Finanzas Pellegrini" in markdown
    assert "## Rutinas" in markdown


def test_finance_section_uses_ledger_window() -> None:
    ledger = FakeLedger(
        ingresos=1000.0,
        gastos=325.5,
        surplus=674.5,
        categories={"super": 200.0, "sube": 125.5},
        coverage_days=4,
    )

    markdown = compose_digest(
        today=date(2026, 7, 11),
        pending=[],
        ledger=ledger,
        window=("2026-07-01", "2026-07-11"),
        routines=[],
    )

    assert "Ventana: 2026-07-01 -> 2026-07-11" in markdown
    assert "Ingresos: $1000.00" in markdown
    assert "Gastos: $325.50" in markdown
    assert "Surplus: $674.50" in markdown
    assert "Coverage days: 4" in markdown
    assert "- super: $200.00" in markdown
    assert ledger.calls == [
        ("balance", "2026-07-01", "2026-07-11"),
        ("surplus", "2026-07-01", "2026-07-11"),
        ("query_by_category", "2026-07-01", "2026-07-11"),
        ("coverage_days", "2026-07-01", "2026-07-11"),
    ]


def test_failed_routines_are_separated_and_sorted() -> None:
    markdown = compose_digest(
        today=date(2026, 7, 11),
        pending=[],
        ledger=FakeLedger(),
        window=("2026-07-01", "2026-07-11"),
        routines=[
            _routine("z", "sin corrida", None, None),
            _routine("b", "ok vieja", "2026-07-10T08:00:00+00:00", "executed"),
            _routine("a", "fallo nueva", "2026-07-11T08:00:00+00:00", "failed"),
            _routine("c", "ok nueva", "2026-07-11T07:00:00+00:00", "queued"),
        ],
    )

    failures = markdown.split("### Rutinas: fallas", 1)[1].split(
        "### Rutinas: ultimas corridas", 1
    )[0]
    latest = markdown.split("### Rutinas: ultimas corridas", 1)[1]
    assert "fallo nueva" in failures
    assert "ok nueva" not in failures
    assert latest.index("ok nueva") < latest.index("ok vieja") < latest.index("sin corrida")


def test_digest_module_has_no_execution_imports() -> None:
    tree = ast.parse(Path("src/orchestrator/digest.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    constructed: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
            imported.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            constructed.add(node.func.id)

    forbidden_imports = {"orchestrator.dispatcher", "PlanExecutor", "PlanRunner"}
    assert imported.isdisjoint(forbidden_imports)
    assert {"Plan", "Action"}.isdisjoint(constructed)


def test_compose_digest_is_deterministic_and_renders_memory_as_data() -> None:
    ledger = FakeLedger(ingresos=10.0, surplus=10.0, coverage_days=1)
    pending = [_pending("p", "task\n*bold*", "A", "EXECUTE", "2026")]
    routines = [_routine("r", "rutina\n#1", None, "unknown")]
    memory = [
        MemoryFact(
            id="m1",
            category="owner",
            value="prefiere\nmate",
            tier="owner",
            source="owner",
            created_at="2026",
            updated_at="2026",
        )
    ]

    first = compose_digest(
        today=date(2026, 7, 11),
        pending=pending,
        ledger=ledger,
        window=("2026-07-01", "2026-07-11"),
        routines=routines,
        memory=memory,
    )
    second = compose_digest(
        today=date(2026, 7, 11),
        pending=pending,
        ledger=ledger,
        window=("2026-07-01", "2026-07-11"),
        routines=routines,
        memory=memory,
    )

    assert first == second
    assert "task \\*bold\\*" in first
    assert "prefiere mate" in first


def test_write_digest_file_creates_and_overwrites(tmp_path: Path) -> None:
    output = write_digest_file(tmp_path / "digests", date(2026, 7, 11), "uno")
    assert output == tmp_path / "digests" / "2026-07-11.md"
    assert output.read_text(encoding="utf-8") == "uno"

    same_output = write_digest_file(tmp_path / "digests", date(2026, 7, 11), "dos")

    assert same_output == output
    assert output.read_text(encoding="utf-8") == "dos"


def _pending(
    pending_id: str,
    task_id: str,
    risk_level: str,
    outcome: str,
    created_at: str,
) -> PendingProposal:
    return PendingProposal(
        id=pending_id,
        task_id=task_id,
        plan_json="{}",
        risk_level=risk_level,
        outcome=outcome,
        status="pending",
        created_at=created_at,
        expires_at="2026-07-12T00:00:00+00:00",
        resolved_at=None,
        resolved_by=None,
        revision=1,
    )


def _routine(
    routine_id: str,
    name: str,
    last_fired_at: str | None,
    last_outcome: str | None,
) -> Routine:
    return Routine(
        id=routine_id,
        name=name,
        schedule_kind="cron",
        schedule_expr="0 8 * * *",
        plan_json="{}",
        catch_up=True,
        status="active",
        created_at="2026-07-01T00:00:00+00:00",
        last_fired_at=last_fired_at,
        last_outcome=last_outcome,
    )
