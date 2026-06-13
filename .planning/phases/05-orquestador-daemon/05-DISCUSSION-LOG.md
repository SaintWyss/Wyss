# Phase 5: Orquestador Daemon - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-13
**Phase:** 5-Orquestador Daemon
**Areas discussed:** Frontera Hermes↔política, Confirmación async+persistencia, Lifecycle Hermes+MCP, Errores por paso+eval dorado

**Modo:** advisor (ADVISOR_MODE=true). NON_TECHNICAL_OWNER override → false (owner autor de la
spec hexagonal `docs/18`, estudiante de sistemas → framing técnico). Research swarm de advisor
**omitido** por decisión del orquestador: decisiones internas de arquitectura wyss, no comparativas
de librerías; research externo aporta poco y contradice "Claude=juicio / token-frugal". Thinking-partner directo.

---

## Frontera Hermes ↔ política determinística

| Option | Description | Selected |
|--------|-------------|----------|
| A — Hermes propone, engine dispone | Hermes clasifica intención + draft plan; CognitivePolicyEngine determinístico asigna A/B/C/D por paso | ✓ |
| B — Router determinístico al frente | Clasificador rules/small-model 9 cat; solo deriva complejos a Hermes | |
| C — Hermes hace todo, engine veta | Hermes propone nivel, engine corrige | |

**User's choice:** A. Sub-decisión: nivel **dinámico por `(action_type, target/args)`** (no estático por tool).
**Notes:** Coincide con código ya construido (`CognitivePolicyEngine` puro + `DenyRule` fnmatch, unknown→C
fail-closed). El nivel nunca lo deriva el LLM; POL-06 mide el engine. Hermes emite `Plan` estructurado.

---

## Confirmación async + persistencia

| Option | Description | Selected |
|--------|-------------|----------|
| A — pending-id + reconnect | Daemon persiste propuesta en SQLite, devuelve pending_id; `wyss confirm <id>` | ✓ |
| B — request JSON-RPC bloqueante | El request queda colgado esperando [s/N] | |

**User's choice:** A. Sub-decisión: **TTL configurable + auto-reject + audit** (más corto para C/D).
**Notes:** ORCH-06 exige sobrevivir restart → estado en SQLite, no en conexión viva. Propuestas
independientes por id. Tras confirm, despacho se encola (Fase 6).

---

## Lifecycle Hermes + MCP server

| Option | Description | Selected |
|--------|-------------|----------|
| A — desacoplado, daemon como cliente | Hermes+MCP via compose aparte; daemon health-check/reconnect | ✓ |
| B — daemon supervisa el container | Daemon spawnea/mata el container Hermes | |

**User's choice:** A. Sub-decisión: **MCP server hosteado por el daemon** (socket local; cada call → policy engine + audit).
**Notes:** Mantiene aislamiento del container (punto de seguridad del Key Decision), core limpio de
Docker. Degradación D-44 si Hermes down. `wyss start` sobrevive socket huérfano; systemd Restart=.

---

## Errores por paso + eval dorado

**User's choice (sin alternativas, confirmado):** `on_error: retry|escalate|abort` declarado en el
Plan schema (Fase 5), enforcement en Fase 6. Eval set dorado anti-falso-A en CI (réplica del gate
`hit@1=20/20` de Fase 4): un falso-A rompe el build.

---

## Claude's Discretion

- Esquema de tablas SQLite de colas y nombres de métodos JSON-RPC.
- Formato de salida de `wyss audit`.
- Transport exacto del MCP server (stdio vs socket TCP local) — invariante: todo call pasa por el engine.
- Naming de agentes (identidad argentina) — configuración, no código.

## Deferred Ideas

- Enforcement de ejecución real (retry/backoff/abort, `Tool` port) → Fase 6.
- Motor de rutinas/scheduler (`routine_trigger` engine) → fase posterior (ex-Fase 9).
- Agentes de dominio con nombre (Belgrano, Sarmiento) → configuración posterior.

## Nota de proceso

- Selección inicial contradictoria del owner ("Lockear las 4" + revisar #1/#2/#3 simultáneo);
  aclarado con una pregunta (mismo principio ORCH-04: ante ambigüedad, preguntar). Owner eligió profundizar.
