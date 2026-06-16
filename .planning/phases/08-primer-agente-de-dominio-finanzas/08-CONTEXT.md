# Phase 8: Primer Agente de Dominio (Finanzas) - Context

**Gathered:** 2026-06-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Fase 8 entrega **Pellegrini**, el primer agente real de Wyss, como un **MVP vertical de coach de finanzas personales**. A diferencia del scope original ("instanciar un agente sobre una BC de documentos"), el owner no tiene documentos financieros para indexar — quiere un coach que **registra sus ingresos/gastos** y lo asesora para ser económicamente estable.

Por eso la fase incluye una **capacidad nueva**: un *ledger* (libro de transacciones) persistido en SQLite tras un port, más el agente Pellegrini que lee ese ledger y razona sobre él.

**En scope:**
- Ledger de transacciones (ingreso: monto+fuente+fecha; gasto: monto+categoría+fecha), store SQLite tras un port (patrón `AuditLogger`/`PendingStore`).
- Carga híbrida: comando CLI determinístico + acción conversacional owner-instruida (`finance.record`) que pasa por el policy engine.
- Pellegrini como `ConfiguredAgent` config-driven (`[[agents]]` en config.toml): lee el ledger y asesora.
- Cableado del presupuesto per-agente (AGENT-07) desde la config al cost gate del gateway + verificación E2E del bloqueo.
- ≥3 tareas reales de asesoría E2E reportando al orquestador, todo auditado (AGENT-09).

**Fuera de scope (deferred):**
- Belgrano (dominio estudio) — agente posterior, mismo molde.
- OCR de fotos de recibos / ingesta automática de extractos bancarios.
- Hermes orquestador real (05-05 bloqueado) — Pellegrini reporta vía daemon dispatcher con FakeOrchestrator.
- Multi-agente y rutinas (Fase 9).

</domain>

<decisions>
## Implementation Decisions

### Identidad del agente
- **D-80:** Nombre **Pellegrini** (Carlos Pellegrini fundó el Banco de la Nación Argentina — temáticamente alineado con finanzas). `agent_id = "pellegrini"`, `domain = "finanzas"`. Convención de nombres argentina (docs/10 §5).
- **D-81:** Modelo `economico` + `budget_usd = 5.0`. Las tareas de finanzas son resumen/clasificación/asesoría — el tier económico alcanza para v0.1. Tope $5 chico a propósito: permite probar el gate de presupuesto agotándolo rápido en test.

### Ledger de transacciones (capacidad nueva)
- **D-82:** Store SQLite tras un port nuevo (mismo patrón que `src/audit/sqlite_logger.py` y `src/orchestrator/pending_store.py`). Modelo de dominio: transacción con tipo (ingreso/gasto), monto, fecha, y para ingreso `fuente` / para gasto `categoria`.
- **D-83:** Categorías **free-text** en v0.1 (no enum fijo). Simplicidad; la categorización inteligente puede venir después.
- **D-84:** Carga **híbrida (CLI + conversacional)**:
  - CLI determinístico para carga rápida/precisa (ej. `wyss fin add-gasto 5000 super`) — sin IA para registrar.
  - Conversacional: el owner le dice "gasté 5000 en super hoy" y Pellegrini lo registra vía una acción `finance.record`. Es una escritura **owner-instruida** que DEBE pasar por el policy engine (segunda muralla) como cualquier acción de plan. No es escritura libre desde contenido de BC (respeta el espíritu de D-71).

### Presupuesto per-agente (AGENT-07)
- **D-85:** El primitivo de enforcement **ya existe** en `src/gateway/cost.py` (`authorize(agent_id, ...)` chequea `_agent_budgets[agent_id]` → `BudgetExceeded`). El trabajo de fase es **cablear `agent_budgets` desde la config `[[agents]].budget_usd`** en el composition root (bootstrap) y verificar E2E que, agotado el tope, las llamadas de Pellegrini se bloquean (criterio #4). NO re-implementar el gate.

### Reporte al orquestador (AGENT-09)
- **D-86:** Pellegrini reporta resultados vía el **daemon dispatcher** existente (`src/orchestrator/dispatcher.py`) con **FakeOrchestrator** — Hermes real está diferido (05-05 bloqueado por build local). El E2E es genuino sobre el path de daemon + auditoría, sin depender de Hermes.

### Tareas de aceptación (AGENT-09 — las 3 reales)
- **D-87:** Las 3 tareas E2E que definen el "done":
  1. "¿Dónde se me va la plata?" → gastos agregados por categoría sobre el ledger.
  2. "Armá mi presupuesto mensual" → propuesta de presupuesto a partir de ingresos vs. gastos históricos.
  3. "¿Cuánto puedo ahorrar / cuánto me sobra?" → cálculo de superávit/déficit + sugerencia.
  (Refinables en planning; son el criterio de validación de la fase.)

### Claude's Discretion
- Esquema exacto de la tabla SQLite del ledger, nombres de columnas, índices.
- Diseño del/los action type(s) del ledger (`finance.record`, `finance.query`) y su clasificación de riesgo en la denylist (esperado: riesgo bajo, owner-instruido).
- Forma de los subcomandos CLI (`wyss fin ...`) y su salida Rich.
- Cómo Pellegrini "lee" el ledger: tool de lectura inyectado vs. retrieval adaptado. El planner/researcher resuelve el patrón más limpio dentro del hexágono.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requisitos y visión
- `.planning/REQUIREMENTS.md` — AGENT-07 (presupuesto runtime por agente), AGENT-09 (≥3 tareas reales E2E reportando al orquestador).
- `.planning/ROADMAP.md` §"Phase 8" — goal y success criteria (re-scopeados a coach+ledger).
- `docs/10-arquitectura-de-agentes.md` — convención de nombres (§5), qué puede/no puede hacer un agente (§7), asignación de inteligencia (§6).
- `.planning/phases/07-modelo-de-agentes/07-CONTEXT.md` — D-70 (anti-injection 2da muralla), D-71 (memoria: solo owner/extracción supervisada escribe), D-72 (permisos), D-73 (config-driven). El ledger híbrido respeta D-71 (escritura owner-instruida, no desde BC).

### Patrones de código a reusar
- `src/gateway/cost.py` — cost gate con enforcement per-agente YA implementado (`authorize`/`record`/`release` por `agent_id`, `BudgetExceeded`). AGENT-07 = cablear config→este gate.
- `src/gateway/gateway.py` — `ask(AgentModelRequest)` ya pasa `agent_id` a `authorize` (líneas 217, 226, 248).
- `src/audit/sqlite_logger.py` + `src/audit/schema.py` — patrón de store SQLite tras port (modelo para el ledger).
- `src/orchestrator/pending_store.py` — otro store SQLite-WAL (patrón ledger).
- `src/agents/configured_agent.py` + `src/agents/registry.py` — molde del agente y registro config-driven.
- `src/bootstrap/config.py` — `AgentConfigModel` / `[[agents]]` parsing (acá se cablea `budget_usd`→`agent_budgets`).
- `src/bootstrap/cli.py` — Typer app (acá cuelgan los subcomandos `wyss fin ...`).
- `src/orchestrator/dispatcher.py` + `src/orchestrator/daemon.py` — path de reporte al orquestador (FakeOrchestrator).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Cost gate per-agente** (`cost.py`): enforcement de AGENT-07 ya hecho — solo falta poblar `agent_budgets` desde config. Ahorra el grueso del criterio #4.
- **Stores SQLite** (`sqlite_logger.py`, `pending_store.py`): plantilla directa para el ledger (port + adapter SQLite, WAL, fail-fast).
- **ConfiguredAgent + AgentRegistry**: instanciar Pellegrini = agregar entrada `[[agents]]`, cero código de agente nuevo (D-73). El código nuevo es el ledger + sus tools/acciones.
- **Daemon dispatcher + FakeOrchestrator**: path de reporte E2E ya probado en Fase 5.

### Established Patterns
- **Hexagonal estricto**: el ledger va como port en `core/ports/` + adapter SQLite en una capa; `lint-imports` prohíbe que core importe infra. El dominio del ledger (Transacción) es stdlib puro.
- **Segunda muralla**: toda acción que muta (incl. `finance.record`) pasa por `engine.evaluate` antes de ejecutar (D-70). Definir su nivel de riesgo en la denylist-as-data.
- **Pydantic solo en bootstrap**: el parsing de `[[agents]].budget_usd` y la config del ledger se validan en bootstrap, no en core.

### Integration Points
- `bootstrap/config.py`: `[[agents]].budget_usd` → `agent_budgets` del cost gate.
- `bootstrap/cli.py`: nuevos subcomandos `wyss fin ...`.
- Denylist del policy engine: nuevo(s) action type(s) del ledger.
- Pellegrini (`[[agents]]`): `kb_ids`/data source apuntando al ledger en vez de a una BC de documentos.

</code_context>

<specifics>
## Specific Ideas

- El owner quiere, textual, "ayudarme a ser económicamente estable" — el norte del agente es asesoría accionable (ahorro, presupuesto, a dónde va la plata), no reporting contable.
- Datos reales hoy: el owner puede *decir* cuánto le ingresa y cuánto gasta diariamente; tiene fotos de recibos que NO se usan en v0.1. El ledger se llena por carga manual (CLI/conversacional), no por OCR.

</specifics>

<deferred>
## Deferred Ideas

- **Belgrano (dominio estudio)** — segundo agente, mismo molde config-driven. El owner tiene datos reales (material UTN, Notion/NotebookLM) — buen candidato siguiente.
- **OCR de recibos / ingesta de extractos bancarios** — automatizar la carga del ledger. Capacidad nueva, fase futura.
- **Categorización inteligente de gastos** (vs. free-text) — cuando haya volumen.
- **Hermes orquestador real** — desbloquear 05-05 (build local de Hermes) para reemplazar FakeOrchestrator.

None fuera de eso — la discusión se mantuvo en el dominio de la fase (con un re-scope explícito y acordado).

</deferred>

---

*Phase: 8-Primer Agente de Dominio (Finanzas)*
*Context gathered: 2026-06-16*
