"""Tests del ModelRouter determinístico (GATE-02, D-16/D-17).

El router resuelve `tier -> TierConfig` puro por config: sin LLM, sin heurística, sin
fallback silencioso. Un tier inexistente es un error explícito (`UnknownTier`) que expone
los tiers disponibles — espejo del fail-closed de `CognitivePolicyEngine`.
"""

import dataclasses

import pytest

from core.domain.errors import UnknownTier
from core.domain.gateway import TierConfig
from gateway.router import ModelRouter


def test_resolve_devuelve_tier_config() -> None:
    """(1) `resolve(tier)` devuelve la TierConfig configurada para ese tier."""
    cfg = TierConfig(provider="litellm", model_alias="gemini-default", max_tokens=2048)
    router = ModelRouter({"economico": cfg})

    assert router.resolve("economico") is cfg


def test_resolve_tier_inexistente_levanta_unknown_tier() -> None:
    """(2) tier desconocido -> `UnknownTier` con `.available` = tiers configurados (D-17)."""
    router = ModelRouter(
        {
            "economico": TierConfig("litellm", "gemini-default", 2048),
            "fuerte": TierConfig("anthropic", "claude-opus-4-6", 4096),
        }
    )

    with pytest.raises(UnknownTier) as excinfo:
        router.resolve("inventado")

    assert excinfo.value.tier == "inventado"
    assert set(excinfo.value.available) == {"economico", "fuerte"}


def test_tier_config_es_frozen() -> None:
    """(3) TierConfig es inmutable: setear un campo levanta FrozenInstanceError."""
    cfg = TierConfig(provider="litellm", model_alias="gemini-default", max_tokens=2048)

    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.max_tokens = 1  # type: ignore[misc]
