# Phase 3: Pipeline de Ingesta — Pattern Map

**Mapped:** 2026-06-12
**Files analyzed:** 24 (nuevos/modificados)
**Analogs found:** 22 / 24

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/knowledge/pipeline.py` | service/orchestrator | batch + event-driven | `src/gateway/gateway.py` | role-match (orquestador con DI, pasos ordenados, auditoría) |
| `src/knowledge/scanner.py` | utility | file-I/O | `src/gateway/minimizer.py` | partial (pure class, sin IO externo, lógica de filtrado) |
| `src/knowledge/secret_filter.py` | utility | transform | `src/gateway/minimizer.py` | exact (misma estructura: 3 capas de detección, mismo patrón fail-closed) |
| `src/knowledge/chunker.py` | utility | transform | `tests/ports/fakes.py` FakeChunker | partial (Chunker port ya definido) |
| `src/knowledge/state_store.py` | service | CRUD | `src/gateway/traces.py` + `src/audit/sqlite_logger.py` | exact (SQLite WAL, open/close, commit por operación) |
| `src/knowledge/fts_index.py` | service | CRUD | `src/gateway/traces.py` (SQLite patterns) | role-match (SQLite adapter que implementa un port) |
| `src/knowledge/vector_index.py` | service | CRUD | `src/gateway/traces.py` (adapter implements port) | role-match (adapter que implementa VectorIndex port) |
| `src/knowledge/extractors/registry.py` | utility | transform | `src/gateway/router.py` | exact (resolve por clave, contenedor de adapters, puro) |
| `src/knowledge/extractors/pdf.py` | utility | file-I/O | `src/gateway/providers/ollama.py` | partial (implementa port, manejo de error específico) |
| `src/knowledge/extractors/docx.py` | utility | file-I/O | `src/gateway/providers/ollama.py` | partial |
| `src/knowledge/extractors/text.py` | utility | file-I/O | `src/gateway/providers/ollama.py` | partial |
| `src/knowledge/extractors/spreadsheet.py` | utility | file-I/O | `src/gateway/providers/ollama.py` | partial |
| `src/knowledge/extractors/image.py` | utility | file-I/O | `src/gateway/providers/ollama.py` | partial |
| `src/knowledge/extractors/video.py` | utility | file-I/O | `src/gateway/providers/ollama.py` | partial |
| `src/bootstrap/cli.py` | config/composition-root | request-response | `src/bootstrap/gateway.py` | exact (composition root, DI manual, wiring de adapters) |
| `src/bootstrap/config.py` | config | transform | `src/bootstrap/config.py` (modificación) | self (agregar sección `[ingest]` al modelo existente) |
| `src/core/domain/knowledge.py` | model | — | `src/core/domain/knowledge.py` (modificación) | self (agregar domain objects: IngestFileStatus, IngestSettings) |
| `src/core/domain/errors.py` | model | — | `src/core/domain/errors.py` (modificación) | self (agregar IndexIntegrityError, ExtractionError, etc.) |
| `tests/knowledge/conftest.py` | test | — | `tests/audit/conftest.py` + `tests/gateway/conftest.py` | exact (fixtures tmp_path DB, factories de domain objects) |
| `tests/knowledge/test_state_store.py` | test | CRUD | `tests/audit/test_sqlite_logger.py` | exact (WAL test, roundtrip, commit-por-op) |
| `tests/knowledge/test_secret_filter.py` | test | transform | `tests/gateway/test_gateway.py` (secret detection section) | role-match |
| `tests/knowledge/test_pipeline.py` | test | batch | `tests/gateway/test_gateway.py` | role-match (orquestador con fakes inyectados) |
| `tests/knowledge/test_scanner.py` | test | file-I/O | `tests/gateway/test_scaffolding.py` | partial |
| `tests/cli/test_index_command.py` | test | request-response | `tests/bootstrap/test_gateway_config.py` | partial (CLI-level tests) |

---

## Pattern Assignments

### `src/knowledge/state_store.py` (service, CRUD)

**Analog primario:** `src/gateway/traces.py` (líneas 1-139)
**Analog secundario:** `src/audit/sqlite_logger.py` (líneas 28-57) para el patrón WAL fail-fast

**Imports pattern** (`src/gateway/traces.py` líneas 1-17):
```python
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from gateway.db import open_gateway_db  # → reemplazar con open_index_db propio
```

**Apertura WAL fail-fast** (`src/gateway/db.py` líneas 28-61):
```python
def open_index_db(db_path: Path) -> sqlite3.Connection:
    """Replicar exacto este patrón para index.db — WAL + 0600 + smoke test."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(db_path, os.O_CREAT, 0o600)
    os.close(fd)
    conn = sqlite3.connect(db_path)
    try:
        os.chmod(db_path, 0o600)
    except OSError as exc:
        _log.warning("no se pudo aplicar 0600 a %s: %s", db_path, exc)
    journal_mode: str | None = None
    for pragma in PRAGMAS:
        row = conn.execute(pragma).fetchone()
        if pragma.endswith("WAL") and row is not None:
            journal_mode = str(row[0]).lower()
    if journal_mode != "wal":
        conn.close()
        raise IndexIntegrityError(...)  # nueva excepción de dominio
    apply_index_schema(conn)
    return conn
```

**Commit por operación / patrón de upsert** (`src/gateway/traces.py` líneas 55-94):
```python
def write(self, ...) -> None:
    """INSERT parametrizado — nunca interpolación de strings."""
    self._conn.execute(_INSERT, (...))
    self._conn.commit()  # commit por operación — reanudabilidad (KNOW-03)
```

**Patrón context manager** (`src/gateway/traces.py` líneas 125-139):
```python
def close(self) -> None:
    self._conn.close()

def __enter__(self) -> "TraceStore":
    return self

def __exit__(self, exc_type, exc, tb) -> None:
    self.close()
```

**Schema DDL pattern** (`src/audit/schema.py` y `src/gateway/traces_schema.py`):
```python
# PRAGMAS idénticos a audit/schema.py y traces_schema.py
PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA busy_timeout=5000",
)

# Todo IF NOT EXISTS — idempotente
CREATE_FILE_STATE = """
CREATE TABLE IF NOT EXISTS file_state (
    path       TEXT NOT NULL,
    kb_id      TEXT NOT NULL,
    size       INTEGER NOT NULL,
    mtime      REAL NOT NULL,
    sha256     TEXT,
    status     TEXT NOT NULL DEFAULT 'pending',
    attempts   INTEGER NOT NULL DEFAULT 0,
    error      TEXT,
    indexed_at REAL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (path, kb_id)
)
"""
```

---

### `src/knowledge/secret_filter.py` (utility, transform)

**Analog exacto:** `src/gateway/minimizer.py` (líneas 1-57)

Este es el analog más cercano del proyecto: misma estructura de 3 capas de detección, mismo patrón fail-closed, mismo principio de que el valor nunca viaja a la excepción.

**Imports y clase pura** (`src/gateway/minimizer.py` líneas 18-44):
```python
import re

from core.domain.errors import SecretDetected  # → usar nueva SecretFileExcluded

# Clase pura sin IO — los patrones se inyectan por constructor (D-30)
class ContextMinimizer:
    def __init__(
        self,
        env_values: frozenset[str],
        config_patterns: tuple[tuple[str, re.Pattern[str]], ...],
    ) -> None:
        self._patterns: tuple[tuple[str, re.Pattern[str]], ...] = (
            BUILTIN_SECRET_PATTERNS + config_patterns  # aditivo — NUNCA sustractivo
        )
```

**Patrón de detección fail-closed** (`src/gateway/minimizer.py` líneas 45-57):
```python
def scan(self, prompt: str) -> str:
    """Devuelve limpio o levanta excepción — fail-closed."""
    for name, pattern in self._patterns:
        if pattern.search(prompt):
            raise SecretDetected(name)  # SOLO el nombre, NUNCA el valor (D-20)
    return prompt
```

**Adaptación para SecretFilter:** El `SecretFilter` recibe `BUILTIN_SECRET_PATTERNS` por inyección desde el composition root (`bootstrap/cli.py` importa de `gateway`), NO importa directamente de gateway (ver Pitfall 4 en RESEARCH.md). La firma del constructor:
```python
class SecretFilter:
    def __init__(
        self,
        *,
        builtin_patterns: tuple[tuple[str, re.Pattern[str]], ...],  # inyectado desde bootstrap
        path_denylist: frozenset[str],
        ext_denylist: frozenset[str],
        entropy_allowlist: frozenset[str],  # D-30: globs que desactivan solo capa 3
    ) -> None: ...

    def check_path(self, path: str) -> bool:
        """Capa 1: True si el path/extension está en denylist (archivo no se abre)."""
        ...

    def check_content(self, text: str, path: str) -> str | None:
        """Capas 2+3: retorna nombre de patrón si hay match, None si limpio.
        El texto del secreto NUNCA sale de este método."""
        ...
```

---

### `src/knowledge/pipeline.py` (service/orchestrator, batch)

**Analog:** `src/gateway/gateway.py` (líneas 64-278)

Este es el patrón de orquestador del proyecto: recibe todos los componentes por DI, los compone en pasos ordenados, audita cada transición.

**Constructor con DI** (`src/gateway/gateway.py` líneas 68-87):
```python
class ModelGateway:
    def __init__(
        self,
        *,
        router: ModelRouter,
        minimizer: ContextMinimizer,
        cost: CostTracker,
        traces: TraceStore,
        providers: Mapping[str, ModelProvider],
        audit: AuditPort,
        max_retries: int = 2,
        backoff_base: float = 0.5,
    ) -> None:
        self._router = router
        self._minimizer = minimizer
        # ... etc — todos los componentes stored como self._X
```

**Adaptación para IngestPipeline:**
```python
class IngestPipeline:
    def __init__(
        self,
        *,
        scanner: Scanner,
        secret_filter: SecretFilter,
        registry: ExtractorRegistry,
        chunker: Chunker,
        state_store: StateStore,
        fts_index: FullTextIndex,
        embedder: EmbeddingProvider,
        vector_index: VectorIndex,
        audit: AuditPort,
        settings: IngestSettings,
    ) -> None: ...
```

**Patrón de error por archivo que no aborta la corrida** (`src/gateway/gateway.py` líneas 121-143):
```python
# En gateway: un fallo post-record se audita pero NO se silencia — similar a D-36
try:
    cost = self._cost.record(...)
except Exception as exc:
    self._audit_failed(request, "fallo grave", extra={"error": type(exc).__name__})
    raise CostLedgerError(...) from exc
```

**Patrón de auditoría de fallos** (`src/gateway/gateway.py` líneas 257-278):
```python
def _audit_failed(self, request, reason: str, *, extra=None) -> None:
    """MOTIVO de fallo — nunca el contenido (D-20/V7)."""
    payload: dict[str, object] = {"tier": request.tier, "reason": reason}
    if extra is not None:
        payload.update(extra)
    self._audit.log(AuditEvent.new(
        actor_type=ActorType.SYSTEM,
        actor_id="gateway",
        event_type=AuditEventType.TASK_FAILED,
        ...
    ))
```

---

### `src/knowledge/extractors/registry.py` (utility, transform)

**Analog exacto:** `src/gateway/router.py`

El `ModelRouter` es el registro por clave del proyecto — misma estructura: dict interno, resolve sin fallback (o con fallback controlado), puro sin IO.

**Patrón completo a copiar** (leer `src/gateway/router.py` para el patrón completo):
```python
class ExtractorRegistry:
    """Registro de extractores: register() + resolve() — Plugin Pattern (regla #9)."""

    def __init__(self) -> None:
        self._by_type: dict[str, Extractor] = {}

    def register(self, extractor: Extractor) -> None:
        for media_type in extractor.media_types:
            self._by_type[media_type] = extractor

    def resolve(self, media_type: str) -> Extractor | None:
        if media_type in self._by_type:
            return self._by_type[media_type]
        # Prefix match: "text/" matchea "text/plain", "text/markdown", etc.
        prefix = media_type.split("/")[0] + "/"
        return self._by_type.get(prefix)
```

---

### `src/knowledge/extractors/*.py` (utility, file-I/O — cada extractor)

**Analog:** `src/gateway/providers/ollama.py` (líneas 17-36)

El `OllamaEmbeddingProvider` implementa el `EmbeddingProvider` Protocol — mismo patrón exacto para cada extractor: `@property media_types` + método principal + excepción de dominio ante error.

**Estructura de un extractor** (`src/gateway/providers/ollama.py` líneas 17-36):
```python
class OllamaEmbeddingProvider:
    """Adapter. Implementa EmbeddingProvider."""

    def __init__(self, client: httpx.AsyncClient, ...) -> None:
        self._client = client
        # almacenar config, no hacer IO aquí

    async def embed(self, texts: Sequence[str]) -> Sequence[Vector]:
        resp = await self._client.post(self._url, json={...})
        resp.raise_for_status()
        return [tuple(vec) for vec in resp.json()["embeddings"]]
        # El dict del JSON muere acá — afuera solo tipos de dominio
```

**Adaptación para extractores** (misma estructura, sync):
```python
class PdfExtractor:
    """Implementa Extractor Protocol. Retorna tipos de dominio, nunca dicts."""

    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"application/pdf"})

    def extract(self, source: SourceFile) -> ExtractedContent:
        # El dict de metadata pymupdf muere acá — afuera solo ExtractedContent de dominio
        ...
```

**Error ante formato no soportado** — levantar excepción de dominio (análogo a `SecretDetected`):
```python
# D-40: PDF encriptado → excepción de dominio, el pipeline marca skipped_unsupported
if doc.is_encrypted:
    raise UnsupportedFileError(f"PDF encriptado: {source.path}")
```

---

### `src/knowledge/fts_index.py` (service, CRUD)

**Analog:** `src/gateway/traces.py` (patrón SQLite adapter que implementa un port)

**Imports y estructura:**
```python
import sqlite3
from collections.abc import Sequence

from core.domain.knowledge import Chunk, Hit, IndexEntry

class FTS5Index:
    """Implementa FullTextIndex port. SQLite FTS5 external content."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        # La DB ya fue abierta y verificada por StateStore/open_index_db
```

**Patrón INSERT parametrizado** (`src/gateway/traces.py` líneas 55-94):
```python
# Nunca interpolación de strings en SQL — solo parámetros (?)
self._conn.execute(
    "INSERT INTO chunks (chunk_id, kb_id, source_path, position, text) "
    "VALUES (?, ?, ?, ?, ?) ON CONFLICT(chunk_id) DO UPDATE SET text=excluded.text",
    (entry.chunk.chunk_id, entry.kb_id, entry.chunk.source_path,
     entry.chunk.position, entry.chunk.text),
)
self._conn.commit()
```

---

### `src/knowledge/vector_index.py` (service, CRUD)

**Analog:** `src/gateway/providers/ollama.py` (adapter que implementa un port, inyecta la dependencia externa)

Sin analog exacto en SQLite — VectorIndex usa ChromaDB. La estructura del adapter sigue el mismo patrón: implementa el Protocol, la dependencia externa (ChromaDB client) se inyecta por constructor.

```python
import chromadb

from core.domain.knowledge import Hit, IndexEntry, Vector
from core.ports.knowledge import VectorIndex

class ChromaVectorIndex:
    """Implementa VectorIndex port. ChromaDB PersistentClient, colección por kb_id."""

    def __init__(self, client: chromadb.PersistentClient) -> None:
        self._client = client
        # client ya construido en bootstrap — no se abre ChromaDB acá
```

---

### `src/bootstrap/cli.py` (config/composition-root, request-response)

**Analog exacto:** `src/bootstrap/gateway.py` (líneas 1-93)

Este es el patrón de composition root del proyecto: importa de todos los adapters concretos, cablea todo por DI manual, es el ÚNICO módulo que puede importar de múltiples capas.

**Imports cross-layer** (`src/bootstrap/gateway.py` líneas 1-31):
```python
# Bootstrap es el único módulo que importa de múltiples capas
import os
import re
from pathlib import Path

import httpx

from core.domain.config import GatewaySettings
from core.ports.audit import AuditPort
from gateway.cost import CostTracker
from gateway.gateway import ModelGateway
from gateway.minimizer import ContextMinimizer
from gateway.providers.anthropic import AnthropicProvider
from gateway.router import ModelRouter
from gateway.traces import TraceStore
```

**Patrón de función build_X** (`src/bootstrap/gateway.py` líneas 34-93):
```python
def build_gateway(
    settings: GatewaySettings,
    *,
    client: httpx.AsyncClient,
    audit: AuditPort,
    data_dir: str,
) -> ModelGateway:
    """Arma el componente completo desde settings + deps inyectadas."""
    # 1. Construir adapters concretos
    router = ModelRouter(dict(settings.tiers))
    minimizer = ContextMinimizer(...)
    traces = TraceStore(db_path)
    # 2. Retornar el componente principal con DI manual
    return ModelGateway(router=router, minimizer=minimizer, ...)
```

**Adaptación para CLI:** El composition root de CLI también es donde `BUILTIN_SECRET_PATTERNS` se importa de `gateway` y se inyecta al `SecretFilter` (solución al Pitfall 4 del RESEARCH.md):
```python
# bootstrap/cli.py puede importar de gateway (sin restricción de independence)
from gateway.secrets_patterns import BUILTIN_SECRET_PATTERNS
from knowledge.secret_filter import SecretFilter

# Inyección: los patrones viajan como parámetro, no como import en knowledge/
secret_filter = SecretFilter(
    builtin_patterns=BUILTIN_SECRET_PATTERNS,
    ...
)
```

---

### `src/bootstrap/config.py` (modificación — agregar sección `[ingest]`)

**Analog:** El archivo mismo (`src/bootstrap/config.py` líneas 125-195 — patrón de sección de config Pydantic)

**Patrón de sección nueva** (copiar de `GatewayConfigModel` líneas 168-183):
```python
class IngestConfigModel(BaseModel):
    """Sección [ingest]: configuración del pipeline de ingesta."""

    model_config = ConfigDict(extra="forbid")  # typo = boot abortado

    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 51          # 10% de 512
    max_file_bytes: int = 104_857_600       # 100 MB
    dir_denylist: list[str] = [".git", "node_modules", ".cache", "__pycache__",
                                ".venv", "venv", "dist", "build", ".tox"]
    entropy_allowlist: list[str] = []       # D-30: globs que desactivan capa 3
    default_kb_id: str = "default"          # Open Question 2
```

**Agregado a WyssConfigModel** (`src/bootstrap/config.py` líneas 186-194):
```python
class WyssConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    data_dir: Path
    audit_db: Path
    policy: PolicyConfigModel = PolicyConfigModel()
    gateway: GatewayConfigModel = GatewayConfigModel()
    ingest: IngestConfigModel = IngestConfigModel()  # ← nueva sección
```

---

### `src/core/domain/errors.py` (modificación — agregar errores de ingesta)

**Analog:** El archivo mismo (`src/core/domain/errors.py` líneas 1-76)

**Patrón de excepción de dominio** (copiar de `SecretDetected` líneas 33-42):
```python
class IndexIntegrityError(WyssError):
    """La DB de índice no pudo garantizar durabilidad (WAL falla — análogo a AuditIntegrityError)."""

class ExtractionError(WyssError):
    """Un extractor no pudo procesar el archivo. El pipeline lo marca 'failed' y continúa (D-36)."""

class UnsupportedFileError(WyssError):
    """Formato no soportado o PDF encriptado. El pipeline lo marca 'skipped_unsupported' (D-40)."""
```

---

### `tests/knowledge/conftest.py` (test fixtures)

**Analog exacto:** `tests/audit/conftest.py` (líneas 1-44) + `tests/gateway/conftest.py` (líneas 1-73)

**Patrón de fixture tmp_path DB** (`tests/audit/conftest.py` líneas 12-19):
```python
@pytest.fixture
def logger(tmp_path: Path) -> Iterator[SqliteAuditLogger]:
    """Logger sobre tmp_path (ext4/tmpfs — WAL funciona)."""
    log = SqliteAuditLogger(tmp_path / "audit.db")
    try:
        yield log
    finally:
        log.close()
```

**Patrón de factory fixture** (`tests/audit/conftest.py` líneas 22-44 + `tests/gateway/conftest.py` líneas 53-73):
```python
@pytest.fixture
def make_source_file() -> Callable[..., SourceFile]:
    def _make(
        *,
        path: str = "/tmp/test.txt",
        media_type: str = "text/plain",
        size: int = 100,
        mtime: float = 1.0,
    ) -> SourceFile:
        return SourceFile(path=path, media_type=media_type, size=size, mtime=mtime)
    return _make
```

**Patrón de FakeAuditPort** (`tests/ports/fakes.py` líneas 42-62): reusar directamente `FakeAuditPort` y los fakes de knowledge existentes (`FakeExtractor`, `FakeChunker`, `FakeEmbeddingProvider`, `FakeFullTextIndex`, `FakeVectorIndex`) — todos ya están en `tests/ports/fakes.py`.

---

### `tests/knowledge/test_state_store.py` (test, CRUD)

**Analog exacto:** `tests/audit/test_sqlite_logger.py` (líneas 1-238)

**Patrón de test WAL** (líneas 21-28):
```python
def test_wal_active(logger, tmp_path: Path) -> None:
    """El state store deja journal_mode=WAL sobre tmp_path."""
    conn = sqlite3.connect(tmp_path / "index.db")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        conn.close()
```

**Patrón de test WAL fail-fast** (líneas 205-215):
```python
def test_fail_fast_when_journal_not_wal(tmp_path, monkeypatch) -> None:
    """journal_mode ≠ wal → IndexIntegrityError con el path en el mensaje."""
    monkeypatch.setattr(mod, "PRAGMAS", ("PRAGMA journal_mode=DELETE",))
    with pytest.raises(IndexIntegrityError) as excinfo:
        StateStore(tmp_path / "index.db")
    assert str(tmp_path / "index.db") in str(excinfo.value)
```

**Patrón de test de concurrencia** (líneas 168-202): aplicar el mismo patrón para verificar que commit-por-archivo no causa "database is locked".

---

### `tests/knowledge/test_secret_filter.py` (test, transform)

**Analog:** `tests/gateway/test_gateway.py` (patrón de test de secretos)

**Patrón de test directed (prueba obligatoria KNOW-07):**
```python
def test_planted_secret_not_indexed(tmp_path: Path) -> None:
    """Prueba dirigida obligatoria (criterio 4): secreto plantado no aparece en índice."""
    # 1. Crear BC trampa con archivo que contiene un secreto conocido
    secret_file = tmp_path / "credentials.txt"
    secret_file.write_text("token=sk-ant-api03-FAKE_KEY_FOR_TEST_abc123def456")

    # 2. Correr pipeline completo sobre tmp_path
    # ...

    # 3. Verificar que el secreto NO está en FTS5 ni en ChromaDB
    # Consultar la DB directamente (como test_roundtrip_persists_all_d07_fields)
    conn = sqlite3.connect(index_db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM chunks WHERE text LIKE '%sk-ant%'"
    ).fetchone()[0]
    assert count == 0

    # 4. Verificar que el archivo está marcado excluded_secret en file_state
    status = conn.execute(
        "SELECT status FROM file_state WHERE path=?", (str(secret_file),)
    ).fetchone()[0]
    assert status == "excluded_secret"
```

---

### `tests/knowledge/test_pipeline.py` (test, batch)

**Analog:** `tests/gateway/test_gateway.py` (líneas 51-79 — build helper con fakes)

**Patrón de build helper con fakes** (`tests/gateway/test_gateway.py` líneas 51-79):
```python
def _build_gateway(
    *,
    db_path: Path,
    audit: FakeAuditPort,
    provider: FakeModelProvider,
    ...
) -> ModelGateway:
    """Arma el componente con todo real (DB en tmp) excepto el provider."""
    router = ModelRouter(_tiers())
    minimizer = ContextMinimizer(...)
    cost = CostTracker(db_path, ...)
    traces = TraceStore(db_path)
    return ModelGateway(router=router, ..., providers={"litellm": provider}, audit=audit)
```

**Adaptación — test de extensibilidad (criterio 6):**
```python
def test_new_extractor_no_pipeline_change(tmp_path: Path, audit: FakeAuditPort) -> None:
    """Registrar un extractor nuevo no modifica una línea del pipeline (regla #9)."""
    registry = ExtractorRegistry()
    registry.register(FakeExtractor())  # extractor ya existente

    # Registrar extractor nuevo (tipo ficticio) SIN tocar IngestPipeline
    class FakeNewExtractor:
        @property
        def media_types(self) -> frozenset[str]:
            return frozenset({"application/x-new-format"})
        def extract(self, source: SourceFile) -> ExtractedContent:
            return ExtractedContent(source=source, text="nuevo", metadata={})

    registry.register(FakeNewExtractor())
    assert registry.resolve("application/x-new-format") is not None
    # El pipeline ya existente resuelve el nuevo tipo sin modificación
```

---

### `tests/cli/test_index_command.py` (test, request-response)

**Analog:** `tests/bootstrap/test_gateway_config.py` + `tests/gateway/test_embeddings.py` (opt-in pattern)

**Patrón de test opt-in para Ollama** (`tests/gateway/test_embeddings.py` líneas 58-71):
```python
@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("WYSS_TEST_OLLAMA") != "1",
    reason="requiere WYSS_TEST_OLLAMA=1 (Ollama local + `ollama pull nomic-embed-text`)",
)
async def test_ollama_embed_real() -> None:
    ...
```

**Patrón para tests de CLI con Typer** (sin analog en el proyecto — ver sección "No Analog Found"):
```python
from typer.testing import CliRunner
from bootstrap.cli import app

runner = CliRunner()

def test_estimate_no_extraction(tmp_path: Path) -> None:
    """KNOW-08: --estimate proyecta sin llamar extractores."""
    result = runner.invoke(app, ["index", str(tmp_path), "--estimate"])
    assert result.exit_code == 0
    assert "archivos" in result.output
    assert "chunks" in result.output
    # Verificar que no se creó index.db (no se tocó nada)
    assert not (tmp_path / "data" / "index.db").exists()
```

---

## Shared Patterns

### WAL fail-fast al abrir cualquier DB SQLite
**Fuente:** `src/gateway/db.py` líneas 28-61 (función completa)
**Aplicar a:** `src/knowledge/state_store.py` (para `index.db`), eventualmente `src/knowledge/fts_index.py` si usa DB separada
```python
# El smoke test WAL es OBLIGATORIO para cualquier DB SQLite nueva del proyecto
row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
if row[0].lower() != "wal":
    conn.close()
    raise IndexIntegrityError(
        f"index.db en {db_path}: PRAGMA journal_mode retornó "
        f"{row[0]!r}, se esperaba 'wal'. WAL no disponible en este filesystem."
    )
```

### Auditoría de exclusiones de secretos
**Fuente:** `src/gateway/gateway.py` líneas 257-278 (`_audit_failed`) + `src/audit/sqlite_logger.py` líneas 60-79
**Aplicar a:** `src/knowledge/pipeline.py` (para cada exclusión por secreto — D-28, regla #1)
```python
# Solo el pattern_name viaja al AuditEvent — NUNCA el valor del secreto (D-20)
self._audit.log(AuditEvent.new(
    actor_type=ActorType.SYSTEM,
    actor_id="ingest_pipeline",
    event_type=AuditEventType.ACTION_BLOCKED,  # o nuevo INGEST_SECRET_EXCLUDED
    message=f"archivo excluido por secreto detectado: {pattern_name}",
    task_id=run_id,
    payload={
        "path": str(path),           # path OK — no es el secreto
        "pattern": pattern_name,     # nombre del patrón — no es el secreto
        "layer": layer_name,         # "path_denylist" | "builtin_pattern" | "entropy"
    },
))
```

### Commit por operación atómica (reanudabilidad KNOW-03)
**Fuente:** `src/gateway/traces.py` línea 94 + `src/audit/sqlite_logger.py` línea 79
**Aplicar a:** `src/knowledge/state_store.py` — cada transición de estado hace `self._conn.commit()` inmediatamente
```python
# Commit por archivo — si el proceso muere, el progreso hasta acá se conserva
self._conn.execute(
    "UPDATE file_state SET status=?, updated_at=unixepoch() WHERE path=? AND kb_id=?",
    (new_status, path, kb_id),
)
self._conn.commit()  # NO hacer batch commit — cada archivo debe ser recuperable
```

### Excepciones de dominio con nombre del error (no el contenido)
**Fuente:** `src/core/domain/errors.py` líneas 33-42 (`SecretDetected`)
**Aplicar a:** Todas las excepciones nuevas de ingesta
```python
# Patrón: el constructor solo toma metadata, nunca el contenido del archivo
class ExtractionError(WyssError):
    def __init__(self, path: str, error_type: str) -> None:
        super().__init__(f"extracción fallida: {path} ({error_type})")
        self.path = path
        self.error_type = error_type  # nombre del tipo de error, no el traceback completo
```

### Clases puras sin IO (inyección de dependencias)
**Fuente:** `src/gateway/minimizer.py` (clase pura) + `src/gateway/router.py`
**Aplicar a:** `SecretFilter`, `ExtractorRegistry`, `Chunker`
```python
# Toda la lógica de negocio vive en clases que no hacen IO
# El IO (abrir archivos, llamar servicios) lo hacen los adapters
# La composición la hace bootstrap/cli.py
```

### Imports de domain objects desde `core.domain` (nunca re-exportar desde adapters)
**Fuente:** Todos los archivos existentes en `src/gateway/` y `src/audit/`
**Aplicar a:** Todo `src/knowledge/`
```python
from core.domain.knowledge import Chunk, ExtractedContent, Hit, IndexEntry, SourceFile, Vector
from core.domain.errors import ExtractionError, IndexIntegrityError, UnsupportedFileError
from core.ports.knowledge import Chunker, EmbeddingProvider, Extractor, FullTextIndex, VectorIndex
# NUNCA: from gateway.xxx import ... (viola independence contract de import-linter)
# NUNCA: import pydantic en knowledge/ (solo en bootstrap/)
```

### Fakes en tests/ports/fakes.py (ya existentes)
**Fuente:** `tests/ports/fakes.py` líneas 77-112
**Aplicar a:** `tests/knowledge/conftest.py` — importar y reusar los fakes existentes
```python
# Ya existen: FakeExtractor, FakeChunker, FakeEmbeddingProvider,
# FakeFullTextIndex, FakeVectorIndex, FakeAuditPort
from tests.ports.fakes import (
    FakeAuditPort,
    FakeChunker,
    FakeEmbeddingProvider,
    FakeExtractor,
    FakeFullTextIndex,
    FakeVectorIndex,
)
```

---

## No Analog Found

Archivos sin analog cercano en el codebase (el planner debe usar los patrones de RESEARCH.md + ejemplos de código propios):

| File | Role | Data Flow | Razón |
|------|------|-----------|-------|
| `src/knowledge/chunker.py` | utility | transform | No existe chunking en el proyecto. El Protocol `Chunker` está en `core/ports/knowledge.py`. Implementar con ventana de tokens y overlap configurable per RESEARCH.md Pattern chunking. |
| `tests/cli/test_index_command.py` (Typer runner) | test | request-response | No existe CLI en el proyecto todavía. Usar `typer.testing.CliRunner` (patrón estándar de Typer) — sin analog real en el repo. |

---

## Metadata

**Scope de búsqueda de analogs:**
- `src/gateway/` — DB patterns, minimizer, provider adapters, composition root
- `src/audit/` — SQLiteAuditLogger, schema DDL, WAL pattern
- `src/bootstrap/` — config Pydantic→domain, build_gateway composition root
- `src/core/domain/` — domain objects, errors hierarchy
- `src/core/ports/knowledge.py` — contracts ya definidos
- `tests/audit/` + `tests/gateway/` + `tests/ports/` — fixtures, fake patterns, test structure

**Archivos leídos:** 20
**Fecha de extracción:** 2026-06-12
