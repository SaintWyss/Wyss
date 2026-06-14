"""Tests de integración PlanExecutor + FileSystemAdapter REAL (rollback D-65 end-to-end).

A diferencia de test_executor.py (que usa adapters MagicMock con `journal_entry_id`
inyectado en el payload), estos tests cablean el FileSystemAdapter real dentro del
PlanExecutor y ejercen la costura completa: record → mutar → entry_id → ABORT → restore.

Cubren la brecha que test_executor.py (fakes) y test_filesystem.py (adapter aislado)
no tocan: que un plan multi-paso que falla a mitad revierta de verdad los pasos
ya aplicados (EXEC-03 / D-65).

asyncio_mode="auto" en pyproject.toml — no necesitan @pytest.mark.asyncio.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from core.domain.plan import Action, ErrorPolicy, Plan
from core.policy.engine import CognitivePolicyEngine
from execution.executor import PlanExecutor
from execution.filesystem import FileSystemAdapter
from execution.git import GitAdapter
from execution.journal import UndoJournal
from execution.shell import ShellAdapter
from tests.execution.conftest import FakeAudit


@pytest.fixture
def fake_audit() -> FakeAudit:
    return FakeAudit()


@pytest.fixture
def journal(tmp_path: Path) -> Iterator[UndoJournal]:
    j = UndoJournal(tmp_path / "journal.db", backup_base_dir=tmp_path / "backups")
    try:
        yield j
    finally:
        j.close()


@pytest.fixture
def executor(
    engine: CognitivePolicyEngine,
    fake_audit: FakeAudit,
    journal: UndoJournal,
    tmp_path: Path,
) -> PlanExecutor:
    """PlanExecutor con FileSystemAdapter REAL (shell/git presentes pero no usados aquí)."""
    filesystem = FileSystemAdapter(engine=engine, audit=fake_audit, journal=journal)
    shell = ShellAdapter(fake_audit, allowed_binaries=set())
    git = GitAdapter(fake_audit, repo_path=tmp_path)
    return PlanExecutor(
        filesystem=filesystem,
        shell=shell,
        git=git,
        journal=journal,
        audit=fake_audit,
    )


def _plan(*actions: Action) -> Plan:
    return Plan(
        task_id="integ-rollback",
        summary="rollback integration",
        steps=tuple(actions),
        rationale="testing rollback end-to-end",
    )


async def test_abort_removes_created_file_on_later_failure(
    executor: PlanExecutor, tmp_path: Path
) -> None:
    """Step 1 crea un archivo nuevo; step 2 falla → ABORT revierte el step 1 (archivo borrado).

    Con el bug de la costura (entry_id no aflora + mark_applied prematuro) el archivo
    queda creado: el rollback no encuentra entradas que restaurar.
    """
    created = tmp_path / "created.txt"
    missing = tmp_path / "does_not_exist.txt"  # delete fallará → ABORT

    plan = _plan(
        Action(
            type="file.write",
            target=str(created),
            parameters={"content": "paso 1"},
            on_error=ErrorPolicy.ABORT,
        ),
        Action(
            type="file.delete",
            target=str(missing),
            parameters={},
            on_error=ErrorPolicy.ABORT,
        ),
    )

    result = await executor.run(plan)

    assert not result.success, "el plan debía fallar en el step 2"
    assert not created.exists(), (
        "rollback D-65 roto: el archivo del step 1 sigue existiendo tras el ABORT"
    )


async def test_abort_restores_overwritten_content_on_later_failure(
    executor: PlanExecutor, tmp_path: Path
) -> None:
    """Step 1 sobrescribe archivo existente; step 2 falla → ABORT restaura contenido original."""
    existing = tmp_path / "existing.txt"
    existing.write_text("contenido original", encoding="utf-8")
    missing = tmp_path / "does_not_exist.txt"

    plan = _plan(
        Action(
            type="file.write",
            target=str(existing),
            parameters={"content": "contenido nuevo"},
            on_error=ErrorPolicy.ABORT,
        ),
        Action(
            type="file.delete",
            target=str(missing),
            parameters={},
            on_error=ErrorPolicy.ABORT,
        ),
    )

    result = await executor.run(plan)

    assert not result.success, "el plan debía fallar en el step 2"
    assert existing.read_text(encoding="utf-8") == "contenido original", (
        "rollback D-65 roto: el contenido sobrescrito no se restauró tras el ABORT"
    )


async def test_successful_plan_marks_entries_applied(
    executor: PlanExecutor, journal: UndoJournal, tmp_path: Path
) -> None:
    """Plan que completa con éxito deja las entradas del journal en estado 'applied'."""
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"

    plan = _plan(
        Action(type="file.write", target=str(f1), parameters={"content": "a"}),
        Action(type="file.write", target=str(f2), parameters={"content": "b"}),
    )

    result = await executor.run(plan)

    assert result.success, f"plan debía completar: {result.detail}"
    assert f1.exists() and f2.exists()
    rows = journal._conn.execute(
        "SELECT status FROM undo_entries"
    ).fetchall()
    assert len(rows) == 2, "se esperaban 2 entradas de journal"
    assert all(r["status"] == "applied" for r in rows), (
        "las entradas deberían quedar 'applied' tras el éxito"
    )
