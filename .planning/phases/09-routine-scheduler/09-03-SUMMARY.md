---
phase: 09-routine-scheduler
plan: 03
status: complete
completed: 2026-07-10
requirements: [SCHED-01, SCHED-02, SCHED-04, SCHED-05]
builder: codex (codex-gsd-exec) — verificado y commiteado por Claude
---

# 09-03 Summary — RoutineScheduler

## Qué se hizo

`src/orchestrator/scheduler.py` (355 líneas) + `tests/orchestrator/test_scheduler.py` (16 tests):

- **`build_plan_from_routine`**: Plan determinístico desde `plan_json` (mismo shape que `_plan_to_dict`), `task_id="routine-{id}"` — cero LLM/gateway.
- **`_fire_routine`**: re-chequea status (paused no dispara), `engine.evaluate()` + `dispatch(ttl_for=routine_ttl_for)` — MISMO gate que ask, jamás llama runner; audita `ROUTINE_TRIGGERED` (payload: routine_id, outcome, risk, policy) y `mark_fired` atómico; excepción → `TASK_FAILED` sin matar el scheduler.
- **`routine_ttl_for`** → 86400 (decisión owner: TTL 24h), `DEFAULT_TTL_BY_LEVEL` intacto.
- **`RoutineScheduler`**: wrapper de AsyncIOScheduler (timezone ARG explícito, `coalesce=True`, `max_instances=1`, misfire grace 300s); add/remove/pause/resume por job id `routine:{id}`; start/shutdown limpios.
- **`register_routines`** (catch-up on boot): `_missed_fire_count` contra `last_fired_at` con guard estricto; `catch_up=True` → coalesce a UN solo fire; `False` → skip auditado como missed.
- **`validate_schedule`/`preview_next_fires`**: cron vía `CronTrigger.from_crontab` con error legible (`ConfigError`), interval floor 60s (T-09-05); preview = próximas N ejecuciones concretas en hora Argentina.

## Verificación (fuera del sandbox)

Cadena completa: **566 passed** (+16) / mypy 0 / ruff 0 / import-linter 2/2 (apscheduler solo en orchestrator/, core puro).

## Nota para 09-04

El scheduler deja planes A en outcome "queued" (por diseño: jamás toca el runner — MULTI-02). La ejecución real de A-level post-dispatch vive en la capa daemon (patrón `_ask`): cablearlo en 09-04 al integrar scheduler+runner en `start_daemon`.
