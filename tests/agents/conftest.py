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
from pathlib import Path

import pytest

from agents.ledger_retrieval import LedgerRetrieval
from core.domain import AgentDefinition, AuditEvent, Span
from core.domain.plan import Plan
from core.domain.policy import AggregateThresholds, PolicyRules
from core.domain.risk import RiskLevel
from core.policy import BUILTIN_DENY, CognitivePolicyEngine
from ledger.sqlite_store import SqliteLedgerStore
from tests.ledger.conftest import DESDE, HASTA, TxSpec, build_transaccion
from tests.ports.fakes import FakePermissionStore, FakeRetrieval

DEFAULT_BASE_LEVELS: dict[str, RiskLevel] = {
    "file.read": RiskLevel.A,
    "file.list": RiskLevel.A,
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


@pytest.fixture
def pellegrini_definition() -> AgentDefinition:
    """Definición declarativa de Pellegrini (config-only, AGENT-09 / D-73)."""
    return AgentDefinition(
        agent_id="pellegrini",
        name="Pellegrini",
        domain="finanzas",
        kb_ids=frozenset(),
        model_alias="economico",
        budget_usd=5.0,
    )


# Espejo del SET RICO de tests/ledger/conftest.py — sembrado del ledger para LedgerRetrieval.
# (transacciones_ricas es un fixture; acá replicamos su contenido para sembrar el store sin
# depender de la inyección cruzada de fixtures entre suites.)
_TRANSACCIONES_RICAS: list[TxSpec] = [
    ("INGRESO", 3000.00, "2026-05-01", "sueldo", None),
    ("INGRESO", 500.00, "2026-05-10", "freelance", None),
    ("GASTO", 800.00, "2026-05-02", None, "supermercado"),
    ("GASTO", 200.00, "2026-05-15", None, "supermercado"),
    ("GASTO", 450.00, "2026-05-05", None, "delivery"),
    ("GASTO", 150.00, "2026-05-20", None, "delivery"),
    ("GASTO", 600.00, "2026-05-03", None, "alquiler"),
    ("GASTO", 100.00, "2026-05-08", None, "transporte"),
    ("GASTO", 999.00, "2026-04-28", None, "delivery"),  # fuera de ventana
    ("INGRESO", 999.00, "2026-06-01", "sueldo", None),  # fuera de ventana
]


@pytest.fixture
def ledger_retrieval(tmp_path: Path) -> Iterator[LedgerRetrieval]:
    """`LedgerRetrieval` sobre un `SqliteLedgerStore` tmp sembrado con el SET RICO (mayo 2026).

    La ventana se fija a `DESDE..HASTA` (2026-05) para que los hechos coincidan con el ground
    truth de tests/ledger/conftest.py (HECHOS_VERIFICADOS) — sin fuga de período.
    """
    store = SqliteLedgerStore(tmp_path / "ledger.db")
    try:
        for spec in _TRANSACCIONES_RICAS:
            store.record(build_transaccion(spec))
        yield LedgerRetrieval(store, desde=DESDE, hasta=HASTA)
    finally:
        store.close()
