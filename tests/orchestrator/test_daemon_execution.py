"""Loop E2E del daemon con ejecución real: ask → policy → confirm → execute → audit.

Cierra el gap RC v0.1: el daemon recibe un `PlanRunner` (PlanExecutor real sobre
adapters reales en tmp_path) y `confirm` ejecuta de verdad, con journal y evidencia
de auditoría. Sin runner inyectado el shape histórico se preserva (compat).
"""

import asyncio
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from core.domain import AuditEventType
from core.domain.ledger import Transaccion
from core.domain.memory import MemoryFact
from core.domain.plan import Action, Plan
from core.orchestrator.intent import IntentCategory, IntentClassification
from core.policy import CognitivePolicyEngine
from execution.executor import PlanExecutor
from execution.filesystem import FileSystemAdapter
from execution.git import GitAdapter
from execution.guard import DeterministicExecutionGuard
from execution.journal import UndoJournal
from execution.shell import ShellAdapter
from orchestrator.daemon import DaemonServer
from orchestrator.pending_store import PendingStore
from orchestrator.routine_store import RoutineStore
from orchestrator.scheduler import RoutineScheduler

from .conftest import FakeAudit


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
    def list_all(self) -> list[MemoryFact]:
        return []

    def edit(self, fact_id: str, value: str) -> bool:
        del fact_id, value
        return False

    def forget(self, fact_id: str) -> bool:
        del fact_id
        return False


class _FakeLedger:
    def record(self, transaccion: Transaccion) -> None:
        del transaccion

    def balance(self, desde: str, hasta: str) -> tuple[float, float]:
        del desde, hasta
        return 0.0, 0.0

    def surplus(self, desde: str, hasta: str) -> float:
        del desde, hasta
        return 0.0

    def query_by_category(self, desde: str, hasta: str) -> dict[str, float]:
        del desde, hasta
        return {}

    def coverage_days(self, desde: str, hasta: str) -> int:
        del desde, hasta
        return 0


async def _rpc(daemon: DaemonServer, method: str, params: dict[str, object]) -> dict[str, Any]:
    reader = asyncio.StreamReader()
    reader.feed_data(
        json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": 1}).encode() + b"\n"
    )
    reader.feed_eof()
    writer = _MemoryWriter()
    await daemon.handle(reader, cast(Any, writer))
    response = json.loads(bytes(writer.data))
    assert "error" not in response, response
    return cast(dict[str, Any], response["result"])


class _PlanOrchestrator:
    """OrchestratorPort fake que devuelve un plan fijo (el LLM real se prueba aparte)."""

    def __init__(self, plan: Plan) -> None:
        self._plan = plan

    async def classify_intent(self, instruction: str) -> IntentClassification:
        del instruction
        return IntentClassification(IntentCategory.FILE_OPERATION, 0.95, False)

    async def draft_plan(self, instruction: str, intent: IntentClassification) -> Plan:
        del instruction, intent
        return self._plan

    async def health_check(self) -> bool:
        return True


@pytest.fixture
def journal(tmp_path: Path) -> Iterator[UndoJournal]:
    j = UndoJournal(tmp_path / "journal.db", backup_base_dir=tmp_path / "undo_backups")
    try:
        yield j
    finally:
        j.close()


def _runner(
    engine: CognitivePolicyEngine, audit: FakeAudit, journal: UndoJournal, tmp_path: Path
) -> PlanExecutor:
    guard = DeterministicExecutionGuard(engine, cast(Any, audit))
    return PlanExecutor(
        filesystem=FileSystemAdapter(guard, audit, journal),
        shell=ShellAdapter(cast(Any, audit), guard),
        git=GitAdapter(cast(Any, audit), tmp_path, guard),
        journal=journal,
        audit=audit,
    )


def _daemon(
    engine: CognitivePolicyEngine,
    plan: Plan,
    pending_store: PendingStore,
    audit: FakeAudit,
    runner: PlanExecutor | None,
) -> DaemonServer:
    return DaemonServer(
        engine=engine,
        orchestrator=_PlanOrchestrator(plan),
        pending_store=pending_store,
        audit=audit,
        routine_store=cast(RoutineStore, object()),
        memory_store=_FakeMemoryStore(),
        ledger=_FakeLedger(),
        scheduler=cast(RoutineScheduler, object()),
        runner=runner,
    )


async def test_confirm_executes_file_write_end_to_end(
    tmp_path: Path,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    journal: UndoJournal,
) -> None:
    """file.write (C) pide CONFIRMAR; el confirm ejecuta, verifica y audita."""
    target = tmp_path / "nota.txt"
    plan = Plan(
        task_id="rc-smoke",
        summary="crear nota de prueba",
        steps=(Action("file.write", str(target), {"content": "hola desde wyss rc"}),),
        rationale="smoke RC v0.1",
    )
    runner = _runner(engine, fake_audit, journal, tmp_path)
    daemon = _daemon(engine, plan, pending_store, fake_audit, runner)

    asked = await _rpc(daemon, "ask", {"instruction": f"crear nota en {target}"})
    assert asked["outcome"] == "pending"
    assert not target.exists()  # nada se ejecuta antes de confirmar

    confirmed = await _rpc(
        daemon, "confirm", {"pending_id": asked["pending_id"], "response": "CONFIRMAR"}
    )
    assert confirmed["accepted"] is True
    assert confirmed["success"] is True
    assert str(confirmed["execution_id"]).startswith("exec-rc-smoke-")

    assert target.read_text(encoding="utf-8") == "hola desde wyss rc"
    event_types = [event.event_type for event in fake_audit.events]
    # El path pending audita la decisión de política dentro de CONFIRMATION_REQUESTED
    # (payload risk_level/outcome); POLICY_DECISION como evento aparece en reject/queued.
    for expected in (
        AuditEventType.COMMAND_RECEIVED,
        AuditEventType.PLAN_CREATED,
        AuditEventType.CONFIRMATION_REQUESTED,
        AuditEventType.CONFIRMATION_ANSWERED,
        AuditEventType.TASK_COMPLETED,
    ):
        assert expected in event_types


async def test_wrong_confirmation_does_not_execute(
    tmp_path: Path,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    journal: UndoJournal,
) -> None:
    """Nivel C exige la palabra literal CONFIRMAR; 's' no alcanza y nada se escribe."""
    target = tmp_path / "nota.txt"
    plan = Plan(
        task_id="rc-neg",
        summary="crear nota",
        steps=(Action("file.write", str(target), {"content": "no"}),),
        rationale="test",
    )
    runner = _runner(engine, fake_audit, journal, tmp_path)
    daemon = _daemon(engine, plan, pending_store, fake_audit, runner)

    asked = await _rpc(daemon, "ask", {"instruction": "crear nota"})
    denied = await _rpc(daemon, "confirm", {"pending_id": asked["pending_id"], "response": "s"})
    assert denied["accepted"] is False
    assert not target.exists()


async def test_queued_read_executes_and_surfaces_output(
    tmp_path: Path,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    journal: UndoJournal,
) -> None:
    """PR-11: A-level ejecuta directo y la salida de la lectura llega al owner
    en la respuesta del daemon (outputs)."""
    target = tmp_path / "x.txt"
    target.write_text("hola operador", encoding="utf-8")
    plan = Plan(
        task_id="rc-read",
        summary="leer archivo",
        steps=(Action("file.read", str(target)),),
        rationale="test",
    )
    runner = _runner(engine, fake_audit, journal, tmp_path)
    daemon = _daemon(engine, plan, pending_store, fake_audit, runner)

    asked = await _rpc(daemon, "ask", {"instruction": "leer archivo"})
    assert asked["outcome"] == "executed"
    assert asked["success"] is True
    assert asked["outputs"] == ["hola operador"]
    assert AuditEventType.TASK_COMPLETED in [e.event_type for e in fake_audit.events]


async def test_queued_read_missing_file_reports_honest_failure(
    tmp_path: Path,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    journal: UndoJournal,
) -> None:
    """Leer un archivo inexistente falla honesto (success=False + TASK_FAILED)."""
    plan = Plan(
        task_id="rc-read-miss",
        summary="leer archivo",
        steps=(Action("file.read", str(tmp_path / "no-existe.txt")),),
        rationale="test",
    )
    runner = _runner(engine, fake_audit, journal, tmp_path)
    daemon = _daemon(engine, plan, pending_store, fake_audit, runner)

    asked = await _rpc(daemon, "ask", {"instruction": "leer archivo"})
    assert asked["outcome"] == "executed"
    assert asked["success"] is False
    assert "not found" in asked["detail"]
    assert AuditEventType.TASK_FAILED in [e.event_type for e in fake_audit.events]


async def test_without_runner_keeps_legacy_shape(
    tmp_path: Path,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
) -> None:
    """Sin runner el daemon falla cerrado y no afirma una ejecución inexistente."""
    target = tmp_path / "nota.txt"
    plan = Plan(
        task_id="rc-legacy",
        summary="crear nota",
        steps=(Action("file.write", str(target), {"content": "x"}),),
        rationale="test",
    )
    daemon = _daemon(engine, plan, pending_store, fake_audit, None)

    asked = await _rpc(daemon, "ask", {"instruction": "crear nota"})
    confirmed = await _rpc(
        daemon, "confirm", {"pending_id": asked["pending_id"], "response": "CONFIRMAR"}
    )
    assert confirmed["accepted"] is False
    assert confirmed["reason"] == "executor no disponible"
    assert "success" not in confirmed
    assert not target.exists()
    loaded = pending_store.load(str(asked["pending_id"]))
    assert loaded is not None
    assert loaded.status == "pending"


async def test_expired_proposal_not_executed(
    tmp_path: Path,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    journal: UndoJournal,
) -> None:
    """PR-08: una propuesta vencida (aunque el reaper no haya corrido) no se ejecuta."""
    from core.domain.policy import PolicyDecision
    from core.domain.risk import Outcome, RiskLevel

    target = tmp_path / "no.txt"
    plan = Plan(
        task_id="rc-exp",
        summary="crear nota",
        steps=(Action("file.write", str(target), {"content": "no"}),),
        rationale="test",
    )
    decision = PolicyDecision(
        task_id="rc-exp", risk_level=RiskLevel.C, outcome=Outcome.CONFIRM_STRONG
    )
    pending_id = pending_store.save(plan, decision, ttl_seconds=-5)  # ya vencida
    runner = _runner(engine, fake_audit, journal, tmp_path)
    daemon = _daemon(engine, plan, pending_store, fake_audit, runner)

    result = await _rpc(daemon, "confirm", {"pending_id": pending_id, "response": "CONFIRMAR"})
    assert result["accepted"] is False
    assert result["reason"] == "propuesta expirada"
    assert not target.exists()


async def test_double_confirm_executes_only_once(
    tmp_path: Path,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    journal: UndoJournal,
) -> None:
    """PR-08: el segundo confirm sobre el mismo pending NO re-ejecuta (resolve atómico:
    UPDATE ... WHERE status='pending' → el segundo caller ve status='confirmed' y corta).
    """
    target = tmp_path / "una-vez.txt"
    plan = Plan(
        task_id="rc-double",
        summary="crear nota",
        steps=(Action("file.write", str(target), {"content": "una vez"}),),
        rationale="test",
    )
    runner = _runner(engine, fake_audit, journal, tmp_path)
    daemon = _daemon(engine, plan, pending_store, fake_audit, runner)

    asked = await _rpc(daemon, "ask", {"instruction": "crear nota"})
    first = await _rpc(
        daemon, "confirm", {"pending_id": asked["pending_id"], "response": "CONFIRMAR"}
    )
    second = await _rpc(
        daemon, "confirm", {"pending_id": asked["pending_id"], "response": "CONFIRMAR"}
    )

    assert first["accepted"] is True
    assert second["accepted"] is False
    assert second["reason"] == "pending no encontrado"
    completed = [e for e in fake_audit.events if e.event_type is AuditEventType.TASK_COMPLETED]
    assert len(completed) == 1  # ejecutó exactamente una vez


async def test_confirm_escalated_risk_requires_stronger_word(
    tmp_path: Path,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    journal: UndoJournal,
) -> None:
    """PR-08: si la re-evaluación sube el riesgo (pending dice B, plan es C), la palabra
    exigida es la del nivel NUEVO: 's' no alcanza, CONFIRMAR sí."""
    from core.domain.policy import PolicyDecision
    from core.domain.risk import Outcome, RiskLevel

    target = tmp_path / "escalada.txt"
    plan = Plan(
        task_id="rc-esc",
        summary="crear nota",
        steps=(Action("file.write", str(target), {"content": "x"}),),  # C real
        rationale="test",
    )
    # pending guardado con nivel B mentido (como si la política hubiera cambiado después)
    stale = PolicyDecision(task_id="rc-esc", risk_level=RiskLevel.B, outcome=Outcome.CONFIRM_SIMPLE)
    pending_id = pending_store.save(plan, stale, ttl_seconds=600)
    runner = _runner(engine, fake_audit, journal, tmp_path)
    daemon = _daemon(engine, plan, pending_store, fake_audit, runner)

    weak = await _rpc(daemon, "confirm", {"pending_id": pending_id, "response": "s"})
    assert weak["accepted"] is False
    assert "re-evaluado" in weak["reason"]
    assert not target.exists()

    strong = await _rpc(daemon, "confirm", {"pending_id": pending_id, "response": "CONFIRMAR"})
    assert strong["accepted"] is True
    assert target.exists()


async def test_confirm_reevaluates_and_rejects_now_dangerous(
    tmp_path: Path,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    journal: UndoJournal,
) -> None:
    """PR-08 (defensa en profundidad): aunque el pending diga C, si el plan es D la
    re-evaluación al confirmar lo rechaza. El store no es la autoridad; la política sí.
    """
    from core.domain.policy import PolicyDecision
    from core.domain.risk import Outcome, RiskLevel

    plan = Plan(
        task_id="rc-sneak",
        summary="borrar passwd",
        steps=(Action("file.delete", "/etc/passwd"),),
        rationale="test",
    )
    # pending guardado con nivel C mentido (como si un caller lo hubiera degradado)
    faked = PolicyDecision(
        task_id="rc-sneak", risk_level=RiskLevel.C, outcome=Outcome.CONFIRM_STRONG
    )
    pending_id = pending_store.save(plan, faked, ttl_seconds=600)
    runner = _runner(engine, fake_audit, journal, tmp_path)
    daemon = _daemon(engine, plan, pending_store, fake_audit, runner)

    result = await _rpc(daemon, "confirm", {"pending_id": pending_id, "response": "CONFIRMAR"})
    assert result["accepted"] is False
    assert "política" in result["reason"]
    rejected = pending_store.load(pending_id)
    assert rejected is not None
    assert rejected.status == "rejected"
    assert rejected.revision == 2

    second = await _rpc(daemon, "confirm", {"pending_id": pending_id, "response": "CONFIRMAR"})
    assert second["accepted"] is False
    assert second["reason"] == "pending no encontrado"


async def test_d_reevaluation_reports_expired_if_ttl_wins_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    fake_audit: FakeAudit,
    journal: UndoJournal,
) -> None:
    from core.domain.policy import PolicyDecision
    from core.domain.risk import Outcome, RiskLevel

    plan = Plan(
        task_id="rc-d-ttl",
        summary="borrar passwd",
        steps=(Action("file.delete", "/etc/passwd"),),
        rationale="test",
    )
    pending_id = pending_store.save(
        plan,
        PolicyDecision("rc-d-ttl", RiskLevel.C, Outcome.CONFIRM_STRONG),
        ttl_seconds=600,
    )
    original_resolve = pending_store.resolve

    def cross_ttl(*args: Any, **kwargs: Any) -> object:
        with sqlite3.connect(tmp_path / "pending.db") as conn:
            conn.execute(
                "UPDATE pending_proposals SET expires_at=? WHERE id=?",
                ("2000-01-01T00:00:00+00:00", pending_id),
            )
        return original_resolve(*args, **kwargs)

    monkeypatch.setattr(pending_store, "resolve", cross_ttl)
    daemon = _daemon(
        engine,
        plan,
        pending_store,
        fake_audit,
        _runner(engine, fake_audit, journal, tmp_path),
    )

    result = await _rpc(
        daemon,
        "confirm",
        {"pending_id": pending_id, "response": "CONFIRMAR"},
    )

    assert result["accepted"] is False
    assert result["reason"] == "propuesta expirada"
    expired = pending_store.load(pending_id)
    assert expired is not None
    assert expired.status == "expired"
    assert expired.revision == 2
