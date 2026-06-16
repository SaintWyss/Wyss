# Wyss — Requirements

**Versión:** v1 (v0.1 del producto según docs/01)
**Fuente:** 18 docs fundacionales (`docs/`) + research (`research/SUMMARY.md` — 10 gaps incorporados)
**Trazabilidad RF:** cada requirement referencia los RF de `docs/04-requerimientos-funcionales.md` que cubre.

---

## v1 Requirements

### Knowledge (El Índice)

- [ ] **KNOW-01**: El owner puede indexar una ruta con `wyss index <ruta>` — escaneo, extracción y indexación híbrida (metadatos + FTS5 + vectores) *(RF-012, RF-013)*
- [ ] **KNOW-02**: La re-indexación es incremental — size+mtime como filtro rápido, hash solo si cambió; 10 archivos modificados no re-procesan 2 TB *(RF-013)*
- [ ] **KNOW-03**: El escaneo es reanudable — estado por archivo en SQLite (pending/extracted/embedded/failed); un crash no pierde progreso
- [x] **KNOW-04**: El owner puede buscar con `wyss search "<consulta>"` — recuperación híbrida con fusión RRF, < 5 segundos sobre cualquier volumen *(RF-014)*
- [x] **KNOW-05**: Cada resultado incluye ruta exacta, extracto relevante, fuente y fecha *(RF-014)*
- [ ] **KNOW-06**: Extractores para PDF, DOCX, TXT, MD, PY/JS/TS, CSV, XLSX; imágenes y video/audio solo metadatos — registrables sin modificar el pipeline *(RF-012)*
- [ ] **KNOW-07**: Los secretos (.env, *.key, tokens, contraseñas, alta entropía) se detectan y excluyen ANTES de indexar — verificado con prueba dirigida *(RF-021, regla #8)*
- [ ] **KNOW-08**: `wyss index --estimate` proyecta chunks y costo de embeddings antes de llamar a la API; `--dry-run` lista qué se indexaría
- [ ] **KNOW-09**: La indexación muestra progreso visible (archivos procesados / total, ETA) *(gap #5)*
- [x] **KNOW-10**: El índice expone su frescura — "indexado al [fecha]" consultable *(gap #6)*
- [ ] **KNOW-11**: Las BC se organizan por contexto (colección separada por BC) — base estructural del aislamiento *(RF-015)*

### Orchestrator (El Núcleo)

- [ ] **ORCH-01**: `wyss start` levanta el daemon (Unix socket + JSON-RPC, asyncio); corre persistente sin intervención *(RF-001)*
- [ ] **ORCH-02**: `wyss ask "<instrucción>"` envía lenguaje natural al daemon y recibe respuesta *(RF-001)*
- [ ] **ORCH-03**: El Intent Router clasifica en ≥ 9 categorías (knowledge_query, file_operation, repo_task, system_action, agent_task, routine_trigger, admin_task, dangerous_operation, ambiguous_request) *(RF-002)*
- [ ] **ORCH-04**: Ante instrucción ambigua el sistema pide aclaración en vez de asumir *(RF-003)*
- [ ] **ORCH-05**: Toda tarea modificadora genera un Plan explícito y legible (pasos, riesgo, justificación) antes de ejecutarse *(RF-004, regla #7)*
- [ ] **ORCH-06**: Las colas de pendientes (confirmaciones, propuestas) viven en SQLite — un restart del daemon no pierde nada
- [ ] **ORCH-07**: Política de errores explícita por paso de plan: retry con backoff / escalar al owner / abortar — las fallas nunca son silenciosas *(gap #3)*

### Cognitive Policy (Seguridad cognitiva)

- [x] **POL-01**: Todo plan pasa por la política cognitiva antes de ejecutarse *(RF-018)*
- [x] **POL-02**: Nivel A ejecuta directo; B pide confirmación simple [s/N]; C pide confirmación fuerte (escribir "CONFIRMAR") *(RF-019)*
- [x] **POL-03**: Nivel D se rechaza con explicación, queda auditado, y ningún path de código lo ejecuta — aunque el owner insista *(RF-020, regla #2)*
- [x] **POL-04**: La clasificación D es determinística (denylist de operaciones); el LLM puede subir el riesgo estimado, nunca bajarlo
- [x] **POL-05**: La política evalúa el plan completo + agregados (cantidad de archivos, directorios tocados) — sin bypass por composición de pasos menores
- [ ] **POL-06**: Eval set del clasificador de política: planes dorados con nivel esperado; un falso-A (ejecutar lo que debía confirmar) se detecta en CI *(gap #8)*
- [x] **POL-07**: El contenido recuperado de BC se trata como dato no confiable — jamás como instrucción; nunca eleva el nivel de un plan aprobado *(gap #10)*

### Gateway (Modelos externos)

- [x] **GATE-01**: Único punto de salida a IA externa; ≥ 2 proveedores configurables, intercambiables vía config sin tocar código *(RF-007)*
- [x] **GATE-02**: Selección de modelo por costo/complejidad/riesgo (lógica local → económico → fuerte) *(RF-007)*
- [x] **GATE-03**: El Context Minimizer filtra secretos, rutas innecesarias y contexto no solicitado antes de TODA llamada externa *(RF-021, regla #4)*
- [x] **GATE-04**: Cost Tracker registra tokens y costo por llamada y actúa como gate — presupuesto con hard-stop, no solo reporte
- [x] **GATE-05**: Tracing por llamada LLM: prompt, contexto, output, latencia, costo — consultable, separado de la auditoría *(gap #9)*

### Agents

- [x] **AGENT-01**: AgentBase define el contrato: recibir tarea → consultar BC habilitada → generar plan → ejecutar → reportar *(RF-008, RF-010)*
- [x] **AGENT-02**: Crear un agente nuevo = entrada en config (identidad, dominio, herramientas, BC, modelo, presupuesto) — sin código nuevo *(RF-008)*
- [x] **AGENT-03**: Un agente sin permiso vigente no puede consultar una BC — filtro estructural ANTES del retrieval; intento sin permiso → bloqueado + auditado *(RF-009, RF-015, regla #3)*
- [x] **AGENT-04**: La revocación de permisos tiene efecto inmediato — verificación por query, sin cache *(RF-015)*
- [x] **AGENT-05**: Los agentes no se comunican entre sí — solo el orquestador delega y consolida *(RF-011, regla #5)*
- [x] **AGENT-06**: Ningún agente puede alterar su propia config, permisos o presupuesto *(regla #6)*
- [x] **AGENT-07**: Cada agente respeta su presupuesto de modelos configurado
- [x] **AGENT-08**: Memoria operativa por agente (patrón MEMORY.md): persiste preferencias del owner en su dominio; solo el owner o extracción supervisada escribe en ella — contenido de BC jamás escribe memoria directamente *(gap #1)*
- [x] **AGENT-09**: Belgrano (dominio estudio) completa ≥ 3 tareas reales de punta a punta, reportando al orquestador

### Execution

- [x] **EXEC-01**: Adaptadores de ejecución desacoplados (FileSystem, Shell, Git) con allowlist de comandos *(RF-016)*
- [x] **EXEC-02**: Toda acción modificadora se verifica después de ejecutada (conteos, hashes, estados) *(RF-017)*
- [x] **EXEC-03**: Operaciones de archivos con undo: papelera en vez de borrado, journal origen→destino con operación inversa *(gap #7)*
- [x] **EXEC-04**: El adapter de ejecución re-verifica el nivel de riesgo antes de ejecutar (segunda muralla tras la política)

### Routines (Multi-agente)

- [ ] **ROUT-01**: Routine Scheduler con rutinas definidas en config (cron o evento); ejemplo obligatorio: resumen ejecutivo semanal lunes 8:00 *(RF-006)*
- [ ] **ROUT-02**: Las acciones B/C generadas por rutinas nunca se auto-ejecutan — quedan como propuestas pendientes
- [ ] **ROUT-03**: Bandeja de aprobaciones: las propuestas pendientes viven en SQLite y el owner es notificado *(gap #4)*
- [ ] **ROUT-04**: Ejecución única por (rutina, ventana) — idempotencia ante reinicios del scheduler
- [ ] **ROUT-05**: Estado durable de tareas multi-paso: una tarea que muere en el paso N retoma desde N *(gap #2)*
- [ ] **ROUT-06**: Tareas multi-dominio: el orquestador divide, delega a cada agente y consolida resultados *(RF-005)*
- [ ] **ROUT-07**: Las 4 BC del owner (Personal, RAGcorp, Beca Ciber #1, Beca Ciber #2) conectadas con habilitaciones selectivas por agente

### Team Mode

- [ ] **TEAM-01**: Interfaz separada para trabajadores — sin acceso al núcleo ni a la auditoría completa
- [ ] **TEAM-02**: Un trabajador solo interactúa con los agentes que el owner le asignó
- [ ] **TEAM-03**: Intento de exceder el rol → escala al owner (probado explícitamente)
- [ ] **TEAM-04**: El agente asignado contacta al trabajador por canal configurado, extrae estado e intención, actualiza tablero de tareas
- [ ] **TEAM-05**: Input de trabajadores = contenido no confiable siempre — anti-injection endurecido

### Audit (transversal)

- [x] **AUD-01**: Toda acción relevante registra: actor, instrucción, plan, decisión de política, confirmación, acciones, resultado, costo — en SQLite *(RF-022, regla #1)*
- [ ] **AUD-02**: El owner puede consultar el historial de acciones *(RF-023)*
- [x] **AUD-03**: Eval set de conocimiento: N consultas doradas con archivo esperado — regresión detectable *(gap #8)*

---

## v2 Requirements (deferred)

- Replicación de instancia para clientes (RF-024) — Fase 6 del roadmap de producto
- Interfaz móvil / voz
- Watcher de filesystem para re-indexación automática (v0.1: re-scan manual o programado)
- Extracción inteligente automática de memoria (v0.1: almacenamiento estructurado, extracción supervisada)
- Sandboxing por contenedores (v0.1: allowlist + paths restringidos)
- GUI / no-code builder

## Out of Scope

- Multiusuario / multiempresa — v1.0 del producto, no v0.1
- Modelos locales pesados — API-first por decisión de diseño
- Marketplace de agentes — futuro
- Domótica — futuro
- Comunicación agente-a-agente (A2A/swarms) — anti-feature deliberada: rompe auditabilidad
- Agentes auto-mejorables que escriben sus propias skills — anti-feature: vector de persistencia de ataques
- Fine-tuning de modelos propios — el model routing da el 90% del beneficio

## Traceability

| Categoría | Requirements | Fase |
|---|---|---|
| POL (núcleo política) | POL-01..05 | Phase 1 — Fundaciones |
| AUD (esquema) | AUD-01 | Phase 1 — Fundaciones |
| GATE | GATE-01..05 | Phase 2 — Gateway |
| KNOW (ingesta) | KNOW-01..03, 06..09, 11 | Phase 3 — Pipeline de Ingesta |
| KNOW (búsqueda) | KNOW-04, 05, 10 · AUD-03 | Phase 4 — Búsqueda Híbrida |
| ORCH | ORCH-01..07 · POL-06 · AUD-02 | Phase 5 — Orquestador Daemon |
| EXEC | EXEC-01..04 | Phase 6 — Capa de Ejecución |
| AGENT (modelo) | AGENT-01..06, 08 · POL-07 | Phase 7 — Modelo de Agentes |
| AGENT (Belgrano) | AGENT-07, 09 | Phase 8 — Belgrano |
| ROUT | ROUT-01..07 | Phase 9 — Multi-agente y Rutinas |
| TEAM | TEAM-01..05 | Phase 10 — Modo Equipo |

55/55 mapeados — cobertura completa.
