---
phase: 02-gateway-de-modelos
plan: 04
subsystem: gateway
tags: [sqlite, wal, traces, cost-gate, budget, observability, tdd]

# Dependency graph
requires:
  - phase: 02-gateway-de-modelos
    plan: 01
    provides: "BudgetExceeded (dominio), scaffolding tests/gateway con fixture traces_db_path, FakeAuditPort"
  - phase: 01-fundaciones
    provides: "patrón SQLite/WAL fail-fast (audit/schema.py + sqlite_logger.py), AuditPort, AuditEvent.new"
provides:
  - "TraceStore: persistencia consultable de traces (traces.db separada, WAL fail-fast, NO append-only — purga 90d, D-22)"
  - "traces_schema: DDL de tabla traces + spend_ledger; PRAGMAS WAL idénticos a audit, SIN triggers de inmutabilidad"
  - "CostTracker: gate de presupuesto pre-autorización (authorize veta ANTES de la llamada, D-18) + record local durable (D-24)"
  - "TraceIntegrityError (dominio): análogo a AuditIntegrityError para traces.db"
affects: [02-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "réplica exacta del smoke test WAL fail-fast de Fase 1, pero sin triggers append-only (traces expiran por retención)"
    - "gate pre-autorización: BudgetExceeded ANTES de provider.complete() — presupuesto enforced, no advisory (Pitfall 2)"
    - "costo calculado LOCAL determinístico (tokens x precio config); el costo del provider se guarda comparativo pero no gobierna el gate (D-24)"
    - "una sola DB de gateway (traces.db) aloja tanto traces como spend_ledger (Open Question 3)"

key-files:
  created:
    - src/gateway/traces_schema.py
    - src/gateway/traces.py
    - src/gateway/cost.py
    - tests/gateway/test_traces.py
    - tests/gateway/test_cost_gate.py
  modified:
    - src/core/domain/errors.py

key-decisions:
  - "spend_ledger (estado de gasto del gate) vive en traces.db junto a la tabla traces — una sola DB de gateway (Open Question 3 resuelta a favor de la recomendación de RESEARCH)"
  - "TraceIntegrityError nuevo en core.domain.errors (no reusar AuditIntegrityError): el error nombra el subsistema correcto (traces != audit, D-22) manteniendo el patrón WyssError"
  - "CostTracker.record devuelve el costo local y emite COST_RECORDED al AuditPort inyectado (nunca importa el sink concreto — contrato independence intacto)"
  - "ventana de mes por replace(day=1, hora 00:00) UTC sobre created_at del ledger — gasto del mes anterior no cuenta para el actual"

patterns-established:
  - "store SQLite NO append-only: purge_older_than(days) borra por retención; opuesto al audit forever"
  - "gate de costo sin setters de límites: el presupuesto solo cambia por config + reload (D-19, regla #6)"

requirements-completed: [GATE-04, GATE-05]

# Metrics
duration: 6min
completed: 2026-06-12
---

# Phase 2 Plan 04: Cost Gate + Trace Store Summary

**TraceStore (traces.db separada, WAL fail-fast, consultable por task/purpose, purga 90d sin append-only) y CostTracker que veta con BudgetExceeded ANTES de cada llamada (gate enforced, costo local determinístico) — el denial-of-wallet queda cerrado y cada llamada deja trace consultable.**

## Performance

- **Duration:** ~6 min
- **Tasks:** 2 (ambas TDD: RED → GREEN)
- **Files modified:** 6 (5 creados, 1 modificado)

## Accomplishments

- `src/gateway/traces_schema.py`: DDL de `traces` (id, trace_id UNIQUE, task_id, agent_id, tier, purpose, prompt POST-minimizer, output, tokens_in/out, cost_usd, latency_ms, created_at) con índices por `task_id` y `(purpose, created_at)`. PRAGMAS WAL/synchronous=FULL/busy_timeout=5000 **copiados idénticos** de `audit/schema.py`. **Sin triggers append-only** (D-22: traces expiran). También define `spend_ledger` (estado durable del gate de costo) con índices por tiempo y por `(agent_id, created_at)`.
- `src/gateway/traces.py`: `TraceStore` que **replica EXACTO** el smoke test WAL fail-fast de `SqliteAuditLogger` (journal_mode != "wal" → `TraceIntegrityError` con el path, Pitfall 6 NTFS). `write()` con INSERT parametrizado; `query_by_task` / `query_by_purpose` consultables (D-22); `purge_older_than(days)` borra por retención (esto NO existe en audit).
- `src/gateway/cost.py`: `CostTracker` con `estimate_cost` local `(in+out)/1000 * precio` (KeyError = config incompleta = fail-fast), `authorize()` que veta con `BudgetExceeded` ANTES de la llamada (global + cap por-agente, D-18), `record()` que persiste el costo **local** (D-24) en `spend_ledger` y emite `COST_RECORDED` al `AuditPort` **inyectado** (nunca importa el sink — contrato `independence` intacto). Ventana de mes calendario; sin setters de límites (D-19, regla #6).
- `core/domain/errors.py`: `TraceIntegrityError` (análogo a `AuditIntegrityError`).

## Task Commits

Cada tarea TDD commiteada atómicamente (RED → GREEN):

1. **Task 1 (RED): tests fallidos TraceStore** - `bf75f17` (test) — incluye `TraceIntegrityError` para que el import resuelva
2. **Task 1 (GREEN): TraceStore + traces_schema** - `4593496` (feat)
3. **Task 2 (RED): tests fallidos CostTracker gate** - `b393d12` (test)
4. **Task 2 (GREEN): CostTracker gate pre-autorización** - `aea6fe4` (feat)

_TDD: ambas tareas siguieron RED → GREEN; refactor no necesario (código limpio al primer GREEN)._

## Files Created/Modified

- `src/gateway/traces_schema.py` - DDL traces + spend_ledger; PRAGMAS WAL; sin triggers append-only
- `src/gateway/traces.py` - TraceStore (WAL fail-fast, query, purge)
- `src/gateway/cost.py` - CostTracker (authorize veta + record local durable)
- `src/core/domain/errors.py` - `TraceIntegrityError`
- `tests/gateway/test_traces.py` - 6 tests (WAL, persistencia D-22, filtros, purga, no-append-only, fail-fast)
- `tests/gateway/test_cost_gate.py` - 9 tests de seguridad del gate (veto global/agente, provider nunca invocado, costo local, estado durable, ventana de mes)

## Decisions Made

- **`spend_ledger` en `traces.db`**: una sola DB de gateway aloja traces y estado de gasto (Open Question 3 → recomendación de RESEARCH). El DDL del ledger lo aporta `traces_schema.apply_schema`, así tanto `TraceStore` como `CostTracker` lo materializan idempotentemente al construir sobre la misma DB.
- **`TraceIntegrityError` nuevo (no reusar `AuditIntegrityError`)**: el plan permitía cualquiera; elegí el específico para que el mensaje de error nombre el subsistema correcto (traces, no audit) — coherente con D-22 (DB separada) y con el patrón `WyssError` del repo.
- **`record()` devuelve el costo local + audita**: facilita que el `gateway.py` (02-05) registre y obtenga el costo en una sola llamada; el evento `COST_RECORDED` (ya existente en la taxonomía) cubre el rastro sin inventar API en el núcleo.

## Deviations from Plan

None - plan executed exactly as written.

(Nota menor: `CostTracker` no repite el smoke test WAL fail-fast de `TraceStore` porque comparte la misma `traces.db` que el `TraceStore` ya valida en bootstrap; `apply_schema` sí ejecuta los PRAGMAS WAL. No es una desviación: el plan dejó "a discreción" la creación del DDL del ledger y la mitigación T-02-trace-wal queda cubierta por el store que abre la DB primero.)

## Threat Model Coverage

| Threat ID | Disposition | Cubierto por |
|-----------|-------------|--------------|
| T-02-budget-bypass | mitigate | `authorize()` levanta ANTES de la llamada; test `test_authorize_provider_never_invoked_on_exceed` verifica que el provider nunca se invoca |
| T-02-budget-advisory | mitigate | costo LOCAL gobierna; `test_record_uses_local_cost_not_provider` verifica que el `provider_reported_cost` no afecta el gate |
| T-02-budget-override | mitigate | `CostTracker` no expone setters de límites (D-19, regla #6) |
| T-02-trace-wal | mitigate | smoke test WAL fail-fast replicado en `TraceStore`; `test_fail_fast_when_journal_not_wal` |
| T-02-trace-pii | accept | traces.db separada, prompt POST-minimizer, retención 90d (riesgo aceptado por diseño) |

## Issues Encountered

Ninguno. Ambas tareas pasaron al primer GREEN; mypy (76 archivos) y lint-imports (2 contratos KEPT) verdes; suite completa `126 passed, 2 skipped`.

## Next Phase Readiness

- `TraceStore` y `CostTracker` listos para que `gateway.py` (02-05) los orqueste: router → minimizer → `cost.authorize` → provider.complete (con retry que re-llama authorize, D-25) → `cost.record` → `traces.write` → audit.log.
- `spend_ledger` y `traces` materializadas en la misma DB; el bootstrap solo necesita inyectar `db_path`, `prices`, `global_budget`, `agent_budgets` y el `SqliteAuditLogger` concreto como `AuditPort`.
- Sin blockers.

## Self-Check: PASSED

- Archivos creados/modificados: todos FOUND (traces_schema.py, traces.py, cost.py, errors.py, test_traces.py, test_cost_gate.py).
- Commits verificados: bf75f17, 4593496, b393d12, aea6fe4.
- Verificación: `tests/gateway/test_traces.py tests/gateway/test_cost_gate.py` → 15 passed; suite completa 126 passed / 2 skipped; mypy + lint-imports verdes.

---
*Phase: 02-gateway-de-modelos*
*Completed: 2026-06-12*
