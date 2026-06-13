# Phase 4: Búsqueda Híbrida — Research

**Researched:** 2026-06-12
**Domain:** Hybrid information retrieval (FTS5 + ChromaDB vector) with RRF fusion, async Python, SQLite freshness, Rich CLI
**Confidence:** HIGH — all critical claims verified by reading actual codebase files; no package installs needed (no new deps)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-43:** Rich Panels verticales por hit (ruta exacta, extracto resaltado, fuente, fecha) como default interactivo + `--json` para scripting + auto-JSON vía `sys.stdout.isatty()`. `--limit` default 10; `--kb` para acotar BC. Zero nuevas deps.
- **D-44:** Ollama caído → auto-fallback FTS5-only con banner visible + `degraded: true` en JSON + exit code 0 + AuditEvent registrado + flag `--fts-only` para forzar modo degradado.
- **D-45:** Eval set — estrategia A: corpus fixture sintético commiteado + FakeEmbedding existente + métrica hit@1 + gate duro en CI. N=20 consultas doradas → archivo esperado. Zero deps externas en CI.
- **D-46:** Default busca en todas las BCs del owner. `--kb` opcional acota. El CLI expande wildcard a lista de kb_ids antes de llamar al port `Retrieval(query, subject)` — el port siempre recibe `kb_ids` explícitos.
- **D-47:** Doble superficie de frescura: footer de 1 línea en cada búsqueda + comando `wyss status` con detalle por BC. Query centralizada en service layer desde `state_store` SQLite. Nunca dos queries divergentes.

### Claude's Discretion

- Parámetros de RRF: constante k (validar k=60 como default), pesos relativos FTS5/vector, configurables en `config.toml`.
- Esquema exacto del JSON de salida (campos de Hit + metadata de corrida).
- Umbral del gate hit@1 en CI y composición del corpus fixture.
- Cómo se obtiene la fecha por resultado (mtime del archivo vs fecha de indexación).
- Detalle del comando `wyss status` (formato, campos adicionales).
- Piloto automático: decisiones menores sin preguntar; consultar solo ante cambios de arquitectura, seguridad o scope.

### Deferred Ideas (OUT OF SCOPE)

- Set de eval curado por el owner sobre archivos reales (N=50, MRR@5, con Ollama vivo) — extensión post-Fase 5.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| KNOW-04 | `wyss search "<consulta>"` — recuperación híbrida con fusión RRF, < 5 segundos | RRF implementado en `knowledge/` como stdlib pura; ambos índices ya implementados y testeados |
| KNOW-05 | Cada resultado incluye ruta exacta, extracto relevante, fuente y fecha | `Hit.source_path` + `Hit.snippet` ya en dominio; fecha via `indexed_at`/`mtime` de `file_state` |
| KNOW-10 | El índice expone su frescura — "indexado al [fecha]" consultable | `file_state.indexed_at` en SQLite; query `MAX(indexed_at)` por `kb_id` ya disponible |
| AUD-03 | Eval set de conocimiento: N consultas doradas con archivo esperado — regresión detectable | Fixture sintético en `tests/knowledge/`; `FakeEmbeddingProvider` ya en `tests/ports/fakes.py` |

</phase_requirements>

---

## Summary

La Fase 4 construye la capa de retrieval híbrido sobre dos índices ya funcionales y testeados: `FTS5Index` (SQLite FTS5, BM25 nativo) y `ChromaVectorIndex` (ChromaDB 1.5.9, cosine distance). El nuevo componente central es `HybridRetrieval` en `src/knowledge/` que implementa el port `Retrieval` (async) con fusión RRF, manejo de degradación sin vectores (D-44) y auditoría obligatoria de cada consulta.

Todos los contratos de dominio necesarios ya existen: `Hit`, `Query`, `Subject`, `IndexEntry` en `core/domain/knowledge.py`. El port `Retrieval.search(query: Query, subject: Subject) -> Sequence[Hit]` está definido en `src/core/ports/knowledge.py`. El composition root en `cli.py` ya muestra el patrón DI exacto a replicar para los nuevos comandos `search` y `status`.

La única decisión técnica no trivial que requería investigación es la compatibilidad de `sqlite3` con asyncio: verificado en la máquina real que llamadas sync directas dentro de `asyncio.run()` son seguras (mismo hilo), pero `run_in_executor` falla con `ProgrammingError` a menos que se use `check_same_thread=False`. La solución correcta para este proyecto es llamar `fts_index.search()` directamente desde el servicio async (sin thread pool), ya que el CLI llama `asyncio.run(retrieval.search(...))` en el hilo principal — el mismo donde se abrió la conexión sqlite3.

**Primary recommendation:** Implementar `HybridRetrieval` en `src/knowledge/retrieval.py` como clase stdlib-only (sin import de chromadb directo), que recibe `FullTextIndex`, `VectorIndex`, `EmbeddingProvider` y `AuditPort` por constructor. La fusión RRF es lógica pura (`score = 1 / (k + rank)`). El servicio vive en `knowledge/` (no en `core/`) para poder recibir los adapters concretos sin violar `lint-imports`.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| CLI `wyss search` + `wyss status` | CLI (bootstrap) | — | Composition root; isatty detection; Rich output |
| Fusión RRF + degradación D-44 | Service (knowledge/) | — | Lógica pura sin infra; recibe ports por DI |
| FTS5 search (BM25) | Adapter (knowledge/) | — | SQLite sync; llamado desde coroutine en hilo principal |
| Vector search (ChromaDB cosine) | Adapter (knowledge/) | — | ChromaDB sync API; mismo patrón que FTS5 |
| Query embedding (Ollama) | Adapter (gateway/) | — | httpx async; su fallo activa D-44 |
| Auditoría de consulta | Transversal (audit/) | service layer | AuditPort inyectado; cada `search()` genera AuditEvent |
| Frescura del índice | Service (knowledge/) | state_store | Query centralizada sobre `file_state.indexed_at` |
| Eval set dorado (CI) | tests/knowledge/ | — | Corpus fixture + FakeEmbeddingProvider determinista |

---

## Standard Stack

### Core (zero deps nuevas — todo ya en pyproject.toml)

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| `sqlite3` | stdlib | FTS5 search ya implementado en `FTS5Index` | `[VERIFIED: codebase]` |
| `chromadb` | 1.5.9 | Vector search ya implementado en `ChromaVectorIndex` | `[VERIFIED: codebase]` |
| `httpx` | 0.28.1 | OllamaEmbeddingProvider embed call; fallo detectado via `HTTPError`/`TransportError` | `[VERIFIED: codebase]` |
| `rich` | >=15.0.0 | Panels, Console — ya usado en `cli.py` | `[VERIFIED: codebase]` |
| `typer` | 0.26.7 | CLI commands — ya usado en `cli.py` | `[VERIFIED: codebase]` |
| `pytest-asyncio` | >=1.4.0 | Tests async del servicio de retrieval | `[VERIFIED: codebase]` |

**No se agrega ningún paquete nuevo.** `[VERIFIED: pyproject.toml]`

### Installation

No action needed — all deps already in lock file.

---

## Package Legitimacy Audit

**No new packages to install in this phase.** All required capabilities are covered by the existing dependency set verified in `pyproject.toml`. This section is not applicable.

---

## Architecture Patterns

### System Architecture Diagram

```
wyss search "<query>" (CLI)
        │
        ▼
  [cli.py: search command]
  ┌─────────────────────────────────────────────┐
  │ 1. load settings + open DBs                │
  │ 2. detect isatty → Rich / JSON output       │
  │ 3. expand wildcard → kb_ids (D-46)          │
  │ 4. build Query(text, kb_ids, limit)         │
  │ 5. asyncio.run(retrieval.search(q, subj))   │
  └─────────────────────────────────────────────┘
        │
        ▼
  [HybridRetrieval.search(query, subject)] — knowledge/retrieval.py
  ┌─────────────────────────────────────────────┐
  │ 1. AuditPort: log COMMAND_RECEIVED          │
  │ 2. try: embed query → OllamaEmbeddingProvider│
  │    except HTTPError/TransportError:          │
  │      → set degraded=True, reason="ollama"   │
  │ 3a. fts_hits = fts_index.search(q, kbids, N)│ ← sync, same thread (safe)
  │ 3b. if not degraded:                         │
  │       vec_hits = vector_index.search(v,N)   │ ← sync, same thread (safe)
  │ 4. rrf_merge(fts_hits, vec_hits, k=60)      │ ← stdlib pure
  │ 5. trim to query.limit                       │
  │ 6. enrich hits with date from state_store   │
  │ 7. AuditPort: log ACTION_COMPLETED + meta   │
  │    (degraded flag, query text, result count) │
  │ 8. return Sequence[Hit]                      │
  └─────────────────────────────────────────────┘
        │
        ▼
  [cli.py: render output]
  ┌─────────────────────────────────────────────┐
  │ if degraded: print banner (D-44)            │
  │ render hits: Rich Panels or JSON            │
  │ print freshness footer (D-47)               │
  └─────────────────────────────────────────────┘
```

```
wyss status (CLI)
        │
        ▼
  [cli.py: status command]
        │
        ▼
  [FreshnessService.status_by_bc(kb_ids)] — knowledge/freshness.py (or inline in retrieval.py)
  ┌─────────────────────────────────────────────┐
  │ SELECT kb_id, MAX(indexed_at), COUNT(*),    │
  │        SUM(CASE status='embedded'...) ...   │
  │ FROM file_state GROUP BY kb_id             │
  └─────────────────────────────────────────────┘
        │
        ▼
  [cli.py: Rich Table per BC]
```

### Recommended Project Structure

```
src/
├── core/
│   ├── domain/knowledge.py      # Hit, Query, Subject — no changes needed
│   └── ports/knowledge.py       # Retrieval protocol — already defined
├── knowledge/
│   ├── retrieval.py             # NEW: HybridRetrieval (implements Retrieval port)
│   ├── rrf.py                   # NEW: rrf_merge() — pure stdlib, zero imports from infra
│   ├── fts_index.py             # UNCHANGED
│   ├── vector_index.py          # UNCHANGED
│   └── state_store.py           # UNCHANGED (freshness query added as method)
├── bootstrap/
│   └── cli.py                   # ADD: search + status commands; wire HybridRetrieval
tests/
├── knowledge/
│   ├── test_retrieval.py        # NEW: unit + integration tests for HybridRetrieval
│   ├── test_rrf.py              # NEW: pure unit tests for rrf_merge()
│   └── golden/
│       ├── corpus.py            # NEW: synthetic corpus fixture (N docs, committed)
│       └── queries.json         # NEW: N=20 golden queries → expected hit@1
└── cli/
    └── test_search_command.py   # NEW: CLI tests (Rich/JSON output, degraded banner)
```

### Pattern 1: RRF Merge (pure stdlib)

**What:** Combine ranked lists from FTS5 and vector search without score normalization. `score = 1 / (k + rank)`, summed across lists. k=60 is the industry-standard default (validated by Cormack & Clarke 2009, used by Azure AI Search, Weaviate, etc.).

**Key property:** RRF ignores raw scores entirely — only rank positions matter. This makes FTS5 BM25 scores (negative floats, lower is better in SQLite) and ChromaDB cosine similarity scores (0-1, higher is better) directly composable without normalization.

**Important:** FTS5 `bm25()` in SQLite returns negative values (lower = more relevant). When building the ranked list for RRF, sort FTS5 hits ascending by score (most relevant first). ChromaDB returns distances (0=identical), but `ChromaVectorIndex.search()` already converts to similarity: `score = 1.0 - distance`. Sort vector hits descending. Both result in rank 1 = best match.

```python
# Source: verified against FTS5Index.search() return type + RRF paper
from collections.abc import Sequence
from core.domain.knowledge import Hit

def rrf_merge(
    *hit_lists: Sequence[Hit],
    k: int = 60,
    limit: int = 10,
) -> list[Hit]:
    """Reciprocal Rank Fusion over N ranked lists of Hits.

    FTS5 hits must already be sorted best-first (ascending BM25 score).
    Vector hits must already be sorted best-first (descending similarity).
    """
    scores: dict[str, float] = {}
    best_hit: dict[str, Hit] = {}
    for hit_list in hit_lists:
        for rank, hit in enumerate(hit_list, start=1):
            scores[hit.entry_id] = scores.get(hit.entry_id, 0.0) + 1.0 / (k + rank)
            if hit.entry_id not in best_hit:
                best_hit[hit.entry_id] = hit
    merged = sorted(best_hit.values(), key=lambda h: scores[h.entry_id], reverse=True)
    return [Hit(
        entry_id=h.entry_id,
        score=scores[h.entry_id],  # RRF score replaces original
        snippet=h.snippet,
        source_path=h.source_path,
    ) for h in merged[:limit]]
```

**Snippet source:** The `best_hit` map retains the first-seen snippet per entry_id. Since FTS5 provides highlighted snippets and vector search returns raw chunk text, prefer FTS5 hits when the same entry appears in both lists.

### Pattern 2: Ollama Failure Detection → D-44 Trigger

**What:** Calling `OllamaEmbeddingProvider.embed()` raises `httpx.HTTPError` or `httpx.TransportError` when Ollama is down (connection refused, timeout). The retrieval service catches these and falls back to FTS5-only.

**Verified failure path from codebase:**
- `cli.py:_build_embedder()` already checks `GET /api/tags` — same pattern applies for per-query embedding
- `OllamaEmbeddingProvider.embed()` does `resp.raise_for_status()` — network errors propagate as `httpx.TransportError` before that line
- Timeout: `httpx.Timeout(2.0)` in `cli.py` for index building; retrieval should use a tighter timeout (e.g., 3.0s for a single embedding call) to stay within the 5-second SLA

```python
# Source: verified from src/gateway/providers/ollama.py + src/bootstrap/cli.py
try:
    query_vector = (await self._embedder.embed([query.text]))[0]
    vec_hits = self._vector_index.search(query_vector, query.kb_ids, over_fetch)
except (httpx.HTTPError, httpx.TransportError):
    degraded = True
    degraded_reason = "ollama unavailable"
    vec_hits = ()
```

### Pattern 3: Async + SQLite3 — Thread Safety

**Verified behavior:** `sqlite3` connections are NOT thread-safe by default (`check_same_thread=True`). Calling `run_in_executor` with a connection created in the main thread raises `sqlite3.ProgrammingError`. [VERIFIED: tested on this machine, Python 3.14]

**Correct pattern for this project:** Since `cli.py` calls `asyncio.run(retrieval.search(...))`, the entire coroutine runs in the main thread. `fts_index.search()` is a sync call inside the coroutine — it executes in the same thread that created the `sqlite3.Connection`. No `run_in_executor` needed or desired.

**Do NOT use `run_in_executor` for FTS5 calls.** The latency of FTS5 on a local SQLite file is < 50ms — far below the 5-second SLA — and thread pool overhead adds complexity without benefit.

**Alternative if threading is ever needed:** Pass `check_same_thread=False` to `sqlite3.connect()`. The `open_index_db()` function in `knowledge/db.py` would need this parameter. Not needed for Phase 4.

### Pattern 4: Freshness Query for D-47

**Source data:** `file_state` table in `index.db` — already has `indexed_at REAL` (unix epoch, set by `mark_embedded()`), `kb_id TEXT`, `status TEXT`. [VERIFIED: src/knowledge/index_schema.py]

```sql
-- Source: verified from index_schema.py CREATE_FILE_STATE
SELECT
  kb_id,
  MAX(indexed_at) AS last_indexed_at,
  COUNT(*) AS total_files,
  SUM(CASE WHEN status='embedded' THEN 1 ELSE 0 END) AS embedded,
  SUM(CASE WHEN status='extracted' THEN 1 ELSE 0 END) AS extracted_pending,
  SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed,
  SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending
FROM file_state
GROUP BY kb_id
ORDER BY kb_id
```

This single query powers both surfaces (D-47): the search footer (compact) and `wyss status` (full table). Add as `freshness_by_kb()` method on `StateStore` or as a standalone function in a new `knowledge/freshness.py`.

### Pattern 5: Hit Date — Source of Truth

Per KNOW-05, each result needs a "date". Two candidates in `file_state`:
- `mtime REAL`: the file's modification time on disk (reflects actual content age)
- `indexed_at REAL`: when wyss processed it (may be later than content was created)

**Recommendation (Claude's Discretion):** Use `mtime` as the displayed date — it reflects when the content was last changed, which is more meaningful to the user than when wyss indexed it. `indexed_at` is useful for "indexed since" in the footer (D-47).

`Hit` domain type currently has no `date` field. Two options:
1. Add `date: float | None` to `Hit` — requires changing the frozen dataclass (additive, not breaking)
2. Return date in a wrapper `SearchResult` at the service layer — avoids touching domain

**Recommendation:** Add `date: float | None = None` to `Hit` in `core/domain/knowledge.py`. It's the simplest path, consistent with "Expandir en Fases 3-4 es aditivo, no breaking" (KNOW-05 comment in knowledge.py). [ASSUMED — not in current `Hit` definition; decision belongs to owner/planner]

### Pattern 6: CLI Composition Root for `search` + `status`

The `index` command in `cli.py` shows the exact DI pattern: `build_pipeline()` constructs all real dependencies from `WyssSettings`. The `search` command needs a similar `build_retrieval()`:

```python
# Based on build_pipeline() pattern in cli.py
def build_retrieval(
    settings: WyssSettings,
    *,
    audit: AuditPort,
    embedder: EmbeddingProvider | None,
) -> HybridRetrieval:
    state_store = StateStore(settings.data_dir / "index.db")
    fts_index = FTS5Index(state_store._conn)
    chroma_client = chromadb.PersistentClient(path=str(settings.data_dir / "chroma"))
    vector_index = ChromaVectorIndex(chroma_client)
    return HybridRetrieval(
        fts_index=fts_index,
        vector_index=vector_index,
        embedder=embedder,  # None triggers degraded mode
        audit=audit,
    )
```

### Pattern 7: Eval Set Architecture (D-45)

**Goal:** N=20 deterministic golden queries that pass `hit@1` gate in CI without Ollama or real data.

**Synthetic corpus design:**
- 5-10 in-memory documents with distinct topics (Python code, markdown, Spanish text, PDF-like content)
- Each doc maps to ≥1 golden query with a known `expected_source_path`
- FakeEmbeddingProvider (existing in `tests/ports/fakes.py`) returns `tuple(float(len(t)) for _ in range(3))` — deterministic but meaningless for semantic similarity
- For this eval set, FTS5 carries the weight of `hit@1` (corpus is designed so keyword search succeeds)
- Vector results with FakeEmbedding add noise but RRF aggregation should not demote FTS5 winners for on-topic queries

**CI gate threshold:** hit@1 >= 0.80 (16/20 queries return correct top result). This is conservative enough to pass with FTS5-dominant corpus but sensitive enough to catch regressions that break FTS5.

**Fixture location:** `tests/knowledge/golden/` — committed to repo. Format: `corpus.py` (list of `(source_path, text, kb_id)` tuples), `queries.json` (array of `{query, kb_id, expected_source_path}`).

### Anti-Patterns to Avoid

- **Calling `run_in_executor` for sqlite3 reads:** Thread safety violation without `check_same_thread=False`. Unnecessary — direct sync call from coroutine is safe when entry point is `asyncio.run()`.
- **Normalizing FTS5 BM25 scores before RRF:** BM25 scores are negative in SQLite FTS5. Normalization is error-prone and unnecessary — RRF uses only rank positions.
- **Putting RRF logic in `core/`:** RRF is stdlib-only and could live in `core/`, but it receives `Sequence[Hit]` which IS a core domain type. However, placing it in `knowledge/rrf.py` avoids confusion — it's only used by the knowledge adapter layer.
- **Two separate `StateStore` instances for search and status:** Opens two connections to the same `index.db`. Share the connection via a single `StateStore` instance in `build_retrieval()`.
- **Fetching full chunk text from ChromaDB for snippet:** `ChromaVectorIndex.search()` already returns `Hit.snippet` (the full document text from the collection). For large chunks this is fine; no need to re-query.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Rank fusion | Custom score normalization (min-max, softmax) | RRF with k=60 | Score normalization requires calibration; RRF is parameter-free and provably robust |
| FTS5 search | Custom tokenizer or relevance scorer | SQLite FTS5 `bm25()` already in `FTS5Index` | Already implemented and tested in Phase 3 |
| Vector search | HNSW from scratch | ChromaDB already in `ChromaVectorIndex` | Already implemented and tested in Phase 3 |
| Query embedding | Direct httpx calls | `OllamaEmbeddingProvider` already built | Already handles batching, L2-norm, error path |
| Audit | Ad-hoc logging | `AuditPort` + `SqliteAuditLogger` already wired | Regla #1: sin auditar no está terminado |
| CLI output | Custom Rich formatter | `Console`, `Panel`, `Table` patterns from existing `cli.py` | Pattern established; isatty logic already there |

**Key insight:** Every infrastructure component for this phase already exists. The only new code is the service layer glue (RRF fusion + degradation logic) and CLI commands.

---

## Common Pitfalls

### Pitfall 1: FTS5 BM25 Score Direction

**What goes wrong:** Treating FTS5 `bm25()` score as "higher = better" and sorting descending. The result list is inverted.

**Why it happens:** BM25 in most implementations returns higher scores for better matches. SQLite FTS5 `bm25()` returns **negative** values where lower (more negative) = better match. `ORDER BY rank` in the FTS5 query already sorts correctly (ascending = best first).

**How to avoid:** In `rrf_merge()`, pass FTS5 hits exactly as returned by `FTS5Index.search()` — they are already sorted best-first by the `ORDER BY rank` SQL clause. Do not re-sort.

**Warning signs:** Test `test_upsert_then_search_returns_hit` in `test_fts_index.py` passes, but RRF test returns wrong top hit.

### Pitfall 2: sqlite3 Thread Safety in `run_in_executor`

**What goes wrong:** `asyncio.get_event_loop().run_in_executor(None, fts_search)` raises `sqlite3.ProgrammingError: SQLite objects created in a thread can only be used in that same thread`.

**Why it happens:** sqlite3 connections default to `check_same_thread=True`. A thread pool executor runs the callable in a different thread.

**How to avoid:** Do NOT use `run_in_executor` for FTS5 calls. The `asyncio.run()` wrapper in `cli.py` runs the coroutine in the main thread — the same thread where `sqlite3.Connection` is created. Direct sync calls from within the coroutine are safe.

**Warning signs:** Tests pass (they use `:memory:` connections freshly created per test) but production crashes on the first real search.

### Pitfall 3: Empty Query Edge Case in RRF

**What goes wrong:** `FTS5Index.search()` returns `()` for empty/tokenized-to-empty queries (already guarded). But `rrf_merge((), ())` returns `[]` — correct behavior that must propagate up cleanly, not raise.

**How to avoid:** `HybridRetrieval.search()` should handle the case where both lists are empty (e.g., Ollama down + FTS5 returns zero results) and return an empty sequence with appropriate audit event.

### Pitfall 4: `Hit.score` Semantics Change After RRF

**What goes wrong:** Downstream code (Fase 5, CLI) assumes `Hit.score` is a cosine similarity (0-1) or BM25 score. After RRF, `score = sum(1/(k+rank))` — a small float around 0.016. Comparisons like `hit.score > 0.5` break.

**How to avoid:** The RRF score replaces the original score in merged `Hit` objects. Document this in a docstring. The CLI renders hits by rank position, not by score threshold — this is safe.

### Pitfall 5: `wyss status` with No Indexed Data

**What goes wrong:** `MAX(indexed_at)` returns `NULL` when no files are embedded. Footer shows "indexado al None".

**How to avoid:** Handle `NULL` explicitly — `indexed_at is None` maps to "nunca indexado". StateStore freshness method returns typed result with `last_indexed_at: float | None`.

### Pitfall 6: Noop Indexes Still Wired in CLI at Search Time

**What goes wrong:** `cli.py` currently has `_NoopFullTextIndex` and `_NoopVectorIndex` as fallbacks for preview/dry-run. If `build_retrieval()` accidentally reuses the preview path, `search()` always returns empty results with no error.

**How to avoid:** `build_retrieval()` must always use `FTS5Index` and `ChromaVectorIndex` — not the noop variants. Noops stay scoped to `_build_preview_pipeline()`. Add an assertion or type annotation that makes the real types explicit.

---

## Runtime State Inventory

This phase does not rename or migrate any existing state. However, it reads from existing state:

| Category | Items | Action |
|----------|-------|--------|
| Stored data | `file_state` table in `index.db` — read-only for freshness queries; `chunks` table — read-only for FTS5 | No migration; read-only access via existing `StateStore._conn` |
| Stored data | ChromaDB persistent collections under `data/chroma/` — read-only for vector search | No migration; `ChromaVectorIndex` uses existing client |
| Live service config | Ollama at `localhost:11434` — must be UP for vector path | D-44 handles gracefully; note in docs |
| OS-registered state | None | None |
| Secrets/env vars | No new keys; existing `WYSS_DATA_DIR` / `config.toml` paths carry forward | No action |
| Build artifacts | No new build artifacts | None |

**Nothing to migrate** — Phase 4 is read-only with respect to the indexes populated by Phase 3.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `sqlite3` FTS5 | FTS5Index.search() | ✓ | 3.50.4 | — |
| `chromadb` | ChromaVectorIndex.search() | ✓ | 1.5.9 | D-44 degraded mode |
| `httpx` | OllamaEmbeddingProvider | ✓ | 0.28.1 | D-44 degraded mode |
| `rich` | CLI output | ✓ | >=15.0.0 | — |
| `typer` | CLI commands | ✓ | 0.26.7 | — |
| `pytest-asyncio` | Async tests | ✓ | >=1.4.0 | — |
| Ollama (localhost:11434) | Query embedding | optional | unknown | D-44: FTS5-only fallback |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** Ollama — D-44 handles gracefully.

---

## Validation Architecture

nyquist_validation is `true` in `.planning/config.json`.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=9 + pytest-asyncio >=1.4.0 |
| Config file | `pyproject.toml` → `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| Quick run command | `uv run pytest tests/knowledge/test_rrf.py tests/knowledge/test_retrieval.py -x` |
| Full suite command | `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports` |

**Baseline:** 263 passed, 3 skipped (confirmed on 2026-06-12). Full green chain confirmed (`mypy`, `ruff`, `lint-imports`).

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| KNOW-04 (RRF) | `rrf_merge()` returns best-ranked Hit from two lists | unit | `uv run pytest tests/knowledge/test_rrf.py -x` | ❌ Wave 0 |
| KNOW-04 (hybrid) | `HybridRetrieval.search()` returns merged results | unit | `uv run pytest tests/knowledge/test_retrieval.py::test_hybrid_returns_merged -x` | ❌ Wave 0 |
| KNOW-04 (<5s) | Smoke test over populated index | integration | `uv run pytest tests/knowledge/test_retrieval.py -m integration` | ❌ Wave 0 |
| KNOW-04 (degraded) | Ollama down → FTS5-only + degraded flag | unit | `uv run pytest tests/knowledge/test_retrieval.py::test_degraded_mode -x` | ❌ Wave 0 |
| KNOW-05 (fields) | Hit contains source_path, snippet, date | unit | included in test_retrieval.py | ❌ Wave 0 |
| KNOW-10 (freshness) | `freshness_by_kb()` returns correct dates | unit | `uv run pytest tests/knowledge/test_retrieval.py::test_freshness -x` | ❌ Wave 0 |
| AUD-03 (eval set) | N=20 golden queries hit@1 >= 0.80 | integration | `uv run pytest tests/knowledge/test_golden_queries.py -x` | ❌ Wave 0 |
| D-44 (audit) | Degraded search produces AuditEvent | unit | `uv run pytest tests/knowledge/test_retrieval.py::test_degraded_audit -x` | ❌ Wave 0 |
| D-43 (CLI JSON) | `wyss search --json` outputs valid JSON | CLI | `uv run pytest tests/cli/test_search_command.py -x` | ❌ Wave 0 |
| D-43 (CLI Rich) | `wyss search` renders Rich Panels | CLI | `uv run pytest tests/cli/test_search_command.py::test_rich_output -x` | ❌ Wave 0 |
| D-47 (status) | `wyss status` shows per-BC freshness | CLI | `uv run pytest tests/cli/test_search_command.py::test_status_command -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/knowledge/ tests/cli/test_search_command.py -x`
- **Per wave merge:** `uv run pytest -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/knowledge/test_rrf.py` — covers KNOW-04 RRF unit
- [ ] `tests/knowledge/test_retrieval.py` — covers KNOW-04, KNOW-05, KNOW-10, D-44, AUD-03 integration
- [ ] `tests/knowledge/test_golden_queries.py` — covers AUD-03 eval set gate
- [ ] `tests/knowledge/golden/corpus.py` — synthetic corpus fixture
- [ ] `tests/knowledge/golden/queries.json` — N=20 golden queries → expected file
- [ ] `tests/cli/test_search_command.py` — covers D-43, D-47 CLI behavior

---

## Code Examples

### RRF merge function

```python
# Source: derived from RRF paper (Cormack & Clarke 2009) + verified FTS5Index/ChromaVectorIndex return types
from collections.abc import Sequence
from core.domain.knowledge import Hit

def rrf_merge(
    *hit_lists: Sequence[Hit],
    k: int = 60,
    limit: int = 10,
) -> list[Hit]:
    scores: dict[str, float] = {}
    best_hit: dict[str, Hit] = {}
    for hit_list in hit_lists:
        for rank, hit in enumerate(hit_list, start=1):
            scores[hit.entry_id] = scores.get(hit.entry_id, 0.0) + 1.0 / (k + rank)
            if hit.entry_id not in best_hit:
                best_hit[hit.entry_id] = hit
    merged = sorted(best_hit.values(), key=lambda h: scores[h.entry_id], reverse=True)
    return [
        Hit(entry_id=h.entry_id, score=scores[h.entry_id], snippet=h.snippet, source_path=h.source_path)
        for h in merged[:limit]
    ]
```

### HybridRetrieval skeleton

```python
# Source: derived from OllamaEmbeddingProvider + FTS5Index + ChromaVectorIndex signatures
import httpx
from collections.abc import Sequence
from core.domain.audit import ActorType, AuditEvent, AuditEventType
from core.domain.knowledge import Hit, Query
from core.domain.security import Subject
from core.ports.audit import AuditPort
from core.ports.knowledge import EmbeddingProvider, FullTextIndex, VectorIndex
from knowledge.rrf import rrf_merge  # stdlib only

_OVER_FETCH_MULTIPLIER = 3  # fetch 3x limit from each index before RRF trim

class HybridRetrieval:
    def __init__(
        self,
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

    async def search(self, query: Query, subject: Subject) -> Sequence[Hit]:
        over_fetch = query.limit * _OVER_FETCH_MULTIPLIER
        fts_hits = self._fts.search(query.text, query.kb_ids, over_fetch)  # sync, safe
        degraded = self._embedder is None
        degraded_reason = "fts-only mode" if degraded else ""
        vec_hits: Sequence[Hit] = ()
        if not degraded:
            try:
                vectors = await self._embedder.embed([query.text])
                vec_hits = self._vec.search(vectors[0], query.kb_ids, over_fetch)
            except (httpx.HTTPError, httpx.TransportError) as exc:
                degraded = True
                degraded_reason = f"ollama unavailable: {exc}"
        merged = rrf_merge(fts_hits, vec_hits, k=self._rrf_k, limit=query.limit)
        self._audit.log(AuditEvent.new(
            actor_type=ActorType.OWNER,
            actor_id=subject.subject_id,
            event_type=AuditEventType.ACTION_COMPLETED,
            message=f"search: '{query.text}' → {len(merged)} results",
            payload={"degraded": degraded, "reason": degraded_reason, "kb_ids": list(query.kb_ids)},
        ))
        return merged
```

### Freshness query on StateStore

```python
# Source: verified from index_schema.py (file_state columns: kb_id, indexed_at, status)
import sqlite3
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class BcFreshness:
    kb_id: str
    last_indexed_at: float | None
    total: int
    embedded: int
    pending: int
    failed: int

def freshness_by_kb(conn: sqlite3.Connection) -> list[BcFreshness]:
    rows = conn.execute("""
        SELECT kb_id,
               MAX(indexed_at),
               COUNT(*),
               SUM(CASE WHEN status='embedded' THEN 1 ELSE 0 END),
               SUM(CASE WHEN status IN ('pending','extracted') THEN 1 ELSE 0 END),
               SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END)
        FROM file_state
        GROUP BY kb_id ORDER BY kb_id
    """).fetchall()
    return [BcFreshness(str(r[0]), r[1], int(r[2]), int(r[3]), int(r[4]), int(r[5])) for r in rows]
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Weighted score normalization for hybrid search | RRF (rank-only, no score normalization) | Eliminates calibration burden; works across heterogeneous scorers |
| Separate keyword vs semantic search | Hybrid FTS5 + vector with RRF | Industry standard since ~2023; ChromaDB, Weaviate, Azure AI all ship RRF |
| `asyncio` + sqlite3 with `run_in_executor` | Direct sync call from coroutine (same thread as connection) | Simpler, avoids thread safety errors for this use case |

**Deprecated/outdated:**
- Score-based fusion (linear combination): requires per-system score normalization; replaced by rank-based methods for hybrid search.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `Hit.date` field should be added to the frozen dataclass with `float \| None = None` | Architecture Patterns §5 | If owner prefers a wrapper type, Hit stays unchanged; retrieval service wraps hits instead |
| A2 | hit@1 >= 0.80 is a reasonable CI gate threshold for N=20 synthetic queries | Validation Architecture | Too high: CI is brittle for synthetic corpus. Too low: misses real regressions. Owner may tune. |
| A3 | RRF k=60 is the correct default (CONTEXT.md delegates this to researcher) | Standard Stack | k=60 is industry consensus; lower k penalizes low-ranked hits more. Configurable in config.toml per D decision. |
| A4 | FakeEmbeddingProvider returns `tuple(float(len(t)) for _ in range(3))` — this is deterministic enough for hit@1 eval | Validation Architecture | The fake returns length-based vectors, so semantic queries won't rank by meaning. Eval corpus must be designed for FTS5 success. |

---

## Open Questions

1. **`Hit` domain extension for date field**
   - What we know: `Hit` is frozen dataclass with `entry_id, score, snippet, source_path`
   - What's unclear: Owner preference — extend `Hit` directly or use a `SearchResult` wrapper at service layer
   - Recommendation: Add `date: float | None = None` to `Hit` — KNOW-05 comment says "Expandir en Fases 3-4 es aditivo, no breaking"

2. **kb_ids wildcard expansion location**
   - What we know: D-46 says "el CLI expande el wildcard a lista de BCs"
   - What's unclear: How does the CLI know which BCs exist? Query `SELECT DISTINCT kb_id FROM file_state` on startup
   - Recommendation: Add `list_kb_ids()` to `StateStore`; CLI calls it before building `Query`

3. **`wyss status` KB list scope**
   - What we know: D-47 says detail per BC
   - What's unclear: Show ALL BCs in index.db or only BCs matching `--kb` filter?
   - Recommendation: Show all BCs (no filter) in `status` command — it's a diagnostic view

---

## Security Domain

`security_enforcement` is not set to false in config.json — treat as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No — owner-only CLI, no auth layer in Phase 4 | — |
| V3 Session Management | No | — |
| V4 Access Control | Partial — `Subject` passed to `Retrieval.search()`; permission enforcement deferred to Phase 7 (AGENT-03) | In Phase 4, subject is always the owner; no multi-subject enforcement yet |
| V5 Input Validation | Yes — query text is user input passed to FTS5 and embedder | FTS5Index already sanitizes via `_match_query()` (token extraction); OllamaEmbedding receives raw text (goes to local Ollama only, not external) |
| V6 Cryptography | No | — |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| FTS5 injection via MATCH syntax | Tampering | `FTS5Index._match_query()` already strips to word tokens; `"term"` quoting prevents MATCH operators. VERIFIED. |
| Query text leaks to external API | Information Disclosure | Ollama is local (localhost:11434) — accepted risk T-02-embed-egress per D-15. No external embedding in Phase 4. |
| IndexEntry content treated as instruction | Spoofing (prompt injection) | Phase 4 returns snippets as data to CLI — no LLM call on retrieved content. POL-07 applies from Phase 7+. |
| Audit bypass via degraded mode | Repudiation | D-44 explicitly requires AuditEvent for degraded search. Regla #1 enforced. |

---

## Sources

### Primary (HIGH confidence — verified by reading actual source files)

- `src/core/ports/knowledge.py` — `Retrieval` protocol signature: `async def search(query: Query, subject: Subject) -> Sequence[Hit]`
- `src/core/domain/knowledge.py` — `Hit`, `Query`, `FileStatus`, `FileRecord` fields; `indexed_at` in schema
- `src/knowledge/fts_index.py` — `FTS5Index.search()` returns negative BM25 scores; `ORDER BY rank` sort order
- `src/knowledge/vector_index.py` — `ChromaVectorIndex.search()` returns similarity `1.0 - distance`
- `src/knowledge/state_store.py` — `file_state` columns; `indexed_at REAL` available
- `src/knowledge/index_schema.py` — `CREATE_FILE_STATE` DDL; `indexed_at REAL` confirmed
- `src/gateway/providers/ollama.py` — raises `httpx.HTTPError`/`TransportError` on failure
- `src/bootstrap/cli.py` — DI pattern, `asyncio.run()` entry point, `isatty()` detection
- `tests/ports/fakes.py` — `FakeEmbeddingProvider` existing implementation
- `pyproject.toml` — dependency versions, `asyncio_mode = "auto"`, `lint-imports` contracts
- Python 3.14 sqlite3 test (run on this machine) — confirmed `run_in_executor` + same connection = `ProgrammingError`; direct sync call from coroutine = OK

### Secondary (MEDIUM confidence)

- [Azure AI Search RRF documentation](https://learn.microsoft.com/en-us/azure/search/hybrid-search-ranking) — k=60 default, score formula `1/(k+rank)`, no normalization needed
- WebSearch results confirming k=60 as industry standard (Cormack & Clarke 2009 original paper)

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — all packages verified in pyproject.toml/codebase
- Architecture: HIGH — all contracts verified in source files; patterns derived from existing `cli.py` and `pipeline.py`
- RRF algorithm: HIGH — formula verified from multiple authoritative sources + consistent with existing index return types
- Thread safety: HIGH — tested on actual Python 3.14 on this machine
- Pitfalls: HIGH — derived from reading actual implementation + verified behaviors

**Research date:** 2026-06-12
**Valid until:** 2026-12-01 (stable domain; ChromaDB API stable; SQLite FTS5 stable)
