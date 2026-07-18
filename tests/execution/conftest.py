"""Fixtures de la suite execution (Fase 06).

`engine` replica el fixture de tests/orchestrator/conftest.py (BUILTIN_DENY + DEFAULT_BASE_LEVELS
+ AggregateThresholds()) para los tests que gatean acciones por política.

`FakeAudit` es una copia directa del homólogo en tests/orchestrator/conftest.py: mantiene la
lista de AuditEvent y el contextmanager Span, sin IO.

`RecordingEngine` envuelve un CognitivePolicyEngine real y registra los planes evaluados en
`.calls`, para que los tests de la segunda muralla (EXEC-04 / D-68) aserten que el re-evaluó.

`journal` fixture añadida en plan 06-02: yields UndoJournal(tmp_path / "journal.db"),
cierra en finally (espejo de tests/orchestrator/conftest.py fixture pending_store).
"""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.domain import Action, AuditEvent, ExecutionAuthorization, RiskLevel, Span
from core.domain.plan import Plan
from core.domain.policy import AggregateThresholds, PolicyDecision, PolicyRules
from core.policy import BUILTIN_DENY, CognitivePolicyEngine
from core.ports.execution import ExecutionGuardPort, PolicyEvaluatorPort
from execution.journal import UndoJournal

DEFAULT_BASE_LEVELS: dict[str, RiskLevel] = {
    "file.read": RiskLevel.A,
    "file.list": RiskLevel.A,
    "file.stat": RiskLevel.A,
    "git.status": RiskLevel.A,
    "git.log": RiskLevel.A,
    "git.diff": RiskLevel.A,
    "notion.read_page": RiskLevel.A,
    "notion.query_database": RiskLevel.A,
    "file.move": RiskLevel.B,
    "file.rename": RiskLevel.B,
    "memory.remember": RiskLevel.B,
    "file.create": RiskLevel.C,
    "file.write": RiskLevel.C,
    "file.delete": RiskLevel.C,
    "shell.run": RiskLevel.C,
    "notion.create_page": RiskLevel.C,
    "notion.update_page": RiskLevel.C,
    "git.push": RiskLevel.C,
}


def make_engine() -> CognitivePolicyEngine:
    """Motor real con la política canónica usada por la suite de ejecución."""
    return CognitivePolicyEngine(
        PolicyRules(
            deny=BUILTIN_DENY,
            base_levels=DEFAULT_BASE_LEVELS,
            thresholds=AggregateThresholds(),
        )
    )


@pytest.fixture
def engine() -> CognitivePolicyEngine:
    return make_engine()


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def log(self, event: AuditEvent) -> None:
        self.events.append(event)

    def span(self, task_id: str, actor: str, event: str) -> AbstractContextManager[Span]:
        return self._span_impl(task_id, actor, event)

    @contextmanager
    def _span_impl(self, task_id: str, actor: str, event: str) -> Iterator[Span]:
        yield Span(
            task_id=task_id,
            actor=actor,
            event=event,
            started_at=datetime.now(UTC),
        )


class RecordingGuard:
    """Guard fake que registra el DTO efectivo entregado por cada adapter."""

    def __init__(self) -> None:
        self.actions: list[Action] = []

    def authorize(
        self,
        action: Action,
        *,
        adapter: str,
        max_risk: RiskLevel,
    ) -> ExecutionAuthorization:
        del adapter, max_risk
        self.actions.append(action)
        return ExecutionAuthorization(True, RiskLevel.C, "")


def make_guard(engine: PolicyEvaluatorPort, audit: FakeAudit) -> ExecutionGuardPort:
    """Construye la segunda muralla real para tests de adapters."""
    from execution.guard import DeterministicExecutionGuard

    return DeterministicExecutionGuard(engine, audit)


class RecordingEngine:
    """Envuelve CognitivePolicyEngine y registra cada Plan evaluado en `.calls`.

    Permite que los tests de la segunda muralla (EXEC-04 / D-68) aserten que el
    engine se re-corrió con la Action resuelta (paths reales), no con la original.
    """

    def __init__(self, inner: CognitivePolicyEngine) -> None:
        self._inner = inner
        self.calls: list[Plan] = []

    def evaluate(self, plan: Plan) -> PolicyDecision:
        self.calls.append(plan)
        return self._inner.evaluate(plan)


@pytest.fixture
def journal(tmp_path: Path) -> Iterator[UndoJournal]:
    """UndoJournal respaldado en tmp_path/journal.db; cierra en finally.

    Espejo del fixture `pending_store` en tests/orchestrator/conftest.py.
    Plan 06-02 (UndoJournal, D-65).
    """
    j = UndoJournal(tmp_path / "journal.db")
    try:
        yield j
    finally:
        j.close()
