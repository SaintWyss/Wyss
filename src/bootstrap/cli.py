"""CLI de Wyss y composition root del pipeline de ingesta."""

import asyncio
import json
import os
import secrets
import sqlite3
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Annotated, Any

import httpx
import typer
import uvicorn
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeRemainingColumn
from rich.table import Table

from adapters.sqlite_idempotency import SqliteIdempotencyStore
from audit.sqlite_logger import SqliteAuditLogger
from bootstrap.config import WyssSettings as BootstrapWyssSettings
from bootstrap.config import load_settings
from bootstrap.gateway import build_gateway
from core.domain import TipoTransaccion, Transaccion
from core.domain.audit import ActorType, AuditEvent, AuditEventType, Span
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
from execution.executor import PlanExecutor
from execution.filesystem import FileSystemAdapter
from execution.git import GitAdapter
from execution.guard import DeterministicExecutionGuard
from execution.journal import UndoJournal
from execution.shell import ShellAdapter
from execution.undo import UndoStep, apply_undo, inverse_plan, plan_undo
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
from ledger.sqlite_store import SqliteLedgerStore
from memory.store import MemoryStore
from memory.tool import MemoryTool
from notion.client import build_notion_client
from notion.tool import NotionTool
from orchestrator.daemon import run_daemon
from orchestrator.llm_orchestrator import LLMOrchestrator
from orchestrator.pending_store import PendingStore
from orchestrator.plan_renderer import prompt_confirmation
from orchestrator.routine_store import RoutineStore
from orchestrator.scheduler import RoutineScheduler, preview_next_fires, validate_schedule

app = typer.Typer(help="Wyss CLI")
fin_app = typer.Typer(help="Ledger de finanzas")
routine_app = typer.Typer(help="Rutinas programadas")
memory_app = typer.Typer(help="Memoria del owner")
app.add_typer(fin_app, name="fin")
app.add_typer(routine_app, name="routine")
app.add_typer(memory_app, name="memory")
console = Console()
stderr_console = Console(stderr=True)

_ACCION_CONFIG = (
    "revisá config/config.toml (o el archivo pasado con --config); "
    "las claves de API van en config/.env"
)
_ACCION_INTEGRIDAD = (
    "data_dir y audit_db deben vivir en un filesystem con soporte WAL "
    "(disco local); revisá config.toml"
)


def _error_panel(causa: str, accion: str) -> None:
    """Error accionable al owner: qué pasó + qué hacer. Siempre a stderr."""
    stderr_console.print(f"Error: {causa}", style="red", soft_wrap=True)
    stderr_console.print(f"→ {accion}", style="red", soft_wrap=True)


def _empty_state(mensaje: str, siguiente_comando: str) -> None:
    """Empty state informativo: qué está vacío + el próximo comando sugerido."""
    console.print(mensaje, soft_wrap=True)
    console.print(f"Siguiente paso: {siguiente_comando}", style="dim", soft_wrap=True)


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
    except NotADirectoryError as exc:
        _error_panel(
            f"la ruta no existe o no es accesible: {exc}",
            "verificá la ruta: wyss index <ruta>",
        )
        raise typer.Exit(code=1) from exc
    except ConfigError as exc:
        _error_panel(str(exc), _ACCION_CONFIG)
        raise typer.Exit(code=1) from exc
    except (IndexIntegrityError, AuditIntegrityError) as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
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
    routine_store: RoutineStore | None = None
    memory_store: MemoryStore | None = None
    ledger_store: SqliteLedgerStore | None = None
    try:
        settings = load_settings(config)
        audit = SqliteAuditLogger(settings.audit_db)
        pending_store = PendingStore(_pending_db_path(settings))
        engine = CognitivePolicyEngine(settings.policy)
        routine_store = RoutineStore(_routine_db_path(settings))
        memory_store = MemoryStore(_memory_db_path(settings))
        ledger_store = SqliteLedgerStore(_ledger_db_path(settings))
        scheduler = RoutineScheduler(
            engine=engine,
            pending_store=pending_store,
            audit=audit,
            routine_store=routine_store,
        )
        asyncio.run(
            _run_start_daemon(
                settings,
                engine,
                pending_store,
                audit,
                routine_store,
                memory_store,
                ledger_store,
                scheduler,
            )
        )
    except typer.Exit:
        # typer.Exit hereda de RuntimeError: sin este re-raise lo tragaría el except de abajo.
        raise
    except ConfigError as exc:
        _error_panel(str(exc), _ACCION_CONFIG)
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        # "daemon ya corriendo": no es un fallo — el daemon está arriba. Antes esto
        # explotaba como traceback crudo y el smoke físico lo leyó como error fatal.
        if "ya corriendo" in str(exc):
            _error_panel(
                str(exc),
                "el daemon ya está arriba: usalo directo con wyss ask/confirm, "
                "o bajalo con: pkill -f 'wyss start'",
            )
        else:
            stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    finally:
        if memory_store is not None:
            memory_store.close()
        if ledger_store is not None:
            ledger_store.close()
        if routine_store is not None:
            routine_store.close()
        if pending_store is not None:
            pending_store.close()
        if audit is not None:
            audit.close()


def _build_plan_runner(
    settings: BootstrapWyssSettings,
    engine: CognitivePolicyEngine,
    audit: SqliteAuditLogger,
    memory_store: MemoryStore,
) -> tuple[PlanExecutor, UndoJournal]:
    """Arma la capa de ejecución real (D-69): adapters + journal tras el mismo engine.

    ShellAdapter arranca con allowlist VACÍA (fail-closed): ningún binario corre
    hasta que el owner lo permita explícitamente por config. GitAdapter apunta al
    data_dir — sin repo ahí, toda acción git falla como resultado, no como excepción.
    """
    exec_dir = settings.data_dir / "execution"
    journal = UndoJournal(exec_dir / "journal.db", backup_base_dir=exec_dir / "undo_backups")
    notion_token = os.environ.get("NOTION_TOKEN")
    notion = (
        NotionTool(client=build_notion_client(notion_token), audit=audit) if notion_token else None
    )
    memory_tool = MemoryTool(store=memory_store, audit=audit)
    guard = DeterministicExecutionGuard(engine, audit)
    executor = PlanExecutor(
        filesystem=FileSystemAdapter(guard, audit, journal),
        shell=ShellAdapter(audit, guard),
        git=GitAdapter(audit, settings.data_dir, guard),
        journal=journal,
        audit=audit,
        notion=notion,
        memory=memory_tool,
    )
    return executor, journal


async def _run_start_daemon(
    settings: BootstrapWyssSettings,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    audit: SqliteAuditLogger,
    routine_store: RoutineStore,
    memory_store: MemoryStore,
    ledger_store: SqliteLedgerStore,
    scheduler: RoutineScheduler,
) -> None:
    idempotency = SqliteIdempotencyStore(_client_requests_db_path(settings))
    journal: UndoJournal | None = None
    try:
        runner, journal = _build_plan_runner(settings, engine, audit, memory_store)
        if settings.orchestrator.mode == "deterministic":
            await run_daemon(
                _socket_path(settings),
                engine=engine,
                orchestrator=_DeterministicOrchestrator(),
                pending_store=pending_store,
                audit=audit,
                audit_query=audit,
                idempotency=idempotency,
                routine_store=routine_store,
                memory_store=memory_store,
                ledger=ledger_store,
                scheduler=scheduler,
                runner=runner,
                digest_enabled=settings.digest.enabled,
                digest_hour=settings.digest.hour,
                digest_minute=settings.digest.minute,
                digest_dir=settings.data_dir / "digests",
            )
            return

        async with httpx.AsyncClient() as client:
            gateway = build_gateway(
                settings.gateway,
                client=client,
                audit=audit,
                data_dir=str(settings.data_dir),
            )
            await run_daemon(
                _socket_path(settings),
                engine=engine,
                orchestrator=LLMOrchestrator(
                    gateway,
                    tier=settings.orchestrator.tier,
                    memory=memory_store,
                ),
                pending_store=pending_store,
                audit=audit,
                audit_query=audit,
                idempotency=idempotency,
                routine_store=routine_store,
                memory_store=memory_store,
                ledger=ledger_store,
                scheduler=scheduler,
                runner=runner,
                digest_enabled=settings.digest.enabled,
                digest_hour=settings.digest.hour,
                digest_minute=settings.digest.minute,
                digest_dir=settings.data_dir / "digests",
            )
    finally:
        if journal is not None:
            journal.close()
        idempotency.close()


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
    except (FileNotFoundError, ConnectionRefusedError, PermissionError) as exc:
        _error_panel("el daemon no está corriendo", "levantalo con: wyss start")
        raise typer.Exit(code=1) from exc
    except ConfigError as exc:
        _error_panel(str(exc), _ACCION_CONFIG)
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc


@app.command("digest")
def digest(
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Pide el digest diario on-demand al daemon."""
    try:
        settings = load_settings(config)
        result = asyncio.run(_json_rpc_call(_socket_path(settings), "digest.today", {}))
        markdown = result.get("markdown")
        if not isinstance(markdown, str):
            raise RuntimeError("respuesta de digest inválida")
        generated_at = str(result.get("generated_at", "sin timestamp"))
        console.print(
            Panel(
                Markdown(markdown),
                title=f"Digest generado {generated_at}",
                expand=False,
            )
        )
    except (FileNotFoundError, ConnectionRefusedError, PermissionError) as exc:
        _error_panel("el daemon no está corriendo", "levantalo con: wyss start")
        raise typer.Exit(code=1) from exc
    except ConfigError as exc:
        _error_panel(str(exc), _ACCION_CONFIG)
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
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
            _error_panel(
                f"no hay propuesta pendiente con id '{pending_id}'",
                'el id aparece en la respuesta de: wyss ask "<instrucción>"',
            )
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
    except typer.Exit:
        # typer.Exit hereda de RuntimeError: sin este re-raise lo tragaría el except genérico.
        raise
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        _error_panel("el daemon no está corriendo", "levantalo con: wyss start")
        raise typer.Exit(code=1) from exc
    except ConfigError as exc:
        _error_panel(str(exc), _ACCION_CONFIG)
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error, RuntimeError, KeyError) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    finally:
        if pending_store is not None:
            pending_store.close()


@routine_app.command("add")
def routine_add(
    name: str,
    schedule_kind: str,
    schedule_expr: str,
    plan_json: Annotated[
        str,
        typer.Option("--plan-json", help="Plan serializado en el formato interno de Wyss."),
    ],
    catch_up: Annotated[
        bool,
        typer.Option("--catch-up/--no-catch-up", help="Ejecuta una vez si hubo disparos perdidos."),
    ] = True,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Crea una rutina tras mostrar las próximas ejecuciones."""
    try:
        settings = load_settings(config)
        validate_schedule(schedule_kind, schedule_expr)
        _plan_from_json(plan_json)
        preview = preview_next_fires(schedule_kind, schedule_expr)
        _print_routine_preview(preview)
        if not typer.confirm("Guardar rutina?", default=False):
            console.print("Rutina no guardada.")
            return
        result = asyncio.run(
            _json_rpc_call(
                _socket_path(settings),
                "routine.add",
                {
                    "name": name,
                    "schedule_kind": schedule_kind,
                    "schedule_expr": schedule_expr,
                    "plan_json": plan_json,
                    "catch_up": catch_up,
                },
            )
        )
        console.print(f"Rutina creada: {result.get('routine_id')}", style="green")
    except typer.Exit:
        raise
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        _error_panel("el daemon no está corriendo", "levantalo con: wyss start")
        raise typer.Exit(code=1) from exc
    except (ConfigError, RuntimeError, ValueError, KeyError) as exc:
        _error_panel(str(exc), "revisá el schedule y el plan; luego reintentá")
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc


@routine_app.command("list")
def routine_list(
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Lista rutinas programadas."""
    try:
        settings = load_settings(config)
        result = asyncio.run(_json_rpc_call(_socket_path(settings), "routine.list", {}))
        routines = result.get("routines", [])
        if not isinstance(routines, list):
            raise RuntimeError("respuesta de rutinas inválida")
        _print_routines_table(routines)
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        _error_panel("el daemon no está corriendo", "levantalo con: wyss start")
        raise typer.Exit(code=1) from exc
    except (ConfigError, RuntimeError) as exc:
        _error_panel(str(exc), "levantalo con: wyss start")
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc


@routine_app.command("pause")
def routine_pause(
    routine_id: str,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Pausa una rutina."""
    _routine_mutation("routine.pause", routine_id, "Rutina pausada", config)


@routine_app.command("resume")
def routine_resume(
    routine_id: str,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Reanuda una rutina."""
    _routine_mutation("routine.resume", routine_id, "Rutina reanudada", config)


@routine_app.command("rm")
def routine_rm(
    routine_id: str,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Borra una rutina."""
    _routine_mutation("routine.delete", routine_id, "Rutina borrada", config)


def _routine_mutation(method: str, routine_id: str, success_message: str, config: Path) -> None:
    try:
        settings = load_settings(config)
        result = asyncio.run(
            _json_rpc_call(_socket_path(settings), method, {"routine_id": routine_id})
        )
        if result.get("ok"):
            console.print(f"{success_message}: {routine_id}", style="green")
            return
        _error_panel(
            f"rutina no encontrada: {routine_id}",
            "listá disponibles con: wyss routine list",
        )
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except (FileNotFoundError, ConnectionRefusedError) as exc:
        _error_panel("el daemon no está corriendo", "levantalo con: wyss start")
        raise typer.Exit(code=1) from exc
    except (ConfigError, RuntimeError) as exc:
        _error_panel(str(exc), "levantalo con: wyss start")
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc


@memory_app.command("list")
def memory_list(
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Lista hechos recordados."""
    try:
        settings = load_settings(config)
        result = asyncio.run(_json_rpc_call(_socket_path(settings), "memory.list", {}))
        facts = result.get("facts", [])
        if not isinstance(facts, list):
            raise RuntimeError("respuesta de memoria inválida")
        _print_memory_table(facts)
    except (FileNotFoundError, ConnectionRefusedError, PermissionError) as exc:
        _error_panel("el daemon no está corriendo", "levantalo con: wyss start")
        raise typer.Exit(code=1) from exc
    except (ConfigError, RuntimeError) as exc:
        _error_panel(str(exc), "levantalo con: wyss start")
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc


@memory_app.command("edit")
def memory_edit(
    fact_id: str,
    value: str,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Edita un hecho recordado."""
    _memory_mutation(
        "memory.edit",
        {"fact_id": fact_id, "value": value},
        fact_id,
        "Memoria editada",
        config,
    )


@memory_app.command("rm")
def memory_rm(
    fact_id: str,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Borra un hecho recordado."""
    _memory_mutation(
        "memory.forget",
        {"fact_id": fact_id},
        fact_id,
        "Memoria borrada",
        config,
    )


def _memory_mutation(
    method: str,
    params: dict[str, object],
    fact_id: str,
    success_message: str,
    config: Path,
) -> None:
    try:
        settings = load_settings(config)
        result = asyncio.run(_json_rpc_call(_socket_path(settings), method, params))
        if result.get("ok"):
            console.print(f"{success_message}: {fact_id}", style="green")
            return
        _error_panel(
            f"memoria no encontrada: {fact_id}",
            "listá disponibles con: wyss memory list",
        )
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except (FileNotFoundError, ConnectionRefusedError, PermissionError) as exc:
        _error_panel("el daemon no está corriendo", "levantalo con: wyss start")
        raise typer.Exit(code=1) from exc
    except (ConfigError, RuntimeError) as exc:
        _error_panel(str(exc), "levantalo con: wyss start")
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc


@app.command()
def undo(
    task_id: str,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Muestra qué se desharía sin tocar nada."),
    ] = False,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Deshace las mutaciones aplicadas de una tarea (journal → inversas + confirmación).

    El undo pasa por el MISMO policy engine que todo lo demás: las operaciones
    inversas se evalúan como un plan y piden confirmación a su nivel de riesgo.
    """
    audit_logger: SqliteAuditLogger | None = None
    journal: UndoJournal | None = None
    try:
        settings = load_settings(config)
        exec_dir = settings.data_dir / "execution"
        journal_db = exec_dir / "journal.db"
        if not journal_db.exists():
            _empty_state(
                "no hay journal de ejecución todavía (ninguna mutación registrada)",
                'wyss ask "<instrucción>"',
            )
            return
        journal = UndoJournal(journal_db, backup_base_dir=exec_dir / "undo_backups")
        steps = plan_undo(journal, task_id)
        if not steps:
            _empty_state(
                f"la tarea '{task_id}' no tiene mutaciones aplicadas para deshacer",
                "wyss audit  (el task_id aparece en la columna task)",
            )
            return

        plan = inverse_plan(task_id, steps)
        engine = CognitivePolicyEngine(settings.policy)
        decision = engine.evaluate(plan)
        _print_undo_table(task_id, steps, decision)
        if dry_run:
            return

        blocked = [step for step in steps if not step.ready]
        if blocked:
            _error_panel(
                f"el estado cambió desde la ejecución: {blocked[0].detail}",
                f"revisá con: wyss undo {task_id} --dry-run",
            )
            raise typer.Exit(code=1)

        audit_logger = SqliteAuditLogger(settings.audit_db)
        audit_logger.log(
            AuditEvent.new(
                task_id=plan.task_id,
                actor_type=ActorType.OWNER,
                actor_id="owner",
                event_type=AuditEventType.COMMAND_RECEIVED,
                message=f"wyss undo {task_id}",
                payload={"undo_of": task_id, "steps": len(steps)},
            )
        )
        if decision.outcome == Outcome.REJECT or decision.risk_level >= RiskLevel.D:
            audit_logger.log(
                AuditEvent.new(
                    task_id=plan.task_id,
                    actor_type=ActorType.SYSTEM,
                    actor_id="policy",
                    event_type=AuditEventType.POLICY_DECISION,
                    message="undo rechazado por política",
                    payload={
                        "risk_level": decision.risk_level.name,
                        "matched_rules": list(decision.matched_rules),
                    },
                )
            )
            _error_panel(
                "la política rechaza las operaciones inversas (nivel D): "
                + ", ".join(decision.matched_rules),
                "el undo pasa por el mismo engine que todo lo demás — no es un bypass",
            )
            raise typer.Exit(code=1)

        if decision.outcome != Outcome.EXECUTE:
            accepted = prompt_confirmation(decision, console)
            audit_logger.log(
                AuditEvent.new(
                    task_id=plan.task_id,
                    actor_type=ActorType.OWNER,
                    actor_id="owner",
                    event_type=AuditEventType.CONFIRMATION_ANSWERED,
                    message="confirmación de undo respondida",
                    payload={"accepted": accepted, "risk_level": decision.risk_level.name},
                )
            )
            if not accepted:
                console.print("Undo no confirmado. Nada se tocó.")
                return

        success, details = apply_undo(journal, steps)
        audit_logger.log(
            AuditEvent.new(
                task_id=plan.task_id,
                actor_type=ActorType.SYSTEM,
                actor_id="undo",
                event_type=(
                    AuditEventType.TASK_COMPLETED if success else AuditEventType.TASK_FAILED
                ),
                message=(
                    f"undo de {task_id}: {len(details)} paso(s)"
                    if success
                    else f"undo de {task_id} falló: {details[-1]}"
                ),
                payload={"undo_of": task_id, "details": details},
            )
        )
        if not success:
            _error_panel(
                f"el undo se detuvo en el primer fallo: {details[-1]}",
                f"revisá el estado con: wyss undo {task_id} --dry-run",
            )
            raise typer.Exit(code=1)
        console.print(
            f"[green]✓ Deshecho:[/] {len(steps)} operación(es) revertida(s) de '{task_id}'."
        )
    except typer.Exit:
        raise
    except ConfigError as exc:
        _error_panel(str(exc), _ACCION_CONFIG)
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error, RuntimeError, KeyError) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    finally:
        if journal is not None:
            journal.close()
        if audit_logger is not None:
            audit_logger.close()


def _print_undo_table(task_id: str, steps: Sequence[UndoStep], decision: PolicyDecision) -> None:
    """Dry-run del undo: qué se revertiría, en qué orden y con qué nivel de riesgo."""
    table = Table(title=f"Undo de '{task_id}' — nivel {decision.risk_level.name}")
    table.add_column("#", justify="right")
    table.add_column("inversa")
    table.add_column("target", overflow="fold")
    table.add_column("estado")
    for index, step in enumerate(steps, start=1):
        estado = "[green]listo[/]" if step.ready else f"[red]{step.detail}[/]"
        table.add_row(str(index), step.inverse.type, step.inverse.target, estado)
    console.print(table)


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
        if not settings.audit_db.exists():
            _empty_state(
                "Sin auditoría todavía: audit.db no existe.",
                "wyss index <ruta> o wyss start (generan los primeros eventos)",
            )
            return
        _print_audit_table(query_audit_events(settings.audit_db, since=since, limit=limit))
    except ConfigError as exc:
        _error_panel(str(exc), _ACCION_CONFIG)
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
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
                _error_panel(
                    f"base de conocimiento '{kb}' no encontrada; "
                    f"disponibles: {_format_available_kbs(available_kb_ids)}",
                    f"indexala primero: wyss index <ruta> --bc {kb}",
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
    except ConfigError as exc:
        _error_panel(str(exc), _ACCION_CONFIG)
        raise typer.Exit(code=1) from exc
    except (IndexIntegrityError, AuditIntegrityError) as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
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
    except ConfigError as exc:
        _error_panel(str(exc), _ACCION_CONFIG)
        raise typer.Exit(code=1) from exc
    except (IndexIntegrityError, AuditIntegrityError) as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    finally:
        if state_store is not None:
            state_store.close()


@app.command()
def web(
    port: Annotated[int, typer.Option("--port")] = 7777,
    lan: Annotated[
        bool,
        typer.Option(
            "--lan",
            help="Expone la UI también en la red local (pairing del teléfono por URL con token).",
        ),
    ] = False,
    tls: Annotated[
        bool,
        typer.Option(
            "--tls",
            help="Sirve por HTTPS (cert self-signed auto-generado en data/tls; "
            "cifra el token en la LAN y destraba la voz del browser).",
        ),
    ] = False,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Levanta la UI web local de Wyss (con --lan, accesible desde el teléfono)."""
    try:
        settings = load_settings(config)
    except ConfigError as exc:
        _error_panel(str(exc), _ACCION_CONFIG)
        raise typer.Exit(code=1) from exc

    from bootstrap.web import build_web_app

    lan_ip: str | None = None
    if lan:
        lan_ip = _lan_ip()
        if lan_ip is None:
            _error_panel(
                "no pude detectar la IP LAN de esta máquina",
                "verificá la conexión de red o levantá sin --lan",
            )
            raise typer.Exit(code=1)

    scheme = "https" if tls else "http"
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None
    cert: Path | None = None
    tls_note = ""
    if tls:
        from bootstrap.tls import ensure_certificate, fingerprint_sha256

        hosts = ["localhost", "127.0.0.1"] + ([lan_ip] if lan_ip else [])
        try:
            cert, key = ensure_certificate(settings.data_dir / "tls", hosts)
        except (OSError, subprocess.CalledProcessError) as exc:
            _error_panel(
                f"no pude generar el certificado TLS: {exc}",
                "verificá que openssl esté instalado, o poné tus certs (mkcert) en "
                f"{settings.data_dir / 'tls'}/cert.pem y key.pem",
            )
            raise typer.Exit(code=1) from exc
        ssl_certfile, ssl_keyfile = str(cert), str(key)
        tls_note = (
            "\nTLS: cert self-firmado — el browser avisa UNA vez; verificá la huella:\n"
            f"{fingerprint_sha256(cert)}\n"
            "(cero avisos: generá certs con mkcert y dejalos en data/tls/)"
        )

    token = _load_or_create_web_token(settings.data_dir)
    intake_token = (
        _load_or_create_intake_token(settings.data_dir) if settings.intake.enabled else None
    )
    local_url = f"{scheme}://127.0.0.1:{port}/?token={token}"
    if not lan:
        console.print(
            Panel(
                f"{local_url}\n\nSolo accesible desde esta máquina." + tls_note,
                title="Wyss web",
                expand=False,
            )
        )
        uvicorn.run(
            build_web_app(
                settings,
                token=token,
                intake_token=intake_token,
                tls=tls,
                lan_ip=lan_ip,
                port=port,
                cert=cert,
            ),
            host="127.0.0.1",
            port=port,
            log_level="warning",
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
        )
        return

    assert lan_ip is not None
    phone_url = f"{scheme}://{lan_ip}:{port}/?token={token}"
    console.print(
        Panel(
            f"PC:       {local_url}\n"
            f"Teléfono: {phone_url}\n\n"
            "Pairing: abrí la URL de teléfono UNA vez; quedás logueado 30 días\n"
            "(el token persiste en data/web_token: reiniciar el server no desloguea).\n"
            + (
                "Intake n8n habilitado: bearer en data/intake_token.\n"
                if settings.intake.enabled
                else ""
            )
            + "App: menú de Chrome → 'Agregar a la pantalla de inicio' → ícono Wyss.\n"
            "⚠ Expuesto a la red local. El PC decide y ejecuta; el teléfono solo\n"
            "propone y confirma. Solo se acepta el host exacto de esta máquina.\n"
            f"Firewall (ufw): sudo ufw allow from 192.168.0.0/16 to any port {port} proto tcp"
            + tls_note,
            title="Wyss web — modo LAN",
            expand=False,
        )
    )
    uvicorn.run(
        build_web_app(
            settings,
            token=token,
            intake_token=intake_token,
            lan_hosts=frozenset({lan_ip}),
            tls=tls,
            lan_ip=lan_ip,
            port=port,
            cert=cert,
        ),
        host="0.0.0.0",  # opt-in explícito (--lan); Host allowlist + token gatean
        port=port,
        log_level="warning",
        ssl_certfile=ssl_certfile,
        ssl_keyfile=ssl_keyfile,
    )


def _load_or_create_web_token(data_dir: Path) -> str:
    """Token del bridge estable entre reinicios (data/web_token, 0600).

    Antes se regeneraba en cada `wyss web` y cada reinicio invalidaba la cookie
    del teléfono (re-pairing forzado). Persistirlo en data/ lo deja al mismo
    nivel de protección que la key TLS y las DBs; borrar el archivo rota el token.
    """
    token_file = data_dir / "web_token"
    if token_file.exists():
        stored = token_file.read_text(encoding="utf-8").strip()
        if len(stored) >= 32:
            return stored
    token = secrets.token_urlsafe(32)
    data_dir.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    return token


def _load_or_create_intake_token(data_dir: Path) -> str:
    """Token de intake estable entre reinicios (data/intake_token, 0600).

    Igual que el token web, queda protegido por permisos de owner; borrar el
    archivo rota el bearer. En FS sin chmod POSIX estricto, el chmod puede ser
    best-effort del sistema.
    """
    token_file = data_dir / "intake_token"
    if token_file.exists():
        stored = token_file.read_text(encoding="utf-8").strip()
        if len(stored) >= 32:
            return stored
    token = secrets.token_urlsafe(32)
    data_dir.mkdir(parents=True, exist_ok=True)
    token_file.write_text(token, encoding="utf-8")
    token_file.chmod(0o600)
    return token


def _lan_ip() -> str | None:
    """IP local de salida (sin tráfico real: UDP connect no envía paquetes)."""
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))  # TEST-NET-1: solo resuelve la ruta local
            ip = str(probe.getsockname()[0])
    except OSError:
        return None
    return None if ip.startswith("127.") else ip


def _ledger_db_path(settings: WyssSettings) -> Path:
    """Archivo propio del ledger (NO audit.db/pending.db — AI-SPEC §4 State Management)."""
    return settings.data_dir / "ledger.db"


def _today_iso() -> str:
    return datetime.now(UTC).date().isoformat()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _validate_monto(monto: float) -> None:
    """Rechaza montos no positivos en la frontera CLI (RESEARCH Pitfall 5, T-08-06)."""
    if monto <= 0:
        _error_panel(
            f"el monto debe ser positivo (recibido {monto})",
            "reintentá con un monto mayor a 0",
        )
        raise typer.Exit(code=1)


@fin_app.command("add-ingreso")
def fin_add_ingreso(
    monto: float,
    fuente: str,
    fecha: Annotated[
        str | None,
        typer.Option("--fecha", help="Fecha ISO YYYY-MM-DD (default hoy UTC)."),
    ] = None,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Registra un ingreso en el ledger (escritura determinística, sin IA — D-84)."""
    store: SqliteLedgerStore | None = None
    try:
        _validate_monto(monto)
        settings = load_settings(config)
        store = SqliteLedgerStore(_ledger_db_path(settings))
        transaccion = Transaccion(
            tipo=TipoTransaccion.INGRESO,
            monto=monto,
            fecha=fecha or _today_iso(),
            fuente=fuente,
            categoria=None,
            created_at=_now_iso(),
        )
        store.record(transaccion)
        console.print(
            f"Ingreso registrado: ${monto:.2f} de '{fuente}' ({transaccion.fecha}).",
            style="green",
        )
    except ConfigError as exc:
        _error_panel(str(exc), _ACCION_CONFIG)
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    finally:
        if store is not None:
            store.close()


@fin_app.command("add-gasto")
def fin_add_gasto(
    monto: float,
    categoria: str,
    fecha: Annotated[
        str | None,
        typer.Option("--fecha", help="Fecha ISO YYYY-MM-DD (default hoy UTC)."),
    ] = None,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Registra un gasto en el ledger (escritura determinística, sin IA — D-84)."""
    store: SqliteLedgerStore | None = None
    try:
        _validate_monto(monto)
        settings = load_settings(config)
        store = SqliteLedgerStore(_ledger_db_path(settings))
        transaccion = Transaccion(
            tipo=TipoTransaccion.GASTO,
            monto=monto,
            fecha=fecha or _today_iso(),
            fuente=None,
            categoria=categoria,
            created_at=_now_iso(),
        )
        store.record(transaccion)
        console.print(
            f"Gasto registrado: ${monto:.2f} en '{categoria}' ({transaccion.fecha}).",
            style="green",
        )
    except ConfigError as exc:
        _error_panel(str(exc), _ACCION_CONFIG)
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    finally:
        if store is not None:
            store.close()


@fin_app.command("ver")
def fin_ver(
    desde: Annotated[
        str | None,
        typer.Option("--desde", help="Inicio de ventana ISO (default 0001-01-01)."),
    ] = None,
    hasta: Annotated[
        str | None,
        typer.Option("--hasta", help="Fin de ventana ISO (default 9999-12-31)."),
    ] = None,
    config: Annotated[
        Path,
        typer.Option("--config", help="Ruta al config.toml."),
    ] = Path("config/config.toml"),
) -> None:
    """Muestra gastos por categoría, balance y superávit (solo lectura, agregaciones SQL)."""
    store: SqliteLedgerStore | None = None
    try:
        settings = load_settings(config)
        store = SqliteLedgerStore(_ledger_db_path(settings))
        ventana_desde = desde or "0001-01-01"
        ventana_hasta = hasta or "9999-12-31"
        gastos_por_categoria = store.query_by_category(ventana_desde, ventana_hasta)
        ingresos, gastos = store.balance(ventana_desde, ventana_hasta)
        superavit = ingresos - gastos
        _print_ledger_table(gastos_por_categoria, ingresos, gastos, superavit)
    except ConfigError as exc:
        _error_panel(str(exc), _ACCION_CONFIG)
        raise typer.Exit(code=1) from exc
    except AuditIntegrityError as exc:
        _error_panel(str(exc), _ACCION_INTEGRIDAD)
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    finally:
        if store is not None:
            store.close()


def _print_ledger_table(
    gastos_por_categoria: Mapping[str, float],
    ingresos: float,
    gastos: float,
    superavit: float,
) -> None:
    if not gastos_por_categoria and ingresos == 0 and gastos == 0:
        _empty_state(
            "Ledger vacío: sin transacciones en la ventana pedida.",
            "wyss fin add-ingreso <monto> <fuente> o wyss fin add-gasto <monto> <categoría>",
        )
        return
    table = Table(title="Ledger de finanzas")
    table.add_column("Categoría (gasto)")
    table.add_column("Total", justify="right")
    if gastos_por_categoria:
        for categoria, total in sorted(gastos_por_categoria.items()):
            table.add_row(categoria, f"${total:.2f}")
    else:
        table.add_row("(sin gastos)", "$0.00")
    console.print(table)
    console.print(f"Ingresos: ${ingresos:.2f}")
    console.print(f"Gastos:   ${gastos:.2f}")
    style = "green" if superavit >= 0 else "red"
    console.print(f"Superávit: ${superavit:.2f}", style=style)


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

    console.print(f"progreso: iniciando indexación de {ruta} en BC {kb_id}")
    result = asyncio.run(pipeline.run(ruta, kb_id))
    console.print("progreso: corrida finalizada")
    return result


def _print_estimate(result: EstimateResult) -> None:
    table = Table(title="Estimación de ingesta")
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
        _empty_state(
            "Nada para indexar en esa ruta.",
            "wyss index <otra-ruta> --dry-run",
        )
        return
    for path, reason in items:
        console.print(f"{reason}: {path}")


def _print_summary(result: IngestRunResult, kb_id: str) -> None:
    console.print(
        f"Resumen BC {kb_id}: {result.indexed} indexados, {result.failed} fallados, "
        f"{result.excluded_secret} excluidos por secretos, {result.skipped} omitidos"
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
        if not kb_ids:
            _empty_state(
                "Índice vacío: no hay bases de conocimiento.",
                "wyss index <ruta>",
            )
        else:
            _empty_state(
                "Sin resultados para la búsqueda.",
                "wyss index <ruta> (si el contenido todavía no está indexado)",
            )
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
    if latest is None:
        stderr_console.print(f"índice sin indexaciones · {len(freshness)} BCs")
        return
    stderr_console.print(f"indexado al {_format_timestamp(latest)} · {len(freshness)} BCs")


def _print_status_table(freshness: Sequence[BcFreshness]) -> None:
    if not freshness:
        _empty_state(
            "Índice vacío: no hay bases de conocimiento.",
            "wyss index <ruta>",
        )
        return
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
        return "(ninguna)"
    return ", ".join(kb_ids)


def _print_routine_preview(fires: Sequence[datetime]) -> None:
    table = Table(title="Próximas ejecuciones (hora Argentina)")
    table.add_column("#", justify="right")
    table.add_column("fecha")
    for index, fire in enumerate(fires, start=1):
        table.add_row(str(index), fire.isoformat(timespec="minutes"))
    console.print(table)


def _print_routines_table(routines: Sequence[object]) -> None:
    if not routines:
        _empty_state(
            "Sin rutinas programadas.",
            "wyss routine add <nombre> <cron|interval> <expr> --plan-json '{...}'",
        )
        return
    table = Table(title="Rutinas")
    table.add_column("id", no_wrap=True)
    table.add_column("nombre")
    table.add_column("schedule")
    table.add_column("status")
    table.add_column("last_fired_at")
    table.add_column("last_outcome")
    for item in routines:
        if not isinstance(item, Mapping):
            continue
        table.add_row(
            str(item.get("id", "")),
            str(item.get("name", "")),
            _format_routine_schedule(item.get("schedule")),
            str(item.get("status", "")),
            str(item.get("last_fired_at") or "nunca"),
            str(item.get("last_outcome") or "-"),
        )
    console.print(table)


def _print_memory_table(facts: Sequence[object]) -> None:
    if not facts:
        _empty_state(
            "Sin memoria guardada.",
            'wyss ask "recordá que prefiero café sin azúcar"',
        )
        return
    table = Table(title="Memoria")
    table.add_column("id", no_wrap=True)
    table.add_column("category")
    table.add_column("value", overflow="fold")
    table.add_column("tier")
    table.add_column("updated_at")
    for item in facts:
        if not isinstance(item, Mapping):
            continue
        table.add_row(
            str(item.get("id", "")),
            str(item.get("category", "")),
            str(item.get("value", "")),
            str(item.get("tier", "")),
            str(item.get("updated_at", "")),
        )
    console.print(table)


def _format_routine_schedule(schedule: object) -> str:
    if not isinstance(schedule, Mapping):
        return "-"
    return f"{schedule.get('kind', '-')}: {schedule.get('expr', '-')}"


def _socket_path(settings: WyssSettings) -> Path:
    return settings.data_dir / "wyss.sock"


def _pending_db_path(settings: WyssSettings) -> Path:
    return settings.data_dir / "pending.db"


def _client_requests_db_path(settings: WyssSettings) -> Path:
    return settings.data_dir / "client_requests.db"


def _routine_db_path(settings: WyssSettings) -> Path:
    return settings.data_dir / "routines.db"


def _memory_db_path(settings: WyssSettings) -> Path:
    return settings.data_dir / "memory.db"


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
    if outcome == "executed":
        _render_execution(result)
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
        if "success" in result:
            _render_execution(result)
        else:
            console.print(f"Encolado: {result.get('execution_id')}")
        return
    reason = result.get("reason")
    console.print(f"No confirmado{f': {reason}' if reason else ''}.")


def _render_execution(result: dict[str, Any]) -> None:
    detail = str(result.get("detail", ""))
    execution_id = result.get("execution_id")
    if result.get("success"):
        console.print(f"Ejecutado ({execution_id}): {detail}", style="green")
        outputs = result.get("outputs")
        if isinstance(outputs, list):
            for output in outputs:
                console.print(Panel(str(output), expand=False))
        return
    stderr_console.print(f"Ejecución falló ({execution_id}): {detail}", style="red")


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
    if not rows:
        _empty_state(
            "Sin eventos de auditoría en la ventana pedida.",
            "wyss audit --limit 50 (sin --since) para ver el historial completo",
        )
        return
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
