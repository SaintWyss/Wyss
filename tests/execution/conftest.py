"""Fixtures de la suite execution (Fase 06).

`engine` replica el fixture de tests/orchestrator/conftest.py (BUILTIN_DENY + DEFAULT_BASE_LEVELS
+ AggregateThresholds()) para los tests que gatean acciones por política.

`FakeAudit` es una copia directa del homólogo en tests/orchestrator/conftest.py: mantiene la
lista de AuditEvent y el contextmanager Span, sin IO.

`RecordingEngine` envuelve un CognitivePolicyEngine real y registra los planes evaluados en
`.calls`, para que los tests de la segunda muralla (EXEC-04 / D-68) aserten que el re-evaluó.

TODO (plan 02): añadir `journal` fixture (UndoJournal SQLite) cuando la clase exista en
src/execution/journal.py. No se define aquí — UndoJournal no existe hasta el plan 06-02.
"""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime

import pytest

from core.domain import AuditEvent, Span
from core.domain.plan import Plan
from core.domain.policy import AggregateThresholds, PolicyRules
from core.domain.risk import RiskLevel
from core.policy import BUILTIN_DENY, CognitivePolicyEngine

DEFAULT_BASE_LEVELS: dict[str, RiskLevel] = {
    "file.read": RiskLevel.A,
    "file.list": RiskLevel.A,
    "file.move": RiskLevel.B,
    "file.rename": RiskLevel.B,
    "file.create": RiskLevel.C,
    "file.write": RiskLevel.C,
    "file.delete": RiskLevel.C,
    "shell.run": RiskLevel.C,
    "git.push": RiskLevel.C,
}


@pytest.fixture
def engine() -> CognitivePolicyEngine:
    return CognitivePolicyEngine(
        PolicyRules(
            deny=BUILTIN_DENY,
            base_levels=DEFAULT_BASE_LEVELS,
            thresholds=AggregateThresholds(),
        )
    )


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def log(self, event: AuditEvent) -> None:
        self.events.append(event)

    def span(
        self, task_id: str, actor: str, event: str
    ) -> AbstractContextManager[Span]:
        return self._span_impl(task_id, actor, event)

    @contextmanager
    def _span_impl(self, task_id: str, actor: str, event: str) -> Iterator[Span]:
        yield Span(
            task_id=task_id,
            actor=actor,
            event=event,
            started_at=datetime.now(UTC),
        )


class RecordingEngine:
    """Envuelve CognitivePolicyEngine y registra cada Plan evaluado en `.calls`.

    Permite que los tests de la segunda muralla (EXEC-04 / D-68) aserten que el
    engine se re-corrió con la Action resuelta (paths reales), no con la original.
    """

    def __init__(self, inner: CognitivePolicyEngine) -> None:
        self._inner = inner
        self.calls: list[Plan] = []

    def evaluate(self, plan: Plan) -> object:
        self.calls.append(plan)
        return self._inner.evaluate(plan)
