---
gsd_state_version: 1.0
milestone: v0.1
milestone_name: milestone
status: En ejecución — 05-01/02/03/04 verdes y commiteados; 05-05 diferido
last_updated: "2026-06-13T16:50:20.009Z"
last_activity: 2026-06-13
progress:
  total_phases: 10
  completed_phases: 4
  total_plans: 27
  completed_plans: 26
  percent: 40
---

# Wyss — State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-10)

**Core value:** Encontrar cualquier cosa en 2 TB en segundos + delegar tareas a agentes con control total y auditoría de todo.
**Current focus:** Phase 5 — orquestador daemon

## Current Position

Phase: 05 (orquestador-daemon) — 4/5 planes COMPLETE, 05-05 BLOQUEADO
Plan: 05-05 (Hermes adapter + MCP server) — BLOQUEADO por A2

- **Phase:** 5 of 10 (orquestador daemon)
- **Status:** En ejecución — 05-01/02/03/04 verdes y commiteados; 05-05 diferido
- **Last activity:** 2026-06-13
- **Blocker 05-05:** A2 FAIL (sin imagen Hermes publicada → clonar+`docker build`), A3 pendiente (key disabled_toolsets), A4 fix UFW. Detalle en `phases/05-orquestador-daemon/05-EMPIRICAL.md`.
- **Next:** revisar/re-planear 05-05 con build-local de Hermes (clonar NousResearch/hermes-agent, buildear, cerrar A3), luego ejecutar. Resto de la fase punta a punta con FakeOrchestrator.

## Decisions Log

| Date | Decision | Context |
|------|----------|---------|
| 2026-06-11 | **Fase 1 (resumen):** 12 decisiones — fail-closed D por valor+isinstance, agregados nivel-plan anti-bypass, BUILTIN_DENY no vaciable, WAL fail-fast, ConfigError en dominio | Detalle: `phases/01-fundaciones/01-DECISIONS.md` |
| 2026-06-12 | **Fase 2 (resumen):** 19 decisiones — gateway fail-closed (SecretDetected sin valor, BUILTIN_SECRET_PATTERNS no vaciable, UnknownTier sin fallback), httpx sin SDK, retry solo en gateway, CostTracker veta pre-llamada, traces.db 0600/90d | Detalle: `phases/02-gateway-de-modelos/02-DECISIONS.md` |
| 2026-06-10 | Roadmap de 10 fases por build order técnico, no las 5 fases del prompt | Dependencias reales: gateway antes que indexación (embeddings), fundaciones antes que todo |
| 2026-06-10 | Las 10 features gap del research incluidas en v1 | Table stakes — se insertan en fases existentes |
| 2026-06-10 | pymupdf primario para PDF (no PyPDF2) | PyPDF2 deprecado; throughput crítico a 2TB |
| 2026-06-10 | Clasificación nivel D determinística por denylist | El LLM puede ser persuadido vía contenido indexado; solo puede subir riesgo |
| 2026-06-10 | Permisos como scoped facades (capability-based) | Filtro estructural antes del retrieval, no checks post-hoc |
| 2026-06-12 | `SecretFilter` de 3 capas (env_values + built-in patterns + config), fail-closed, excluye pre-indexado | KNOW-07: chunk con secreto detectado se descarta; el contenido sensible nunca entra al FTS5/vector; puro + inyectado; espejo del ContextMinimizer del gateway (03-03) |
| 2026-06-12 | `IngestRunResult.warnings` campo aditivo con default `()` | Aviso Ollama-down viaja en el resultado sin romper construcciones existentes (patrón D-26); cross-AI exec (03-06) |

## Blockers

(None)

## Notes

- STACK.md y PITFALLS.md del research escritos inline (límite de sesión cortó los agentes) — versiones de libs a confirmar con `uv add` en Fase 1
- Los stubs existentes en `src/` son placeholders del init original — la Fase 1 define la estructura real (`core/ports/` etc.)
- Research flags: Fases 3-4 (chunking/embeddings a escala), 7 (memoria + anti-injection) y 10 (canal mensajería) necesitarán research adicional al planificarlas
