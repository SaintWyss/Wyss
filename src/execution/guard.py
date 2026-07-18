"""Segunda muralla determinista compartida por los adapters de ejecución."""

from core.domain import (
    Action,
    ActorType,
    AuditEvent,
    AuditEventType,
    ExecutionAuthorization,
    Outcome,
    Plan,
    RiskLevel,
)
from core.ports.audit import AuditPort
from core.ports.execution import PolicyEvaluatorPort


class DeterministicExecutionGuard:
    """Re-evalúa una acción inmediatamente antes del I/O y audita todo bloqueo."""

    def __init__(self, engine: PolicyEvaluatorPort, audit: AuditPort) -> None:
        self._engine = engine
        self._audit = audit

    def authorize(
        self,
        action: Action,
        *,
        adapter: str,
        max_risk: RiskLevel,
    ) -> ExecutionAuthorization:
        decision = self._engine.evaluate(
            Plan(
                task_id="second-wall",
                summary="second-wall check",
                steps=(action,),
                rationale=f"deterministic pre-I/O re-evaluation for {adapter}",
            )
        )
        blocked = decision.outcome is Outcome.REJECT or decision.risk_level > max_risk
        reason = ""
        if decision.outcome is Outcome.REJECT:
            reason = "policy outcome=REJECT"
        elif decision.risk_level > max_risk:
            reason = f"risk_level={decision.risk_level.name} > max_risk={max_risk.name}"

        authorization = ExecutionAuthorization(
            allowed=not blocked,
            risk_level=decision.risk_level,
            reason=reason,
        )
        if blocked:
            self._audit.log(
                AuditEvent.new(
                    actor_type=ActorType.SYSTEM,
                    actor_id=adapter,
                    event_type=AuditEventType.ACTION_COMPLETED,
                    message=f"blocked: second wall — {reason}",
                    payload={
                        "blocked": "second_wall",
                        "action_type": action.type,
                        "level": decision.risk_level.name,
                        "reason": reason,
                        "matched_rules": list(decision.matched_rules),
                    },
                )
            )
        return authorization
