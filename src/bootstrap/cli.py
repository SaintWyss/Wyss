"""CLI de Wyss y composition root del pipeline de ingesta."""

import asyncio
import sqlite3
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Annotated

import httpx
import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from audit.sqlite_logger import SqliteAuditLogger
from bootstrap.config import load_settings
from core.domain.audit import AuditEvent, Span
from core.domain.config import WyssSettings
from core.domain.errors import AuditIntegrityError, ConfigError, IndexIntegrityError
from core.domain.knowledge import (
    EstimateResult,
    FileRecord,
    FileStatus,
    Hit,
    IndexEntry,
    IngestRunResult,
    Vector,
)
from core.ports.audit import AuditPort
from core.ports.knowledge import EmbeddingProvider
from gateway.providers.ollama import OllamaEmbeddingProvider
from gateway.secrets_patterns import BUILTIN_SECRET_PATTERNS
from knowledge.chunker import TokenChunker
from knowledge.extractors import (
    DocxExtractor,
    ExtractorRegistry,
    ImageExtractor,
    PdfExtractor,
    SpreadsheetExtractor,
    TextExtractor,
    VideoExtractor,
)
from knowledge.fts_index import FTS5Index
from knowledge.pipeline import IngestPipeline
from knowledge.scanner import Scanner
from knowledge.secret_filter import SecretFilter
from knowledge.state_store import StateStore
from knowledge.vector_index import ChromaVectorIndex, chromadb

app = typer.Typer(help="Wyss CLI")
console = Console()


@app.callback()
def main() -> None:
    """Herramientas operativas de Wyss."""
    return None


class _NullAudit:
    def log(self, event: AuditEvent) -> None:
        return None

    def span(self, task_id: str, actor: str, event: str) -> "_NullSpan":
        return _NullSpan(task_id=task_id, actor=actor, event=event)


class _NullSpan:
    def __init__(self, *, task_id: str, actor: str, event: str) -> None:
        self._span = Span(
            task_id=task_id,
            actor=actor,
            event=event,
            started_at=datetime.now(UTC),
        )

    def __enter__(self) -> Span:
        return self._span

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


class _PreviewStateStore:
    def needs_reindex(self, path: Path | str, kb_id: str, size: int, mtime: float) -> bool:
        return True

    def mark_extracted(
        self,
        path: Path | str,
        kb_id: str,
        *,
        size: int | None = None,
        mtime: float | None = None,
        sha256: str | None = None,
    ) -> None:
        return None

    def mark_embedded(
        self,
        path: Path | str,
        kb_id: str,
        *,
        size: int | None = None,
        mtime: float | None = None,
        sha256: str | None = None,
    ) -> None:
        return None

    def mark_failed(self, path: Path | str, kb_id: str, error: str) -> None:
        return None

    def mark_excluded_secret(self, path: Path | str, kb_id: str) -> None:
        return None

    def mark_skipped(self, path: Path | str, kb_id: str, status: FileStatus) -> None:
        return None

    def get(self, path: Path | str, kb_id: str) -> FileRecord | None:
        return None


class _NoopFullTextIndex:
    def upsert(self, entries: Sequence[IndexEntry]) -> None:
        return None

    def search(self, query: str, kb_ids: frozenset[str], limit: int) -> Sequence[Hit]:
        return ()


class _NoopVectorIndex:
    def upsert(self, entries: Sequence[tuple[IndexEntry, Vector]]) -> None:
        return None

    def search(self, vector: Vector, kb_ids: frozenset[str], limit: int) -> Sequence[Hit]:
        return ()


def build_pipeline(
    settings: WyssSettings,
    *,
    audit: AuditPort,
    embedder: EmbeddingProvider | None,
) -> IngestPipeline:
    """Arma el pipeline real con DI manual desde `WyssSettings`."""
    state_store = StateStore(
        settings.data_dir / "index.db",
        max_attempts=settings.ingest.max_attempts,
    )
    fts_index = FTS5Index(state_store._conn)
    registry = _build_registry()
    chunker = TokenChunker(
        chunk_size_tokens=settings.ingest.chunk_size_tokens,
        chunk_overlap_tokens=settings.ingest.chunk_overlap_tokens,
    )
    chroma_client = chromadb.PersistentClient(path=str(settings.data_dir / "chroma"))
    vector_index = ChromaVectorIndex(chroma_client)
    secret_filter = SecretFilter(
        builtin_patterns=BUILTIN_SECRET_PATTERNS,
        entropy_allowlist=frozenset(settings.ingest.entropy_allowlist),
    )
    return IngestPipeline(
        scanner=Scanner(),
        secret_filter=secret_filter,
        registry=registry,
        chunker=chunker,
        state_store=state_store,
        fts_index=fts_index,
        embedder=embedder,
        vector_index=vector_index,
        audit=audit,
        settings=settings.ingest,
    )


@app.command()
def index(
    ruta: Path,
    bc: Annotated[str, typer.Option("--bc", help="Base de conocimiento destino.")] = "default",
    estimate: Annotated[
        bool,
        typer.Option("--estimate", help="Proyecta trabajo sin escribir."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Lista archivos sin escribir."),
    ] = False,
    retry_failed: Annotated[
        bool,
        typer.Option("--retry-failed", help="Reintenta fallos agotados."),
    ] = False,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Indexa una ruta local en una base de conocimiento."""
    http_client: httpx.AsyncClient | None = None
    audit: SqliteAuditLogger | _NullAudit | None = None
    pipeline: IngestPipeline | None = None

    try:
        settings = load_settings(config)
        kb_id = bc or settings.ingest.default_kb_id
        if not ruta.exists():
            raise NotADirectoryError(str(ruta))

        console.print(f"BC: {kb_id}")
        if retry_failed:
            console.print("retry_failed: true")

        if estimate or dry_run:
            audit = _NullAudit()
            pipeline = _build_preview_pipeline(settings, audit=audit)
        else:
            audit = SqliteAuditLogger(settings.audit_db)
            http_client, embedder = asyncio.run(_build_embedder())
            if embedder is None:
                console.print("Aviso: Ollama no disponible; se indexa sin embeddings.")
            pipeline = build_pipeline(settings, audit=audit, embedder=embedder)

        if estimate:
            _print_estimate(pipeline.estimate(ruta, kb_id))
            return

        if dry_run:
            _print_dry_run(pipeline.dry_run(ruta, kb_id), kb_id)
            return

        result = _run_with_progress(pipeline, ruta, kb_id)
        _print_summary(result, kb_id)
    except (ConfigError, NotADirectoryError, IndexIntegrityError, AuditIntegrityError) as exc:
        console.print(f"Error: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    finally:
        if pipeline is not None:
            _close_pipeline_state_store(pipeline)
        if audit is not None and hasattr(audit, "close"):
            audit.close()
        if http_client is not None:
            asyncio.run(http_client.aclose())


def _build_registry() -> ExtractorRegistry:
    registry = ExtractorRegistry()
    registry.register(PdfExtractor())
    registry.register(DocxExtractor())
    registry.register(TextExtractor())
    registry.register(SpreadsheetExtractor())
    registry.register(ImageExtractor())
    registry.register(VideoExtractor())
    return registry


def _build_preview_pipeline(settings: WyssSettings, *, audit: AuditPort) -> IngestPipeline:
    return IngestPipeline(
        scanner=Scanner(),
        secret_filter=SecretFilter(
            builtin_patterns=BUILTIN_SECRET_PATTERNS,
            entropy_allowlist=frozenset(settings.ingest.entropy_allowlist),
        ),
        registry=_build_registry(),
        chunker=TokenChunker(
            chunk_size_tokens=settings.ingest.chunk_size_tokens,
            chunk_overlap_tokens=settings.ingest.chunk_overlap_tokens,
        ),
        state_store=_PreviewStateStore(),
        fts_index=_NoopFullTextIndex(),
        embedder=None,
        vector_index=_NoopVectorIndex(),
        audit=audit,
        settings=settings.ingest,
    )


async def _build_embedder() -> tuple[httpx.AsyncClient, EmbeddingProvider | None]:
    client = httpx.AsyncClient(timeout=httpx.Timeout(2.0))
    try:
        response = await client.get("http://localhost:11434/api/tags")
        response.raise_for_status()
    except (httpx.HTTPError, httpx.TransportError):
        return client, None
    return client, OllamaEmbeddingProvider(client)


def _run_with_progress(pipeline: IngestPipeline, ruta: Path, kb_id: str) -> IngestRunResult:
    if sys.stdout.isatty():
        total = max(pipeline.estimate(ruta, kb_id).files, 1)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:
            task_id = progress.add_task("Indexando", total=total)
            result = asyncio.run(pipeline.run(ruta, kb_id))
            progress.update(task_id, completed=total)
            return result

    console.print(f"progreso: iniciando indexacion de {ruta} en BC {kb_id}")
    result = asyncio.run(pipeline.run(ruta, kb_id))
    console.print("progreso: corrida finalizada")
    return result


def _print_estimate(result: EstimateResult) -> None:
    table = Table(title="Estimacion de ingesta")
    table.add_column("Metrica")
    table.add_column("Valor")
    table.add_row("archivos", str(result.files))
    table.add_row("bytes", str(result.total_bytes))
    table.add_row("chunks", str(result.projected_chunks))
    table.add_row("tiempo embedding", f"{result.embed_time_s:.2f}s")
    table.add_row("costo API", "$0 (Ollama local)")
    console.print(table)


def _print_dry_run(items: Sequence[tuple[str, str]], kb_id: str) -> None:
    console.print(f"Dry run BC: {kb_id}")
    if not items:
        console.print("Nada para indexar.")
        return
    for path, reason in items:
        console.print(f"{reason}: {path}")


def _print_summary(result: IngestRunResult, kb_id: str) -> None:
    console.print(
        f"Resumen BC {kb_id}: {result.indexed} indexados, {result.failed} fallados, "
        f"{result.excluded_secret} excluidos por secretos, {result.skipped} skipped"
    )
    for warning in result.warnings:
        console.print(f"Aviso: {warning}")


def _close_pipeline_state_store(pipeline: IngestPipeline) -> None:
    state_store = getattr(pipeline, "_state_store", None)
    if state_store is not None and hasattr(state_store, "close"):
        state_store.close()


__all__ = ["app", "build_pipeline"]
