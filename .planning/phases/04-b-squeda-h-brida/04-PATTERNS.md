# Phase 4: Búsqueda Híbrida - Pattern Map

**Mapped:** 2026-06-12
**Files analyzed:** 9 new/modified files
**Analogs found:** 9 / 9

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/knowledge/retrieval.py` | service | request-response (async) | `src/knowledge/pipeline.py` | role-match |
| `src/knowledge/rrf.py` | utility | transform | `src/knowledge/chunker.py` | partial (pure transform, stdlib-only) |
| `src/knowledge/state_store.py` | service | CRUD | `src/knowledge/state_store.py` (extend) | exact (add method) |
| `src/core/domain/knowledge.py` | model | — | `src/core/domain/knowledge.py` (extend) | exact (add field) |
| `src/bootstrap/cli.py` | controller | request-response | `src/bootstrap/cli.py` (extend) | exact (add commands) |
| `tests/knowledge/test_retrieval.py` | test | request-response | `tests/knowledge/test_fts_index.py` | role-match |
| `tests/knowledge/test_rrf.py` | test | transform | `tests/knowledge/test_fts_index.py` | role-match |
| `tests/knowledge/golden/corpus.py` | test fixture | batch | `tests/policy/test_golden_plans.py` | exact (golden fixture pattern) |
| `tests/cli/test_search_command.py` | test | request-response | `tests/cli/test_index_command.py` | exact |

---

## Pattern Assignments

### `src/knowledge/retrieval.py` (service, async request-response)

**Analog:** `src/knowledge/pipeline.py`

**Imports pattern** (`src/knowledge/pipeline.py` lines 1-31):
```python
import httpx
from collections.abc import Sequence
from core.domain.audit import ActorType, AuditEvent, AuditEventType
from core.domain.knowledge import Hit, Query
from core.domain.security import Subject
from core.ports.audit import AuditPort
from core.ports.knowledge import EmbeddingProvider, FullTextIndex, VectorIndex
from knowledge.rrf import rrf_merge
```

**DI constructor pattern** (`src/knowledge/pipeline.py` lines 81-104):
```python
class HybridRetrieval:
    def __init__(
        self,
        *,
        fts_index: FullTextIndex,
        vector_index: VectorIndex,
        embedder: EmbeddingProvider | None,  # None = degraded mode (D-44)
        audit: AuditPort,
        rrf_k: int = 60,
    ) -> None:
        self._fts = fts_index
        self._vec = vector_index
        self._embedder = embedder
        self._audit = audit
        self._rrf_k = rrf_k
```
Copy: every dependency is injected by keyword, stored as private attribute.

**Ollama failure / degradation pattern** (`src/knowledge/pipeline.py` lines 173-179 + `src/bootstrap/cli.py` lines 291-298):
```python
# From pipeline.py — httpx.TransportError is the signal for Ollama down
except httpx.TransportError as exc:
    warning = f"embedding omitido para {source.path}: {type(exc).__name__}"
    warnings.append(warning)
    self._audit_embedding_failed(source.path, run_id, type(exc).__name__)

# From cli.py _build_embedder — both HTTPError and TransportError caught
except (httpx.HTTPError, httpx.TransportError):
    return client, None
```
In `HybridRetrieval.search()` catch `(httpx.HTTPError, httpx.TransportError)` — set `degraded=True`, `vec_hits = ()`, continue with FTS5-only path.

**AuditEvent emission pattern** (`src/knowledge/pipeline.py` lines 262-276):
```python
self._audit.log(
    AuditEvent.new(
        actor_type=ActorType.SYSTEM,
        actor_id="knowledge.pipeline",
        event_type=AuditEventType.ACTION_COMPLETED,
        message="...",
        task_id=run_id,
        payload={
            "path": path,
            "pattern": pattern_name,
            "layer": layer,
        },
    )
)
```
For `HybridRetrieval`: use `ActorType.OWNER`, `actor_id=subject.subject_id`, emit one `ACTION_COMPLETED` event per `search()` call with payload `{"degraded": bool, "reason": str, "kb_ids": list, "result_count": int}`.

**Async + sync sqlite3 pattern** (Research §Pattern 3 + `src/bootstrap/cli.py` lines 312-313):
```python
# asyncio.run() in cli.py is the entry point — same thread as sqlite3 connection
result = asyncio.run(pipeline.run(ruta, kb_id))

# Inside the async method, FTS5 call is direct sync — safe in same thread:
fts_hits = self._fts.search(query.text, query.kb_ids, over_fetch)  # NO run_in_executor
```

---

### `src/knowledge/rrf.py` (utility, transform)

**Analog:** No direct analog — pure stdlib function with no imports from infra.

**Domain type usage pattern** (`src/core/domain/knowledge.py` lines 88-95):
```python
@dataclass(frozen=True, slots=True)
class Hit:
    entry_id: str
    score: float
    snippet: str
    source_path: str
```
`rrf_merge` receives `Sequence[Hit]` and returns `list[Hit]`. Replace `Hit.score` with the RRF score (`1/(k+rank)`) in the output — the docstring must document this semantic change.

**Stdlib-only import pattern** — no infra imports. Check with `uv run lint-imports` after writing.

**Function signature** (from RESEARCH.md §Pattern 1):
```python
from collections.abc import Sequence
from core.domain.knowledge import Hit

def rrf_merge(
    *hit_lists: Sequence[Hit],
    k: int = 60,
    limit: int = 10,
) -> list[Hit]:
    """Reciprocal Rank Fusion over N ranked lists of Hits.

    FTS5 hits must be passed already sorted best-first (ascending BM25 score —
    SQLite ORDER BY rank already does this in FTS5Index.search()).
    Vector hits must be passed already sorted best-first (descending similarity —
    ChromaVectorIndex.search() already does this).

    Hit.score in the output is the RRF score (sum of 1/(k+rank)), NOT the
    original BM25 or cosine score. Downstream code must not threshold by score.
    """
```

---

### `src/knowledge/state_store.py` (extend — add `freshness_by_kb` and `list_kb_ids`)

**Analog:** `src/knowledge/state_store.py` itself (additive extension)

**Existing SQL pattern** (`src/knowledge/state_store.py` lines 170-190):
```python
def list_resumable(self, kb_id: str) -> list[FileRecord]:
    rows = self._conn.execute(
        f"""
        SELECT {", ".join(_COLUMNS)}
        FROM file_state
        WHERE kb_id=?
          AND (
            status IN (?, ?)
            OR (status=? AND attempts < ?)
          )
        ORDER BY path
        """,
        (kb_id, ...),
    ).fetchall()
    return [self._row_to_record(row) for row in rows]
```
Copy: parameterized SQL, `.fetchall()`, return typed list. New methods follow same pattern.

**New `BcFreshness` dataclass** — use same frozen+slots style as domain types:
```python
@dataclass(frozen=True, slots=True)
class BcFreshness:
    kb_id: str
    last_indexed_at: float | None   # NULL when no file has been embedded
    total: int
    embedded: int
    pending: int   # status IN ('pending','extracted')
    failed: int
```
Place in `src/knowledge/state_store.py` (same file) or in a new `src/knowledge/freshness.py`. Both are equivalent — keep in `state_store.py` to avoid a one-class file.

**New `list_kb_ids` method** — needed for D-46 wildcard expansion in CLI:
```python
def list_kb_ids(self) -> list[str]:
    rows = self._conn.execute(
        "SELECT DISTINCT kb_id FROM file_state ORDER BY kb_id"
    ).fetchall()
    return [str(row[0]) for row in rows]
```

**SQL for `freshness_by_kb`** (from RESEARCH.md §Pattern 4, verified against `index_schema.py`):
```sql
-- file_state columns: path, kb_id, size, mtime, sha256, status, attempts, error, indexed_at, updated_at
SELECT
  kb_id,
  MAX(indexed_at),
  COUNT(*),
  SUM(CASE WHEN status='embedded' THEN 1 ELSE 0 END),
  SUM(CASE WHEN status IN ('pending','extracted') THEN 1 ELSE 0 END),
  SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END)
FROM file_state
GROUP BY kb_id
ORDER BY kb_id
```
`indexed_at` is `REAL` (unix epoch), set by `mark_embedded()`. Returns `NULL` when no file is embedded — handle as `float | None`.

---

### `src/core/domain/knowledge.py` (extend — add `date` field to `Hit`)

**Analog:** `src/core/domain/knowledge.py` itself — additive field.

**Existing `Hit` definition** (lines 88-95):
```python
@dataclass(frozen=True, slots=True)
class Hit:
    """Un resultado de búsqueda: ubicación exacta + extracto + score."""
    entry_id: str
    score: float
    snippet: str
    source_path: str
```

**Extension pattern** — add `date: float | None = None` as the last field (default prevents breaking callers that construct `Hit` positionally in tests):
```python
@dataclass(frozen=True, slots=True)
class Hit:
    entry_id: str
    score: float
    snippet: str
    source_path: str
    date: float | None = None   # mtime of the source file (KNOW-05)
```
Comment at top of file says "Expandir en Fases 3-4 es aditivo, no breaking" — this is the intended extension point.

---

### `src/bootstrap/cli.py` (extend — add `search` and `status` commands + `build_retrieval`)

**Analog:** `src/bootstrap/cli.py` itself — exact same pattern as `index` command.

**build_pipeline DI pattern** (lines 149-183 — copy structure exactly):
```python
def build_retrieval(
    settings: WyssSettings,
    *,
    audit: AuditPort,
    embedder: EmbeddingProvider | None,
) -> HybridRetrieval:
    """Arma el retrieval real con DI manual desde WyssSettings."""
    state_store = StateStore(settings.data_dir / "index.db")
    fts_index = FTS5Index(state_store._conn)
    chroma_client = chromadb.PersistentClient(path=str(settings.data_dir / "chroma"))
    vector_index = ChromaVectorIndex(chroma_client)
    return HybridRetrieval(
        fts_index=fts_index,
        vector_index=vector_index,
        embedder=embedder,
        audit=audit,
    )
```
Note: uses `state_store._conn` exactly as `build_pipeline` does (line 160). Single `StateStore` instance shared between retrieval and freshness queries (anti-pattern: two instances = two connections).

**isatty + JSON output pattern** (lines 301-319):
```python
def _run_with_progress(pipeline, ruta, kb_id):
    if sys.stdout.isatty():
        # Rich output path
        ...
    # Non-tty / pipe path: plain output
    console.print("progreso: iniciando ...")
    result = asyncio.run(pipeline.run(ruta, kb_id))
    console.print("progreso: corrida finalizada")
    return result
```
For `search` command: `if not sys.stdout.isatty(): output JSON` / else: render Rich Panels. `--json` flag forces JSON mode regardless of isatty (D-43).

**Error handling pattern** (lines 242-254):
```python
try:
    settings = load_settings(config)
    ...
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
```
Copy: the `finally` block must close `StateStore` (via `state_store.close()`) and audit. Degraded mode is NOT a caught exception — it's a normal return path with `exit code 0` (D-44).

**Typer command signature pattern** (lines 186-207):
```python
@app.command()
def search(
    query: str,
    kb: Annotated[str | None, typer.Option("--kb", help="Acotar a BC.")] = None,
    limit: Annotated[int, typer.Option("--limit", help="Resultados máximos.")] = 10,
    json_output: Annotated[bool, typer.Option("--json", help="Salida JSON.")] = False,
    fts_only: Annotated[bool, typer.Option("--fts-only", help="Forzar modo FTS5-only.")] = False,
    config: Annotated[Path, typer.Option("--config")] = Path("config/config.toml"),
) -> None:
    """Busca en la base de conocimiento (híbrido FTS5 + vectores)."""
```
Copy the `Annotated` style and `--config` param from existing `index` command.

**Rich Table pattern** (lines 322-332):
```python
table = Table(title="Estimacion de ingesta")
table.add_column("Metrica")
table.add_column("Valor")
table.add_row("archivos", str(result.files))
console.print(table)
```
For `wyss status`: use `Table` with columns `BC`, `Última indexación`, `Total`, `Embebidos`, `Pendientes`, `Fallados`. For `wyss search`: use `Panel` per hit (Rich `Panel` is already imported in the existing dependency set; add to import line).

---

### `tests/knowledge/test_retrieval.py` (test, async request-response)

**Analog:** `tests/knowledge/test_fts_index.py`

**In-memory fixture pattern** (`tests/knowledge/test_fts_index.py` lines 1-25):
```python
import sqlite3
from core.domain.knowledge import Chunk, Hit, IndexEntry
from knowledge.fts_index import FTS5Index
from knowledge.index_schema import apply_index_schema

def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    apply_index_schema(conn)
    return conn

def _entry(entry_id: str, kb_id: str, text: str, source_path: str = "/docs/a.md") -> IndexEntry:
    return IndexEntry(
        entry_id=entry_id,
        kb_id=kb_id,
        chunk=Chunk(chunk_id=entry_id, text=text, source_path=source_path, position=0),
    )
```
Copy: use `:memory:` sqlite3, `apply_index_schema`, and a `_entry()` factory.

**FakeAuditPort pattern** (`tests/ports/fakes.py` lines 42-63):
```python
class FakeAuditPort:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def log(self, event: AuditEvent) -> None:
        self.events.append(event)
```
Use `FakeAuditPort` for audit assertion: `assert any(e.event_type == AuditEventType.ACTION_COMPLETED for e in audit.events)`.

**FakeEmbeddingProvider** (`tests/ports/fakes.py` lines 93-95):
```python
class FakeEmbeddingProvider:
    async def embed(self, texts: Sequence[str]) -> Sequence[Vector]:
        return [tuple(float(len(t)) for _ in range(3)) for t in texts]
```
Use as-is for non-degraded path. For degraded path tests: pass `embedder=None` to `HybridRetrieval`.

**Async test pattern** — `pyproject.toml` has `asyncio_mode = "auto"`, so `async def test_...()` works without decorator:
```python
async def test_hybrid_returns_merged() -> None:
    ...
    results = await retrieval.search(query, subject)
    assert len(results) > 0
```

---

### `tests/knowledge/test_rrf.py` (test, pure unit)

**Analog:** `tests/knowledge/test_fts_index.py` (same structure but no fixtures needed)

Pure unit tests — no DB, no fakes. Build `Hit` objects directly:
```python
from core.domain.knowledge import Hit
from knowledge.rrf import rrf_merge

def _hit(entry_id: str, score: float = 0.0, source_path: str = "/a.md") -> Hit:
    return Hit(entry_id=entry_id, score=score, snippet="", source_path=source_path)

def test_rrf_merge_single_list_preserves_order() -> None:
    hits = [_hit("a"), _hit("b"), _hit("c")]
    result = rrf_merge(hits)
    assert [h.entry_id for h in result] == ["a", "b", "c"]
```

---

### `tests/knowledge/golden/corpus.py` and `queries.json` (test fixtures, batch)

**Analog:** `tests/policy/test_golden_plans.py` (golden fixture pattern)

**Golden fixture pattern** (`tests/policy/test_golden_plans.py` lines 27-50):
```python
@dataclass(frozen=True)
class Golden:
    name: str
    plan: Plan
    expected: RiskLevel

GOLDEN_CASES: tuple[Golden, ...] = (
    Golden("A: lectura unica", _plan(Action("file.read", "~/Documents/notas.md")), RiskLevel.A),
    ...
)

@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c.name)
def test_golden_plan(case: Golden, engine: CognitivePolicyEngine) -> None:
    decision = engine.evaluate(case.plan)
    assert decision.risk_level == case.expected
```
Copy: define `CORPUS: tuple[...]` as committed data, `GOLDEN_QUERIES` as parametrized cases. Use `@pytest.mark.parametrize` with `ids`.

**`corpus.py` shape:**
```python
# List of (source_path, text, kb_id) — inserted into FTS5 + vector index
CORPUS: tuple[tuple[str, str, str], ...] = (
    ("/docs/python_guide.md", "Python es un lenguaje de programación ...", "personal"),
    ...
)
```

**`queries.json` shape** (Claude's Discretion — N=20):
```json
[
  {"query": "Python programación", "kb_id": "personal", "expected_source_path": "/docs/python_guide.md"},
  ...
]
```
Gate: `hit@1 >= 0.80` (16/20 pass). Corpus must be designed so FTS5 keyword overlap guarantees hit@1 — FakeEmbedding provides noise, not signal.

---

### `tests/cli/test_search_command.py` (test, CLI)

**Analog:** `tests/cli/test_index_command.py` — exact same structure

**CliRunner + monkeypatch pattern** (`tests/cli/test_index_command.py` lines 1-17, 118-143):
```python
from typer.testing import CliRunner
import bootstrap.cli as cli
from bootstrap.cli import app

runner = CliRunner()

def test_exit_code_zero_with_failures(tmp_path, monkeypatch):
    def fake_build_pipeline(settings, *, audit, embedder):
        return FakePipeline(run_result=failed_result)

    monkeypatch.setattr(cli, "_build_embedder", _fake_build_embedder)
    monkeypatch.setattr(cli, "build_pipeline", fake_build_pipeline)

    result = runner.invoke(app, ["index", str(sample), "--config", str(cfg)])
    assert result.exit_code == 0
```
Copy: `monkeypatch.setattr(cli, "build_retrieval", fake_build_retrieval)` to inject fake retrieval in search tests. For JSON output tests: `runner.invoke(app, ["search", "query", "--json", "--config", str(cfg)])` and `json.loads(result.output)`.

**Config fixture** (`tests/cli/test_index_command.py` lines 52-67):
```python
def _write_config(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    audit_db = tmp_path / "audit" / "audit.db"
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f'data_dir = "{data_dir}"\naudit_db = "{audit_db}"\n[ingest]\n...',
        encoding="utf-8",
    )
    return cfg
```
Reuse `_write_config` or copy — same `data_dir` / `audit_db` structure needed.

**Integration test marker** (`tests/cli/test_index_command.py` lines 177-189):
```python
@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("WYSS_TEST_OLLAMA") != "1",
    reason="requiere WYSS_TEST_OLLAMA=1 (Ollama local + nomic-embed-text)",
)
def test_search_command_with_ollama_real(tmp_path: Path) -> None:
    ...
```
Copy: integration tests with Ollama are skipped in CI unless `WYSS_TEST_OLLAMA=1`.

---

## Shared Patterns

### Audit Emission
**Source:** `src/knowledge/pipeline.py` lines 262-276 + `src/core/domain/audit.py` lines 55-76
**Apply to:** `src/knowledge/retrieval.py`
```python
self._audit.log(
    AuditEvent.new(
        actor_type=ActorType.OWNER,     # owner-initiated search
        actor_id=subject.subject_id,
        event_type=AuditEventType.ACTION_COMPLETED,
        message=f"search: '{query.text}' -> {len(merged)} results",
        payload={
            "degraded": degraded,
            "reason": degraded_reason,
            "kb_ids": list(query.kb_ids),
            "result_count": len(merged),
        },
    )
)
```
Regla #1: sin auditar no está terminado. Every `search()` call — including degraded path — emits one event.

### Error Handling in CLI Commands
**Source:** `src/bootstrap/cli.py` lines 242-254
**Apply to:** `search` and `status` commands in `src/bootstrap/cli.py`
- `ConfigError`, `IndexIntegrityError`, `AuditIntegrityError` → `typer.Exit(code=1)`
- `OSError`, `sqlite3.Error` → `typer.Exit(code=1)`
- Degraded search (Ollama down) → `exit code 0`, banner to stderr/console
- `finally:` always closes `StateStore` and audit logger

### Parameterized SQL
**Source:** `src/knowledge/state_store.py` lines 40-64, `src/knowledge/fts_index.py` lines 44-73
**Apply to:** all new SQL in `state_store.py` freshness methods
All SQL uses `?` placeholders. No f-string interpolation for values. Identifiers (column names, table names) may appear in f-strings only when they come from constants, never from user input.

### Frozen Dataclasses (stdlib-only domain types)
**Source:** `src/core/domain/knowledge.py` lines 27-141
**Apply to:** `BcFreshness` dataclass in `state_store.py`
```python
@dataclass(frozen=True, slots=True)
class BcFreshness:
    ...
```
All new domain/result types: `frozen=True, slots=True`. No Pydantic in `core/` or `knowledge/`.

### Test Fixture Convention
**Source:** `tests/knowledge/test_fts_index.py` + `tests/knowledge/test_vector_index.py`
**Apply to:** all new test files in `tests/knowledge/`
- `_entry()` factory function for `IndexEntry`
- `_connect()` returns `:memory:` sqlite3 with schema applied
- `chromadb.PersistentClient(path=str(tmp_path / "chroma"))` for vector tests
- `@pytest.mark.integration` for tests requiring real DB/Ollama

---

## No Analog Found

All files have analogs. No entries in this section.

---

## Metadata

**Analog search scope:** `src/knowledge/`, `src/bootstrap/`, `src/core/domain/`, `src/core/ports/`, `src/audit/`, `tests/knowledge/`, `tests/cli/`, `tests/ports/`, `tests/policy/`
**Files scanned:** 18 source + 12 test files read directly
**Pattern extraction date:** 2026-06-12
