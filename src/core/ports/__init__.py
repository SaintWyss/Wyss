"""Contratos del núcleo — definidos antes que sus implementaciones (D-11)."""

from core.ports.agent import AgentBase
from core.ports.audit import AuditPort, AuditQueryPort
from core.ports.config import ConfigStore
from core.ports.execution import ExecutionGuardPort, PlanRunner, PolicyEvaluatorPort, Tool
from core.ports.gateway import ModelGatewayPort, ModelProvider
from core.ports.home import (
    CalendarPort,
    CameraPort,
    ClientEventPort,
    HomePort,
    IdempotencyPort,
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
    "ExecutionGuardPort",
    "Extractor",
    "FullTextIndex",
    "HomePort",
    "IdempotencyPort",
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
    "PolicyEvaluatorPort",
    "ProjectionPort",
    "ReminderPort",
    "Retrieval",
    "SpeechPort",
    "TaskRepository",
    "TimerPort",
    "Tool",
    "VectorIndex",
]
