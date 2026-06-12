"""AnthropicProvider (tier fuerte, D-14): adapter httpx directo sobre la Messages API.

Implementa `ModelProvider.complete(ModelRequest) -> ModelResponse`. httpx directo, sin SDK:
los transientes (429/5xx) los maneja el retry centralizado del gateway (D-25), NO el provider
ni un SDK — así se evita el doble-retry que descontrola el gate de presupuesto (Pitfall 1).
El dict del JSON de la API muere acá: afuera solo viaja ModelResponse de dominio. El costo lo
calcula CostTracker (D-24), por eso `cost_usd=0.0`. La api_key viaja en header, nunca se loguea.
"""

import time

import httpx

from core.domain.gateway import ModelRequest, ModelResponse

_MESSAGES_URL = "https://api.anthropic.com/v1/messages"


class AnthropicProvider:
    """Adapter de la Messages API de Anthropic (httpx directo). Implementa ModelProvider."""

    def __init__(
        self, client: httpx.AsyncClient, api_key: str, *, version: str = "2023-06-01"
    ) -> None:
        self._client = client
        self._headers = {
            "x-api-key": api_key,  # auth de Anthropic (V2); nunca logueado
            "anthropic-version": version,  # header requerido por la Messages API
            "content-type": "application/json",
        }

    @property
    def name(self) -> str:
        return "anthropic"

    async def complete(self, request: ModelRequest) -> ModelResponse:
        started = time.monotonic()
        resp = await self._client.post(
            _MESSAGES_URL,
            headers=self._headers,
            json={
                "model": request.model_alias,
                "max_tokens": request.max_tokens,
                "messages": [{"role": "user", "content": request.prompt}],
            },
        )
        resp.raise_for_status()  # transientes los maneja el retry del gateway (D-25), no acá
        data = resp.json()
        # El dict de la API muere acá: traducimos a dominio y descartamos el resto.
        text = "".join(
            block["text"] for block in data["content"] if block.get("type") == "text"
        )
        usage = data["usage"]
        return ModelResponse(
            text=text,
            tokens_in=usage["input_tokens"],
            tokens_out=usage["output_tokens"],
            cost_usd=0.0,  # el costo lo calcula CostTracker (D-24), no el provider
            latency_ms=int((time.monotonic() - started) * 1000),
        )
