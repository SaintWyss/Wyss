---
phase: 08-primer-agente-de-dominio-finanzas
plan: 01
subsystem: testing
tags: [pytest, import-linter, toml, pydantic, ledger, cost-gate, red-scaffold, nyquist]

# Dependency graph
requires:
  - phase: 02-gateway-de-modelos
    provides: CostTracker budget gate (authorize/record) + agent_budgets wiring
  - phase: 05-orquestador
    provides: dispatcher.dispatch + FakeOrchestrator fixture
  - phase: 07-modelo-de-agentes
    provides: AgentBase template method + AgentConfigModel/[[agents]] config
provides:
  - "llm_judge pytest marker (opt-in D3 eval)"
  - "ledger import-linter root package + empty src/ledger package (hexagon boundary enforced)"
  - "Pellegrini agent wired into config template (both [[agents]] and [gateway.agent_budgets])"
  - "7 RED test files + ledger conftest defining all AGENT-07 / AGENT-09 contracts"
affects: [08-02-ledger-adapter, 08-03-pellegrini-agent, 08-04-e2e-tasks]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "RED scaffold via deferred imports inside test bodies (no importorskip, no xfail)"
    - "Forward-compatible mypy ignore: # type: ignore[import-untyped,import-not-found,unused-ignore]"
    - "Hand-computed ground-truth constants as the arithmetic label (AI-SPEC D1)"
    - "Fixtures return raw TxSpec tuples; domain object built in test body so RED surfaces as FAILED not ERROR"

key-files:
  created:
    - src/ledger/__init__.py
    - tests/ledger/__init__.py
    - tests/ledger/conftest.py
    - tests/ledger/test_sqlite_store.py
    - tests/gateway/test_cost_agent_budget_e2e.py
    - tests/bootstrap/test_agent_budget_wiring.py
    - tests/agents/test_pellegrini_second_wall.py
    - tests/agents/test_pellegrini_no_fabrication.py
    - tests/agents/test_pellegrini_e2e.py
  modified:
    - pyproject.toml
    - config/config.example.toml

key-decisions:
  - "config/config.toml is gitignored; the durable tracked artifact is config.example.toml (wired Pellegrini there + synced local config.toml for verify)"
  - "Created src/ledger/__init__.py because import-linter requires the root_package to be importable (plan assumed vacuous satisfaction; it errors without the package)"
  - "Gateway D4 + bootstrap-wiring + second-wall-routing tests are GREEN (they exercise pre-existing implemented contracts); the truly-unimplemented contracts (ledger, pellegrini agent) are RED"

patterns-established:
  - "Deferred-import RED pattern: import the not-yet-existing module inside the test/helper body with a forward-compatible type-ignore, so collection + mypy stay clean and the failure is a clear ModuleNotFoundError"
  - "Ground-truth-as-constant: aggregation totals computed by hand in conftest, never recomputed at test time"

requirements-completed: [AGENT-07, AGENT-09]

# Metrics
duration: ~40min
completed: 2026-06-16
---

# Phase 8 Plan 01: RED Scaffold + Phase Plumbing Summary

**Wave 0 scaffold: llm_judge marker, ledger import-linter package, Pellegrini wired into config, and 7 RED test files defining every AGENT-07/AGENT-09 contract with hand-computed ground truth — mypy/ruff/lint-imports green, pre-existing suite intact (404 passed), new tests RED as designed (16 failed).**

## Performance

- **Duration:** ~40 min
- **Started:** 2026-06-16T20:25Z (approx)
- **Completed:** 2026-06-16T21:06Z
- **Tasks:** 3
- **Files modified:** 11 (2 modified, 9 created)

## Accomplishments
- Closed RESEARCH Pitfalls 3 & 4: `ledger` registered in all three import-linter locations (root_packages, core-puro forbidden, layer independence) and the `llm_judge` marker registered (no PytestUnknownMarkWarning).
- Wired Pellegrini into the config template: `[[agents]]` entry (domain=finanzas, tier=economico, budget_usd=5.0) + `[gateway.agent_budgets].pellegrini = 5.0` — the field `CostTracker.authorize` actually reads (Pitfall 1).
- 7 RED test files + ledger conftest define the full phase contract surface: ledger aggregation (D1/D2), no-period-leak window filtering, coverage_days (D3), budget gate blocking (D4), second-wall on finance.record (D5), no-fabrication (D2 regex subset), and 3 D-87 E2E tasks via dispatcher + FakeOrchestrator + FakeAudit.
- Green chain verified: `pytest` (404 passed / 16 RED-by-design / 6 skipped), `mypy` (183 files), `ruff`, `lint-imports` (2 contracts kept) all pass on the gating dimensions.

## Task Commits

Each task was committed atomically:

1. **Task 1: infra gaps (llm_judge marker + ledger import-linter package)** — `ceb7641` (chore)
2. **Task 2: real config with Pellegrini agent + wired budget** — `78b7fc5` (feat)
3. **Task 3: 7 RED test files defining phase contracts** — `314d471` (test)

**Plan metadata:** _(this docs commit)_

## Files Created/Modified
- `pyproject.toml` — added llm_judge marker; added `ledger` to root_packages + core-puro forbidden_modules + independence modules; added `src/ledger` to hatch wheel packages.
- `config/config.example.toml` — added Pellegrini `[[agents]]` entry + `[gateway.agent_budgets].pellegrini = 5.0`.
- `src/ledger/__init__.py` — empty package so import-linter resolves the root_package (filled in Plan 02).
- `tests/ledger/conftest.py` — hand-computed ground truth (rich + sparse sets, HECHOS_VERIFICADOS block); fixtures return raw TxSpec tuples.
- `tests/ledger/test_sqlite_store.py` — D1/D2 aggregation + window-filter RED tests.
- `tests/gateway/test_cost_agent_budget_e2e.py` — D4 budget gate E2E (GREEN — gate pre-exists).
- `tests/bootstrap/test_agent_budget_wiring.py` — AGENT-07 Pitfall 1 unit tests (GREEN — wiring pre-exists).
- `tests/agents/test_pellegrini_second_wall.py` — D5 finance.record muralla (1 GREEN routing, 2 RED agent).
- `tests/agents/test_pellegrini_no_fabrication.py` — D2 reported ⊆ facts (RED).
- `tests/agents/test_pellegrini_e2e.py` — 3 D-87 tasks + @llm_judge advisory quality (RED).

## Decisions Made
- **config.toml is gitignored** (`.gitignore:82`) and was identical to `config.example.toml`. The plan assumed `config/config.toml` did not exist (RESEARCH Pitfall 2 was stale). Resolution: wire Pellegrini into the tracked `config.example.toml` (the durable artifact) and sync the local `config.toml` so the verify command passes. The `must_haves` artifact `config/config.toml contains pellegrini` is satisfied on disk; the committed record lives in the example template.
- **Gate/wiring/routing tests are GREEN, not RED.** D4 (cost gate), AGENT-07 wiring, and the second-wall routing assertion exercise contracts already implemented in Phases 2/5/7 (cost.py, build_gateway, AgentBase). They pass truthfully. Only the genuinely-unimplemented contracts (ledger adapter, Pellegrini agent) are RED. This is honest RED — failing for the right reason (ModuleNotFoundError), not faked failure.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created src/ledger package so import-linter resolves the root_package**
- **Found during:** Task 1
- **Issue:** The plan stated the `ledger` import-linter contracts would be "vacuously satisfied" with no package present. In reality, `lint-imports` errors with `Could not find package 'ledger' in your Python path` when a root_package does not exist.
- **Fix:** Created empty `src/ledger/__init__.py` (documented, fills in Plan 02) and added `src/ledger` to `[tool.hatch.build.targets.wheel].packages` so the editable install exposes it.
- **Files modified:** src/ledger/__init__.py, pyproject.toml
- **Verification:** `uv run lint-imports` → 2 contracts kept, 0 broken; `import ledger` succeeds.
- **Committed in:** ceb7641 (Task 1 commit)

**2. [Rule 3 - Blocking] Wired Pellegrini into config.example.toml instead of (only) config.toml**
- **Found during:** Task 2
- **Issue:** `config/config.toml` is gitignored and could not be committed; it already existed (contradicting the plan's premise).
- **Fix:** Edited the tracked `config.example.toml` to add Pellegrini in both budget fields; synced local `config.toml` for the verify command.
- **Files modified:** config/config.example.toml (tracked); config/config.toml (untracked, synced)
- **Verification:** `load_settings(Path('config/config.toml'))` returns Pellegrini with domain=finanzas, model_alias=economico, agent_budgets['pellegrini']==5.0, economico max_tokens==1024.
- **Committed in:** 78b7fc5 (Task 2 commit)

**3. [Rule 1 - Bug] Corrected the D4 e2e budget math to the gate's actual estimation**
- **Found during:** Task 3
- **Issue:** Initial budget thresholds assumed the gate estimates cost from the response token counts; the gate actually estimates from the prompt-length heuristic and persists the real cost via `cost.record`. The test "DID NOT RAISE".
- **Fix:** Set the per-agent budget so the first call's recorded real cost (1.0) equals the cap, making the second `authorize()` veto before the provider; rewrote the isolation test to exhaust pellegrini via a recorded call first.
- **Files modified:** tests/gateway/test_cost_agent_budget_e2e.py
- **Verification:** Both D4 e2e tests pass; provider `.calls` does not increase on the vetoed call.
- **Committed in:** 314d471 (Task 3 commit)

**4. [Rule 1 - Bug] Made ledger RED surface as FAILED instead of fixture ERROR**
- **Found during:** Task 3
- **Issue:** Building `Transaccion` inside fixtures made the ModuleNotFoundError a fixture-setup ERROR; the plan's acceptance wants FAILED.
- **Fix:** Fixtures now return raw `TxSpec` tuples; `Transaccion` is constructed inside `_build_store` (test body) via `build_transaccion`, so the RED failure is a test FAILURE.
- **Files modified:** tests/ledger/conftest.py, tests/ledger/test_sqlite_store.py
- **Verification:** `pytest tests/ledger` → 6 failed (ModuleNotFoundError), 0 errors.
- **Committed in:** 314d471 (Task 3 commit)

---

**Total deviations:** 4 auto-fixed (2 blocking, 2 bug)
**Impact on plan:** All necessary to make the scaffold actually green-chain-clean and to honor the plan's RED-as-FAILED acceptance. The config.toml/ledger-package deviations correct stale plan premises; no scope creep.

## TDD Gate Compliance
N/A — this plan is a pure RED scaffold (no `tdd="true"` task with production source files). It creates failing tests that downstream plans (08-02..08-04) turn GREEN. The `test(...)` commit (314d471) is the RED gate for the whole phase.

## Issues Encountered
- mypy strict over `tests/` rejects imports of not-yet-existing modules. Resolved with the forward-compatible ignore `# type: ignore[import-untyped,import-not-found,unused-ignore]` placed on the single-line `import ... as` statement (verified it stays clean in both the missing-module and future module-exists states).

## Known Stubs
- `src/ledger/__init__.py` is an intentionally empty package (only a docstring). It exists to satisfy import-linter's root_package resolution; the `SqliteLedgerStore` adapter is implemented in Plan 02. Documented and expected.

## User Setup Required
None — no external service configuration required. (API keys still come from `.env` via the existing `_gateway_env_values()`; no secrets added to config.)

## Next Phase Readiness
- Feedback loop ready: `uv run pytest tests/ledger tests/gateway/test_cost_agent_budget_e2e.py tests/agents/test_pellegrini_*.py -q` is the per-task RED→GREEN target for Plans 02–04.
- Plan 02 must create `core.domain.ledger` (Transaccion/TipoTransaccion), `core.ports.ledger.LedgerPort`, and `ledger.sqlite_store.SqliteLedgerStore` to turn the ledger tests green.
- Plan 03 must create `agents.pellegrini` exposing `build_pellegrini`, `handle_task`, `advise`, `propuesta_presupuesto`, `judge_advisory_quality` and register `finance.query`/`finance.record` base levels.

## Self-Check: PASSED
- All 11 created/modified files verified present on disk.
- All 3 task commits (ceb7641, 78b7fc5, 314d471) verified in git log.

---
*Phase: 08-primer-agente-de-dominio-finanzas*
*Completed: 2026-06-16*
