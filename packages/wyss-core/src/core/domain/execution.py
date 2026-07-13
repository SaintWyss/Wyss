"""Entidades de ejecución (mínimas) — resultado de una herramienta + su verificación."""

from collections.abc import Mapping
from dataclasses import dataclass

from core.domain.risk import RiskLevel


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Resultado de ejecutar una Action vía una Tool."""

    success: bool
    detail: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class Verification:
    """Verificación post-ejecución de una Action (doc 11: resultado + verificación)."""

    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class ExecutionAuthorization:
    """Decisión fail-closed de la segunda muralla previa al I/O real."""

    allowed: bool
    risk_level: RiskLevel
    reason: str
