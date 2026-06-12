"""Fakes de providers del gateway: intercambiables con los reales por config (D-14, criterio 5).

Espejan la firma EXACTA de los ports (`ModelProvider`, `EmbeddingProvider`): `.name` property +
`complete` async; `embed` async. Permiten inyectar una respuesta o una excepción para testear el
gateway (retry, gate de presupuesto) sin tocar la red. Viven en `gateway/` —junto a los reales—
para que el bootstrap los cablee por config sin que el core dependa de httpx ni de ningún adapter.
"""

from collections.abc import Sequence

from core.domain.gateway import ModelRequest, ModelResponse
from core.domain.knowledge import Vector


class FakeModelProvider:
    """ModelProvider en memoria: devuelve una ModelResponse fija o levanta excepción inyectada."""

    def __init__(
        self,
        *,
        response: ModelResponse | None = None,
        error: Exception | None = None,
        name: str = "fake",
    ) -> None:
        self._response = response or ModelResponse(
            text="", tokens_in=0, tokens_out=0, cost_usd=0.0, latency_ms=0
        )
        self._error = error
        self._name = name
        self.calls: list[ModelRequest] = []

    @property
    def name(self) -> str:
        return self._name

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        if self._error is not None:
            raise self._error
        return self._response


class FakeEmbeddingProvider:
    """EmbeddingProvider determinista: un vector por texto según el largo (sin red, CI-safe)."""

    def __init__(self, *, dims: int = 3) -> None:
        self._dims = dims
        self.calls: list[Sequence[str]] = []

    async def embed(self, texts: Sequence[str]) -> Sequence[Vector]:
        self.calls.append(texts)
        return [tuple(float(len(t)) for _ in range(self._dims)) for t in texts]
