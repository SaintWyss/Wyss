# Phase 2: Gateway de Modelos - Context

**Gathered:** 2026-06-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Único punto de salida a IA externa: ModelRouter + ContextMinimizer + CostTracker + tracing + EmbeddingProvider, antes de que exista cualquier consumidor. Dos proveedores reales intercambiables por config, secretos nunca salen, presupuesto con hard-stop pre-autorizado, cada llamada deja trace consultable. (GATE-01..05.)

</domain>

<decisions>
## Implementation Decisions

### Proveedores
- **D-14:** Dos `ModelProvider` reales: **LiteLLMProvider** (tier económico — proxy local OpenAI-compatible en `localhost:4000`, ya corriendo en Docker del owner, expone Gemini/Qwen/DeepSeek) y **AnthropicProvider** (tier fuerte — API directa). Intercambiables vía config sin tocar código; FakeProvider para tests (success criterion 1).
- **D-15:** `EmbeddingProvider` real: **Ollama local** (p.ej. nomic-embed-text). El contenido de archivos personales nunca sale de la máquina para indexarse. Fake de embeddings para tests (success criterion 5).

### Routing (GATE-02)
- **D-16:** Tiers definidos en `config.toml` (p.ej. `economico` → LiteLLM/modelo X, `fuerte` → Anthropic/modelo Y) con aliases de modelo. **El caller declara el tier** en el request — el router resuelve tier→provider+modelo de forma determinística. Sin clasificación automática de complejidad, sin LLM decidiendo routing.
- **D-17:** **Fail-fast entre proveedores**: si el provider del tier falla, error claro al caller, auditado. Sin fallback automático de tier, sin retry cross-provider — un fallback silencioso cambia costo/calidad sin decisión humana.

### Presupuesto (GATE-04)
- **D-18:** Presupuesto **global mensual + límite opcional por agente**, ambos en `config.toml`. El CostTracker chequea ambos ANTES de cada llamada (pre-autorización, no reporte). Prepara AGENT-02 (presupuesto por agente, Fase 7).
- **D-19:** Destrabe de presupuesto agotado: **solo editando config.toml + reload**. Decisión humana explícita, auditada como cambio de config. Sin override por chat ni comando de agente (regla #6: un agente jamás toca presupuesto).

### Context Minimizer (GATE-03)
- **D-20:** Secreto detectado en payload saliente → **la llamada NO sale** (bloqueo fail-closed, no redacción). Error auditado registrando QUÉ patrón matchó, sin loguear el secreto. Un secreto llegando al borde es bug upstream a arreglar, no a parchear.
- **D-21:** Detección por tres fuentes: **valores reales del `.env` cargados al boot** (match exacto/substring) + **regex built-in** de formatos conocidos (sk-, AKIA, ghp-, JWT, private keys, etc.) + **patrones extra por config** (aditivos, como la denylist de política).

### Tracing (GATE-05)
- **D-22:** DB SQLite **propia y separada** (`traces.db`) — distinta de audit.db y de los datos de usuario. Prompt y output **completos POST-minimizer**, tokens in/out, costo, latencia, task_id, agent_id, tier, purpose. Retención configurable, default 90 días (audit es forever; traces expiran).

### Resiliencia y costo
- **D-23:** **Sin streaming** en esta fase: `ask()` devuelve respuesta completa. Si la CLI de Fase 5 lo necesita, se agrega `ask_stream()` como extensión aditiva (regla #9).
- **D-24:** Costo calculado con **tabla local de precios por modelo en `config.toml`** (tokens × precio). Mismo cálculo determinístico para todo provider; el gate nunca depende de que el provider reporte bien. Si LiteLLM devuelve costo, se guarda en el trace como dato comparativo.
- **D-25:** **2 retries con backoff SOLO en errores transientes** (timeout, 429, 5xx) del MISMO provider; errores no-transientes (4xx) fail-fast directo. Timeout por llamada configurable (default 120s). Cada retry re-pasa el gate de presupuesto.

### Identidad del request
- **D-26:** `AgentModelRequest` viaja con **agent_id + task_id + tier + purpose** (string corto: "plan", "summarize", "classify"…). Traces consultables por tipo de uso; correlación de cadenas vía task_id (sin trace jerárquico por ahora).

### Claude's Discretion
- Esquema exacto de tablas de `traces.db` (respetando campos de D-22).
- Naming de aliases de tiers/modelos en config y estructura interna del módulo `gateway/`.
- Set inicial exacto de regex built-in de secretos (D-21 lista los formatos mínimos).
- Mecánica del "secreto trampa" fixture para el test de GATE-03 (success criterion 2).
- Librería HTTP/SDK por provider (httpx directo vs SDK oficial anthropic) — decidir en research según lo que minimice deps.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Spec de implementación (canónica del owner)
- `docs/18-prompt-implementacion.md` — Model Gateway: único punto de salida, ≥2 proveedores, registra tokens y costo, aplica Context Minimizer antes de cada llamada (§Model Gateway); reglas inviolables 1-9; layout `gateway/` ← ModelRouter, ContextMinimizer, CostTracker.
- `docs/16-criterios-de-aceptacion.md` — criterio transversal: nada se acepta con secreto enviado afuera o acción sin auditar.

### Research (decisiones técnicas commiteadas)
- `.planning/research/ARCHITECTURE.md` — Flow 4 (model call flow): Minimizer → CostTracker pre-autoriza (puede VETAR antes del send) → ModelProviderPort.complete → record + audit. AuditPort inyectado al ModelRouter.
- `.planning/research/PITFALLS.md` — presupuestos advisory vs enforced; auditoría primero.
- `.planning/research/STACK.md` — Pydantic v2 solo en bootstrap, mypy strict, WAL.

### Contratos existentes (Fase 1 — NO romper, extender)
- `src/core/ports/gateway.py` — `ModelProvider` (name, complete async) y `ModelGatewayPort` (ask async). El planner puede necesitar extender `AgentModelRequest` (D-26: tier, purpose) — cambio en dominio frozen, verificar tests de Fase 1.
- `src/core/domain/gateway.py` — `ModelRequest`, `ModelResponse`, `AgentModelRequest`.
- `src/bootstrap/config.py` — patrón establecido: modelos Pydantic `extra="forbid"`, `ConfigError` legible, mapping a dominio frozen. Los bloques de config del gateway (tiers, precios, presupuesto, timeout, retención) siguen este patrón.
- `src/audit/sqlite_logger.py` — patrón SQLite establecido (separación de DBs, WAL fail-fast smoke test) que `traces.db` replica.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/core/ports/gateway.py` + `src/core/domain/gateway.py` — port y entidades base ya commiteados (Fase 1, interfaces primero). Esta fase los implementa; extensión de entidades permitida si los tests de conformance se actualizan.
- `src/bootstrap/config.py` — `WyssConfigModel` extensible con sección `[gateway]`; `load_settings` ya fail-fast.
- `src/audit/` — `SqliteAuditLogger` como referencia de cómo montar `traces.db` (esquema, PRAGMAs, smoke test WAL).
- `tests/ports/fakes.py` — patrón de fakes de conformance para FakeProvider/FakeEmbedding.
- Infra externa del owner ya corriendo: LiteLLM en Docker (`localhost:4000`) y Ollama instalable local.

### Established Patterns
- Core stdlib-only (lint-imports lo refuerza) — SDKs de providers viven en `src/gateway/` (capa application/adapter), JAMÁS en `core/`.
- Fail-closed en todo: política, config, y ahora minimizer (D-20).
- Denylist/config aditiva: BUILTIN deny + config — los patrones de secretos (D-21) siguen el mismo patrón.
- DI por constructor manual; AuditPort inyectado (D-08).

### Integration Points
- `src/gateway/` — módulo stub existente a rellenar (ModelRouter, ContextMinimizer, CostTracker, providers).
- Composition root en bootstrap cablea: config → providers → minimizer → cost tracker → router, con AuditPort inyectado.
- Consumidores futuros: Fase 3 (SummarizerPort vía gateway), Fase 4 (EmbeddingProvider), Fase 5 (orquestador/Hermes). Decisión Hermes híbrido (PROJECT.md Key Decisions): este gateway es el único path de modelos también cuando Hermes sea el cerebro — no acoplar nada del gateway a un consumidor concreto.

</code_context>

<specifics>
## Specific Ideas

- El owner ya opera LiteLLM (Docker, `localhost:4000`, Gemini+Qwen+DeepSeek, conectado a n8n/OpenCode) — el LiteLLMProvider debe funcionar contra esa instancia real tal cual está.
- Filosofía rectora: humano primero — el gateway nunca toma decisiones de costo/calidad por su cuenta (sin fallback de tier, sin override de presupuesto, sin routing heurístico).
- "No es prototipo": cada pieza completa, con tests de seguridad explícitos (secreto trampa nunca sale; presupuesto agotado bloquea).

</specifics>

<deferred>
## Deferred Ideas

- **`ask_stream()` streaming** — agregar como extensión aditiva si la CLI interactiva de Fase 5 lo necesita.
- **Trace jerárquico (parent_trace_id/span estilo OpenTelemetry)** — evaluar en Fase 9 (multi-agente y rutinas), cuando existan cadenas de llamadas reales.

</deferred>

---

*Phase: 2-Gateway de Modelos*
*Context gathered: 2026-06-11*
