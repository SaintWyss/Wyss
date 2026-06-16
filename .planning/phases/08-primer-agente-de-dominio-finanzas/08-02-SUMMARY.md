---
phase: 08-primer-agente-de-dominio-finanzas
plan: 02
status: complete
subsystem: ledger
tags: [hexagonal, sqlite, wal, ledger, finanzas, sql-aggregation, frozen-dataclass, protocol]

# Dependency graph
requires:
  - phase: 08-primer-agente-de-dominio-finanzas
    provides: "RED ledger tests + conftest ground truth (08-01)"
  - phase: 05-orquestador
    provides: "pending_store WAL fail-fast molde + AuditIntegrityError"
  - phase: 02-gateway-de-modelos
    provides: "cost.py windowed COALESCE(SUM) aggregation molde"
provides:
  - "core.domain.ledger.Transaccion (frozen stdlib) + TipoTransaccion enum"
  - "core.ports.ledger.LedgerPort Protocol (record/query_by_category/balance/surplus/coverage_days)"
  - "ledger.sqlite_store.SqliteLedgerStore — WAL fail-fast adapter, SQL-side aggregations"
  - "ledger.schema (transacciones table + idx_transacciones_fecha)"
affects: [08-03-pellegrini-agent, 08-04-e2e-tasks]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SQL-side aggregation authority: COALESCE(SUM)/GROUP BY/COUNT(DISTINCT) over WHERE fecha BETWEEN ? AND ? — LLM never sums (AI-SPEC failure mode #1)"
    - "WAL fail-fast on construction (raise AuditIntegrityError if journal_mode != wal) — mirrored from pending_store"
    - "Parameterized ? placeholders exclusively for free-text categoria/fuente (STRIDE T-08-03)"
    - "Module-level structural-conformance assert (_: type[LedgerPort] = SqliteLedgerStore) verified by mypy, zero runtime cost"

key-files:
  created:
    - src/core/domain/ledger.py
    - src/core/ports/ledger.py
    - src/ledger/schema.py
    - src/ledger/sqlite_store.py
  modified:
    - src/core/domain/__init__.py
    - src/core/ports/__init__.py

key-decisions:
  - "synchronous=NORMAL (not FULL) for the ledger: it is not an append-only audit log, so fsync-per-commit cost is unjustified (AI-SPEC §3 / PATTERNS)"
  - "query_by_category filters tipo='GASTO' SQL-side — the ground truth is gasto-by-category; balance splits INGRESO/GASTO via conditional SUM in one query"
  - "Registered LedgerPort in core/ports/__init__.py alongside the other 15 contracts (consistency); test imports it directly from core.ports.ledger as the plan specifies"

requirements-completed: [AGENT-09]

# Metrics
duration: ~25min
completed: 2026-06-16
---

# Phase 8 Plan 02: Ledger Domain + SQLite Store Summary

**Vertical-slice ledger foundation for Pellegrini: frozen stdlib `Transaccion` + `LedgerPort` Protocol in pure core, and a `SqliteLedgerStore` adapter with WAL fail-fast and SQL-side aggregations — turning the 6 RED ledger tests from Plan 01 GREEN, with the full chain (pytest/mypy/ruff/lint-imports) clean and arithmetic structurally kept out of the LLM (AI-SPEC failure mode #1).**

## Performance

- **Duration:** ~25 min
- **Completed:** 2026-06-16
- **Tasks:** 2
- **Files modified:** 6 (4 created, 2 modified)

## Accomplishments
- Defined the ledger domain atom: `Transaccion` as a `@dataclass(frozen=True, slots=True)` of pure stdlib (no Pydantic — AI-SPEC §4b) with free-text `categoria` (D-83), plus a stdlib `TipoTransaccion(Enum)` (INGRESO/GASTO). Re-exported from `core.domain`.
- Defined `LedgerPort(Protocol)` in `core/ports/ledger.py` with `record/query_by_category/balance/surplus/coverage_days` — the arithmetic-authority contract; core never imports `sqlite3`/infra (lint-imports `core puro` kept).
- Implemented `SqliteLedgerStore` (infra `ledger/` package) satisfying `LedgerPort` structurally: WAL fail-fast on construction (`AuditIntegrityError` if `journal_mode != wal`, mirrored from `pending_store`), `row_factory=sqlite3.Row`, idempotent `apply_schema`, parameterized INSERT, and `close`/`__enter__`/`__exit__`.
- All aggregations computed SQL-side over an explicit `WHERE fecha BETWEEN ? AND ?` window: `query_by_category` (SUM + GROUP BY on tipo='GASTO'), `balance` (conditional SUM splitting INGRESO/GASTO in one query), `surplus` (ingresos − gastos), `coverage_days` (COUNT(DISTINCT fecha)). No Python loop ever sums raw rows — structural prevention of AI-SPEC failure mode #1.
- Turned the 6 RED ledger tests GREEN against the hand-computed ground truth (centavo-exact, no period leak): supermercado=1000, delivery=600, alquiler=600, transporte=100; balance=(3500, 2300); surplus=1200; coverage_days=8 (rich) / 5 (sparse).

## Task Commits

1. **Task 1: Transaccion domain type + LedgerPort Protocol** — `7527ed9` (feat)
2. **Task 2: SqliteLedgerStore adapter + schema (WAL fail-fast, SQL aggregations)** — `bfa69b2` (feat)

**Plan metadata:** _(this docs commit)_

## Files Created/Modified
- `src/core/domain/ledger.py` — `TipoTransaccion(Enum)` + frozen `Transaccion` (tipo/monto/fecha/fuente/categoria/created_at), stdlib only.
- `src/core/domain/__init__.py` — re-export `Transaccion`, `TipoTransaccion`.
- `src/core/ports/ledger.py` — `LedgerPort(Protocol)`, imports only `core.domain`.
- `src/core/ports/__init__.py` — register `LedgerPort` in the contract barrel.
- `src/ledger/schema.py` — PRAGMAS (WAL/synchronous=NORMAL/busy_timeout), `CREATE TABLE transacciones`, `idx_transacciones_fecha`, `apply_schema`.
- `src/ledger/sqlite_store.py` — `SqliteLedgerStore` implementing `LedgerPort`, WAL fail-fast, parameterized queries, SQL-side aggregations, context-manager.

## Decisions Made
- **synchronous=NORMAL, not FULL.** The ledger is not an append-only audit log; the durability/perf tradeoff of fsync-per-commit is unjustified here (AI-SPEC §3 / PATTERNS). WAL is still fail-fast to guarantee the journal mode actually took.
- **`query_by_category` filters `tipo='GASTO'` SQL-side.** The ground truth and the agent's spending-breakdown use case are about gastos; ingresos are not categorized in the fixtures. `balance` returns both totals in a single conditional-SUM query.
- **`LedgerPort` also registered in `core/ports/__init__.py`.** Consistency with the existing 15 contracts; the RED tests and the plan's verify command import it directly from `core.ports.ledger`, which resolves either way.

## Deviations from Plan
None — plan executed exactly as written. Both tasks' verify commands and acceptance criteria passed on first implementation; ruff auto-organized the two `__init__.py` import blocks (mechanical, no behavior change).

## TDD Gate Compliance
This plan is the GREEN half of the phase TDD cycle. The RED gate is Plan 01's `test(...)` commit `314d471` (the 6 ledger tests defining `core.domain.ledger` / `ledger.sqlite_store` contracts via deferred imports). This plan's two `feat(...)` commits (`7527ed9`, `bfa69b2`) are the GREEN gate — the previously-RED ledger tests now pass centavo-exact. No REFACTOR commit needed (implementation was minimal and clean).

## Green Chain
- `uv run pytest tests/ledger -q` → **6 passed** (was 6 RED).
- `uv run pytest -q` → **410 passed**, 6 skipped, **10 failed** — all 10 are `agents.pellegrini` ModuleNotFoundError, which belong to Plan 08-03 (out of this plan's scope). Passing count rose from 404 → 410 (the +6 ledger tests).
- `uv run mypy` → no issues in 187 source files.
- `uv run ruff check src tests` → all checks passed.
- `uv run lint-imports` → 2 contracts kept, 0 broken (core puro + layer independence).
- SQL-injection grep gate (`grep -nE "execute\(.*(format|%|f\")" src/ledger/sqlite_store.py`) → empty (only `?` placeholders).

## Threat Mitigations Applied
- **T-08-03 (Tampering, free-text categoria → SQL):** mitigated — `record()` uses a parameterized INSERT with `?` placeholders for all values incl. `categoria`/`fuente`; grep gate confirms no interpolation.
- **T-08-04 (Tampering, core purity):** mitigated — `core/ports/ledger.py` imports only `core.domain`; lint-imports `core puro` contract kept.
- **T-08-05 (Repudiation/Integrity, durability):** mitigated — WAL fail-fast raises `AuditIntegrityError` naming the path if WAL is not achieved.

## Known Stubs
None. `src/ledger/__init__.py` (created empty in Plan 01) now backs the implemented `schema.py` + `sqlite_store.py`.

## Next Phase Readiness
- Plan 08-03 (`agents.pellegrini`) can now build advisory logic on a deterministic ledger: inject `SqliteLedgerStore` (a `LedgerPort`) and read `balance`/`surplus`/`query_by_category`/`coverage_days` as the verified-facts block. The 10 remaining RED tests (pellegrini second-wall, no-fabrication, e2e) are 08-03/08-04 scope.

## Self-Check: PASSED
- All 4 created files present on disk; both modified `__init__.py` updated.
- Both task commits (`7527ed9`, `bfa69b2`) verified in git log.
- 6 ledger tests GREEN; full chain clean on gating dimensions.

---
*Phase: 08-primer-agente-de-dominio-finanzas*
*Completed: 2026-06-16*
