"""Tool adapter para escribir memoria owner-instruida."""

from core.domain.audit import ActorType, AuditEvent, AuditEventType
from core.domain.execution import ToolResult, Verification
from core.domain.plan import Action
from core.domain.risk import RiskLevel
from core.ports.audit import AuditPort
from memory.store import MemoryStore


class MemoryTool:
    """Adapter de memoria para writes gateados por politica."""

    def __init__(self, *, store: MemoryStore, audit: AuditPort) -> None:
        self._store = store
        self._audit = audit

    @property
    def name(self) -> str:
        return "memory"

    @property
    def max_risk(self) -> RiskLevel:
        return RiskLevel.B

    def describe(self, action: Action) -> str:
        raw_value = action.parameters.get("value", "")
        value = raw_value if isinstance(raw_value, str) else ""
        preview = _truncate(value.strip(), 80)
        return f"recordar en {action.target}: {preview}"

    async def execute(self, action: Action) -> ToolResult:
        """Ejecuta una action de memoria y convierte errores esperables en ToolResult."""
        fact_id: str | None = None
        if action.type != "memory.remember":
            result = ToolResult(
                success=False,
                detail=f"unsupported action type: {action.type!r}",
                payload={"action_type": action.type},
            )
            self._audit_result(action, fact_id, result)
            return result

        raw_value = action.parameters.get("value", "")
        if not isinstance(raw_value, str):
            result = ToolResult(
                success=False,
                detail="valor invalido, nada que recordar",
                payload={"category": action.target},
            )
            self._audit_result(action, fact_id, result)
            return result

        value = raw_value.strip()
        if not value:
            result = ToolResult(
                success=False,
                detail="valor vacio, nada que recordar",
                payload={"category": action.target},
            )
            self._audit_result(action, fact_id, result)
            return result

        try:
            fact_id = self._store.remember(
                category=action.target,
                value=value,
                tier="owner",
                source="owner",
            )
        except Exception as exc:
            result = ToolResult(
                success=False,
                detail=f"no se pudo recordar: {exc}",
                payload={"category": action.target},
            )
            self._audit_result(action, fact_id, result)
            return result

        result = ToolResult(
            success=True,
            detail="memoria recordada",
            payload={
                "fact_id": fact_id,
                "category": action.target,
                "output": f"Recordado: {value}",
            },
        )
        self._audit_result(action, fact_id, result)
        return result

    async def verify(self, action: Action, result: ToolResult) -> Verification:
        """La verificacion del adapter refleja el resultado del store."""
        return Verification(passed=result.success, detail=result.detail)

    def _audit_result(self, action: Action, fact_id: str | None, result: ToolResult) -> None:
        payload: dict[str, object] = {
            "action_type": action.type,
            "category": action.target,
            "success": result.success,
        }
        if fact_id is not None:
            payload["fact_id"] = fact_id
        self._audit.log(
            AuditEvent.new(
                actor_type=ActorType.SYSTEM,
                actor_id=self.name,
                event_type=AuditEventType.ACTION_COMPLETED,
                message=f"memory action completed: {action.type}",
                payload=payload,
            )
        )


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1]}..."
