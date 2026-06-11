# Features Research

**Proyecto:** Wyss — asistente operativo personal multi-agente
**Dimensión:** Features (comparativa contra el ecosistema 2025-2026)
**Investigado:** 2026-06-10
**Sistemas analizados:** LangGraph, CrewAI, AutoGen (en mantenimiento → Microsoft Agent Framework), AutoGPT (legado), Khoj, OpenClaw/Clawdbot, mem0, Google ADK
**Confianza general:** MEDIUM-HIGH (verificado contra docs oficiales y múltiples fuentes; marcas LOW donde aplica)

---

## Table Stakes (must have or the system is broken)

Features que todo sistema comparable tiene y cuya ausencia hace que el sistema se sienta roto. Contrastadas contra los RF actuales (docs/04).

| Feature | Estado en Wyss | Complejidad | Evidencia / Notas |
|---------|---------------|-------------|-------------------|
| Búsqueda híbrida sobre archivos propios | ✅ RF-012/013/014 | Alta | Khoj lo valida como producto entero (34k stars). Wyss ya lo tiene como núcleo. |
| Ingesta incremental (nunca re-procesar todo) | ✅ Flujo 4 | Media | Crítico a escala TB. Ya es regla de diseño. |
| Human-in-the-loop con niveles | ✅ RF-018/019/020 | Media | LangGraph lo trae como primitiva (`interrupt`). Wyss lo supera con 4 niveles. |
| Audit trail | ✅ RF-022/023 | Media | Estándar en todo framework serio. |
| Scheduler de rutinas | ✅ RF-006 | Media | OpenClaw "proactive automation"; estándar. |
| Routing de modelos por costo/riesgo | ✅ RF-007 | Media | Diferenciador parcial: pocos lo hacen con gate de presupuesto. |
| **Memoria conversacional persistente (episódica + semántica de preferencias)** | ❌ **AUSENTE en RF** | Media | El gap más grande. Khoj, OpenClaw, mem0: todos lo tienen. Sin esto el owner repite contexto en cada sesión ("ya te dije que los informes van en X carpeta"). El índice de conocimiento NO es memoria del agente: indexa archivos, no interacciones ni preferencias. CoALA distingue working / episódica / semántica / procedural — Wyss solo cubre semántica-de-archivos. Confianza: HIGH. |
| **Estado durable de tareas + resume** | ❌ AUSENTE | Media-Alta | LangGraph: checkpointing es SU feature insignia de producción; Google ADK lo promociona como "pause, resume, never lose context". Si una tarea de 20 pasos muere en el paso 14 (crash, corte, rate limit), debe retomar desde 14, no desde 0. Hoy Wyss solo persiste "propuestas pendientes" de rutinas. Confianza: HIGH. |
| **Manejo de errores con política (retry / escalar / abortar)** | ❌ AUSENTE | Media | RF-010 dice "reportar errores" pero no qué hacer con ellos. Todo framework maduro define: reintento con backoff, escalado a humano, branch de error. Sin esto, las rutinas desatendidas (Flujo 3) fallan en silencio. Confianza: HIGH. |
| **Bandeja de aprobaciones asíncronas + notificación** | ❌ AUSENTE | Media | Consecuencia directa de B/C + rutinas: si el lunes 8:00 una rutina genera 3 propuestas nivel B, ¿dónde viven? ¿cómo se entera el owner? Se necesita una cola de pendientes con canal de notificación. Sin esto, el flujo 3 está incompleto. Confianza: HIGH (se deriva de los propios flujos). |
| **Feedback de progreso en tareas largas** | ❌ AUSENTE | Baja-Media | Streaming/progress es primitiva en LangGraph y expectativa de UX universal. Indexar 2TB sin barra de progreso = parece colgado. Confianza: MEDIUM. |
| **Frescura del índice (watcher / detección de stale)** | ⚠️ Parcial | Media | La ingesta es incremental pero disparada por el owner (UC-008). Falta: watcher de filesystem o re-scan programado + indicador "índice actualizado al [fecha]". Una respuesta basada en índice viejo es peor que no responder. Confianza: MEDIUM. |
| Sandboxing real de ejecución | ⚠️ Parcial | Alta | RF-016 dice "comandos permitidos" (allowlist) pero no aísla. Mínimo viable: allowlist + paths restringidos por agente; ideal: contenedor. El caso OpenClaw demuestra el blast radius de no hacerlo. Confianza: HIGH. |

---

## Differentiators (ventajas específicas de Wyss a proteger)

Features que el ecosistema NO tiene bien resueltas y que constituyen la identidad del producto. **No diluir ni recortar en MVP.**

| Diferenciador | Por qué es raro en el ecosistema | Riesgo si se diluye |
|---------------|----------------------------------|---------------------|
| **Política cognitiva graduada A/B/C/D con rechazo absoluto (D)** | LangGraph/CrewAI tienen HITL binario (interrumpir o no). Nadie tiene un nivel D que rechaza *aunque el owner insista*, con explicación y alternativa. Es la respuesta directa al desastre de seguridad de OpenClaw. | Si D se vuelve "configurable off", se pierde la garantía. Mantener D inviolable. |
| **Permission Manager agente↔BC con alcance y vigencia** | Los frameworks dan a los agentes acceso global a tools/datos. Permisos con expiración y revocación de efecto inmediato en retrieval no existe en ninguno de los comparados. Es lo que habilita team mode y replicación para clientes. | Es el feature que convierte a Wyss de "asistente personal" en "producto vendible". |
| **Context Minimizer + redacción de secretos antes de toda IA externa** | OpenClaw filtró API keys en texto plano; ningún framework intercepta y minimiza contexto saliente por defecto. Cadena obligatoria del Flujo 7 = privacy-first real. | Cualquier bypass "por performance" rompe la promesa central. |
| **Cost Tracker con gate de presupuesto (no solo tracking)** | LangSmith/observabilidad *miden* costo; casi nadie *bloquea* por presupuesto por agente. AutoGPT murió en parte por loops que quemaban dinero. | Mantenerlo como gate previo a la llamada, no como reporte posterior. |
| **Prohibición de dirección horizontal (hub-and-spoke estricto)** | La tendencia 2025-2026 es lo contrario (A2A, swarms). La evidencia de producción favorece a Wyss: las conversaciones multi-agente libres son la principal fuente de comportamiento emergente no auditable. | No ceder a la moda A2A. El orquestador como único punto de delegación es lo que hace el audit trail completo. |
| **Verificación posterior de toda acción modificadora (RF-017)** | Conteos/hashes/estados post-ejecución prácticamente no existe en frameworks generales ("harness failures": el agente cree que hizo algo que no hizo). | Es lo que separa "parece que funcionó" de "funcionó". |
| **Agentes config-driven sin código nuevo (RF-008/024)** | CrewAI se acerca (roles en YAML) pero sin permisos ni política integrados. Config + permisos + presupuesto por agente = replicación de instancia trivial (UC-010). | — |
| **Local-first sobre 2TB con FTS5 + semántica** | Khoj es lo más cercano pero sin capa agentic/operativa encima. La combinación búsqueda-personal-masiva + agentes-con-permisos no existe como producto integrado. | — |

---

## Common Omissions (lo que los builders de sistemas similares lamentan no haber construido temprano)

Ordenadas por frecuencia/severidad en post-mortems y guías de ingeniería. Cada una con su implicancia para Wyss.

### 1. Evals desde el día 1 (el arrepentimiento #1)
**Quién lo dice:** PostHog ("what we wish we knew"), Anthropic ("Demystifying evals for AI agents"). Confianza: HIGH.
**El error:** construir el agente, lanzarlo, y recién ahí descubrir que no hay forma de saber si un cambio de prompt/modelo mejoró o empeoró el sistema. En agentes los errores se propagan y componen entre turnos.
**Para Wyss:** crear desde la fase 1 un set de casos dorados: N consultas de conocimiento con respuesta esperada (¿encontró el archivo correcto?), M planes con nivel de política esperado (¿clasificó B como B y D como D?). El clasificador de política cognitiva ES el componente de seguridad: un falso-A (ejecutar lo que debía confirmar) es el peor bug posible y solo un eval lo detecta antes que el owner.

### 2. Observabilidad/tracing ≠ auditoría
**Quién lo dice:** PostHog, survey AgentOps (arXiv), AgentSight. Confianza: HIGH.
**El error:** confundir el log de auditoría (para rendir cuentas: qué se hizo) con tracing (para debuggear: por qué el agente decidió eso — prompt exacto, contexto recuperado, output crudo, latencia, tokens). Cuando el agente hace algo raro, el audit trail dice "agente X ejecutó Y" pero no permite reconstruir la decisión.
**Para Wyss:** el RF-022 cubre auditoría; falta el trace por llamada LLM (input/output/latencia/costo) consultable. Barato de agregar al principio, carísimo de retrofittear.

### 3. Memoria del agente agregada tarde
**Quién lo dice:** ecosistema mem0/Redis/CoALA; todos los asistentes personales convergieron en esto. Confianza: HIGH.
**El error:** tratar la memoria como "nice to have" y descubrir que sin ella el asistente personal no se siente personal. Después hay que migrar conversaciones históricas que nunca se guardaron estructuradamente.
**Para Wyss:** definir el esquema de memoria (preferencias del owner, decisiones pasadas, resultados de tareas) aunque la extracción automática llegue después. Mínimo: guardar todo desde el día 1 en formato recuperable.

### 4. Context engineering / context rot en tareas largas
**Quién lo dice:** Towards Data Science, paper de coding agents (arXiv 2603.05344): "lo que parecen fallas del modelo son fallas del harness — el agente olvidó porque nada persistió el estado correcto". Confianza: HIGH.
**El error:** dejar que el contexto crezca sin control en tareas multi-paso → degradación de calidad + explosión de costo.
**Para Wyss:** el Context Minimizer ya existe para privacidad; extenderlo a gestión de contexto por longitud (compactación, artefactos durables entre pasos del plan en vez de re-inyectar historia completa).

### 5. Prompt injection vía contenido indexado (el punto ciego de la política cognitiva)
**Quién lo dice:** caso OpenClaw (Cisco, CrowdStrike, HiddenLayer, The Hacker News): inyección indirecta → RCE silencioso, exfiltración, persistencia. Confianza: HIGH.
**El error específico que amenaza a Wyss:** la política A/B/C/D evalúa *planes*, pero el contenido recuperado de las BC entra al contexto del agente *antes* de planificar. Un documento malicioso entre los 2TB (un PDF bajado, un mail archivado, un repo clonado) puede contener instrucciones que el agente interprete. Con team mode, terceros escriben mensajes que un agente procesa: superficie de ataque directa.
**Para Wyss:** (a) separar instrucciones de datos — el contenido recuperado se marca como dato no-confiable, nunca como instrucción; (b) niveles de confianza por BC (mis notas ≠ descargas de internet ≠ mensajes de trabajadores); (c) regla: contenido recuperado jamás puede elevar el nivel de acción de un plan ya aprobado.

### 6. Undo / rollback de acciones sobre archivos
**El error:** RF-017 verifica que la acción se hizo, no permite deshacerla. Un agente que "organiza" 500 archivos según un plan aprobado pero mal interpretado es un desastre sin undo.
**Para Wyss:** mover-a-papelera en vez de borrar, journal de operaciones de archivos (origen→destino) con operación inversa, snapshot previo en operaciones masivas. Confianza: MEDIUM (síntesis de mejores prácticas, no de una fuente única).

### 7. Idempotencia y concurrencia en rutinas
**El error:** una rutina que dispara dos veces (reinicio del scheduler, reloj) y duplica efectos; dos tareas tocando los mismos archivos.
**Para Wyss:** ejecución-única por (rutina, ventana), lock por recurso o cola serializada en v0.1. Confianza: MEDIUM.

### 8. Interfaz multi-canal antes de lo previsto
**Observación:** OpenClaw se volvió viral por vivir en Telegram/WhatsApp, no por su motor. Wyss arranca CLI (correcto para v0.1), pero el Flujo 6 (Fama) ya exige un canal de mensajería para trabajadores — y la bandeja de aprobaciones necesita notificar al owner fuera de la CLI. Diseñar la capa de canal como adaptador desde el principio, aunque solo CLI esté implementado. Confianza: MEDIUM.

---

## Anti-features (deliberadamente NO construir — y por qué eso es correcto)

| Anti-feature | Por qué evitarlo | Qué hace Wyss en su lugar | Evidencia |
|--------------|------------------|---------------------------|-----------|
| **Comunicación libre agente-a-agente (swarms, A2A)** | Comportamiento emergente no auditable; las "conversaciones diversas" de AutoGen son su feature menos usable en producción; Microsoft mismo lo pasó a mantenimiento. | RF-011: solo el orquestador delega. Hub-and-spoke. | HIGH |
| **Agentes auto-mejorables que escriben sus propias skills** | El feature "AGI-like" de OpenClaw es exactamente lo que habilitó backdoors persistentes vía memoria local y RCE. Código autogenerado sin revisión = nivel D por definición. | Agentes config-driven; nuevas capacidades = nueva config aprobada por el owner. | HIGH |
| **Autonomía total sin confirmación (modo AutoGPT)** | AutoGPT demostró el patrón: loops infinitos, costo descontrolado, acciones destructivas. Es la razón por la que el ecosistema entero migró a HITL. | Política A/B/C/D. | HIGH |
| **Memoria de largo plazo escribible por contenido externo** | Vector de persistencia de OpenClaw: la inyección escribe en memoria y sobrevive sesiones. | Solo el owner (o extracción supervisada) escribe en memoria/preferencias; contenido de BC nunca escribe memoria directamente. | HIGH |
| **GUI / no-code builder temprano (estilo AutoGen Studio)** | Costo enorme, congela el modelo de datos antes de validarlo. AutoGen Studio no salvó a AutoGen. | CLI + archivos de config versionables; GUI post-validación. | MEDIUM |
| **Voz como interfaz primaria en v0.1** | Complejidad transversal (STT/TTS/turnos) que no valida ninguna hipótesis del núcleo. | Texto primero; voz como adaptador de canal futuro (UC-007 ya prevé voz solo como input de trabajadores). | MEDIUM |
| **Framework multi-agente genérico propio** | Wyss es un producto opinado, no un framework. Competir con LangGraph en generalidad es perder. | Núcleo mínimo propio (o LangGraph como motor interno — decisión de STACK, no de features). | MEDIUM |
| **Fine-tuning de modelos propios** | Costo/mantenimiento injustificado; el routing de modelos (RF-007) da el 90% del beneficio. | Model Router + prompts por agente. | HIGH |

---

## Phase Mapping (qué feature pertenece a qué fase)

Ordenado por dependencias y por la prioridad declarada en los flujos (Flujo 1 = el más frecuente). Las features nuevas detectadas en esta investigación van en **negrita**.

### Fase 1 — Núcleo de conocimiento (Flujos 1 y 4)
- Ingesta incremental + indexación híbrida (RF-012/013/014)
- Consulta con fuente y extracto (UC-001)
- Auditoría base (RF-022/023) + **tracing de llamadas LLM** (omisión #2 — barato ahora, caro después)
- **Eval set semilla: consultas doradas + progreso de indexación visible** (omisión #1, table stake)
- **Indicador de frescura del índice** (puede ser solo metadato "indexado al X" en v0.1)

### Fase 2 — Orquestador + política + ejecución (Flujo 2)
- Intent router, generación de plan (RF-001/002/003/004)
- Policy Engine A/B/C/D (RF-018/019/020) + **evals del clasificador de política** (falso-A = bug crítico)
- Ejecución local con allowlist + verificación posterior (RF-016/017)
- **Undo/journal de operaciones de archivos** (omisión #6 — junto con la primera acción modificadora, no después)
- **Política de errores: retry/escalar/abortar** (table stake)
- Flujo 7 completo: Model Router + Context Minimizer + Cost Tracker con gate

### Fase 3 — Agentes + permisos (Flujos 2 y 5)
- Instanciación config-driven (RF-008), aislamiento (RF-009), reporte (RF-010), no-horizontal (RF-011)
- Permission Manager con alcance/vigencia/revocación inmediata (RF-015)
- **Defensa de prompt injection: niveles de confianza por BC + separación instrucción/dato** (omisión #5 — obligatorio ANTES de que agentes consuman BC con contenido de origen externo)
- **Memoria del agente: esquema + persistencia de interacciones y preferencias** (table stake ausente; la extracción inteligente puede madurar después, el almacenamiento no puede esperar)

### Fase 4 — Rutinas + operación desatendida (Flujo 3)
- Scheduler (RF-006) con **idempotencia** (omisión #7)
- **Bandeja de aprobaciones pendientes + notificación al owner** (table stake — sin esto el Flujo 3 no cierra)
- **Estado durable de tareas + resume** (table stake — las rutinas desatendidas lo vuelven obligatorio)
- UC-006: creación guiada de rutinas con confirmación fuerte

### Fase 5 — Team mode (Flujo 6)
- Adaptador de canal de mensajería (el patrón Fama lo exige; diseñar la abstracción en Fase 1-2, implementar acá)
- Permisos de trabajador (subconjunto del Permission Manager de Fase 3)
- **Endurecer anti-injection: input de trabajadores = contenido no confiable siempre** (extiende omisión #5)

### Fase 6 — Producto replicable (UC-010)
- Replicación de instancia (RF-024) — valida que las Fases 1-5 fueron realmente config-driven
- Proceso guiado de onboarding de cliente
- Sandboxing reforzado (contenedores) si la instancia corre en entorno ajeno

### Señales para el roadmap
- **Fases con mayor necesidad de research adicional:** Fase 1 (chunking/embeddings a escala 2TB, performance FTS5+vectores), Fase 3 (esquema de memoria, técnicas concretas anti-injection), Fase 5 (integración de canal de mensajería).
- **Fases de patrones estándar (poco research):** Fase 2 (planning+HITL bien documentado), Fase 4 (scheduling es territorio conocido; lo nuevo es la bandeja de aprobaciones).

---

## Sources

- [AI Agent Frameworks Compared: LangGraph vs CrewAI vs AutoGen (2026)](https://pecollective.com/blog/ai-agent-frameworks-compared/) — MEDIUM
- [Best Multi-Agent Frameworks in 2026](https://gurusup.com/blog/best-multi-agent-frameworks-2026) — MEDIUM
- [What we wish we knew about building AI agents — PostHog](https://newsletter.posthog.com/p/what-we-wish-we-knew-before-building) — HIGH (post-mortem de primera mano)
- [Demystifying evals for AI agents — Anthropic](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — HIGH (fuente oficial)
- [A Survey on AgentOps (arXiv 2508.02121)](https://arxiv.org/pdf/2508.02121) — HIGH
- [Build long-running AI agents that pause, resume — Google ADK](https://developers.googleblog.com/build-long-running-ai-agents-that-pause-resume-and-never-lose-context-with-adk/) — HIGH (fuente oficial)
- [Personal AI Agents like OpenClaw Are a Security Nightmare — Cisco](https://blogs.cisco.com/ai/personal-ai-agents-like-openclaw-are-a-security-nightmare) — HIGH
- [What Security Teams Need to Know About OpenClaw — CrowdStrike](https://www.crowdstrike.com/en-us/blog/what-security-teams-need-to-know-about-openclaw-ai-super-agent/) — HIGH
- [OpenClaw AI Agent Flaws — The Hacker News](https://thehackernews.com/2026/03/openclaw-ai-agent-flaws-could-enable.html) — MEDIUM
- [Types of AI Agent Memory (CoALA) — Atlan](https://atlan.com/know/types-of-ai-agent-memory/) — MEDIUM
- [AI agent memory: stateful systems — Redis](https://redis.io/blog/ai-agent-memory-stateful-systems/) — MEDIUM (vendor, pero alineado con CoALA)
- [Context Engineering for AI Agents — Towards Data Science](https://towardsdatascience.com/deep-dive-into-context-engineering-for-ai-agents/) — MEDIUM
- [Building Effective AI Coding Agents: Lessons Learned (arXiv 2603.05344)](https://arxiv.org/pdf/2603.05344) — HIGH
- [Khoj — open source personal AI](https://railway.com/deploy/khoj) + GitHub — HIGH para features de Khoj
- [8 Best Open-Source Personal AI Assistants in 2026 — Vellum](https://www.vellum.ai/blog/best-open-source-personal-ai-assistants) — MEDIUM
