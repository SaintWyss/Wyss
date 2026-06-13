# Phase 4: Búsqueda Híbrida - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning

<domain>
## Phase Boundary

`wyss search "<consulta>"` — recuperación híbrida sobre el índice ya poblado por Fase 3: FTS5 + vectores fusionados con RRF, < 5 segundos, cada resultado con ruta exacta + extracto + fuente + fecha, funciona degradada sin vectores, toda consulta auditada, eval set dorado en CI. Implementa el port `Retrieval` (async, fusionado). El daemon/orquestador que consume la búsqueda es Fase 5 — acá el único caller es el owner por CLI. (KNOW-04, KNOW-05, KNOW-10, AUD-03.)

</domain>

<decisions>
## Implementation Decisions

### Salida del CLI `wyss search`
- **D-43:** Modo híbrido de presentación: **Rich Panels verticales por hit** (ruta exacta, extracto con término resaltado, fuente, fecha — KNOW-05 completo, sin truncar) como default interactivo + **`--json`** para scripting (n8n, Hermes en Fase 5) + auto-JSON al detectar pipe vía `sys.stdout.isatty()` (patrón ya existente en `_run_with_progress()`). `--limit` default 10; `--kb` para acotar BC. rich ya es dependencia declarada y usada en `cli.py` — cero deps nuevas.

### Degradación sin vectores
- **D-44:** Ollama caído o embeddings pendientes → **auto-fallback a FTS5-only** con banner visible en modo interactivo + campo `degraded: true` (con motivo) en la salida JSON + **exit code 0** (coherente con D-38: exit ≠ 0 solo si la corrida no completó, y con D-32: Ollama caído es degradación explícita, no error fatal). La degradación queda registrada en el AuditEvent de la consulta. Flag `--fts-only` para forzar el modo degradado deliberadamente (benchmarks, tests). Rechazado exit code 2: confunde degradado con error.

### Eval set dorado (AUD-03)
- **D-45:** Estrategia A — **corpus fixture sintético commiteado al repo + FakeEmbedding (existente de Fase 2) + métrica hit@1 + gate duro en CI**, N=20 consultas doradas → archivo esperado. Cero dependencias externas en CI (sin Ollama, sin los 2 TB), determinista, espejo del patrón POL-06 (planes dorados). Un set curado por el owner sobre archivos reales (corrido localmente con Ollama vivo) puede agregarse después como extensión aditiva — no bloquea esta fase.

### Alcance de BC
- **D-46:** Default busca en **todas las BC del owner**; `--kb` opcional acota. Implementación sin deuda hacia Fase 7: el CLI pasa wildcard que la capa de servicio expande a la lista de BCs — el port `Retrieval(query, subject)` siempre recibe `kb_ids` explícitos (parámetro estructural, KNOW-11). En Fase 7 el wildcard muere en el borde del CLI sin tocar el port.

### Frescura del índice (KNOW-10)
- **D-47:** Doble superficie: **footer compacto de 1 línea en cada búsqueda** ("indexado al [fecha] · N BCs") + **comando `wyss status`** con detalle por BC (última corrida, archivos por estado, pendientes de embedding). Query de frescura **centralizada en el service layer** — ambas superficies llaman a la misma función; fuente: state store SQLite de Fase 3 (mtime/estados por path+kb_id). Nunca dos queries divergentes.

### Claude's Discretion
- Parámetros de RRF (constante k, pesos relativos FTS5/vector) — researcher valida defaults estándar (k=60 típico); configurables en `config.toml`.
- Esquema exacto del JSON de salida (campos de Hit + metadata de corrida).
- Umbral exacto del gate hit@1 en CI y composición del corpus fixture (tipos de archivo, tamaño).
- Cómo se obtiene la fecha por resultado (mtime del archivo vs fecha de indexación) — respetando KNOW-05.
- Detalle del comando `wyss status` (formato, campos adicionales útiles).
- Modo "piloto automático" autorizado por el owner (heredado de Fase 3): ante decisiones menores no listadas, tomar la opción recomendada sin preguntar; consultar solo si cambia arquitectura, seguridad o scope.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Spec del owner
- `docs/18-prompt-implementacion.md` — spec canónica: hexagonal, SOLID, plugin pattern, reglas inviolables 1-9 (regla #1: sin auditar no está terminado).
- `docs/16-criterios-de-aceptacion.md` — criterio transversal: nada se acepta con acción sin auditar.

### Decisiones y artefactos previos
- `.planning/phases/03-pipeline-de-ingesta/03-CONTEXT.md` — D-27..D-42 (estados por archivo, D-32 Ollama caído no aborta, D-38 exit codes) — precedentes directos de D-44.
- `.planning/phases/02-gateway-de-modelos/02-CONTEXT.md` — D-15 (Ollama embeddings local), D-22 (separación de DBs).
- `.planning/REQUIREMENTS.md` — KNOW-04, KNOW-05, KNOW-10, AUD-03 con criterios exactos.

### Contratos y código existente (NO romper, implementar/extender)
- `src/core/ports/knowledge.py` — `FullTextIndex`, `VectorIndex`, `Retrieval` (async; el contrato que esta fase implementa con fusión RRF + filtrado kb_ids).
- `src/core/domain/knowledge.py` — `Hit`, `Query`, `IndexEntry`, `FileStatus`.
- `src/knowledge/fts_index.py` — `FTS5Index.search()` con bm25 + snippet, funcionando.
- `src/knowledge/vector_index.py` — `ChromaVectorIndex.search()` cosine por colección/BC, funcionando.
- `src/knowledge/state_store.py` — estados por (path, kb_id) — fuente de la frescura (D-47).
- `src/gateway/providers/ollama.py` — `OllamaEmbeddingProvider` para embeber la query.
- `src/bootstrap/cli.py` — typer app con `wyss index`; patrones `_print_estimate()`, `isatty()`; acá se agregan `search` y `status`.
- `tests/ports/fakes.py` — FakeEmbedding y fakes de conformance para el eval set (D-45).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `FTS5Index.search()` y `ChromaVectorIndex.search()`: ambos lados de la fusión ya implementados y testeados en Fase 3 — esta fase construye el fusionador RRF encima, no los índices.
- `OllamaEmbeddingProvider` (httpx, localhost:11434): embebe la query; su fallo dispara D-44.
- rich (`Console`, `Table`, `Progress`) ya en uso en `cli.py` — Panels sin deps nuevas.
- State store SQLite: query de frescura lee de acá (última corrida, estados).

### Established Patterns
- Core stdlib-only (lint-imports); el fusionador RRF es lógica pura → candidato a `core/` o `knowledge/` según imports.
- Fail-closed en seguridad, resiliente en disponibilidad con aviso (D-32/D-44).
- AuditPort inyectado por constructor (D-08) — el servicio de búsqueda lo recibe y audita cada consulta.
- TDD cadena verde: `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports`.

### Integration Points
- `src/knowledge/` — vive el servicio de retrieval (fusión RRF + degradación + frescura).
- `src/bootstrap/cli.py` — comandos `search` y `status`; composition root cablea índices reales (hoy hay `_NoopFullTextIndex`/`_NoopVectorIndex` placeholder — reemplazar por los reales).
- Consumidor futuro: Fase 5 (orquestador/Hermes) llama `Retrieval.search(query, subject)` — no acoplar el servicio al CLI.

</code_context>

<specifics>
## Specific Ideas

- Primer valor real para el owner: `wyss search` sobre ~2 TB en `~/Data/` — la vara es "encuentro cualquier cosa en segundos".
- Pendiente operativo previo a verificar esta fase: corrida de ingesta real con Ollama UP para poblar embeddings (los archivos en estado `extracted` sin `embedded` solo ejercitan el camino degradado).
- Las 4 decisiones fueron seleccionadas de tablas comparativas con research (advisor mode) — el owner eligió la opción recomendada en las 4 áreas.

</specifics>

<deferred>
## Deferred Ideas

- **Set de eval curado por el owner sobre archivos reales** (N=50, MRR@5, corrido localmente con Ollama) — extensión aditiva del eval set sintético de D-45; evaluar en Fase 5+ cuando la búsqueda tenga uso real acumulado.

</deferred>

---

*Phase: 4-Búsqueda Híbrida*
*Context gathered: 2026-06-12*
