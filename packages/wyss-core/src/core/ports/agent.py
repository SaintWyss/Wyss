"""AgentBase — la única ABC. Template method: audit y rechazo D no son salteables.

Vive en core/ports/ (Open Question 1): satisface "14 ports en core/ports/" y es pura
(solo importa domain + ports hermanos). NO crear subclases concretas acá — ConfiguredAgent
llega en Fase 7.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from core.domain import (
    ActorType,
    AgentDefinition,
    AuditEvent,
    AuditEventType,
    Outcome,
    Plan,
    PolicyDecision,
    PolicyViolation,
    Report,
    RiskLevel,
)
from core.ports.audit import AuditPort
from core.ports.execution import Tool
from core.ports.gateway import ModelGatewayPort
from core.ports.knowledge import Retrieval


class AgentBase(ABC):
    """Base de todo agente. El template method `execute` impone audit + rechazo D estructuralmente.

    `audit` es obligatorio sin default (D-08, regla #1: si no está auditado, no está terminado).
    """

    def __init__(
        self,
        definition: AgentDefinition,
        retrieval: Retrieval,
        gateway: ModelGatewayPort,
        tools: Mapping[str, Tool],
        audit: AuditPort,
    ) -> None:
        self._definition = definition
        self._retrieval = retrieval
        self._gateway = gateway
        self._tools = tools
        self._audit = audit

    def execute(self, plan: Plan, decision: PolicyDecision) -> Report:
        """Template method NO salteable.

        El nivel FINAL viaja en `PolicyDecision` (no en `Plan`, que es frozen y solo lleva
        `estimated_risk`). Rechazo por VALOR + fail-closed (CR-01, POL-03): comparar por
        valor/orden (no por identidad de singleton) y rechazar ante tipos corruptos no-enum.
        Una `PolicyDecision` puede llegar deserializada de JSON-RPC (Fase 5) con ints crudos
        que mypy no validó; la guarda `is` era un no-op ante esos valores. Si REJECT, nivel D,
        o tipo corrupto: audita el rechazo y raisea `PolicyViolation` SIN llamar `_run()`
        (T1, belt-and-suspenders).
        """
        agent_id = self._definition.agent_id

        risk = decision.risk_level
        outcome = decision.outcome
        if (
            not isinstance(risk, RiskLevel)
            or not isinstance(outcome, Outcome)
            or outcome == Outcome.REJECT
            or risk >= RiskLevel.D
        ):
            self._audit.log(
                AuditEvent.new(
                    task_id=plan.task_id,
                    actor_type=ActorType.AGENT,
                    actor_id=agent_id,
                    event_type=AuditEventType.POLICY_DECISION,
                    message="plan rechazado por política (nivel D / REJECT / tipo corrupto)",
                    payload={
                        "risk_level": risk.name if isinstance(risk, RiskLevel) else repr(risk),
                        "outcome": (
                            outcome.name if isinstance(outcome, Outcome) else repr(outcome)
                        ),
                        "matched_rules": list(decision.matched_rules),
                        "reasons": list(decision.reasons),
                    },
                )
            )
            level = risk.name if isinstance(risk, RiskLevel) else repr(risk)
            raise PolicyViolation(f"plan {plan.task_id} rechazado: nivel {level}")

        self._audit.log(
            AuditEvent.new(
                task_id=plan.task_id,
                actor_type=ActorType.AGENT,
                actor_id=agent_id,
                event_type=AuditEventType.ACTION_STARTED,
                message="inicio de ejecución del plan",
            )
        )
        try:
            report = self._run(plan)
        except Exception:
            self._audit.log(
                AuditEvent.new(
                    task_id=plan.task_id,
                    actor_type=ActorType.AGENT,
                    actor_id=agent_id,
                    event_type=AuditEventType.TASK_FAILED,
                    message="la ejecución del plan falló",
                )
            )
            raise
        self._audit.log(
            AuditEvent.new(
                task_id=plan.task_id,
                actor_type=ActorType.AGENT,
                actor_id=agent_id,
                event_type=AuditEventType.TASK_COMPLETED,
                message="plan completado",
            )
        )
        return report

    @abstractmethod
    def _run(self, plan: Plan) -> Report: ...
