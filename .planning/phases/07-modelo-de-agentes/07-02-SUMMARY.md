---
plan: 07-02
status: complete
---

Built the Wave 1 agent runtime pieces:

- `src/agents/memory.py`: added `AgentMemory` with read-only `load()` fallback template and the single supervised markdown write path `write_supervised()` for D-71.
- `src/agents/permission_store.py`: added `SQLitePermissionStore` implementing `grants_for/save/revoke` with SQLite stdlib persistence, WAL, ISO datetime roundtrip, and revocation timestamps.
- `src/agents/scoped_retrieval.py`: added `ScopedRetrieval` and `PermissionDenied`; permissions are checked per query with no cache, revoked grants are denied, unauthorized KBs are audited as `POLICY_DECISION` before inner retrieval.
- `tests/agents/test_permission_store.py`: added roundtrip coverage for save, grants lookup, and revoke.
- `src/core/domain/knowledge.py`: gave `Query.limit` a default of `5` so existing agent tests can instantiate `Query` with only text and `kb_ids`.

Verification:

- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/agents/test_memory.py tests/agents/test_permission_store.py tests/agents/test_scoped_retrieval.py -q` → `5 passed`
- `UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/agents` → success
- `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` → contracts kept
