"""Daemon asyncio sobre Unix socket JSON-RPC para el orquestador."""

import asyncio
import hashlib
import json
import os
import socket
import struct
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from core.domain import (
    ActorType,
    AuditEvent,
    AuditEventType,
    AuditQuery,
    ClaimStatus,
    IdempotencyClaim,
    Outcome,
    RiskLevel,
)
from core.domain.home import JsonValue
from core.domain.memory import MemoryFact
from core.domain.plan import Action, ErrorPolicy, Plan, RetryParams
from core.domain.policy import PolicyDecision
from core.domain.risk import outcome_for
from core.orchestrator.intent import IntentCategory
from core.policy import CognitivePolicyEngine
from core.ports.audit import AuditPort, AuditQueryPort
from core.ports.execution import PlanRunner
from core.ports.home import IdempotencyPort
from core.ports.ledger import LedgerPort
from core.ports.memory import MemoryAdmin
from core.ports.orchestrator import OrchestratorPort
from orchestrator.digest import compose_digest, write_digest_file
from orchestrator.dispatcher import dispatch, ttl_for_risk
from orchestrator.home_plan_preview import home_action_step
from orchestrator.pending_store import PendingStore
from orchestrator.routine_store import Routine, RoutineStore
from orchestrator.scheduler import (
    ARG_TZ,
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
    home_server: asyncio.AbstractServer | None = None
    home_socket_path: Path | None = None

    async def aclose(self) -> None:
        """Cierra server, background task y socket."""
        self.server.close()
        await self.server.wait_closed()
        if self.home_server is not None:
            self.home_server.close()
            await self.home_server.wait_closed()
        self.reaper_task.cancel()
        with suppress(asyncio.CancelledError):
            await self.reaper_task
        self.scheduler.shutdown(wait=False)
        self.socket_path.unlink(missing_ok=True)
        if self.home_socket_path is not None:
            self.home_socket_path.unlink(missing_ok=True)


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
        memory_store: MemoryAdmin,
        ledger: LedgerPort,
        scheduler: RoutineScheduler,
        runner: PlanRunner | None = None,
        audit_query: AuditQueryPort | None = None,
        idempotency: IdempotencyPort | None = None,
        home_rate_limit_per_second: int = 50,
        home_peer_uid: int | None = None,
    ) -> None:
        if home_rate_limit_per_second < 1:
            raise ValueError("home_rate_limit_per_second debe ser positivo")
        self._engine = engine
        self._orchestrator = orchestrator
        self._pending_store = pending_store
        self._audit = audit
        self._routine_store = routine_store
        self._memory_store = memory_store
        self._ledger = ledger
        self._scheduler = scheduler
        self._runner = runner
        self._audit_query = audit_query
        self._idempotency = idempotency
        self._home_rate_limit = home_rate_limit_per_second
        self._home_peer_uid = home_peer_uid
        self._home_request_times: deque[float] = deque()
        self._handlers: dict[str, JsonHandler] = {
            "ask": self._ask,
            "intake.propose": self._intake_propose,
            "confirm": self._confirm,
            "home.intent": self._home_intent,
            "home.plan.answer": self._home_plan_answer,
            "status": self._status,
            "audit": self._audit_events,
            "routine.add": self._routine_add,
            "routine.list": self._routine_list,
            "routine.pause": self._routine_pause,
            "routine.resume": self._routine_resume,
            "routine.delete": self._routine_delete,
            "memory.list": self._memory_list,
            "memory.edit": self._memory_edit,
            "memory.forget": self._memory_forget,
            "digest.today": self._digest_today,
        }

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Atiende una request JSON-RPC por línea."""
        await self._handle_transport(reader, writer, home_only=False)

    async def handle_home(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Atiende sólo el contrato Home y deriva la identidad del socket dedicado."""
        if self._home_peer_uid is not None and _peer_uid(writer) != self._home_peer_uid:
            await _write_closed_error(writer, -32001, "Home peer no autorizado")
            return
        await self._handle_transport(reader, writer, home_only=True)

    async def _handle_transport(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        home_only: bool,
    ) -> None:
        try:
            try:
                raw = await reader.readline()
            except ValueError:
                response = _error_response(None, -32600, "Request demasiado grande")
            else:
                try:
                    request = json.loads(raw)
                except (json.JSONDecodeError, RecursionError):
                    response = _error_response(None, -32700, "Parse error")
                else:
                    response = await self._dispatch(request, home_only=home_only)
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def _dispatch(self, request: object, *, home_only: bool = False) -> JsonDict:
        if not isinstance(request, dict):
            return _error_response(None, -32600, "Invalid Request")
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})
        if home_only and not self._allow_home_request():
            return _error_response(req_id, -32029, "rate limit excedido")
        if home_only and method not in {"home.intent", "home.plan.answer", "status"}:
            return _error_response(req_id, -32601, "Method not found")
        if not isinstance(method, str) or method not in self._handlers:
            return _error_response(req_id, -32601, "Method not found")
        if not isinstance(params, Mapping):
            return _error_response(req_id, -32602, "Invalid params")
        if home_only and _json_depth(params) > 16:
            return _error_response(req_id, -32602, "payload demasiado profundo")
        if home_only and method in {"home.intent", "home.plan.answer"}:
            params = {**params, "source": "home-edge"}
        try:
            result = await self._handlers[method](params)
        except Exception as exc:
            if home_only:
                self._audit.log(
                    AuditEvent.new(
                        actor_type=ActorType.SYSTEM,
                        actor_id="home-rpc",
                        event_type=AuditEventType.TASK_FAILED,
                        message=f"request Home falló ({type(exc).__name__})",
                        payload={"method": method},
                    )
                )
                return _error_response(req_id, -32000, "Home request failed")
            return _error_response(req_id, -32000, str(exc))
        return {"jsonrpc": "2.0", "result": result, "id": req_id}

    def _allow_home_request(self) -> bool:
        now = time.monotonic()
        threshold = now - 1.0
        while self._home_request_times and self._home_request_times[0] <= threshold:
            self._home_request_times.popleft()
        if len(self._home_request_times) >= self._home_rate_limit:
            return False
        self._home_request_times.append(now)
        return True

    async def _ask(self, params: Mapping[str, Any]) -> JsonDict:
        instruction = str(params.get("instruction", "")).strip()
        if not instruction:
            raise ValueError("instruction requerido")
        return await self._process_instruction(instruction, actor_id="owner")

    async def _process_instruction(self, instruction: str, *, actor_id: str) -> JsonDict:
        self._audit.log(
            AuditEvent.new(
                actor_type=ActorType.OWNER,
                actor_id=actor_id,
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
        if intent.category == IntentCategory.AMBIGUOUS_REQUEST or intent.clarification_needed:
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
        if dispatched.get("outcome") == "pending":
            pending = self._pending_store.load(str(dispatched["pending_id"]))
            if pending is None:
                raise RuntimeError("pending recién creado no disponible")
            dispatched.update(
                {
                    "risk": decision.risk_level.name,
                    "summary": plan.summary,
                    "steps": [home_action_step(action) for action in plan.steps],
                    "expires_in_ms": min(ttl_for_risk(decision.risk_level) * 1000, 300_000),
                    "revision": pending.revision,
                }
            )
        return dispatched

    async def _home_intent(self, params: Mapping[str, Any]) -> JsonDict:
        self._require_home_keys(
            params,
            {"message_id", "request_id", "source", "text", "input"},
        )
        message_id = _bounded_string(params.get("message_id"), name="message_id", maximum=128)
        request_id = _bounded_string(params.get("request_id"), name="request_id", maximum=128)
        source = _bounded_string(params.get("source"), name="source", maximum=128)
        text = _bounded_string(params.get("text"), name="text", maximum=1000)
        input_kind = _bounded_string(params.get("input"), name="input", maximum=16)
        if input_kind not in {"text", "voice"}:
            raise ValueError("input debe ser text o voice")
        fingerprint = _fingerprint(
            {
                "request_id": request_id,
                "source": source,
                "text": text,
                "input": input_kind,
            }
        )
        claim = self._claim_idempotency(f"home.intent:{source}:{message_id}", fingerprint)
        if claim.status is ClaimStatus.REPLAY:
            assert claim.response is not None
            return dict(claim.response)
        if claim.status is ClaimStatus.CONFLICT:
            return {"outcome": "conflict", "request_id": request_id}
        if claim.status is ClaimStatus.IN_PROGRESS:
            return {"outcome": "in_progress", "request_id": request_id}

        try:
            result = await self._process_instruction(text, actor_id=source)
        except Exception:
            result = {
                "outcome": "failed",
                "status": "failed",
                "message": "Wyss no pudo procesar la intención.",
            }
        result.update({"request_id": request_id, "source": "wyss:authority"})
        self._complete_idempotency(f"home.intent:{source}:{message_id}", result)
        return result

    async def _home_plan_answer(self, params: Mapping[str, Any]) -> JsonDict:
        self._require_home_keys(
            params,
            {
                "message_id",
                "plan_id",
                "decision",
                "confirmation",
                "expected_revision",
                "source",
            },
        )
        message_id = _bounded_string(params.get("message_id"), name="message_id", maximum=128)
        plan_id = _bounded_string(params.get("plan_id"), name="plan_id", maximum=128)
        decision = _bounded_string(params.get("decision"), name="decision", maximum=16)
        confirmation = _optional_string(params.get("confirmation"), name="confirmation", maximum=32)
        source = _bounded_string(params.get("source"), name="source", maximum=128)
        expected_revision = _bounded_int(
            params.get("expected_revision"),
            name="expected_revision",
            minimum=1,
            maximum=2_147_483_647,
        )
        if decision not in {"approve", "reject"}:
            raise ValueError("decision debe ser approve o reject")
        fingerprint = _fingerprint(
            {
                "plan_id": plan_id,
                "decision": decision,
                "confirmation": confirmation,
                "expected_revision": expected_revision,
                "source": source,
            }
        )
        key = f"home.plan.answer:{source}:{message_id}"
        claim = self._claim_idempotency(key, fingerprint)
        if claim.status is ClaimStatus.REPLAY:
            assert claim.response is not None
            return dict(claim.response)
        if claim.status is ClaimStatus.CONFLICT:
            return {"outcome": "conflict", "plan_id": plan_id}
        if claim.status is ClaimStatus.IN_PROGRESS:
            return {"outcome": "in_progress", "plan_id": plan_id}

        if decision == "reject":
            result = await self._reject_pending(
                plan_id,
                actor_id=source,
                expected_revision=expected_revision,
            )
        else:
            confirmed = await self._confirm_pending(
                plan_id,
                confirmation,
                actor_id=source,
                expected_revision=expected_revision,
            )
            result = _home_confirmation_result(plan_id, confirmed)
        self._complete_idempotency(key, result)
        return result

    async def _reject_pending(
        self,
        pending_id: str,
        *,
        actor_id: str,
        expected_revision: int,
    ) -> JsonDict:
        proposal = self._pending_store.load(pending_id)
        if proposal is None or proposal.status != "pending":
            return {
                "outcome": "already_resolved",
                "plan_id": pending_id,
                "revision": proposal.revision if proposal is not None else None,
                "policy_reevaluated": False,
            }
        if proposal.revision != expected_revision:
            return {
                "outcome": "conflict",
                "plan_id": pending_id,
                "revision": proposal.revision,
                "policy_reevaluated": False,
            }
        if _is_expired(proposal.expires_at):
            return {
                "outcome": "expired",
                "plan_id": pending_id,
                "policy_reevaluated": False,
            }
        plan = _plan_from_json(proposal.plan_json)
        fresh_decision = self._engine.evaluate(plan)
        resolved = self._pending_store.resolve(
            pending_id,
            actor_id,
            status="rejected",
            expected_revision=expected_revision,
        )
        if resolved is None:
            current = self._pending_store.load(pending_id)
            return {
                "outcome": "already_resolved",
                "plan_id": pending_id,
                "revision": current.revision if current is not None else None,
                "policy_reevaluated": True,
            }
        self._audit.log(
            AuditEvent.new(
                task_id=proposal.task_id,
                actor_type=ActorType.OWNER,
                actor_id=actor_id,
                event_type=AuditEventType.CONFIRMATION_ANSWERED,
                message="plan rechazado por owner",
                payload={
                    "pending_id": pending_id,
                    "accepted": False,
                    "risk_level": fresh_decision.risk_level.name,
                    "source": actor_id,
                },
            )
        )
        return {
            "outcome": "resolved",
            "plan_id": pending_id,
            "accepted": False,
            "status": "verified",
            "revision": resolved.revision,
            "message": "Plan rechazado.",
            "policy_reevaluated": True,
        }

    @staticmethod
    def _require_home_keys(params: Mapping[str, Any], allowed: set[str]) -> None:
        extras = set(params) - allowed
        if extras:
            raise ValueError(f"campos no permitidos: {', '.join(sorted(extras))}")

    def _claim_idempotency(self, key: str, fingerprint: str) -> IdempotencyClaim:
        if self._idempotency is None:
            raise RuntimeError("idempotencia Home no configurada")
        return self._idempotency.claim(key, fingerprint)

    def _complete_idempotency(self, key: str, response: Mapping[str, Any]) -> None:
        assert self._idempotency is not None
        self._idempotency.complete(key, _json_mapping(response))

    async def _intake_propose(self, params: Mapping[str, Any]) -> JsonDict:
        instruction = str(params.get("instruction", "")).strip()
        if not instruction:
            raise ValueError("instruction requerido")
        self._audit.log(
            AuditEvent.new(
                actor_type=ActorType.SYSTEM,
                actor_id="intake",
                event_type=AuditEventType.COMMAND_RECEIVED,
                message=f"[intake externo] {instruction}",
            )
        )
        if not await self._safe_health_check():
            return {
                "outcome": "degraded",
                "message": "Orquestador Hermes no disponible.",
                "fallback_available": True,
            }

        intent = await self._orchestrator.classify_intent(instruction)
        if intent.category == IntentCategory.AMBIGUOUS_REQUEST or intent.clarification_needed:
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
        decision = _floor_intake_decision(self._engine.evaluate(plan))
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
        return await self._confirm_pending(pending_id, response, actor_id="owner")

    async def _confirm_pending(
        self,
        pending_id: str,
        response: str,
        *,
        actor_id: str,
        expected_revision: int | None = None,
    ) -> JsonDict:
        proposal = self._pending_store.load(pending_id)
        if proposal is None or proposal.status != "pending":
            return {
                "accepted": False,
                "execution_id": None,
                "reason": "pending no encontrado",
                "revision": proposal.revision if proposal is not None else None,
                "policy_reevaluated": False,
            }
        if expected_revision is not None and proposal.revision != expected_revision:
            return {
                "accepted": False,
                "execution_id": None,
                "reason": "revision conflict",
                "revision": proposal.revision,
                "policy_reevaluated": False,
            }
        # Defensa en profundidad: el ttl_reaper corre cada N s, así que una propuesta
        # puede estar vencida por tiempo pero seguir status='pending' hasta la próxima
        # barrida. No la ejecutamos: el TTL es un límite duro, no una sugerencia.
        if _is_expired(proposal.expires_at):
            return {
                "accepted": False,
                "execution_id": None,
                "reason": "propuesta expirada",
                "policy_reevaluated": False,
            }

        # Re-evaluación ANTES de validar la palabra: el pending store no es la
        # autoridad, la política sí. Si el plan es D ahora, ni la palabra correcta
        # lo ejecuta; si el riesgo subió (p.ej. B→C), la palabra exigida es la del
        # nivel NUEVO, no la del nivel guardado.
        plan = _plan_from_json(proposal.plan_json)
        fresh_decision = self._engine.evaluate(plan)
        if fresh_decision.outcome == Outcome.REJECT or fresh_decision.risk_level >= RiskLevel.D:
            resolved = self._pending_store.resolve(
                pending_id,
                "policy",
                status="rejected",
                expected_revision=proposal.revision,
            )
            if resolved is None:
                current = self._pending_store.load(pending_id)
                if current is not None and current.status == "pending":
                    current = self._pending_store.expire(
                        pending_id,
                        expected_revision=current.revision,
                    ) or self._pending_store.load(pending_id)
                if current is None or current.status != "rejected":
                    reason = (
                        "propuesta expirada"
                        if current is not None and current.status == "expired"
                        else "pending stale"
                    )
                    return {
                        "accepted": False,
                        "execution_id": None,
                        "reason": reason,
                        "revision": current.revision if current is not None else None,
                        "policy_reevaluated": True,
                    }
                resolved = current
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
                "revision": resolved.revision if resolved is not None else proposal.revision,
                "policy_reevaluated": True,
            }

        stored_level = RiskLevel[proposal.risk_level]
        effective_level = max(stored_level, fresh_decision.risk_level)
        accepted = _confirmation_matches(effective_level, response)
        self._audit.log(
            AuditEvent.new(
                task_id=proposal.task_id,
                actor_type=ActorType.OWNER,
                actor_id=actor_id,
                event_type=AuditEventType.CONFIRMATION_ANSWERED,
                message="confirmación respondida",
                payload={
                    "pending_id": pending_id,
                    "accepted": accepted,
                    "risk_level": effective_level.name,
                    "source": actor_id,
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
                    "policy_reevaluated": True,
                    "required_risk": effective_level.name,
                    "revision": proposal.revision,
                }
            return {"accepted": False, "execution_id": None, "policy_reevaluated": True}

        if self._runner is None:
            return {
                "accepted": False,
                "execution_id": None,
                "reason": "executor no disponible",
                "revision": proposal.revision,
                "policy_reevaluated": True,
            }

        resolved = self._pending_store.resolve(
            pending_id,
            actor_id,
            expected_revision=expected_revision,
        )
        if resolved is None:
            current = self._pending_store.load(pending_id)
            return {
                "accepted": False,
                "execution_id": None,
                "reason": "pending stale",
                "revision": current.revision if current is not None else proposal.revision,
                "policy_reevaluated": True,
            }
        executed = await self._execute_plan(plan)
        return {
            "accepted": True,
            "revision": resolved.revision,
            "policy_reevaluated": True,
            **executed,
        }

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
        if self._audit_query is None:
            raise RuntimeError("consulta de auditoría no configurada")
        limit = _bounded_int(params.get("limit", 50), name="limit", minimum=1, maximum=200)
        since = _optional_datetime(params.get("since"), name="since")
        task_id = _optional_non_empty_string(params.get("task_id"), name="task_id")
        event_type_raw = _optional_non_empty_string(params.get("event_type"), name="event_type")
        try:
            event_type = AuditEventType(event_type_raw) if event_type_raw is not None else None
        except ValueError as exc:
            raise ValueError("event_type inválido") from exc
        include_payload = params.get("include_payload", False)
        if not isinstance(include_payload, bool):
            raise ValueError("include_payload debe ser booleano")
        events = self._audit_query.query(
            AuditQuery(since=since, limit=limit, task_id=task_id, event_type=event_type)
        )
        return {
            "events": [
                {
                    "event_id": event.event_id,
                    "task_id": event.task_id,
                    "actor_type": event.actor_type.value,
                    "actor_id": event.actor_id,
                    "event_type": event.event_type.value,
                    "message": event.message,
                    **({"payload": dict(event.payload)} if include_payload else {}),
                    "created_at": event.created_at.isoformat(),
                }
                for event in events
            ]
        }

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

    async def _memory_list(self, params: Mapping[str, Any]) -> JsonDict:
        del params
        facts = [_memory_to_json(fact) for fact in self._memory_store.list_all()]
        return {"facts": facts}

    async def _memory_edit(self, params: Mapping[str, Any]) -> JsonDict:
        fact_id = _memory_fact_id_param(params)
        value = _memory_value_param(params)
        ok = self._memory_store.edit(fact_id, value)
        return {"ok": ok}

    async def _memory_forget(self, params: Mapping[str, Any]) -> JsonDict:
        fact_id = _memory_fact_id_param(params)
        ok = self._memory_store.forget(fact_id)
        return {"ok": ok}

    async def _digest_today(self, params: Mapping[str, Any]) -> JsonDict:
        """Compone el digest on-demand con ventana mes corriente → hoy en Argentina."""
        del params
        now = datetime.now(ARG_TZ)
        today = now.date()
        window = _digest_window(today)
        markdown = compose_digest(
            today=today,
            pending=self._pending_store.load_pending(),
            ledger=self._ledger,
            window=window,
            routines=self._routine_store.list_all(),
            memory=self._memory_store.list_all(),
        )
        self._audit.log(
            AuditEvent.new(
                actor_type=ActorType.SYSTEM,
                actor_id="digest",
                event_type=AuditEventType.DIGEST_GENERATED,
                message="digest generado",
                payload={"date": today.isoformat()},
            )
        )
        return {
            "markdown": markdown,
            "generated_at": now.isoformat(timespec="seconds"),
        }

    async def _safe_health_check(self) -> bool:
        try:
            return await self._orchestrator.health_check()
        except Exception:
            return False


def _floor_intake_decision(decision: PolicyDecision) -> PolicyDecision:
    """Aplica el floor B para intake externo sin tocar D/REJECT."""
    if decision.outcome == Outcome.REJECT or decision.risk_level >= RiskLevel.D:
        return decision
    risk_level = max(decision.risk_level, RiskLevel.B)
    outcome = outcome_for(risk_level)
    if risk_level == decision.risk_level and outcome == decision.outcome:
        return decision
    reasons = decision.reasons
    if risk_level > decision.risk_level:
        reasons = (*reasons, "floor B por origen intake externo")
    return PolicyDecision(
        task_id=decision.task_id,
        risk_level=risk_level,
        outcome=outcome,
        matched_rules=decision.matched_rules,
        reasons=reasons,
    )


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
    memory_store: MemoryAdmin,
    ledger: LedgerPort,
    scheduler: RoutineScheduler,
    runner: PlanRunner | None = None,
    audit_query: AuditQueryPort | None = None,
    idempotency: IdempotencyPort | None = None,
    home_socket_path: Path | None = None,
    home_peer_uid: int | None = None,
    home_peer_gid: int | None = None,
    reaper_interval_s: float = 30.0,
    digest_enabled: bool = False,
    digest_hour: int = 8,
    digest_minute: int = 0,
    digest_dir: Path | None = None,
) -> RunningDaemon:
    """Arranca el Unix socket server y devuelve recursos cerrables."""
    await _cleanup_stale_socket(socket_path)
    if home_socket_path is not None:
        await _cleanup_stale_socket(home_socket_path)
        if home_peer_uid is None or home_peer_gid is None:
            raise RuntimeError("socket Home requiere UID y GID de peer dedicados")
        if home_peer_uid == os.getuid():
            raise RuntimeError("Home Edge debe usar un UID distinto al owner de Wyss")
        _validate_home_runtime_dir(home_socket_path.parent, home_peer_gid)
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    daemon = DaemonServer(
        engine=engine,
        orchestrator=orchestrator,
        pending_store=pending_store,
        audit=audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=ledger,
        scheduler=scheduler,
        runner=runner,
        audit_query=audit_query,
        idempotency=idempotency,
        home_peer_uid=home_peer_uid,
    )
    scheduler.set_on_queued(daemon._execute_plan if runner is not None else None)
    server = await asyncio.start_unix_server(daemon.handle, str(socket_path))
    os.chmod(socket_path, 0o600)
    home_server: asyncio.AbstractServer | None = None
    if home_socket_path is not None:
        if idempotency is None or runner is None:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)
            raise RuntimeError("socket Home requiere idempotencia y executor configurados")
        try:
            home_server = await asyncio.start_unix_server(
                daemon.handle_home,
                str(home_socket_path),
            )
            assert home_peer_gid is not None
            os.chown(home_socket_path, -1, home_peer_gid)
            os.chmod(home_socket_path, 0o660)
        except BaseException:
            server.close()
            await server.wait_closed()
            socket_path.unlink(missing_ok=True)
            home_socket_path.unlink(missing_ok=True)
            raise
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
    if digest_enabled:
        target_dir = digest_dir if digest_dir is not None else socket_path.parent / "digests"

        async def digest_job() -> None:
            today = datetime.now(ARG_TZ).date()
            window = _digest_window(today)
            markdown = compose_digest(
                today=today,
                pending=pending_store.load_pending(),
                ledger=ledger,
                window=window,
                routines=routine_store.list_all(),
                memory=memory_store.list_all(),
            )
            output = write_digest_file(target_dir, today, markdown)
            audit.log(
                AuditEvent.new(
                    actor_type=ActorType.SYSTEM,
                    actor_id="digest",
                    event_type=AuditEventType.DIGEST_GENERATED,
                    message="digest programado generado",
                    payload={"date": today.isoformat(), "path": str(output)},
                )
            )

        scheduler.schedule_digest(
            hour=digest_hour,
            minute=digest_minute,
            callback=digest_job,
        )
    scheduler.start()
    return RunningDaemon(
        server=server,
        socket_path=socket_path,
        reaper_task=reaper_task,
        scheduler=scheduler,
        home_server=home_server,
        home_socket_path=home_socket_path,
    )


async def run_daemon(
    socket_path: Path,
    *,
    engine: CognitivePolicyEngine,
    orchestrator: OrchestratorPort,
    pending_store: PendingStore,
    audit: AuditPort,
    routine_store: RoutineStore,
    memory_store: MemoryAdmin,
    ledger: LedgerPort,
    scheduler: RoutineScheduler,
    runner: PlanRunner | None = None,
    audit_query: AuditQueryPort | None = None,
    idempotency: IdempotencyPort | None = None,
    home_socket_path: Path | None = None,
    home_peer_uid: int | None = None,
    home_peer_gid: int | None = None,
    reaper_interval_s: float = 30.0,
    digest_enabled: bool = False,
    digest_hour: int = 8,
    digest_minute: int = 0,
    digest_dir: Path | None = None,
) -> None:
    """Corre el daemon hasta cancelación/señal y limpia socket al salir."""
    running = await start_daemon(
        socket_path,
        engine=engine,
        orchestrator=orchestrator,
        pending_store=pending_store,
        audit=audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=ledger,
        scheduler=scheduler,
        runner=runner,
        audit_query=audit_query,
        idempotency=idempotency,
        home_socket_path=home_socket_path,
        home_peer_uid=home_peer_uid,
        home_peer_gid=home_peer_gid,
        reaper_interval_s=reaper_interval_s,
        digest_enabled=digest_enabled,
        digest_hour=digest_hour,
        digest_minute=digest_minute,
        digest_dir=digest_dir,
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


def _peer_uid(writer: asyncio.StreamWriter) -> int | None:
    """Lee SO_PEERCRED del socket Unix; ausencia o formato inválido falla cerrado."""
    peer_socket = writer.get_extra_info("socket")
    if peer_socket is None or not hasattr(peer_socket, "getsockopt"):
        return None
    try:
        raw = peer_socket.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        _pid, uid, _gid = struct.unpack("3i", raw)
    except (OSError, struct.error):
        return None
    return int(uid)


async def _write_closed_error(writer: asyncio.StreamWriter, code: int, message: str) -> None:
    writer.write(json.dumps(_error_response(None, code, message)).encode() + b"\n")
    await writer.drain()
    writer.close()
    await writer.wait_closed()


def _validate_home_runtime_dir(path: Path, shared_gid: int) -> None:
    """Exige un runtime dir precreado, atravesable sólo por owner y grupo Edge."""
    if not path.is_dir():
        raise RuntimeError(f"runtime dir Home no existe: {path}")
    stat = path.stat()
    mode = stat.st_mode & 0o777
    if stat.st_gid != shared_gid:
        raise RuntimeError("runtime dir Home no pertenece al grupo compartido configurado")
    if stat.st_uid != os.getuid():
        raise RuntimeError("runtime dir Home no pertenece al owner de Wyss")
    if shared_gid not in {*os.getgroups(), os.getegid()}:
        raise RuntimeError("el proceso Wyss no pertenece al grupo compartido Home")
    if mode != 0o750:
        raise RuntimeError("runtime dir Home debe ser 0750: grupo r-x y sin acceso para otros")


def _digest_window(today: date) -> tuple[str, str]:
    start = today.replace(day=1)
    return (start.isoformat(), today.isoformat())


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


def _home_confirmation_result(plan_id: str, confirmed: Mapping[str, Any]) -> JsonDict:
    reevaluated = confirmed.get("policy_reevaluated") is True
    if confirmed.get("accepted") is True:
        success = confirmed.get("success")
        return {
            "outcome": "resolved",
            "plan_id": plan_id,
            "accepted": True,
            "status": "failed" if success is False else "verified",
            "message": str(confirmed.get("detail") or "Plan resuelto por Wyss."),
            "policy_reevaluated": reevaluated,
            **({"revision": confirmed["revision"]} if "revision" in confirmed else {}),
            **({"execution_id": confirmed["execution_id"]} if "execution_id" in confirmed else {}),
        }
    reason = str(confirmed.get("reason") or "confirmación inválida")
    if reason in {"pending no encontrado", "pending stale"}:
        outcome = "already_resolved"
    elif reason == "propuesta expirada":
        outcome = "expired"
    elif reason == "plan rechazado por política al confirmar":
        outcome = "policy_rejected"
    elif reason == "revision conflict":
        outcome = "conflict"
    elif reason == "executor no disponible":
        outcome = "degraded"
    else:
        outcome = "confirmation_required"
    return {
        "outcome": outcome,
        "plan_id": plan_id,
        "accepted": False,
        "status": "failed",
        "message": reason,
        "policy_reevaluated": reevaluated,
        **({"revision": confirmed["revision"]} if "revision" in confirmed else {}),
        **({"required_risk": confirmed["required_risk"]} if "required_risk" in confirmed else {}),
    }


def _fingerprint(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _json_depth(value: object, *, _depth: int = 0) -> int:
    if _depth > 16:
        return _depth
    if isinstance(value, Mapping):
        return max(
            (_json_depth(item, _depth=_depth + 1) for item in value.values()),
            default=_depth,
        )
    if isinstance(value, (list, tuple)):
        return max((_json_depth(item, _depth=_depth + 1) for item in value), default=_depth)
    return _depth


def _json_mapping(value: Mapping[str, Any]) -> Mapping[str, JsonValue]:
    encoded = json.dumps(dict(value), ensure_ascii=False, separators=(",", ":"))
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise TypeError("respuesta Home no es un objeto JSON")
    return cast(dict[str, JsonValue], decoded)


def _bounded_string(value: object, *, name: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{name} debe tener entre 1 y {maximum} caracteres")
    return value.strip()


def _optional_string(value: object, *, name: str, maximum: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f"{name} debe tener como máximo {maximum} caracteres")
    return value


def _bounded_int(value: object, *, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} debe estar entre {minimum} y {maximum}")
    return value


def _optional_datetime(value: object, *, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} debe ser ISO 8601")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} debe ser ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{name} debe incluir zona horaria")
    return parsed


def _optional_non_empty_string(value: object, *, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} debe ser texto no vacío")
    return value.strip()


def _routine_id_param(params: Mapping[str, Any]) -> str:
    routine_id = str(params.get("routine_id", "")).strip()
    if not routine_id:
        raise ValueError("routine_id requerido")
    return routine_id


def _memory_fact_id_param(params: Mapping[str, Any]) -> str:
    fact_id = str(params.get("fact_id", "")).strip()
    if not fact_id:
        raise ValueError("fact_id requerido")
    return fact_id


def _memory_value_param(params: Mapping[str, Any]) -> str:
    value = str(params.get("value", "")).strip()
    if not value:
        raise ValueError("value requerido")
    return value


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


def _memory_to_json(fact: MemoryFact) -> JsonDict:
    return {
        "id": str(fact.id),
        "category": str(fact.category),
        "value": str(fact.value),
        "tier": str(fact.tier),
        "source": str(fact.source),
        "created_at": str(fact.created_at),
        "updated_at": str(fact.updated_at),
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
