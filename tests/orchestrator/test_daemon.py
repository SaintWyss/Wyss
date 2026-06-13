"""Daemon JSON-RPC y dispatcher fail-closed."""

import asyncio
import json
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

    running = await start_daemon(
        socket_path,
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
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
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
) -> None:
    """ORCH-02: `ask` por JSON-RPC sobre el socket devuelve respuesta del dispatcher."""
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
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
