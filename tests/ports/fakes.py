"""Fakes mínimos — un implementador por cada port (primer cliente real de los contratos).

Cada fake respeta la firma EXACTA (sync/async, @property donde corresponde): son la
verificación de conformidad de Pattern 5 y detectan el Pitfall 4 ya en esta fase.
"""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from core.domain import (
    Action,
    AgentDefinition,
    AgentModelRequest,
    AuditEvent,
    Chunk,
    ExtractedContent,
    Hit,
    IndexEntry,
    ModelRequest,
    ModelResponse,
    Permission,
    Plan,
    PolicyRules,
    Query,
    Report,
    RiskLevel,
    SourceFile,
    Span,
    Subject,
    Task,
    TaskStatus,
    ToolResult,
    Vector,
    Verification,
    WyssSettings,
)
from core.ports.agent import AgentBase


class FakeAuditPort:
    """Acumula eventos en memoria; permite inspeccionar el rastro de auditoría en tests."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def log(self, event: AuditEvent) -> None:
        self.events.append(event)

    @contextmanager
    def _span(self, task_id: str, actor: str, event: str) -> Iterator[Span]:
        span = Span(
            task_id=task_id,
            actor=actor,
            event=event,
            started_at=datetime.now(UTC),
        )
        yield span

    def span(self, task_id: str, actor: str, event: str) -> AbstractContextManager[Span]:
        return self._span(task_id, actor, event)


class FakeConfigStore:
    def __init__(self, settings: WyssSettings | None = None) -> None:
        self._settings = settings or WyssSettings(
            data_dir=Path("/tmp/wyss"),
            audit_db=Path("/tmp/wyss/audit.db"),
            policy=PolicyRules(deny=(), base_levels={}),
        )

    def load(self) -> WyssSettings:
        return self._settings


class FakeExtractor:
    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"text/plain"})

    def extract(self, source: SourceFile) -> ExtractedContent:
        return ExtractedContent(source=source, text="", metadata={})


class FakeChunker:
    def chunk(self, content: ExtractedContent) -> Sequence[Chunk]:
        return [
            Chunk(chunk_id="c-0", text=content.text, source_path=content.source.path, position=0)
        ]


class FakeEmbeddingProvider:
    async def embed(self, texts: Sequence[str]) -> Sequence[Vector]:
        return [tuple(float(len(t)) for _ in range(3)) for t in texts]


class FakeFullTextIndex:
    def upsert(self, entries: Sequence[IndexEntry]) -> None:
        return None

    def search(self, query: str, kb_ids: frozenset[str], limit: int) -> Sequence[Hit]:
        return []


class FakeVectorIndex:
    def upsert(self, entries: Sequence[tuple[IndexEntry, Vector]]) -> None:
        return None

    def search(self, vector: Vector, kb_ids: frozenset[str], limit: int) -> Sequence[Hit]:
        return []


class FakeRetrieval:
    async def search(self, query: Query, subject: Subject) -> Sequence[Hit]:
        return []


class FakePermissionStore:
    def grants_for(self, subject: Subject) -> Sequence[Permission]:
        return []

    def save(self, permission: Permission) -> None:
        return None

    def revoke(self, permission_id: str) -> None:
        return None


class FakeModelProvider:
    @property
    def name(self) -> str:
        return "fake"

    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(text="", tokens_in=0, tokens_out=0, cost_usd=0.0, latency_ms=0)


class FakeModelGatewayPort:
    async def ask(self, request: AgentModelRequest) -> ModelResponse:
        return ModelResponse(text="", tokens_in=0, tokens_out=0, cost_usd=0.0, latency_ms=0)


class FakeTool:
    @property
    def name(self) -> str:
        return "fake.tool"

    @property
    def max_risk(self) -> RiskLevel:
        return RiskLevel.B

    def describe(self, action: Action) -> str:
        return f"{action.type} -> {action.target}"

    async def execute(self, action: Action) -> ToolResult:
        return ToolResult(success=True, detail="", payload={})

    async def verify(self, action: Action, result: ToolResult) -> Verification:
        return Verification(passed=True, detail="")


class FakeTaskRepository:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def save(self, task: Task) -> None:
        self._tasks[task.task_id] = task

    def get(self, task_id: str) -> Task:
        return self._tasks[task_id]


class FakeAgent(AgentBase):
    """Implementa el hook `_run`; espía si fue invocado (test de ausencia, T1)."""

    def __init__(
        self,
        definition: AgentDefinition,
        retrieval: FakeRetrieval,
        gateway: FakeModelGatewayPort,
        tools: Mapping[str, FakeTool],
        audit: FakeAuditPort,
    ) -> None:
        super().__init__(definition, retrieval, gateway, tools, audit)
        self.run_called = False

    def _run(self, plan: Plan) -> Report:
        self.run_called = True
        return Report(
            task_id=plan.task_id,
            agent_id=self._definition.agent_id,
            summary="hecho",
            success=True,
        )


def sample_task() -> Task:
    return Task(
        task_id="t-1",
        instruction="indexar",
        status=TaskStatus.PENDING,
        created_at=datetime.now(UTC),
    )
