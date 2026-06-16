---
plan: 07-03
status: complete
---

Built the Pydantic-to-domain agent config boundary for D-73 / AGENT-02:

- `src/core/domain/config.py`: added `WyssSettings.agents: tuple[AgentDefinition, ...] = ()`, preserving construction without agents and keeping the domain config frozen.
- `src/bootstrap/config.py`: added `AgentConfigModel` with `extra="forbid"`, wired `WyssConfigModel.agents`, and added `_to_agent_definition()` so `[[agents]]` entries become frozen `AgentDefinition` values.
- `src/bootstrap/config.py`: mapped `knowledge_bases` to `AgentDefinition.kb_ids` via `frozenset(...)`, `model_tier` to `model_alias`, and preserved defaults `model_tier="economico"`, `budget_usd=0.0`, `knowledge_bases=[]`.
- `.planning/phases/07-modelo-de-agentes/07-03-SUMMARY.md`: recorded this execution summary.

Verification:

- `UV_CACHE_DIR=/tmp/uv-cache MYPY_CACHE_DIR=/tmp/mypy-cache uv run pytest tests/bootstrap/test_agent_config.py tests/bootstrap/test_config.py -x -q` -> `11 passed`
- `UV_CACHE_DIR=/tmp/uv-cache MYPY_CACHE_DIR=/tmp/mypy-cache uv run pytest tests/bootstrap/ -q` -> `19 passed`
- `UV_CACHE_DIR=/tmp/uv-cache MYPY_CACHE_DIR=/tmp/mypy-cache uv run mypy src/bootstrap/config.py src/core/domain/config.py` -> success
- `UV_CACHE_DIR=/tmp/uv-cache MYPY_CACHE_DIR=/tmp/mypy-cache uv run pytest tests/agents/test_memory.py tests/agents/test_permission_store.py tests/agents/test_scoped_retrieval.py -q` -> `5 passed`
- `UV_CACHE_DIR=/tmp/uv-cache MYPY_CACHE_DIR=/tmp/mypy-cache uv run mypy src/agents` -> success
- `UV_CACHE_DIR=/tmp/uv-cache MYPY_CACHE_DIR=/tmp/mypy-cache uv run lint-imports` -> contracts kept

Note: `uv` cache writes were redirected to `/tmp` because the sandbox exposes the default home cache as read-only.
