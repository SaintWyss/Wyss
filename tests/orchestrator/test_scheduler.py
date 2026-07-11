"""Tests del scheduler de rutinas (SCHED-01/02/04/05)."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest

import orchestrator.scheduler as scheduler_module
from core.domain import AuditEvent, AuditEventType, ConfigError, RiskLevel
from core.domain.plan import Plan
from core.policy import CognitivePolicyEngine
from orchestrator.pending_store import PendingStore
from orchestrator.routine_store import Routine, RoutineStore
from orchestrator.scheduler import (
    ARG_TZ,
    RoutineScheduler,
    _fire_routine,
    build_plan_from_routine,
    preview_next_fires,
    register_routines,
    routine_ttl_for,
    validate_schedule,
)

from .conftest import FakeAudit


@pytest.fixture
def routine_store(tmp_path: Path) -> Iterator[RoutineStore]:
    store = RoutineStore(tmp_path / "routines.db")
    try:
        yield store
    finally:
        store.close()


def test_preview_next_fires() -> None:
    now = datetime(2026, 7, 10, 7, 0, tzinfo=ARG_TZ)

    fires = preview_next_fires("cron", "0 8 * * *", 4, now=now)

    assert len(fires) == 4
    assert all(fire.tzinfo == ARG_TZ for fire in fires)
    assert all(fire.hour == 8 and fire.minute == 0 for fire in fires)
    assert fires == sorted(fires)
    assert len(set(fires)) == len(fires)


def test_invalid_cron_is_legible() -> None:
    with pytest.raises(ConfigError, match="cron invalido"):
        preview_next_fires("cron", "99 99 * * *")


def test_validate_schedule_floor() -> None:
    with pytest.raises(ConfigError, match="minimo 60s"):
        validate_schedule("interval", "59")

    validate_schedule("interval", "60")


def test_build_plan_from_routine() -> None:
    routine = _routine("abc", _plan_json("file.read", "/tmp/source.txt", "B"))

    plan = build_plan_from_routine(routine)

    assert plan.task_id == "routine-abc"
    assert plan.summary == "hacer tarea"
    assert plan.estimated_risk == RiskLevel.B
    assert len(plan.steps) == 1
    assert plan.steps[0].type == "file.read"
    assert plan.steps[0].target == "/tmp/source.txt"


def test_routine_ttl_for() -> None:
    assert routine_ttl_for(RiskLevel.B) == 86400
    assert routine_ttl_for(RiskLevel.C) == 86400


async def test_schedule_digest_registers_internal_job(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)
    calls = 0

    async def callback() -> None:
        nonlocal calls
        calls += 1

    scheduler.schedule_digest(hour=8, minute=0, callback=callback)

    job = scheduler._scheduler.get_job("internal:digest")
    assert job is not None
    assert job.id == "internal:digest"
    assert scheduler._scheduler.get_job("routine:internal:digest") is None
    await job.func()
    assert calls == 1


async def test_schedule_digest_does_not_touch_routine_store(
    monkeypatch: pytest.MonkeyPatch,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)

    def fail_list_active() -> list[Routine]:
        raise AssertionError("schedule_digest no debe leer RoutineStore")

    monkeypatch.setattr(routine_store, "list_active", fail_list_active)

    async def callback() -> None:
        return None

    scheduler.schedule_digest(hour=8, minute=0, callback=callback)

    assert routine_store.list_all() == []


async def test_routine_fire_respects_policy_gate(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        "lectura",
        "cron",
        "0 8 * * *",
        _plan_json("file.read", "/tmp/source.txt"),
    )
    routine = _loaded(routine_store, routine_id)

    await _fire_routine(
        routine,
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
    )

    fired = _loaded(routine_store, routine_id)
    assert fired.last_outcome == "queued"
    assert pending_store.load_pending() == []
    assert _events(fake_audit, AuditEventType.ROUTINE_TRIGGERED)


async def test_a_routine_executes_queued_plan_with_callback(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        "lectura",
        "cron",
        "0 8 * * *",
        _plan_json("file.read", "/tmp/source.txt"),
    )
    called: list[Plan] = []

    async def on_queued(plan: Plan) -> dict[str, object]:
        called.append(plan)
        return {"execution_id": "exec-test", "success": True, "detail": "ok"}

    await _fire_routine(
        _loaded(routine_store, routine_id),
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        on_queued=on_queued,
    )

    assert [plan.task_id for plan in called] == [f"routine-{routine_id}"]
    assert _loaded(routine_store, routine_id).last_outcome == "executed"
    event = _events(fake_audit, AuditEventType.ROUTINE_TRIGGERED)[-1]
    assert event.payload["outcome"] == "executed"
    assert event.payload["execution_id"] == "exec-test"


async def test_a_routine_marks_failed_when_callback_fails_plan(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        "lectura",
        "cron",
        "0 8 * * *",
        _plan_json("file.read", "/tmp/source.txt"),
    )

    async def on_queued(plan: Plan) -> dict[str, object]:
        del plan
        return {"execution_id": "exec-test", "success": False, "detail": "falló"}

    await _fire_routine(
        _loaded(routine_store, routine_id),
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        on_queued=on_queued,
    )

    assert _loaded(routine_store, routine_id).last_outcome == "failed"


async def test_bc_routine_never_auto_executes(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        "escritura",
        "cron",
        "0 8 * * *",
        _plan_json("file.write", "/tmp/target.txt"),
    )

    await _fire_routine(
        _loaded(routine_store, routine_id),
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
    )

    pending = pending_store.load_pending()
    assert len(pending) == 1
    assert pending[0].task_id == f"routine-{routine_id}"
    assert _loaded(routine_store, routine_id).last_outcome == "pending"


async def test_bc_routine_never_calls_on_queued(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    b_routine_id = routine_store.add(
        "movida",
        "cron",
        "0 8 * * *",
        _plan_json("file.move", "/tmp/target.txt"),
    )
    c_routine_id = routine_store.add(
        "escritura",
        "cron",
        "0 8 * * *",
        _plan_json("file.write", "/tmp/target.txt"),
    )
    calls = 0

    async def on_queued(plan: Plan) -> dict[str, object]:
        nonlocal calls
        del plan
        calls += 1
        return {"success": True}

    await _fire_routine(
        _loaded(routine_store, b_routine_id),
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        on_queued=on_queued,
    )
    await _fire_routine(
        _loaded(routine_store, c_routine_id),
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        on_queued=on_queued,
    )

    assert calls == 0
    assert _loaded(routine_store, b_routine_id).last_outcome == "pending"
    assert _loaded(routine_store, c_routine_id).last_outcome == "pending"


async def test_bc_routine_uses_24h_ttl(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        "escritura",
        "cron",
        "0 8 * * *",
        _plan_json("file.write", "/tmp/target.txt"),
    )

    await _fire_routine(
        _loaded(routine_store, routine_id),
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
    )

    proposal = pending_store.load_pending()[0]
    created_at = datetime.fromisoformat(proposal.created_at)
    expires_at = datetime.fromisoformat(proposal.expires_at)
    ttl = (expires_at - created_at).total_seconds()
    assert 86395 <= ttl <= 86405


async def test_fire_is_audited(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        "lectura",
        "cron",
        "0 8 * * *",
        _plan_json("file.read", "/tmp/source.txt"),
    )

    await _fire_routine(
        _loaded(routine_store, routine_id),
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
    )

    event = _events(fake_audit, AuditEventType.ROUTINE_TRIGGERED)[-1]
    assert event.actor_id == "scheduler"
    assert event.task_id == f"routine-{routine_id}"
    assert event.payload["routine_id"] == routine_id
    assert event.payload["outcome"] == "queued"


async def test_fire_failure_is_audited(
    monkeypatch: pytest.MonkeyPatch,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add("rota", "cron", "0 8 * * *", "{}")

    def boom(routine: Routine) -> Plan:
        del routine
        raise RuntimeError("boom")

    monkeypatch.setattr(scheduler_module, "build_plan_from_routine", boom)

    await _fire_routine(
        _loaded(routine_store, routine_id),
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
    )

    failures = _events(fake_audit, AuditEventType.TASK_FAILED)
    assert len(failures) == 1
    assert failures[0].payload["error_type"] == "RuntimeError"
    assert _loaded(routine_store, routine_id).last_fired_at is None


async def test_paused_routine_skips_fire(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        "pausada",
        "cron",
        "0 8 * * *",
        _plan_json("file.write", "/tmp/target.txt"),
    )
    assert routine_store.pause(routine_id) is True

    await _fire_routine(
        _loaded(routine_store, routine_id),
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
    )

    assert pending_store.load_pending() == []
    assert _loaded(routine_store, routine_id).last_fired_at is None
    assert fake_audit.events == []


async def test_catchup_on_boot_coalesces(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        "diaria",
        "cron",
        "0 8 * * *",
        _plan_json("file.read", "/tmp/source.txt"),
        catch_up=True,
    )
    last_fired = datetime(2026, 7, 7, 8, 5, tzinfo=ARG_TZ).astimezone(UTC)
    assert routine_store.mark_fired(routine_id, last_fired.isoformat(), "old")
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)

    await register_routines(
        scheduler,
        routine_store,
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        now=datetime(2026, 7, 10, 9, 0, tzinfo=ARG_TZ),
    )

    triggered = _events(fake_audit, AuditEventType.ROUTINE_TRIGGERED)
    real_fires = [event for event in triggered if not event.payload.get("missed")]
    assert len(real_fires) == 1
    assert _loaded(routine_store, routine_id).last_outcome == "queued"


async def test_catchup_on_boot_propagates_on_queued(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        "diaria",
        "cron",
        "0 8 * * *",
        _plan_json("file.read", "/tmp/source.txt"),
        catch_up=True,
    )
    last_fired = datetime(2026, 7, 7, 8, 5, tzinfo=ARG_TZ).astimezone(UTC)
    assert routine_store.mark_fired(routine_id, last_fired.isoformat(), "old")
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)

    async def on_queued(plan: Plan) -> dict[str, object]:
        del plan
        return {"execution_id": "exec-catchup", "success": True, "detail": "ok"}

    await register_routines(
        scheduler,
        routine_store,
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        now=datetime(2026, 7, 10, 9, 0, tzinfo=ARG_TZ),
        on_queued=on_queued,
    )

    assert _loaded(routine_store, routine_id).last_outcome == "executed"


async def test_catchup_false_skips(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        "diaria",
        "cron",
        "0 8 * * *",
        _plan_json("file.read", "/tmp/source.txt"),
        catch_up=False,
    )
    last_fired = datetime(2026, 7, 7, 8, 5, tzinfo=ARG_TZ).astimezone(UTC)
    assert routine_store.mark_fired(routine_id, last_fired.isoformat(), "old")
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)

    await register_routines(
        scheduler,
        routine_store,
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        now=datetime(2026, 7, 10, 9, 0, tzinfo=ARG_TZ),
    )

    assert _loaded(routine_store, routine_id).last_outcome == "old"
    missed = _events(fake_audit, AuditEventType.ROUTINE_TRIGGERED)
    assert len(missed) == 1
    assert missed[0].payload["missed"] is True
    assert pending_store.load_pending() == []


async def test_no_double_fire_on_restart(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        "diaria",
        "cron",
        "0 8 * * *",
        _plan_json("file.read", "/tmp/source.txt"),
        catch_up=True,
    )
    last_fired = datetime(2026, 7, 10, 8, 30, tzinfo=ARG_TZ).astimezone(UTC)
    assert routine_store.mark_fired(routine_id, last_fired.isoformat(), "old")
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)

    await register_routines(
        scheduler,
        routine_store,
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        now=datetime(2026, 7, 10, 9, 0, tzinfo=ARG_TZ),
    )

    assert _loaded(routine_store, routine_id).last_outcome == "old"
    assert _events(fake_audit, AuditEventType.ROUTINE_TRIGGERED) == []


async def test_missed_without_last_fired(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        "nueva",
        "cron",
        "0 8 * * *",
        _plan_json("file.read", "/tmp/source.txt"),
        catch_up=True,
    )
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)

    await register_routines(
        scheduler,
        routine_store,
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        now=datetime(2026, 7, 10, 9, 0, tzinfo=ARG_TZ),
    )

    loaded = _loaded(routine_store, routine_id)
    assert loaded.last_fired_at is None
    assert fake_audit.events == []


async def test_missed_is_audited(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> None:
    routine_id = routine_store.add(
        "diaria",
        "cron",
        "0 8 * * *",
        _plan_json("file.read", "/tmp/source.txt"),
        catch_up=False,
    )
    last_fired = datetime(2026, 7, 8, 8, 5, tzinfo=ARG_TZ).astimezone(UTC)
    assert routine_store.mark_fired(routine_id, last_fired.isoformat(), "old")
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)

    await register_routines(
        scheduler,
        routine_store,
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        now=datetime(2026, 7, 10, 9, 0, tzinfo=ARG_TZ),
    )

    event = _events(fake_audit, AuditEventType.ROUTINE_TRIGGERED)[0]
    assert event.task_id == f"routine-{routine_id}"
    assert event.payload["missed"] is True
    assert cast(int, event.payload["coalesced"]) >= 1


def _routine_scheduler(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    routine_store: RoutineStore,
) -> RoutineScheduler:
    return RoutineScheduler(
        engine=engine,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
    )


def _plan_json(
    action_type: str,
    target: str,
    estimated_risk: str | None = None,
) -> str:
    return json.dumps(
        {
            "task_id": "stored-task",
            "summary": "hacer tarea",
            "steps": [
                {
                    "type": action_type,
                    "target": target,
                    "parameters": {},
                    "on_error": "abort",
                    "retry_params": None,
                }
            ],
            "rationale": "test",
            "estimated_risk": estimated_risk,
        }
    )


def _routine(routine_id: str, plan_json: str) -> Routine:
    return Routine(
        id=routine_id,
        name="rutina",
        schedule_kind="cron",
        schedule_expr="0 8 * * *",
        plan_json=plan_json,
        catch_up=True,
        status="active",
        created_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
        last_fired_at=None,
        last_outcome=None,
    )


def _loaded(store: RoutineStore, routine_id: str) -> Routine:
    routine = store.get(routine_id)
    assert routine is not None
    return routine


def _events(fake_audit: FakeAudit, event_type: AuditEventType) -> list[AuditEvent]:
    return [event for event in fake_audit.events if event.event_type == event_type]
