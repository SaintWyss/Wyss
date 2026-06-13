---
phase: 06-capa-de-ejecuci-n
plan: "03"
subsystem: execution-adapters
tags: [shell-adapter, git-adapter, allowlist, argv-exec, tool-port, d-66, exec-01]
dependency_graph:
  requires: [06-01]
  provides: [ShellAdapter, GitAdapter, AllowlistViolation]
  affects: [src/execution/shell.py, src/execution/git.py, src/core/domain/errors.py]
tech_stack:
  added: []
  patterns:
    - asyncio.create_subprocess_exec con shell=False (D-66, T-shell-injection)
    - Allowlist fail-closed con audit event (T-06-ALLOW-1)
    - asyncio.wait_for + proc.kill() + drain communicate() anti-zombie (T-06-ALLOW-2)
    - cast(Sequence[object], ...) para Mapping[str, object] -> iterable en mypy strict
key_files:
  created:
    - src/execution/shell.py
    - src/execution/git.py
    - tests/execution/test_shell.py
    - tests/execution/test_git.py
  modified:
    - src/core/domain/errors.py
decisions:
  - "action.target = binario/subcomando; action.parameters['args'] = lista de argumentos (taxonomía Action)"
  - "ShellAdapter y GitAdapter son independientes (no shared helper module) para mantener simplicidad y claridad de imports"
  - "GitAdapter cachea shutil.which('git') en primer uso (lazy resolve)"
  - "AllowlistViolation no se levanta en execute(); se captura internamente y se retorna como ToolResult(success=False) — el caller no necesita try/except para el caso bloqueado"
  - "AST-based shell=True test (no grep de texto) — evita falsos positivos en docstrings"
metrics:
  duration: "~20 min"
  completed: "2026-06-13"
  tasks: 2
  files: 5
---

# Phase 06 Plan 03: ShellAdapter + GitAdapter Summary

ShellAdapter y GitAdapter implementando el puerto Tool con allowlist fail-closed y argv exec (asyncio.create_subprocess_exec, shell=False siempre) conforme a D-66/EXEC-01.

## Tasks Completed

| Task | Name | Commits | Files |
|------|------|---------|-------|
| 1 | ShellAdapter + AllowlistViolation | RED: 22f2585, GREEN: 1a49912 | src/execution/shell.py, src/core/domain/errors.py, tests/execution/test_shell.py |
| 2 | GitAdapter | RED: 0979f85, GREEN: b695192 | src/execution/git.py, tests/execution/test_git.py |

## What Was Built

### `src/core/domain/errors.py` — AllowlistViolation

Nueva clase de error `AllowlistViolation(WyssError)` appended al final del archivo siguiendo el patrón existente. Constructor toma solo el nombre del binario/subcomando (nunca los argumentos — que podrían contener datos sensibles). Usada internamente por los adapters; el caller recibe `ToolResult(success=False)` sin necesidad de try/except.

### `src/execution/shell.py` — ShellAdapter

- Implementa `Tool` protocol: `name="shell"`, `max_risk=RiskLevel.B`
- `execute()`: extrae `binary = action.target`, `args = action.parameters["args"]`
- Allowlist check fail-closed: si `binary ∉ allowed_binaries` → `AuditEvent(ACTION_COMPLETED, payload={"blocked":"allowlist","binary":...})` + `ToolResult(success=False)`, sin spawn
- `_exec_allowed()`: `shutil.which(binary)` → `asyncio.create_subprocess_exec(resolved, *args, stdout=PIPE, stderr=PIPE)` → `asyncio.wait_for(communicate(), timeout)` → en `TimeoutError`: `proc.kill()` + `await proc.communicate()` (drain)
- `verify()`: `passed = result.success and returncode == 0`
- Constructor acepta `allowed_binaries: set[str]` (tests) o `config_path` TOML (prod)
- `cast(Sequence[object], ...)` para iterar `Mapping[str, object]` en mypy strict

### `src/execution/git.py` — GitAdapter

- Implementa `Tool` protocol: `name="git"`, `max_risk=RiskLevel.B`
- `execute()`: extrae `subcommand = action.target`, `args = action.parameters["args"]`
- Allowlist check fail-closed: si `subcommand ∉ allowed_subcommands` → mismo patrón de audit + `ToolResult(success=False)`
- `_exec_git()`: `asyncio.create_subprocess_exec(git, subcommand, *args, cwd=repo_path)` — mismo patrón de timeout/kill/drain
- Default allowlist: `{"status", "diff", "add", "commit", "log"}`
- No GitPython — invoca `git` CLI directamente (solo stdlib + `core.*`)
- Resolución lazy de `shutil.which("git")` cacheada

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test grep de `shell=True` fallaba en docstrings**
- **Found during:** Task 1 GREEN (primer run pytest)
- **Issue:** El test original usaba `line.lstrip().startswith("#")` para excluir comentarios, pero las docstrings que mencionan `shell=True` como texto no comienzan con `#`. Dos líneas de docstring de shell.py causaban fallo falso positivo.
- **Fix:** Reemplazado por verificación AST (`ast.walk` sobre `ast.Call` buscando `kw.arg == "shell"` con valor `True`). Solo detecta `shell=True` como keyword argument real en una llamada — no menciones en strings/docstrings. El test de Task 2 fue escrito directamente con el patrón AST correcto.
- **Files modified:** tests/execution/test_shell.py (líneas 155-175)
- **Commit:** 1a49912 (incluido en el commit GREEN de Task 1)

## Threat Surface Scan

No se introdujeron nuevas superficies de red, rutas de auth, ni acceso a archivos fuera de los declarados en el `<threat_model>` del plan. Las mitigaciones T-shell-injection, T-06-ALLOW-1 y T-06-ALLOW-2 están implementadas y cubiertas por tests.

## Verification Results

```
uv run pytest tests/execution/test_shell.py tests/execution/test_git.py -q
15 passed in 0.09s

grep check: shell.py -> 0 (sin shell=True en código)
grep check: git.py  -> 0 (sin shell=True en código)

uv run lint-imports
Contracts: 2 kept, 0 broken.

uv run mypy src/execution/shell.py src/execution/git.py
Success: no issues found in 2 source files
```

## Self-Check: PASSED

- [x] src/execution/shell.py exists
- [x] src/execution/git.py exists
- [x] src/core/domain/errors.py has AllowlistViolation
- [x] tests/execution/test_shell.py exists (8 tests)
- [x] tests/execution/test_git.py exists (7 tests)
- [x] Commits: 22f2585, 1a49912, 0979f85, b695192 all present
