---
phase: 09-routine-scheduler
plan: 04
status: complete
completed: 2026-07-10
requirements: [SCHED-01, SCHED-03]
builder: codex (codex-gsd-exec) — verificado y commiteado por Claude
---

# 09-04 Summary — Daemon RPCs routine.* + CLI `wyss routine`

## Qué se hizo

- **Daemon** (`src/orchestrator/daemon.py`): 5 handlers JSON-RPC `routine.add/list/pause/resume/delete` (add valida schedule ANTES de persistir y devuelve preview; list incluye status/schedule/last_fired_at/last_outcome; pause/resume/delete afectan store + scheduler). `RunningDaemon.scheduler` + `aclose()` con `shutdown(wait=False)`. `start_daemon` hace `register_routines` (catch-up) antes de `scheduler.start()`.
- **CLI** (`src/bootstrap/cli.py`): sub-app `wyss routine` (add/list/pause/resume/rm) como thin RPC client — jamás abre routines.db; `add` muestra preview de próximas ejecuciones (hora Argentina) antes de guardar (SCHED-01); daemon caído → panel accionable. `wyss start` construye RoutineStore + RoutineScheduler y cierra el store en finally.
- **Desviación documentada (autorizada)**: el plan no cableaba la ejecución de planes A de rutina ("queued" sin consumidor). Fix espejo de `_ask`: `on_queued: QueuedPlanCallback | None` en `_fire_routine`/`RoutineScheduler`/`register_routines`; el daemon lo setea a `_execute_plan` solo si hay runner. **B/C jamás llaman on_queued** (dispatch devuelve pending) — testeado explícito para B y para C. Cumple el criterio "A ejecuta directo" sin tocar MULTI-02.

## Verificación (fuera del sandbox)

Cadena completa: **573 passed** (+7) / mypy 0 / ruff 0 / import-linter 2/2. `wyss routine --help` expone add/list/pause/resume/rm.

## Deviations

Solo la de `on_queued` (arriba), autorizada por el orquestador antes de construir.
