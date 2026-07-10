# Pitfalls Research

**Proyecto:** Wyss
**Dimensión:** Pitfalls (errores comunes en sistemas similares)
**Investigado:** 2026-06-10
**Confianza:** MEDIUM-HIGH (escrito inline desde patrones conocidos de RAG local, daemons Python y orquestadores multi-agente)

---

## Área 1 — Indexación local sobre 2TB

- **Pitfall**: Indexar todo de una sola pasada sin checkpoint. Un crash a las 6 horas pierde todo el progreso.
  - **Warning sign**: el pipeline no persiste estado por archivo procesado.
  - **Prevention**: tabla `files` en SQLite con estado por archivo (pending/extracted/embedded/failed). El escaneo es reanudable por diseño desde el commit 1.
  - **Phase**: 1

- **Pitfall**: Embeddings de todo el corpus de entrada = costo descontrolado (2TB puede ser millones de chunks → cientos de dólares).
  - **Warning sign**: no hay estimación de costo antes de arrancar el embedding masivo.
  - **Prevention**: `wyss index --estimate` que cuenta chunks y proyecta costo ANTES de llamar a la API. Embedding por lotes con presupuesto configurable. FTS5 primero (gratis) — la búsqueda funciona sin vectores; los vectores mejoran, no habilitan.
  - **Phase**: 1

- **Pitfall**: Chunking naive (N caracteres fijos) rompe semántica y arruina retrieval.
  - **Warning sign**: resultados de búsqueda devuelven fragmentos cortados a mitad de oración.
  - **Prevention**: chunking por estructura (párrafos/headers para MD, páginas para PDF) con overlap. Tamaño objetivo ~512 tokens.
  - **Phase**: 1

- **Pitfall**: Archivos corruptos/raros (PDFs escaneados, encodings rotos, archivos de 0 bytes, symlinks circulares) matan el pipeline.
  - **Warning sign**: el extractor no tiene try/except por archivo con registro de fallo.
  - **Prevention**: todo extractor falla *por archivo*, registra el error en la tabla `files`, sigue. Nunca un archivo malo detiene el escaneo. Límite de tamaño configurable por tipo.
  - **Phase**: 1

- **Pitfall**: NTFS (~/Data es NTFS) — mtime y permisos se comportan distinto; hash-only para detección de cambios es lento sobre 2TB.
  - **Warning sign**: re-indexación incremental tarda horas sin cambios reales.
  - **Prevention**: detección en dos niveles: (size + mtime) como filtro rápido → hash solo si cambió. Nunca hashear 2TB enteros por pasada.
  - **Phase**: 1

## Área 2 — Daemon Python (Unix socket + JSON-RPC)

- **Pitfall**: Socket file huérfano tras crash → "Address already in use" al reiniciar.
  - **Warning sign**: `wyss start` falla tras kill -9.
  - **Prevention**: al boot, si el socket existe, probar conexión; si nadie responde, borrar y recrear. Lockfile con PID.
  - **Phase**: 2

- **Pitfall**: Operaciones largas (indexar, llamada LLM) bloquean el event loop → el daemon no responde.
  - **Warning sign**: `wyss ask` se cuelga mientras corre un index.
  - **Prevention**: trabajo pesado en `asyncio.to_thread` o ProcessPoolExecutor; el loop solo coordina. Timeouts en todas las llamadas externas.
  - **Phase**: 2

- **Pitfall**: Estado solo en memoria del daemon → reinicio pierde confirmaciones pendientes y propuestas de rutinas.
  - **Warning sign**: tras restart, las propuestas B/C pendientes desaparecieron.
  - **Prevention**: toda cola de pendientes vive en SQLite, no en RAM. El daemon es stateless recuperable.
  - **Phase**: 2 (crítico para Fase 4 — propuestas de rutinas)

## Área 3 — Cognitive Policy Engine (nivel D absoluto)

- **Pitfall**: Clasificación de riesgo hecha por el LLM → el LLM puede ser persuadido (prompt injection vía contenido de archivos indexados).
  - **Warning sign**: el nivel de riesgo de una acción viene de una llamada al modelo sin validación determinística.
  - **Prevention**: la clasificación D es **determinística** (denylist de operaciones: rm masivo, modificación de config propia, exfiltración). El LLM puede *subir* el riesgo estimado, nunca bajarlo. Defensa en profundidad: el adapter de ejecución re-verifica antes de ejecutar (segunda muralla).
  - **Phase**: 2

- **Pitfall**: Bypass por composición — acción D disfrazada de pasos A/B individuales (borrar 1000 archivos de a uno).
  - **Warning sign**: la política evalúa pasos individuales, no el plan completo.
  - **Prevention**: la política evalúa el Plan entero + agregados (cuántos archivos toca, qué directorios). Umbrales acumulativos.
  - **Phase**: 2

- **Pitfall**: Confirmación fatigada — si todo pide confirmación, el owner confirma sin leer.
  - **Warning sign**: el owner escribe "s" reflejo en < 2 segundos.
  - **Prevention**: calibrar A/B agresivamente — lecturas y operaciones reversibles son A. La confirmación debe ser rara para que signifique algo.
  - **Phase**: 2

## Área 4 — Permission system (agente ↔ BC)

- **Pitfall**: Filtro de permisos aplicado *después* del retrieval (post-filter) → el contenido prohibido ya entró al contexto del agente.
  - **Warning sign**: el RetrievalEngine busca en todas las colecciones y filtra resultados.
  - **Prevention**: regla inviolable #3 ya lo cubre — filtro ANTES de buscar. Con ChromaDB: colección separada por BC; el agente literalmente no recibe handle de colecciones no habilitadas. Capability-based, no check-based.
  - **Phase**: 3

- **Pitfall**: Revocación que no aplica a sesiones en curso.
  - **Warning sign**: agente con tarea larga sigue leyendo BC revocada.
  - **Prevention**: el permiso se verifica en cada query de retrieval, no al inicio de la tarea. Sin cache de permisos.
  - **Phase**: 3

## Área 5 — Extractores multi-formato

- **Pitfall**: God-class extractor con if/elif por extensión → cada formato nuevo modifica código existente (viola regla #9).
  - **Prevention**: `ExtractorRegistry` con Protocol `can_handle()/extract()` desde el día 1. Test explícito: registrar extractor fake nuevo sin tocar pipeline.
  - **Phase**: 1

- **Pitfall**: Confiar en la extensión del archivo → .pdf renombrado a .txt rompe el extractor o mete binario al índice.
  - **Prevention**: `python-magic` (libmagic) decide el tipo; la extensión es hint secundario.
  - **Phase**: 1

## Área 6 — Cost management LLM

- **Pitfall**: Tracking de costo "para después" → primera factura sorpresa.
  - **Prevention**: CostTracker es parte del Gateway desde el primer commit de Fase 2. Toda llamada registra tokens in/out y costo calculado. Presupuesto diario/mensual con hard-stop configurable.
  - **Phase**: 2

- **Pitfall**: Contexto creciente sin control — historiales completos enviados en cada llamada.
  - **Warning sign**: costo por llamada crece linealmente con la vida de la sesión.
  - **Prevention**: Context Minimizer con límite duro de tokens por llamada; truncado explícito y loggeado.
  - **Phase**: 2

## Cross-Cutting Pitfalls

1. **Auditoría como afterthought** — si el AuditLogger se integra al final, la mitad de los paths no auditan. Prevención: el AuditLogger es la *primera* pieza de Fase 1; toda función relevante lo recibe inyectado. Criterio transversal de aceptación ya lo exige.
2. **Tests de seguridad como tests felices** — probar que el permiso funciona cuando existe, no que *bloquea* cuando falta. Prevención: los tests de las reglas inviolables son tests de *ausencia* (acceso sin permiso → excepción + registro de auditoría).
3. **Sobre-ingeniería del hexágono en v0.1** — 40 interfaces para 5 implementaciones. Prevención: port solo donde hay ≥2 implementaciones reales o un test que lo necesite (embeddings, extractores, vector store, LLM providers, ejecución). El resto, clases concretas hasta que duela.
4. **Scope creep multi-agente antes de que el índice sirva** — la Fase 1 entrega el valor real (encontrar archivos). Si la Fase 1 no cierra sus criterios, nada de lo demás importa.

## Quick Wins

- `wyss index --dry-run` y `--estimate`: lista qué se indexaría y costo proyectado. Barato, previene desastres de costo.
- Denylist de rutas por default: `.git/`, `node_modules/`, `__pycache__/`, `.env*`, `*.key`, `~/.ssh/` — excluidas antes de cualquier extracción.
- systemd user unit con `Restart=on-failure` desde Fase 2 — supervisión gratis.
- `PRAGMA journal_mode=WAL` en todos los SQLite — lecturas concurrentes daemon+CLI sin locks.
- Fixture de "BC trampa" en tests: una BC con un secreto plantado; ningún test E2E pasa si ese secreto aparece en un índice o en un payload a API externa.
