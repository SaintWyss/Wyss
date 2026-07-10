"""Daemon asyncio sobre Unix socket JSON-RPC para el orquestador."""

import asyncio
import json
import os
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from core.domain import ActorType, AuditEvent, AuditEventType, Outcome, RiskLevel
from core.domain.plan import Action, ErrorPolicy, Plan, RetryParams
from core.orchestrator.intent import IntentCategory
from core.policy import CognitivePolicyEngine
from core.ports.audit import AuditPort
from core.ports.execution import PlanRunner
from core.ports.orchestrator import OrchestratorPort
from orchestrator.dispatcher import dispatch, ttl_for_risk
from orchestrator.pending_store import PendingStore
from orchestrator.routine_store import Routine, RoutineStore
from orchestrator.scheduler import (
    RoutineScheduler,
    preview_next_fires,
    register_routines,
    validate_schedule,
)
from orchestrator.ttl_reaper import ttl_reaper

JsonDict = dict[str, Any]
JsonHandler = Callable[[Mapping[str, Any]], Awaitable[JsonDict]]


@dataclass(slots=True)
class RunningDaemon:
    """Recursos vivos de un daemon arrancado para tests o `run_daemon`."""

    server: asyncio.AbstractServer
    socket_path: Path
    reaper_task: asyncio.Task[None]
    scheduler: RoutineScheduler

    async def aclose(self) -> None:
        """Cierra server, background task y socket."""
        self.server.close()
        await self.server.wait_closed()
        self.reaper_task.cancel()
        with suppress(asyncio.CancelledError):
            await self.reaper_task
        self.scheduler.shutdown(wait=False)
        self.socket_path.unlink(missing_ok=True)


class DaemonServer:
    """Servidor JSON-RPC inyectado con engine, orquestador, pending store y audit."""

    def __init__(
        self,
        *,
        engine: CognitivePolicyEngine,
        orchestrator: OrchestratorPort,
        pending_store: PendingStore,
        audit: AuditPort,
        routine_store: RoutineStore,
        scheduler: RoutineScheduler,
        runner: PlanRunner | None = None,
    ) -> None:
        self._engine = engine
        self._orchestrator = orchestrator
        self._pending_store = pending_store
        self._audit = audit
        self._routine_store = routine_store
        self._scheduler = scheduler
        self._runner = runner
        self._handlers: dict[str, JsonHandler] = {
            "ask": self._ask,
            "confirm": self._confirm,
            "status": self._status,
            "audit": self._audit_events,
            "routine.add": self._routine_add,
            "routine.list": self._routine_list,
            "routine.pause": self._routine_pause,
            "routine.resume": self._routine_resume,
            "routine.delete": self._routine_delete,
        }

    async def handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Atiende una request JSON-RPC por línea."""
        try:
            raw = await reader.readline()
            try:
                request = json.loads(raw)
            except json.JSONDecodeError:
                response = _error_response(None, -32700, "Parse error")
            else:
                response = await self._dispatch(request)
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _dispatch(self, request: object) -> JsonDict:
        if not isinstance(request, dict):
            return _error_response(None, -32600, "Invalid Request")
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})
        if not isinstance(method, str) or method not in self._handlers:
            return _error_response(req_id, -32601, "Method not found")
        if not isinstance(params, Mapping):
            return _error_response(req_id, -32602, "Invalid params")
        try:
            result = await self._handlers[method](params)
        except Exception as exc:
            return _error_response(req_id, -32000, str(exc))
        return {"jsonrpc": "2.0", "result": result, "id": req_id}

    async def _ask(self, params: Mapping[str, Any]) -> JsonDict:
        instruction = str(params.get("instruction", "")).strip()
        if not instruction:
            raise ValueError("instruction requerido")
        self._audit.log(
            AuditEvent.new(
                actor_type=ActorType.OWNER,
                actor_id="owner",
                event_type=AuditEventType.COMMAND_RECEIVED,
                message=instruction,
            )
        )
        if not await self._safe_health_check():
            return {
                "outcome": "degraded",
                "message": "Orquestador Hermes no disponible.",
                "fallback_available": True,
            }

        intent = await self._orchestrator.classify_intent(instruction)
        if (
            intent.category == IntentCategory.AMBIGUOUS_REQUEST
            or intent.clarification_needed
        ):
            return {
                "outcome": "clarification_needed",
                "message": "Necesito una instrucción más específica.",
                "category": intent.category.value,
            }
        plan = await self._orchestrator.draft_plan(instruction, intent)
        self._audit.log(
            AuditEvent.new(
                task_id=plan.task_id,
                actor_type=ActorType.SYSTEM,
                actor_id="daemon",
                event_type=AuditEventType.PLAN_CREATED,
                message="plan creado por orquestador",
                payload={"summary": plan.summary, "steps": len(plan.steps)},
            )
        )
        decision = self._engine.evaluate(plan)
        dispatched = await dispatch(
            plan,
            decision,
            pending_store=self._pending_store,
            audit=self._audit,
            ttl_for=ttl_for_risk,
        )
        if dispatched.get("outcome") == "queued" and self._runner is not None:
            executed = await self._execute_plan(plan)
            return {"outcome": "executed", **executed}
        return dispatched

    async def _confirm(self, params: Mapping[str, Any]) -> JsonDict:
        pending_id = str(params.get("pending_id", "")).strip()
        response = str(params.get("response", "")).strip()
        if not pending_id:
            raise ValueError("pending_id requerido")
        proposal = self._pending_store.load(pending_id)
        if proposal is None or proposal.status != "pending":
            return {"accepted": False, "execution_id": None, "reason": "pending no encontrado"}
        # Defensa en profundidad: el ttl_reaper corre cada N s, así que una propuesta
        # puede estar vencida por tiempo pero seguir status='pending' hasta la próxima
        # barrida. No la ejecutamos: el TTL es un límite duro, no una sugerencia.
        if _is_expired(proposal.expires_at):
            return {"accepted": False, "execution_id": None, "reason": "propuesta expirada"}

        # Re-evaluación ANTES de validar la palabra: el pending store no es la
        # autoridad, la política sí. Si el plan es D ahora, ni la palabra correcta
        # lo ejecuta; si el riesgo subió (p.ej. B→C), la palabra exigida es la del
        # nivel NUEVO, no la del nivel guardado.
        plan = _plan_from_json(proposal.plan_json)
        fresh_decision = self._engine.evaluate(plan)
        if (
            fresh_decision.outcome == Outcome.REJECT
            or fresh_decision.risk_level >= RiskLevel.D
        ):
            await dispatch(
                plan,
                fresh_decision,
                pending_store=self._pending_store,
                audit=self._audit,
            )
            return {
                "accepted": False,
                "execution_id": None,
                "reason": "plan rechazado por política al confirmar",
            }

        stored_level = RiskLevel[proposal.risk_level]
        effective_level = max(stored_level, fresh_decision.risk_level)
        accepted = _confirmation_matches(effective_level, response)
        self._audit.log(
            AuditEvent.new(
                task_id=proposal.task_id,
                actor_type=ActorType.OWNER,
                actor_id="owner",
                event_type=AuditEventType.CONFIRMATION_ANSWERED,
                message="confirmación respondida",
                payload={
                    "pending_id": pending_id,
                    "accepted": accepted,
                    "risk_level": effective_level.name,
                },
            )
        )
        if not accepted:
            if fresh_decision.risk_level > stored_level:
                return {
                    "accepted": False,
                    "execution_id": None,
                    "reason": (
                        f"el riesgo re-evaluado subió a {effective_level.name}: "
                        "se requiere la confirmación de ese nivel"
                    ),
                }
            return {"accepted": False, "execution_id": None}

        resolved = self._pending_store.resolve(pending_id, "owner")
        if resolved is None:
            return {"accepted": False, "execution_id": None, "reason": "pending stale"}
        if self._runner is None:
            execution_id = f"exec-{resolved.task_id}-{pending_id[:12]}"
            return {"accepted": True, "execution_id": execution_id}
        executed = await self._execute_plan(plan)
        return {"accepted": True, **executed}

    async def _execute_plan(self, plan: Plan) -> JsonDict:
        """Ejecuta un plan ya autorizado por política y audita el resultado terminal."""
        assert self._runner is not None
        execution_id = f"exec-{plan.task_id}-{uuid4().hex[:12]}"
        result = await self._runner.run(plan)
        success = bool(getattr(result, "success", False))
        detail = str(getattr(result, "detail", ""))
        raw_outputs = getattr(result, "outputs", ())
        outputs = [str(item) for item in raw_outputs] if raw_outputs else []
        self._audit.log(
            AuditEvent.new(
                task_id=plan.task_id,
                actor_type=ActorType.SYSTEM,
                actor_id="executor",
                event_type=(
                    AuditEventType.TASK_COMPLETED if success else AuditEventType.TASK_FAILED
                ),
                message=detail or ("plan ejecutado" if success else "plan falló"),
                payload={"execution_id": execution_id, "success": success},
            )
        )
        return {
            "execution_id": execution_id,
            "success": success,
            "detail": detail,
            "outputs": outputs,
        }

    async def _status(self, params: Mapping[str, Any]) -> JsonDict:
        del params
        return {
            "daemon_version": "05-04",
            "hermes_up": await self._safe_health_check(),
            "pending_count": len(self._pending_store.load_pending()),
        }

    async def _audit_events(self, params: Mapping[str, Any]) -> JsonDict:
        del params
        return {"events": []}

    async def _routine_add(self, params: Mapping[str, Any]) -> JsonDict:
        name = str(params.get("name", "")).strip()
        schedule_kind = str(params.get("schedule_kind", "")).strip()
        schedule_expr = str(params.get("schedule_expr", "")).strip()
        plan_json = str(params.get("plan_json", "")).strip()
        catch_up = bool(params.get("catch_up", True))
        if not name:
            raise ValueError("name requerido")
        if not plan_json:
            raise ValueError("plan_json requerido")
        validate_schedule(schedule_kind, schedule_expr)
        _plan_from_json(plan_json)
        routine_id = self._routine_store.add(
            name,
            schedule_kind,
            schedule_expr,
            plan_json,
            catch_up=catch_up,
        )
        routine = self._routine_store.get(routine_id)
        if routine is None:
            raise RuntimeError("rutina persistida no encontrada")
        self._scheduler.add_routine(routine)
        self._audit.log(
            AuditEvent.new(
                task_id=f"routine-{routine_id}",
                actor_type=ActorType.OWNER,
                actor_id="owner",
                event_type=AuditEventType.COMMAND_RECEIVED,
                message="routine.add",
                payload={
                    "routine_id": routine_id,
                    "routine_name": name,
                    "schedule_kind": schedule_kind,
                    "schedule_expr": schedule_expr,
                    "catch_up": catch_up,
                },
            )
        )
        preview = preview_next_fires(schedule_kind, schedule_expr)
        return {"routine_id": routine_id, "preview": [item.isoformat() for item in preview]}

    async def _routine_list(self, params: Mapping[str, Any]) -> JsonDict:
        del params
        routines = [_routine_to_json(routine) for routine in self._routine_store.list_all()]
        return {"routines": routines}

    async def _routine_pause(self, params: Mapping[str, Any]) -> JsonDict:
        routine_id = _routine_id_param(params)
        ok = self._routine_store.pause(routine_id)
        if ok:
            self._scheduler.pause_job(routine_id)
        return {"ok": ok}

    async def _routine_resume(self, params: Mapping[str, Any]) -> JsonDict:
        routine_id = _routine_id_param(params)
        ok = self._routine_store.resume(routine_id)
        if ok:
            routine = self._routine_store.get(routine_id)
            if routine is not None:
                self._scheduler.add_routine(routine)
            self._scheduler.resume_job(routine_id)
        return {"ok": ok}

    async def _routine_delete(self, params: Mapping[str, Any]) -> JsonDict:
        routine_id = _routine_id_param(params)
        ok = self._routine_store.delete(routine_id)
        if ok:
            self._scheduler.remove_routine(routine_id)
        return {"ok": ok}

    async def _safe_health_check(self) -> bool:
        try:
            return await self._orchestrator.health_check()
        except Exception:
            return False


async def _cleanup_stale_socket(path: Path) -> None:
    """Elimina socket huérfano; si responde, falla porque ya hay daemon."""
    if not path.exists():
        return
    try:
        _reader, writer = await asyncio.open_unix_connection(str(path))
    except (ConnectionRefusedError, FileNotFoundError):
        path.unlink(missing_ok=True)
        return
    writer.close()
    await writer.wait_closed()
    raise RuntimeError(f"daemon ya corriendo en {path}")


async def start_daemon(
    socket_path: Path,
    *,
    engine: CognitivePolicyEngine,
    orchestrator: OrchestratorPort,
    pending_store: PendingStore,
    audit: AuditPort,
    routine_store: RoutineStore,
    scheduler: RoutineScheduler,
    runner: PlanRunner | None = None,
    reaper_interval_s: float = 30.0,
) -> RunningDaemon:
    """Arranca el Unix socket server y devuelve recursos cerrables."""
    await _cleanup_stale_socket(socket_path)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    daemon = DaemonServer(
        engine=engine,
        orchestrator=orchestrator,
        pending_store=pending_store,
        audit=audit,
        routine_store=routine_store,
        scheduler=scheduler,
        runner=runner,
    )
    scheduler.set_on_queued(daemon._execute_plan if runner is not None else None)
    server = await asyncio.start_unix_server(daemon.handle, str(socket_path))
    os.chmod(socket_path, 0o600)
    reaper_task = asyncio.create_task(
        ttl_reaper(pending_store, audit, interval_s=reaper_interval_s)
    )
    await register_routines(
        scheduler,
        routine_store,
        engine=engine,
        pending_store=pending_store,
        audit=audit,
        on_queued=daemon._execute_plan if runner is not None else None,
    )
    scheduler.start()
    return RunningDaemon(
        server=server,
        socket_path=socket_path,
        reaper_task=reaper_task,
        scheduler=scheduler,
    )


async def run_daemon(
    socket_path: Path,
    *,
    engine: CognitivePolicyEngine,
    orchestrator: OrchestratorPort,
    pending_store: PendingStore,
    audit: AuditPort,
    routine_store: RoutineStore,
    scheduler: RoutineScheduler,
    runner: PlanRunner | None = None,
    reaper_interval_s: float = 30.0,
) -> None:
    """Corre el daemon hasta cancelación/señal y limpia socket al salir."""
    running = await start_daemon(
        socket_path,
        engine=engine,
        orchestrator=orchestrator,
        pending_store=pending_store,
        audit=audit,
        routine_store=routine_store,
        scheduler=scheduler,
        runner=runner,
        reaper_interval_s=reaper_interval_s,
    )
    try:
        await running.server.serve_forever()
    finally:
        await running.aclose()


def _error_response(req_id: object, code: int, message: str) -> JsonDict:
    return {
        "jsonrpc": "2.0",
        "error": {"code": code, "message": message},
        "id": req_id,
    }


def _is_expired(expires_at: str) -> bool:
    """True si `expires_at` (ISO 8601) ya pasó. Un timestamp corrupto se trata como
    vencido (fail-closed): mejor rechazar una confirmación que ejecutar sobre basura."""
    from datetime import UTC, datetime

    try:
        return datetime.fromisoformat(expires_at) < datetime.now(UTC)
    except ValueError:
        return True


def _confirmation_matches(level: RiskLevel, response: str) -> bool:
    if level == RiskLevel.B:
        return response.lower() == "s"
    if level == RiskLevel.C:
        return response == "CONFIRMAR"
    return False


def _routine_id_param(params: Mapping[str, Any]) -> str:
    routine_id = str(params.get("routine_id", "")).strip()
    if not routine_id:
        raise ValueError("routine_id requerido")
    return routine_id


def _routine_to_json(routine: Routine) -> JsonDict:
    return {
        "id": routine.id,
        "name": routine.name,
        "schedule": {
            "kind": routine.schedule_kind,
            "expr": routine.schedule_expr,
        },
        "status": routine.status,
        "catch_up": routine.catch_up,
        "last_fired_at": routine.last_fired_at,
        "last_outcome": routine.last_outcome,
    }


def _plan_from_json(raw: str) -> Plan:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("plan_json inválido")
    return Plan(
        task_id=str(data["task_id"]),
        summary=str(data["summary"]),
        steps=tuple(_action_from_dict(item) for item in data.get("steps", [])),
        rationale=str(data["rationale"]),
        estimated_risk=(
            RiskLevel[str(data["estimated_risk"])] if data.get("estimated_risk") else None
        ),
    )


def _action_from_dict(data: object) -> Action:
    if not isinstance(data, dict):
        raise ValueError("action inválida")
    retry_raw = data.get("retry_params")
    retry_params = None
    if isinstance(retry_raw, dict):
        retry_params = RetryParams(
            max_attempts=int(retry_raw.get("max_attempts", 3)),
            backoff_base_s=float(retry_raw.get("backoff_base_s", 1.0)),
            backoff_max_s=float(retry_raw.get("backoff_max_s", 60.0)),
        )
    params = data.get("parameters", {})
    if not isinstance(params, Mapping):
        params = {}
    return Action(
        type=str(data["type"]),
        target=str(data["target"]),
        parameters=dict(params),
        on_error=ErrorPolicy(str(data.get("on_error", ErrorPolicy.ABORT.value))),
        retry_params=retry_params,
    )
