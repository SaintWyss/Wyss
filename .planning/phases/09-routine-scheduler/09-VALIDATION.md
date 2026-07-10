---
phase: 9
slug: routine-scheduler
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-10
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (asyncio strict, ya configurado) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/orchestrator -q` |
| **Full suite command** | `uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports` |
| **Estimated runtime** | ~15 s (quick) / ~60 s (full) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/orchestrator -q`
- **After every plan wave:** Run full suite command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-T1 | 01 | 1 | SCHED-05 | T-09-SC | apscheduler aprobado por owner antes del install (gate legitimidad) | checkpoint | (blocking-human) | n/a | ⬜ pending |
| 09-01-T2 | 01 | 1 | SCHED-05 | T-09-01a | ROUTINE_TRIGGERED distingue disparos de rutina en la traza | unit | `uv run python -c "from core.domain.audit import AuditEventType; assert AuditEventType.ROUTINE_TRIGGERED=='routine.triggered'"` | ✅ nuevo | ⬜ pending |
| 09-02-T1 | 02 | 1 | SCHED-03 | T-09-07 | store falla-cerrado si WAL no disponible | unit | `uv run pytest tests/orchestrator/test_routine_store.py -x -q` | ❌ Wave 0 | ⬜ pending |
| 09-02-T2 | 02 | 1 | SCHED-03 | T-09-03 | mark_fired atómico (last_fired_at + outcome en un UPDATE) | unit | `uv run pytest tests/orchestrator/test_routine_store.py -x -q` | ❌ Wave 0 | ⬜ pending |
| 09-03-T1 | 03 | 2 | SCHED-01 | T-09-05 | validate_schedule con floor 60s + cron inválido legible | unit | `uv run pytest tests/orchestrator/test_scheduler.py -x -q` | ❌ Wave 0 | ⬜ pending |
| 09-03-T2 | 03 | 2 | SCHED-02, SCHED-05 | T-09-01, T-09-06, T-09-08 | B/C jamás auto-ejecuta; fire re-chequea status; auditoría éxito+fallo | unit | `uv run pytest tests/orchestrator/test_scheduler.py -x -q` | ❌ Wave 0 | ⬜ pending |
| 09-03-T3 | 03 | 2 | SCHED-04 | T-09-03, T-09-04 | catch-up coalesce a 1 fire; guard `>` anti doble-fire | unit | `uv run pytest tests/orchestrator/test_scheduler.py -x -q` | ❌ Wave 0 | ⬜ pending |
| 09-04-T1 | 04 | 3 | SCHED-03 | T-09-05, T-09-09 | handlers routine.* solo sobre socket 0o600; validate en el add | unit/integration | `uv run pytest tests/orchestrator/test_daemon.py -x -q` | ✅ existente (extender) | ⬜ pending |
| 09-04-T2 | 04 | 3 | SCHED-01, SCHED-03 | T-09-06, T-09-10 | CLI thin RPC client; preview antes de guardar; no abre db directo | unit | `uv run pytest tests/orchestrator -q` | ✅ existente | ⬜ pending |
| 09-05-T1 | 05 | 4 | SCHED-02, SCHED-04, SCHED-05 | T-09-01 | rutina real cae a la bandeja sin auto-exec, auditada (reloj real) | checkpoint (manual) | (blocking-human) | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Nyquist:** cada tarea productora de código tiene `<automated>`; ninguna corrida de 3 tareas consecutivas sin verify automatizado (los 2 checkpoints — 09-01-T1 y 09-05-T1 — son pre-install approval y smoke de reloj real, no reemplazan cobertura: la lógica está en tests unitarios de 09-02/03/04).

---

## Wave 0 Requirements

- [ ] `tests/orchestrator/test_routine_store.py` — creado en 09-02: CRUD, pause/resume/delete, mark_fired atómico, guard WAL (SCHED-03)
- [ ] `tests/orchestrator/test_scheduler.py` — creado en 09-03: preview, gate de política + no auto-exec, catch-up/no doble-fire, auditoría éxito+fallo (SCHED-01/02/04/05)
- [ ] `tests/orchestrator/test_daemon.py` — extendido en 09-04: handlers routine.* round-trip + aclose apaga scheduler
- [ ] `uv add apscheduler` (09-01) — dependencia runtime, tras checkpoint de aprobación del owner
- [ ] Framework ya instalado — pytest/mypy/ruff/lint-imports operativos

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Rutina dispara a la hora local real y cae a la bandeja | SCHED-02 | tiempo real de reloj + daemon vivo | Plan 09-05 (checkpoint): crear rutina a T+2min, esperar, verificar bandeja + audit |
| Catch-up coalesce tras downtime real | SCHED-04 | requiere bajar/subir el daemon con el reloj corriendo | Plan 09-05 (checkpoint opcional): bajar daemon, esperar ocurrencia, relevantar, confirmar 1 solo fire |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned (2026-07-10) — pendiente de ejecución
