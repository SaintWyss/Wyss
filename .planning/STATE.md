---
gsd_state_version: 1.0
milestone: v0.1
milestone_name: milestone
status: executing
last_updated: "2026-06-12T23:46:53.886Z"
last_activity: 2026-06-12
progress:
  total_phases: 10
  completed_phases: 2
  total_plans: 18
  completed_plans: 12
  percent: 20
---

# Wyss — State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-10)

**Core value:** Encontrar cualquier cosa en 2 TB en segundos + delegar tareas a agentes con control total y auditoría de todo.
**Current focus:** Phase 03 — pipeline-de-ingesta

## Current Position

Phase: 03 (pipeline-de-ingesta) — EXECUTING
Plan: 2 of 7

- **Phase:** 3 of 10 (pipeline de ingesta)
- **Status:** Executing Phase 03 — Plan 1 complete
- **Last activity:** 2026-06-12

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
| 2026-06-12 | `AgentModelRequest` +tier/+purpose con defaults (`economico`/`general`) | D-26: campos aditivos con default no rompen construcciones posicionales de Fase 1 (Pitfall 5); suite de ports verde (02-01) |
| 2026-06-12 | `SecretDetected` solo recibe `pattern_name`, jamás el secreto | D-20 fail-closed: el error nombra el patrón que matcheó; el valor sensible nunca entra a la clase ni al audit (02-01) |
| 2026-06-12 | `UnknownTier(tier, *, available)` sin fallback silencioso | D-17: tier desconocido → error explícito con tiers disponibles; el router nunca enruta a un default (02-01) |
| 2026-06-12 | Re-export de las 3 excepciones desde `core.domain.__init__` | Coherente con PolicyViolation/ConfigError ya re-exportados; replica el patrón existente del repo, no inventa uno nuevo (02-01) |
| 2026-06-12 | httpx directo (sin SDK anthropic/openai, sin tenacity) | Evita doble-retry; el retry manual centralizado se hace en 02-05 (02-01) |
| 2026-06-12 | `ContextMinimizer.scan` fail-closed de 3 fuentes (env_values + built-in + config) | GATE-03: secreto detectado → `SecretDetected` → la llamada NO sale (D-20); nunca redacta. Spine de seguridad del gateway (02-02) |
| 2026-06-12 | `BUILTIN_SECRET_PATTERNS` `Final[tuple]` no vaciable; merge aditivo `BUILTIN + config` | D-21: config solo AGREGA patrones; si pudiera vaciarlos la minimización dejaría de ser absoluta editando un archivo. Espejo de `BUILTIN_DENY` (02-02) |
| 2026-06-12 | `env_values` filtrados a `len>=8`; el valor del secreto jamás entra a la excepción | Evita falsos positivos de strings triviales; el error solo lleva `pattern_name`, nunca el secreto (D-20, V7) (02-02) |
| 2026-06-12 | `ModelRouter` determinístico `tier->TierConfig` fail-closed | D-16/D-17: lookup puro por config; tier inexistente → `UnknownTier(available)` sin fallback silencioso; espejo del fail-closed de `CognitivePolicyEngine` (02-03) |
| 2026-06-12 | `TierConfig` frozen en `core.domain.gateway` (no en router.py) | Bootstrap (02-05) y gateway la importan sin ciclo; `max_tokens` lo fija el tier, NO el caller (Open Question 1 resuelta) (02-03) |
| 2026-06-12 | Providers httpx directo (sin SDK); `cost_usd=0.0` desde el adapter | Anti doble-retry (Pitfall 1, D-25): `raise_for_status` propaga 4xx, retry vive en el gateway; el dict de la API muere en el adapter; el CostTracker calcula el costo (D-24) (02-03) |
| 2026-06-12 | `OllamaEmbeddingProvider` reusa `EmbeddingProvider` de core/ports/knowledge | No se inventa port nuevo (D-15); embeddings LOCALES vía `/api/embed`; test real opt-in `skipif WYSS_TEST_OLLAMA` (espejo del NTFS) (02-03) |
| 2026-06-12 | `TraceStore` NO append-only: replica el WAL fail-fast de audit pero omite triggers; `purge_older_than(90d)` (D-22) | traces expira por retención, audit es forever; `TraceIntegrityError` nuevo nombra el subsistema correcto (02-04) |
| 2026-06-12 | `spend_ledger` del gate de costo vive en `traces.db` (una sola DB de gateway, Open Question 3) | `CostTracker` y `TraceStore` comparten la DB; el DDL del ledger lo aporta `traces_schema.apply_schema` idempotente (02-04) |
| 2026-06-12 | `CostTracker.authorize` veta con `BudgetExceeded` ANTES de la llamada; costo LOCAL gobierna, no el del provider; sin setters de límites | Presupuesto enforced no advisory (Pitfall 2, D-18/D-24); test verifica que el provider nunca se invoca al exceder; destrabe solo por config+reload (D-19) (02-04) |
| 2026-06-12 | `ModelGateway.ask` orquesta Flow 4 con retry centralizado en el gateway (no en providers) | D-25: 2x transiente (429/5xx/timeout), 4xx fail-fast, gate re-pasado cada intento, sin fallback de tier; evita doble-retry (Pitfall 1) (02-05) |
| 2026-06-12 | `GatewaySettings` frozen con default vacío en `WyssSettings` | No rompe configs de Fase 1 sin sección [gateway]; sección presente se valida fail-closed (extra=forbid) (02-05) |
| 2026-06-12 | `build_gateway` es el único composition root del gateway; API keys solo de os.environ | Pattern 4: cablea adapters+application+facade; AuditPort inyectado nunca import audit; keys jamás en config/traces/AuditEvent (V2, Pitfall 4) (02-05) |
| 2026-06-12 | `traces.db` con chmod 0600 en `TraceStore` (best-effort, suppress OSError) | T-02-trace-file-perms: prompts completos post-min restringidos al owner; cubre toda creación de la DB, tolerante a FS sin modos POSIX (02-05) |

## Blockers

(None)

## Notes

- STACK.md y PITFALLS.md del research escritos inline (límite de sesión cortó los agentes) — versiones de libs a confirmar con `uv add` en Fase 1
- Los stubs existentes en `src/` son placeholders del init original — la Fase 1 define la estructura real (`core/ports/` etc.)
- Research flags: Fases 3-4 (chunking/embeddings a escala), 7 (memoria + anti-injection) y 10 (canal mensajería) necesitarán research adicional al planificarlas
