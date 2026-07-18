"""OllamaEmbeddingProvider (D-15): embeddings LOCALES — el contenido nunca sale de la máquina.

Implementa el `EmbeddingProvider` de `core/ports/knowledge.py` (port REUSADO, no inventado):
`async def embed(texts) -> Sequence[Vector]`. POST a `/api/embed` (singular, con batching y salida
L2-normalizada — NO el deprecado `/api/embeddings`). httpx directo; el dict del JSON muere acá,
afuera solo tuplas `Vector` de dominio. Riesgo de egress aceptado: Ollama corre en localhost de
confianza (D-15, threat T-02-embed-egress: accept).
"""

from collections.abc import Sequence

import httpx

from core.domain.knowledge import Vector


class OllamaEmbeddingProvider:
    """Adapter de embeddings de Ollama local (httpx, /api/embed). Implementa EmbeddingProvider."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
    ) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}/api/embed"
        self._model = model

    async def embed(self, texts: Sequence[str]) -> Sequence[Vector]:
        resp = await self._client.post(self._url, json={"model": self._model, "input": list(texts)})
        resp.raise_for_status()
        # /api/embed devuelve "embeddings" (batch, L2-normalizado). El dict muere acá.
        return [tuple(vec) for vec in resp.json()["embeddings"]]
