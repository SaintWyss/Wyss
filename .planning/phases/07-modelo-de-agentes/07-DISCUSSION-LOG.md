# Phase 7 — Discussion Log

**Fecha:** 2026-06-13 (sesión 10)
**Modo:** advisor (owner técnico, directiva delegador)

## Áreas presentadas (gray areas)

Se ofrecieron 4 áreas; el owner seleccionó las 4. Cada una con recomendación pre-cargada.

### 1. Anti-injection (POL-07)
- **Opciones:** wrapping estructural + re-evaluación por engine vs. solo confiar en rechazo D de AgentBase.
- **Selección:** wrapping `<untrusted_content>` + plan re-pasa por `engine.evaluate` (2ª muralla) + test dorado anti-injection. → D-70.

### 2. Memoria del agente (AGENT-08)
- **Opciones:** MEMORY.md markdown per-agente vs. store SQLite.
- **Selección:** MEMORY.md en `data/agents/<id>/`, write-path solo owner/extracción supervisada, BC nunca escribe directo, v0.1 estructurado. → D-71.

### 3. Permisos: store + revocación (AGENT-03/04)
- **Opciones:** grants en TOML vs. SQLite; cache vs. por-query.
- **Selección:** grants en config TOML + scoped facade verifica por-query sin cache, bloqueo+audit antes del retrieval. → D-72.

### 4. Schema config del agente (AGENT-02)
- **Opciones:** `[[agents]]` en config.toml vs. archivos por agente.
- **Selección:** `[[agents]]` en config.toml validado Pydantic en bootstrap, AgentRegistry instancia ConfiguredAgent. → D-73.

## Confirmación final
"Cerrar las 4 y seguir" → CONTEXT.md escrito, avanza a research+plan.

## Deferred
- Extracción inteligente automática de memoria → futura fase.
- AGENT-07 (presupuesto runtime) + AGENT-09 (Belgrano) → Fase 8.

## Claude's Discretion
Directiva owner: piloto automático para decisiones menores; consultar solo arquitectura/seguridad/scope.
