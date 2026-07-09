"""Tests E2E de `wyss undo` (PR-09) vía CliRunner.

El undo NO es bypass: el plan inverso pasa por el CognitivePolicyEngine real que
arma load_settings (BUILTIN_DENY + base_levels), pide la palabra del nivel que
corresponde y solo entonces aplica las inversas del journal.
"""

from pathlib import Path

from typer.testing import CliRunner

from bootstrap.cli import app
from execution.journal import UndoJournal

runner = CliRunner()


def _write_config(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    audit_db = tmp_path / "audit" / "audit.db"
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f"""\
data_dir = "{data_dir}"
audit_db = "{audit_db}"
""",
        encoding="utf-8",
    )
    return cfg


def _journal_with_new_file(tmp_path: Path, task_id: str, target: Path) -> None:
    """Simula una tarea ejecutada que creó `target` (inversa: borrarlo)."""
    exec_dir = tmp_path / "data" / "execution"
    with UndoJournal(exec_dir / "journal.db", backup_base_dir=exec_dir / "undo_backups") as j:
        entry_id = j.record(
            task_id=task_id,
            step_index=0,
            action_type="file.write",
            origin=str(target),
            destination=None,
            inverse_op={"type": "file.delete", "target": str(target), "parameters": {}},
        )
        j.mark_applied(entry_id)


def test_undo_sin_journal_empty_state(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)

    result = runner.invoke(app, ["undo", "t1", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "journal" in result.stdout


def test_undo_task_sin_entradas(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    exec_dir = tmp_path / "data" / "execution"
    UndoJournal(exec_dir / "journal.db", backup_base_dir=exec_dir / "undo_backups").close()

    result = runner.invoke(app, ["undo", "fantasma", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "fantasma" in result.stdout


def test_undo_dry_run_no_toca(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    created = tmp_path / "creado.txt"
    created.write_text("x")
    _journal_with_new_file(tmp_path, "t-dry", created)

    result = runner.invoke(app, ["undo", "t-dry", "--dry-run", "--config", str(cfg)])

    assert result.exit_code == 0
    assert created.exists()  # dry-run jamás muta
    assert "listo" in result.stdout


def test_undo_confirmar_ejecuta(tmp_path: Path) -> None:
    """La inversa file.delete es nivel C → exige CONFIRMAR; con la palabra, revierte."""
    cfg = _write_config(tmp_path)
    created = tmp_path / "creado.txt"
    created.write_text("x")
    _journal_with_new_file(tmp_path, "t-go", created)

    result = runner.invoke(
        app, ["undo", "t-go", "--config", str(cfg)], input="CONFIRMAR\n"
    )

    assert result.exit_code == 0, result.output
    assert not created.exists()
    assert "Deshecho" in result.stdout


def test_undo_palabra_incorrecta_no_toca(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    created = tmp_path / "creado.txt"
    created.write_text("x")
    _journal_with_new_file(tmp_path, "t-no", created)

    result = runner.invoke(app, ["undo", "t-no", "--config", str(cfg)], input="nope\n")

    assert result.exit_code == 0
    assert created.exists()
    assert "no confirmado" in result.stdout.lower()


def test_undo_denegado_por_politica(tmp_path: Path) -> None:
    """Si la inversa cae en la denylist (borrar /etc/passwd), el undo se rechaza:
    mismo engine, no bypass."""
    cfg = _write_config(tmp_path)
    _journal_with_new_file(tmp_path, "t-mal", Path("/etc/passwd"))

    result = runner.invoke(app, ["undo", "t-mal", "--config", str(cfg)])

    assert result.exit_code == 1
    assert "política" in result.stderr
    assert Path("/etc/passwd").exists()


def test_undo_estado_cambiado_bloquea(tmp_path: Path) -> None:
    """Colisión de move (el origen fue re-creado) → el undo entero se rechaza."""
    cfg = _write_config(tmp_path)
    origin = tmp_path / "origen.txt"
    dest = tmp_path / "destino.txt"
    dest.write_text("movido")
    origin.write_text("recreado")  # colisión
    exec_dir = tmp_path / "data" / "execution"
    with UndoJournal(exec_dir / "journal.db", backup_base_dir=exec_dir / "undo_backups") as j:
        entry_id = j.record(
            task_id="t-col",
            step_index=0,
            action_type="file.move",
            origin=str(origin),
            destination=str(dest),
            inverse_op={
                "type": "file.move",
                "target": str(dest),
                "parameters": {"destination": str(origin)},
            },
        )
        j.mark_applied(entry_id)

    result = runner.invoke(app, ["undo", "t-col", "--config", str(cfg)])

    assert result.exit_code == 1
    assert "estado cambió" in result.stderr
    assert dest.read_text() == "movido"  # nada se movió
