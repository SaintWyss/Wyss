"""Config del orquestador y derivación de presupuesto al gateway."""

from pathlib import Path

import pytest

from bootstrap.config import load_settings


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")
    return path


def test_orchestrator_absent_defaults_to_deterministic(tmp_path: Path) -> None:
    settings = load_settings(
        _write(
            tmp_path,
            """\
data_dir = "data"
audit_db = "data/audit.db"
""",
        )
    )

    assert settings.orchestrator.mode == "deterministic"
    assert settings.orchestrator.tier == "economico"
    assert settings.orchestrator.budget_usd is None


def test_orchestrator_llm_budget_derives_gateway_agent_budget(tmp_path: Path) -> None:
    settings = load_settings(
        _write(
            tmp_path,
            """\
data_dir = "data"
audit_db = "data/audit.db"

[orchestrator]
mode = "llm"
tier = "fuerte"
budget_usd = 2.0
""",
        )
    )

    assert settings.orchestrator.mode == "llm"
    assert settings.orchestrator.tier == "fuerte"
    assert settings.gateway.agent_budgets.get("orchestrator") == pytest.approx(2.0)


def test_explicit_gateway_orchestrator_budget_wins(tmp_path: Path) -> None:
    settings = load_settings(
        _write(
            tmp_path,
            """\
data_dir = "data"
audit_db = "data/audit.db"

[gateway.agent_budgets]
orchestrator = 7.0

[orchestrator]
mode = "llm"
budget_usd = 2.0
""",
        )
    )

    assert settings.gateway.agent_budgets.get("orchestrator") == pytest.approx(7.0)
