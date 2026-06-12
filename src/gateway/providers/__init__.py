"""Adaptadores de proveedor del gateway (httpx directo) + fakes intercambiables (D-14/D-15).

Barrel de exports. httpx y los dicts de las APIs viven SOLO acá (import-linter: el core sigue
stdlib-only; el gateway puede usar httpx). Los reales y los fakes comparten la firma de port,
por eso son intercambiables por config sin tocar código.
"""

from gateway.providers.anthropic import AnthropicProvider
from gateway.providers.fakes import FakeEmbeddingProvider, FakeModelProvider
from gateway.providers.litellm import LiteLLMProvider
from gateway.providers.ollama import OllamaEmbeddingProvider

__all__ = [
    "AnthropicProvider",
    "FakeEmbeddingProvider",
    "FakeModelProvider",
    "LiteLLMProvider",
    "OllamaEmbeddingProvider",
]
