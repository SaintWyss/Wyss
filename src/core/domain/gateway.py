"""Entidades del gateway de modelos (mínimas) — request/response de proveedores."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Pedido a un proveedor de modelos concreto."""

    prompt: str
    model_alias: str
    max_tokens: int


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Respuesta de un modelo más métricas de costo y latencia."""

    text: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int


@dataclass(frozen=True, slots=True)
class AgentModelRequest:
    """Pedido de un agente al gateway (routing/minimizado/costo ocurren adentro)."""

    agent_id: str
    task_id: str
    prompt: str
    # NUEVO (D-26) — defaults obligatorios para no romper construcciones posicionales de Fase 1.
    tier: str = "economico"
    purpose: str = "general"
