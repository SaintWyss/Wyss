"""Action y Plan — el objeto que la política evalúa (frozen, sin mutación post-evaluación)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from core.domain.risk import RiskLevel


class ErrorPolicy(StrEnum):
    """Política declarativa ante fallo de un paso del Plan (D-62)."""

    RETRY = "retry"
    ESCALATE = "escalate"
    ABORT = "abort"


@dataclass(frozen=True, slots=True)
class RetryParams:
    """Parámetros de retry declarados en el Plan; el enforcement vive en Fase 6."""

    max_attempts: int = 3
    backoff_base_s: float = 1.0
    backoff_max_s: float = 60.0


@dataclass(frozen=True, slots=True)
class Action:
    """Un paso atómico de un plan.

    `parameters` es `Mapping` (no `dict`) — la interfaz no expone mutación y mypy strict
    rechaza `params["x"] = y`. `type` usa taxonomía con prefijo ("file.delete"); un tipo
    desconocido clasifica C (fail-closed) en el engine de política.
    """

    type: str
    target: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    on_error: ErrorPolicy = ErrorPolicy.ABORT
    retry_params: RetryParams | None = None


@dataclass(frozen=True, slots=True)
class Plan:
    """Plan completo evaluado por la política.

    `steps` es `tuple` (no `list`) — inmutable. `estimated_risk` es la estimación del
    LLM/planner: solo puede SUBIR el nivel final (POL-04), nunca bajarlo.
    """

    task_id: str
    summary: str
    steps: tuple[Action, ...]
    rationale: str
    estimated_risk: RiskLevel | None = None
