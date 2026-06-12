"""Entidades de dominio frozen (stdlib only) — vocabulario público del núcleo."""

from core.domain.agent import AgentDefinition, Report
from core.domain.audit import ActorType, AuditEvent, AuditEventType, Span
from core.domain.config import WyssSettings
from core.domain.errors import (
    AuditIntegrityError,
    BudgetExceeded,
    ConfigError,
    PolicyViolation,
    SecretDetected,
    UnknownTier,
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
    ExtractedContent,
    Hit,
    IndexEntry,
    Query,
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
    # plan
    "Action",
    # audit
    "ActorType",
    # agent
    "AgentDefinition",
    "AgentModelRequest",
    "AggregateThresholds",
    "AuditEvent",
    "AuditEventType",
    "AuditIntegrityError",
    "BudgetExceeded",
    "Chunk",
    # errors
    "ConfigError",
    # policy
    "DenyRule",
    "ExtractedContent",
    "Hit",
    "IndexEntry",
    # gateway
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
    # risk
    "RiskLevel",
    "SecretDetected",
    "SourceFile",
    "Span",
    # security
    "Subject",
    # task
    "Task",
    "TaskStatus",
    "TierConfig",
    # execution
    "ToolResult",
    "UnknownTier",
    # knowledge
    "Vector",
    "Verification",
    # errors
    "WyssError",
    # config
    "WyssSettings",
    "outcome_for",
]
