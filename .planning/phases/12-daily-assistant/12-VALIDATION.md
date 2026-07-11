---
phase: 12
slug: daily-assistant
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-11
updated: 2026-07-11
---

# Phase 12 — Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (asyncio strict) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/orchestrator -q` |
| **Full suite command** | `uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports` |
| **Estimated runtime** | ~15 s (quick) / ~70 s (full) |

## Sampling Rate

- After every task commit: quick command
- After every plan wave: full suite
- Before verify-work: full suite green
- Max feedback latency: 70 seconds

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01-T1 | 12-01 | 1 | DAILY-01 | T-12-03 | [digest] valida fail-closed; DIGEST_GENERATED en dominio | unit | `uv run pytest tests/bootstrap/test_config.py -q` | ✅ | ⬜ pending |
| 12-01-T2 | 12-01 | 1 | DAILY-01, DAILY-02 | T-12-01, T-12-02 | composer puro, determinístico, cero imports de ejecución | unit (tdd) | `uv run pytest tests/orchestrator/test_digest.py -q` | ✅ | ⬜ pending |
| 12-02-T1 | 12-02 | 2 | DAILY-01, DAILY-03 | T-12-05, T-12-08 | digest.today solo-lectura + audita DIGEST_GENERATED | unit (tdd) | `uv run pytest tests/orchestrator/test_daemon.py -q` | ✅ | ⬜ pending |
| 12-02-T2 | 12-02 | 2 | DAILY-01 | T-12-06, T-12-07 | job interno sin dispatch; materializa data/digests/*.md | unit (tdd) | `uv run pytest tests/orchestrator/test_scheduler.py tests/orchestrator/test_digest.py -q` | ✅ | ⬜ pending |
| 12-03-T1 | 12-03 | 3 | DAILY-01 | T-12-11 | ledger real inyectado; digest job solo si enabled; sin fugas | unit | `uv run pytest tests/bootstrap/test_cli.py -q` | ✅ | ⬜ pending |
| 12-03-T2 | 12-03 | 3 | DAILY-03 | T-12-09, T-12-10 | thin client por RPC; daemon caído = panel accionable | unit | `uv run pytest tests/bootstrap/test_cli.py -q` | ✅ | ⬜ pending |
| 12-04-T1 | 12-04 | 4 | DAILY-01..03 | T-12-12, T-12-13 | digest real solo-lectura + archivo programado | manual | checkpoint human-verify | — | ⬜ pending |

## Wave 0 Requirements

- [x] Framework ya instalado (pytest asyncio)
- [ ] Tests del composer del digest (bandeja + ledger + fallas de rutinas, formato estable) — creados en 12-01 Task 2
- [ ] Tests de config `[digest]` fail-closed — creados en 12-01 Task 1

Nota Nyquist: no hay `<automated>MISSING</automated>` — cada task de código crea su propio test file en la misma pasada (test_digest.py, test_config.py, test_daemon.py, test_scheduler.py, test_cli.py ya existen o se extienden). El único manual-only es el checkpoint final (reloj + datos vivos).

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Digest real on-demand + rutina programada materializando archivo | DAILY-01/02/03 | reloj real + datos vivos | Plan 12-04: `wyss digest` + esperar la hora de `[digest]` y verificar data/digests/AAAA-MM-DD.md; confirmar cero writes/propuestas |

## Key Decisions (documentadas en los planes)

1. **Fuente de fallas de rutinas = `RoutineStore.last_outcome`** (no audit.db TASK_FAILED). `AuditPort` no tiene método de lectura y agregar un audit-read port/adapter es superficie extra sin lector hoy; `last_outcome=="failed"` satisface "fallas de rutinas". Enriquecimiento por TASK_FAILED de crash duro = extensión futura documentada. (Plan 12-01)
2. **Ledger vía `core.ports.ledger.LedgerPort` inyectado** desde bootstrap → orchestrator nunca importa `src/ledger` (independence import-linter respetada). (Planes 12-01/12-02/12-03)
3. **Digest programado = job interno del scheduler (`internal:digest`)**, NO una Routine de usuario ni un action type. Es la opción de menor superficie: sin `_BASE_LEVELS`/`_ACTION_TYPES`/5-conftests, sin dispatch. Además mantiene el digest estructuralmente fuera del camino de Plan/política → DAILY-02 por construcción, MULTI-02 intacto. (Plan 12-02)
4. **Almacenamiento del digest materializado = archivo `data/digests/YYYY-MM-DD.md`** (lo más simple y honesto; no tabla DB). (Plan 12-02)
5. **DAILY-03 "en la web"**: fase 12 entrega el RPC `digest.today` listo; el panel web es WEB-02 (fase 14). El on-demand se satisface por `wyss digest`. (Plan 12-03/12-04)

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity OK
- [x] Wave 0 covers MISSING references (tests creados en la misma pasada que el código)
- [x] No watch-mode flags
- [x] Feedback latency < 70s
- [x] nyquist_compliant: true set in frontmatter

**Approval:** pending
