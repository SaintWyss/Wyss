"""Daemon JSON-RPC y dispatcher fail-closed."""

import asyncio
import grp
import json
import os
import pwd
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from adapters.sqlite_idempotency import SqliteIdempotencyStore
from core.domain import ActorType, AuditEvent, AuditEventType, AuditQuery, Outcome, RiskLevel
from core.domain.ledger import Transaccion
from core.domain.memory import MemoryFact
from core.domain.plan import Action, Plan
from core.domain.policy import PolicyDecision
from core.policy import CognitivePolicyEngine
from core.ports.ledger import LedgerPort
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


class _FakeMemoryStore:
    def __init__(self) -> None:
        self._facts: dict[str, MemoryFact] = {}

    def list_all(self) -> list[MemoryFact]:
        return list(self._facts.values())

    def edit(self, fact_id: str, value: str) -> bool:
        fact = self._facts.get(fact_id)
        if fact is None:
            return False
        self._facts[fact_id] = MemoryFact(
            id=fact.id,
            category=fact.category,
            value=value,
            tier=fact.tier,
            source=fact.source,
            created_at=fact.created_at,
            updated_at="2026-01-02T00:00:00+00:00",
        )
        return True

    def forget(self, fact_id: str) -> bool:
        return self._facts.pop(fact_id, None) is not None

    def add(self, fact: MemoryFact) -> None:
        self._facts[fact.id] = fact


class _FakeLedger:
    def record(self, transaccion: Transaccion) -> None:
        del transaccion

    def balance(self, desde: str, hasta: str) -> tuple[float, float]:
        del desde, hasta
        return 1000.0, 250.0

    def surplus(self, desde: str, hasta: str) -> float:
        del desde, hasta
        return 750.0

    def query_by_category(self, desde: str, hasta: str) -> dict[str, float]:
        del desde, hasta
        return {"super": 250.0}

    def coverage_days(self, desde: str, hasta: str) -> int:
        del desde, hasta
        return 2


class _SpyRunner:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, plan: Plan) -> object:
        del plan
        self.calls += 1
        return object()


class _FakeAuditQuery:
    def __init__(self, events: list[AuditEvent]) -> None:
        self.events = events
        self.query_seen: AuditQuery | None = None

    def query(self, query: AuditQuery) -> list[AuditEvent]:
        self.query_seen = query
        return self.events[: query.limit]


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


@pytest.fixture
def memory_store() -> _FakeMemoryStore:
    return _FakeMemoryStore()


@pytest.fixture
def fake_ledger() -> LedgerPort:
    return _FakeLedger()


@pytest.fixture
def idempotency(tmp_path: Path) -> Iterator[SqliteIdempotencyStore]:
    store = SqliteIdempotencyStore(tmp_path / "client_requests.db")
    try:
        yield store
    finally:
        store.close()


async def _handle_rpc(
    daemon: DaemonServer, method: str, params: dict[str, object]
) -> dict[str, Any]:
    reader = asyncio.StreamReader()
    reader.feed_data(
        json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 7}).encode() + b"\n"
    )
    reader.feed_eof()
    writer = _MemoryWriter()
    await daemon.handle(reader, cast(Any, writer))
    response = json.loads(bytes(writer.data))
    assert response["id"] == 7
    return cast(dict[str, Any], response)


async def _handle_home_rpc(
    daemon: DaemonServer, method: str, params: dict[str, object]
) -> dict[str, Any]:
    reader = asyncio.StreamReader()
    reader.feed_data(
        json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 8}).encode() + b"\n"
    )
    reader.feed_eof()
    writer = _MemoryWriter()
    await daemon.handle_home(reader, cast(Any, writer))
    return cast(dict[str, Any], json.loads(bytes(writer.data)))


async def test_stale_socket_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
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
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=scheduler,
        reaper_interval_s=3600,
    )
    try:
        assert socket_path.exists()
        assert socket_path.stat().st_mode & 0o777 == 0o600
    finally:
        await running.aclose()
    assert not socket_path.exists()


async def test_start_daemon_binds_private_dedicated_home_socket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
    idempotency: SqliteIdempotencyStore,
) -> None:
    owner_socket = tmp_path / "wyss.sock"
    home_socket = tmp_path / "wyss-home.sock"
    tmp_path.chmod(0o750)

    async def fake_start_unix_server(handler: object, path: str) -> _FakeAsyncioServer:
        del handler
        Path(path).write_text("socket", encoding="utf-8")
        return _FakeAsyncioServer()

    monkeypatch.setattr(asyncio, "start_unix_server", fake_start_unix_server)
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)
    running = await start_daemon(
        owner_socket,
        home_socket_path=home_socket,
        home_peer_uid=os.getuid() + 1,
        home_peer_gid=os.getgid(),
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=scheduler,
        runner=_SpyRunner(),
        idempotency=idempotency,
        reaper_interval_s=3600,
    )
    try:
        assert owner_socket.stat().st_mode & 0o777 == 0o600
        assert home_socket.stat().st_mode & 0o777 == 0o660
        assert running.home_server is not None
    finally:
        await running.aclose()

    assert not owner_socket.exists()
    assert not home_socket.exists()


async def test_home_socket_refuses_same_owner_uid(
    tmp_path: Path,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
) -> None:
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)
    with pytest.raises(RuntimeError, match="UID distinto"):
        await start_daemon(
            tmp_path / "owner.sock",
            home_socket_path=tmp_path / "home.sock",
            home_peer_uid=os.getuid(),
            home_peer_gid=os.getgid(),
            engine=engine,
            orchestrator=fake_orchestrator,
            pending_store=pending_store,
            audit=fake_audit,
            routine_store=routine_store,
            memory_store=memory_store,
            ledger=fake_ledger,
            scheduler=scheduler,
        )


async def test_dedicated_home_socket_real_ipc_rejects_admin_method(
    tmp_path: Path,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
    idempotency: SqliteIdempotencyStore,
) -> None:
    owner_socket = tmp_path / "wyss-real.sock"
    home_socket = tmp_path / "wyss-home-real.sock"
    tmp_path.chmod(0o750)
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)
    running = await start_daemon(
        owner_socket,
        home_socket_path=home_socket,
        home_peer_uid=os.getuid() + 1,
        home_peer_gid=os.getgid(),
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=scheduler,
        runner=_SpyRunner(),
        idempotency=idempotency,
        reaper_interval_s=3600,
    )
    try:
        reader, writer = await asyncio.open_unix_connection(str(home_socket))
        writer.write(
            json.dumps(
                {"jsonrpc": "2.0", "method": "audit", "params": {}, "id": "home-real"}
            ).encode()
            + b"\n"
        )
        await writer.drain()
        response = json.loads(await reader.readline())
        writer.close()
        await writer.wait_closed()

        assert response["error"]["code"] == -32001
        assert response["error"]["message"] == "Home peer no autorizado"
        assert response["id"] is None
    finally:
        await running.aclose()


@pytest.mark.skipif(
    not os.environ.get("WYSS_EDGE_SMOKE_USER"),
    reason="requiere identidad local Edge preparada explícitamente",
)
async def test_authorized_edge_uid_can_only_open_home_socket(
    tmp_path: Path,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
    idempotency: SqliteIdempotencyStore,
) -> None:
    edge_user = os.environ["WYSS_EDGE_SMOKE_USER"]
    shared_group = os.environ["WYSS_EDGE_SMOKE_GROUP"]
    runtime_dir = Path(os.environ["WYSS_EDGE_SMOKE_RUNTIME"])
    edge_uid = pwd.getpwnam(edge_user).pw_uid
    shared_gid = grp.getgrnam(shared_group).gr_gid
    owner_socket = tmp_path / "owner-private.sock"
    home_socket = runtime_dir / f"authority-test-{os.getpid()}.sock"
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)
    running = await start_daemon(
        owner_socket,
        home_socket_path=home_socket,
        home_peer_uid=edge_uid,
        home_peer_gid=shared_gid,
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=scheduler,
        runner=_SpyRunner(),
        idempotency=idempotency,
        reaper_interval_s=3600,
    )
    client = """
import json, socket, sys
home, owner = sys.argv[1:3]
s = socket.socket(socket.AF_UNIX)
s.connect(home)
s.sendall(b'{"jsonrpc":"2.0","method":"status","params":{},"id":"edge"}\\n')
response = json.loads(s.recv(8192))
s.close()
owner_errno = None
try:
    o = socket.socket(socket.AF_UNIX)
    o.connect(owner)
except OSError as exc:
    owner_errno = exc.errno
print(json.dumps({"response": response, "owner_errno": owner_errno}))
"""
    try:
        process = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            "-u",
            edge_user,
            "/usr/bin/python3",
            "-c",
            client,
            str(home_socket),
            str(owner_socket),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        assert process.returncode == 0, stderr.decode(errors="replace")
        evidence = json.loads(stdout)
        assert evidence["response"]["result"]["daemon_version"] == "05-04"
        assert evidence["owner_errno"] == 13
    finally:
        await running.aclose()


async def test_ask_round_trip(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
) -> None:
    """ORCH-02: `ask` por JSON-RPC sobre el socket devuelve respuesta del dispatcher."""
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
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


async def test_home_intent_is_idempotent_and_b_confirmation_resolves_once(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
    idempotency: SqliteIdempotencyStore,
) -> None:
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
        idempotency=idempotency,
        runner=_SpyRunner(),
    )
    intent: dict[str, object] = {
        "message_id": "msg-intent-1",
        "request_id": "request-1",
        "source": "panel:living",
        "text": "mover archivo",
        "input": "text",
    }

    first = await _handle_rpc(daemon, "home.intent", intent)
    replay = await _handle_rpc(daemon, "home.intent", intent)

    assert first["result"] == replay["result"]
    proposed = first["result"]
    assert proposed["outcome"] == "pending"
    assert proposed["risk"] == "B"
    assert proposed["summary"] == "mover archivo"
    assert proposed["steps"] == [{"description": "file.move", "target": "/tmp/source.txt"}]
    assert proposed["revision"] == 1
    assert len(pending_store.load_pending()) == 1

    answer = {
        "message_id": "msg-answer-1",
        "plan_id": proposed["pending_id"],
        "decision": "approve",
        "confirmation": "s",
        "expected_revision": 1,
        "source": "panel:living",
    }
    revision_conflict = await _handle_rpc(
        daemon,
        "home.plan.answer",
        {**answer, "message_id": "msg-answer-stale", "expected_revision": 2},
    )
    assert revision_conflict["result"]["outcome"] == "conflict"
    assert revision_conflict["result"]["revision"] == 1

    resolved = await _handle_rpc(daemon, "home.plan.answer", answer)
    resolved_replay = await _handle_rpc(daemon, "home.plan.answer", answer)

    assert resolved["result"] == resolved_replay["result"]
    assert resolved["result"]["outcome"] == "resolved"
    assert resolved["result"]["policy_reevaluated"] is True
    assert resolved["result"]["revision"] == 2
    confirmed = pending_store.load(str(proposed["pending_id"]))
    assert confirmed is not None
    assert confirmed.status == "confirmed"

    stale = await _handle_rpc(
        daemon,
        "home.plan.answer",
        {**answer, "message_id": "msg-answer-2", "source": "android:owner"},
    )
    assert stale["result"]["outcome"] == "already_resolved"
    assert stale["result"]["revision"] == 2


async def test_home_socket_is_method_scoped_and_derives_edge_identity(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
    idempotency: SqliteIdempotencyStore,
) -> None:
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
        idempotency=idempotency,
        runner=_SpyRunner(),
        home_rate_limit_per_second=4,
    )

    forbidden = await _handle_home_rpc(daemon, "audit", {"include_payload": True})
    assert forbidden["error"]["code"] == -32601

    nested: dict[str, object] = {}
    cursor = nested
    for _ in range(17):
        child: dict[str, object] = {}
        cursor["child"] = child
        cursor = child
    too_deep = await _handle_home_rpc(daemon, "status", nested)
    assert too_deep["error"]["code"] == -32602

    closed_error = await _handle_home_rpc(
        daemon,
        "home.intent",
        {"message_id": "invalid-without-required-fields"},
    )
    assert closed_error["error"]["message"] == "Home request failed"

    accepted = await _handle_home_rpc(
        daemon,
        "home.intent",
        {
            "message_id": "scoped-1",
            "request_id": "request-scoped-1",
            "source": "forged-admin",
            "text": "mover archivo",
            "input": "text",
        },
    )
    assert "error" not in accepted
    received = next(
        event for event in fake_audit.events if event.event_type is AuditEventType.COMMAND_RECEIVED
    )
    assert received.actor_id == "home-edge"

    limited = await _handle_home_rpc(daemon, "status", {})
    assert limited["error"]["code"] == -32029


async def test_first_concurrent_home_answer_wins_once(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
    idempotency: SqliteIdempotencyStore,
) -> None:
    runner = _SpyRunner()
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
        idempotency=idempotency,
        runner=runner,
    )
    proposed = await _handle_rpc(
        daemon,
        "home.intent",
        {
            "message_id": "race-intent",
            "request_id": "race-request",
            "source": "panel:living",
            "text": "mover archivo",
            "input": "text",
        },
    )
    plan_id = str(proposed["result"]["pending_id"])
    base = {
        "plan_id": plan_id,
        "decision": "approve",
        "confirmation": "s",
        "expected_revision": 1,
    }

    panel, android = await asyncio.gather(
        _handle_rpc(
            daemon,
            "home.plan.answer",
            {**base, "message_id": "race-panel", "source": "panel:living"},
        ),
        _handle_rpc(
            daemon,
            "home.plan.answer",
            {**base, "message_id": "race-android", "source": "android:owner"},
        ),
    )

    outcomes = {panel["result"]["outcome"], android["result"]["outcome"]}
    assert outcomes == {"resolved", "already_resolved"}
    assert runner.calls == 1


async def test_home_c_requires_literal_and_d_never_becomes_pending(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
    idempotency: SqliteIdempotencyStore,
) -> None:
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
        idempotency=idempotency,
        runner=_SpyRunner(),
    )
    c_intent = await _handle_rpc(
        daemon,
        "home.intent",
        {
            "message_id": "msg-c",
            "request_id": "request-c",
            "source": "android:owner",
            "text": "borrar archivo",
            "input": "text",
        },
    )
    plan_id = str(c_intent["result"]["pending_id"])
    weak = await _handle_rpc(
        daemon,
        "home.plan.answer",
        {
            "message_id": "msg-c-weak",
            "plan_id": plan_id,
            "decision": "approve",
            "confirmation": "s",
            "expected_revision": 1,
            "source": "android:owner",
        },
    )
    assert weak["result"]["outcome"] == "confirmation_required"
    still_pending = pending_store.load(plan_id)
    assert still_pending is not None
    assert still_pending.status == "pending"

    strong = await _handle_rpc(
        daemon,
        "home.plan.answer",
        {
            "message_id": "msg-c-strong",
            "plan_id": plan_id,
            "decision": "approve",
            "confirmation": "CONFIRMAR",
            "expected_revision": 1,
            "source": "panel:living",
        },
    )
    assert strong["result"]["outcome"] == "resolved"

    denied = await _handle_rpc(
        daemon,
        "home.intent",
        {
            "message_id": "msg-d",
            "request_id": "request-d",
            "source": "panel:living",
            "text": "formatear disco",
            "input": "text",
        },
    )
    assert denied["result"]["outcome"] == "rejected"
    assert "pending_id" not in denied["result"]


async def test_home_rejection_resolves_without_execution(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
    idempotency: SqliteIdempotencyStore,
) -> None:
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
        idempotency=idempotency,
    )
    proposed = await _handle_rpc(
        daemon,
        "home.intent",
        {
            "message_id": "msg-reject-intent",
            "request_id": "request-reject",
            "source": "panel:living",
            "text": "mover archivo",
            "input": "text",
        },
    )
    plan_id = str(proposed["result"]["pending_id"])

    rejected = await _handle_rpc(
        daemon,
        "home.plan.answer",
        {
            "message_id": "msg-reject-answer",
            "plan_id": plan_id,
            "decision": "reject",
            "confirmation": "",
            "expected_revision": 1,
            "source": "panel:living",
        },
    )

    assert rejected["result"]["outcome"] == "resolved"
    assert rejected["result"]["accepted"] is False
    assert rejected["result"]["policy_reevaluated"] is True
    stored_rejection = pending_store.load(plan_id)
    assert stored_rejection is not None
    assert stored_rejection.status == "rejected"


async def test_audit_rpc_queries_port_with_closed_filters(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
) -> None:
    event = AuditEvent.new(
        task_id="task-audit",
        actor_type=ActorType.SYSTEM,
        actor_id="daemon",
        event_type=AuditEventType.TASK_COMPLETED,
        message="terminado",
        payload={"private": "detalle"},
    )
    query_port = _FakeAuditQuery([event])
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        audit_query=query_port,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
    )

    response = await _handle_rpc(
        daemon,
        "audit",
        {"limit": 10, "task_id": "task-audit", "event_type": "task.completed"},
    )

    assert "error" not in response
    assert response["result"]["events"] == [
        {
            "event_id": event.event_id,
            "task_id": "task-audit",
            "actor_type": "system",
            "actor_id": "daemon",
            "event_type": "task.completed",
            "message": "terminado",
            "created_at": event.created_at.isoformat(),
        }
    ]
    assert query_port.query_seen == AuditQuery(
        limit=10,
        task_id="task-audit",
        event_type=AuditEventType.TASK_COMPLETED,
    )


async def test_audit_rpc_rejects_out_of_range_limit(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
) -> None:
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        audit_query=_FakeAuditQuery([]),
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
    )

    response = await _handle_rpc(daemon, "audit", {"limit": 201})

    assert response["error"]["code"] == -32000
    assert "entre 1 y 200" in response["error"]["message"]


async def test_intake_propose_floors_a_to_pending_b_and_never_executes(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
) -> None:
    runner = _SpyRunner()
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
        runner=runner,
    )

    response = await _handle_rpc(daemon, "intake.propose", {"instruction": "leer /tmp/a"})

    assert "error" not in response
    assert response["result"]["outcome"] == "pending"
    assert response["result"]["risk_level"] == "B"
    assert runner.calls == 0
    pending = pending_store.load_pending()
    assert len(pending) == 1
    assert pending[0].risk_level == "B"
    received = next(
        event for event in fake_audit.events if event.event_type == AuditEventType.COMMAND_RECEIVED
    )
    assert received.actor_type is ActorType.SYSTEM
    assert received.actor_id == "intake"
    assert received.message == "[intake externo] leer /tmp/a"


@pytest.mark.parametrize(
    ("instruction", "expected_level"),
    [
        ("mover /tmp/a /tmp/b", "B"),
        ("borrar /tmp/a", "C"),
    ],
)
async def test_intake_propose_preserves_b_or_c_as_pending(
    instruction: str,
    expected_level: str,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
) -> None:
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
    )

    response = await _handle_rpc(daemon, "intake.propose", {"instruction": instruction})

    assert "error" not in response
    assert response["result"]["outcome"] == "pending"
    assert response["result"]["risk_level"] == expected_level
    pending = pending_store.load_pending()
    assert len(pending) == 1
    assert pending[0].risk_level == expected_level


async def test_intake_propose_preserves_d_reject(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
) -> None:
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
    )

    response = await _handle_rpc(daemon, "intake.propose", {"instruction": "formatear disco"})

    assert "error" not in response
    assert response["result"]["outcome"] == "rejected"
    assert pending_store.load_pending() == []


async def test_intake_propose_empty_instruction_returns_rpc_error(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
) -> None:
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
    )

    response = await _handle_rpc(daemon, "intake.propose", {"instruction": "   "})

    assert "error" in response
    assert response["error"]["message"] == "instruction requerido"
    assert pending_store.load_pending() == []


async def test_routine_handlers_round_trip_via_rpc(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
) -> None:
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
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


async def test_memory_handlers_round_trip_via_rpc(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
) -> None:
    memory_store.add(
        MemoryFact(
            id="fact-1",
            category="preferences",
            value="cafe sin azucar",
            tier="owner",
            source="owner",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
    )
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=scheduler,
    )

    listed = await _handle_rpc(daemon, "memory.list", {})
    facts = listed["result"]["facts"]
    assert facts == [
        {
            "id": "fact-1",
            "category": "preferences",
            "value": "cafe sin azucar",
            "tier": "owner",
            "source": "owner",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        }
    ]

    edited = await _handle_rpc(daemon, "memory.edit", {"fact_id": "fact-1", "value": "mate amargo"})
    assert edited["result"] == {"ok": True}
    assert memory_store.list_all()[0].value == "mate amargo"

    missing_edit = await _handle_rpc(daemon, "memory.edit", {"fact_id": "missing", "value": "x"})
    assert missing_edit["result"] == {"ok": False}

    forgotten = await _handle_rpc(daemon, "memory.forget", {"fact_id": "fact-1"})
    assert forgotten["result"] == {"ok": True}
    assert memory_store.list_all() == []

    missing_forget = await _handle_rpc(daemon, "memory.forget", {"fact_id": "missing"})
    assert missing_forget["result"] == {"ok": False}


async def test_routine_add_invalid_schedule_returns_rpc_error(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
) -> None:
    scheduler = _routine_scheduler(engine, pending_store, fake_audit, routine_store)
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
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
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
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
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=scheduler,
        reaper_interval_s=3600,
    )

    await asyncio.wait_for(running.aclose(), timeout=1)

    assert waits == [False]
    assert not socket_path.exists()


async def test_digest_today_rpc_returns_markdown_and_audits(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
) -> None:
    plan = Plan(
        task_id="digest-pending",
        summary="mover",
        steps=(Action("file.move", "/tmp/a"),),
        rationale="test",
    )
    decision = PolicyDecision(
        task_id=plan.task_id,
        risk_level=RiskLevel.B,
        outcome=Outcome.CONFIRM_SIMPLE,
    )
    pending_store.save(plan, decision, ttl_seconds=3600)
    routine_store.add("rutina digest", "cron", "0 8 * * *", _plan_json())
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
    )

    response = await _handle_rpc(daemon, "digest.today", {})

    assert "error" not in response
    result = response["result"]
    assert isinstance(result["markdown"], str)
    assert "## Pendientes de bandeja" in result["markdown"]
    assert "## Finanzas Pellegrini" in result["markdown"]
    assert "## Rutinas" in result["markdown"]
    assert isinstance(result["generated_at"], str)
    event = fake_audit.events[-1]
    assert event.event_type == AuditEventType.DIGEST_GENERATED
    assert event.actor_id == "digest"
    assert "date" in event.payload


async def test_digest_today_empty_state_and_no_dispatch(
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    routine_store: RoutineStore,
    memory_store: _FakeMemoryStore,
    fake_audit: FakeAudit,
    fake_orchestrator: FakeOrchestrator,
    fake_ledger: LedgerPort,
) -> None:
    runner = _SpyRunner()
    daemon = DaemonServer(
        engine=engine,
        orchestrator=fake_orchestrator,
        pending_store=pending_store,
        audit=fake_audit,
        routine_store=routine_store,
        memory_store=memory_store,
        ledger=fake_ledger,
        scheduler=_routine_scheduler(engine, pending_store, fake_audit, routine_store),
        runner=runner,
    )

    response = await _handle_rpc(daemon, "digest.today", {})

    assert "error" not in response
    markdown = str(response["result"]["markdown"])
    assert "Sin pendientes" in markdown
    assert "Sin rutinas" in markdown
    assert runner.calls == 0
    assert pending_store.load_pending() == []


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
