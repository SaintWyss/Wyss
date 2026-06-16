---
plan: 07-05
status: blocked
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

Bloqueo:
- El phase gate literal `UV_CACHE_DIR=/tmp/uv-cache uv run pytest && ...` no queda verde porque `pytest` falla de forma reproducible en `tests/execution/test_shell.py::test_allowed_binary_executes`, fuera del alcance de 07-05: `ShellAdapter` retorna `ToolResult(success=False, detail="timeout (5.0s) ejecutando 'echo'", payload={'returncode': -1, 'stdout': '', 'stderr': 'timeout'})`.
- Repro aislado: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/execution/test_shell.py::test_allowed_binary_executes -q -vv` falla igual. Un script directo fuera de pytest con el mismo `ShellAdapter` y `echo` retorna `success=True`, por lo que el bloqueo parece estar en la interaccion pytest/asyncio subprocess de la suite de execution, no en los cambios de agentes.
- En el intento de full suite previo al corte: `398 passed, 6 skipped, 1 failed`.
