# Decisions — Fase 2 (gateway-de-modelos)

Movidas desde STATE.md al cierre de fase (compactación del Decisions Log).

| Date | Decision | Context |
|------|----------|---------|
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
