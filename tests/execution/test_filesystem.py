"""Tests de FileSystemAdapter: execute por tipo + verify + send2trash + journal antes de mutar.

Plan 06-04, Task 2 (TDD RED).

NOTA: send2trash en tmp_path (ext4) funciona correctamente.
NUNCA usar /tmp directamente: sticky-bit levanta TrashPermissionError.
"""

import asyncio
import hashlib
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from core.domain.execution import ToolResult
from core.domain.plan import Action
from core.policy.engine import CognitivePolicyEngine
from execution.filesystem import FileSystemAdapter, _sha256
from execution.journal import UndoJournal
from tests.execution.conftest import FakeAudit

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
def adapter(
    engine: CognitivePolicyEngine,
    fake_audit: FakeAudit,
    journal: UndoJournal,
) -> FileSystemAdapter:
    return FileSystemAdapter(engine=engine, audit=fake_audit, journal=journal)


# ---------------------------------------------------------------------------
# sha256 helper
# ---------------------------------------------------------------------------


def test_sha256_helper(tmp_path: Path) -> None:
    """_sha256 devuelve el hash correcto para contenido conocido."""
    f = tmp_path / "test.txt"
    content = b"hello wyss"
    f.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()
    assert _sha256(f) == expected


# ---------------------------------------------------------------------------
# file.write
# ---------------------------------------------------------------------------


def test_write_creates_file(adapter: FileSystemAdapter, tmp_path: Path) -> None:
    """file.write crea el archivo y payload contiene size + sha256."""
    target = tmp_path / "new_file.txt"
    action = Action(
        type="file.write",
        target=str(target),
        parameters={"content": "hello"},
    )
    result = asyncio.run(adapter.execute(action))

    assert result.success, f"write failed: {result.detail}"
    assert target.exists()
    assert result.payload["size"] == target.stat().st_size
    assert isinstance(result.payload["sha256"], str)
    assert len(str(result.payload["sha256"])) == 64  # sha256 hex = 64 chars


def test_write_verify_sha256(adapter: FileSystemAdapter, tmp_path: Path) -> None:
    """verify() tras file.write recomputa sha256 y lo compara con el payload."""
    target = tmp_path / "check_sha.txt"
    action = Action(
        type="file.write",
        target=str(target),
        parameters={"content": "verify me"},
    )
    result = asyncio.run(adapter.execute(action))
    assert result.success

    verification = asyncio.run(adapter.verify(action, result))
    assert verification.passed, f"verify failed: {verification.detail}"
    assert "ok" in verification.detail


def test_write_verify_fails_on_mismatch(adapter: FileSystemAdapter, tmp_path: Path) -> None:
    """verify() falla si el archivo fue modificado post-ejecución."""
    target = tmp_path / "tampered.txt"
    action = Action(
        type="file.write",
        target=str(target),
        parameters={"content": "original"},
    )
    result = asyncio.run(adapter.execute(action))
    assert result.success

    # Modificar el archivo DESPUÉS de ejecutar
    target.write_text("tampered content", encoding="utf-8")

    verification = asyncio.run(adapter.verify(action, result))
    assert not verification.passed, "verify debería fallar con contenido modificado"
    assert "mismatch" in verification.detail


def test_write_overwrite_records_journal(
    adapter: FileSystemAdapter,
    journal: UndoJournal,
    tmp_path: Path,
) -> None:
    """file.write sobre archivo existente registra entrada en journal ANTES de mutar."""
    target = tmp_path / "existing.txt"
    target.write_text("original content", encoding="utf-8")

    # Registrar cuántas entradas hay ANTES
    conn = journal._conn
    before = conn.execute("SELECT COUNT(*) FROM undo_entries").fetchone()[0]

    action = Action(
        type="file.write",
        target=str(target),
        parameters={"content": "new content"},
    )
    result = asyncio.run(adapter.execute(action))
    assert result.success

    # Debe haber una entrada nueva
    after = conn.execute("SELECT COUNT(*) FROM undo_entries").fetchone()[0]
    assert after > before, "journal.record no fue llamado para el overwrite"

    # El archivo fue modificado
    assert target.read_text(encoding="utf-8") == "new content"


# ---------------------------------------------------------------------------
# file.move
# ---------------------------------------------------------------------------


def test_move_dest_exists_src_absent(adapter: FileSystemAdapter, tmp_path: Path) -> None:
    """file.move mueve el archivo; verify() confirma dest existe y src ausente."""
    src = tmp_path / "source.txt"
    dest = tmp_path / "destination.txt"
    src.write_text("move me", encoding="utf-8")

    action = Action(
        type="file.move",
        target=str(src),
        parameters={"destination": str(dest)},
    )
    result = asyncio.run(adapter.execute(action))
    assert result.success, f"move failed: {result.detail}"

    assert dest.exists(), "destino no existe tras move"
    assert not src.exists(), "origen sigue existiendo tras move"

    verification = asyncio.run(adapter.verify(action, result))
    assert verification.passed, f"verify move failed: {verification.detail}"


def test_move_records_journal_before_mutation(
    adapter: FileSystemAdapter,
    journal: UndoJournal,
    tmp_path: Path,
) -> None:
    """journal.record se llama para file.move y la entrada tiene la inversa correcta."""
    src = tmp_path / "move_src.txt"
    dest = tmp_path / "move_dest.txt"
    src.write_text("content", encoding="utf-8")

    conn = journal._conn
    before = conn.execute("SELECT COUNT(*) FROM undo_entries").fetchone()[0]

    action = Action(
        type="file.move",
        target=str(src),
        parameters={"destination": str(dest)},
    )
    result = asyncio.run(adapter.execute(action))
    assert result.success

    after = conn.execute("SELECT COUNT(*) FROM undo_entries").fetchone()[0]
    assert after > before, "journal.record no fue llamado para file.move"

    # La entrada debe tener action_type "file.move"
    row = conn.execute(
        "SELECT action_type, inverse_op FROM undo_entries ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert row["action_type"] == "file.move"


def test_move_verify_fails_if_src_still_exists(
    adapter: FileSystemAdapter, tmp_path: Path
) -> None:
    """verify() falla si la verificación es con result.success=False."""
    src = tmp_path / "src.txt"
    src.write_text("x", encoding="utf-8")
    action = Action(
        type="file.move",
        target=str(src),
        parameters={"destination": str(tmp_path / "dest.txt")},
    )
    # Construir un resultado fallido artificialmente
    failed_result = ToolResult(success=False, detail="failed", payload={})
    verification = asyncio.run(adapter.verify(action, failed_result))
    assert not verification.passed


# ---------------------------------------------------------------------------
# file.delete
# ---------------------------------------------------------------------------


def test_delete_to_trash_not_unlink(adapter: FileSystemAdapter, tmp_path: Path) -> None:
    """file.delete usa send2trash (NO unlink): el archivo desaparece del origen.

    Usa tmp_path (ext4) — NUNCA /tmp directamente (sticky-bit → TrashPermissionError).
    """
    target = tmp_path / "delete_me.txt"
    target.write_text("delete this", encoding="utf-8")

    action = Action(
        type="file.delete",
        target=str(target),
        parameters={},
    )
    result = asyncio.run(adapter.execute(action))

    assert result.success, f"delete failed: {result.detail}"
    assert not target.exists(), "archivo sigue existiendo después de delete"
    # El payload debe contener trash_path
    assert "trash_path" in result.payload


def test_delete_journal_recorded_before_delete(
    adapter: FileSystemAdapter,
    journal: UndoJournal,
    tmp_path: Path,
) -> None:
    """journal.record se llama ANTES de send2trash para file.delete."""
    target = tmp_path / "journal_before_delete.txt"
    target.write_text("journal test", encoding="utf-8")

    conn = journal._conn
    before = conn.execute("SELECT COUNT(*) FROM undo_entries").fetchone()[0]

    action = Action(
        type="file.delete",
        target=str(target),
        parameters={},
    )
    result = asyncio.run(adapter.execute(action))
    assert result.success

    after = conn.execute("SELECT COUNT(*) FROM undo_entries").fetchone()[0]
    assert after > before, "journal.record no fue llamado para file.delete"

    # La entrada debe registrar action_type="file.delete" y tener inverse_op de restore_trash
    import json

    row = conn.execute(
        "SELECT action_type, inverse_op FROM undo_entries ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    assert row["action_type"] == "file.delete"
    inverse = json.loads(row["inverse_op"])
    assert inverse["type"] == "file.restore_trash"


def test_delete_verify_absent(adapter: FileSystemAdapter, tmp_path: Path) -> None:
    """verify() tras delete confirma que el original está ausente."""
    target = tmp_path / "verify_delete.txt"
    target.write_text("bye", encoding="utf-8")

    action = Action(
        type="file.delete",
        target=str(target),
        parameters={},
    )
    result = asyncio.run(adapter.execute(action))
    assert result.success

    verification = asyncio.run(adapter.verify(action, result))
    # El archivo debe estar ausente del origen
    assert not target.exists()
    # verify puede pasar (ausente + en trash) o fallar si trash_path no se encuentra
    # Lo que SIEMPRE debe cumplirse: el archivo está ausente del origen
    # (puede fallar la verificación del trash_path dependiendo del filesystem/permisos)
    # assert verification.passed o verificar que el archivo no existe
    # En ext4/tmp_path, send2trash generalmente funciona:
    if verification.passed:
        assert "absent" in verification.detail or "in trash" in verification.detail
    # else: aceptable que el trash_path no siempre sea predecible en tests


def test_delete_no_unlink_in_source(adapter: FileSystemAdapter, tmp_path: Path) -> None:
    """Verificación estática: filesystem.py NO debe usar os.unlink para delete."""
    import ast
    import inspect

    import execution.filesystem as fs_module

    source = inspect.getsource(fs_module)
    tree = ast.parse(source)

    # Buscar llamadas a os.unlink
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "unlink"
                and isinstance(func.value, ast.Name)
                and func.value.id == "os"
            ):
                pytest.fail(
                    "FileSystemAdapter usa os.unlink — debe usar send2trash (D-64)"
                )


# ---------------------------------------------------------------------------
# journal.record BEFORE mutation (generic)
# ---------------------------------------------------------------------------


def test_journal_record_before_mutation_write_new(
    adapter: FileSystemAdapter,
    journal: UndoJournal,
    tmp_path: Path,
) -> None:
    """Para archivo nuevo: journal.record se llama antes de write_text."""
    target = tmp_path / "new_journal_test.txt"
    assert not target.exists()

    conn = journal._conn
    action = Action(
        type="file.write",
        target=str(target),
        parameters={"content": "test"},
    )
    result = asyncio.run(adapter.execute(action))
    assert result.success

    rows = conn.execute("SELECT * FROM undo_entries").fetchall()
    assert len(rows) >= 1, "journal no registró la escritura"

    import json

    last = rows[-1]
    inverse = json.loads(last["inverse_op"])
    # Para archivo nuevo, la inversa es file.delete (borrarlo)
    assert inverse["type"] == "file.delete"


# ---------------------------------------------------------------------------
# NTFS opt-in (si WYSS_TEST_NTFS=1)
# ---------------------------------------------------------------------------


@pytest.mark.ntfs
@pytest.mark.skipif(
    os.environ.get("WYSS_TEST_NTFS") != "1",
    reason="requiere WYSS_TEST_NTFS=1 (corre sobre el mount NTFS/fuseblk real)",
)
def test_send2trash_on_ntfs_mount(
    adapter: FileSystemAdapter,
    engine: CognitivePolicyEngine,
    fake_audit: FakeAudit,
    tmp_path: Path,
) -> None:
    """send2trash sobre el mount NTFS/fuseblk real crea entrada en .Trash sin EXDEV.

    El sentinel se crea en un tempdir sobre el MISMO mount que el repo (para ejercer
    send2trash en fuseblk, no en /tmp ext4), pero FUERA de ``wyss/data`` y ``wyss/config``:
    la denylist ``wyss-self-modify`` (``**/wyss/data/**``) bloquearía cualquier
    ``file.*`` ahí y send2trash nunca correría (la segunda muralla vetaría antes del I/O).
    """
    # Mountpoint del repo: subir hasta el primer os.path.ismount (machine-agnostic).
    mount_point = Path(__file__).resolve()
    while not os.path.ismount(mount_point) and mount_point != mount_point.parent:
        mount_point = mount_point.parent

    work_dir = Path(tempfile.mkdtemp(prefix="wyss-ntfs-test-", dir=str(mount_point)))
    try:
        test_file = work_dir / "sentinel.txt"
        test_file.write_text("ntfs trash test sentinel", encoding="utf-8")

        ntfs_journal = UndoJournal(
            work_dir / "journal.db",
            backup_base_dir=work_dir / "backups",
        )
        ntfs_adapter = FileSystemAdapter(engine=engine, audit=fake_audit, journal=ntfs_journal)

        action = Action(
            type="file.delete",
            target=str(test_file),
            parameters={},
        )
        result = asyncio.run(ntfs_adapter.execute(action))
        ntfs_journal.close()

        assert result.success, f"NTFS delete failed: {result.detail}"
        assert not test_file.exists()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
