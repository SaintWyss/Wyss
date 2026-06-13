"""Modelo puro de intención del orquestador (ORCH-03/04)."""

from dataclasses import dataclass
from enum import StrEnum


class IntentCategory(StrEnum):
    """Categorías operativas clasificables por el orquestador (ORCH-03)."""

    KNOWLEDGE_QUERY = "knowledge_query"
    FILE_OPERATION = "file_operation"
    REPO_TASK = "repo_task"
    SYSTEM_ACTION = "system_action"
    AGENT_TASK = "agent_task"
    ROUTINE_TRIGGER = "routine_trigger"
    ADMIN_TASK = "admin_task"
    DANGEROUS_OPERATION = "dangerous_operation"
    AMBIGUOUS_REQUEST = "ambiguous_request"


@dataclass(frozen=True, slots=True)
class IntentClassification:
    """Resultado de clasificar NL; el nivel A/B/C/D lo asigna el policy engine."""

    category: IntentCategory
    confidence: float
    clarification_needed: bool
