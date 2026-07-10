"""Daemon JSON-RPC y dispatcher fail-closed."""

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from core.domain import AuditEventType, Outcome, RiskLevel
from core.domain.plan import Action, Plan
from core.domain.policy import PolicyDecision
from core.policy import CognitivePolicyEngine
from orchestrator.daemon import DaemonServer, start_daemon
from orchestrator.dispatcher import dispatch
from orchestrator.pending_store import PendingStore
from orchestrator.routine_store import RoutineStore
from orchestrator.scheduler import RoutineScheduler

from .conftest import FakeAudit, FakeOrchestrator


class _FakeAsyncioServer:
    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None

    async def serve_forever(self) -> None:
        await asyncio.Future()


class _MemoryWriter:
    def __init__(self) -> None:
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


@pytest.fixture
def routine_store(tmp_path: Path) -> Iterator[RoutineStore]:
    store = RoutineStore(tmp_path / "routines.db")
    try:
        yield store
    finally:
        store.close()


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


async def _handle_rpc(
    daemon: DaemonServer, method: str, params: dict[str, object]
) -> dict[str, Any]:
    reader = asyncio.StreamReader()
    reader.feed_data(
        json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 7}).encode()
        + b"\n"
    )
    reader.feed_eof()
    writer = _MemoryWriter()
    await daemon.handle(reader, cast(Any, writer))
    response = json.loads(bytes(writer.data))
    assert response["id"] == 7
    return cast(dict[str, Any], response)


async def test_stale_socket_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
) -> None:
    """ORCH-01: el daemon limpia un socket stale al arrancar y rebindea."""
    socket_path = tmp_path / "wyss.sock"
    socket_path.write_text("stale", encoding="utf-8")

    async def fake_open_unix_connection(path: str) -> tuple[object, object]:
        assert path == str(socket_path)
        raise ConnectionRefusedError

    async def fake_start_unix_server(handler: object, path: str) -> _FakeAsyncioServer:
        del handler
        assert path == str(socket_path)
        socket_path.write_text("socket", encoding="utf-8")
        return _FakeAsyncioServer()

    monkeypatch.setattr(asyncio, "open_unix_connection", fake_open_unix_connection)
    monkeypatch.setattr(asyncio, "start_unix_server", fake_start_unix_server)
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)

    running = await start_daemon(
        socket_path,
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        scheduler=scheduler,
        reaper_interval_s=3600,
    )
    try:
        assert socket_path.exists()
        assert socket_path.stat().st_mode & 0o777 == 0o600
    finally:
        await running.aclose()
    assert not socket_path.exists()


async def test_ask_round_trip(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
) -> None:
    """ORCH-02: `ask` por JSON-RPC sobre el socket devuelve respuesta del dispatcher."""
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
    )
    response = await _handle_rpc(daemon, "ask", {"instruction": "leer /tmp/source.txt"})

    assert "error" not in response
    assert response["result"]["outcome"] == "queued"
    assert str(response["result"]["execution_id"]).startswith("exec-fake-task-")
    assert {event.event_type for event in fake_audit.events} >= {
        AuditEventType.COMMAND_RECEIVED,
        AuditEventType.PLAN_CREATED,
        AuditEventType.POLICY_DECISION,
    }


async def test_routine_handlers_round_trip_via_rpc(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
) -> None:
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        scheduler=scheduler,
    )

    added = await _handle_rpc(
        daemon,
        "routine.add",
        {
            "name": "lectura",
            "schedule_kind": "interval",
            "schedule_expr": "300",
            "plan_json": _plan_json(),
            "catch_up": True,
        },
    )
    assert "error" not in added
    routine_id = str(added["result"]["routine_id"])
    assert added["result"]["preview"]

    listed = await _handle_rpc(daemon, "routine.list", {})
    routines = listed["result"]["routines"]
    assert len(routines) == 1
    assert routines[0]["id"] == routine_id
    assert routines[0]["status"] == "active"
    assert routines[0]["schedule"] == {"kind": "interval", "expr": "300"}
    assert routines[0]["last_fired_at"] is None
    assert routines[0]["last_outcome"] is None

    paused = await _handle_rpc(daemon, "routine.pause", {"routine_id": routine_id})
    assert paused["result"] == {"ok": True}
    assert _loaded_status(routine_store, routine_id) == "paused"

    resumed = await _handle_rpc(daemon, "routine.resume", {"routine_id": routine_id})
    assert resumed["result"] == {"ok": True}
    assert _loaded_status(routine_store, routine_id) == "active"

    deleted = await _handle_rpc(daemon, "routine.delete", {"routine_id": routine_id})
    assert deleted["result"] == {"ok": True}
    assert routine_store.get(routine_id) is None


async def test_routine_add_invalid_schedule_returns_rpc_error(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
) -> None:
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        scheduler=scheduler,
    )
    response = await _handle_rpc(
        daemon,
        "routine.add",
        {
            "name": "rapida",
            "schedule_kind": "interval",
            "schedule_expr": "59",
            "plan_json": _plan_json(),
            "catch_up": True,
        },
    )
    assert "error" in response
    assert "minimo 60s" in response["error"]["message"]
    assert routine_store.list_all() == []


async def test_aclose_shutdowns_scheduler_without_waiting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
) -> None:
    socket_path = tmp_path / "wyss.sock"
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)
    original_shutdown = scheduler.shutdown
    waits: list[bool] = []

    def spy_shutdown(*, wait: bool = False) -> None:
        waits.append(wait)
        original_shutdown(wait=wait)

    monkeypatch.setattr(scheduler, "shutdown", spy_shutdown)

    async def fake_start_unix_server(handler: object, path: str) -> _FakeAsyncioServer:
        del handler
        assert path == str(socket_path)
        socket_path.write_text("socket", encoding="utf-8")
        return _FakeAsyncioServer()

    monkeypatch.setattr(asyncio, "start_unix_server", fake_start_unix_server)
    running = await start_daemon(
        socket_path,
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        scheduler=scheduler,
        reaper_interval_s=3600,
    )

    await asyncio.wait_for(running.aclose(), timeout=1)

    assert waits == [False]
    assert not socket_path.exists()


async def test_dispatch_d_rejects_and_audits(
    pending_store: PendingStore,
    fake_audit: FakeAudit,
) -> None:
    plan = Plan(
        task_id="d",
        summary="formatear disco",
        steps=(Action("shell.run", "mkfs /dev/sda1"),),
        rationale="test",
    )
    decision = PolicyDecision(
        task_id=plan.task_id,
        risk_level=RiskLevel.D,
        outcome=Outcome.REJECT,
        matched_rules=("disk-format",),
        reasons=("denylist: disk-format",),
    )

    result = await dispatch(plan, decision, pending_store=pending_store, audit=fake_audit)

    assert result == {"outcome": "rejected", "reasons": ["denylist: disk-format"]}
    assert pending_store.load_pending() == []
    assert fake_audit.events[-1].event_type == AuditEventType.POLICY_DECISION


def _plan_json() -> str:
    return json.dumps(
        {
            "task_id": "stored-task",
            "summary": "leer archivo",
            "steps": [
                {
                    "type": "file.read",
                    "target": "/tmp/source.txt",
                    "parameters": {},
                    "on_error": "abort",
                    "retry_params": None,
                }
            ],
            "rationale": "test",
            "estimated_risk": None,
        }
    )


def _loaded_status(store: RoutineStore, routine_id: str) -> str:
    routine = store.get(routine_id)
    assert routine is not None
    return routine.status


async def test_dispatch_b_persists_pending(
    pending_store: PendingStore,
    fake_audit: FakeAudit,
) -> None:
    plan = Plan(
        task_id="b",
        summary="mover archivo",
        steps=(Action("file.move", "/tmp/source.txt"),),
        rationale="test",
    )
    decision = PolicyDecision(
        task_id=plan.task_id,
        risk_level=RiskLevel.B,
        outcome=Outcome.CONFIRM_SIMPLE,
        reasons=("per_action=B",),
    )

    result = await dispatch(plan, decision, pending_store=pending_store, audit=fake_audit)

    assert result["outcome"] == "pending"
    # smoke físico: sin risk_level la SPA defaulteaba el chip a B y no exigía
    # tipear CONFIRMAR en propuestas C
    assert result["risk_level"] == "B"
    assert "Resumen: mover archivo" in str(result["plan"])
    pending_id = str(result["pending_id"])
    loaded = pending_store.load(pending_id)
    assert loaded is not None
    assert loaded.task_id == "b"
    assert fake_audit.events[-1].event_type == AuditEventType.CONFIRMATION_REQUESTED


async def test_dispatch_a_queues(
    pending_store: PendingStore,
    fake_audit: FakeAudit,
) -> None:
    plan = Plan(
        task_id="a",
        summary="leer archivo",
        steps=(Action("file.read", "/tmp/source.txt"),),
        rationale="test",
    )
    decision = PolicyDecision(
        task_id=plan.task_id,
        risk_level=RiskLevel.A,
        outcome=Outcome.EXECUTE,
        reasons=("per_action=A",),
    )

    result = await dispatch(plan, decision, pending_store=pending_store, audit=fake_audit)

    assert result["outcome"] == "queued"
    assert str(result["execution_id"]).startswith("exec-a-")
    assert pending_store.load_pending() == []
    assert fake_audit.events[-1].event_type == AuditEventType.POLICY_DECISION


async def test_dispatch_corrupt_outcome_rejects(
    pending_store: PendingStore,
    fake_audit: FakeAudit,
) -> None:
    plan = Plan(
        task_id="corrupt",
        summary="tipo corrupto",
        steps=(Action("file.read", "/tmp/source.txt"),),
        rationale="test",
    )
    decision = PolicyDecision(
        task_id=plan.task_id,
        risk_level=cast(Any, "A"),
        outcome=cast(Any, "EXECUTE"),
    )

    result = await dispatch(plan, decision, pending_store=pending_store, audit=fake_audit)

    assert result["outcome"] == "rejected"
    assert pending_store.load_pending() == []
