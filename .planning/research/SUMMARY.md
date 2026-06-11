# Research Summary — Wyss

**Sintetizado:** 2026-06-10
**Fuentes:** STACK.md · FEATURES.md · ARCHITECTURE.md · PITFALLS.md
**Nota:** ARCHITECTURE y FEATURES investigados por agentes (Fable, fuentes web verificadas). STACK y PITFALLS escritos inline tras corte de límite de sesión — versiones exactas a confirmar con `uv add` en Fase 1.

---

## Stack (decisiones validadas + cambios)

**Validado:** Python 3.12+ · uv · ChromaDB embebido (colección por BC) · SQLite FTS5 · TOML + Pydantic v2 · Unix socket + JSON-RPC sobre asyncio · Typer + Rich · pytest + ruff + mypy strict en core.

**Cambios sobre el prompt original:**
- `pymupdf` como extractor PDF primario (no PyPDF2 — deprecado; pdfplumber solo fallback para tablas)
- Agregar: `python-magic` (tipo real de archivo), `detect-secrets` (regla #8), `tenacity` (retries), `structlog`
- LiteLLM como adapter inicial del gateway (un adapter → muchos proveedores) — opcional, decidir en Fase 2
- systemd user unit para supervisión del daemon (patrón ya usado por el owner)
- NO usar: LangChain/LlamaIndex, Celery, FastAPI para IPC, SQLAlchemy ORM

## Arquitectura (cómo construir)

- **Hexagonal con matiz:** el Núcleo se divide en domain core (puro, sin IO) + application services. Ports como `Protocol` en `core/ports/`; ABCs solo donde hay comportamiento compartido forzado (AgentBase con template method `execute()` no-overridable).
- **Dominio:** frozen dataclasses; Pydantic solo en el boundary (config, JSON-RPC).
- **DI:** composition root manual en `bootstrap/` — sin framework DI.
- **Permisos estructurales:** scoped facades — el agente recibe un handle que *solo puede* ver sus BC habilitadas (capability-based, no checks).
- **Policy engine:** Enums + exhaustive matching; clasificación D determinística (denylist), el LLM solo puede subir riesgo, nunca bajarlo.
- **14 ports clave** definidos en ARCHITECTURE.md §Interface Contracts — escribirlos ANTES de implementar.
- **Build order (12 pasos):** domain → ports → audit → policy → config/bootstrap → gateway → knowledge → orchestration → agents → execution adapters → CLI → scheduler. AuditLogger en paso 2 — todo lo posterior lo recibe inyectado.

## Gaps detectados en los RF (features ausentes — table stakes)

1. **Memoria conversacional persistente del agente** — el índice indexa archivos, no interacciones. Guardar desde el día 1 aunque la extracción inteligente llegue después. (Fase 3)
2. **Estado durable de tareas + resume** — tarea de 20 pasos que muere en el 14 retoma desde el 14. (Fase 4, esquema desde Fase 2)
3. **Política de errores** (retry/escalar/abortar) — sin esto las rutinas fallan en silencio. (Fase 2)
4. **Bandeja de aprobaciones asíncronas + notificación** — las propuestas B/C de rutinas necesitan dónde vivir. (Fase 4)
5. **Progreso visible en tareas largas** — indexar 2TB sin barra = parece colgado. (Fase 1)
6. **Frescura del índice** — metadato "indexado al X". (Fase 1)
7. **Undo/journal de operaciones de archivos** — papelera + operación inversa registrada. (Fase 2, junto con la primera acción modificadora)
8. **Evals desde el día 1** — set dorado de consultas (Fase 1) + evals del clasificador de política (Fase 2: un falso-A es el peor bug posible).
9. **Tracing LLM ≠ auditoría** — prompt/contexto/output/latencia por llamada, consultable. Barato ahora, carísimo retrofittear. (Fase 1-2)
10. **Defensa prompt injection vía contenido indexado** — contenido recuperado = dato no confiable, jamás instrucción; niveles de confianza por BC; contenido recuperado nunca eleva el nivel de un plan aprobado. (Fase 3, obligatorio antes de que agentes consuman BC externas)

## Diferenciadores a proteger (no diluir)

- Política A/B/C/D con **D inviolable** (nadie más lo tiene; respuesta directa al desastre OpenClaw)
- Permission Manager con vigencia y revocación inmediata en retrieval
- Context Minimizer + redacción de secretos pre-IA-externa
- Cost Tracker como **gate** (bloquea), no solo reporte
- Hub-and-spoke estricto — no ceder a la moda A2A/swarms
- Verificación posterior de acciones (RF-017)

## Pitfalls críticos (top 8)

1. Indexación sin checkpoint → tabla `files` con estado por archivo, reanudable desde commit 1
2. Costo de embeddings descontrolado → `--estimate` antes de embedder; FTS5 primero (la búsqueda funciona sin vectores)
3. Clasificación D vía LLM → determinística por denylist; doble muralla en el execution adapter
4. Bypass por composición (acción D como 1000 pasos A) → la política evalúa el plan completo + agregados
5. Post-filter de permisos → filtro estructural ANTES del retrieval (colecciones separadas)
6. Daemon con estado en RAM → colas de pendientes en SQLite; daemon stateless recuperable
7. Auditoría como afterthought → AuditLogger es la pieza #2 del build order
8. Sobre-ingeniería del hexágono → ports solo donde hay ≥2 implementaciones o un test que lo exige

## Quick wins

`wyss index --dry-run/--estimate` · denylist de rutas default (.git, node_modules, .ssh, .env*) · WAL mode en todos los SQLite · fixture "BC trampa" con secreto plantado (ningún E2E pasa si aparece en índice o payload externo) · systemd `Restart=on-failure`.

## Implicancias para el roadmap

- Fase 1 entrega el valor real y de-riskea el subsistema más difícil — milestone A: búsqueda instantánea standalone
- Audit + domain + ports son pre-fase-1 (build order 0-2) — considerar fase 0.5 de fundaciones o integrarlo al arranque de Fase 1
- Los 10 gaps se insertan en las fases indicadas — no son fases nuevas
- Fases que necesitarán más research al planificar: 1 (chunking/embeddings a escala), 3 (memoria + anti-injection), 5 (canal de mensajería)
