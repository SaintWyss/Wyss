"""Tests de UX de la CLI (PR-07): errores accionables, empty states y exit codes.

Asserts por substring estable (no frase exacta) para no fijar la redacción.
"""

import json
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import bootstrap.cli as cli
from bootstrap.cli import app
from core.domain.config import WyssSettings
from core.domain.knowledge import Hit, Query, SearchResult
from core.domain.security import Subject
from core.ports.audit import AuditPort
from core.ports.knowledge import EmbeddingProvider
from knowledge.state_store import BcFreshness

runner = CliRunner()


def _write_config(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    audit_db = tmp_path / "audit" / "audit.db"
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f"""\
data_dir = "{data_dir}"
audit_db = "{audit_db}"

[ingest]
chunk_size_tokens = 16
chunk_overlap_tokens = 1
""",
        encoding="utf-8",
    )
    return cfg


class FakeRetrieval:
    def __init__(self, result: SearchResult) -> None:
        self._result = result

    async def search(self, query: Query, subject: Subject) -> SearchResult:
        return self._result


class FakeStateStore:
    def __init__(
        self,
        *,
        kb_ids: list[str] | None = None,
        freshness: list[BcFreshness] | None = None,
    ) -> None:
        self._kb_ids = kb_ids if kb_ids is not None else ["personal"]
        self._freshness = freshness if freshness is not None else []

    def list_kb_ids(self) -> list[str]:
        return self._kb_ids

    def freshness_by_kb(self) -> list[BcFreshness]:
        return self._freshness

    def close(self) -> None:
        return None


async def _fake_build_embedder() -> tuple[httpx.AsyncClient, EmbeddingProvider | None]:
    return httpx.AsyncClient(), None


def _patch_search(
    monkeypatch: pytest.MonkeyPatch,
    *,
    kb_ids: list[str],
    hits: tuple[Hit, ...] = (),
) -> None:
    fake_state = FakeStateStore(kb_ids=kb_ids)
    fake_retrieval = FakeRetrieval(SearchResult(hits=hits))

    def fake_build_retrieval(
        settings: WyssSettings,
        *,
        audit: AuditPort,
        embedder: EmbeddingProvider | None,
    ) -> tuple[FakeRetrieval, FakeStateStore]:
        return fake_retrieval, fake_state

    monkeypatch.setattr(cli, "_build_embedder", _fake_build_embedder)
    monkeypatch.setattr(cli, "build_retrieval", fake_build_retrieval)


def test_ask_daemon_caido(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)

    result = runner.invoke(app, ["ask", "hola", "--config", str(cfg)])

    assert result.exit_code == 1
    assert "daemon" in result.stderr
    assert "wyss start" in result.stderr


def test_confirm_daemon_caido(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    (tmp_path / "data").mkdir()

    result = runner.invoke(app, ["confirm", "nope", "--config", str(cfg)])

    assert result.exit_code == 1
    assert "nope" in result.stderr
    assert "wyss ask" in result.stderr
    # typer.Exit hereda de RuntimeError: no debe caer en el except sistémico.
    assert "Error sistémico" not in result.stderr


def test_start_daemon_ya_corriendo_es_accionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PR-14 (smoke físico): 'daemon ya corriendo' salía como traceback crudo de
    80 líneas y se leyó como fallo fatal — debe ser un panel accionable."""
    cfg = _write_config(tmp_path)

    async def fake_run(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("daemon ya corriendo en data/wyss.sock")

    monkeypatch.setattr(cli, "_run_start_daemon", fake_run)

    result = runner.invoke(app, ["start", "--config", str(cfg)])

    assert result.exit_code == 1
    assert "ya corriendo" in result.stderr
    assert "ya está arriba" in result.stderr
    assert "Traceback" not in result.stderr
    assert "Error sistémico" not in result.stderr


def test_audit_sin_db(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)

    result = runner.invoke(app, ["audit", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "audit.db no existe" in result.stdout
    assert "Siguiente paso" in result.stdout


def test_audit_sin_eventos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_config(tmp_path)
    audit_db = tmp_path / "audit" / "audit.db"
    audit_db.parent.mkdir(parents=True)
    audit_db.touch()
    monkeypatch.setattr(cli, "query_audit_events", lambda *args, **kwargs: [])

    result = runner.invoke(app, ["audit", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "Sin eventos" in result.stdout
    assert "Siguiente paso" in result.stdout


def test_search_indice_vacio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_config(tmp_path)
    _patch_search(monkeypatch, kb_ids=[])
    monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)

    result = runner.invoke(app, ["search", "needle", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "Índice vacío" in result.stdout
    assert "wyss index" in result.stdout


def test_search_sin_resultados(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_config(tmp_path)
    _patch_search(monkeypatch, kb_ids=["personal"])
    monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)

    result = runner.invoke(app, ["search", "needle", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "Sin resultados" in result.stdout
    assert "wyss index" in result.stdout


def test_search_json_vacio_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Contrato D-43: --json siempre emite una lista JSON, aun sin resultados."""
    cfg = _write_config(tmp_path)
    _patch_search(monkeypatch, kb_ids=["personal"])

    result = runner.invoke(app, ["search", "needle", "--json", "--config", str(cfg)])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == []


def test_status_indice_vacio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_config(tmp_path)

    class EmptyStateStore(FakeStateStore):
        def __init__(self, db_path: Path) -> None:
            super().__init__(freshness=[])

    monkeypatch.setattr(cli, "StateStore", EmptyStateStore)

    result = runner.invoke(app, ["status", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "Índice vacío" in result.stdout
    assert "wyss index" in result.stdout


def test_fin_ver_vacio(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    (tmp_path / "data").mkdir()

    result = runner.invoke(app, ["fin", "ver", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "Ledger vacío" in result.stdout
    assert "fin add-ingreso" in result.stdout


def test_fin_monto_no_positivo(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)

    result = runner.invoke(app, ["fin", "add-ingreso", "0", "sueldo", "--config", str(cfg)])

    assert result.exit_code == 1
    assert "positivo" in result.stderr


def test_mal_uso_exit_code_2() -> None:
    """Convención Typer: argumentos faltantes = exit code 2."""
    result = runner.invoke(app, ["fin", "add-ingreso"])

    assert result.exit_code == 2
