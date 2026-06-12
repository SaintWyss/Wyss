"""Tests del dominio extendido para el gateway (D-26, D-17/18/20).

Cubren la extensión de `AgentModelRequest` (+tier/+purpose con defaults) y las tres
excepciones de dominio que las olas siguientes de la Fase 2 levantan: `SecretDetected`,
`BudgetExceeded`, `UnknownTier`. Todas derivan de `WyssError` (fail-closed).
"""

from core.domain.config import GatewaySettings
from core.domain.errors import (
    BudgetExceeded,
    SecretDetected,
    UnknownTier,
    WyssError,
)
from core.domain.gateway import AgentModelRequest


def test_agent_model_request_defaults() -> None:
    """Construcción posicional de Fase 1 sigue válida; tier/purpose tienen default (D-26)."""
    req = AgentModelRequest(agent_id="a", task_id="t", prompt="p")
    assert req.tier == "economico"
    assert req.purpose == "general"


def test_agent_model_request_explicit_tier_purpose() -> None:
    """tier y purpose se asignan cuando vienen explícitos."""
    req = AgentModelRequest(agent_id="a", task_id="t", prompt="p", tier="fuerte", purpose="plan")
    assert req.tier == "fuerte"
    assert req.purpose == "plan"


def test_secret_detected_carries_pattern_name_not_secret() -> None:
    """SecretDetected guarda SOLO el nombre del patrón, jamás el valor del secreto (D-20)."""
    err = SecretDetected("env_value")
    assert err.pattern_name == "env_value"
    # El mensaje nombra el patrón, no contiene un secreto crudo.
    assert "env_value" in str(err)


def test_domain_exceptions_derive_from_wyss_error() -> None:
    """Las tres excepciones nuevas son subclases de WyssError (fail-closed coherente)."""
    assert isinstance(SecretDetected("x"), WyssError)
    assert isinstance(BudgetExceeded("x"), WyssError)
    assert isinstance(UnknownTier("t", available=("a",)), WyssError)


def test_gateway_settings_repr_never_exposes_env_values() -> None:
    """WR-01: env_values (API keys reales) NO aparece en repr() — canal latente de fuga."""
    secret = "sk-ant-valor-real-super-secreto-de-test"
    settings = GatewaySettings(
        tiers={}, prices={}, global_budget=1.0, env_values=(secret,)
    )
    assert secret not in repr(settings)
    assert secret not in str(settings)


def test_unknown_tier_exposes_tier_and_available() -> None:
    """UnknownTier expone el tier pedido y los tiers disponibles (D-17)."""
    err = UnknownTier("fuerte", available=("economico",))
    assert err.tier == "fuerte"
    assert err.available == ("economico",)
    msg = str(err)
    assert "fuerte" in msg
    assert "economico" in msg
