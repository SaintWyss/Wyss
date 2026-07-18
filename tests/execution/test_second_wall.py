"""Tests de la segunda muralla (EXEC-04 / D-68): el FileSystemAdapter resuelve paths reales
antes de re-evaluar con el engine de política.

Plan 06-04, Task 1 (TDD RED).
"""

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from core.domain.plan import Action, ErrorPolicy
from core.policy.engine import CognitivePolicyEngine
from tests.execution.conftest import FakeAudit, RecordingEngine

if TYPE_CHECKING:
    from execution.filesystem import FileSystemAdapter


def _make_adapter(
    engine: CognitivePolicyEngine,
    audit: FakeAudit,
    tmp_path: Path,
) -> "FileSystemAdapter":
    from execution.filesystem import FileSystemAdapter
    from execution.journal import UndoJournal

    journal = UndoJournal(tmp_path / "journal.db", backup_base_dir=tmp_path / "backups")
    return FileSystemAdapter(engine=engine, audit=audit, journal=journal)


def test_symlink_resolved_before_eval(tmp_path: Path) -> None:
    """Path.resolve() expande ~/Data -> /mnt/hdd/Data (symlink en esta máquina).

    Verifica que la función auxiliar _resolve_target sigue los symlinks reales.
    En este entorno ~/Data es symlink a /mnt/hdd/Data.
    """
    from execution.filesystem import _resolve_target

    # ~/Data debe resolverse a /mnt/hdd/Data en este entorno
    data_path = Path(os.path.expanduser("~/Data"))
    if data_path.is_symlink():
        target = "~/Data/test_sentinel.txt"
        resolved = _resolve_target(target)
        # El symlink ~/Data -> /mnt/hdd/Data, por tanto la ruta resuelta empieza con /mnt/hdd
        assert resolved.startswith("/mnt/hdd"), (
            f"Expected resolved path under /mnt/hdd, got: {resolved!r}"
        )
        assert "~" not in resolved, "tilde no debe quedar en la ruta resuelta"
    else:
        pytest.skip("~/Data no es symlink en este entorno — test solo aplica en Santiago-PC")


def test_resolve_target_expands_tilde(tmp_path: Path) -> None:
    """_resolve_target expande ~ y devuelve una ruta absoluta real."""
    from execution.filesystem import _resolve_target

    resolved = _resolve_target("~/nonexistent_sentinel_path")
    # Debe ser absoluta (no empezar con ~)
    assert not resolved.startswith("~")
    assert os.path.isabs(resolved)


def test_recording_engine_called_on_execute(
    engine: CognitivePolicyEngine,
    tmp_path: Path,
) -> None:
    """execute() llama engine.evaluate() con el Plan de la segunda muralla (EXEC-04)."""
    recording = RecordingEngine(engine)
    fake_audit = FakeAudit()
    adapter = _make_adapter(recording, fake_audit, tmp_path)  # type: ignore[arg-type]

    # Acción benigna en tmp_path
    target_file = tmp_path / "write_me.txt"
    action = Action(
        type="file.write",
        target=str(target_file),
        parameters={"content": "hello"},
        on_error=ErrorPolicy.ABORT,
    )

    import asyncio

    asyncio.run(adapter.execute(action))

    # El engine debe haber sido llamado por la segunda muralla
    assert len(recording.calls) >= 1, "engine.evaluate no fue llamado por la segunda muralla"
    # El plan de la segunda muralla debe tener task_id="second-wall"
    second_wall_plans = [p for p in recording.calls if p.task_id == "second-wall"]
    assert len(second_wall_plans) >= 1, (
        f"No se encontró plan con task_id='second-wall' en calls: {recording.calls}"
    )


def test_tampered_path_blocked(
    engine: CognitivePolicyEngine,
    tmp_path: Path,
) -> None:
    """Una acción cuyo resolved path difiere del original (path tricks) es bloqueada + auditada."""
    fake_audit = FakeAudit()

    # Crear un symlink que apunte a otro directorio
    real_dir = tmp_path / "real_target"
    real_dir.mkdir()
    link = tmp_path / "innocent_link"
    link.symlink_to(real_dir)

    # La acción usa el symlink como target (pre-resolución)
    # Cuando el adapter resuelve el symlink, obtendrá la ruta real (diferente de 'innocent_link')
    action = Action(
        type="file.write",
        target=str(link),  # este es el symlink — al resolver cambia a real_dir
        parameters={"content": "x"},
        on_error=ErrorPolicy.ABORT,
    )

    adapter = _make_adapter(engine, fake_audit, tmp_path)

    import asyncio

    result = asyncio.run(adapter.execute(action))

    # DEBE bloquearse porque resolved != original target
    assert result.success is False, f"Se esperaba bloqueo por path tamperado, resultado: {result}"
    assert "second wall" in result.detail.lower(), (
        f"Detail no menciona 'second wall': {result.detail!r}"
    )
    # DEBE haberse registrado un evento de audit
    assert len(fake_audit.events) >= 1, "No se registró evento de auditoría al bloquear"
    blocked_events = [
        e
        for e in fake_audit.events
        if isinstance(e.payload, dict) and e.payload.get("blocked") == "second_wall"
    ]
    assert len(blocked_events) >= 1, (
        f"No hay evento con blocked='second_wall' en: {fake_audit.events}"
    )


def test_resolved_path_above_max_risk_blocked(
    engine: CognitivePolicyEngine,
    tmp_path: Path,
) -> None:
    """Un symlink que apunta a ~/.ssh (si existe) o a una ruta denylist es bloqueado."""
    fake_audit = FakeAudit()
    ssh_dir = Path(os.path.expanduser("~/.ssh"))

    if not ssh_dir.exists():
        pytest.skip("~/.ssh no existe — test de denylist aplicable solo si existe")

    # Crear symlink en tmp_path que apunta a ~/.ssh
    link = tmp_path / "innocent_ssh_link"
    link.symlink_to(ssh_dir)

    action = Action(
        type="file.write",
        target=str(link / "id_rsa"),  # apunta dentro de ~/.ssh vía el symlink
        parameters={"content": "evil"},
        on_error=ErrorPolicy.ABORT,
    )

    adapter = _make_adapter(engine, fake_audit, tmp_path)

    import asyncio

    result = asyncio.run(adapter.execute(action))

    # ~/.ssh está en denylist → la segunda muralla DEBE bloquear
    assert result.success is False, (
        f"Se esperaba bloqueo para acción en ~/.ssh vía symlink, resultado: {result}"
    )
    assert "second wall" in result.detail.lower()


def test_path_traversal_to_system_dir_blocked(
    engine: CognitivePolicyEngine,
    tmp_path: Path,
) -> None:
    """PR-08: un target con `../` que escapa hacia /etc se resuelve ANTES de re-evaluar,
    y la denylist (system-files-write) lo corta en la segunda muralla."""
    import asyncio

    traversal = os.path.join(str(tmp_path), *[".."] * 30, "etc", "passwd")
    action = Action(
        type="file.write",
        target=traversal,
        parameters={"content": "evil"},
        on_error=ErrorPolicy.ABORT,
    )
    fake_audit = FakeAudit()
    adapter = _make_adapter(engine, fake_audit, tmp_path)

    result = asyncio.run(adapter.execute(action))

    assert result.success is False, f"traversal debía bloquearse: {result}"
    assert "second wall" in result.detail.lower()
    assert not Path("/etc/passwd_evil").exists()


def test_directory_symlink_parent_is_allowed(
    engine: CognitivePolicyEngine,
    tmp_path: Path,
) -> None:
    """F3 (PR-08): un symlink de DIRECTORIO padre (infra tipo ~/Data → /mnt/hdd/Data)
    NO debe disparar el bloqueo por path-tricks — solo el archivo-symlink final lo hace.
    """
    import asyncio

    real_dir = tmp_path / "real_data"
    real_dir.mkdir()
    link_dir = tmp_path / "Data"  # symlink de directorio, como ~/Data en producción
    link_dir.symlink_to(real_dir)

    fake_audit = FakeAudit()
    adapter = _make_adapter(engine, fake_audit, tmp_path)

    action = Action(
        type="file.write",
        target=str(link_dir / "nota.txt"),  # el archivo NO es symlink; el padre sí
        parameters={"content": "hola"},
        on_error=ErrorPolicy.ABORT,
    )
    result = asyncio.run(adapter.execute(action))

    assert result.success is True, (
        f"symlink de directorio padre benigno no debe bloquearse: {result.detail!r}"
    )
    assert (real_dir / "nota.txt").read_text() == "hola"
