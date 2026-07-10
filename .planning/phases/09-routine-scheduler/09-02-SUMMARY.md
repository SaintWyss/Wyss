---
phase: 09-routine-scheduler
plan: 02
status: complete
completed: 2026-07-10
requirements: [SCHED-03]
builder: codex (codex-gsd-exec) — verificado y commiteado por Claude
---

# 09-02 Summary — RoutineStore

## Qué se hizo

- `src/orchestrator/routine_store.py`: `Routine` (frozen+slots, 10 campos) + `RoutineStore` — espejo exacto del estilo PendingStore: pragmas WAL, guard fail-fast con `AuditIntegrityError` reusado, `sqlite3.Row`, timestamps ISO UTC, context manager. Tabla `routines` + índice por status.
- CRUD completo: `add/get/list_all/list_active/pause/resume/delete` — mutadores devuelven `rowcount == 1`, False sobre id ausente sin lanzar.
- **`mark_fired` atómico**: `last_fired_at` + `last_outcome` en UNA sentencia UPDATE / un commit (requisito duro anti doble-fire, T-09-03).
- `tests/orchestrator/test_routine_store.py`: 10 tests (CRUD, round-trip catch_up bool, pause/resume durable, delete idempotente, mark_fired atómico y sobre id ausente). Fixture local al archivo (no toca conftest).

## Verificación (fuera del sandbox de Codex)

Cadena completa: **550 passed** / mypy 0 / ruff 0 / import-linter 2/2. Los 2 fallos que Codex reportó en su sandbox (test_ask_daemon_caido, test_shell echo) eran artefactos del sandbox — pasan acá.

## Deviations

Fixture del store local al test en vez de conftest (decisión de Codex, razonable: no contamina el conftest compartido).
