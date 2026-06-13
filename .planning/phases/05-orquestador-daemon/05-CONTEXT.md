# Phase 5: Orquestador Daemon - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Proceso persistente siempre-activo (`wyss start`) que convierte lenguaje natural del owner en
intención clasificada → Plan legible → flujo de confirmación → despacho auditado, con el
`CognitivePolicyEngine` (niveles A/B/C/D) operativo punta a punta.

**Arquitectura locked (Key Decision proyecto, 2026-06-11):** modo **híbrido con Hermes Agent**
(NousResearch) como cerebro de orquestación. Hermes corre en container aislado, built-in tools
**off**; su única vía de acción es el **MCP server de Wyss**, gateado fail-closed por
`CognitivePolicyEngine` + audit. Hermes = adapter detrás de `OrchestratorPort`. Las reglas
inviolables 1-9 (`docs/18`) son la garantía determinística — Hermes nunca las saltea.

**En scope:** daemon (Unix socket + JSON-RPC + asyncio), Intent classification, generación de
Plan legible, motor de confirmación async persistente, gating de política end-to-end, eval set
dorado anti-falso-A en CI, consulta de auditoría (`wyss audit`).

**Fuera de scope (Fase 6):** ejecución real de los pasos del Plan (la `Tool` port y su
enforcement). Fase 5 **declara** la política de error por paso en el Plan; Fase 6 la **ejecuta**.
</domain>

<decisions>
## Implementation Decisions

### Frontera Hermes ↔ política determinística (ORCH-03, POL-06)
- **D-50:** **Hermes propone, engine dispone.** Hermes hace lo que un LLM hace bien (entender NL,
  clasificar intención en ≥9 categorías, draftear el Plan). El **nivel A/B/C/D lo asigna el
  `CognitivePolicyEngine` determinístico** (puro, sin LLM, ya existe en `src/core/policy/engine.py`),
  nunca el LLM. La categoría de intención puede venir de Hermes; el **nivel jamás**.
- **D-51:** Hermes emite un **Plan estructurado** (`core.domain.plan.Plan` / `Action` — ya existe),
  no texto libre. Solo así el engine puede puntuar paso a paso + agregado (anti-bypass POL-05).
- **D-52:** **Nivel dinámico por `(action_type, target/args)`** vía denylist-as-data — NO estático
  por tool. Mismo `file.delete` es A en `/tmp` y C/D en `~/Data`. Coherente con el diseño ya
  implementado (`engine._base_level` + `DenyRule` fnmatch con expansión `~`, unknown → C fail-closed).
- **D-53:** La garantía anti-falso-A vive en el engine determinístico, no en Hermes. POL-06 mide el
  engine.

### Confirmación async + persistencia (ORCH-04, ORCH-05, ORCH-06)
- **D-54:** **Patrón pending-id + reconnect**, NO request JSON-RPC bloqueante. `wyss ask` → daemon
  arma Plan → `engine.evaluate` → si `outcome=CONFIRM` (B/C) persiste `pending_proposal` en SQLite
  (estado, Plan, nivel, expiry) y responde con el Plan legible + `pending_id`. El owner confirma
  con `wyss confirm <id>` (B: `[s/N]`; C: exige escribir `CONFIRMAR`).
- **D-55:** La cola de pendientes es la **fuente de verdad en SQLite** → un restart del daemon no
  pierde confirmaciones ni propuestas (ORCH-06). Propuestas **independientes por id**, el owner
  confirma en cualquier orden.
- **D-56:** **TTL configurable con auto-reject + audit.** Las propuestas expiran (más corto para
  C/D); al vencer → auto-reject + entrada de auditoría. Evita ejecución stale de acciones
  destructivas confirmadas tarde.
- **D-57:** Tras `wyss confirm`, el despacho a ejecución se **encola** (Fase 6 ejecuta); `confirm`
  responde aceptado + execution-id. El daemon nunca bloquea en la ejecución.

### Lifecycle Hermes + MCP server (ORCH-01)
- **D-58:** **Hermes desacoplado** — container Hermes + integración vía `docker compose` aparte;
  el daemon es **cliente** detrás de `OrchestratorPort`. El daemon NO spawnea/supervisa el container
  (no mete Docker en el core). `wyss start` levanta solo el daemon; el compose de Hermes es
  prerequisito documentado.
- **D-59:** **El MCP server de Wyss lo hostea el daemon** (socket local que el container Hermes
  alcanza). Cada call MCP de Hermes → `CognitivePolicyEngine` + audit antes de tocar nada. Como
  Hermes tiene built-in tools off, el MCP server del daemon es su **única** superficie de acción —
  ahí vive todo el gating en un solo proceso confiable.
- **D-60:** **Degradación D-44** (sin excepción): si Hermes está down, el daemon responde explícito
  ("orquestador no disponible") en vez de tirar excepción. Las consultas determinísticas
  (`knowledge_query` directa al Retrieval de Fase 4) pueden seguir andando.
- **D-61:** `wyss start` sobrevive a **socket huérfano** (detecta + limpia stale socket al arrancar);
  systemd reinicia el daemon ante fallo (unit file con `Restart=`).

### Errores por paso + eval dorado (ORCH-07, POL-06)
- **D-62:** **Política de error declarada en el Plan schema** — cada `Action` lleva
  `on_error: retry|escalate|abort` + parámetros de backoff. Fase 5 define el schema y lo deja listo;
  el **enforcement es de la Capa de Ejecución (Fase 6)**. Las fallas nunca son silenciosas.
- **D-63:** **Eval set dorado anti-falso-A** réplica del gate `hit@1=20/20` de Fase 4: fixtures
  `NL → nivel esperado` (~20-30 casos cubriendo A/B/C/D + ambiguos), corre en CI; **cualquier
  falso-A (esperado B/C/D, obtuvo A) rompe el build**. Mide el engine determinístico, no a Hermes.

### Claude's Discretion
Por directiva del owner (2026-06-13): *"tomá las decisiones recomendadas y solo preguntame cuando
haya algo serio serio"* — piloto automático en decisiones menores; consultar solo ante cambios de
arquitectura/seguridad/scope. Quedan a discreción de research/planner (decisiones menores):
- Esquema concreto de las tablas SQLite de colas (`pending_proposals`, etc.) y nombres de métodos JSON-RPC.
- Formato de salida de `wyss audit` (sigue el patrón de CLI ya establecido en fases previas).
- Transport exacto del MCP server (stdio vs socket TCP local) — decidir en research según cómo el
  container Hermes alcanza al host; el invariante es que TODO call pase por el policy engine.
- Naming de los agentes (identidad argentina) — es configuración, no código (`docs/10` §5).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Spec canónica del owner (autoridad)
- `docs/18-prompt-implementacion.md` — spec de implementación: hexagonal, SOLID, plugin pattern,
  **reglas inviolables 1-9**, niveles A/B/C/D (D absoluto), fail-closed. Autoridad sobre todo lo demás.

### Arquitectura del orquestador y agentes
- `docs/10-arquitectura-de-agentes.md` — jerarquía orquestador↔agentes, comunicación vertical
  (horizontal prohibida), modelo base, lo que un agente nunca puede hacer.
- `docs/07-arquitectura-conceptual.md` — arquitectura conceptual del sistema.
- `docs/08-diagrama-componentes.md` — componentes y sus relaciones.
- `docs/12-flujos-de-trabajo.md` — flujos NL → plan → confirmación → ejecución.

### Política, seguridad, requerimientos
- `docs/13-politica-acceso-seguridad.md` — niveles A/B/C/D, política cognitiva, fail-closed.
- `docs/04-requerimientos-funcionales.md` — RF-001 (daemon/NL), RF-002 (intent), RF-003 (ambigüedad),
  RF-004 (plan explícito), RF-023 (auditoría consultable).
- `docs/16-criterios-de-aceptacion.md` — criterios de aceptación del orquestador.
- `.planning/REQUIREMENTS.md` — ORCH-01..07, POL-06, AUD-02 (texto completo de los requisitos).

### Decisión de arquitectura (locked)
- `.planning/PROJECT.md` §Key Decisions — **Hermes híbrido** como cerebro de orquestación
  (registrado 2026-06-11). MUST read: define el modo híbrido y el gating MCP fail-closed.

### Decisiones de fases previas (patrones a reusar)
- `.planning/phases/02-gateway-de-modelos/02-CONTEXT.md` — ModelGateway, fail-closed, GatewaySettings.
- `.planning/phases/03-pipeline-de-ingesta/03-CONTEXT.md` — pipeline de ingesta, gate empírico.
- `.planning/phases/04-b-squeda-h-brida/04-CONTEXT.md` — HybridRetrieval (RRF), gate dorado
  `hit@1=20/20` (patrón a replicar en POL-06), degradación D-44 sin excepción.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (ya construido — reusar, no reinventar)
- `src/core/policy/engine.py` — `CognitivePolicyEngine.evaluate(plan) -> PolicyDecision`: PURO, sin
  IO/LLM, algoritmo de 5 pasos (denylist D incondicional → per-action → aggregate anti-bypass POL-05
  → max → outcome). Es exactamente el "engine dispone" de D-50/D-52. NO expone `evaluate_action()`
  (anti-bypass por composición). El daemon lo invoca con el Plan que emite Hermes.
- `src/core/policy/builtin_deny.py` — `BUILTIN_DENY` (denylist base, aditiva con config).
- `src/core/domain/plan.py` — `Plan` / `Action` schema. Hermes DEBE emitir esto (D-51); extender con
  `on_error` por Action (D-62).
- `src/core/domain/risk.py` — `RiskLevel` (IntEnum, "subir sí, bajar jamás" vía `max()`), `outcome_for`.
- `src/core/domain/policy.py` — `PolicyRules`, `DenyRule`, `PolicyDecision`, `unknown → C` fail-closed.
- `src/audit/sqlite_logger.py` + `src/audit/schema.py` — backend de auditoría (AUD-02 / `wyss audit`).
- `src/core/ports/execution.py` — `Tool` Protocol (`max_risk`, `describe`, `execute`, `verify`):
  contrato de la Capa de Ejecución (Fase 6) que Fase 5 NO implementa.
- `src/core/ports/agent.py` — `AgentBase.execute(plan, decision) -> Report`.
- `src/core/ports/audit.py`, `persistence.py`, `gateway.py`, `knowledge.py`, `security.py`, `config.py`.
- `src/bootstrap/cli.py` + `src/bootstrap/gateway.py` — composition root y CLI existente (sumar `start`/`ask`/`confirm`/`audit`).

### Established Patterns
- **Hexagonal + ports/adapters:** crear `OrchestratorPort` en `src/core/ports/` (NO existe aún);
  Hermes = adapter detrás de ese port. Layout `src/core/ports/` + módulos por capa (no `adapters/` top-level).
- **Fail-closed everywhere:** unknown action → C; Hermes down → degradación explícita (D-60); D nunca ejecuta.
- **Pydantic SOLO en bootstrap** (lint-imports lo enforcea); el core es puro.
- **Gate dorado en CI** (patrón Fase 4): replicar para POL-06 (D-63).
- **Decisions Log compactado:** al cerrar la fase, detalle en `phases/05-*/DECISIONS.md`, STATE.md solo resumen.

### Integration Points
- `src/orchestrator/__init__.py` — placeholder vacío (132B): aquí va el daemon (socket JSON-RPC asyncio).
- El daemon hostea el MCP server de Wyss (D-59) → cada tool call MCP pasa por `CognitivePolicyEngine` + audit.
- Daemon → `engine.evaluate(plan)` → branch por `outcome` (AUTO dispatch / CONFIRM persist pending / REJECT audit+refuse).
- Retrieval de Fase 4 reusable para `knowledge_query` directa (camino determinístico, sigue vivo si Hermes down).
</code_context>

<specifics>
## Specific Ideas

- El patrón mental es **"Hermes propone, el engine determinístico dispone"** — calcado del Key
  Decision: *"toda acción real pasa por MCP server gateado por CognitivePolicyEngine fail-closed"*.
- POL-06 debe ser tan estricto como el gate `hit@1=20/20` de Fase 4: un falso-A es catastrófico
  (ejecutar sin confirmar algo destructivo) → rompe el build sin excepción.
- Pendiente empírico heredado de Fase 4 (diferido, NO bloquea Fase 5): `wyss index` real con Ollama
  UP — embeddings reales nunca corrieron E2E.
</specifics>

<deferred>
## Deferred Ideas

- **Enforcement de ejecución (retry/backoff/abort real, la `Tool` port):** Fase 6 — Capa de Ejecución.
  Fase 5 solo declara `on_error` en el Plan schema.
- **Rutinas / triggers programados (`routine_trigger`):** la *categoría* de intención se clasifica en
  Fase 5, pero el motor de rutinas/scheduler es fase posterior (solapa el scope original de Fase 9,
  absorbido parcialmente por Hermes).
- **Agentes de dominio con nombre (Belgrano, Sarmiento, etc.):** instanciación de agentes concretos
  por dominio es configuración posterior; Fase 5 entrega el orquestador, no los agentes pobladores.
</deferred>

---

*Phase: 5-Orquestador Daemon*
*Context gathered: 2026-06-13*
