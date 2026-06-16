"""Tests del bootstrap de config para agentes (D-73).

Verifica que AgentConfigModel sigue el patrón D-15:
- extra="forbid" rechaza claves desconocidas en [[agents]]
- La conversión Pydantic→AgentDefinition produce dataclass frozen, no BaseModel

Wave 0 — RED: AgentConfigModel y el campo agents en WyssSettings aún no existen.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from bootstrap.config import load_settings
from core.domain.agent import AgentDefinition
from core.domain.errors import ConfigError

# TOML base con un [[agents]] válido
_VALID_AGENT_TOML = """\
data_dir = "data"
audit_db = "data/audit.db"

[[agents]]
agent_id = "belgrano"
name = "Agente Belgrano"
domain = "investigacion"
knowledge_bases = ["kb-historia"]
model_tier = "standard"
budget_usd = 1.0
"""


def _write_toml(tmp_path: Path, content: str) -> Path:
    """Helper: escribe TOML en tmp_path y retorna el path."""
    path = tmp_path / "config.toml"
    path.write_text(content, encoding="utf-8")
    return path


def test_agent_extra_key_rejected(tmp_path: Path) -> None:
    """D-73: una clave desconocida en [[agents]] falla con ConfigError (extra=forbid).

    El bootstrap falla cerrado (fail-closed): un typo en la config del agente
    aborta el arranque en lugar de ignorar silenciosamente el campo.
    """
    toml_content = """\
data_dir = "data"
audit_db = "data/audit.db"

[[agents]]
agent_id = "belgrano"
name = "Agente Belgrano"
domain = "investigacion"
knowledge_bases = ["kb-historia"]
model_tier = "standard"
budget_usd = 1.0
campo_desconocido = "valor"
"""
    path = _write_toml(tmp_path, toml_content)
    with pytest.raises(ConfigError, match="campo_desconocido"):
        load_settings(path)


def test_agents_become_definitions(tmp_path: Path) -> None:
    """D-73: settings.agents[0] es AgentDefinition (frozen dataclass), no BaseModel.

    El patrón D-15 garantiza que Pydantic solo existe en bootstrap. Fuera de bootstrap,
    toda la app ve frozen dataclasses de core.domain.
    """
    path = _write_toml(tmp_path, _VALID_AGENT_TOML)
    settings = load_settings(path)

    assert hasattr(settings, "agents"), (
        "WyssSettings debe tener el campo 'agents'"
    )
    assert len(settings.agents) == 1, (
        f"Debe haber 1 agente en settings.agents; got: {settings.agents}"
    )
    agent_def = settings.agents[0]
    assert isinstance(agent_def, AgentDefinition), (
        f"settings.agents[0] debe ser AgentDefinition, got: {type(agent_def)}"
    )
    assert not isinstance(agent_def, BaseModel), (
        "settings.agents[0] NO debe ser BaseModel — Pydantic no cruza la frontera de bootstrap"
    )
    # Verificar conversión correcta de campos
    assert agent_def.agent_id == "belgrano"
    assert agent_def.domain == "investigacion"
    assert isinstance(agent_def.kb_ids, frozenset), (
        f"kb_ids debe ser frozenset; got: {type(agent_def.kb_ids)}"
    )
    assert "kb-historia" in agent_def.kb_ids
