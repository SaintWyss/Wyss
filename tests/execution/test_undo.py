"""Tests de execution/undo.py (PR-09): plan_undo, pre-chequeos de colisión y apply.

Las entradas se registran con las MISMAS formas de inverse_op que produce el
FileSystemAdapter en producción (write-nuevo → file.delete; overwrite → file.write
+ backup; move → file.move con parameters.destination; delete → file.restore_trash).
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from execution.journal import UndoJournal
from execution.undo import apply_undo, inverse_plan, plan_undo


@pytest.fixture
def journal(tmp_path: Path) -> Iterator[UndoJournal]:
    j = UndoJournal(tmp_path / "journal.db", backup_base_dir=tmp_path / "undo_backups")
    try:
        yield j
    finally:
        j.close()


def _record_applied(
    journal: UndoJournal,
    task_id: str,
    step_index: int,
    action_type: str,
    origin: str,
    inverse_op: dict[str, object],
    destination: str | None = None,
) -> str:
    entry_id = journal.record(
        task_id=task_id,
        step_index=step_index,
        action_type=action_type,
        origin=origin,
        destination=destination,
        inverse_op=inverse_op,
    )
    journal.mark_applied(entry_id)
    return entry_id


def test_plan_undo_reverse_order_and_only_applied(journal: UndoJournal, tmp_path: Path) -> None:
    """Solo entradas 'applied' de la tarea, en orden inverso de ejecución."""
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("a")
    second.write_text("b")
    _record_applied(
        journal,
        "t1",
        0,
        "file.write",
        str(first),
        {"type": "file.delete", "target": str(first), "parameters": {}},
    )
    _record_applied(
        journal,
        "t1",
        1,
        "file.write",
        str(second),
        {"type": "file.delete", "target": str(second), "parameters": {}},
    )
    # pendiente (plan en vuelo) y de otra tarea: no deben aparecer
    journal.record(
        task_id="t1",
        step_index=2,
        action_type="file.write",
        origin="x",
        destination=None,
        inverse_op={"type": "file.delete", "target": "x"},
    )
    _record_applied(
        journal,
        "otra",
        0,
        "file.write",
        "y",
        {"type": "file.delete", "target": "y", "parameters": {}},
    )

    steps = plan_undo(journal, "t1")

    assert [s.entry.step_index for s in steps] == [1, 0]
    assert all(s.ready for s in steps)


def test_undo_new_file_write_deletes(journal: UndoJournal, tmp_path: Path) -> None:
    """write de archivo nuevo → la inversa borra el archivo creado."""
    created = tmp_path / "nuevo.txt"
    created.write_text("contenido")
    entry_id = _record_applied(
        journal,
        "t-new",
        0,
        "file.write",
        str(created),
        {"type": "file.delete", "target": str(created), "parameters": {}},
    )

    steps = plan_undo(journal, "t-new")
    success, details = apply_undo(journal, steps)

    assert success, details
    assert not created.exists()
    loaded = journal.load(entry_id)
    assert loaded is not None
    assert loaded.status == "rolled_back"
    # idempotencia: un segundo undo no encuentra nada
    assert plan_undo(journal, "t-new") == []


def test_undo_overwrite_restores_backup(journal: UndoJournal, tmp_path: Path) -> None:
    """overwrite → la inversa restaura el contenido previo desde el backup."""
    target = tmp_path / "nota.txt"
    target.write_text("viejo")
    entry_id = journal.record(
        task_id="t-ow",
        step_index=0,
        action_type="file.write",
        origin=str(target),
        destination=None,
        inverse_op={"type": "file.write", "target": str(target), "parameters": {}},
    )
    journal.capture_overwrite_backup(entry_id, target)
    target.write_text("nuevo")  # la mutación
    journal.mark_applied(entry_id)

    steps = plan_undo(journal, "t-ow")
    assert steps[0].ready
    success, _ = apply_undo(journal, steps)

    assert success
    assert target.read_text() == "viejo"


def test_undo_move_moves_back(journal: UndoJournal, tmp_path: Path) -> None:
    origin = tmp_path / "origen.txt"
    dest = tmp_path / "destino.txt"
    dest.write_text("movido")  # estado post-move: el archivo vive en dest
    _record_applied(
        journal,
        "t-mv",
        0,
        "file.move",
        str(origin),
        {"type": "file.move", "target": str(dest), "parameters": {"destination": str(origin)}},
        destination=str(dest),
    )

    steps = plan_undo(journal, "t-mv")
    success, _ = apply_undo(journal, steps)

    assert success
    assert origin.read_text() == "movido"
    assert not dest.exists()


def test_undo_move_collision_not_ready(journal: UndoJournal, tmp_path: Path) -> None:
    """Check de colisión: si el origen fue re-creado, el paso NO está listo."""
    origin = tmp_path / "origen.txt"
    dest = tmp_path / "destino.txt"
    dest.write_text("movido")
    origin.write_text("recreado a mano")  # colisión
    _record_applied(
        journal,
        "t-col",
        0,
        "file.move",
        str(origin),
        {"type": "file.move", "target": str(dest), "parameters": {"destination": str(origin)}},
        destination=str(dest),
    )

    steps = plan_undo(journal, "t-col")

    assert not steps[0].ready
    assert "colisión" in steps[0].detail


def test_unknown_inverse_not_ready(journal: UndoJournal, tmp_path: Path) -> None:
    """Un tipo de inversa desconocido se marca irreversible, nunca se aplica a ciegas."""
    _record_applied(
        journal,
        "t-unk",
        0,
        "shell.run",
        "algo",
        {"type": "shell.rerun", "target": "algo", "parameters": {}},
    )

    steps = plan_undo(journal, "t-unk")

    assert not steps[0].ready
    assert "irreversible" in steps[0].detail


def test_restore_guard_by_expected_status(journal: UndoJournal, tmp_path: Path) -> None:
    """restore() default (pending) NO revierte una entrada 'applied' — el rollback
    intra-plan del executor no puede tocar mutaciones de tareas ya completadas."""
    created = tmp_path / "guard.txt"
    created.write_text("x")
    entry_id = _record_applied(
        journal,
        "t-guard",
        0,
        "file.write",
        str(created),
        {"type": "file.delete", "target": str(created), "parameters": {}},
    )

    assert journal.restore(entry_id) is False  # default espera 'pending'
    assert created.exists()
    assert journal.restore(entry_id, expected_status="applied") is True
    assert not created.exists()


def test_inverse_plan_is_fail_closed_material(journal: UndoJournal, tmp_path: Path) -> None:
    """El plan inverso lleva task_id undo-<task> y los steps con las inversas,
    listo para engine.evaluate (file.restore_trash desconocido → C fail-closed)."""
    created = tmp_path / "p.txt"
    created.write_text("x")
    _record_applied(
        journal,
        "t-plan",
        0,
        "file.write",
        str(created),
        {"type": "file.delete", "target": str(created), "parameters": {}},
    )

    steps = plan_undo(journal, "t-plan")
    plan = inverse_plan("t-plan", steps)

    assert plan.task_id == "undo-t-plan"
    assert plan.steps[0].type == "file.delete"
    assert plan.steps[0].target == str(created)
