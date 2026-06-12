"""ModelRouter determinístico (GATE-02, D-16/D-17): `tier -> TierConfig` puro por config.

El caller declara el tier; el router resuelve a (provider, model_alias, max_tokens) por
lookup directo. Sin LLM, sin heurística, sin fallback silencioso: un tier desconocido es un
error explícito (`UnknownTier` con los tiers disponibles), igual que `CognitivePolicyEngine`
trata lo desconocido como error y no como asunción (fail-closed). `TierConfig` vive en
`core.domain.gateway` (frozen) — el router solo guarda los tiers inyectados y los resuelve.
"""

from core.domain.errors import UnknownTier
from core.domain.gateway import TierConfig


class ModelRouter:
    """Resuelve `tier -> TierConfig` por config inyectada. Determinístico, fail-closed (D-16/D-17)."""

    def __init__(self, tiers: dict[str, TierConfig]) -> None:
        self._tiers = tiers

    def resolve(self, tier: str) -> TierConfig:
        """Devuelve la TierConfig del tier; tier inexistente -> `UnknownTier` (sin fallback, D-17)."""
        try:
            return self._tiers[tier]
        except KeyError:
            raise UnknownTier(tier, available=tuple(self._tiers)) from None
