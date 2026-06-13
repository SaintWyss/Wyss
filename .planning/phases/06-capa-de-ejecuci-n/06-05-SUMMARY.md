---
phase: 06-capa-de-ejecuci-n
plan: "05"
subsystem: execution
tags: [executor, step-loop, on_error, rollback, retry, escalate, tdd]
dependency_graph:
  requires: [06-02, 06-03, 06-04]
  provides: [PlanExecutor, execution-package-exports]
  affects: [05-dispatcher, phase-07+]
tech_stack:
  added: []
  patterns:
    - TDD RED/GREEN en executor.py
    - _retry_with_backoff con backoff exponencial capped (asyncio.sleep)
    - reversed(applied_entry_ids) para ABORT rollback en orden inverso
    - ErrorPolicy.RETRY pre-ejecutado en run() (no duplicado en _handle_failure)
    - TYPE_CHECKING para forward refs de adapters en tests
key_files:
  created:
    - src/execution/executor.py
    - tests/execution/test_executor.py
  modified:
    - src/execution/__init__.py
    - src/execution/filesystem.py
    - src/execution/shell.py
    - src/execution/git.py
    - tests/execution/test_filesystem.py
    - tests/execution/test_git.py
    - tests/execution/test_journal.py
    - tests/execution/test_second_wall.py
    - tests/execution/test_shell.py
decisions:
  - "RETRY pre-ejecutado en run() via _retry_with_backoff: el primer intento cuenta como parte del loop de max_attempts, no ejecuta adicionalmente en _handle_failure — evita N+1 llamadas a execute"
  - "ExecutorResult dataclass frozen: success, detail, applied_entries (tuple), failed_step — informa al caller qué entries quedaron aplicadas y dónde falló"
  - "_handle_failure con ErrorPolicy.RETRY terminal: si llega ahí, el backoff ya se agotó — tratar como ABORT sin re-loop"
metrics:
  duration: ~10m
  completed: 2026-06-13
  tasks_completed: 2
  files_created: 2
  files_modified: 9
---

# Phase 06 Plan 05: PlanExecutor — Step Loop + on_error Enforcement Summary

**One-liner:** PlanExecutor con dispatch por prefijo, verify post-step, ABORT/RETRY/ESCALATE enforcement y exports del paquete execution/ completos.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | PlanExecutor tests — TDD RED | c1c1bad | tests/execution/test_executor.py |
| 1 (GREEN) | PlanExecutor implementation | 3935901 | src/execution/executor.py |
| 2 | Finalize __init__.py + full suite green | 76a3dd1 | src/execution/__init__.py + 9 pre-existing fixes |

## What Was Built

### `src/execution/executor.py` — PlanExecutor (D-69, EXEC-03 + EXEC-02)

**`PlanExecutor`** recibe por constructor: `filesystem`, `shell`, `git` adapters, `journal` (UndoJournal) y `audit` (AuditPort).

**`_adapter_for(action)`:** split por `"."` sobre `action.type`; `"file"` → FileSystemAdapter, `"shell"` → ShellAdapter, `"git"` → GitAdapter; prefijo desconocido levanta `ValueError` (fail-closed).

**`_retry_with_backoff(adapter, action, params)`:** loop de `params.max_attempts` iteraciones totales; ejecuta `adapter.execute(action)` en cada iteración; en falla duerme `min(delay, backoff_max_s)` y dobla `delay`; retorna el primer éxito o la última falla.

**`run(plan)`:** por cada Action:
- Si `on_error == RETRY`: delega directamente a `_retry_with_backoff` (todos los intentos en ese loop, no hay primera llamada suelta)
- Si no: llama `adapter.execute()` una vez
- Si tuvo éxito: llama `adapter.verify()`; `verify.passed=False` es falla del paso
- Acumula `entry_id` del `payload["journal_entry_id"]` en `applied_entry_ids`
- En falla despacha a `_handle_failure`:
  - **ABORT** (y RETRY exhausto): `_abort_and_rollback()` itera `reversed(applied_entry_ids)` llamando `journal.restore(eid)` por cada uno (T-undo-corruption)
  - **ESCALATE**: `audit.log(AuditEvent.new(TASK_FAILED, payload={"escalate": True, "step": N}))` sin rollback (T-06-EXEC-1 / ORCH-07)
- En éxito completo: `journal.mark_applied(eid)` por cada entry acumulada

**`ExecutorResult`:** dataclass frozen con `success`, `detail`, `applied_entries: tuple[str, ...]`, `failed_step: int | None`.

### `src/execution/__init__.py` — Package exports

Re-exporta `FileSystemAdapter, GitAdapter, PlanExecutor, ShellAdapter, UndoJournal` con `__all__` ordenado alfabéticamente (RUF022).

## Verification Chain Results

```
uv run pytest tests/execution -q      → 51 passed, 3 skipped
uv run pytest -q                      → 379 passed, 6 skipped
uv run lint-imports                   → Contracts: 2 kept, 0 broken
uv run ruff check src tests           → All checks passed!
uv run mypy                           → Success: no issues found in 158 source files
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Pre-existing ruff/mypy violations in waves 1-2 files**

- **Found during:** Task 2 (running `uv run ruff check src tests`)
- **Issue:** 49 ruff violations and 5 mypy errors in files from plans 06-02, 06-03, 06-04 that were not caught at commit time (auto-fix hadn't been applied to those files)
- **Fix:** Applied `ruff check --fix` for auto-fixable items; manually fixed E501/SIM/F821/F841 violations in filesystem.py, shell.py, git.py, test_*.py files. Added `TYPE_CHECKING` imports for forward refs. Added `contextlib.suppress` pattern. Split long f-strings.
- **Rationale:** Plan 06-05 acceptance criteria explicitly requires `uv run ruff check src tests && uv run mypy` both exit 0 — impossible without fixing pre-existing violations.
- **Files modified:** src/execution/filesystem.py, src/execution/shell.py, src/execution/git.py, tests/execution/test_filesystem.py, tests/execution/test_git.py, tests/execution/test_journal.py, tests/execution/test_second_wall.py, tests/execution/test_shell.py

**2. [Rule 1 - Bug] RETRY N+1 execute calls**

- **Found during:** Task 1 GREEN (test_retry_respects_max_attempts failed: 4 != 3)
- **Issue:** `run()` called `adapter.execute()` once before delegating to `_retry_with_backoff` which called it `max_attempts` more times → total = max_attempts + 1
- **Fix:** Moved RETRY dispatch inline in `run()`: `if action.on_error == RETRY: result = await _retry_with_backoff(...)` eliminates the extra call. `_handle_failure` for RETRY case is now only reached after exhaustion, treated as terminal ABORT.

## Known Stubs

None. PlanExecutor is fully wired: dispatches to real adapters, reads real journal payload, enforces real on_error.

## Threat Flags

All threats from the plan's `<threat_model>` are mitigated:

| Flag | File | Description |
|------|------|-------------|
| T-undo-corruption | executor.py | ABORT rollback uses `reversed(applied_entry_ids)` — verified in test_abort_rolls_back_in_reverse |
| T-verify-bypass | executor.py | verify.passed=False is treated as step failure — same code path as execute failure |
| T-06-EXEC-1 | executor.py | ESCALATE logs AuditEvent(TASK_FAILED, payload={escalate:True}) before returning |
| T-06-EXEC-2 | executor.py | RetryParams.max_attempts caps total execute calls; backoff capped at backoff_max_s |

## Self-Check: PASSED

- [x] `src/execution/executor.py` exists (328 lines, contains `class PlanExecutor`, `_adapter_for`, `_retry_with_backoff`, `ExecutorResult`)
- [x] `tests/execution/test_executor.py` exists (5 async tests, all pass)
- [x] `src/execution/__init__.py` exports all 5 symbols with `__all__`
- [x] RED commit c1c1bad exists
- [x] GREEN commit 3935901 exists
- [x] Task 2 commit 76a3dd1 exists
- [x] 379 tests pass, 6 skipped — no regressions
