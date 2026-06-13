"""Puerto del cerebro de orquestación detrás del daemon."""

from typing import Protocol

from core.domain.plan import Plan
from core.orchestrator.intent import IntentClassification


class OrchestratorPort(Protocol):
    """Contrato vertical del daemon hacia Hermes; los agentes no lo invocan.

    El port clasifica intención y propone Planes estructurados. El nivel A/B/C/D
    siempre lo asigna `CognitivePolicyEngine.evaluate(plan)`, nunca este port.
    """

    async def classify_intent(self, instruction: str) -> IntentClassification: ...

    async def draft_plan(self, instruction: str, intent: IntentClassification) -> Plan: ...

    async def health_check(self) -> bool: ...
