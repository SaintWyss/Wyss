"""Regresión — el tope por-agente llega al gate desde config (AGENT-07).

Cierra RESEARCH Pitfall 1 a nivel unit (Plan 08-03, Opción b): el campo que
`CostTracker.authorize` lee es `settings.gateway.agent_budgets[agent_id]`. Antes, declarar
`budget_usd` SOLO en `[[agents]]` dejaba el tope del GATE sin setear. Ahora `bootstrap.config`
DERIVA `agent_budgets[agent_id]` desde `[[agents]].budget_usd` cuando no hay valor explícito en
`[gateway.agent_budgets]`; el valor explícito de `[gateway.agent_budgets]` tiene precedencia.

Tests determinísticos sobre `load_settings` (frontera Pydantic→dominio) + un CostTracker real
(DB en tmp_path — NUNCA bajo el repo data/ por el denylist NTFS de la segunda muralla).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bootstrap.config import load_settings
from gateway.cost import CostTracker
from tests.ports.fakes import FakeAuditPort

# TOML con Pellegrini en AMBOS campos (el correcto, como config.example.toml).
_TOML_WIRED = """\
data_dir = "data"
audit_db = "data/audit.db"

[gateway]
global_budget = 50.0

[gateway.tiers.economico]
provider = "litellm"
model_alias = "gemini-default"
max_tokens = 1024

[gateway.prices]
gemini-default = 0.0005

[gateway.agent_budgets]
pellegrini = 5.0

[[agents]]
agent_id = "pellegrini"
name = "Pellegrini"
domain = "finanzas"
knowledge_bases = []
model_tier = "economico"
budget_usd = 5.0
"""

# TOML que SOLO declara budget_usd en [[agents]] — ahora DERIVA el tope del gate (Pitfall 1).
_TOML_ONLY_AGENT_FIELD = """\
data_dir = "data"
audit_db = "data/audit.db"

[gateway]
global_budget = 50.0

[gateway.tiers.economico]
provider = "litellm"
model_alias = "gemini-default"
max_tokens = 1024

[gateway.prices]
gemini-default = 0.0005

[[agents]]
agent_id = "pellegrini"
name = "Pellegrini"
domain = "finanzas"
knowledge_bases = []
model_tier = "economico"
budget_usd = 5.0
"""

# TOML con AMBOS campos pero con valores DISTINTOS — el explícito de [gateway] debe ganar.
_TOML_PRECEDENCE = """\
data_dir = "data"
audit_db = "data/audit.db"

[gateway]
global_budget = 50.0

[gateway.tiers.economico]
provider = "litellm"
model_alias = "gemini-default"
max_tokens = 1024

[gateway.prices]
gemini-default = 0.0005

[gateway.agent_budgets]
pellegrini = 3.0

[[agents]]
agent_id = "pellegrini"
name = "Pellegrini"
domain = "finanzas"
knowledge_bases = []
model_tier = "economico"
budget_usd = 5.0
"""


def _write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(content, encoding="utf-8")
    return p


def _tracker_from_settings(tmp_path: Path, toml: str) -> CostTracker:
    settings = load_settings(_write(tmp_path, toml))
    return CostTracker(
        tmp_path / "traces.db",
        prices=dict(settings.gateway.prices),
        global_budget=settings.gateway.global_budget,
        agent_budgets=dict(settings.gateway.agent_budgets),
        audit=FakeAuditPort(),
    )


def test_agent_budgets_field_feeds_gate(tmp_path: Path) -> None:
    """[gateway.agent_budgets].pellegrini=5.0 produce un cap real de 5.0 en el gate.

    Tras gastar 5.0 (el tope), el siguiente authorize de pellegrini veta con su nombre.
    """
    ct = _tracker_from_settings(tmp_path, _TOML_WIRED)
    try:
        assert ct._agent_budgets.get("pellegrini") == pytest.approx(5.0)
        # gastar exactamente el tope (5.0) → siguiente authorize veta
        ct.record("pellegrini", "gemini-default", 5_000_000, 5_000_000)  # 10M/1000*0.0005=5.0
        from core.domain.errors import BudgetExceeded

        with pytest.raises(BudgetExceeded, match="pellegrini"):
            ct.authorize("pellegrini", "gemini-default", 1000, 1000)
    finally:
        ct.close()


def test_agent_budget_usd_derives_gate_cap(tmp_path: Path) -> None:
    """Pitfall 1 cerrado: declarar SOLO [[agents]].budget_usd DERIVA el cap del gate.

    Aunque [gateway.agent_budgets] esté vacío, `agent_budgets["pellegrini"]` queda en 5.0
    (derivado de [[agents]].budget_usd) y el gate veta tras agotarlo — el footgun desaparece
    para todo agente futuro.
    """
    settings = load_settings(_write(tmp_path, _TOML_ONLY_AGENT_FIELD))
    assert any(a.agent_id == "pellegrini" and a.budget_usd == 5.0 for a in settings.agents)
    # ahora el gate SÍ lo conoce, derivado del campo del agente
    assert settings.gateway.agent_budgets.get("pellegrini") == pytest.approx(5.0)

    ct = _tracker_from_settings(tmp_path, _TOML_ONLY_AGENT_FIELD)
    try:
        assert ct._agent_budgets.get("pellegrini") == pytest.approx(5.0)
        ct.record("pellegrini", "gemini-default", 5_000_000, 5_000_000)  # 10M/1000*0.0005=5.0
        from core.domain.errors import BudgetExceeded

        with pytest.raises(BudgetExceeded, match="pellegrini"):
            ct.authorize("pellegrini", "gemini-default", 1000, 1000)
    finally:
        ct.close()


def test_explicit_gateway_budget_wins_over_derived(tmp_path: Path) -> None:
    """Precedencia: el valor explícito de [gateway.agent_budgets] gana sobre el derivado.

    El [[agents]].budget_usd=5.0 NO pisa el [gateway.agent_budgets].pellegrini=3.0 explícito.
    Sin override silencioso: el cap real del gate es 3.0.
    """
    settings = load_settings(_write(tmp_path, _TOML_PRECEDENCE))
    assert settings.gateway.agent_budgets.get("pellegrini") == pytest.approx(3.0)
