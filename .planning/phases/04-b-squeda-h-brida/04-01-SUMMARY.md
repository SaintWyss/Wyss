## What was built
Implemented the Phase 4 base layer and Wave 0 scaffolds: `Hit` now carries additive source `date`, `SearchResult` is the query-level retrieval wrapper, the `Retrieval` port and fake return that wrapper, `rrf_merge()` provides pure stdlib Reciprocal Rank Fusion, and `StateStore` exposes BC freshness, distinct KB listing, and source mtime lookup. Added the golden corpus fixture with 8 documents across 4 disjoint topics and 20 golden queries, plus the requested real/stub tests for RRF, freshness, retrieval, golden evaluation, and search/status CLI scaffolding.

## key-files.created
- `/mnt/hdd/Data/10_Workspace/projects/wyss/src/knowledge/rrf.py`
- `/mnt/hdd/Data/10_Workspace/projects/wyss/tests/knowledge/test_rrf.py`
- `/mnt/hdd/Data/10_Workspace/projects/wyss/tests/knowledge/test_retrieval.py`
- `/mnt/hdd/Data/10_Workspace/projects/wyss/tests/knowledge/test_golden_queries.py`
- `/mnt/hdd/Data/10_Workspace/projects/wyss/tests/knowledge/golden/__init__.py`
- `/mnt/hdd/Data/10_Workspace/projects/wyss/tests/knowledge/golden/corpus.py`
- `/mnt/hdd/Data/10_Workspace/projects/wyss/tests/knowledge/golden/queries.json`
- `/mnt/hdd/Data/10_Workspace/projects/wyss/tests/cli/test_search_command.py`
- `/mnt/hdd/Data/10_Workspace/projects/wyss/.planning/phases/04-b-squeda-h-brida/04-01-SUMMARY.md`

## key-files.modified
- `/mnt/hdd/Data/10_Workspace/projects/wyss/src/core/domain/knowledge.py`
- `/mnt/hdd/Data/10_Workspace/projects/wyss/src/core/domain/__init__.py`
- `/mnt/hdd/Data/10_Workspace/projects/wyss/src/core/ports/knowledge.py`
- `/mnt/hdd/Data/10_Workspace/projects/wyss/src/knowledge/state_store.py`
- `/mnt/hdd/Data/10_Workspace/projects/wyss/tests/ports/fakes.py`

## Decisions / deviations from the plan
- Updated `Retrieval.search()` and `FakeRetrieval.search()` to return `SearchResult`, because the plan defines `SearchResult(hits, degraded, reason)` as the unique retrieval return contract.
- Used `UV_CACHE_DIR=/tmp/uv-cache` for `uv` commands because the sandbox cannot write to the default home cache. No package installs or network IO were added.

## Self-Check: PASSED — `uv run pytest` 273 passed, 11 skipped; `uv run mypy` clean; `uv run ruff check src tests` clean; `uv run lint-imports` kept both contracts.
