---
phase: 04-b-squeda-h-brida
plan: 02
subsystem: knowledge
tags: [retrieval, rrf, fts5, vector-search, audit, state-store]

requires:
  - phase: 04-b-squeda-h-brida
    provides: rrf_merge, Hit.date, SearchResult, StateStore.mtime_by_path, retrieval test scaffolds
provides:
  - HybridRetrieval service implementing the Retrieval port with a single SearchResult-returning search method
  - RRF fusion of FTS5 and vector hits with over-fetch before limit trim
  - D-44 degraded FTS5-only search path for missing/unavailable embedder
  - Hit.date enrichment from StateStore.mtime_by_path
  - Exactly one AuditEvent per search, including degraded searches
affects: [phase-04-cli-search, phase-05-orchestrator, knowledge-retrieval]

tech-stack:
  added: []
  patterns: [keyword-only dependency injection, query-level degradation metadata, audit-once retrieval]

key-files:
  created:
    - src/knowledge/retrieval.py
  modified:
    - tests/knowledge/test_retrieval.py

key-decisions:
  - "StateStore remains a mandatory keyword-only dependency of HybridRetrieval; the service opens no SQLite connections itself."
  - "Degradation lives only on SearchResult, not on individual Hit objects."
  - "The exact required `(httpx.HTTPError, httpx.TransportError)` catch tuple was kept."

patterns-established:
  - "HybridRetrieval composes ports and StateStore through constructor DI only."
  - "Search audit payload includes degraded, reason, sorted kb_ids, and result_count."
  - "Date enrichment reconstructs frozen Hit objects via dataclasses.replace."

requirements-completed: [KNOW-04, KNOW-05]

duration: ~25min
completed: 2026-06-13T03:15:17Z
---

# Phase 4: Hybrid Retrieval Summary

**HybridRetrieval now provides audited FTS5 + vector RRF search with D-44 FTS5-only degradation and mtime-backed result dates.**

## What was built
- Added `HybridRetrieval` in `src/knowledge/retrieval.py`.
- `search()` is the only retrieval method and returns `SearchResult(hits, degraded, reason)`.
- Normal path searches FTS5 and vectors, over-fetches `limit * 3`, fuses with `rrf_merge()`, trims to the query limit, enriches each `Hit.date` from `StateStore.mtime_by_path()`, and audits once.
- Degraded path handles `embedder=None` and `(httpx.HTTPError, httpx.TransportError)` by returning FTS5-only results with `degraded=True` and a non-empty reason, without raising.
- Activated the Wave 0 retrieval tests for merged results, degraded mode, hit fields, and degraded audit behavior.

## Key Files Created/Modified
- `src/knowledge/retrieval.py` - New `HybridRetrieval` service with RRF fusion, D-44 fallback, mtime enrichment, and audit emission.
- `tests/knowledge/test_retrieval.py` - Replaced Wave 2 skipped stubs with async tests and local fakes covering the required behaviors.

## Decisions / Deviations
- No architecture or scope deviations.
- The existing `Retrieval` port already returned `SearchResult` from plan 04-01, so no port edit was needed in this plan.
- Used local test fakes for deterministic RRF/degradation assertions instead of real FTS5/Chroma wiring; this keeps the tests focused on service behavior.
- Used `UV_CACHE_DIR=/tmp/uv-cache` for all `uv` commands.

## Verification
- `uv run pytest tests/knowledge/test_retrieval.py -x` - PASSED, 6 passed.
- `uv run pytest tests/knowledge/test_retrieval.py::test_hybrid_returns_merged -x` - PASSED.
- `uv run pytest tests/knowledge/test_retrieval.py::test_degraded_mode -x` - PASSED.
- `uv run pytest tests/knowledge/test_retrieval.py::test_hit_fields -x` - PASSED.
- `uv run pytest tests/knowledge/test_retrieval.py::test_degraded_audit -x` - PASSED.
- Acceptance source checks passed: `class HybridRetrieval`, `state_store: StateStore`, `mtime_by_path`, `rrf_merge`, `SearchResult`, and `self._audit.log` are present; `search_with_meta` is absent.

## Self-Check: PASSED

Green chain result: `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports` passed.

- `pytest`: 277 passed, 7 skipped.
- `mypy`: Success, no issues in 127 source files.
- `ruff`: All checks passed.
- `lint-imports`: 2 contracts kept, 0 broken.
