---
phase: 01-fundaciones
plan: 04
subsystem: security
tags: [policy, agent-base, fail-closed, isinstance, enum, cr-01]

# Dependency graph
requires:
  - phase: 01-fundaciones
    provides: AgentBase template method en core/ports/agent.py (01-02), RiskLevel/Outcome IntEnum y PolicyDecision en core/domain (01-02)
provides:
  - "AgentBase.execute con guarda de rechazo D por valor/orden (>=, ==) en vez de identidad (is)"
  - "Guarda isinstance fail-closed ante PolicyDecision con tipos no-enum (int crudo de deserializacion)"
  - "Payload del evento de rechazo incluye decision.reasons (trazabilidad T-01-04-R)"
affects: [orquestador, daemon-ipc, policy-engine, fase-5-jsonrpc]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Comparacion de enums por valor/orden (==, >=) en fronteras de confianza, nunca por identidad (is)"
    - "isinstance guard fail-closed antes de cualquier ejecucion cuando un dato cruza una frontera de deserializacion"

key-files:
  created: []
  modified:
    - src/core/ports/agent.py
    - tests/ports/test_agent_base.py

key-decisions:
  - "Rechazo D comparado por valor/orden (risk >= RiskLevel.D, outcome == Outcome.REJECT) tras isinstance guard, no por identidad de singleton"
  - "Tipo no-enum (int crudo) entra al bloque de rechazo fail-closed: nunca se invoca _run() ante datos corruptos"
  - "decision.reasons agregado al payload del evento POLICY_DECISION del rechazo (T-01-04-R)"

patterns-established:
  - "Enum-comparison-by-value: en codigo de seguridad comparar IntEnum por == / >=, no por is — la identidad falla ante valores deserializados"
  - "Fail-closed-isinstance: validar isinstance del enum antes de actuar; tipo invalido = rechazo, nunca ejecucion"

requirements-completed: [POL-03]

# Metrics
duration: ~12min
completed: 2026-06-11
---

# Phase 01 Plan 04: Cierre CR-01 — guarda de rechazo D fail-closed Summary

**AgentBase.execute ahora rechaza nivel D / REJECT por valor/orden con isinstance fail-closed, cerrando el BLOCKER CR-01: una PolicyDecision con ints crudos (deserializacion JSON-RPC) ya no puede saltear el rechazo estructural de POL-03.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-11T19:19:47Z
- **Completed:** 2026-06-11
- **Tasks:** 2 (TDD: 1 RED, 1 GREEN)
- **Files modified:** 2

## Accomplishments
- Test de regresion CR-01: dos casos de bypass por int crudo (`risk_level=4`, `outcome=3` y `outcome=1`) que demuestran que la guarda `is` era un no-op.
- Fix CR-01: guarda reescrita a `not isinstance(risk, RiskLevel) or not isinstance(outcome, Outcome) or outcome == Outcome.REJECT or risk >= RiskLevel.D` — comparacion por valor/orden + fail-closed.
- Trazabilidad mejorada: el payload del evento de rechazo POLICY_DECISION ahora incluye `decision.reasons` (T-01-04-R).
- POL-03 cumplido estructuralmente: nivel D es imposible de saltear incluso ante tipos no-enum.

## Task Commits

Each task was committed atomically:

1. **Task 1: Test de regresion CR-01 (RED)** - `e09e83f` (test)
2. **Task 2: Fix CR-01 — guarda por valor/orden + isinstance fail-closed (GREEN)** - `626ec73` (fix)

**Plan metadata:** (final docs commit)

_Note: plan TDD — RED (test) seguido de GREEN (fix). No requirio REFACTOR._

## Files Created/Modified
- `src/core/ports/agent.py` - Guarda de `execute()` reescrita: identidad (`is`) reemplazada por isinstance fail-closed + comparacion por valor/orden; `reasons` agregado al payload del rechazo.
- `tests/ports/test_agent_base.py` - Dos tests nuevos de bypass por int crudo (`test_raw_int_level_d_does_not_bypass_rejection`, `test_raw_int_corrupt_types_fail_closed`); los 5 tests existentes intactos.

## Decisions Made
- Rechazo D comparado por valor/orden (`>=`, `==`) tras `isinstance` guard, no por identidad de singleton — la identidad fallaba ante valores deserializados de JSON-RPC (Fase 5).
- Tipos no-enum entran al bloque de rechazo fail-closed: el payload usa `risk.name if isinstance(...) else repr(...)` para auditar incluso valores corruptos sin romper.
- `decision.reasons` agregado al payload del evento de rechazo per T-01-04-R.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] E501 line-too-long en docstrings tras el fix**
- **Found during:** Task 2 (fix CR-01)
- **Issue:** El docstring extendido de `execute()` y el docstring del primer test nuevo superaban los 100 columnas; `uv run ruff check` reportaba 4 errores E501.
- **Fix:** Reformateo de las lineas del docstring de `execute()` y acortamiento del docstring de `test_raw_int_level_d_does_not_bypass_rejection`. Sin cambio de logica.
- **Files modified:** src/core/ports/agent.py, tests/ports/test_agent_base.py
- **Verification:** `uv run ruff check src tests` → "All checks passed!"
- **Committed in:** `626ec73` (parte del commit de Task 2)

---

**Total deviations:** 1 auto-fixed (1 bug de formato)
**Impact on plan:** Fix de formato necesario para pasar la cadena verde. Sin scope creep — solo whitespace de docstrings.

## Issues Encountered
None — el patron TDD funciono limpio: tests en RED contra el codigo con `is`, GREEN tras el fix por valor.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- BLOCKER CR-01 cerrado: la guarda de rechazo D es estructural y fail-closed.
- La frontera de deserializacion JSON-RPC de Fase 5 ya esta protegida en el nivel AgentBase.
- Cadena canonica completa verde: `uv run pytest` (37 passed, 1 skipped), `uv run mypy` (no issues, 45 files), `uv run ruff check src tests` (All checks passed), `uv run lint-imports` (2 kept, 0 broken).

## Self-Check: PASSED

- FOUND: src/core/ports/agent.py
- FOUND: tests/ports/test_agent_base.py
- FOUND: .planning/phases/01-fundaciones/01-04-SUMMARY.md
- FOUND commit: e09e83f (Task 1 RED)
- FOUND commit: 626ec73 (Task 2 GREEN)

---
*Phase: 01-fundaciones*
*Completed: 2026-06-11*
