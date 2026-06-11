"""Action y Plan — el objeto que la política evalúa (frozen, sin mutación post-evaluación)."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from core.domain.risk import RiskLevel


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
