"""Tests de los providers HTTP reales (GATE-01, D-14) + el fake intercambiable.

Los providers usan httpx directo (sin SDK): los transientes los maneja el retry del gateway,
NO el provider (Pitfall 1, D-25). respx intercepta el tráfico httpx sin red y valida el shape
del request real. El dict del JSON de la API muere dentro del adapter: afuera solo viaja
ModelResponse de dominio. El costo lo calcula CostTracker (D-24), por eso `cost_usd == 0.0`.
"""

import json

import httpx
import pytest
import respx

from core.domain.gateway import ModelRequest, ModelResponse
from gateway.providers import AnthropicProvider, FakeModelProvider, LiteLLMProvider


@pytest.fixture
def request_economico() -> ModelRequest:
    return ModelRequest(prompt="hola", model_alias="gemini-default", max_tokens=256)


async def test_anthropic_complete_traduce_a_model_response(
    http_client: httpx.AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """(1) AnthropicProvider parsea content[].text + usage -> ModelResponse; cost_usd=0.0."""
    route = respx_mock.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "respuesta de claude"}],
                "usage": {"input_tokens": 12, "output_tokens": 7},
            },
        )
    )
    provider = AnthropicProvider(http_client, api_key="sk-ant-secreto", version="2023-06-01")

    result = await provider.complete(
        ModelRequest(prompt="hola", model_alias="claude-opus-4-6", max_tokens=512)
    )

    assert isinstance(result, ModelResponse)
    assert result.text == "respuesta de claude"
    assert result.tokens_in == 12
    assert result.tokens_out == 7
    assert result.cost_usd == 0.0
    assert provider.name == "anthropic"
    assert route.called


async def test_anthropic_envia_headers_correctos(
    http_client: httpx.AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """(3a) AnthropicProvider envía x-api-key + anthropic-version + el body esperado."""
    route = respx_mock.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )
    )
    provider = AnthropicProvider(http_client, api_key="sk-ant-XYZ", version="2023-06-01")

    await provider.complete(
        ModelRequest(prompt="ping", model_alias="claude-opus-4-6", max_tokens=42)
    )

    sent = route.calls.last.request
    assert sent.headers["x-api-key"] == "sk-ant-XYZ"
    assert sent.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(sent.content)
    assert body["model"] == "claude-opus-4-6"
    assert body["max_tokens"] == 42
    assert body["messages"] == [{"role": "user", "content": "ping"}]


async def test_litellm_complete_mapea_openai_shape(
    http_client: httpx.AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """(2) LiteLLMProvider parsea choices[0].message.content + usage.prompt/completion_tokens."""
    route = respx_mock.post("http://localhost:4000/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "respuesta gemini"}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5},
            },
        )
    )
    provider = LiteLLMProvider(
        http_client, base_url="http://localhost:4000", master_key="sk-master"
    )

    result = await provider.complete(
        ModelRequest(prompt="hola", model_alias="gemini-default", max_tokens=256)
    )

    assert result.text == "respuesta gemini"
    assert result.tokens_in == 20
    assert result.tokens_out == 5
    assert result.cost_usd == 0.0
    assert provider.name == "litellm"
    assert route.called


async def test_litellm_envia_authorization_bearer(
    http_client: httpx.AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """(3b) LiteLLMProvider envía Authorization: Bearer {master_key}."""
    route = respx_mock.post("http://localhost:4000/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )
    )
    provider = LiteLLMProvider(
        http_client, base_url="http://localhost:4000/", master_key="sk-master-123"
    )

    await provider.complete(
        ModelRequest(prompt="ping", model_alias="gemini-default", max_tokens=8)
    )

    assert route.calls.last.request.headers["authorization"] == "Bearer sk-master-123"


async def test_provider_propaga_4xx_sin_reintentar(
    http_client: httpx.AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """(4) 4xx -> raise_for_status propaga; el provider NO reintenta (el retry vive afuera, D-25)."""
    route = respx_mock.post("https://api.anthropic.com/v1/messages").mock(
        return_value=httpx.Response(400, json={"error": "bad request"})
    )
    provider = AnthropicProvider(http_client, api_key="sk-ant-x")

    with pytest.raises(httpx.HTTPStatusError):
        await provider.complete(
            ModelRequest(prompt="x", model_alias="claude-opus-4-6", max_tokens=8)
        )

    assert route.call_count == 1  # un solo intento: el provider no reintenta


async def test_fake_model_provider_intercambiable(
    request_economico: ModelRequest,
) -> None:
    """(5) FakeModelProvider implementa la misma firma (.name + complete async), intercambiable."""
    fake = FakeModelProvider(
        response=ModelResponse(
            text="fake", tokens_in=1, tokens_out=1, cost_usd=0.0, latency_ms=0
        )
    )

    result = await fake.complete(request_economico)

    assert fake.name == "fake"
    assert result.text == "fake"


async def test_fake_model_provider_puede_inyectar_excepcion(
    request_economico: ModelRequest,
) -> None:
    """(5b) FakeModelProvider con error inyectado lo levanta (para tests del gateway/retry)."""
    fake = FakeModelProvider(error=httpx.ConnectTimeout("boom"))

    with pytest.raises(httpx.ConnectTimeout):
        await fake.complete(request_economico)
