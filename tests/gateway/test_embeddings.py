"""Tests del EmbeddingProvider (GATE-01 criterio 5, D-15).

Tres capas:
1. FakeEmbeddingProvider — corre siempre en CI (cobertura del contrato, intercambiable).
2. OllamaEmbeddingProvider con respx — valida el shape de `/api/embed` sin Ollama real (CI).
3. OllamaEmbeddingProvider real — opt-in (`WYSS_TEST_OLLAMA=1`), patrón EXACTO del skipif NTFS.
   Ollama NO está instalado en la máquina del owner; en CI se saltea (el fake + respx cubren).

Para correr el test real: instalar Ollama, `ollama pull nomic-embed-text`, luego
`WYSS_TEST_OLLAMA=1 uv run pytest tests/gateway/test_embeddings.py`.
"""

import os

import httpx
import pytest
import respx

from gateway.providers import FakeEmbeddingProvider, OllamaEmbeddingProvider


async def test_fake_embedding_provider_intercambiable() -> None:
    """(1) FakeEmbeddingProvider implementa `embed(texts) -> Sequence[Vector]`, determinista."""
    fake = FakeEmbeddingProvider(dims=3)

    vectors = await fake.embed(["hola", "mundo!"])

    assert len(vectors) == 2
    assert all(len(v) == 3 for v in vectors)
    # Determinista por largo del texto: "hola"=4, "mundo!"=6.
    assert vectors[0] == (4.0, 4.0, 4.0)
    assert vectors[1] == (6.0, 6.0, 6.0)


async def test_ollama_embed_shape_con_respx(
    http_client: httpx.AsyncClient, respx_mock: respx.MockRouter
) -> None:
    """(2) OllamaEmbeddingProvider POSTea a /api/embed y parsea "embeddings" -> tuplas Vector."""
    route = respx_mock.post("http://localhost:11434/api/embed").mock(
        return_value=httpx.Response(
            200,
            json={"embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]},
        )
    )
    provider = OllamaEmbeddingProvider(http_client)

    vectors = await provider.embed(["texto uno", "texto dos"])

    assert vectors == [(0.1, 0.2, 0.3), (0.4, 0.5, 0.6)]
    assert route.called
    # Verifica el endpoint singular /api/embed (no el deprecado /api/embeddings) + body batch.
    sent = route.calls.last.request
    assert sent.url.path == "/api/embed"
    body = sent.content.decode()
    assert '"input"' in body and "texto uno" in body and "texto dos" in body


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("WYSS_TEST_OLLAMA") != "1",
    reason="requiere WYSS_TEST_OLLAMA=1 (Ollama local + `ollama pull nomic-embed-text`)",
)
async def test_ollama_embed_real() -> None:
    """(3) Opt-in: embed real contra Ollama local (localhost:11434, nomic-embed-text)."""
    async with httpx.AsyncClient() as client:
        provider = OllamaEmbeddingProvider(client)
        vectors = await provider.embed(["un texto de prueba"])

    assert len(vectors) == 1
    assert len(vectors[0]) > 0  # nomic-embed-text -> 768 dims
    assert all(isinstance(x, float) for x in vectors[0])
