"""Entidades de ejecución (mínimas) — resultado de una herramienta + su verificación."""

from collections.abc import Mapping
from dataclasses import dataclass


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
