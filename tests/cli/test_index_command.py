"""Tests del comando `wyss index`."""

import os
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

import bootstrap.cli as cli
from bootstrap.cli import app
from core.domain.config import WyssSettings
from core.domain.knowledge import EstimateResult, IngestRunResult
from core.ports.audit import AuditPort
from core.ports.knowledge import EmbeddingProvider

runner = CliRunner()


class FakePipeline:
    def __init__(
        self,
        *,
        run_result: IngestRunResult | None = None,
        dry_items: list[tuple[str, str]] | None = None,
    ) -> None:
        self._run_result = run_result or IngestRunResult(
            indexed=1,
            failed=0,
            excluded_secret=0,
            skipped=0,
            run_id="run-test",
        )
        self._dry_items = dry_items or []

    def estimate(self, root: Path, kb_id: str) -> EstimateResult:
        return EstimateResult(
            files=1,
            total_bytes=100,
            projected_chunks=1,
            embed_time_s=0.01,
            cost_usd=0.0,
        )

    def dry_run(self, root: Path, kb_id: str) -> list[tuple[str, str]]:
        return self._dry_items

    async def run(self, root: Path, kb_id: str) -> IngestRunResult:
        return self._run_result


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


def _sample_dir(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    root.mkdir()
    (root / "note.txt").write_text("texto de prueba para indexar", encoding="utf-8")
    return root


async def _fake_build_embedder() -> tuple[httpx.AsyncClient, EmbeddingProvider | None]:
    return httpx.AsyncClient(), None


def test_estimate_no_extraction(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    sample = _sample_dir(tmp_path)

    result = runner.invoke(app, ["index", str(sample), "--estimate", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "archivos" in result.output
    assert "chunks" in result.output
    assert not (tmp_path / "data" / "index.db").exists()


def test_dry_run_lists(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    sample = _sample_dir(tmp_path)

    result = runner.invoke(app, ["index", str(sample), "--dry-run", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "nuevo:" in result.output
    assert "note.txt" in result.output
    assert not (tmp_path / "data" / "index.db").exists()


def test_kb_id_in_output(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    sample = _sample_dir(tmp_path)

    result = runner.invoke(
        app,
        ["index", str(sample), "--bc", "beca", "--estimate", "--config", str(cfg)],
    )

    assert result.exit_code == 0
    assert "beca" in result.output


def test_exit_code_zero_with_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_config(tmp_path)
    sample = _sample_dir(tmp_path)
    failed_result = IngestRunResult(
        indexed=0,
        failed=1,
        excluded_secret=0,
        skipped=0,
        run_id="run-failed-files",
    )

    def fake_build_pipeline(
        settings: WyssSettings,
        *,
        audit: AuditPort,
        embedder: EmbeddingProvider | None,
    ) -> FakePipeline:
        return FakePipeline(run_result=failed_result)

    monkeypatch.setattr(cli, "_build_embedder", _fake_build_embedder)
    monkeypatch.setattr(cli, "build_pipeline", fake_build_pipeline)

    result = runner.invoke(app, ["index", str(sample), "--config", str(cfg)])

    assert result.exit_code == 0
    assert "1 fallados" in result.output


def test_exit_code_nonzero_on_systemic(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)

    result = runner.invoke(app, ["index", str(tmp_path / "missing"), "--config", str(cfg)])

    assert result.exit_code != 0
    assert "Error:" in result.output


def test_progress_modes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_config(tmp_path)
    sample = _sample_dir(tmp_path)

    def fake_build_pipeline(
        settings: WyssSettings,
        *,
        audit: AuditPort,
        embedder: EmbeddingProvider | None,
    ) -> FakePipeline:
        return FakePipeline()

    monkeypatch.setattr(cli, "_build_embedder", _fake_build_embedder)
    monkeypatch.setattr(cli, "build_pipeline", fake_build_pipeline)

    result = runner.invoke(app, ["index", str(sample), "--config", str(cfg)])

    assert result.exit_code == 0
    assert "progreso: iniciando" in result.output
    assert "corrida finalizada" in result.output


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("WYSS_TEST_OLLAMA") != "1",
    reason="requiere WYSS_TEST_OLLAMA=1 (Ollama local + nomic-embed-text)",
)
def test_index_command_with_ollama_real(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    sample = _sample_dir(tmp_path)

    result = runner.invoke(app, ["index", str(sample), "--config", str(cfg)])

    assert result.exit_code == 0
    assert "Resumen BC default" in result.output
