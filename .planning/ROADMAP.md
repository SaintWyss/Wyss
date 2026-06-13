# Wyss — Roadmap v0.1

**Estructura:** Horizontal Layers (capas técnicas completas, ensamblaje progresivo)
**Granularidad:** fine — 10 fases
**Orden:** derivado del build order de `research/ARCHITECTURE.md` — dependencias técnicas reales, no las 5 fases del prompt original (que se mapean: prompt F1 → fases 3-4; F2 → 5-6; F3 → 7-8; F4 → 9; F5 → 10)
**Regla:** cada fase entrega valor verificable antes de avanzar. Criterio transversal de `docs/16`: nada se acepta con acción sin auditar, acceso sin habilitación, vía para ejecutar D, o secreto enviado afuera.

---

## Fases

### Phase 1: Fundaciones
**Goal:** Núcleo hexagonal puro: dominio, ports, auditoría y política cognitiva — sin IO, completamente testeado.
**Requirements:** POL-01, POL-02, POL-03, POL-04, POL-05, AUD-01 (esquema)
**Success Criteria**:
1. Los 14 ports de `research/ARCHITECTURE.md` existen como Protocols en `core/ports/` y mypy strict pasa en `core/`
2. El CognitivePolicyEngine clasifica planes dorados en A/B/C/D correctamente — D por denylist determinística, sin LLM
3. Un plan compuesto de pasos menores que agregan a nivel D se clasifica D (test de bypass por composición)
4. AuditLogger escribe eventos a SQLite y todo componente posterior lo recibe inyectado (firma verificada por tests)
5. La config TOML se valida con Pydantic al boot — config inválida = fail-fast con error legible

**Plans:** 6/6 plans complete
- [x] 01-01-PLAN.md — toolchain uv + esqueleto multi-paquete
- [x] 01-02-PLAN.md — dominio frozen + 14 ports (interfaces primero)
- [x] 01-03-PLAN.md — SqliteAuditLogger append-only (AUD-01)
- [x] 01-04-PLAN.md — fix CR-01: rechazo D no salteable por valor + isinstance (POL-03)
- [x] 01-05-PLAN.md — CognitivePolicyEngine + denylist built-in + golden/composición (POL-03/04/05)
- [x] 01-06-PLAN.md — bootstrap config Pydantic→dominio, fail-fast, denylist aditiva (POL-04/05)

### Phase 2: Gateway de Modelos
**Goal:** Único punto de salida a IA externa, con minimización de contexto, gate de costo y tracing — antes de que exista cualquier consumidor.
**Requirements:** GATE-01, GATE-02, GATE-03, GATE-04, GATE-05
**Success Criteria**:
1. Dos proveedores configurables e intercambiables vía config sin tocar código (probado con FakeProvider en tests)
2. El Context Minimizer redacta secretos plantados antes de cada llamada — el fixture "secreto trampa" nunca aparece en un payload saliente
3. El Cost Tracker bloquea la llamada cuando el presupuesto se agota (gate, no reporte)
4. Cada llamada deja trace consultable: prompt, output, latencia, tokens, costo
5. EmbeddingProvider funciona con al menos un proveedor real y uno fake

### Phase 3: Pipeline de Ingesta
**Goal:** Escanear, extraer e indexar archivos en FTS5 de forma incremental, reanudable y con secretos excluidos.
**Requirements:** KNOW-01, KNOW-02, KNOW-03, KNOW-06, KNOW-07, KNOW-08, KNOW-09, KNOW-11
**Success Criteria**:
1. `wyss index <ruta>` escanea, extrae e indexa PDF/DOCX/TXT/MD/código/CSV/XLSX; imágenes y video como metadatos
2. Re-correr sobre 10 archivos modificados no re-procesa el resto (incremental por size+mtime→hash)
3. Matar el proceso a mitad de escaneo y relanzar continúa donde quedó (estado por archivo en SQLite)
4. El secreto plantado en la BC trampa no aparece en el índice (prueba dirigida)
5. `--estimate` proyecta chunks y costo antes de llamar a la API; la indexación muestra progreso con ETA
6. Registrar un extractor nuevo no modifica una línea del pipeline (test de extensibilidad)

**Plans:** 7/7 plans complete
- [x] 03-01-PLAN.md — fundación: deps + dominio de ingesta + errores + sección [ingest] + scaffolding de tests (Wave 0)
- [x] 03-02-PLAN.md — StateStore: index.db WAL fail-fast + incremental (KNOW-02) + reanudable (KNOW-03)
- [x] 03-03-PLAN.md — SecretFilter de 3 capas, puro e inyectado (KNOW-07)
- [x] 03-04-PLAN.md — Scanner + ExtractorRegistry (plugin pattern) + 6 extractores (KNOW-06)
- [x] 03-05-PLAN.md — TokenChunker + FTS5Index (external content) + ChromaVectorIndex por kb_id (KNOW-01/KNOW-11)
- [x] 03-06-PLAN.md — IngestPipeline: secret-gate + reanudabilidad + estimate/dry-run + extensibilidad (prueba dirigida, criterio 4/6)
- [x] 03-07-PLAN.md — CLI wyss index: composition root + flags + progreso Rich + exit codes (KNOW-08/09/11)

### Phase 4: Búsqueda Híbrida
**Goal:** Encontrar cualquier archivo en segundos — FTS5 + semántica fusionadas. El primer valor real para el owner.
**Requirements:** KNOW-04, KNOW-05, KNOW-10, AUD-03
**Success Criteria**:
1. `wyss search "<consulta>"` responde en < 5 segundos sobre el volumen indexado
2. Cada resultado trae ruta exacta, extracto, fuente y fecha
3. La búsqueda funciona sin vectores (FTS5 solo) y mejora con ellos (fusión RRF)
4. Toda consulta queda auditada
5. El eval set dorado (N consultas → archivo esperado) corre en CI y pasa

**Plans:** 3/3 plans complete
- [x] 04-01-PLAN.md — base pura: rrf_merge + Hit.date + frescura StateStore + corpus dorado N=20 + scaffolds de test (Wave 0)
- [x] 04-02-PLAN.md — HybridRetrieval: fusión RRF + degradación D-44 + auditoría + date(mtime) (KNOW-04/05)
- [x] 04-03-PLAN.md — CLI search/status: salida Rich/JSON (D-43) + banner degradado (D-44) + footer/status (D-47) + gate dorado hit@1 (AUD-03)

### Phase 5: Orquestador Daemon
**Goal:** Proceso persistente que recibe lenguaje natural, clasifica intención, genera planes y gestiona confirmaciones — política cognitiva operativa de punta a punta.
**Requirements:** ORCH-01, ORCH-02, ORCH-03, ORCH-04, ORCH-05, ORCH-06, ORCH-07, POL-06, AUD-02
**Success Criteria**:
1. `wyss start` levanta el daemon; sobrevive a socket huérfano; systemd lo reinicia ante fallo
2. `wyss ask` clasifica ≥ 9 categorías de intención; lo ambiguo pide aclaración en vez de asumir
3. Toda tarea modificadora muestra plan legible; B pide [s/N], C exige "CONFIRMAR", D se rechaza con explicación y queda auditado
4. Reiniciar el daemon no pierde confirmaciones ni propuestas pendientes (colas en SQLite)
5. El eval del clasificador de política corre en CI — un falso-A rompe el build
6. `wyss audit` permite al owner consultar el historial

### Phase 6: Capa de Ejecución
**Goal:** Acciones reales sobre el entorno (archivos, shell, git) con verificación posterior, undo y segunda muralla de riesgo.
**Requirements:** EXEC-01, EXEC-02, EXEC-03, EXEC-04
**Success Criteria**:
1. FileSystemAdapter ejecuta un plan real con confirmación B de punta a punta (Milestone B del research)
2. Toda acción modificadora se verifica después (conteos/hashes) y el resultado queda auditado
3. Borrar = papelera; el journal registra origen→destino con operación inversa aplicable
4. El adapter re-verifica el nivel de riesgo antes de ejecutar — un plan adulterado post-política se bloquea
5. ShellAdapter solo ejecuta comandos de la allowlist

### Phase 7: Modelo de Agentes
**Goal:** AgentBase + registro config-driven + permisos estructurales — la maquinaria para instanciar agentes sin código nuevo.
**Requirements:** AGENT-01, AGENT-02, AGENT-03, AGENT-04, AGENT-05, AGENT-06, AGENT-08, POL-07
**Success Criteria**:
1. Un agente nuevo se crea agregando una entrada en config — cero código nuevo (probado con agente de prueba)
2. Intento de acceso a BC sin permiso → bloqueado estructuralmente (scoped facade) + auditado
3. Revocar un permiso surte efecto en la siguiente query, sin reiniciar nada
4. Un agente no puede invocar a otro ni modificar su propia config/presupuesto (tests de ausencia)
5. El contenido recuperado se marca como dato no confiable y un documento con instrucciones inyectadas no altera el plan (test anti-injection)
6. La memoria del agente persiste preferencias y solo el owner/extracción supervisada la escribe

### Phase 8: Belgrano
**Goal:** Primer agente real operando en el dominio estudio del owner — validación end-to-end de toda la maquinaria.
**Requirements:** AGENT-07, AGENT-09
**Success Criteria**:
1. Belgrano existe solo como config (identidad, dominio estudio, BC habilitada, modelo, presupuesto)
2. Completa ≥ 3 tareas reales de su dominio de punta a punta ("organizá el material del parcial", "resumí los apuntes de X")
3. Reporta resultados al orquestador y todo queda auditado
4. Agotado su presupuesto, sus llamadas se bloquean (gate verificado)

### Phase 9: Multi-agente y Rutinas
**Goal:** Varios agentes conviviendo + rutinas programadas con bandeja de aprobaciones — operación desatendida segura.
**Requirements:** ROUT-01, ROUT-02, ROUT-03, ROUT-04, ROUT-05, ROUT-06, ROUT-07
**Success Criteria**:
1. Dos o más agentes operan en simultáneo sin interferirse
2. Una tarea multi-dominio se divide, delega y consolida correctamente
3. La rutina semanal (lunes 8:00) corre por scheduler; sus acciones B/C quedan como propuestas en la bandeja, nunca auto-ejecutadas, y el owner es notificado
4. Una rutina no se duplica ante reinicio del scheduler (idempotencia por ventana)
5. Una tarea multi-paso interrumpida en el paso N retoma desde N
6. Las 4 BC (Personal, RAGcorp, Beca #1, Beca #2) conectadas con habilitaciones selectivas

### Phase 10: Modo Equipo
**Goal:** Trabajadores humanos interactuando con agentes asignados, sin acceso al núcleo.
**Requirements:** TEAM-01, TEAM-02, TEAM-03, TEAM-04, TEAM-05
**Success Criteria**:
1. Un trabajador interactúa con su agente asignado por interfaz separada — sin ver núcleo ni auditoría completa
2. Solo accede a los agentes que el owner le asignó
3. Intento de exceder el rol escala al owner (probado explícitamente)
4. El agente extrae estado/intención de reportes del trabajador y actualiza el tablero
5. Todo input de trabajador se trata como contenido no confiable (anti-injection endurecido)

---

## Coverage

55/55 requirements v1 mapeados a exactamente una fase. Verificación:
- KNOW: 01-03, 06-09, 11 → P3 · 04, 05, 10 → P4
- ORCH: 01-07 → P5
- POL: 01-05 → P1 · 06 → P5 · 07 → P7
- GATE: 01-05 → P2
- AGENT: 01-06, 08 → P7 · 07, 09 → P8
- EXEC: 01-04 → P6
- ROUT: 01-07 → P9
- TEAM: 01-05 → P10
- AUD: 01 → P1 · 02 → P5 · 03 → P4

## Milestones del research

- **Milestone A** (fin P4): búsqueda instantánea standalone — el valor que el owner usa todos los días
- **Milestone B** (fin P6): primer plan real ejecutado con confirmación — la política cognitiva probada en el mundo real
