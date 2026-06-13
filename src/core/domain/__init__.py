"""Entidades de dominio frozen (stdlib only) — vocabulario público del núcleo."""

from core.domain.agent import AgentDefinition, Report
from core.domain.audit import ActorType, AuditEvent, AuditEventType, Span
from core.domain.config import GatewaySettings, WyssSettings
from core.domain.errors import (
    AuditIntegrityError,
    BudgetExceeded,
    ConfigError,
    ExtractionError,
    IndexIntegrityError,
    PolicyViolation,
    SecretDetected,
    SecretFileExcluded,
    UnknownTier,
    UnsupportedFileError,
    WyssError,
)
from core.domain.execution import ToolResult, Verification
from core.domain.gateway import (
    AgentModelRequest,
    ModelRequest,
    ModelResponse,
    TierConfig,
)
from core.domain.knowledge import (
    Chunk,
    EstimateResult,
    ExtractedContent,
    FileRecord,
    FileStatus,
    Hit,
    IndexEntry,
    IngestRunResult,
    IngestSettings,
    Query,
    SearchResult,
    SourceFile,
    Vector,
)
from core.domain.plan import Action, Plan
from core.domain.policy import (
    DEFAULT_SENSITIVE_DIRS,
    AggregateThresholds,
    DenyRule,
    PolicyDecision,
    PolicyRules,
)
from core.domain.risk import Outcome, RiskLevel, outcome_for
from core.domain.security import Permission, Subject
from core.domain.task import Task, TaskStatus

__all__ = [
    "DEFAULT_SENSITIVE_DIRS",
    "Action",
    "ActorType",
    "AgentDefinition",
    "AgentModelRequest",
    "AggregateThresholds",
    "AuditEvent",
    "AuditEventType",
    "AuditIntegrityError",
    "BudgetExceeded",
    "Chunk",
    "ConfigError",
    "DenyRule",
    "EstimateResult",
    "ExtractedContent",
    "ExtractionError",
    "FileRecord",
    "FileStatus",
    "GatewaySettings",
    "Hit",
    "IndexEntry",
    "IndexIntegrityError",
    "IngestRunResult",
    "IngestSettings",
    "ModelRequest",
    "ModelResponse",
    "Outcome",
    "Permission",
    "Plan",
    "PolicyDecision",
    "PolicyRules",
    "PolicyViolation",
    "Query",
    "Report",
    "RiskLevel",
    "SearchResult",
    "SecretDetected",
    "SecretFileExcluded",
    "SourceFile",
    "Span",
    "Subject",
    "Task",
    "TaskStatus",
    "TierConfig",
    "ToolResult",
    "UnknownTier",
    "UnsupportedFileError",
    "Vector",
    "Verification",
    "WyssError",
    "WyssSettings",
    "outcome_for",
]
