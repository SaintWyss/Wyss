# Wyss — Prompt de Implementación (spec canónica)

**Versión:** 1.0
**Estado:** Aprobado por el owner
**Rol:** Documento de decisiones de implementación que complementa los docs fundacionales 00-17. Ante conflicto con docs 00-17: seguridad cognitiva primero, luego funcionalidad.

---

## CONTEXTO

Ingeniero de software senior implementando **Wyss** desde cero.
Repo en `~/Data/10_Workspace/projects/wyss`. Docs de diseño en `docs/`.
Leer todos los docs antes de escribir una línea.

**No es prototipo. No es MVP. Cada fase se implementa completa.**

---

## DECISIONES TÉCNICAS FIJAS

| Decisión | Valor |
|---|---|
| Lenguaje | Python 3.12+ |
| Gestor de dependencias | `uv` + `pyproject.toml` |
| Vector store | ChromaDB embebido (sin servidor dedicado) |
| Full-text search | SQLite FTS5 |
| Embeddings | API externa; proveedor configurable en `.env` (OpenAI, Voyage, Google — intercambiable sin tocar código) |
| Formato de config | TOML (`config.toml`) |
| Resúmenes de archivos | Doble estrategia: extracto determinístico (primeros N tokens) + resumen IA por lotes cuando hay presupuesto |
| IPC daemon | Unix socket + JSON-RPC (simple, sin dependencia HTTP) |
| Audit store | SQLite separado de datos de usuario |

---

## PRINCIPIOS DE ARQUITECTURA

**El sistema debe poder crecer sin romper lo que ya funciona.**
Esto no es aspiracional — es un requisito de implementación.

### Arquitectura Hexagonal (Ports & Adapters)

El núcleo (orquestador, política cognitiva, agentes) no depende de infraestructura.
SQLite, ChromaDB, APIs externas y filesystem son adaptadores intercambiables.
El núcleo los conoce solo a través de protocolos/ABCs abstractos definidos en `src/core/ports/`.

```
core/ports/          ← interfaces que el núcleo usa (define el contrato)
core/                ← lógica de negocio pura (sin imports de infra)
adapters/            ← implementaciones concretas de cada puerto
```

### SOLID aplicado

- **S** — cada clase tiene una sola razón para cambiar. `AuditLogger` no parsea archivos. `IngestionPipeline` no elige proveedores.
- **O** — abierto para extensión, cerrado para modificación. Agregar soporte `.odt` = nueva clase `OdtExtractor`; nunca tocar `IngestionPipeline`.
- **L** — subtipos respetan el contrato. Todo `AgentBase` puede ser usado donde se espera un agente.
- **I** — interfaces pequeñas. `Extractor` solo expone `can_handle(path)` + `extract(path)`. Los agentes no implementan métodos de infraestructura.
- **D** — depender de abstracciones. `IngestionPipeline` recibe `ExtractorRegistry` inyectado, no instancias concretas.

### Puntos de extensión explícitos (Plugin Pattern)

| Punto de extensión | Mecanismo |
|---|---|
| Tipo de archivo nuevo | Registrar clase `Extractor` — cero cambios en pipeline |
| Proveedor de embeddings | Nuevo adapter + entrada en `config.toml` |
| Proveedor de modelo | Nuevo adapter + entrada en `config.toml` |
| Agente nuevo | Nueva entrada en `agents.toml` — sin código nuevo |
| Adapter de ejecución | Nueva clase que implementa `ExecutionPort` |

### Dependency Injection

Las dependencias se inyectan, no se construyen internamente.
Constructores explícitos o contenedor liviano (no framework DI pesado).

### Interfaces primero

Antes de implementar un módulo: definir el protocolo/ABC que otros módulos usarán.
Los módulos vecinos importan de `core/ports/`, nunca de la implementación concreta.

---

## FASES DE IMPLEMENTACIÓN (vista del owner)

> Nota: el roadmap operativo (`.planning/ROADMAP.md`) expande estas 5 fases en 10 por build order técnico. Mapeo: F1 → fases 3-4 · F2 → 5-6 · F3 → 7-8 · F4 → 9 · F5 → 10, con Fundaciones y Gateway como fases previas.

### Fase 1 — El Índice

**Objetivo:** encontrar cualquier archivo en segundos con lenguaje natural.

- `wyss index <ruta>` — escanea, extrae, indexa. Incremental: hash + fecha, solo procesa cambios.
- `wyss search "<consulta>"` — recuperación híbrida (FTS5 + semántica), < 5 segundos sobre cualquier volumen.
- Resultado incluye: ruta exacta, extracto relevante, fuente, fecha.
- Secretos (`.env`, `*.key`, tokens, contraseñas) detectados y excluidos antes de indexar.
- Toda consulta auditada en SQLite.
- Tipos soportados: `.pdf`, `.docx`, `.txt`, `.md`, `.py`, `.js`, `.ts`, `.csv`, `.xlsx`, imágenes (solo metadatos en v0.1), video/audio (solo metadatos en v0.1).
- `Watchdog` opcional para re-indexación automática.

### Fase 2 — El Orquestador

**Objetivo:** daemon persistente que recibe instrucciones en lenguaje natural y aplica política cognitiva.

- `wyss start` — levanta daemon (Unix socket + JSON-RPC).
- `wyss ask "<instrucción>"` — envía instrucción al daemon activo.
- **Intent Router** — clasifica en: `knowledge_query`, `file_operation`, `repo_task`, `system_action`, `agent_task`, `routine_trigger`, `admin_task`, `dangerous_operation`, `ambiguous_request`.
- **Task Planner** — convierte intención en plan explícito: pasos, nivel de riesgo, justificación.
- **Cognitive Policy Engine** (componente más crítico):
  - A: ejecuta directo.
  - B: muestra plan, pide `[s/N]`.
  - C: muestra plan con advertencia, pide escribir `"CONFIRMAR"`.
  - D: **rechaza siempre**. Ningún path de código lo ejecuta. Rechazo auditado.
- **Model Gateway** — único punto de salida a IA externa. ≥2 proveedores configurables. Registra tokens y costo. Aplica Context Minimizer antes de cada llamada.
- **Confirmation Manager** — gestiona flujo de confirmación y registra respuesta.
- **Audit Logger** — registra actor, instrucción, plan, decisión de política, confirmación, acciones, resultado, costo en SQLite.

### Fase 3 — El Primer Agente

**Objetivo:** primer agente especializado (Belgrano, dominio: estudio) instanciado desde modelo base replicable por config.

- **AgentBase** — protocolo: recibir tarea → consultar BC habilitada → generar plan → ejecutar → reportar.
- **AgentRegistry** — catálogo config-driven. Agente nuevo = entrada en `agents.toml`, sin código.
- **AgentRuntime** — ejecuta instancias según registro.
- **PermissionManager** — habilitaciones agente ↔ BC. Sin permiso vigente: bloqueado + auditado. Revocación inmediata.
- **Belgrano** — dominio estudio. Tareas ejemplo: "organizá el material del parcial", "resumí los apuntes de X". Respeta presupuesto de modelos configurado.
- Memoria operativa: `MEMORY.md` por agente — persiste preferencias del owner en su dominio.

### Fase 4 — Multi-agente y Rutinas

- Múltiples agentes conviviendo sin interferencia ni comunicación horizontal directa.
- **Routine Scheduler** — rutinas en config (cron o evento). Obligatorio: resumen ejecutivo semanal lunes 8:00.
- División multi-dominio: orquestador divide → delega → consolida.
- Rutinas nunca auto-ejecutan acciones B/C — quedan como propuestas pendientes.
- 4 KBs del owner conectadas: Personal, RAGcorp, Beca Ciber #1, Beca Ciber #2. Habilitaciones selectivas por agente.

### Fase 5 — Modo Equipo

- Interfaz separada para trabajadores (sin visibilidad del núcleo ni auditoría completa).
- Trabajador solo accede a agentes que el owner le asignó explícitamente.
- Exceder el rol escala al owner — probado explícitamente.
- Agente asignado puede contactar al trabajador por canal configurado, extraer estado e intención, actualizar tablero de tareas.

---

## ESTRUCTURA DEL REPOSITORIO

```
wyss/
├── docs/                  ← documentos fundacionales
├── src/
│   ├── core/
│   │   ├── ports/         ← interfaces/ABCs que el núcleo expone y consume
│   │   └── ...            ← lógica de negocio pura
│   ├── orchestrator/      ← IntentRouter, TaskPlanner, CognitivePolicyEngine, ConfirmationManager, RoutineScheduler
│   ├── agents/            ← AgentBase, AgentRegistry, AgentRuntime, PermissionManager
│   ├── knowledge/         ← IngestionPipeline, ExtractorRegistry, SemanticIndex, RetrievalEngine
│   ├── gateway/           ← ModelRouter, ContextMinimizer, CostTracker
│   ├── execution/         ← Adapters (FileSystem, Shell, Git…)
│   └── audit/             ← AuditLogger
├── tests/
├── config/
│   ├── config.example.toml
│   └── .env.example
├── scripts/
└── data/                  ← runtime (DB, índices) — gitignoreado
```

Si se agregan carpetas, documentarlas en el README.

---

## REGLAS INVIOLABLES

1. **Auditoría obligatoria** — toda acción relevante se registra. Si no está auditado, no está terminado.
2. **Nivel D es absoluto** — ningún path de código ejecuta una acción D. El rechazo se registra siempre.
3. **Permisos antes de buscar** — el RetrievalEngine aplica el filtro de permisos *antes* de consultar la KB, no después.
4. **Contexto mínimo** — el Context Minimizer filtra secretos, rutas innecesarias y contexto no solicitado antes de toda llamada externa.
5. **Sin comunicación horizontal entre agentes** — los agentes no se llaman entre sí. Solo el orquestador divide y consolida.
6. **Sin auto-modificación** — ningún agente puede alterar su propia config, permisos o presupuesto.
7. **Plan antes de acción modificadora** — ninguna acción que modifique estado se ejecuta sin Plan explícito previo.
8. **Secretos fuera del índice** — el pipeline detecta y excluye patrones de secretos antes de indexar.
9. **Extensibilidad sin ruptura** — agregar un extractor, proveedor o agente nunca modifica código existente. Si hay que modificar código existente para agregar una feature, es un defecto de diseño.

---

## TESTS

Criterio mínimo por módulo:

- Flujo feliz funciona como se espera.
- Flujo de error no deja estado inconsistente.
- Tests de seguridad explícitos:
  - Acceso sin habilitación → bloqueado + auditado.
  - Acción nivel D → rechazada, nunca ejecutada.
  - Secreto en texto de entrada → no aparece en índice.
  - Extractor nuevo agregado → pipeline existente no se modifica.

`pytest`. El foco son los casos de borde críticos, no el coverage.

---

## REGLAS DE PROCESO

1. Leer **todos** los docs en `docs/` antes de escribir código.
2. Verificar criterios de `docs/16-criterios-de-aceptacion.md` al cerrar cada fase.
3. Commit al final de cada fase con mensaje descriptivo.
4. Contradicciones entre docs: **seguridad cognitiva primero, luego funcionalidad**.

---

## CONTEXTO DEL OWNER

- **Santiago Wyss** — el sistema lleva su apellido.
- Argentina. PC como entorno principal de trabajo.
- ~2 TB de archivos personales que quiere encontrar en segundos.
- Empresa: RAGcorp. Dos proyectos de beca en ciberseguridad.
- Primer agente operativo: **Belgrano**, dominio estudio.
- Filosofía: **humano primero, IA cuando corresponde**. Wyss no decide por Santiago — ejecuta lo que Santiago ya decidió, de forma precisa, trazable y auditable.
