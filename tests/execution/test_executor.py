"""Tests de PlanExecutor (EXEC-03 rollback + EXEC-02 enforcement, D-69).

TDD RED: estos tests deben fallar hasta que exista src/execution/executor.py.

Cubre:
- dispatch por prefijo de action.type (file/shell/git/unknown)
- ABORT: rollback en orden inverso vía journal.restore
- RETRY: adapter.execute llamado exactamente max_attempts veces antes de fallar
- ESCALATE: audit recibe TASK_FAILED + journal.restore NO se llama

asyncio_mode="auto" en pyproject.toml — no necesitan @pytest.mark.asyncio.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.domain.audit import AuditEventType
from core.domain.execution import ToolResult, Verification
from core.domain.plan import Action, ErrorPolicy, Plan, RetryParams
from execution.executor import PlanExecutor

# ---------------------------------------------------------------------------
# Helpers — adaptadores falsos deterministas
# ---------------------------------------------------------------------------


def _make_plan(
    *actions: Action, task_id: str = "task-test-1"
) -> Plan:
    return Plan(
        task_id=task_id,
        summary="test plan",
        steps=tuple(actions),
        rationale="testing",
    )


def _ok_adapter(
    journal_entry_id: str = "entry-ok",
    verify_passed: bool = True,
) -> MagicMock:
    """Adapter fake que siempre tiene éxito."""
    adapter = MagicMock()
    adapter.execute = AsyncMock(
        return_value=ToolResult(
            success=True,
            detail="ok",
            payload={"journal_entry_id": journal_entry_id},
        )
    )
    adapter.verify = AsyncMock(
        return_value=Verification(passed=verify_passed, detail="ok")
    )
    return adapter


def _fail_adapter(
    journal_entry_id: str = "entry-fail",
    verify_passed: bool = False,
) -> MagicMock:
    """Adapter fake que siempre falla en execute."""
    adapter = MagicMock()
    adapter.execute = AsyncMock(
        return_value=ToolResult(
            success=False,
            detail="fail",
            payload={"journal_entry_id": journal_entry_id},
        )
    )
    adapter.verify = AsyncMock(
        return_value=Verification(passed=verify_passed, detail="failed verify")
    )
    return adapter


# ---------------------------------------------------------------------------
# Test 1: dispatch por prefijo de action.type
# ---------------------------------------------------------------------------


async def test_dispatch_by_type_prefix() -> None:
    """_adapter_for devuelve el adapter correcto por prefijo y eleva ValueError para desconocido."""
    filesystem = _ok_adapter("e1")
    shell = _ok_adapter("e2")
    git = _ok_adapter("e3")
    journal = MagicMock()
    journal.restore = MagicMock(return_value=True)
    journal.mark_applied = MagicMock()
    audit = MagicMock()
    audit.log = MagicMock()

    executor = PlanExecutor(
        filesystem=filesystem,
        shell=shell,
        git=git,
        journal=journal,
        audit=audit,
    )

    # El método interno _adapter_for debe existir
    assert executor._adapter_for(Action(type="file.write", target="/x")) is filesystem
    assert executor._adapter_for(Action(type="shell.run", target="ls")) is shell
    assert executor._adapter_for(Action(type="git.push", target="origin")) is git

    with pytest.raises(ValueError, match="no adapter for action type"):
        executor._adapter_for(Action(type="calendar.create", target="x"))


async def test_dispatch_notion_prefix_to_injected_tool() -> None:
    """notion.* se despacha al Tool notion inyectado, no a file/shell/git."""
    filesystem = _ok_adapter("file-entry")
    shell = _ok_adapter("shell-entry")
    git = _ok_adapter("git-entry")
    notion = _ok_adapter("notion-entry")
    journal = MagicMock()
    journal.restore = MagicMock(return_value=True)
    journal.mark_applied = MagicMock()
    audit = MagicMock()
    audit.log = MagicMock()

    executor = PlanExecutor(
        filesystem=filesystem,
        shell=shell,
        git=git,
        journal=journal,
        audit=audit,
        notion=notion,
    )
    plan = _make_plan(Action(type="notion.read_page", target="page-123"))

    result = await executor.run(plan)

    assert result.success
    notion.execute.assert_awaited_once_with(plan.steps[0])
    filesystem.execute.assert_not_called()
    shell.execute.assert_not_called()
    git.execute.assert_not_called()


async def test_notion_without_adapter_returns_legible_failure() -> None:
    """Si no se inyecta NotionTool, notion.* falla como ToolResult accionable."""
    filesystem = _ok_adapter("file-entry")
    shell = _ok_adapter("shell-entry")
    git = _ok_adapter("git-entry")
    journal = MagicMock()
    journal.restore = MagicMock(return_value=True)
    journal.mark_applied = MagicMock()
    audit = MagicMock()
    audit.log = MagicMock()

    executor = PlanExecutor(
        filesystem=filesystem,
        shell=shell,
        git=git,
        journal=journal,
        audit=audit,
    )
    plan = _make_plan(Action(type="notion.read_page", target="page-123"))

    result = await executor.run(plan)

    assert not result.success
    assert result.failed_step == 0
    assert "NOTION_TOKEN" in result.detail
    assert "Notion no configurado" in result.detail
    filesystem.execute.assert_not_called()
    shell.execute.assert_not_called()
    git.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: ABORT rollback en orden inverso
# ---------------------------------------------------------------------------


async def test_abort_rolls_back_in_reverse() -> None:
    """ABORT policy: step 2 falla → se restaura el journal entry del step 1 (orden inverso).

    step 1: file.write → entry-1, éxito
    step 2: file.write → entry-2, falla
    Expect: journal.restore("entry-1") llamado 1 vez; "entry-2" NO restaurado (no aplicado).
    """
    step1 = Action(type="file.write", target="/a", on_error=ErrorPolicy.ABORT)
    step2 = Action(type="file.write", target="/b", on_error=ErrorPolicy.ABORT)
    plan = _make_plan(step1, step2)

    # El filesystem adapter se llama en orden: primero step1 (ok), luego step2 (fail)
    filesystem = MagicMock()
    filesystem.execute = AsyncMock(
        side_effect=[
            ToolResult(success=True, detail="ok", payload={"journal_entry_id": "entry-1"}),
            ToolResult(success=False, detail="fail", payload={"journal_entry_id": "entry-2"}),
        ]
    )
    filesystem.verify = AsyncMock(
        side_effect=[
            Verification(passed=True, detail="ok"),
        ]
    )

    journal = MagicMock()
    journal.restore = MagicMock(return_value=True)
    journal.mark_applied = MagicMock()

    audit = MagicMock()
    audit.log = MagicMock()

    executor = PlanExecutor(
        filesystem=filesystem,
        shell=MagicMock(),
        git=MagicMock(),
        journal=journal,
        audit=audit,
    )

    result = await executor.run(plan)

    # Plan falló
    assert not result.success

    # journal.restore llamado con "entry-1" (el único aplicado)
    journal.restore.assert_called_once_with("entry-1")


# ---------------------------------------------------------------------------
# Test 3: RETRY respeta max_attempts
# ---------------------------------------------------------------------------


async def test_retry_respects_max_attempts() -> None:
    """RETRY policy: adapter siempre falla → execute() llamado exactamente max_attempts veces."""
    step = Action(
        type="file.write",
        target="/x",
        on_error=ErrorPolicy.RETRY,
        retry_params=RetryParams(max_attempts=3, backoff_base_s=0.0, backoff_max_s=0.0),
    )
    plan = _make_plan(step)

    filesystem = MagicMock()
    filesystem.execute = AsyncMock(
        return_value=ToolResult(success=False, detail="always fails", payload={})
    )
    filesystem.verify = AsyncMock(
        return_value=Verification(passed=False, detail="fail verify")
    )

    journal = MagicMock()
    journal.restore = MagicMock(return_value=True)
    journal.mark_applied = MagicMock()

    audit = MagicMock()
    audit.log = MagicMock()

    executor = PlanExecutor(
        filesystem=filesystem,
        shell=MagicMock(),
        git=MagicMock(),
        journal=journal,
        audit=audit,
    )

    result = await executor.run(plan)

    # Falló
    assert not result.success

    # execute llamado exactamente 3 veces (max_attempts)
    assert filesystem.execute.call_count == 3


# ---------------------------------------------------------------------------
# Test 4: ESCALATE audita sin rollback
# ---------------------------------------------------------------------------


async def test_escalate_audits_without_rollback() -> None:
    """ESCALATE policy: falla → FakeAudit recibe TASK_FAILED; journal.restore NO se llama."""
    step = Action(
        type="file.write",
        target="/x",
        on_error=ErrorPolicy.ESCALATE,
    )
    plan = _make_plan(step, task_id="task-escalate-1")

    filesystem = MagicMock()
    filesystem.execute = AsyncMock(
        return_value=ToolResult(success=False, detail="escalation fail", payload={})
    )
    filesystem.verify = AsyncMock(
        return_value=Verification(passed=False, detail="fail verify")
    )

    journal = MagicMock()
    journal.restore = MagicMock(return_value=True)
    journal.mark_applied = MagicMock()

    from tests.execution.conftest import FakeAudit

    fake_audit = FakeAudit()

    executor = PlanExecutor(
        filesystem=filesystem,
        shell=MagicMock(),
        git=MagicMock(),
        journal=journal,
        audit=fake_audit,
    )

    result = await executor.run(plan)

    # Plan falló
    assert not result.success

    # journal.restore NO fue llamado
    journal.restore.assert_not_called()

    # FakeAudit recibió exactamente un evento TASK_FAILED con escalate=True
    escalate_events = [
        e
        for e in fake_audit.events
        if e.event_type == AuditEventType.TASK_FAILED
        and e.payload.get("escalate") is True
    ]
    assert len(escalate_events) == 1, (
        f"Esperaba 1 evento TASK_FAILED escalate, encontré: {fake_audit.events}"
    )


# ---------------------------------------------------------------------------
# Test 5: plan completo con éxito marca entries como aplicadas
# ---------------------------------------------------------------------------


async def test_successful_plan_marks_applied() -> None:
    """Un plan que termina sin errores marca todas las journal entries como applied."""
    step1 = Action(type="file.write", target="/a")
    step2 = Action(type="shell.run", target="echo")
    plan = _make_plan(step1, step2)

    filesystem = MagicMock()
    filesystem.execute = AsyncMock(
        return_value=ToolResult(success=True, detail="ok", payload={"journal_entry_id": "e1"})
    )
    filesystem.verify = AsyncMock(
        return_value=Verification(passed=True, detail="ok")
    )

    shell = MagicMock()
    shell.execute = AsyncMock(
        return_value=ToolResult(success=True, detail="ok", payload={"journal_entry_id": "e2"})
    )
    shell.verify = AsyncMock(
        return_value=Verification(passed=True, detail="ok")
    )

    journal = MagicMock()
    journal.restore = MagicMock(return_value=True)
    journal.mark_applied = MagicMock()

    audit = MagicMock()
    audit.log = MagicMock()

    executor = PlanExecutor(
        filesystem=filesystem,
        shell=shell,
        git=MagicMock(),
        journal=journal,
        audit=audit,
    )

    result = await executor.run(plan)

    assert result.success

    # mark_applied llamado para cada entry_id en orden
    journal.mark_applied.assert_any_call("e1")
    journal.mark_applied.assert_any_call("e2")
    assert journal.mark_applied.call_count == 2
