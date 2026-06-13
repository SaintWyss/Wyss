---
phase: 04-b-squeda-h-brida
plan: 03
subsystem: knowledge-cli
tags: [typer, rich, fts5, chromadb, rrf, golden-gate]
requires:
  - phase: 04-b-squeda-h-brida-01
    provides: rrf_merge, Hit.date, SearchResult, StateStore freshness APIs, golden corpus
  - phase: 04-b-squeda-h-brida-02
    provides: HybridRetrieval search service with degradation and audit
provides:
  - wyss search CLI command with Rich and pure JSON output modes
  - wyss status freshness table by knowledge base
  - build_retrieval composition root returning HybridRetrieval and StateStore
  - active golden retrieval gate hit@1 >= 0.80
affects: [phase-05-orchestrator, knowledge-retrieval, cli]
tech-stack:
  added: []
  patterns: [Typer command DI, stderr diagnostics for JSON purity, synthetic golden retrieval gate]
key-files:
  created:
    - .planning/phases/04-b-squeda-h-brida/04-03-SUMMARY.md
  modified:
    - src/bootstrap/cli.py
    - tests/cli/test_search_command.py
    - tests/knowledge/test_golden_queries.py
key-decisions:
  - "D-43 JSON stdout is a pure array of hit objects; degraded banner and freshness footer are stderr-only."
  - "build_retrieval returns (HybridRetrieval, StateStore) so the CLI owns freshness reads and closure."
  - "Golden gate uses real FTS5 and Chroma adapters with FakeEmbeddingProvider; no Ollama dependency."
requirements-completed: [KNOW-04, KNOW-05, KNOW-10, AUD-03]
completed: 2026-06-13
---

# Phase 04-03 Summary

**Hybrid retrieval is now wired into the owner CLI with JSON-safe search output, freshness status, and an active CI golden gate.**

## Accomplishments
- Added `wyss search` with `--kb`, `--limit`, `--json`, `--fts-only`, auto-JSON for pipes, Rich Panels for TTY, degraded banner on stderr, and freshness footer on stderr.
- Added `wyss status` with per-BC freshness, total files, embedded, pending, and failed counts.
- Added `build_retrieval(settings, *, audit, embedder) -> tuple[HybridRetrieval, StateStore]` using real `FTS5Index` and `ChromaVectorIndex`.
- Activated CLI tests for JSON purity, Rich output, unknown KB validation, degraded exit code 0, and status output.
- Activated `tests/knowledge/test_golden_queries.py` as a deterministic CI gate; result: hit@1 = 20/20 (1.00), above the 0.80 threshold.

## Files Created/Modified
- `src/bootstrap/cli.py` - Search/status commands, retrieval composition root, stderr diagnostics, freshness formatting, JSON hit serialization.
- `tests/cli/test_search_command.py` - Active command tests using fake retrieval and fake state store.
- `tests/knowledge/test_golden_queries.py` - Active golden gate using synthetic corpus, real indexes, fake embeddings, and `HybridRetrieval`.
- `.planning/phases/04-b-squeda-h-brida/04-03-SUMMARY.md` - This summary.

## Decisions / Deviations
- No new dependencies were added.
- No commits or staging were performed, per instruction.
- The test environment’s `CliRunner` does not support `mix_stderr`; tests use the available separate `result.stdout` / `result.stderr` capture instead.
- A small `_stdout_is_tty()` helper was added so Rich/JSON auto-detection remains production-equivalent and testable.
- Noop indexes remain scoped to `_build_preview_pipeline`; `build_retrieval` uses only real indexes.

## Self-Check: PASSED
- `uv run pytest tests/cli/test_search_command.py tests/knowledge/test_golden_queries.py -x` - PASSED, 6 passed.
- `uv run pytest` - PASSED, 283 passed, 3 skipped.
- `uv run mypy` - PASSED, no issues in 127 source files.
- `uv run ruff check src tests` - PASSED.
- `uv run lint-imports` - PASSED, 2 contracts kept, 0 broken.
- Full required chain `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports` - PASSED.
- Golden gate `tests/knowledge/test_golden_queries.py` - PASSED, hit@1 = 20/20 (1.00).
