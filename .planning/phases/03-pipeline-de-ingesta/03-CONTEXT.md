# Phase 3: Pipeline de Ingesta - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning

<domain>
## Phase Boundary

`wyss index <ruta>` escanea, extrae e indexa archivos de forma incremental (size+mtime→hash), reanudable (estado por archivo en SQLite) y con secretos excluidos ANTES de indexar. Entrega el pipeline COMPLETO: metadatos + FTS5 + chunks + embeddings a ChromaDB. La búsqueda sobre el índice es Fase 4 — acá solo se construye y puebla el índice.

</domain>

<decisions>
## Implementation Decisions

### Exclusión de secretos (KNOW-07)
- **D-27:** Archivo con secreto detectado → se excluye el archivo ENTERO del índice. Sin redacción ni exclusión parcial por chunk. Fail-closed coherente con el gateway: el owner limpia el archivo y re-indexa si quiere recuperarlo.
- **D-28:** Reporte de exclusiones: resumen al final de la corrida con rutas excluidas + estado `excluded_secret` por archivo en SQLite (consultable después) + AuditEvent por cada exclusión (regla #1).
- **D-29:** Detección en 3 capas: (1) denylist de rutas/extensiones (`.env*`, `*.key`, `*.pem`, `id_rsa`, `credentials`, etc.) — esos archivos NI SE ABREN; (2) reuso de `BUILTIN_SECRET_PATTERNS` de `src/gateway/secrets_patterns.py` sobre contenido — una sola fuente de verdad de patrones; (3) detector de alta entropía para tokens sin prefijo conocido.
- **D-30:** Válvula para falsos positivos: allowlist por ruta/glob en `config.toml` que desactiva SOLO la capa de entropía para esas rutas. Las capas de patrones conocidos y denylist de rutas NUNCA se apagan (aditivas, mismo espíritu que D-21). Editable solo por config+reload, sin comando de agente (regla #6).

### Vectores y embeddings
- **D-31:** Pipeline completo en Fase 3: metadatos + FTS5 + chunking + embeddings a ChromaDB vía `OllamaEmbeddingProvider` (construido en Fase 2). Fase 4 solo construye la búsqueda sobre el índice ya poblado.
- **D-32:** Ollama caído NO aborta la indexación: el escaneo+extracción+FTS5 completa igual; los archivos quedan en estado `extracted` (sin `embedded`) y un re-run con Ollama vivo completa los embeddings pendientes. Aviso claro al inicio de la corrida y en el resumen final. Coherente con reanudable (KNOW-03).
- **D-33:** Estrategia de chunking (tamaño, overlap, por tipo): la decide el researcher/planner con defaults en `config.toml` ajustables. El owner NO fijó números.
- **D-34:** `--estimate` proyecta: N archivos a procesar (nuevos/modificados), chunks proyectados, tamaño total, tiempo estimado de embedding local, y "costo API: $0 (Ollama local)" — la columna de costo queda cableada para un futuro provider pago (consistente con D-24, tabla local de precios).

### UX del CLI
- **D-35:** Progreso: barra interactiva (librería la elige el planner — rich/tqdm) con etapa (scan/extract/embed), archivo actual, N/total y ETA. En terminal no-interactiva (pipe/cron) degrada a líneas de log cada N archivos.
- **D-36:** Errores por archivo NO cortan la corrida: el archivo queda `failed` con el error en SQLite y la corrida sigue. Resumen final: "N indexados, M fallados, K excluidos por secretos" + comando para listar fallados. Aborta solo ante errores sistémicos (DB inaccesible, ruta raíz inexistente, disco lleno).
- **D-37:** Re-run muestra el conteo de skipped (sin cambios) en el resumen. `--dry-run` lista qué se indexaría y por qué (nuevo/modificado) sin tocar nada.
- **D-38:** Exit codes: 0 si la corrida completó (aunque haya archivos fallados — están reportados); ≠0 solo si la corrida no pudo completar.

### Archivos problemáticos
- **D-39:** Archivos `failed` se reintentan automáticamente en la próxima corrida, máximo 3 intentos (contador en SQLite); después quedan `failed` permanente hasta `--retry-failed` explícito.
- **D-40:** PDFs encriptados / formatos no soportados → estado `skipped_unsupported` (distinto de `failed`, no se reintentan). Nunca pedir passwords.
- **D-41:** Límite de tamaño de archivo configurable en `config.toml` (default lo valida el researcher); archivos que lo excedan se indexan SOLO con metadatos.
- **D-42:** Symlinks NO se siguen (evita loops y duplicados); quedan registrados como `skipped_symlink`. Dirs ocultos y de ruido (`.git`, `node_modules`, `.cache`, etc.) excluidos por denylist de dirs configurable.

### Claude's Discretion
- Librería de barra de progreso (rich vs tqdm vs alternativa).
- Esquema exacto de la tabla de estado por archivo en SQLite (estados mínimos: pending/extracted/embedded/failed/excluded_secret/skipped_unsupported/skipped_symlink + attempts + error).
- Umbral y algoritmo del detector de entropía (researcher investiga; Shannon vs otros).
- Cómo se nombra/selecciona la BC destino en el CLI (`--bc <nombre>` con default, o derivada de la ruta) — respetando KNOW-11: colección separada por BC.
- Defaults de chunking y límite de tamaño.
- Modo "piloto automático" autorizado por el owner: ante decisiones menores no listadas, tomar la opción recomendada sin preguntar; consultar solo si algo es serio (cambia arquitectura, seguridad o scope).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Spec del owner
- `docs/18-prompt-implementacion.md` — spec canónica: hexagonal, SOLID, plugin pattern para extractores, reglas inviolables 1-9 (regla #8 = secretos nunca se indexan).

### Decisiones y artefactos previos
- `.planning/phases/01-fundaciones/01-CONTEXT.md` — D-01..D-13 (layout, audit inyectado, config TOML+Pydantic en bootstrap, DI manual).
- `.planning/phases/02-gateway-de-modelos/02-CONTEXT.md` — D-14..D-26 (Ollama local para embeddings D-15, tabla local de precios D-24).
- `src/gateway/secrets_patterns.py` — BUILTIN_SECRET_PATTERNS a reusar en la capa 2 de detección (D-29). Final y aditivo — extender, nunca debilitar.
- `src/core/ports/knowledge.py` — ports de knowledge ya definidos en Fase 1; las implementaciones de esta fase los rellenan (D-11: módulos vecinos importan de core/ports).
- `src/gateway/providers/ollama.py` — OllamaEmbeddingProvider existente para los embeddings (D-31).
- `.planning/REQUIREMENTS.md` — KNOW-01..03, 06..09, 11 con criterios exactos.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/gateway/secrets_patterns.py`: patrones de secretos compartidos — la ingesta los importa, no los duplica.
- `src/gateway/providers/ollama.py`: provider de embeddings listo (httpx, localhost:11434).
- `src/gateway/db.py` (`open_gateway_db`): patrón WAL fail-fast + permisos 0600 — replicar para la DB de índice/estado.
- `src/bootstrap/config.py`: WyssConfigModel extra=forbid + loader .env — agregar sección `[ingest]` acá.
- `src/audit/`: SqliteAuditLogger — inyectar AuditPort al pipeline (D-08).

### Established Patterns
- Pydantic SOLO en bootstrap (lint-imports lo refuerza); core stdlib-only.
- Frozen dataclasses de dominio en `core/domain/`; settings frozen convertidas desde Pydantic en bootstrap.
- Estados y errores como excepciones de dominio (`core/domain/errors.py`).
- TDD con cadena verde: `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports`.

### Integration Points
- `src/knowledge/` (scaffold vacío) — acá vive el pipeline: scanner, extractores (plugin registry), chunker, indexer FTS5, embedder, state store.
- `src/core/ports/knowledge.py` — contratos a implementar.
- CLI `wyss index` — primer comando CLI real del proyecto; entry point a definir por el planner (composition root en bootstrap).
- DB del índice SEPARADA de audit.db y traces.db (D-06/D-22: datos de usuario aparte).

</code_context>

<specifics>
## Specific Ideas

- Volumen real del owner: ~2 TB en `~/Data/` — las decisiones de incremental/reanudable/errores están pensadas para ese volumen (una corrida larga no puede morir por un PDF roto ni por Ollama caído).
- Prueba dirigida obligatoria (criterio 4 del roadmap): BC trampa con secreto plantado → el secreto NO aparece en el índice (FTS5 ni Chroma).
- Test de extensibilidad (criterio 6): registrar un extractor nuevo sin tocar una línea del pipeline.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 3-pipeline-de-ingesta*
*Context gathered: 2026-06-12*
