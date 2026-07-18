"""Los 17 contratos del núcleo (16 Protocols + AgentBase) — definidos antes que las impls (D-11)."""

from core.ports.agent import AgentBase
from core.ports.audit import AuditPort, AuditQueryPort
from core.ports.config import ConfigStore
from core.ports.execution import PlanRunner, Tool
from core.ports.gateway import ModelGatewayPort, ModelProvider
from core.ports.home import (
    CalendarPort,
    CameraPort,
    ClientEventPort,
    HomePort,
    MediaPort,
    NotificationPort,
    ProjectionPort,
    ReminderPort,
    SpeechPort,
    TimerPort,
)
from core.ports.knowledge import (
    Chunker,
    EmbeddingProvider,
    Extractor,
    FullTextIndex,
    Retrieval,
    VectorIndex,
)
from core.ports.ledger import LedgerPort
from core.ports.memory import MemoryAdmin, MemoryPort
from core.ports.orchestrator import OrchestratorPort
from core.ports.persistence import TaskRepository
from core.ports.security import PermissionStore

__all__ = [
    "AgentBase",
    "AuditPort",
    "AuditQueryPort",
    "CalendarPort",
    "CameraPort",
    "Chunker",
    "ClientEventPort",
    "ConfigStore",
    "EmbeddingProvider",
    "Extractor",
    "FullTextIndex",
    "HomePort",
    "LedgerPort",
    "MediaPort",
    "MemoryAdmin",
    "MemoryPort",
    "ModelGatewayPort",
    "ModelProvider",
    "NotificationPort",
    "OrchestratorPort",
    "PermissionStore",
    "PlanRunner",
    "ProjectionPort",
    "ReminderPort",
    "Retrieval",
    "SpeechPort",
    "TaskRepository",
    "TimerPort",
    "Tool",
    "VectorIndex",
]
