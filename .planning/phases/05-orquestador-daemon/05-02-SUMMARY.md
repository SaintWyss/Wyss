---
phase: 05-orquestador-daemon
plan: 02
type: execute
status: complete
wave: 1
executor: codex (codex-gsd-exec, reasoning=high)
verified_by: opus (cadena verde re-corrida + review dominio)
---

---
phase: 05-orquestador-daemon
plan: 02
subsystem: orchestrator-domain
tags: [policy, orchestrator, intent, plan-schema, golden-tests]

requires:
  - phase: 01-fundaciones
    provides: CognitivePolicyEngine, Plan/Action, RiskLevel, ports pattern
provides:
  - Action.on_error schema with ErrorPolicy and RetryParams
  - OrchestratorPort protocol for Hermes adapter
  - IntentCategory and IntentClassification pure domain model
  - POL-06 golden NL→risk gate with 21 deterministic fixtures
affects: [phase-05, phase-06, orchestrator, execution]

tech-stack:
  added: []
  patterns:
    - frozen dataclass domain schema
    - Protocol port contract
    - deterministic golden policy gate

key-files:
  created:
    - src/core/orchestrator/__init__.py
    - src/core/orchestrator/intent.py
    - src/core/ports/orchestrator.py
  modified:
    - src/core/domain/plan.py
    - src/core/domain/errors.py
    - src/core/domain/__init__.py
    - src/core/ports/__init__.py
    - tests/domain/test_plan_on_error.py
    - tests/orchestrator/test_intent_router.py
    - tests/policy/test_golden_nl_plans.py

key-decisions:
  - "Action.on_error defaults to ErrorPolicy.ABORT for fail-safe retro-compatibility."
  - "Intent model lives under core.orchestrator and remains pure: no IO, Hermes, MCP, or Pydantic."
  - "POL-06 fixtures construct Plan objects by hand so the gate measures CognitivePolicyEngine with Hermes DOWN."

patterns-established:
  - "Schema-only error policy on Action; enforcement deferred to Phase 6."
  - "OrchestratorPort classifies/drafts/health-checks but never assigns A/B/C/D risk."
  - "Every destructive C/D NL golden case name includes the literal FALSO-A CATASTROFICO."

requirements-completed: [ORCH-03, ORCH-04, ORCH-07, POL-06]

duration: not recorded
completed: 2026-06-13
---

# Phase 05 Plan 02: Dominio Puro Orquestador Summary

**Plan schema, orchestrator intent contract, and deterministic anti-falso-A policy gate are in place.**

## Accomplishments

- Extended `Action` with `ErrorPolicy` and `RetryParams` while preserving existing positional callsites.
- Added pure `IntentCategory`/`IntentClassification` and `OrchestratorPort` contracts for later Hermes integration.
- Replaced Wave 0 skips with real tests, including 21 POL-06 NL→Plan→Risk fixtures.

## Verification

Cadena verde final:

```bash
UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/ -q && \
UV_CACHE_DIR=/tmp/uvcache uv run mypy && \
UV_CACHE_DIR=/tmp/uvcache uv run ruff check src tests && \
UV_CACHE_DIR=/tmp/uvcache uv run lint-imports
```

Resultado:

```text
311 passed, 11 skipped in 11.83s
Success: no issues found in 139 source files
All checks passed!
Contracts: 2 kept, 0 broken.
```

## Deviations from Plan

- No se creó `.planning/phases/05-orquestador-daemon/05-02-SUMMARY.md` porque la regla dura del pedido fue no tocar `.planning/`.
- No hubo commits porque la regla dura del pedido fue no commitear.

## Issues Encountered

- One initial POL-06 fixture expected C for `~/.ssh/config`, but the existing denylist correctly classifies that as D via `secret-exfiltration`. The fixture was changed to a non-denylist local config write while keeping C coverage.

## Next Phase Readiness

Ready for 05-03. The domain contracts and golden gate are green, and `lint-imports` confirms the core boundary remains pure.