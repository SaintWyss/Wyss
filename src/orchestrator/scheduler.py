"""Scheduler de rutinas sobre APScheduler.

El modulo mantiene APScheduler del lado orchestrator y deja el core libre de
dependencias externas. Cada disparo reconstruye un Plan deterministico desde la
rutina persistida y vuelve a pasar por el gate de politica compartido.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from apscheduler.triggers.interval import IntervalTrigger  # type: ignore[import-untyped]

from core.domain import ActorType, AuditEvent, AuditEventType, ConfigError, RiskLevel
from core.domain.plan import Action, ErrorPolicy, Plan, RetryParams
from core.policy import CognitivePolicyEngine
from core.ports.audit import AuditPort
from orchestrator.dispatcher import dispatch
from orchestrator.pending_store import PendingStore
from orchestrator.routine_store import Routine, RoutineStore

ARG_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
ROUTINE_TTL_SECONDS = 24 * 60 * 60
MIN_INTERVAL_SECONDS = 60
MISFIRE_GRACE_SECONDS = 5 * 60
_MAX_MISSED_COUNT = 10_000
QueuedPlanCallback = Callable[[Plan], Awaitable[dict[str, object]]]


def routine_ttl_for(level: RiskLevel) -> int:
    """TTL fijo de 24h para propuestas originadas por rutinas."""
    del level
    return ROUTINE_TTL_SECONDS


def build_plan_from_routine(routine: Routine) -> Plan:
    """Reconstruye un Plan desde `plan_json`, sin gateway ni LLM."""
    data = json.loads(routine.plan_json)
    if not isinstance(data, dict):
        raise ValueError("plan_json invalido")
    return Plan(
        task_id=f"routine-{routine.id}",
        summary=str(data["summary"]),
        steps=tuple(_action_from_dict(item) for item in data.get("steps", [])),
        rationale=str(data["rationale"]),
        estimated_risk=(
            RiskLevel[str(data["estimated_risk"])] if data.get("estimated_risk") else None
        ),
    )


def validate_schedule(
    schedule_kind: str,
    schedule_expr: str,
    *,
    tz: ZoneInfo = ARG_TZ,
) -> None:
    """Valida cron/interval y traduce errores a mensajes de configuracion legibles."""
    _build_trigger(schedule_kind, schedule_expr, tz=tz)


def preview_next_fires(
    schedule_kind: str,
    schedule_expr: str,
    count: int = 5,
    *,
    tz: ZoneInfo = ARG_TZ,
    now: datetime | None = None,
) -> list[datetime]:
    """Devuelve las proximas `count` ejecuciones timezone-aware en hora Argentina."""
    if count <= 0:
        return []
    current = _to_tz(now if now is not None else datetime.now(tz), tz)
    trigger = _build_trigger(schedule_kind, schedule_expr, tz=tz, start_date=current)
    fires: list[datetime] = []
    previous: datetime | None = None
    for _ in range(count):
        next_fire = trigger.get_next_fire_time(previous, current)
        if next_fire is None:
            break
        fires.append(_to_tz(next_fire, tz))
        previous = next_fire
        current = next_fire
    return fires


async def _fire_routine(
    routine: Routine,
    *,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    audit: AuditPort,
    routine_store: RoutineStore,
    on_queued: QueuedPlanCallback | None = None,
) -> None:
    """Dispara una rutina por el gate normal de politica y audita fallos."""
    try:
        current = routine_store.get(routine.id)
        if current is None or current.status != "active":
            return
        plan = build_plan_from_routine(current)
        decision = engine.evaluate(plan)
        result = await dispatch(
            plan,
            decision,
            pending_store=pending_store,
            audit=audit,
            ttl_for=routine_ttl_for,
        )
        outcome = str(result.get("outcome", "unknown"))
        execution_result: dict[str, object] | None = None
        if outcome == "queued" and on_queued is not None:
            execution_result = await on_queued(plan)
            outcome = "executed" if execution_result.get("success") is True else "failed"
        audit.log(
            AuditEvent.new(
                task_id=plan.task_id,
                actor_type=ActorType.SYSTEM,
                actor_id="scheduler",
                event_type=AuditEventType.ROUTINE_TRIGGERED,
                message="rutina disparada",
                payload={
                    "routine_id": current.id,
                    "routine_name": current.name,
                    "outcome": outcome,
                    "risk_level": decision.risk_level.name,
                    "policy_outcome": decision.outcome.name,
                    "execution_id": (
                        execution_result.get("execution_id")
                        if execution_result is not None
                        else None
                    ),
                    "execution_success": (
                        execution_result.get("success")
                        if execution_result is not None
                        else None
                    ),
                },
            )
        )
        routine_store.mark_fired(current.id, datetime.now(UTC).isoformat(), outcome)
    except Exception as exc:
        audit.log(
            AuditEvent.new(
                task_id=f"routine-{routine.id}",
                actor_type=ActorType.SYSTEM,
                actor_id="scheduler",
                event_type=AuditEventType.TASK_FAILED,
                message="fallo al disparar rutina",
                payload={
                    "routine_id": routine.id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        )


class RoutineScheduler:
    """Wrapper fino de AsyncIOScheduler para rutinas persistidas."""

    def __init__(
        self,
        *,
        engine: CognitivePolicyEngine,
        pending_store: PendingStore,
        audit: AuditPort,
        routine_store: RoutineStore,
        on_queued: QueuedPlanCallback | None = None,
    ) -> None:
        self._engine = engine
        self._pending_store = pending_store
        self._audit = audit
        self._routine_store = routine_store
        self._on_queued = on_queued
        self._scheduler = AsyncIOScheduler(timezone=ARG_TZ)

    def add_routine(self, routine: Routine) -> None:
        """Registra o reemplaza el job de una rutina."""
        trigger = _trigger_for_routine(routine)
        self._scheduler.add_job(
            self._run_routine,
            trigger=trigger,
            id=_job_id(routine.id),
            args=[routine.id],
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=MISFIRE_GRACE_SECONDS,
        )

    def remove_routine(self, routine_id: str) -> None:
        """Remueve un job si esta registrado."""
        job_id = _job_id(routine_id)
        if self._scheduler.get_job(job_id) is not None:
            self._scheduler.remove_job(job_id)

    def pause_job(self, routine_id: str) -> None:
        """Pausa un job registrado."""
        job_id = _job_id(routine_id)
        if self._scheduler.get_job(job_id) is not None:
            self._scheduler.pause_job(job_id)

    def resume_job(self, routine_id: str) -> None:
        """Reanuda un job registrado."""
        job_id = _job_id(routine_id)
        if self._scheduler.get_job(job_id) is not None:
            self._scheduler.resume_job(job_id)

    def set_on_queued(self, on_queued: QueuedPlanCallback | None) -> None:
        """Configura el callback opcional para ejecutar planes A encolados."""
        self._on_queued = on_queued

    def start(self) -> None:
        """Arranca APScheduler en el loop asyncio actual."""
        self._scheduler.start()

    def shutdown(self, *, wait: bool = False) -> None:
        """Detiene APScheduler sin esperar jobs en curso."""
        self._scheduler.shutdown(wait=wait)

    async def _run_routine(self, routine_id: str) -> None:
        routine = self._routine_store.get(routine_id)
        if routine is None:
            return
        await _fire_routine(
            routine,
            engine=self._engine,
            pending_store=self._pending_store,
            audit=self._audit,
            routine_store=self._routine_store,
            on_queued=self._on_queued,
        )


async def register_routines(
    scheduler: RoutineScheduler,
    routine_store: RoutineStore,
    *,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    audit: AuditPort,
    now: datetime | None = None,
    on_queued: QueuedPlanCallback | None = None,
) -> None:
    """Registra rutinas activas y aplica catch-up coalescente al boot."""
    boot_now = _to_tz(now if now is not None else datetime.now(ARG_TZ), ARG_TZ)
    for routine in routine_store.list_active():
        missed = _missed_fire_count(routine, boot_now)
        if missed > 0 and routine.catch_up:
            await _fire_routine(
                routine,
                engine=engine,
                pending_store=pending_store,
                audit=audit,
                routine_store=routine_store,
                on_queued=on_queued,
            )
        elif missed > 0:
            audit.log(
                AuditEvent.new(
                    task_id=f"routine-{routine.id}",
                    actor_type=ActorType.SYSTEM,
                    actor_id="scheduler",
                    event_type=AuditEventType.ROUTINE_TRIGGERED,
                    message="rutina omitida por catch_up desactivado",
                    payload={
                        "routine_id": routine.id,
                        "missed": True,
                        "coalesced": missed,
                        "catch_up": False,
                    },
                )
            )
        scheduler.add_routine(routine)


def _action_from_dict(data: object) -> Action:
    if not isinstance(data, dict):
        raise ValueError("action invalida")
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


def _trigger_for_routine(routine: Routine) -> Any:
    start_date = _parse_datetime(routine.created_at, ARG_TZ)
    return _build_trigger(
        routine.schedule_kind,
        routine.schedule_expr,
        tz=ARG_TZ,
        start_date=start_date,
    )


def _build_trigger(
    schedule_kind: str,
    schedule_expr: str,
    *,
    tz: ZoneInfo,
    start_date: datetime | None = None,
) -> Any:
    if schedule_kind == "cron":
        try:
            return CronTrigger.from_crontab(schedule_expr, timezone=tz)
        except Exception as exc:
            raise ConfigError(f"cron invalido {schedule_expr!r}: {exc}") from exc
    if schedule_kind == "interval":
        seconds = _parse_interval_seconds(schedule_expr)
        if seconds < MIN_INTERVAL_SECONDS:
            raise ConfigError(
                f"interval invalido {schedule_expr!r}: minimo {MIN_INTERVAL_SECONDS}s"
            )
        try:
            return IntervalTrigger(seconds=seconds, start_date=start_date, timezone=tz)
        except Exception as exc:
            raise ConfigError(f"interval invalido {schedule_expr!r}: {exc}") from exc
    raise ConfigError(f"schedule_kind invalido {schedule_kind!r}")


def _parse_interval_seconds(schedule_expr: str) -> int:
    try:
        return int(schedule_expr)
    except ValueError as exc:
        raise ConfigError(f"interval invalido {schedule_expr!r}: debe ser segundos") from exc


def _missed_fire_count(routine: Routine, now: datetime) -> int:
    if routine.last_fired_at is None:
        return 0
    last_fired = _parse_datetime(routine.last_fired_at, ARG_TZ)
    if last_fired >= now:
        return 0
    trigger = _trigger_for_routine(routine)
    current = last_fired + timedelta(microseconds=1)
    previous: datetime | None = None
    missed = 0
    while missed < _MAX_MISSED_COUNT:
        next_fire = trigger.get_next_fire_time(previous, current)
        if next_fire is None or next_fire > now:
            break
        missed += 1
        previous = next_fire
        current = next_fire + timedelta(microseconds=1)
    return missed


def _parse_datetime(value: str, tz: ZoneInfo) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(tz)


def _to_tz(value: datetime, tz: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def _job_id(routine_id: str) -> str:
    return f"routine:{routine_id}"
