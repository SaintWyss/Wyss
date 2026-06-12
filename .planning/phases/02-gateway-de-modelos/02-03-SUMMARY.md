---
phase: 02-gateway-de-modelos
plan: 03
subsystem: gateway
tags: [httpx, respx, routing, providers, embeddings, ollama, anthropic, litellm, domain]

# Dependency graph
requires:
  - phase: 02-gateway-de-modelos
    plan: 01
    provides: "dominio gateway (ModelRequest/ModelResponse), UnknownTier, ports (ModelProvider/EmbeddingProvider), deps httpx/respx, scaffolding tests/gateway"
provides:
  - "TierConfig frozen en core.domain.gateway (importable sin ciclo por bootstrap+gateway)"
  - "ModelRouter determinístico: tier -> TierConfig, fail-closed (UnknownTier sin fallback)"
  - "AnthropicProvider + LiteLLMProvider (httpx directo, sin SDK, sin doble-retry)"
  - "OllamaEmbeddingProvider (embeddings LOCALES sobre EmbeddingProvider de core/ports/knowledge)"
  - "FakeModelProvider/FakeEmbeddingProvider intercambiables en gateway/providers/fakes.py"
affects: [02-04, 02-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "adapter de provider httpx directo: el dict del JSON muere en el adapter, afuera solo dominio"
    - "entidad de dominio (TierConfig) en core.domain para evitar ciclo bootstrap<->gateway"
    - "router determinístico fail-closed espejo de CognitivePolicyEngine (lo desconocido es error)"
    - "test real opt-in vía skipif por env var (WYSS_TEST_OLLAMA, patrón del NTFS de Fase 1)"

key-files:
  created:
    - src/gateway/router.py
    - src/gateway/providers/__init__.py
    - src/gateway/providers/anthropic.py
    - src/gateway/providers/litellm.py
    - src/gateway/providers/ollama.py
    - src/gateway/providers/fakes.py
    - tests/gateway/test_router.py
    - tests/gateway/test_providers.py
    - tests/gateway/test_embeddings.py
  modified:
    - src/core/domain/gateway.py
    - src/core/domain/__init__.py

key-decisions:
  - "TierConfig vive en core.domain.gateway (no en router.py) — bootstrap y gateway la importan sin ciclo (decisión fijada por plan-checker)"
  - "max_tokens lo fija el tier (TierConfig), NO el caller (Open Question 1 resuelta)"
  - "OllamaEmbeddingProvider reusa EmbeddingProvider de core/ports/knowledge.py — no se inventa port nuevo"
  - "ollama.py se creó en el commit de Task 2 (lo importa el barrel providers/__init__); su test/skipif llegó en Task 3"

patterns-established:
  - "Provider adapter: httpx directo, raise_for_status propaga 4xx, retry vive en el gateway (D-25)"
  - "cost_usd=0.0 desde el provider — el CostTracker calcula el costo (D-24), nunca el provider"

requirements-completed: [GATE-01, GATE-02]

# Metrics
duration: 4min
completed: 2026-06-12
---

# Phase 2 Plan 03: Routing + Adaptadores de Proveedor Summary

**Routing determinístico (ModelRouter tier→TierConfig, fail-closed sin fallback) + dos providers HTTP intercambiables (Anthropic Messages API y LiteLLM OpenAI-compatible vía httpx directo, sin doble-retry) + OllamaEmbeddingProvider local sobre el port existente, todos con fakes intercambiables y el dict de la API confinado al adapter.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-06-12T00:40:35Z
- **Completed:** 2026-06-12T00:44:51Z
- **Tasks:** 3
- **Files modified:** 11 (9 creados, 2 modificados)

## Accomplishments

- **TierConfig** frozen (`@dataclass(frozen=True, slots=True)`) agregado a `core.domain.gateway` y exportado en `core.domain.__init__`: provider + model_alias + max_tokens. Vive en core para que bootstrap (02-05) y gateway la importen sin ciclo. El `max_tokens` lo fija el tier, no el caller (Open Question 1).
- **ModelRouter** determinístico (GATE-02, D-16/D-17): `resolve(tier) -> TierConfig` por lookup puro; tier inexistente → `UnknownTier(tier, available=...)` sin fallback silencioso. Espejo del fail-closed de `CognitivePolicyEngine`.
- **AnthropicProvider** (Messages API directa) y **LiteLLMProvider** (proxy OpenAI-compatible en localhost:4000), ambos con httpx directo, sin SDK (evita el doble-retry de Pitfall 1, D-25): `raise_for_status` propaga 4xx, el retry vive en el gateway. Traducen el JSON a `ModelResponse` dentro del adapter — afuera solo dominio. `cost_usd=0.0` (el CostTracker calcula, D-24).
- **OllamaEmbeddingProvider** (GATE-01 criterio 5, D-15): embeddings LOCALES sobre el `EmbeddingProvider` de `core/ports/knowledge.py` (port reusado, no nuevo). POST a `/api/embed` (singular, batch L2-normalizado — no el deprecado `/api/embeddings`).
- **Fakes** intercambiables (`FakeModelProvider`, `FakeEmbeddingProvider`) en `gateway/providers/fakes.py` con la firma exacta del port; permiten inyectar respuesta/excepción para tests del gateway/retry.
- **Tests:** router (3), providers (7, respx sin red), embeddings (fake CI + respx shape CI + real opt-in skipif `WYSS_TEST_OLLAMA`). 12 passed, 1 skipped en el alcance del plan.

## Task Commits

Cada tarea commiteada atómicamente (TDD en Task 1 y 2):

1. **Task 1 (RED): tests fallidos del ModelRouter** - `7974c78` (test)
2. **Task 1 (GREEN): ModelRouter + TierConfig de dominio** - `e74f904` (feat)
3. **Task 2 (RED): tests fallidos de providers HTTP + fake** - `3513f1a` (test)
4. **Task 2 (GREEN): AnthropicProvider/LiteLLMProvider + fakes httpx directo** - `00f9b30` (feat)
5. **Task 3: OllamaEmbeddingProvider tests opt-in + ruff E501 cleanup** - `fde25a3` (feat)

**Plan metadata:** (commit docs final)

_TDD: Task 1 RED (7974c78) → GREEN (e74f904); Task 2 RED (3513f1a) → GREEN (00f9b30); refactor no necesario. Task 3 no es TDD (el plan no lo marca tdd) — provider+fake creados en Task 2 para el barrel, test agregado acá._

## Files Created/Modified

- `src/core/domain/gateway.py` - `TierConfig` frozen (provider/model_alias/max_tokens)
- `src/core/domain/__init__.py` - export de `TierConfig`
- `src/gateway/router.py` - `ModelRouter` determinístico fail-closed
- `src/gateway/providers/__init__.py` - barrel (Anthropic/LiteLLM/Ollama/fakes)
- `src/gateway/providers/anthropic.py` - `AnthropicProvider` (Messages API, httpx)
- `src/gateway/providers/litellm.py` - `LiteLLMProvider` (OpenAI-compatible, httpx)
- `src/gateway/providers/ollama.py` - `OllamaEmbeddingProvider` (/api/embed, httpx)
- `src/gateway/providers/fakes.py` - `FakeModelProvider`, `FakeEmbeddingProvider`
- `tests/gateway/test_router.py` - 3 tests (resolve, UnknownTier, frozen)
- `tests/gateway/test_providers.py` - 7 tests respx (shape, headers, 4xx, fake)
- `tests/gateway/test_embeddings.py` - fake + respx shape + real opt-in skipif

## Decisions Made

- **`TierConfig` en `core.domain.gateway`, no en `router.py`**: el plan-checker fijó que vive en dominio para que bootstrap (GatewaySettings, 02-05) y gateway la importen sin ciclo. Se exportó en `core.domain.__init__` junto al resto del vocabulario público.
- **`max_tokens` lo fija el tier**: Open Question 1 resuelta — el agente solo declara `tier`+`purpose`, el límite de tokens es decisión de config (TierConfig), no del caller.
- **`ollama.py` creado en el commit de Task 2**: el barrel `providers/__init__.py` lo importa, así que el módulo tenía que existir para que el import de Task 2 fuera limpio; su test (skipif opt-in) y la verificación específica llegaron en Task 3, tal como pide el plan. No constituye desviación: ambos tasks comparten el archivo de fakes/providers.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test usaba un símbolo httpx interno inexistente**
- **Found during:** Task 2 (GREEN)
- **Issue:** El test de headers de Anthropic parseaba el body con `httpx._content.json_loads`, que no existe en httpx 0.28.1 (`AttributeError`).
- **Fix:** Reemplazado por `json.loads(sent.content)` de stdlib.
- **Files modified:** tests/gateway/test_providers.py
- **Commit:** 00f9b30

**2. [Rule 3 - Blocking] Ruff E501 (líneas >100) en docstrings**
- **Found during:** Task 3 (verificación final ruff, que no estaba en el `<verify>` de cada task pero sí en el gate de fase)
- **Issue:** 5 docstrings excedían 100 chars (router.py, fakes.py, test_providers.py); ruff cuenta el ancho unicode, así que palabras acentuadas ("Determinístico") empujaban el límite.
- **Fix:** Acortados los docstrings; ruff `All checks passed`.
- **Files modified:** src/gateway/router.py, src/gateway/providers/fakes.py, tests/gateway/test_providers.py
- **Commit:** fde25a3

## Issues Encountered

- Ruff cuenta el ancho de caracteres unicode: un docstring de exactamente 100 chars con acentos reportaba 101. Resuelto reformulando las líneas. Sin impacto funcional.

## User Setup Required

- **Ollama (opcional, para el test real de embeddings):** el test `test_ollama_embed_real` se saltea en CI. Para correrlo: instalar Ollama, `ollama pull nomic-embed-text`, luego `WYSS_TEST_OLLAMA=1 uv run pytest tests/gateway/test_embeddings.py`. La cobertura del adapter en CI la garantiza el test respx del shape de `/api/embed`.
- **Keys para llamadas reales (no requeridas en esta ola):** `ANTHROPIC_API_KEY` (AnthropicProvider) y `LITELLM_MASTER_KEY` (proxy del owner en localhost:4000). El shape de ambos providers se valida con respx sin tocar la red.

## Next Phase Readiness

- Router + providers + embeddings listos para que 02-04 (CostTracker) y 02-05 (gateway facade + bootstrap + traces) los cableen: la fachada `ModelGateway.ask()` orquestará router→minimizer→cost→provider→trace.
- Verificación global verde: `111 passed, 2 skipped` (ntfs + ollama opt-in), `mypy` sin issues en 71 archivos, `lint-imports` 2 contratos KEPT (httpx solo en gateway/, core stdlib-only), `ruff` All checks passed.
- Sin blockers.

## Self-Check: PASSED

- Archivos creados/modificados: todos FOUND (router.py, providers/{__init__,anthropic,litellm,ollama,fakes}.py, gateway.py, domain/__init__.py, test_router.py, test_providers.py, test_embeddings.py, SUMMARY.md).
- Commits verificados en git log: 7974c78, e74f904, 3513f1a, 00f9b30, fde25a3.

---
*Phase: 02-gateway-de-modelos*
*Completed: 2026-06-12*
