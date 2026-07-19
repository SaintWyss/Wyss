"""Entidades del gateway de modelos (mínimas) — request/response de proveedores."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Pedido a un proveedor de modelos concreto."""

    prompt: str
    model_alias: str
    max_tokens: int


@dataclass(frozen=True, slots=True)
class TierConfig:
    """Resolución de un tier (entidad de dominio): provider + alias de modelo + tope de tokens.

    Vive en `core.domain` (no en `gateway.router`) para que el bootstrap (02-05 GatewaySettings)
    y el gateway la importen sin ciclo. El `max_tokens` lo fija el tier, NO el caller (Open
    Question 1 resuelta): el agente solo declara `tier`+`purpose`, la config decide el límite.
    """

    provider: str  # "litellm" | "anthropic"
    model_alias: str  # p.ej. "gemini-default", "claude-opus-4-6"
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
