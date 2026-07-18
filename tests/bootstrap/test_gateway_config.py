"""Tests de la sección [gateway] del config (Pydantic→GatewaySettings frozen, D-09/D-21).

Cubre: carga válida → GatewaySettings de dominio con tiers/precios/presupuesto/timeout/
retención/secret_patterns; clave extra/typo → ConfigError fail-closed nombrando el loc; y
los secret_patterns de config son ADITIVOS (el GatewaySettings NO incluye los built-in —
el minimizer hace el merge en runtime, pero config nunca vacía los built-in).
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from bootstrap.config import load_settings
from core.domain.config import GatewaySettings, WyssSettings
from core.domain.errors import ConfigError
from core.domain.gateway import TierConfig

_VALID = """\
data_dir = "data"
audit_db = "data/audit.db"

[gateway]
global_budget = 50.0
timeout_s = 90.0
trace_retention_days = 30

[gateway.tiers.economico]
provider = "litellm"
model_alias = "gemini-default"
max_tokens = 512

[gateway.tiers.fuerte]
provider = "anthropic"
model_alias = "claude-opus"
max_tokens = 1024

[gateway.prices]
gemini-default = 0.001
claude-opus = 0.015

[gateway.agent_budgets]
belgrano = 10.0

[[gateway.secret_patterns]]
name = "internal_token"
regex = "INT-[0-9]{6}"
"""


def test_loads_valid_gateway_section(write_config: Callable[[str], Path]) -> None:
    """Una sección [gateway] válida mapea a GatewaySettings frozen de dominio."""
    settings = load_settings(write_config(_VALID))

    assert isinstance(settings, WyssSettings)
    gw: GatewaySettings = settings.gateway
    assert isinstance(gw, GatewaySettings)
    assert gw.global_budget == 50.0
    assert gw.timeout_s == 90.0
    assert gw.trace_retention_days == 30
    assert gw.tiers["economico"] == TierConfig(
        provider="litellm", model_alias="gemini-default", max_tokens=512
    )
    assert gw.tiers["fuerte"].provider == "anthropic"
    assert gw.prices["gemini-default"] == 0.001
    assert gw.agent_budgets["belgrano"] == 10.0
    # config_patterns: solo los de config (name, regex-string), NO los built-in.
    assert ("internal_token", "INT-[0-9]{6}") in gw.config_patterns


def test_gateway_defaults_when_absent(write_config: Callable[[str], Path]) -> None:
    """Sin sección [gateway], GatewaySettings tiene defaults (no rompe configs de Fase 1)."""
    settings = load_settings(write_config('data_dir = "data"\naudit_db = "data/audit.db"\n'))
    assert settings.gateway.timeout_s == 120.0  # default D-25
    assert settings.gateway.trace_retention_days == 90  # default D-22
    assert settings.gateway.tiers == {}


def test_extra_key_in_gateway_rejected(write_config: Callable[[str], Path]) -> None:
    """Una clave extra/typo bajo [gateway] falla (extra=forbid) nombrando el loc."""
    bad = _VALID + "\n[gateway.no_existe]\nx = 1\n"
    with pytest.raises(ConfigError, match="no_existe"):
        load_settings(write_config(bad))


def test_extra_key_in_tier_rejected(write_config: Callable[[str], Path]) -> None:
    """Una clave extra dentro de un tier falla (TierConfigModel extra=forbid)."""
    bad = """\
data_dir = "data"
audit_db = "data/audit.db"

[gateway]
global_budget = 10.0

[gateway.tiers.economico]
provider = "litellm"
model_alias = "gemini-default"
max_tokens = 512
typo_field = "x"
"""
    with pytest.raises(ConfigError, match="typo_field"):
        load_settings(write_config(bad))


def test_unknown_tier_provider_rejected_at_boot(
    write_config: Callable[[str], Path],
) -> None:
    """WR-04: un typo en provider ('antropic') aborta el BOOT con ConfigError legible,
    no un KeyError crudo en runtime tras pasar router y minimizer."""
    bad = """\
data_dir = "data"
audit_db = "data/audit.db"

[gateway]
global_budget = 10.0

[gateway.tiers.fuerte]
provider = "antropic"
model_alias = "claude-opus"
max_tokens = 512
"""
    with pytest.raises(ConfigError, match="antropic"):
        load_settings(write_config(bad))


def test_invalid_regex_in_secret_pattern_fails(
    write_config: Callable[[str], Path],
) -> None:
    """Un regex inválido en secret_patterns → ConfigError legible al boot (fail-fast)."""
    bad = """\
data_dir = "data"
audit_db = "data/audit.db"

[gateway]
global_budget = 10.0

[[gateway.secret_patterns]]
name = "broken"
regex = "INT-[0-9"
"""
    with pytest.raises(ConfigError):
        load_settings(write_config(bad))


def test_env_values_cover_all_documented_env_keys(
    write_config: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """CR-01/NOTION-04: los secretos documentados en .env.example entran a env_values.

    GOOGLE_API_KEY y OPENAI_API_KEY quedaban fuera de la red de substring del minimizer.
    """
    expected = {
        "ANTHROPIC_API_KEY": "valor-anthropic-de-test-123",
        "LITELLM_MASTER_KEY": "valor-litellm-de-test-456",
        "GOOGLE_API_KEY": "valor-google-de-test-789",
        "OPENAI_API_KEY": "valor-openai-de-test-012",
        "NOTION_TOKEN": "valor-notion-de-test-345",
    }
    for key, value in expected.items():
        monkeypatch.setenv(key, value)

    settings = load_settings(write_config(_VALID))

    assert set(expected.values()) <= set(settings.gateway.env_values)


def test_config_patterns_do_not_include_builtins(
    write_config: Callable[[str], Path],
) -> None:
    """config_patterns son SOLO los de config; el merge con BUILTIN ocurre en el minimizer."""
    settings = load_settings(write_config(_VALID))
    names = {name for name, _ in settings.gateway.config_patterns}
    assert names == {"internal_token"}  # built-ins NO están acá (el minimizer los agrega)
