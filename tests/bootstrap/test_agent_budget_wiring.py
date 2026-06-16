"""RED/regresión — el tope por-agente se cablea desde [gateway.agent_budgets] (AGENT-07).

Documenta RESEARCH Pitfall 1 a nivel unit: el campo que `CostTracker.authorize` lee es
`settings.gateway.agent_budgets[agent_id]` — NO `[[agents]].budget_usd`. Un TOML que solo
declara `budget_usd` en el [[agents]] deja el tope del GATE sin setear (informativo, no
enforced). El gate solo veta si el agente aparece en [gateway.agent_budgets].

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

# TOML que SOLO declara budget_usd en [[agents]] — NO cablea el gate (Pitfall 1).
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


def test_only_agent_budget_usd_leaves_gate_cap_unset(tmp_path: Path) -> None:
    """Pitfall 1: declarar SOLO [[agents]].budget_usd no setea el cap del gate.

    Sin entrada en [gateway.agent_budgets], `agent_budgets` no tiene a pellegrini → el
    gate solo aplica el global. Esto documenta que budget_usd es informativo, no enforced.
    """
    settings = load_settings(_write(tmp_path, _TOML_ONLY_AGENT_FIELD))
    # el agente existe y declara budget_usd, pero el gate NO lo conoce
    assert any(a.agent_id == "pellegrini" and a.budget_usd == 5.0 for a in settings.agents)
    assert "pellegrini" not in settings.gateway.agent_budgets

    ct = _tracker_from_settings(tmp_path, _TOML_ONLY_AGENT_FIELD)
    try:
        assert ct._agent_budgets.get("pellegrini") is None
        # sin cap por-agente, un gasto grande NO veta por agente (solo el global aplicaría)
        ct.authorize("pellegrini", "gemini-default", 1000, 1000)  # no raise
    finally:
        ct.close()
