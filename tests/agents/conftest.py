"""Fixtures compartidos de la suite agents (Fase 07).

Sigue el mismo molde que tests/execution/conftest.py y tests/orchestrator/conftest.py:
- engine: CognitivePolicyEngine con BUILTIN_DENY + DEFAULT_BASE_LEVELS + AggregateThresholds
- FakeAudit: copia directa del homólogo en execution/conftest
- RecordingEngine: envuelve engine real, registra planes en .calls
- fake_retrieval / fake_permission_store: importados de tests.ports.fakes
- FakePlanRunner: registra el plan y devuelve objeto con .success=True
- sample_definition: AgentDefinition de prueba estable
"""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime

import pytest

from core.domain import AgentDefinition, AuditEvent, Span
from core.domain.plan import Plan
from core.domain.policy import AggregateThresholds, PolicyRules
from core.domain.risk import RiskLevel
from core.policy import BUILTIN_DENY, CognitivePolicyEngine
from tests.ports.fakes import FakePermissionStore, FakeRetrieval

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
    """Acumula AuditEvents en memoria y provee contextmanager Span sin IO."""

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

    Permite que test_golden_injection.py aserte que engine.evaluate fue invocado
    con el plan generado tras procesar el documento con instrucciones inyectadas.
    """

    def __init__(self, inner: CognitivePolicyEngine) -> None:
        self._inner = inner
        self.calls: list[Plan] = []

    def evaluate(self, plan: Plan) -> object:
        self.calls.append(plan)
        return self._inner.evaluate(plan)


class FakePlanRunner:
    """Registra el plan recibido y retorna un resultado stub con success=True.

    Simula PlanExecutor.run sin levantar el stack completo de execution/.
    ConfiguredAgent inspecciona .success y .detail vía duck typing.
    """

    def __init__(self) -> None:
        self.last_plan: Plan | None = None

    async def run(self, plan: Plan) -> object:
        self.last_plan = plan

        class _Result:
            success = True
            detail = "FakePlanRunner: ejecución simulada"
            applied_entries: tuple[str, ...] = ()
            failed_step: int | None = None

        return _Result()


@pytest.fixture
def fake_audit() -> FakeAudit:
    return FakeAudit()


@pytest.fixture
def fake_retrieval() -> FakeRetrieval:
    return FakeRetrieval()


@pytest.fixture
def fake_permission_store() -> FakePermissionStore:
    return FakePermissionStore()


@pytest.fixture
def fake_plan_runner() -> FakePlanRunner:
    return FakePlanRunner()


@pytest.fixture
def sample_definition() -> AgentDefinition:
    return AgentDefinition(
        agent_id="test-agent",
        name="Test Agent",
        domain="test",
        kb_ids=frozenset({"kb-1"}),
        model_alias="economico",
        budget_usd=1.0,
    )
