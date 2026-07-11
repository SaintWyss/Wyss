"""Tests de `wyss memory` como cliente RPC thin."""

from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import bootstrap.cli as cli
from bootstrap.cli import app

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


def test_memory_list_renderiza_tabla_legible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _write_config(tmp_path)

    async def fake_rpc(
        socket_path: Path, method: str, params: dict[str, object]
    ) -> dict[str, Any]:
        del socket_path, params
        assert method == "memory.list"
        return {
            "facts": [
                {
                    "id": "fact-1",
                    "category": "preferences",
                    "value": "cafe sin azucar",
                    "tier": "owner",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        }

    monkeypatch.setattr(cli, "_json_rpc_call", fake_rpc)

    result = runner.invoke(app, ["memory", "list", "--config", str(cfg)])

    assert result.exit_code == 0, result.output
    assert "Memoria" in result.stdout
    for column in ("id", "category", "value", "tier", "updated_at"):
        assert column in result.stdout
    assert "fact-1" in result.stdout
    assert "cafe sin azucar" in result.stdout
    assert '"facts"' not in result.stdout


def test_memory_list_empty_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_config(tmp_path)

    async def fake_rpc(
        socket_path: Path, method: str, params: dict[str, object]
    ) -> dict[str, Any]:
        del socket_path, method, params
        return {"facts": []}

    monkeypatch.setattr(cli, "_json_rpc_call", fake_rpc)

    result = runner.invoke(app, ["memory", "list", "--config", str(cfg)])

    assert result.exit_code == 0, result.output
    assert "Sin memoria" in result.stdout
    assert "Siguiente paso" in result.stdout


def test_memory_edit_y_rm_invocan_rpc_correcto(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _write_config(tmp_path)
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_rpc(
        socket_path: Path, method: str, params: dict[str, object]
    ) -> dict[str, Any]:
        del socket_path
        calls.append((method, params))
        return {"ok": True}

    monkeypatch.setattr(cli, "_json_rpc_call", fake_rpc)

    edited = runner.invoke(
        app,
        ["memory", "edit", "fact-1", "mate amargo", "--config", str(cfg)],
    )
    removed = runner.invoke(app, ["memory", "rm", "fact-1", "--config", str(cfg)])

    assert edited.exit_code == 0, edited.output
    assert removed.exit_code == 0, removed.output
    assert calls == [
        ("memory.edit", {"fact_id": "fact-1", "value": "mate amargo"}),
        ("memory.forget", {"fact_id": "fact-1"}),
    ]


def test_memory_daemon_caido_es_accionable(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)

    result = runner.invoke(app, ["memory", "list", "--config", str(cfg)])

    assert result.exit_code == 1
    assert "daemon" in result.stderr
    assert "wyss start" in result.stderr
