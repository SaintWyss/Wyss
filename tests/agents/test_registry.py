"""Tests del AgentRegistry config-driven (AGENT-02, D-73).

Wave 0 — RED: AgentRegistry aún no existe; los tests fallan por ImportError.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from core.domain import AgentDefinition
from tests.agents.conftest import FakeAudit, FakePlanRunner
from tests.ports.fakes import FakeModelGatewayPort, FakeRetrieval

if TYPE_CHECKING:
    from agents.registry import AgentRegistry


def _make_registry(
    definitions: dict[str, AgentDefinition],
    fake_audit: FakeAudit,
    fake_retrieval: FakeRetrieval,
    fake_plan_runner: FakePlanRunner,
    tmp_path: Path,
) -> AgentRegistry:
    """Factory que instancia AgentRegistry con fakes inyectados."""
    from agents.memory import AgentMemory
    from agents.registry import AgentRegistry

    def scoped_retrieval_factory(agent_id: str) -> FakeRetrieval:
        return fake_retrieval

    def memory_factory(agent_id: str) -> AgentMemory:
        return AgentMemory(agent_id=agent_id, data_dir=tmp_path)

    return AgentRegistry(
        definitions=definitions,
        gateway=FakeModelGatewayPort(),
        tools={},
        audit=fake_audit,
        engine=None,  # type: ignore[arg-type]
        scoped_retrieval_factory=scoped_retrieval_factory,
        memory_factory=memory_factory,
        plan_runner=fake_plan_runner,
    )


def test_registry_instantiates_from_definition(
    sample_definition: AgentDefinition,
    fake_audit: FakeAudit,
    fake_retrieval: FakeRetrieval,
    fake_plan_runner: FakePlanRunner,
    tmp_path: Path,
) -> None:
    """AGENT-02: AgentRegistry instancia ConfiguredAgent desde AgentDefinition sin código nuevo.

    Crear un agente = añadir la definición al dict. El registry lo instancia automáticamente.
    """
    from agents.configured_agent import ConfiguredAgent

    definitions = {sample_definition.agent_id: sample_definition}
    registry = _make_registry(definitions, fake_audit, fake_retrieval, fake_plan_runner, tmp_path)

    agent = registry.get(sample_definition.agent_id)
    assert isinstance(agent, ConfiguredAgent), (
        f"El registry debe retornar una instancia de ConfiguredAgent, got: {type(agent)}"
    )
    assert agent._definition.agent_id == sample_definition.agent_id


def test_get_unknown_raises_keyerror(
    fake_audit: FakeAudit,
    fake_retrieval: FakeRetrieval,
    fake_plan_runner: FakePlanRunner,
    tmp_path: Path,
) -> None:
    """AGENT-02 / D-73: registry.get() de un agente no registrado levanta KeyError."""
    registry = _make_registry({}, fake_audit, fake_retrieval, fake_plan_runner, tmp_path)

    with pytest.raises(KeyError, match="no-existe"):
        registry.get("no-existe")
