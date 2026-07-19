"""Entidades de agente (mínimas) — definición declarativa y reporte de resultado.

Un agente se crea por configuración (AGENT-01): AgentDefinition es esa configuración.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """Configuración de un agente: dominio, BCs habilitadas, modelo y presupuesto."""

    agent_id: str
    name: str
    domain: str
    kb_ids: frozenset[str]
    model_alias: str
    budget_usd: float


@dataclass(frozen=True, slots=True)
class Report:
    """Resultado consolidado de la ejecución de un plan por un agente."""

    task_id: str
    agent_id: str
    summary: str
    success: bool
