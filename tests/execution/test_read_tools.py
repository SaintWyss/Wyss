"""Tests de PR-11 Operator Read Tools: file.read/list/stat en el FileSystemAdapter
y afloramiento de salidas en el PlanExecutor.

Las lecturas NO journalan (no mutan) pero SÍ pasan la segunda muralla: leer un
secreto (.env, ~/.ssh) resuelve D por secret-exfiltration y se bloquea igual que
una escritura.
"""

import asyncio
from pathlib import Path
from typing import Any, cast

from core.domain.plan import Action, Plan
from core.policy.engine import CognitivePolicyEngine
from execution.executor import PlanExecutor
from execution.filesystem import _LIST_CAP_ENTRIES, _READ_CAP_BYTES, FileSystemAdapter
from execution.git import GitAdapter
from execution.journal import UndoJournal
from execution.shell import ShellAdapter
from tests.execution.conftest import FakeAudit


def _adapter(
    engine: CognitivePolicyEngine, audit: FakeAudit, journal: UndoJournal
) -> FileSystemAdapter:
    return FileSystemAdapter(engine=engine, audit=audit, journal=journal)


def test_read_returns_content(
    engine: CognitivePolicyEngine, journal: UndoJournal, tmp_path: Path
) -> None:
    target = tmp_path / "nota.txt"
    target.write_text("hola wyss", encoding="utf-8")
    adapter = _adapter(engine, FakeAudit(), journal)

    result = asyncio.run(adapter.execute(Action("file.read", str(target))))

    assert result.success
    assert result.payload["output"] == "hola wyss"
    assert result.payload["truncated"] is False


def test_read_truncates_at_cap(
    engine: CognitivePolicyEngine, journal: UndoJournal, tmp_path: Path
) -> None:
    """Un archivo más grande que el tope se corta honesto — jamás volcar gigas."""
    target = tmp_path / "grande.txt"
    target.write_bytes(b"x" * (_READ_CAP_BYTES + 1000))
    adapter = _adapter(engine, FakeAudit(), journal)

    result = asyncio.run(adapter.execute(Action("file.read", str(target))))

    assert result.success
    assert result.payload["truncated"] is True
    assert "truncado" in str(result.payload["output"])


def test_read_missing_file_honest(
    engine: CognitivePolicyEngine, journal: UndoJournal, tmp_path: Path
) -> None:
    adapter = _adapter(engine, FakeAudit(), journal)

    result = asyncio.run(adapter.execute(Action("file.read", str(tmp_path / "no.txt"))))

    assert result.success is False
    assert "not found" in result.detail


def test_read_secret_blocked_by_second_wall(
    engine: CognitivePolicyEngine, journal: UndoJournal, tmp_path: Path
) -> None:
    """Leer un .env resuelve D (secret-exfiltration) → la segunda muralla bloquea la
    LECTURA igual que bloquearía una escritura."""
    secret = tmp_path / ".env"
    secret.write_text("API_KEY=xxx")
    audit = FakeAudit()
    adapter = _adapter(engine, audit, journal)

    result = asyncio.run(adapter.execute(Action("file.read", str(secret))))

    assert result.success is False
    assert "second wall" in result.detail.lower()
    assert any(
        isinstance(e.payload, dict) and e.payload.get("blocked") == "second_wall"
        for e in audit.events
    )


def test_list_sorted_dirs_marked_and_capped(
    engine: CognitivePolicyEngine, journal: UndoJournal, tmp_path: Path
) -> None:
    base = tmp_path / "listado"  # subdir limpio: tmp_path tiene el journal.db del fixture
    base.mkdir()
    (base / "b.txt").write_text("b")
    (base / "a.txt").write_text("a")
    (base / "carpeta").mkdir()
    adapter = _adapter(engine, FakeAudit(), journal)

    result = asyncio.run(adapter.execute(Action("file.list", str(base))))

    assert result.success
    lines = str(result.payload["output"]).splitlines()
    assert lines == ["a.txt", "b.txt", "carpeta/"]
    assert result.payload["count"] == 3

    # tope de entradas: honesto sobre lo omitido
    many = tmp_path / "muchos"
    many.mkdir()
    for i in range(_LIST_CAP_ENTRIES + 2):
        (many / f"f{i:04d}").touch()
    capped = asyncio.run(adapter.execute(Action("file.list", str(many))))
    assert capped.payload["count"] == _LIST_CAP_ENTRIES + 2
    assert "entradas más" in str(capped.payload["output"])


def test_list_on_file_fails_honest(
    engine: CognitivePolicyEngine, journal: UndoJournal, tmp_path: Path
) -> None:
    target = tmp_path / "archivo.txt"
    target.write_text("x")
    adapter = _adapter(engine, FakeAudit(), journal)

    result = asyncio.run(adapter.execute(Action("file.list", str(target))))

    assert result.success is False
    assert "not a directory" in result.detail


def test_stat_reports_fields(
    engine: CognitivePolicyEngine, journal: UndoJournal, tmp_path: Path
) -> None:
    target = tmp_path / "nota.txt"
    target.write_text("12345")
    adapter = _adapter(engine, FakeAudit(), journal)

    result = asyncio.run(adapter.execute(Action("file.stat", str(target))))

    assert result.success
    assert result.payload["size"] == 5
    assert result.payload["kind"] == "file"
    output = str(result.payload["output"])
    assert "tipo: file" in output
    assert "mtime:" in output


def test_executor_surfaces_read_outputs(
    engine: CognitivePolicyEngine, journal: UndoJournal, tmp_path: Path
) -> None:
    """PR-11: el PlanExecutor junta las salidas visibles de los pasos de lectura."""
    target = tmp_path / "leeme.txt"
    target.write_text("contenido visible")
    audit = FakeAudit()
    executor = PlanExecutor(
        filesystem=_adapter(engine, audit, journal),
        shell=ShellAdapter(cast(Any, audit)),
        git=GitAdapter(cast(Any, audit), tmp_path),
        journal=journal,
        audit=audit,
    )
    plan = Plan(
        task_id="read-1",
        summary="leer archivo",
        steps=(Action("file.read", str(target)), Action("file.stat", str(target))),
        rationale="test",
    )

    result = asyncio.run(executor.run(plan))

    assert result.success
    assert result.outputs[0] == "contenido visible"
    assert "tipo: file" in result.outputs[1]
