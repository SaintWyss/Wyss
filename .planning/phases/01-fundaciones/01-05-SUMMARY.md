---
phase: 01-fundaciones
plan: 05
subsystem: core/policy
tags: [policy, security, cognitive-engine, denylist, anti-bypass]
requires:
  - core.domain.plan (Plan, Action)
  - core.domain.policy (DenyRule, PolicyRules, AggregateThresholds, PolicyDecision)
  - core.domain.risk (RiskLevel, Outcome, outcome_for)
provides:
  - core.policy.BUILTIN_DENY (Final, 7 reglas D no removibles)
  - core.policy.CognitivePolicyEngine (evaluate puro Plan -> PolicyDecision)
affects:
  - Fase 5 (orquestador): gatea cada plan vía CognitivePolicyEngine
  - Fase 9 (Hermes adapter): toda acción real pasa por este engine fail-closed
tech-stack:
  added: []
  patterns:
    - "denylist aditiva Final (config solo agrega, nunca vacía)"
    - "max() sobre IntEnum = subir sí, bajar jamás (POL-04)"
    - "agregación a nivel-plan anti-bypass por composición (POL-05)"
    - "fail-closed: action_type desconocido -> C, nunca A"
key-files:
  created:
    - src/core/policy/builtin_deny.py
    - src/core/policy/engine.py
    - tests/policy/__init__.py
    - tests/policy/conftest.py
    - tests/policy/test_golden_plans.py
    - tests/policy/test_aggregation.py
  modified:
    - src/core/policy/__init__.py
decisions:
  - "Engine sin evaluate_action() público — evaluar por-acción saltearía los agregados (bypass)"
  - "Targets sensibles tipo dir (~/.ssh, /etc) se expanden a `<dir>/**` para fnmatch; los globs (**/.env*) van tal cual"
  - "mass-delete recursivo se modela con params_equal en BUILTIN_DENY; el umbral >50 lo evalúa _matches_aggregate"
metrics:
  duration: "~12 min"
  completed: 2026-06-11
  tasks: 3
  files: 7
---

# Phase 1 Plan 5: CognitivePolicyEngine Summary

CognitivePolicyEngine puro (`Plan -> PolicyDecision`) con denylist built-in `Final` no vaciable por config, agregación anti-bypass a nivel-plan (POL-05) y combinación `max()` donde `estimated_risk` solo sube el nivel (POL-04) — cierra el gap raíz del stub `core/policy/__init__.py`.

## What Was Built

- **`src/core/policy/builtin_deny.py`** — `BUILTIN_DENY: Final[tuple[DenyRule, ...]]` con 7 reglas D conservadoras (mass-delete, wyss-self-modify, audit-tamper, secret-exfiltration, system-files-write, git-force-push-main, disk-format). Solo stdlib (`typing.Final`) + `core.domain`. Documentado como no removible por config (regla #2 del owner).
- **`src/core/policy/engine.py`** — `CognitivePolicyEngine.evaluate(plan)` con el algoritmo de 5 pasos: hit de denylist → D incondicional (REJECT); si no, `final = max(per_action, aggregate, estimated or A)`. Helpers privados `_matches` (fnmatch sobre type/target + subset de params_equal), `_matches_aggregate` (mass-delete > delete_count_d), `_base_level` (fail-closed a C), `_aggregate_level` (conteos a nivel-plan: targets/dirs distintos, cualquier delete → C, target sensible en write → C). Sin API pública por-acción.
- **`src/core/policy/__init__.py`** — re-export de `BUILTIN_DENY` y `CognitivePolicyEngine` con `__all__` (reemplaza el stub de docstring).
- **`tests/policy/`** — 23 tests: 15 golden plans (A/B/C/D, una por regla de denylist), POL-04 (estimated sube/no baja), fail-closed unknown→C, test de bypass por composición (200 deletes → D), 60 writes / 6 dirs → C, y `engine_sin_config` (base_levels vacío sigue clasificando D la denylist).

## Verification Results

- `uv run pytest` → **60 passed, 1 skipped** (23 nuevos en tests/policy + 37 previos)
- `uv run mypy` → **no issues found in 51 source files**
- `uv run ruff check src tests` → **All checks passed!**
- `uv run lint-imports` → **2 kept, 0 broken** (core/policy sigue stdlib-only)
- `from core.policy import CognitivePolicyEngine, BUILTIN_DENY` → exit 0

## Success Criteria

- **SC2** ✓ — el engine clasifica golden plans A/B/C/D, D por denylist determinística sin LLM.
- **SC3** ✓ — plan compuesto de 200 deletes individuales (cada uno C) se clasifica D (test de bypass por composición pasa).
- **POL-04** ✓ — `estimated_risk` solo sube vía `max()` sobre IntEnum (test explícito: delete+estimated=A sigue C).
- **POL-05** ✓ — agregados evaluados sobre el plan entero en `_aggregate_level` y `_matches_aggregate`.
- **Denylist no vaciable** ✓ — `engine_sin_config` (base_levels vacío) sigue clasificando D los golden plans de denylist.

## Threat Model Coverage

| Threat ID | Disposition | Evidencia |
|-----------|-------------|-----------|
| T-01-05-EoP-1 (elevación vía vaciar denylist) | mitigate ✓ | `BUILTIN_DENY` es `Final`; test `test_empty_config_still_denies_D` |
| T-01-05-EoP-2 (estimated_risk baja nivel) | mitigate ✓ | `max(...)` sobre IntEnum; test `test_estimated_risk_no_baja_el_nivel` |
| T-01-05-EoP-3 (bypass por composición) | mitigate ✓ | `_aggregate_level`/`_matches_aggregate`; test `test_composition_bypass_200_deletes_es_D` |
| T-01-05-T (action_type desconocido) | mitigate ✓ | `_base_level` fail-closed a C; test `test_unknown_action_type_es_C_no_A` |

## Deviations from Plan

None - plan executed exactly as written. Único ajuste menor: dos docstrings se acortaron para respetar el límite de 100 columnas de ruff (E501) — cosmético, sin cambio de comportamiento.

## Commits

- `2caecd2` feat(01-05): BUILTIN_DENY — 7 reglas D Final no removibles por config
- `e68954d` feat(01-05): CognitivePolicyEngine — clasificación + agregación + max
- `4ead44b` test(01-05): golden plans A/B/C/D + bypass por composición + denylist-sin-config

## Known Stubs

None — el stub previo (`core/policy/__init__.py` de 1 línea) quedó resuelto: ahora re-exporta el engine real.

## Self-Check: PASSED

Todos los archivos creados existen en disco; los 3 commits (2caecd2, e68954d, 4ead44b) están en el historial.
