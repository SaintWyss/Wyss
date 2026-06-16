---
plan: 07-05
status: complete
---

Implementado:
- `src/agents/registry.py`: `AgentRegistry` config-driven que materializa cada `AgentDefinition` en un `ConfiguredAgent`, inyectando gateway, tools, audit, engine, plan runner, retrieval factory y memory factory. `get()` devuelve el agente o levanta `KeyError("agente '<id>' no registrado")`.
- `src/agents/__init__.py`: exports publicos de `AgentMemory`, `AgentRegistry`, `ConfiguredAgent`, `PermissionDenied`, `SQLitePermissionStore` y `ScopedRetrieval`.
- `tests/ports/test_conformance.py`: conformance de `SQLitePermissionStore` contra `PermissionStore` y de `ScopedRetrieval` contra `Retrieval`.
- Limpieza de ignores/anotaciones en tests de agentes/bootstrap necesaria para que `mypy src tests` vuelva a pasar con `strict`.

Verificacion:
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/agents/test_registry.py -x -q && UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/agents/registry.py && UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports`: PASS (`2 passed`; mypy ok; import-linter ok).
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/ports/test_conformance.py -x -q && UV_CACHE_DIR=/tmp/uv-cache uv run python -c "import agents; assert all(hasattr(agents,n) for n in ['ConfiguredAgent','AgentRegistry','ScopedRetrieval','AgentMemory','SQLitePermissionStore','PermissionDenied']); print('exports ok')" && UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports`: PASS (`18 passed`; exports ok; import-linter ok).
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/agents tests/ports/test_conformance.py -q`: PASS (`31 passed`).
- `UV_CACHE_DIR=/tmp/uv-cache uv run mypy src tests && UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests && UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports`: PASS.

Bloqueo reportado por Codex — descartado en el cierre (orquestador, Opus 4.8):
- Codex marcó `blocked` por un fallo en `tests/execution/test_shell.py::test_allowed_binary_executes` (`ShellAdapter` timeout 5.0s ejecutando `echo`), fuera del alcance de 07-05.
- No reproducible: en el cierre el full suite quedó verde — `399 passed, 6 skipped, 0 failed`; el test aislado pasó 3/3. Fue un timeout transitorio (echo bajo carga / cache frío), no una regresión.
- Cadena de cierre verde verificada por el orquestador: `pytest` (399 passed), `mypy src tests` (174 files), `ruff check src tests`, `lint-imports` (2 contratos), y los 6 exports de `agents`.
