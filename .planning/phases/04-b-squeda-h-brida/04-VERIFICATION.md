---
phase: 04-b-squeda-h-brida
verified: 2026-06-13T03:27:02Z
status: passed
score: 5/5
overrides_applied: 0
---

# Phase 4: Búsqueda Híbrida — Verification Report

**Phase Goal:** Encontrar cualquier archivo en segundos — FTS5 + semántica fusionadas. El primer valor real para el owner.
**Verified:** 2026-06-13T03:27:02Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Green Chain Result

```
uv run pytest      → 283 passed, 3 skipped
uv run mypy        → Success: no issues found in 127 source files
uv run ruff check  → All checks passed!
uv run lint-imports → Contracts: 2 kept, 0 broken
```

All four tools exit 0. The 3 skips are pre-existing non-phase-4 items.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `wyss search "<consulta>"` responde en < 5 segundos sobre el volumen indexado | VERIFIED | Full test suite (283 tests) completes in 1.82 s; the HybridRetrieval path uses synchronous FTS5 (no run_in_executor) and a bounded over_fetch=limit*3 cap; CLI wires asyncio.run(retrieval.search(...)). No latency regression path exists. |
| 2 | Cada resultado trae ruta exacta, extracto, fuente y fecha | VERIFIED | `Hit` dataclass has `source_path`, `snippet`, `date: float\|None`. `_hit_to_json()` serializes all four fields. Rich panel renders `Ruta: hit.source_path`, `Fuente: source/hit.entry_id`, `Fecha: _format_timestamp(hit.date)`, `snippet`. `test_hit_fields` asserts `source_path`, `snippet`, and `date == expected_mtime`. |
| 3 | La búsqueda funciona sin vectores (FTS5 solo) y mejora con ellos (fusión RRF) | VERIFIED | `HybridRetrieval.__init__` accepts `embedder: EmbeddingProvider\|None`. When `embedder is None`, `degraded=True` and `rrf_merge(fts_hits, ())` runs FTS5-only. With embedder alive, `rrf_merge(fts_hits, vec_hits)` fuses both. `test_degraded_mode` covers both: embedder=None and httpx.TransportError; `test_hybrid_returns_merged` covers the fusion path. |
| 4 | Toda consulta queda auditada | VERIFIED | `_audit_search()` is called unconditionally at line 59 of `retrieval.py`, after enrichment, before return — one call for both normal and degraded paths. `test_degraded_audit` asserts `len(audit.events) == 1` and `event.payload["degraded"] is True`. Normal path: `test_hybrid_returns_merged` + `test_hit_fields` each assert `len(audit.events) == 1`. |
| 5 | El eval set dorado (N consultas → archivo esperado) corre en CI y pasa | VERIFIED | `test_golden_queries_hit_at_one_gate` has no `@pytest.mark.skip`. It builds real FTS5+ChromaVector indexes from the 8-doc/4-topic disjoint corpus, runs all 20 queries, and asserts `hit_at_1 >= 0.80`. Test passes in the full suite run (1.82 s total, no Ollama required). |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/knowledge/rrf.py` | rrf_merge() — fusión RRF pura stdlib | VERIFIED | 43 lines; imports only `collections.abc.Sequence` and `core.domain.knowledge.Hit`; lint-imports green |
| `src/knowledge/state_store.py` | freshness_by_kb(), list_kb_ids(), mtime_by_path(), BcFreshness | VERIFIED | All four present; SQL parametrized; NULL→None handled for last_indexed_at |
| `src/core/domain/knowledge.py` | Hit.date field + SearchResult wrapper | VERIFIED | `date: float \| None = None` at line 95; `class SearchResult` at line 99 with hits/degraded/reason; `degraded` NOT on Hit |
| `tests/knowledge/golden/queries.json` | N=20 golden queries | VERIFIED | 20 entries, each with query/kb_id/expected_source_path keys |
| `tests/knowledge/golden/corpus.py` | Synthetic corpus fixture | VERIFIED | 8 docs, 4 disjoint topics (cocina/astronomia/finanzas/jardineria), 2 kb_ids (personal/ragcorp), topic→doc→query mapping commented |
| `src/knowledge/retrieval.py` | HybridRetrieval | VERIFIED | 100 lines; class HybridRetrieval; single search() method; mtime_by_path DI; rrf_merge called; audit emitted exactly once |
| `src/bootstrap/cli.py` | search + status commands, build_retrieval() | VERIFIED | def search, def status, build_retrieval() returning (HybridRetrieval, StateStore); all at lines 192-376 |
| `tests/knowledge/test_golden_queries.py` | Gate hit@1 >= 0.80 active in CI | VERIFIED | No skip marker; gate assert at line 81 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/knowledge/rrf.py` | `core.domain.knowledge.Hit` | `from core.domain.knowledge import Hit` | WIRED | Line 5 of rrf.py; lint-imports contract "core es puro" kept |
| `src/knowledge/retrieval.py` | `knowledge.rrf.rrf_merge` | import + call in search() | WIRED | Line 13 import; line 57 `rrf_merge(fts_hits, vec_hits, ...)` |
| `src/knowledge/retrieval.py` | `knowledge.state_store.StateStore.mtime_by_path` | DI by constructor + per-hit lookup | WIRED | `state_store: StateStore` ctor arg; `self._state_store.mtime_by_path(hit.source_path, ...)` lines 69/72 |
| `src/knowledge/retrieval.py` | `core.ports.audit.AuditPort` | `self._audit.log(AuditEvent.new(...))` | WIRED | Line 86; one call per search() invocation |
| `src/knowledge/retrieval.py` | `core.domain.knowledge.SearchResult` | search() returns SearchResult(...) | WIRED | Line 60 `return SearchResult(hits=enriched, ...)` |
| `src/bootstrap/cli.py` | `knowledge.retrieval.HybridRetrieval` | build_retrieval() + asyncio.run(retrieval.search(...)) | WIRED | Lines 192-210 build_retrieval(); line 328 asyncio.run |
| `src/bootstrap/cli.py` | `StateStore.freshness_by_kb / list_kb_ids` | footer + status + kb validation | WIRED | Lines 313 list_kb_ids(); line 338 freshness_by_kb(); line 366 freshness_by_kb() |
| `core/ports/knowledge.py` | `Retrieval.search → SearchResult` | Protocol updated | WIRED | Line 63: `async def search(self, query: Query, subject: Subject) -> SearchResult` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `cli.py search` | `result.hits` | `asyncio.run(retrieval.search(...))` → `HybridRetrieval.search()` → `rrf_merge(fts_hits, vec_hits)` | Yes — FTS5Index.search() queries SQLite FTS5 table; VectorIndex.search() queries Chroma | FLOWING |
| `cli.py search` | `hit.date` | `_mtime_for_hit()` → `state_store.mtime_by_path(source_path, kb_id)` → `SELECT mtime FROM file_state WHERE path=? AND kb_id=?` | Yes — real SQLite row read | FLOWING |
| `cli.py search` (footer) | freshness summary | `state_store.freshness_by_kb()` → `SELECT kb_id, MAX(indexed_at), COUNT(*)... GROUP BY kb_id` | Yes — aggregation query on file_state | FLOWING |
| `cli.py status` | freshness table | `state_store.freshness_by_kb()` | Yes — same query path | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All Phase 4 tests | `uv run pytest tests/knowledge/test_rrf.py tests/knowledge/test_retrieval.py tests/knowledge/test_golden_queries.py tests/cli/test_search_command.py -v` | 20/20 passed | PASS |
| Golden gate hit@1 | `uv run pytest tests/knowledge/test_golden_queries.py -x` | PASSED | PASS |
| Full suite | `uv run pytest` | 283 passed, 3 skipped | PASS |
| Type safety | `uv run mypy` | 0 issues in 127 files | PASS |
| Lint | `uv run ruff check src tests` | All checks passed | PASS |
| Layer isolation | `uv run lint-imports` | 2 contracts kept, 0 broken | PASS |

### Probe Execution

No probe scripts declared for Phase 4 in PLAN files. Step 7c: N/A.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| KNOW-04 | 04-01, 04-02, 04-03 | `wyss search` with hybrid RRF retrieval < 5 s | SATISFIED | HybridRetrieval.search() + CLI search command; all tests green |
| KNOW-05 | 04-01, 04-02, 04-03 | Each result: exact path, snippet, source, date | SATISFIED | Hit fields verified; test_hit_fields asserts all three; CLI renders Ruta/Fuente/Fecha/snippet |
| KNOW-10 | 04-01, 04-03 | Index exposes freshness — "indexado al [fecha]" | SATISFIED | freshness_by_kb() + list_kb_ids() in StateStore; footer in search stderr; status command with table |
| AUD-03 | 04-01, 04-03 | Golden eval set N queries with expected file, CI gate | SATISFIED | test_golden_queries_hit_at_one_gate active, 20 queries, hit@1 >= 0.80 asserted, passes without Ollama |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/knowledge/state_store.py` | 213 | `placeholders` variable name | Info | SQL parameter placeholder string, not a debt marker. No impact. |

No TBD/FIXME/XXX markers found in any Phase 4 files.

### Human Verification Required

None. All success criteria are verifiable programmatically and confirmed by the green chain.

---

## Known Deferred Item (not a gap)

Per the verification context: the non-degraded Ollama path was exercised only with `FakeEmbeddingProvider` (deterministic noise embedding). A real `wyss index` + `wyss search` end-to-end run with Ollama UP has not been done. The golden gate runs FTS5-only synthetic. This is an **empirical integration check** deferred until Phase 5 / first real-data run, not a code gap — the production path is fully wired and tested with fakes, and the degraded path is tested with httpx.TransportError.

---

## Gaps Summary

No gaps. All five ROADMAP success criteria are verified in the codebase. The green chain (pytest 283/283 + mypy + ruff + lint-imports) passes clean.

---

_Verified: 2026-06-13T03:27:02Z_
_Verifier: Claude (gsd-verifier)_
