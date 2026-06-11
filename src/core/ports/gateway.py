"""Puertos del gateway de modelos: proveedor concreto y la fachada que ven los agentes."""

from typing import Protocol

from core.domain import AgentModelRequest, ModelRequest, ModelResponse


class ModelProvider(Protocol):
    """Un proveedor de modelos concreto (OpenAI, Anthropic…). Async."""

    @property
    def name(self) -> str: ...

    async def complete(self, request: ModelRequest) -> ModelResponse: ...


class ModelGatewayPort(Protocol):
    """Lo único que ven los agentes: routing, minimizado y costo ocurren adentro. Async."""

    async def ask(self, request: AgentModelRequest) -> ModelResponse: ...
