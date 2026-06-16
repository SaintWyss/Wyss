---
phase: 08-primer-agente-de-dominio-finanzas
plan: 03
status: complete
subsystem: bootstrap
tags: [cli, typer, rich, ledger, cost-gate, budget-wiring, finance-classification, hexagonal]

# Dependency graph
requires:
  - phase: 08-primer-agente-de-dominio-finanzas
    provides: "SqliteLedgerStore + Transaccion/TipoTransaccion + LedgerPort (08-02)"
  - phase: 02-gateway-de-modelos
    provides: "CostTracker.authorize per-agent budget gate (cost.py:87)"
  - phase: 07-modelo-de-agentes
    provides: "AgentConfigModel / [[agents]] config + _BASE_LEVELS classification surface"
provides:
  - "finance.query=A, finance.record=B in _BASE_LEVELS (policy-engine classification)"
  - "agent_budgets derived from [[agents]].budget_usd (RESEARCH Pitfall 1 closed at the source)"
  - "wyss fin sub-Typer: add-ingreso / add-gasto / ver — deterministic CLI write path (D-84)"
affects: [08-04-e2e-tasks]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Config-derived per-agent budget: [[agents]].budget_usd populates the gate's agent_budgets when no explicit [gateway.agent_budgets] value exists; explicit value wins (precedence rule)"
    - "Typer sub-Typer via app.add_typer(name=fin) for literal multi-word subcommands"
    - "CLI boundary amount validation (monto<=0 → exit 1) before any persistence (Pitfall 5)"
    - "Ledger gets its own SQLite file (ledger.db), separate from audit.db/pending.db"

key-files:
  created: []
  modified:
    - src/bootstrap/config.py
    - src/bootstrap/cli.py
    - tests/bootstrap/test_agent_budget_wiring.py

key-decisions:
  - "Precedence: explicit [gateway.agent_budgets] value WINS over derived [[agents]].budget_usd — no silent override; budget_usd==0.0 (default) derives nothing"
  - "finance.query=A, finance.record=B (confirmed against docs/10 §7: financial writes are NOT level D; §7 enumerates the D prohibitions and excludes them)"
  - "Updated the Plan-01 wiring test that encoded the un-fixed Pitfall-1 behavior to assert the new derived behavior + precedence (it was the GREEN target, mislabeled as still-RED in the plan's read_first)"
  - "Bare `wyss fin add-gasto -100 super` is parsed by Click as an unknown option (exit 2); the domain validation (exit 1) fires whenever the value reaches the command (via `--` or programmatically). Both paths reject the negative write — nothing persists."

requirements-completed: [AGENT-07, AGENT-09]

# Metrics
duration: ~30min
completed: 2026-06-16
---

# Phase 8 Plan 03: CLI Ledger Path + AGENT-07 Budget Wiring Summary

**First user-facing vertical slice: `wyss fin add-ingreso/add-gasto/ver` write the ledger deterministically with zero AI in the loop, `finance.query`/`finance.record` are now classified by the policy engine (A/B), and per-agent budgets are derived from `[[agents]].budget_usd` into the cost gate — closing RESEARCH Pitfall 1 at the source so every future agent (Belgrano next) inherits a wired budget. Full 4-tool gate green; the only remaining RED tests are the 10 `agents.pellegrini` contracts belonging to 08-04.**

## Performance
- **Duration:** ~30 min
- **Completed:** 2026-06-16
- **Tasks:** 2
- **Files modified:** 3 (0 created, 3 modified)

## Accomplishments
- **finance.* classification:** Added `finance.query → RiskLevel.A` and `finance.record → RiskLevel.B` to `_BASE_LEVELS`, confirmed against `docs/10 §7` (financial writes are not among the level-D prohibitions). The policy engine now classifies both action types instead of fail-closing record to C.
- **Budget wiring (Pitfall 1 closed):** New `_derive_agent_budgets(explicit, agents)` helper derives `agent_budgets[agent_id]` from each `[[agents]].budget_usd > 0` when no explicit `[gateway.agent_budgets]` entry exists. Wired through `_to_gateway_settings(model, agents)` ← `_to_settings`. `cost.py`/`gateway.py` untouched (D-85). The gate now provably blocks: a config with only `[[agents]].budget_usd = 5.0` produces `agent_budgets["pellegrini"] == 5.0`, and exhausting it raises `BudgetExceeded("...pellegrini...")`.
- **Deterministic CLI ledger path (D-84):** `fin_app` sub-Typer registered via `app.add_typer(fin_app, name="fin")` giving literal `wyss fin add-gasto`. Three commands: `add-ingreso <monto> <fuente>`, `add-gasto <monto> <categoria>`, `ver [--desde/--hasta]` — all persist/read against a dedicated `ledger.db` (own file, not audit/pending), with Rich output and the existing `try/except (ConfigError,AuditIntegrityError)/(OSError,sqlite3.Error)/finally` + `typer.Exit(code=1)` pattern. No gateway/LLM import or call in any `fin` body.
- **Amount validation (Pitfall 5 / T-08-06):** `_validate_monto` rejects `monto <= 0` with a red error + exit 1 before any persistence.

## Task Commits
1. **Task 1: wire finance.* risk levels + derive agent_budgets** — `f8235c7` (feat)
2. **Task 2: wyss fin sub-Typer add-ingreso/add-gasto/ver** — `413e455` (feat)

**Plan metadata:** _(this docs commit)_

## Files Created/Modified
- `src/bootstrap/config.py` — `_BASE_LEVELS` += finance.query=A/finance.record=B; new `_derive_agent_budgets` helper; `_to_gateway_settings` now takes the agents list and derives budgets; `_to_settings` passes `model.agents`.
- `src/bootstrap/cli.py` — `fin_app` sub-Typer + `fin_add_ingreso`/`fin_add_gasto`/`fin_ver` commands, `_ledger_db_path`/`_today_iso`/`_now_iso`/`_validate_monto`/`_print_ledger_table` helpers; added `Transaccion`/`TipoTransaccion`/`SqliteLedgerStore`/`Mapping` imports.
- `tests/bootstrap/test_agent_budget_wiring.py` — updated the formerly-Pitfall-1-documenting test to `test_agent_budget_usd_derives_gate_cap` (asserts derivation + gate veto) and added `test_explicit_gateway_budget_wins_over_derived` (precedence). Docstring rewritten to describe the closed behavior.

## Decisions Made
- **Budget precedence (Open Question 2 / Option b):** explicit `[gateway.agent_budgets]` value wins over the derived `[[agents]].budget_usd`; `budget_usd == 0.0` (the default) derives nothing (0 = "no per-agent cap"). This removes the two-unsynced-fields footgun for every future agent without breaking any explicit override.
- **finance.record = B, finance.query = A:** verified directly against `docs/10 §7` "Lo que un agente nunca puede hacer" — the level-D list (acceder a BC sin habilitación, ejecutar nivel D, dirigir/crear/modificar agentes, modificar propias habilitaciones/presupuesto, saltear orquestador, enviar secretos) does not include financial writes. B (second-wall confirmation) is correct, not C/D.
- **Ledger has its own file:** `data_dir / "ledger.db"`, separate from `audit.db`/`pending.db` per AI-SPEC §4 State Management.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The Plan-01 wiring test encoded the un-fixed Pitfall-1 behavior; updated to the GREEN target**
- **Found during:** Task 1
- **Issue:** The plan's `read_first` calls `tests/bootstrap/test_agent_budget_wiring.py` "the RED contract this must turn GREEN," but it was already GREEN and its `test_only_agent_budget_usd_leaves_gate_cap_unset` asserted `"pellegrini" not in settings.gateway.agent_budgets` — the exact opposite of the plan's required derivation behavior (behavior spec line 90). Implementing the derivation necessarily breaks that assertion.
- **Fix:** Replaced it with `test_agent_budget_usd_derives_gate_cap` (asserts the cap is now derived to 5.0 and the gate vetoes) and added `test_explicit_gateway_budget_wins_over_derived` for the precedence rule; rewrote the module docstring.
- **Files modified:** tests/bootstrap/test_agent_budget_wiring.py
- **Verification:** `pytest tests/bootstrap/test_agent_budget_wiring.py -q` → 3 passed.
- **Committed in:** f8235c7

**2. [Rule 1 - Behavior boundary] Bare negative amount `-100` is a Click parse error (exit 2), not the domain exit-1**
- **Found during:** Task 2
- **Issue:** Acceptance criterion expects `wyss fin add-gasto -100 super` → exit 1 via `_validate_monto`. Typer/Click parses a leading-dash token as an unknown option and exits 2 before the command body runs, so the domain validation never sees `-100`.
- **Fix:** Kept `_validate_monto` (exit 1) which fires whenever the value reaches the command (via `--` separator or programmatic call, both verified exit 1). The intent — reject the negative write — holds on every path: exit 2 (bare) or exit 1 (`--`), and nothing persists in either case. Disabling Click option parsing to force exit 1 on a leading dash would be worse UX; this is idiomatic Typer behavior.
- **Files modified:** src/bootstrap/cli.py (validation present as designed)
- **Verification:** `fin add-gasto -- -100 super` → exit 1 red error; `fin add-gasto 0 super` → exit 1; bare `-100` → exit 2; subsequent `ver` shows the negative never persisted.
- **Committed in:** 413e455

**Total deviations:** 2 auto-fixed. Neither is scope creep — #1 corrects a stale plan premise (the test documented the bug the plan closes), #2 documents a CLI-parser reality while preserving the security guarantee.

## TDD Gate Compliance
Task 1 is `tdd="true"`: the RED gate is Plan 01's `test(...)` commit `314d471` (the budget-wiring contracts). This plan turns the derivation behavior GREEN via `feat` commit `f8235c7` (implementation + updated contract test). The finance-classification assertion is exercised by the verify command and the pre-existing second-wall routing test (`>= RiskLevel.B`, still GREEN at B). No REFACTOR needed.

## Green Chain
- `uv run pytest -q` → **413 passed**, 6 skipped, **10 failed** — all 10 are `agents.pellegrini` ModuleNotFoundError (08-04 scope: Pellegrini agent E2E, second-wall agent build, no-fabrication). Passing count rose 410 → 413 (+3 budget tests; net +1 new precedence test, +2 from the rewritten/expanded wiring file vs the prior 2).
- `uv run mypy` → no issues in 187 source files.
- `uv run ruff check src tests` → all checks passed.
- `uv run lint-imports` → 2 contracts kept, 0 broken (core puro + layer independence; bootstrap→ledger allowed as composition root).
- `cost.py`/`gateway.py` → `git diff --stat` empty (untouched, D-85 honored).
- AGENT-07 provable block: `test_agent_budget_usd_derives_gate_cap` records 5.0 then asserts `pytest.raises(BudgetExceeded, match="pellegrini")` on the next `authorize`.

## Threat Mitigations Applied
- **T-08-06 (Tampering, amount input):** mitigated — `_validate_monto` rejects `monto <= 0` at the CLI boundary (exit 1); ledger writes remain parameterized (Plan 02 guarantee).
- **T-08-07 (EoP, budget wiring):** mitigated — budget cap is read-only config → gate (`_derive_agent_budgets` only reads config at boot); no runtime setter introduced (D-19 preserved); `cost.py` untouched.
- **T-08-08 (Spoofing, finance.* classification):** mitigated — `finance.record=B` routes mutations through the policy engine; explicit `_BASE_LEVELS` entry means it is never classifiable below A by accident.

## Known Stubs
None. The CLI commands wire real persistence and aggregations end-to-end against `SqliteLedgerStore`.

## Next Phase Readiness
- 08-04 can now exercise the budget cutoff E2E against a config-derived `agent_budgets["pellegrini"]=5.0` and build `agents.pellegrini` (the 10 remaining RED tests). The deterministic ledger write path and `finance.*` classification are both live.

## Self-Check: PASSED
- All 3 modified files verified present and contain the changes (config.py `_derive_agent_budgets` + finance.record; cli.py fin_app; test rewrite).
- Both task commits (`f8235c7`, `413e455`) verified in git log.
- Green chain clean on all 4 gating dimensions; only deferred 08-04 RED tests remain.

---
*Phase: 08-primer-agente-de-dominio-finanzas*
*Completed: 2026-06-16*
