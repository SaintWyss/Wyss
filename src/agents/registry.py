"""Registry config-driven de agentes (AGENT-02 / D-73)."""

from collections.abc import Callable, Mapping

from agents.configured_agent import ConfiguredAgent
from agents.memory import AgentMemory
from core.domain.agent import AgentDefinition
from core.policy.engine import CognitivePolicyEngine
from core.ports.audit import AuditPort
from core.ports.execution import PlanRunner, Tool
from core.ports.gateway import ModelGatewayPort
from core.ports.knowledge import Retrieval


class AgentRegistry:
    """Materializa definiciones de config en instancias de `ConfiguredAgent`."""

    def __init__(
        self,
        definitions: Mapping[str, AgentDefinition],
        gateway: ModelGatewayPort,
        tools: Mapping[str, Tool],
        audit: AuditPort,
        engine: CognitivePolicyEngine,
        plan_runner: PlanRunner,
        scoped_retrieval_factory: Callable[[str], Retrieval],
        memory_factory: Callable[[str], AgentMemory],
    ) -> None:
        self._agents: dict[str, ConfiguredAgent] = {}
        for agent_id, defn in definitions.items():
            self._agents[agent_id] = ConfiguredAgent(
                definition=defn,
                retrieval=scoped_retrieval_factory(agent_id),
                gateway=gateway,
                tools=tools,
                audit=audit,
                engine=engine,
                memory=memory_factory(agent_id),
                plan_runner=plan_runner,
            )

    def get(self, agent_id: str) -> ConfiguredAgent:
        """Devuelve el agente registrado o falla con mensaje legible."""
        if agent_id not in self._agents:
            raise KeyError(f"agente '{agent_id}' no registrado")
        return self._agents[agent_id]
