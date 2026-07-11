"""Fixtures de la suite orchestrator (Fase 05).

`engine` replica el fixture de tests/policy/conftest.py (BUILTIN_DENY + DEFAULT_BASE_LEVELS
+ AggregateThresholds()) para los tests que gatean acciones por política. Los fixtures
`fake_orchestrator` implementa OrchestratorPort sin Hermes real para 05-04.
"""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.domain import AuditEvent, Span
from core.domain.plan import Action, Plan
from core.domain.policy import AggregateThresholds, PolicyRules
from core.domain.risk import RiskLevel
from core.orchestrator.intent import IntentCategory, IntentClassification
from core.policy import BUILTIN_DENY, CognitivePolicyEngine
from orchestrator.pending_store import PendingStore

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


class FakeOrchestrator:
    async def classify_intent(self, instruction: str) -> IntentClassification:
        if "ambiguo" in instruction:
            return IntentClassification(IntentCategory.AMBIGUOUS_REQUEST, 0.4, True)
        return IntentClassification(IntentCategory.FILE_OPERATION, 0.95, False)

    async def draft_plan(self, instruction: str, intent: IntentClassification) -> Plan:
        del intent
        if "mover" in instruction:
            action = Action("file.move", "/tmp/source.txt")
        elif "borrar" in instruction:
            action = Action("file.delete", "/tmp/source.txt")
        elif "formatear" in instruction:
            action = Action("shell.run", "mkfs /dev/sda1")
        else:
            action = Action("file.read", "/tmp/source.txt")
        return Plan(
            task_id="fake-task",
            summary=instruction,
            steps=(action,),
            rationale="fake",
        )

    async def health_check(self) -> bool:
        return True


@pytest.fixture
def fake_orchestrator() -> FakeOrchestrator:
    return FakeOrchestrator()


@pytest.fixture
def fake_audit() -> FakeAudit:
    return FakeAudit()


@pytest.fixture
def pending_store(tmp_path: Path) -> Iterator[PendingStore]:
    store = PendingStore(tmp_path / "pending.db")
    try:
        yield store
    finally:
        store.close()
