---
phase: 03-pipeline-de-ingesta
plan: 03-07
status: complete
requirements_covered:
  - KNOW-01
  - KNOW-08
  - KNOW-09
  - KNOW-11
---

# Plan 03-07 Summary

**One-liner:** Se construyo el comando `wyss index <ruta>` con composition root real del pipeline, modos `--estimate`/`--dry-run`, seleccion de BC, progreso y exit codes D-38.

## What was built
Task 1: `src/bootstrap/cli.py` agrega `app` Typer, comando `index`, y `build_pipeline()` como composition root manual. Cablea `StateStore`, `FTS5Index` sobre la misma conexion, `Scanner`, `ExtractorRegistry` con los 6 extractores, `TokenChunker`, `chromadb.PersistentClient` -> `ChromaVectorIndex`, `OllamaEmbeddingProvider` via `httpx.AsyncClient`, `SqliteAuditLogger`, y `SecretFilter` con `BUILTIN_SECRET_PATTERNS` importado desde `gateway` e inyectado desde bootstrap.

Task 1 tambien agrega `[project.scripts] wyss = "bootstrap.cli:app"` en `pyproject.toml`. El comando muestra el `kb_id`, usa Rich cuando stdout es TTY, degrada a lineas `progreso:` en no-interactiva, imprime resumen final de indexados/fallados/excluidos/skipped, y sale 0 cuando la corrida completa aunque haya archivos fallados.

Task 2: `tests/cli/test_index_command.py` cubre los 6 comportamientos pedidos: estimate sin crear `index.db`, dry-run sin escribir, `--bc` visible en output, exit 0 con fallos por archivo, exit no-cero ante error sistemico, y modo de progreso no-interactivo. Se agrego un smoke opt-in con `WYSS_TEST_OLLAMA=1`.

Task 2 tambien actualiza `.planning/phases/03-pipeline-de-ingesta/03-VALIDATION.md`: `nyquist_compliant: true`, mapa de verificacion por tarea y sign-off de validacion.

## Key files
### Created
- `src/bootstrap/cli.py` - CLI Typer + composition root `build_pipeline()`.
- `tests/cli/test_index_command.py` - cobertura CLI con `CliRunner`.
- `.planning/phases/03-pipeline-de-ingesta/03-07-SUMMARY.md` - resumen de ejecucion del plan.

### Modified
- `pyproject.toml` - entry point `wyss = "bootstrap.cli:app"`.
- `.planning/phases/03-pipeline-de-ingesta/03-VALIDATION.md` - mapa de verificacion y `nyquist_compliant: true`.

## Deviations From Plan
- `--estimate` y `--dry-run` usan adapters preview no persistentes en bootstrap. Esto evita crear `index.db`, cumpliendo el criterio literal de no escribir/tocar estado; el composition root real queda en `build_pipeline()` para corridas de indexacion.
- `uv sync` fue intentado con `UV_CACHE_DIR=/tmp/uv-cache`, pero no pudo completar porque el sandbox no tiene red y `hatchling` no estaba en cache. La verificacion se ejecuto con `uv run --no-sync` contra el entorno existente.

## Verification Evidence
Command:
```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync
```

Output:
```text
Resolved 102 packages in 0.98ms
Building wyss @ file:///mnt/hdd/Data/10_Workspace/projects/wyss
Failed to resolve requirements from build-system.requires: hatchling
Failed to fetch: https://pypi.org/simple/hatchling/
dns error: Temporary failure in name resolution
```

Command:
```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync --offline
```

Output:
```text
Because hatchling was not found in the cache and you require hatchling,
we can conclude that your requirements are unsatisfiable.
```

Command:
```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest tests/cli/test_index_command.py -x -q
```

Output:
```text
6 passed, 1 skipped in 1.01s
```

Command:
```bash
UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync python -c "from bootstrap.cli import app, build_pipeline; print('ok')" && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync pytest -q && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync mypy && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync ruff check src tests && UV_CACHE_DIR=/tmp/uv-cache uv run --no-sync lint-imports
```

Output:
```text
ok
259 passed, 3 skipped in 1.63s
Success: no issues found in 117 source files
All checks passed!
Contracts: 2 kept, 0 broken.
```

## Acceptance Coverage
- `from bootstrap.cli import app, build_pipeline` importa sin error.
- `src/bootstrap/cli.py` importa `BUILTIN_SECRET_PATTERNS` desde `gateway.secrets_patterns` y lo inyecta a `SecretFilter(builtin_patterns=...)`; `knowledge` no importa `gateway`.
- `[project.scripts]` contiene `wyss = "bootstrap.cli:app"`.
- `test_estimate_no_extraction`: exit 0, output con `archivos`/`chunks`, sin crear `index.db`.
- `test_dry_run_lists`: `--dry-run` lista `nuevo:` y no crea `index.db`.
- `test_kb_id_in_output`: `--bc beca` aparece en el output.
- `test_exit_code_zero_with_failures`: corrida con fallados termina con exit 0.
- `test_exit_code_nonzero_on_systemic`: ruta inexistente termina con exit no-cero y mensaje legible.
- `test_progress_modes`: en no-interactiva se emiten lineas de progreso en vez de barra Rich.
- `lint-imports` verde: el independence contract sigue intacto.
