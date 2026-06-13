"""CLI de Wyss y composition root del pipeline de ingesta."""

import asyncio
import json
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Annotated, Any

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from audit.sqlite_logger import SqliteAuditLogger
from bootstrap.config import load_settings
from core.domain.audit import ActorType, AuditEvent, Span
from core.domain.config import WyssSettings
from core.domain.errors import AuditIntegrityError, ConfigError, IndexIntegrityError
from core.domain.knowledge import (
    EstimateResult,
    FileRecord,
    FileStatus,
    Hit,
    IndexEntry,
    IngestRunResult,
    Query,
    Vector,
)
from core.domain.plan import Action, ErrorPolicy, Plan, RetryParams
from core.domain.policy import PolicyDecision
from core.domain.risk import Outcome, RiskLevel
from core.domain.security import Subject
from core.orchestrator.intent import IntentCategory, IntentClassification
from core.policy import CognitivePolicyEngine
from core.ports.audit import AuditPort
from core.ports.knowledge import EmbeddingProvider
from gateway.providers.ollama import OllamaEmbeddingProvider
from gateway.secrets_patterns import BUILTIN_SECRET_PATTERNS
from knowledge.chunker import TokenChunker
from knowledge.extractors import (
    DocxExtractor,
    ExtractorRegistry,
    HtmlExtractor,
    ImageExtractor,
    PdfExtractor,
    RtfExtractor,
    SpreadsheetExtractor,
    TextExtractor,
    VideoExtractor,
)
from knowledge.fts_index import FTS5Index
from knowledge.pipeline import IngestPipeline
from knowledge.retrieval import HybridRetrieval
from knowledge.scanner import Scanner
from knowledge.secret_filter import SecretFilter
from knowledge.state_store import BcFreshness, StateStore
from knowledge.vector_index import ChromaVectorIndex, chromadb
from orchestrator.daemon import run_daemon
from orchestrator.pending_store import PendingStore
from orchestrator.plan_renderer import prompt_confirmation

app = typer.Typer(help="Wyss CLI")
console = Console()
stderr_console = Console(stderr=True)


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


class _DeterministicOrchestrator:
    """Fake local de 05-04: Hermes real se conecta en el plan 05-05."""

    async def classify_intent(self, instruction: str) -> IntentClassification:
        text = instruction.lower()
        if "algo" in text and "archivo" in text:
            return IntentClassification(IntentCategory.AMBIGUOUS_REQUEST, 0.4, True)
        if any(word in text for word in ("formate", "mkfs", "fdisk", "parted")):
            return IntentClassification(IntentCategory.DANGEROUS_OPERATION, 0.95, False)
        if any(word in text for word in ("borr", "elimin", "delete")):
            return IntentClassification(IntentCategory.FILE_OPERATION, 0.9, False)
        if any(word in text for word in ("mov", "renombr")):
            return IntentClassification(IntentCategory.FILE_OPERATION, 0.85, False)
        return IntentClassification(IntentCategory.KNOWLEDGE_QUERY, 0.8, False)

    async def draft_plan(self, instruction: str, intent: IntentClassification) -> Plan:
        text = instruction.lower()
        task_id = f"cli-{abs(hash(instruction))}"
        if intent.category == IntentCategory.DANGEROUS_OPERATION:
            action = Action("shell.run", "mkfs /dev/sda1")
        elif any(word in text for word in ("borr", "elimin", "delete")):
            action = Action("file.delete", "/tmp/wyss-demo.txt", {"to_trash": True})
        elif any(word in text for word in ("mov", "renombr")):
            action = Action("file.move", "/tmp/wyss-demo.txt")
        else:
            action = Action("file.read", "/tmp/wyss-demo.txt")
        return Plan(
            task_id=task_id,
            summary=instruction,
            steps=(action,),
            rationale="fake determinístico hasta integrar Hermes",
        )

    async def health_check(self) -> bool:
        return True


@dataclass(frozen=True, slots=True)
class AuditRow:
    created_at: str
    actor_id: str
    event_type: str
    message: str


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


def build_retrieval(
    settings: WyssSettings,
    *,
    audit: AuditPort,
    embedder: EmbeddingProvider | None,
) -> tuple[HybridRetrieval, StateStore]:
    """Arma retrieval real y devuelve el StateStore compartido para frescura/cierre."""
    state_store = StateStore(settings.data_dir / "index.db")
    fts_index = FTS5Index(state_store._conn)
    chroma_client = chromadb.PersistentClient(path=str(settings.data_dir / "chroma"))
    vector_index = ChromaVectorIndex(chroma_client)
    retrieval = HybridRetrieval(
        fts_index=fts_index,
        vector_index=vector_index,
        embedder=embedder,
        audit=audit,
        state_store=state_store,
    )
    return retrieval, state_store


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


@app.command()
def start(
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Levanta el daemon Wyss sobre Unix socket."""
    audit: SqliteAuditLogger | None = None
    pending_store: PendingStore | None = None
    try:
        settings = load_settings(config)
        audit = SqliteAuditLogger(settings.audit_db)
        pending_store = PendingStore(_pending_db_path(settings))
        engine = CognitivePolicyEngine(settings.policy)
        asyncio.run(
            run_daemon(
                _socket_path(settings),
                engine=engine,
                orchestrator=_DeterministicOrchestrator(),
                pending_store=pending_store,
                audit=audit,
            )
        )
    except (ConfigError, AuditIntegrityError) as exc:
        stderr_console.print(f"Error: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    finally:
        if pending_store is not None:
            pending_store.close()
        if audit is not None:
            audit.close()


@app.command()
def ask(
    instruction: str,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Envía una instrucción NL al daemon."""
    try:
        settings = load_settings(config)
        result = asyncio.run(
            _json_rpc_call(
                _socket_path(settings),
                "ask",
                {"instruction": instruction},
            )
        )
        _render_ask_result(result)
    except FileNotFoundError as exc:
        stderr_console.print("Daemon no está corriendo. Usar: wyss start", style="red")
        raise typer.Exit(code=1) from exc
    except (ConfigError, AuditIntegrityError) as exc:
        stderr_console.print(f"Error: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc


@app.command()
def confirm(
    pending_id: str,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Confirma una propuesta pendiente sin ejecutar en foreground."""
    pending_store: PendingStore | None = None
    try:
        settings = load_settings(config)
        pending_store = PendingStore(_pending_db_path(settings))
        proposal = pending_store.load(pending_id)
        if proposal is None:
            stderr_console.print("Pending no encontrado.", style="red")
            raise typer.Exit(code=1)
        decision = PolicyDecision(
            task_id=proposal.task_id,
            risk_level=RiskLevel[proposal.risk_level],
            outcome=Outcome[proposal.outcome],
        )
        accepted = prompt_confirmation(decision, console)
        response = "CONFIRMAR" if accepted and decision.risk_level == RiskLevel.C else "s"
        if not accepted:
            response = ""
        result = asyncio.run(
            _json_rpc_call(
                _socket_path(settings),
                "confirm",
                {"pending_id": pending_id, "response": response},
            )
        )
        _render_confirm_result(result)
    except FileNotFoundError as exc:
        stderr_console.print("Daemon no está corriendo. Usar: wyss start", style="red")
        raise typer.Exit(code=1) from exc
    except (ConfigError, AuditIntegrityError) as exc:
        stderr_console.print(f"Error: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error, RuntimeError, KeyError) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    finally:
        if pending_store is not None:
            pending_store.close()


@app.command()
def audit(
    since: Annotated[str | None, typer.Option("--since", help="ISO timestamp mínimo.")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Eventos máximos.")] = 50,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Lista el historial auditado."""
    try:
        settings = load_settings(config)
        _print_audit_table(query_audit_events(settings.audit_db, since=since, limit=limit))
    except (ConfigError, AuditIntegrityError) as exc:
        stderr_console.print(f"Error: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc


@app.command()
def search(
    query: str,
    kb: Annotated[str | None, typer.Option("--kb", help="Acotar a BC.")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Resultados máximos.")] = 10,
    json_output: Annotated[bool, typer.Option("--json", help="Salida JSON.")] = False,
    fts_only: Annotated[
        bool,
        typer.Option("--fts-only", help="Forzar modo FTS5-only."),
    ] = False,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Busca en bases de conocimiento con retrieval híbrido FTS5 + vectores."""
    http_client: httpx.AsyncClient | None = None
    audit: SqliteAuditLogger | None = None
    state_store: StateStore | None = None

    try:
        settings = load_settings(config)
        audit = SqliteAuditLogger(settings.audit_db)
        if fts_only:
            embedder: EmbeddingProvider | None = None
        else:
            http_client, embedder = asyncio.run(_build_embedder())

        retrieval, state_store = build_retrieval(settings, audit=audit, embedder=embedder)
        available_kb_ids = state_store.list_kb_ids()
        if kb is not None:
            if kb not in available_kb_ids:
                stderr_console.print(
                    f"Error: knowledge base '{kb}' not found. "
                    f"Available: {_format_available_kbs(available_kb_ids)}",
                    style="red",
                )
                raise typer.Exit(code=1)
            kb_ids = frozenset({kb})
        else:
            kb_ids = frozenset(available_kb_ids)

        retrieval_query = Query(query, kb_ids, limit)
        subject = Subject(subject_id="owner", subject_type=ActorType.OWNER)
        result = asyncio.run(retrieval.search(retrieval_query, subject))

        if result.degraded:
            _print_degraded_banner(result.reason)

        if json_output or not _stdout_is_tty():
            print(json.dumps([_hit_to_json(hit) for hit in result.hits]))
        else:
            _print_search_panels(result.hits, kb_ids)

        _print_freshness_footer(state_store.freshness_by_kb())
    except (ConfigError, IndexIntegrityError, AuditIntegrityError) as exc:
        stderr_console.print(f"Error: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    finally:
        if state_store is not None:
            state_store.close()
        if audit is not None:
            audit.close()
        if http_client is not None:
            asyncio.run(http_client.aclose())


@app.command()
def status(
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Muestra frescura y estado del índice por base de conocimiento."""
    state_store: StateStore | None = None
    try:
        settings = load_settings(config)
        state_store = StateStore(settings.data_dir / "index.db")
        _print_status_table(state_store.freshness_by_kb())
    except (ConfigError, IndexIntegrityError, AuditIntegrityError) as exc:
        stderr_console.print(f"Error: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    finally:
        if state_store is not None:
            state_store.close()


def _build_registry() -> ExtractorRegistry:
    registry = ExtractorRegistry()
    registry.register(PdfExtractor())
    registry.register(DocxExtractor())
    registry.register(HtmlExtractor())
    registry.register(RtfExtractor())
    registry.register(TextExtractor())
    registry.register(SpreadsheetExtractor())
    registry.register(ImageExtractor())
    registry.register(VideoExtractor())
    return registry


def _stdout_is_tty() -> bool:
    return sys.stdout.isatty()


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


def _hit_to_json(hit: Hit) -> dict[str, object]:
    return {
        "entry_id": hit.entry_id,
        "score": hit.score,
        "snippet": hit.snippet,
        "source_path": hit.source_path,
        "date": hit.date,
    }


def _print_degraded_banner(reason: str) -> None:
    detail = reason or "fts-only mode"
    stderr_console.print(f"[degradado] {detail} — solo FTS5", style="yellow", markup=False)


def _print_search_panels(hits: Sequence[Hit], kb_ids: frozenset[str]) -> None:
    if not hits:
        console.print("Sin resultados.")
        return

    source = "all" if len(kb_ids) != 1 else next(iter(kb_ids))
    for position, hit in enumerate(hits, start=1):
        body = (
            f"Ruta: {hit.source_path}\n"
            f"Fuente: {source}/{hit.entry_id}\n"
            f"Fecha: {_format_timestamp(hit.date)}\n"
            f"Score: {hit.score:.6f}\n\n"
            f"{hit.snippet}"
        )
        console.print(Panel(body, title=f"Resultado {position}", expand=False))


def _print_freshness_footer(freshness: Sequence[BcFreshness]) -> None:
    latest = max(
        (item.last_indexed_at for item in freshness if item.last_indexed_at is not None),
        default=None,
    )
    stderr_console.print(f"indexado al {_format_timestamp(latest)} · {len(freshness)} BCs")


def _print_status_table(freshness: Sequence[BcFreshness]) -> None:
    table = Table(title="Estado del índice")
    table.add_column("BC")
    table.add_column("Última indexación", no_wrap=True)
    table.add_column("Total", justify="right")
    table.add_column("Embebidos", justify="right")
    table.add_column("Pendientes", justify="right")
    table.add_column("Fallados", justify="right")
    for item in freshness:
        table.add_row(
            item.kb_id,
            _format_timestamp(item.last_indexed_at),
            str(item.total),
            str(item.embedded),
            str(item.pending),
            str(item.failed),
        )
    console.print(table)


def _format_timestamp(value: float | None) -> str:
    if value is None:
        return "nunca indexado"
    return datetime.fromtimestamp(value, UTC).isoformat(timespec="seconds")


def _format_available_kbs(kb_ids: Sequence[str]) -> str:
    if not kb_ids:
        return "(none)"
    return ", ".join(kb_ids)


def _socket_path(settings: WyssSettings) -> Path:
    return settings.data_dir / "wyss.sock"


def _pending_db_path(settings: WyssSettings) -> Path:
    return settings.data_dir / "pending.db"


async def _json_rpc_call(
    socket_path: Path, method: str, params: dict[str, object]
) -> dict[str, Any]:
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        writer.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "method": method,
                    "params": params,
                    "id": 1,
                }
            ).encode()
            + b"\n"
        )
        await writer.drain()
        response = json.loads(await reader.readline())
        if "error" in response:
            error = response["error"]
            message = error.get("message", "JSON-RPC error") if isinstance(error, dict) else error
            raise RuntimeError(str(message))
        result = response.get("result", {})
        if not isinstance(result, dict):
            raise RuntimeError("respuesta JSON-RPC inválida")
        return result
    finally:
        writer.close()
        await writer.wait_closed()


def _render_ask_result(result: dict[str, Any]) -> None:
    outcome = str(result.get("outcome", ""))
    if outcome == "pending":
        console.print(
            Panel(
                str(result.get("plan", "")),
                title=f"Pending {result.get('pending_id')}",
                expand=False,
            )
        )
        return
    if outcome == "rejected":
        reasons = "\n".join(str(item) for item in result.get("reasons", []))
        console.print(Panel(reasons or "Sin detalle.", title="Rechazado", expand=False))
        return
    if outcome == "queued":
        console.print(f"Encolado: {result.get('execution_id')}")
        return
    if outcome == "degraded":
        stderr_console.print(
            str(result.get("message", "Orquestador no disponible.")),
            style="yellow",
        )
        return
    console.print(str(result.get("message", result)))


def _render_confirm_result(result: dict[str, Any]) -> None:
    if result.get("accepted"):
        console.print(f"Encolado: {result.get('execution_id')}")
        return
    reason = result.get("reason")
    console.print(f"No confirmado{f': {reason}' if reason else ''}.")


def query_audit_events(
    db_path: Path, *, since: str | None = None, limit: int = 50
) -> list[AuditRow]:
    sql = (
        "SELECT created_at, actor_id, event_type, message FROM audit_events "
        f"{'WHERE created_at >= ? ' if since is not None else ''}"
        "ORDER BY created_at DESC LIMIT ?"
    )
    params: tuple[object, ...] = (since, limit) if since is not None else (limit,)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()
    return [
        AuditRow(
            created_at=str(row[0]),
            actor_id=str(row[1]),
            event_type=str(row[2]),
            message=str(row[3]),
        )
        for row in rows
    ]


def _print_audit_table(rows: Sequence[AuditRow]) -> None:
    table = Table(title="Auditoría")
    table.add_column("created_at", no_wrap=True)
    table.add_column("actor_id")
    table.add_column("event_type")
    table.add_column("message")
    for row in rows:
        table.add_row(row.created_at, row.actor_id, row.event_type, row.message)
    console.print(table)


def _plan_from_json(raw: str) -> Plan:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("plan_json inválido")
    return Plan(
        task_id=str(data["task_id"]),
        summary=str(data["summary"]),
        steps=tuple(_action_from_dict(item) for item in data.get("steps", [])),
        rationale=str(data["rationale"]),
        estimated_risk=(
            RiskLevel[str(data["estimated_risk"])] if data.get("estimated_risk") else None
        ),
    )


def _action_from_dict(data: object) -> Action:
    if not isinstance(data, dict):
        raise ValueError("action inválida")
    retry_raw = data.get("retry_params")
    retry_params = None
    if isinstance(retry_raw, dict):
        retry_params = RetryParams(
            max_attempts=int(retry_raw.get("max_attempts", 3)),
            backoff_base_s=float(retry_raw.get("backoff_base_s", 1.0)),
            backoff_max_s=float(retry_raw.get("backoff_max_s", 60.0)),
        )
    params = data.get("parameters", {})
    if not isinstance(params, dict):
        params = {}
    return Action(
        type=str(data["type"]),
        target=str(data["target"]),
        parameters=params,
        on_error=ErrorPolicy(str(data.get("on_error", ErrorPolicy.ABORT.value))),
        retry_params=retry_params,
    )


def _close_pipeline_state_store(pipeline: IngestPipeline) -> None:
    state_store = getattr(pipeline, "_state_store", None)
    if state_store is not None and hasattr(state_store, "close"):
        state_store.close()


__all__ = ["app", "build_pipeline", "build_retrieval", "query_audit_events"]
