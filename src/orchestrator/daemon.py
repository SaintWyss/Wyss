"""Daemon asyncio sobre Unix socket JSON-RPC para el orquestador."""

import asyncio
import json
import os
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.domain import ActorType, AuditEvent, AuditEventType, Outcome, RiskLevel
from core.domain.plan import Action, ErrorPolicy, Plan, RetryParams
from core.domain.policy import PolicyDecision
from core.orchestrator.intent import IntentCategory
from core.policy import CognitivePolicyEngine
from core.ports.audit import AuditPort
from core.ports.orchestrator import OrchestratorPort
from orchestrator.dispatcher import dispatch, ttl_for_risk
from orchestrator.pending_store import PendingProposal, PendingStore
from orchestrator.ttl_reaper import ttl_reaper

JsonDict = dict[str, Any]
JsonHandler = Callable[[Mapping[str, Any]], Awaitable[JsonDict]]


@dataclass(slots=True)
class RunningDaemon:
    """Recursos vivos de un daemon arrancado para tests o `run_daemon`."""

    server: asyncio.AbstractServer
    socket_path: Path
    reaper_task: asyncio.Task[None]

    async def aclose(self) -> None:
        """Cierra server, background task y socket."""
        self.server.close()
        await self.server.wait_closed()
        self.reaper_task.cancel()
        with suppress(asyncio.CancelledError):
            await self.reaper_task
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
    ) -> None:
        self._engine = engine
        self._orchestrator = orchestrator
        self._pending_store = pending_store
        self._audit = audit
        self._handlers: dict[str, JsonHandler] = {
            "ask": self._ask,
            "confirm": self._confirm,
            "status": self._status,
            "audit": self._audit_events,
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
        return await dispatch(
            plan,
            decision,
            pending_store=self._pending_store,
            audit=self._audit,
            ttl_for=ttl_for_risk,
        )

    async def _confirm(self, params: Mapping[str, Any]) -> JsonDict:
        pending_id = str(params.get("pending_id", "")).strip()
        response = str(params.get("response", "")).strip()
        if not pending_id:
            raise ValueError("pending_id requerido")
        proposal = self._pending_store.load(pending_id)
        if proposal is None or proposal.status != "pending":
            return {"accepted": False, "execution_id": None, "reason": "pending no encontrado"}

        decision = _decision_from_proposal(proposal)
        accepted = _confirmation_matches(decision, response)
        self._audit.log(
            AuditEvent.new(
                task_id=proposal.task_id,
                actor_type=ActorType.OWNER,
                actor_id="owner",
                event_type=AuditEventType.CONFIRMATION_ANSWERED,
                message="confirmación respondida",
                payload={"pending_id": pending_id, "accepted": accepted},
            )
        )
        if not accepted:
            return {"accepted": False, "execution_id": None}

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

        resolved = self._pending_store.resolve(pending_id, "owner")
        if resolved is None:
            return {"accepted": False, "execution_id": None, "reason": "pending stale"}
        execution_id = f"exec-{resolved.task_id}-{pending_id[:12]}"
        return {"accepted": True, "execution_id": execution_id}

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
    )
    server = await asyncio.start_unix_server(daemon.handle, str(socket_path))
    os.chmod(socket_path, 0o600)
    reaper_task = asyncio.create_task(
        ttl_reaper(pending_store, audit, interval_s=reaper_interval_s)
    )
    return RunningDaemon(server=server, socket_path=socket_path, reaper_task=reaper_task)


async def run_daemon(
    socket_path: Path,
    *,
    engine: CognitivePolicyEngine,
    orchestrator: OrchestratorPort,
    pending_store: PendingStore,
    audit: AuditPort,
    reaper_interval_s: float = 30.0,
) -> None:
    """Corre el daemon hasta cancelación/señal y limpia socket al salir."""
    running = await start_daemon(
        socket_path,
        engine=engine,
        orchestrator=orchestrator,
        pending_store=pending_store,
        audit=audit,
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


def _decision_from_proposal(proposal: PendingProposal) -> PolicyDecision:
    return PolicyDecision(
        task_id=proposal.task_id,
        risk_level=RiskLevel[proposal.risk_level],
        outcome=Outcome[proposal.outcome],
    )


def _confirmation_matches(decision: PolicyDecision, response: str) -> bool:
    if decision.risk_level == RiskLevel.B:
        return response.lower() == "s"
    if decision.risk_level == RiskLevel.C:
        return response == "CONFIRMAR"
    return False


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
