---
phase: 9
slug: routine-scheduler
status: draft
nyquist_compliant: false
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

(La completa el planner por tarea.)

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | — | — | SCHED-01..05 | — | rutinas B/C jamás auto-ejecutan | unit/integration | `uv run pytest tests/orchestrator -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/orchestrator/test_routine_store.py` — stubs para SCHED-01/03 (CRUD + estado)
- [ ] `tests/orchestrator/test_scheduler.py` — stubs para SCHED-02/04/05 (dispatch por política, catch-up, auditoría)
- [ ] Framework ya instalado — pytest/mypy/ruff/lint-imports operativos

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Rutina dispara a la hora local real y cae a la bandeja | SCHED-02 | tiempo real de reloj | crear rutina a T+2min, esperar, verificar bandeja + audit |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
