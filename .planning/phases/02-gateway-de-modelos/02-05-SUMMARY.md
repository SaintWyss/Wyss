---
phase: 02-gateway-de-modelos
plan: 05
subsystem: gateway
tags: [facade, flow4, retry, composition-root, e2e-security, pydantic, bootstrap, tdd]

# Dependency graph
requires:
  - phase: 02-gateway-de-modelos
    plan: 02
    provides: "ContextMinimizer.scan fail-closed (env_values + built-in + config aditivo)"
  - phase: 02-gateway-de-modelos
    plan: 03
    provides: "ModelRouter, TierConfig (core.domain.gateway), LiteLLM/Anthropic providers, FakeModelProvider"
  - phase: 02-gateway-de-modelos
    plan: 04
    provides: "CostTracker.authorize/estimate_cost/record (gate pre-call), TraceStore.write/query (traces.db WAL)"
  - phase: 01-fundaciones
    provides: "AuditPort, AuditEvent.new, patrón Pydantic→dominio en bootstrap/config.py, WyssSettings frozen"
provides:
  - "ModelGateway.ask() — fachada que orquesta Flow 4 (router→minimizer→authorize→provider(retry)→record→trace→audit) y devuelve ModelResponse con costo LOCAL"
  - "retry centralizado D-25: 2x transiente (timeout/429/5xx), 4xx fail-fast, gate re-pasado cada intento, sin fallback de tier"
  - "GatewaySettings frozen (core.domain.config) + sección [gateway] validada Pydantic (extra=forbid) en bootstrap/config.py"
  - "bootstrap.gateway.build_gateway — composition root: WyssSettings→ModelGateway completo con AuditPort inyectado"
  - "tests e2e de seguridad (anclas de aceptación de la fase): secreto trampa sin egress, presupuesto bloquea pre-call, happy path con trace consultable"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "facade + retry manual centralizado en el gateway (nunca en providers): evita doble-retry que descontrola el gate (Pitfall 1, D-25)"
    - "Flow 4 fail-closed: minimizer.scan ANTES de cualquier provider.complete; authorize re-pasado en cada intento"
    - "composition root (Pattern 4): único módulo que cablea adapters + application + facade; AuditPort inyectado, nunca import audit"
    - "API keys solo de os.environ (V2): jamás en config.toml, traces, AuditEvent ni ModelResponse"
    - "GatewaySettings default vacío en WyssSettings → configs de Fase 1 sin [gateway] siguen cargando"

key-files:
  created:
    - src/gateway/gateway.py
    - src/bootstrap/gateway.py
    - tests/gateway/test_gateway.py
    - tests/gateway/test_retry.py
    - tests/gateway/test_e2e_security.py
    - tests/bootstrap/test_gateway_config.py
  modified:
    - src/gateway/__init__.py
    - src/core/domain/config.py
    - src/core/domain/__init__.py
    - src/bootstrap/config.py
    - src/gateway/traces.py
    - config/config.example.toml

key-decisions:
  - "GatewaySettings con default vacío en WyssSettings (tiers={}, prices={}, global_budget=0.0): no rompe configs de Fase 1 sin sección [gateway], y mantiene WyssSettings construible sin gateway en fakes existentes"
  - "env_values del minimizer salen de os.environ filtrado por _GATEWAY_ENV_KEYS (ANTHROPIC_API_KEY, LITELLM_MASTER_KEY) al boot — solo los VALORES, los nombres viven en código"
  - "traces.db chmod 0600 dentro de TraceStore (no en build_gateway): cubre siempre que se crea la DB, best-effort con contextlib.suppress(OSError) para FS sin modos POSIX (NTFS)"
  - "config_patterns en GatewaySettings lleva SOLO los de config (name, regex-string); el merge con BUILTIN_SECRET_PATTERNS lo hace el minimizer en runtime (D-21 aditivo)"

patterns-established:
  - "ModelGateway.ask es el ÚNICO punto de salida a IA externa con las 7 garantías de Flow 4 probadas e2e"
  - "_is_transient(exc) clasifica 429/5xx como retry, 4xx como fail-fast (Pitfall 1)"

requirements-completed: [GATE-01, GATE-02, GATE-03, GATE-04, GATE-05]

# Metrics
duration: 10min
completed: 2026-06-12
---

# Phase 2 Plan 05: ModelGateway Facade + Composition Root + E2E Security Summary

**ModelGateway.ask() cierra la Fase 2: orquesta Flow 4 (router→minimizer fail-closed→cost.authorize pre-call→provider con retry 2x transiente que re-pasa el gate→cost.record local→trace→audit), el composition root arma el gateway completo desde WyssSettings con AuditPort inyectado, y los tests e2e prueban de punta a punta que el secreto trampa nunca egresa, el presupuesto agotado bloquea antes de gastar y cada llamada deja trace consultable.**

## Performance

- **Duration:** ~10 min
- **Tasks:** 3 (Task 1 y 2 TDD: RED→GREEN; Task 3 integración)
- **Files modified:** 12 (6 creados, 6 modificados)

## Accomplishments

- **`src/gateway/gateway.py` — `ModelGateway`**: implementa `ModelGatewayPort.ask` y compone los 7 pasos de Flow 4 en orden EXACTO. Minimizer fail-closed ANTES de cualquier egress (D-20); `authorize()` RE-PASADO en cada intento del loop de retry (D-18/D-25); retry 2x SOLO en transiente (timeout/429/5xx vía `_is_transient`), 4xx fail-fast (Pitfall 1), sin fallback de tier (D-17); `ModelRequest` con model_alias + max_tokens del TIER (D-16); devuelve `dataclasses.replace(resp, cost_usd=cost)` con el costo LOCAL (D-24). `AuditPort` inyectado — el módulo nunca importa el paquete `audit` (Pitfall 4, verificado por un test que escanea el source).
- **`src/core/domain/config.py` — `GatewaySettings`** frozen: tiers, prices, global_budget, agent_budgets, timeout_s (120 default, D-25), trace_retention_days (90 default, D-22), env_values, config_patterns. `WyssSettings.gateway` lo expone con default vacío.
- **`src/bootstrap/config.py`**: `TierConfigModel`/`SecretPatternModel`/`GatewayConfigModel` (todos `extra="forbid"`), `gateway` agregado a `WyssConfigModel`, `_to_gateway_settings` (Pydantic→dominio, compila/valida regex → ConfigError fail-fast), `_gateway_env_values()` lee os.environ. config_patterns aditivos (built-ins los agrega el minimizer).
- **`config/config.example.toml`**: sección `[gateway]` completa y comentada con dos tiers (economico→litellm/gemini-default, fuerte→anthropic/claude-opus-4-6), tabla de precios con aliases reales del LiteLLM del owner (gemini/deepseek/qwen), budget global+por-agente, timeout, retención y ejemplo de secret_patterns.
- **`src/bootstrap/gateway.py` — `build_gateway`**: composition root (Pattern 4), único módulo que cablea adapters + application + facade. API keys de os.environ (V2). Nunca importa `audit`.
- **`src/gateway/traces.py`**: `os.chmod(db_path, 0o600)` best-effort tras crear la DB (T-02-trace-file-perms).
- **Tests**: `test_gateway.py` (7), `test_retry.py` (3 respx), `test_gateway_config.py` (6), `test_e2e_security.py` (10 — incluye los 5 formatos trampa parametrizados + env-value + budget + happy path + intercambiabilidad + perms).

## Task Commits

1. **Task 1 (RED): tests fallidos de ModelGateway** - `184e577` (test)
2. **Task 1 (GREEN): ModelGateway.ask Flow 4 + retry** - `3d46b9d` (feat)
3. **Task 2 (RED): retry respx + config [gateway] tests** - `198c139` (test) — retry verde contra Task 1; config RED
4. **Task 2 (GREEN): GatewaySettings + sección [gateway]** - `8099e8e` (feat)
5. **Task 3: composition root + e2e security + traces 0600** - `8adfb6c` (feat)

_TDD: Task 1 RED→GREEN; Task 2 RED→GREEN (la parte de retry ya pasaba contra Task 1 porque el retry se implementó en gateway.py; la parte de config era el RED real). Refactor no necesario._

## Files Created/Modified

- `src/gateway/gateway.py` - `ModelGateway.ask()` Flow 4 + retry centralizado
- `src/gateway/__init__.py` - barrel exporta `ModelGateway`
- `src/core/domain/config.py` - `GatewaySettings` frozen + `WyssSettings.gateway`
- `src/core/domain/__init__.py` - export de `GatewaySettings`
- `src/bootstrap/config.py` - modelos Pydantic [gateway] + `_to_gateway_settings`
- `src/bootstrap/gateway.py` - `build_gateway` composition root
- `src/gateway/traces.py` - chmod 0600 de traces.db
- `config/config.example.toml` - sección [gateway] completa
- `tests/gateway/test_gateway.py` - 7 tests de orquestación Flow 4
- `tests/gateway/test_retry.py` - 3 tests respx del retry D-25
- `tests/gateway/test_e2e_security.py` - 10 tests e2e (anclas de fase)
- `tests/bootstrap/test_gateway_config.py` - 6 tests de la sección [gateway]

## Decisions Made

- **GatewaySettings default vacío en WyssSettings**: el plan agregaba `gateway` a `WyssSettings`; para no romper las construcciones existentes de Fase 1 (FakeConfigStore, configs de test sin [gateway]) se le dio un default_factory vacío. Una sección [gateway] presente sí se valida fail-closed.
- **env_values de os.environ filtrado por keys conocidas**: el bootstrap lee solo ANTHROPIC_API_KEY/LITELLM_MASTER_KEY de os.environ para alimentar el bloqueo por substring del minimizer (D-21). Los nombres viven en `_GATEWAY_ENV_KEYS` en código; los valores nunca se loguean.
- **chmod 0600 en TraceStore, no en build_gateway**: así la mitigación cubre cualquier creación de traces.db (no solo la del composition root), con `contextlib.suppress(OSError)` para que NTFS/fuseblk (sin modos POSIX) no aborte el boot.

## Deviations from Plan

None - plan executed exactly as written.

(Notas menores, no desviaciones: (1) la parte de retry de los tests de Task 2 ya pasaba contra el gateway de Task 1 porque el retry se implementó en `gateway.py` en Task 1 — el RED real de Task 2 fue la sección [gateway] de config; (2) ruff RUF022 pidió reubicar `GatewaySettings` en `__all__` para mantener el orden global — se insertó entre `ExtractedContent` y `Hit` sin tocar el resto; (3) ruff SIM105 forzó `contextlib.suppress` en vez de try/except/pass para el chmod.)

## Threat Model Coverage

| Threat ID | Disposition | Cubierto por |
|-----------|-------------|--------------|
| T-02-e2e-secret-egress | mitigate | `test_format_secret_never_egresses` (5 formatos) + `test_env_value_secret_never_egresses`: provider 0 llamadas (respx call_count==0) |
| T-02-e2e-secret-log | mitigate | los tests verifican que ni payload ni message del TASK_FAILED contienen el secreto; solo `pattern` |
| T-02-budget-bypass | mitigate | `test_budget_exhausted_blocks_pre_call`: BudgetExceeded antes de la llamada, 0 egress, TASK_FAILED |
| T-02-double-retry | mitigate | `test_4xx_fail_fast_no_retry` (1 call), `test_transient_exhausts_retries` (3 calls exactas) |
| T-02-tier-fallback | mitigate | `test_unknown_tier_propagates_without_fallback`: UnknownTier propaga, provider 0 veces |
| T-02-key-in-trace | mitigate | api_key/master_key de os.environ a headers del provider; nunca en config/trace/AuditEvent (build_gateway) |
| T-02-trace-file-perms | mitigate | `test_traces_db_has_restrictive_permissions`: 0600 verificado |
| T-02-audit-independence | mitigate | `lint-imports` (contrato independence) verde + test que escanea gateway.py por `import audit` |
| T-02-config-regex-dos | accept | regex de config compilados al boot (fail-fast si inválido); config es del owner de confianza |

## Known Stubs

None — el gateway está completamente cableado y probado e2e. `build_gateway` arma componentes reales sobre datos reales; los providers reales (LiteLLM/Anthropic) se validan vía respx/fakes sin red. La llamada real a APIs externas es opt-in (requiere claves en .env) y queda para los consumidores de Fases 3-5.

## Issues Encountered

- mypy: `build_gateway` infería `providers` como `dict[str, object]` (se anotó `dict[str, ModelProvider]`) y `float(row["cost_usd"])` sobre un `object` del row (se usó `isinstance(cost, float)`). Resueltos sin cambio de comportamiento.
- ruff: RUF022 (`__all__` no ordenado) y SIM105 (`try/except/pass`). Resueltos respetando el patrón del repo.

## Next Phase Readiness

- Fase 2 cerrada end-to-end: `ModelGateway.ask()` es el único punto de salida a IA con las 5 garantías de los success criteria probadas (2 providers intercambiables, secreto nunca egresa, presupuesto bloquea pre-call, trace consultable, embeddings local cubierto en 02-03).
- Consumidores de Fase 3+ (SummarizerPort, EmbeddingProvider) y Fase 5 (orquestador/Hermes) inyectan/consumen `ModelGateway` vía `build_gateway` con su `SqliteAuditLogger` como AuditPort.
- Cadena verde de fin de fase: `152 passed, 2 skipped`, mypy 82 archivos clean, ruff clean, lint-imports 2 contratos KEPT.
- Sin blockers.

## Self-Check: PASSED

- Archivos creados/modificados: todos FOUND (gateway.py, bootstrap/gateway.py, test_gateway.py, test_retry.py, test_e2e_security.py, test_gateway_config.py, + 6 modificados).
- Commits verificados: 184e577, 3d46b9d, 198c139, 8099e8e, 8adfb6c.
- Verificación: cadena verde completa (`uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports`) toda verde.

---
*Phase: 02-gateway-de-modelos*
*Completed: 2026-06-12*
