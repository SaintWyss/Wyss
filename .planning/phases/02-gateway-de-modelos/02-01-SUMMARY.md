---
phase: 02-gateway-de-modelos
plan: 01
subsystem: infra
tags: [httpx, respx, pytest-asyncio, gateway, domain, exceptions, uv]

# Dependency graph
requires:
  - phase: 01-fundaciones
    provides: "dominio frozen (AgentModelRequest, WyssError), ports, tests/ports fakes, patrón SQLite/WAL"
provides:
  - "deps del gateway instaladas y pineadas en uv.lock (httpx 0.28.1, respx 0.23.1, pytest-asyncio 1.4.0)"
  - "AgentModelRequest extendido con tier+purpose (defaults) — D-26"
  - "3 excepciones de dominio: SecretDetected, BudgetExceeded, UnknownTier (derivan de WyssError)"
  - "scaffolding tests/gateway/ con fixtures compartidas (respx_mock, http_client, audit, traces_db_path, make_request)"
  - "config/.env.example documenta ANTHROPIC_API_KEY y LITELLM_MASTER_KEY"
  - "markers pytest integration/gateway + asyncio_mode=auto"
affects: [02-02, 02-03, 02-04, 02-05]

# Tech tracking
tech-stack:
  added: [httpx>=0.28.1, respx (dev), pytest-asyncio (dev)]
  patterns:
    - "extensión aditiva de dominio frozen con defaults (no rompe construcciones de Fase 1)"
    - "excepciones de dominio fail-closed que solo cargan metadatos seguros (pattern_name, nunca el secreto)"
    - "fixtures de gateway: AuditPort reusado/inyectado nunca importado (independence)"

key-files:
  created:
    - config/.env.example (ya existía; documentado para el gateway)
    - tests/gateway/__init__.py
    - tests/gateway/conftest.py
    - tests/gateway/test_scaffolding.py
    - tests/domain/test_gateway_domain.py
  modified:
    - pyproject.toml
    - uv.lock
    - src/core/domain/gateway.py
    - src/core/domain/errors.py
    - src/core/domain/__init__.py

key-decisions:
  - "Re-export de las 3 excepciones desde core.domain (consistente con PolicyViolation/ConfigError ya re-exportados, aunque PATTERNS sugería import directo)"
  - "UnknownTier con available como kwarg-only (tuple[str, ...]) para firma clara y testeable"
  - "No instalar tenacity ni SDKs anthropic/openai (retry manual en 02-05; httpx directo evita doble-retry)"

patterns-established:
  - "Excepción fail-closed: el constructor solo recibe metadatos seguros (pattern_name), el valor sensible nunca entra a la clase (D-20)"
  - "tests/gateway/conftest provee fixtures compartidas para las olas que implementan cada componente"

requirements-completed: [GATE-01, GATE-02, GATE-03, GATE-04, GATE-05]

# Metrics
duration: 3min
completed: 2026-06-12
---

# Phase 2 Plan 01: Fundación del Gateway de Modelos Summary

**Deps del gateway pineadas (httpx/respx/pytest-asyncio), AgentModelRequest extendido con tier+purpose, 3 excepciones de dominio fail-closed (SecretDetected/BudgetExceeded/UnknownTier) y scaffolding tests/gateway/ listo — Fase 1 intacta.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-06-12T00:29:02Z
- **Completed:** 2026-06-12T00:31:57Z
- **Tasks:** 3
- **Files modified:** 10 (5 creados, 5 modificados)

## Accomplishments

- `uv add httpx` (runtime) + `respx`/`pytest-asyncio` (dev): versiones reales resueltas y pineadas en `uv.lock` (httpx 0.28.1, respx 0.23.1, pytest-asyncio 1.4.0), sin hardcodear.
- `AgentModelRequest` extendido con `tier="economico"` y `purpose="general"` por default (D-26) — las construcciones posicionales de Fase 1 siguen verdes.
- Tres excepciones de dominio nuevas derivadas de `WyssError`: `SecretDetected` (solo `pattern_name`, jamás el secreto — D-20), `BudgetExceeded` (veto pre-autorización — D-18), `UnknownTier` (expone `tier`+`available`, sin fallback — D-17).
- Scaffolding `tests/gateway/` con conftest de fixtures compartidas (`respx_mock`, `http_client`, `audit`=FakeAuditPort, `traces_db_path`, `make_request`) + test de scaffolding verde.
- `config/.env.example` documenta `ANTHROPIC_API_KEY` y `LITELLM_MASTER_KEY` (solo placeholders); `.env` confirmado en `.gitignore`.

## Task Commits

Cada tarea commiteada atómicamente:

1. **Task 1: Deps gateway + marker integration + env.example** - `c10c404` (chore)
2. **Task 2 (RED): tests fallidos dominio extendido** - `0ae35e2` (test)
3. **Task 2 (GREEN): AgentModelRequest +tier/purpose + 3 excepciones** - `ef332d1` (feat)
4. **Task 3: scaffolding tests/gateway** - `5add896` (test)

**Plan metadata:** (commit docs final)

_TDD: Task 2 siguió RED (0ae35e2) → GREEN (ef332d1); refactor no necesario._

## Files Created/Modified

- `pyproject.toml` - deps httpx + dev respx/pytest-asyncio; `asyncio_mode=auto`; markers `integration`/`gateway`
- `uv.lock` - versiones pineadas (resueltas contra PyPI real)
- `config/.env.example` - documentadas las 2 vars del gateway (placeholders)
- `src/core/domain/gateway.py` - `AgentModelRequest` +tier +purpose
- `src/core/domain/errors.py` - `SecretDetected`, `BudgetExceeded`, `UnknownTier`
- `src/core/domain/__init__.py` - re-export + `__all__` de las 3 excepciones
- `tests/domain/test_gateway_domain.py` - tests del dominio extendido (5 tests)
- `tests/gateway/__init__.py` - paquete de tests del gateway
- `tests/gateway/conftest.py` - fixtures compartidas del gateway
- `tests/gateway/test_scaffolding.py` - sanidad del scaffolding (4 tests verdes)

## Decisions Made

- **Re-export de las 3 excepciones desde `core.domain`**: PATTERNS sugería seguir el patrón de import directo, pero `PolicyViolation`/`ConfigError`/`AuditIntegrityError` YA se re-exportan en `core/domain/__init__.py` con su `__all__`. Para coherencia repliqué ese patrón existente (no inventé un re-export nuevo: ya era el patrón del repo para excepciones).
- **`UnknownTier(tier, *, available=...)`**: `available` como kwarg-only para una firma autodocumentada, alineada con el ejemplo de PATTERNS (`UnknownTier(tier, available=tuple(...))`).

## Deviations from Plan

None - plan executed exactly as written.

`config/.env.example` ya existía de la fase init con las dos variables requeridas; se enriqueció con comentarios sobre el propósito de cada key en el gateway (no constituye desviación: el acceptance criteria solo exigía que existieran los placeholders).

## Issues Encountered

- Ruff E501 (línea >100) en el docstring de `tests/gateway/conftest.py` al primer lint. Resuelto acortando las líneas del docstring antes del commit de Task 3. Sin impacto funcional.

## User Setup Required

None bloqueante en esta fase. `config/.env.example` documenta `ANTHROPIC_API_KEY` (opcional aquí — el shape de providers se testea con respx) y `LITELLM_MASTER_KEY` (del `.env` de litellm-local del owner). Las olas siguientes que ejecuten contra servicios reales necesitarán estas keys en `config/.env`.

## Next Phase Readiness

- Dominio extendido, excepciones y fixtures listos: las olas 02-02 a 02-05 (providers, router, minimizer, cost, traces) ya pueden importar de aquí y escribir tests sobre el scaffolding.
- Verificación global verde: `78 passed, 1 skipped` (el `ntfs` opt-in), `mypy` sin issues en 59 archivos, `lint-imports` 2 contratos KEPT.
- Sin blockers.

## Self-Check: PASSED

- Archivos creados/modificados: todos FOUND (gateway.py, errors.py, conftest.py, test_scaffolding.py, test_gateway_domain.py, .env.example, SUMMARY.md).
- Commits verificados en git log: c10c404, 0ae35e2, ef332d1, 5add896.

---
*Phase: 02-gateway-de-modelos*
*Completed: 2026-06-12*
