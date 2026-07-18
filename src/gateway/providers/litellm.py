"""LiteLLMProvider (tier económico, D-14): adapter httpx sobre el proxy OpenAI-compatible.

Implementa `ModelProvider.complete(ModelRequest) -> ModelResponse` contra el proxy LiteLLM del
owner (localhost:4000), que expone una API OpenAI-compatible (`/v1/chat/completions`). httpx
directo, sin SDK: el retry vive en el gateway (D-25), no acá (Pitfall 1). El dict del JSON muere
en el adapter; afuera solo ModelResponse de dominio. El master_key viaja en Authorization Bearer,
nunca se loguea. El costo lo calcula CostTracker (D-24): `cost_usd=0.0` aunque la API reporte uno.
"""

import time

import httpx

from core.domain.gateway import ModelRequest, ModelResponse


class LiteLLMProvider:
    """Adapter del proxy LiteLLM (OpenAI-compatible, httpx directo). Implementa ModelProvider."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, master_key: str) -> None:
        self._client = client
        # El adapter es dueño del path: acepta base URL con o sin `/v1` (ambas
        # convenciones circulan — OpenAI SDK usa base con /v1) y evita `/v1/v1`.
        base = base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        self._url = f"{base}/v1/chat/completions"
        self._headers = {"authorization": f"Bearer {master_key}"}  # nunca logueado

    @property
    def name(self) -> str:
        return "litellm"

    async def complete(self, request: ModelRequest) -> ModelResponse:
        started = time.monotonic()
        resp = await self._client.post(
            self._url,
            headers=self._headers,
            json={
                "model": request.model_alias,
                "messages": [{"role": "user", "content": request.prompt}],
                "max_tokens": request.max_tokens,
            },
        )
        resp.raise_for_status()  # transientes los maneja el retry del gateway (D-25)
        data = resp.json()
        # El dict OpenAI-shape muere acá: traducimos a dominio.
        text = data["choices"][0]["message"]["content"]
        usage = data["usage"]
        return ModelResponse(
            text=text,
            tokens_in=usage["prompt_tokens"],
            tokens_out=usage["completion_tokens"],
            # CostTracker calcula el costo real (D-24); el "response_cost" del proxy, si viene,
            # se guardará como dato comparativo en el trace (02-05), nunca como verdad del gate.
            cost_usd=0.0,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
