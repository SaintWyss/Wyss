"""Scaffolds de los comandos `wyss search` y `wyss status`."""

import json
from pathlib import Path
from typing import Any

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
        self.queries: list[Query] = []

    async def search(self, query: Query, subject: Subject) -> SearchResult:
        self.queries.append(query)
        return self._result


class FakeStateStore:
    def __init__(
        self,
        *,
        kb_ids: list[str] | None = None,
        freshness: list[BcFreshness] | None = None,
    ) -> None:
        self._kb_ids = kb_ids or ["personal"]
        self._freshness = freshness or [
            BcFreshness(
                kb_id="personal",
                last_indexed_at=1_700_000_000.0,
                total=2,
                embedded=1,
                pending=1,
                failed=0,
            )
        ]
        self.closed = False

    def list_kb_ids(self) -> list[str]:
        return self._kb_ids

    def freshness_by_kb(self) -> list[BcFreshness]:
        return self._freshness

    def close(self) -> None:
        self.closed = True


async def _fake_build_embedder() -> tuple[httpx.AsyncClient, EmbeddingProvider | None]:
    return httpx.AsyncClient(), None


def _hit() -> Hit:
    return Hit(
        entry_id="entry-1",
        score=0.42,
        snippet="needle aparece en este extracto",
        source_path="/docs/personal.md",
        date=1_700_000_000.0,
    )


def test_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_config(tmp_path)
    fake_state = FakeStateStore()
    fake_retrieval = FakeRetrieval(
        SearchResult(hits=(_hit(),), degraded=True, reason="ollama unavailable")
    )

    def fake_build_retrieval(
        settings: WyssSettings,
        *,
        audit: AuditPort,
        embedder: EmbeddingProvider | None,
    ) -> tuple[FakeRetrieval, FakeStateStore]:
        return fake_retrieval, fake_state

    monkeypatch.setattr(cli, "_build_embedder", _fake_build_embedder)
    monkeypatch.setattr(cli, "build_retrieval", fake_build_retrieval)

    result = runner.invoke(app, ["search", "needle", "--json", "--config", str(cfg)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert payload == [
        {
            "entry_id": "entry-1",
            "score": 0.42,
            "snippet": "needle aparece en este extracto",
            "source_path": "/docs/personal.md",
            "date": 1_700_000_000.0,
        }
    ]
    assert "degradado" not in result.stdout
    assert "degradado" in result.stderr
    assert "indexado al" in result.stderr


def test_rich_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_config(tmp_path)
    fake_state = FakeStateStore()
    fake_retrieval = FakeRetrieval(SearchResult(hits=(_hit(),)))

    def fake_build_retrieval(
        settings: WyssSettings,
        *,
        audit: AuditPort,
        embedder: EmbeddingProvider | None,
    ) -> tuple[FakeRetrieval, FakeStateStore]:
        return fake_retrieval, fake_state

    monkeypatch.setattr(cli, "_build_embedder", _fake_build_embedder)
    monkeypatch.setattr(cli, "build_retrieval", fake_build_retrieval)
    monkeypatch.setattr(cli, "_stdout_is_tty", lambda: True)

    result = runner.invoke(app, ["search", "needle", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "Resultado 1" in result.stdout
    assert "/docs/personal.md" in result.stdout
    assert "needle aparece" in result.stdout
    assert "indexado al" in result.stderr


def test_unknown_kb(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_config(tmp_path)
    fake_state = FakeStateStore(kb_ids=["personal"])
    fake_retrieval = FakeRetrieval(SearchResult(hits=(_hit(),)))

    def fake_build_retrieval(
        settings: WyssSettings,
        *,
        audit: AuditPort,
        embedder: EmbeddingProvider | None,
    ) -> tuple[FakeRetrieval, FakeStateStore]:
        return fake_retrieval, fake_state

    monkeypatch.setattr(cli, "_build_embedder", _fake_build_embedder)
    monkeypatch.setattr(cli, "build_retrieval", fake_build_retrieval)

    result = runner.invoke(
        app,
        ["search", "needle", "--kb", "noexiste", "--config", str(cfg)],
    )

    assert result.exit_code == 1
    assert "no encontrada" in result.stderr
    assert "personal" in result.stderr
    assert "wyss index" in result.stderr


def test_degraded_exit_code_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_config(tmp_path)
    fake_state = FakeStateStore()
    fake_retrieval = FakeRetrieval(
        SearchResult(hits=(_hit(),), degraded=True, reason="fts-only mode")
    )

    def fake_build_retrieval(
        settings: WyssSettings,
        *,
        audit: AuditPort,
        embedder: EmbeddingProvider | None,
    ) -> tuple[FakeRetrieval, FakeStateStore]:
        return fake_retrieval, fake_state

    monkeypatch.setattr(cli, "build_retrieval", fake_build_retrieval)

    result = runner.invoke(app, ["search", "needle", "--fts-only", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "degradado" in result.stderr


def test_status_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _write_config(tmp_path)

    class StatusStateStore(FakeStateStore):
        def __init__(self, db_path: Path, **kwargs: Any) -> None:
            super().__init__(
                freshness=[
                    BcFreshness(
                        kb_id="personal",
                        last_indexed_at=1_700_000_000.0,
                        total=3,
                        embedded=2,
                        pending=1,
                        failed=0,
                    ),
                    BcFreshness(
                        kb_id="ragcorp",
                        last_indexed_at=None,
                        total=1,
                        embedded=0,
                        pending=0,
                        failed=1,
                    ),
                ]
            )

    monkeypatch.setattr(cli, "StateStore", StatusStateStore)

    result = runner.invoke(app, ["status", "--config", str(cfg)])

    assert result.exit_code == 0
    assert "Estado del índice" in result.stdout
    assert "personal" in result.stdout
    assert "ragcorp" in result.stdout
    assert "2023-11-14T22:13:20+00:00" in result.stdout
    assert "nunca indexado" in result.stdout
