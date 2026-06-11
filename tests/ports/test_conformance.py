"""Conformance assignments (Pattern 5): cada fake asignado a su port, verificado por mypy strict.

Si una firma no cumple el contrato, falla `uv run mypy` (files incluye tests), no pytest.
Los tests solo assertan `is not None`; la verificación REAL es estática.
"""

from pathlib import Path

from audit import SqliteAuditLogger
from core.domain import AgentDefinition
from core.ports import (
    AgentBase,
    AuditPort,
    Chunker,
    ConfigStore,
    EmbeddingProvider,
    Extractor,
    FullTextIndex,
    ModelGatewayPort,
    ModelProvider,
    PermissionStore,
    Retrieval,
    TaskRepository,
    Tool,
    VectorIndex,
)
from tests.ports.fakes import (
    FakeAgent,
    FakeAuditPort,
    FakeChunker,
    FakeConfigStore,
    FakeEmbeddingProvider,
    FakeExtractor,
    FakeFullTextIndex,
    FakeModelGatewayPort,
    FakeModelProvider,
    FakePermissionStore,
    FakeRetrieval,
    FakeTaskRepository,
    FakeTool,
    FakeVectorIndex,
)


def test_audit_port_conforms() -> None:
    port: AuditPort = FakeAuditPort()
    assert port is not None


def test_sqlite_audit_logger_conforms(tmp_path: Path) -> None:
    # Pattern 5: mypy verifica que el adapter real cumple AuditPort (no solo el fake).
    logger: AuditPort = SqliteAuditLogger(tmp_path / "audit.db")
    assert logger is not None


def test_config_store_conforms() -> None:
    port: ConfigStore = FakeConfigStore()
    assert port is not None


def test_extractor_conforms() -> None:
    port: Extractor = FakeExtractor()
    assert port is not None


def test_chunker_conforms() -> None:
    port: Chunker = FakeChunker()
    assert port is not None


def test_embedding_provider_conforms() -> None:
    port: EmbeddingProvider = FakeEmbeddingProvider()
    assert port is not None


def test_full_text_index_conforms() -> None:
    port: FullTextIndex = FakeFullTextIndex()
    assert port is not None


def test_vector_index_conforms() -> None:
    port: VectorIndex = FakeVectorIndex()
    assert port is not None


def test_retrieval_conforms() -> None:
    port: Retrieval = FakeRetrieval()
    assert port is not None


def test_permission_store_conforms() -> None:
    port: PermissionStore = FakePermissionStore()
    assert port is not None


def test_model_provider_conforms() -> None:
    port: ModelProvider = FakeModelProvider()
    assert port is not None


def test_model_gateway_conforms() -> None:
    port: ModelGatewayPort = FakeModelGatewayPort()
    assert port is not None


def test_tool_conforms() -> None:
    port: Tool = FakeTool()
    assert port is not None


def test_task_repository_conforms() -> None:
    port: TaskRepository = FakeTaskRepository()
    assert port is not None


def test_agent_base_conforms() -> None:
    agent: AgentBase = FakeAgent(
        AgentDefinition(
            agent_id="belgrano",
            name="Belgrano",
            domain="estudio",
            kb_ids=frozenset(),
            model_alias="cheap",
            budget_usd=1.0,
        ),
        FakeRetrieval(),
        FakeModelGatewayPort(),
        {},
        FakeAuditPort(),
    )
    assert agent is not None
