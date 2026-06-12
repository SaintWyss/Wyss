---
phase: 02-gateway-de-modelos
plan: 02
subsystem: gateway
tags: [minimizer, secrets, fail-closed, security, regex, gateway, tdd]

# Dependency graph
requires:
  - phase: 02-gateway-de-modelos
    plan: 01
    provides: "SecretDetected (core.domain.errors), scaffolding tests/gateway/, fixtures compartidas"
  - phase: 01-fundaciones
    provides: "patrón BUILTIN_DENY Final no-vaciable (core.policy.builtin_deny), engine puro inyectado"
provides:
  - "BUILTIN_SECRET_PATTERNS Final[tuple] con 8 patrones verificados, no vaciable por config (D-21)"
  - "ContextMinimizer.scan fail-closed de 3 fuentes (env_values + built-in + config aditivo)"
  - "suite de seguridad del minimizer: fixture secreto trampa multi-formato (GATE-03, criterion 2)"
affects: [02-03, 02-04, 02-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "minimizer fail-closed: detección → SecretDetected → la llamada NO sale (D-20), nunca redacta"
    - "merge aditivo BUILTIN_SECRET_PATTERNS + config_patterns (espejo de deny = BUILTIN_DENY + config)"
    - "el valor del secreto jamás entra a la excepción ni al audit; solo viaja el pattern_name"

key-files:
  created:
    - src/gateway/secrets_patterns.py
    - src/gateway/minimizer.py
    - tests/gateway/test_minimizer.py
  modified: []

key-decisions:
  - "env_values filtrados a len>=8 en el constructor para evitar falsos positivos de strings triviales"
  - "openai_key (sk-) es un prefijo subsumido por anthropic_key (sk-ant-): el orden built-in pone anthropic primero, así sk-ant- matchea su nombre específico"
  - "PEM detectado por header multilínea explícito (no por el cuerpo base64) — baja tasa de falso negativo sin falsos positivos de base64 legítimo"

patterns-established:
  - "ContextMinimizer sigue el patrón de CognitivePolicyEngine: clase pura, patrones inyectados por constructor, sin IO"
  - "test de seguridad parametrizado con fixture trampa que verifica además que el secreto nunca se loguea (D-20)"

requirements-completed: [GATE-03]

# Metrics
duration: 5min
completed: 2026-06-12
---

# Phase 2 Plan 02: Context Minimizer Fail-Closed Summary

**ContextMinimizer (GATE-03) implementado: el último checkpoint antes de la frontera de red detecta secretos de 3 fuentes (env_values del .env + 8 regex built-in no-vaciables + config aditivo) y levanta SecretDetected fail-closed — la llamada NUNCA sale (D-20) y el valor del secreto jamás se loguea.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-12T00:33Z
- **Completed:** 2026-06-12T00:37Z
- **Tasks:** 2
- **Files created:** 3

## Accomplishments

- `BUILTIN_SECRET_PATTERNS: Final[tuple[...]]` con los 8 patrones verificados (anthropic `sk-ant-`, openai `sk-`, aws `AKIA`, github `ghp_`, github_fine `github_pat_`, `jwt` eyJ..., `pem_private` header multilínea, slack `xox`). Docstring justifica el `Final` espejo de `BUILTIN_DENY`: si config pudiera vaciarlos, la minimización dejaría de ser absoluta editando un archivo (D-21, regla #4/#8).
- `ContextMinimizer` clase pura (patrón de `CognitivePolicyEngine`): patrones inyectados por constructor, merge aditivo `BUILTIN_SECRET_PATTERNS + config_patterns`, `scan()` fail-closed de 3 fuentes. Bloquea primero por env_value (substring exacto, no nombra el valor), luego por regex; si nada matchea devuelve el prompt.
- `env_values` filtrados a `len >= 8` en el constructor: descarta strings triviales (puertos, flags) que generarían falsos positivos.
- Suite de seguridad parametrizada en `tests/gateway/test_minimizer.py` (21 tests): cada formato trampa bloquea, el secreto plantado nunca aparece en `pattern_name` ni `str(exc)` (D-20), sin falso positivo en prompt realista, built-ins activos con config vacío.

## Task Commits

Cada tarea commiteada atómicamente:

1. **Task 1 (RED): tests fallidos del minimizer** - `a4946ae` (test)
2. **Task 1 (GREEN): BUILTIN_SECRET_PATTERNS Final + ContextMinimizer fail-closed** - `c34fd04` (feat)
3. **Task 2: security suite con fixture secreto trampa multi-formato** - `bd4ed54` (test)

**Plan metadata:** (commit docs final)

_TDD: Task 1 siguió RED (a4946ae, ModuleNotFoundError) → GREEN (c34fd04); refactor no necesario._

## Files Created/Modified

- `src/gateway/secrets_patterns.py` - `BUILTIN_SECRET_PATTERNS` Final con 8 patrones (solo stdlib `re`/`typing.Final`)
- `src/gateway/minimizer.py` - `ContextMinimizer.scan` fail-closed de 3 fuentes, merge aditivo
- `tests/gateway/test_minimizer.py` - 21 tests: behaviors de Task 1 + suite de seguridad parametrizada de Task 2

## Decisions Made

- **`env_values` filtrados a `len>=8`**: el constructor descarta valores triviales para que un string corto del .env (un puerto, un flag) no bloquee prompts normales. Es la red de alta precisión (substring exacto) complementada por los regex de formato.
- **Orden built-in anthropic antes que openai**: `sk-` (openai) es prefijo de `sk-ant-` (anthropic). Con anthropic primero en la tupla, un `sk-ant-...` reporta su nombre específico `anthropic_key` (más preciso para el audit); ambos siguen bloqueando fail-closed de todos modos.
- **PEM por header multilínea explícito**: el regex matchea el header `-----BEGIN ... PRIVATE KEY-----` (no el cuerpo base64), evitando falsos positivos de base64 legítimo en prompts (Pitfall 3).

## Deviations from Plan

None - plan executed exactly as written.

El plan describía los behaviors de Task 1 viviendo en `test_minimizer.py` (mismo archivo que Task 2 expande): se respetó escribiendo primero los 5 tests RED de Task 1 en ese archivo y luego agregando la suite de seguridad parametrizada en Task 2, sin sobrescribir los tests previos.

## Issues Encountered

- Ruff E501 (línea >100) en la tupla `_TRAP_CASES` del caso `env_value` (el valor trampa aparecía dos veces en la misma línea). Resuelto extrayendo `_ENV_TRAP` a una constante antes del commit de Task 2. Sin impacto funcional.

## Threat Model Compliance

Las 3 mitigaciones del threat register están implementadas y testeadas:

- **T-02-secret-egress** (mitigate): `scan()` fail-closed; fixture trampa multi-formato bloquea cada formato; 3 fuentes (env_value + regex + config).
- **T-02-secret-log** (mitigate): test verifica que ni `pattern_name` ni `str(exc)` contienen el valor del secreto plantado (D-20, V7).
- **T-02-patterns-tamper** (mitigate): `BUILTIN_SECRET_PATTERNS` es `Final[tuple]`, merge aditivo, test de no-vaciable con config vacío (D-21).

## Known Stubs

None — el componente está completamente cableado: `ContextMinimizer.scan` opera sobre datos reales (prompt + env_values + config_patterns) y bloquea de verdad. La integración del minimizer en el flujo del gateway (cargar `env_values` reales del .env al boot e invocar `scan()` antes de cada provider call) corresponde a la ola del orquestador del gateway (02-03+).

## Next Phase Readiness

- `ContextMinimizer` listo para que la ola que ensambla el gateway lo invoque antes de cada llamada externa. El caller debe construirlo con `env_values` = valores reales del `.env` cargados al boot y `config_patterns` = patrones extra de la config TOML.
- Verificación global verde: `99 passed, 1 skipped`, `mypy` sin issues en 62 archivos, `lint-imports` 2 contratos KEPT, `ruff` clean.
- Sin blockers.

## Self-Check: PASSED

- Archivos creados: src/gateway/secrets_patterns.py, src/gateway/minimizer.py, tests/gateway/test_minimizer.py — todos FOUND.
- Commits verificados en git log: a4946ae (RED), c34fd04 (GREEN feat), bd4ed54 (security suite).

---
*Phase: 02-gateway-de-modelos*
*Completed: 2026-06-12*
