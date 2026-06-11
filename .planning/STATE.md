---
gsd_state_version: 1.0
milestone: v0.1
milestone_name: milestone
status: verifying
last_updated: "2026-06-11T19:32:36.298Z"
last_activity: 2026-06-11
progress:
  total_phases: 10
  completed_phases: 1
  total_plans: 6
  completed_plans: 6
  percent: 10
---

# Wyss — State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-10)

**Core value:** Encontrar cualquier cosa en 2 TB en segundos + delegar tareas a agentes con control total y auditoría de todo.
**Current focus:** Phase 01 — fundaciones

## Current Position

Phase: 01 (fundaciones) — EXECUTING
Plan: 6 of 6

- **Phase:** 1 of 10 (Fundaciones)
- **Status:** Phase complete — ready for verification
- **Last activity:** 2026-06-11

## Decisions Log

| Date | Decision | Context |
|------|----------|---------|
| 2026-06-10 | Roadmap de 10 fases por build order técnico, no las 5 fases del prompt | Dependencias reales: gateway antes que indexación (embeddings), fundaciones antes que todo |
| 2026-06-10 | Las 10 features gap del research incluidas en v1 | Table stakes — se insertan en fases existentes |
| 2026-06-10 | pymupdf primario para PDF (no PyPDF2) | PyPDF2 deprecado; throughput crítico a 2TB |
| 2026-06-10 | Clasificación nivel D determinística por denylist | El LLM puede ser persuadido vía contenido indexado; solo puede subir riesgo |
| 2026-06-10 | Permisos como scoped facades (capability-based) | Filtro estructural antes del retrieval, no checks post-hoc |
| 2026-06-11 | `include_external_packages=true` en import-linter | El contrato `forbidden` de `core` lista `pydantic` (externo); sin esa opción `lint-imports` aborta (01-01) |
| 2026-06-11 | `uv.lock` commiteado; `src/__init__.py` eliminado | Instalaciones reproducibles; el `__init__.py` raíz rompía los imports flat `from core...` (Assumption A5) (01-01) |
| 2026-06-11 | `AgentBase` en `core/ports/agent.py` (Open Question 1) | Satisface "14 ports en core/ports/" y es puro (solo domain + ports); import-linter verde (01-02) |
| 2026-06-11 | `execute(plan, decision)` recibe ambos | `Plan` es frozen y solo lleva `estimated_risk`; el nivel FINAL viaja en `PolicyDecision` (01-02) |
| 2026-06-11 | `SqliteAuditLogger.span()` usa `AuditEvent.new` directo | El dominio frozen solo expone `new()`; el adapter compone los SPAN_* sin inventar API en el núcleo puro (01-03) |
| 2026-06-11 | Smoke test WAL fail-fast al construir el logger | `journal_mode≠wal` → `AuditIntegrityError`; nunca degradar silencioso un audit log sobre NTFS/fuseblk (Pitfall 6/T4) (01-03) |
| 2026-06-11 | Test ntfs opt-in vía `skipif` por `WYSS_TEST_NTFS` | No alterar `addopts` globales; el test de integración sobre el mount real corre solo on-demand (01-03) |
| 2026-06-11 | Guarda de rechazo D por valor/orden + `isinstance` fail-closed (no `is`) | CR-01: `risk_level is RiskLevel.D` era no-op ante ints crudos de deserialización JSON-RPC; ahora `risk >= RiskLevel.D` tras isinstance guard rechaza fail-closed (POL-03, 01-04) |
| 2026-06-11 | `CognitivePolicyEngine` sin `evaluate_action()` público; agregados a nivel-plan | Evaluar pasos uno a uno saltearía los umbrales agregados (bypass por composición); 200 deletes → D solo si se evalúa el plan entero (POL-05, 01-05) |
| 2026-06-11 | `BUILTIN_DENY` como `Final[tuple[DenyRule,...]]` en código, no en TOML | La config solo agrega reglas (`deny = BUILTIN_DENY + config`); nunca puede vaciarlas — D sigue absoluto sin importar el TOML (regla #2; POL-04, 01-05) |
| 2026-06-11 | `load_settings` levanta `ConfigError` (dominio) en vez de `sys.exit` | Fail-fast testeable con `pytest.raises`; el caller CLI de Fase 5 decide el exit. Pydantic muere en bootstrap — core nunca ve un BaseModel (import-linter; SC5, 01-06) |
| 2026-06-11 | deny rules de config: `match_action`→`action_type`, `match_target`→`target_patterns` | Mapeo del TOML canónico al `DenyRule` de dominio; `match_target` ausente = tupla vacía (matchea cualquier target) (01-06) |

## Blockers

(None)

## Notes

- STACK.md y PITFALLS.md del research escritos inline (límite de sesión cortó los agentes) — versiones de libs a confirmar con `uv add` en Fase 1
- Los stubs existentes en `src/` son placeholders del init original — la Fase 1 define la estructura real (`core/ports/` etc.)
- Research flags: Fases 3-4 (chunking/embeddings a escala), 7 (memoria + anti-injection) y 10 (canal mensajería) necesitarán research adicional al planificarlas
