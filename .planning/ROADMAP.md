# Roadmap: Wyss

## Milestones

- ✅ **v0.1 Demo técnica** — Phases 1-8 (shipped 2026-07-10, tagged v0.1.0)
- ✅ **v1.0 Producto final — app móvil + asistente diario** — Phases 9-15 (complete)
- ✅ **v1.0 Integración Home autoritativa** — Phase 16 (complete 2026-07-20)

**Regla transversal inviolable:** nada B/C se auto-ejecuta — todo productor de planes (rutinas, intake, agentes) pasa por `CognitivePolicyEngine` y cae a la bandeja; el owner sella. Nivel D absoluto.

**Estructura v1.0:** vertical slices ordenados por dependencia (research/SUMMARY.md, confidence HIGH). Sin un segundo camino de ejecución: cada feature reusa `dispatch()` (nuevo productor de Plan) o el patrón Tool adapter (nueva Action gateada).

## Phases

- [x] **Phase 1: Fundaciones** - Núcleo hexagonal, política cognitiva A/D, auditoría
- [x] **Phase 2: Gateway de Modelos** - Salida única a IA con minimización + costo + tracing
- [x] **Phase 3: Pipeline de Ingesta** - Indexado incremental FTS5 + vectores, secretos excluidos
- [x] **Phase 4: Búsqueda Híbrida** - Encontrar cualquier archivo en segundos (RRF)
- [x] **Phase 5: Orquestador Daemon** - Daemon persistente, planes, confirmaciones
- [x] **Phase 6: Capa de Ejecución** - Acciones reales (fs/shell/git) con undo + 2da muralla
- [x] **Phase 7: Modelo de Agentes** - AgentBase config-driven + permisos estructurales
- [x] **Phase 8: Primer Agente (Finanzas)** - Pellegrini coach + ledger SQLite
- [x] **Phase 9: Routine Scheduler** - Rutinas programadas que caen a la bandeja por política
- [x] **Phase 10: Notion Adapter** - Leer/escribir Notion como acciones gateadas
- [x] **Phase 11: Owner Memory** - Memoria persistente, editable y trust-tiered
- [x] **Phase 12: Daily Assistant** - Digest diario proactivo (solo lectura)
- [x] **Phase 13: Intake n8n** - Webhook externo → propuesta → bandeja con bearer token
- [x] **Phase 14: Web PC Polish** - Glow-up desktop + superficies de rutinas/digest/memoria
- [x] **Phase 15: Mobile APK** - Capacitor + pairing QR + cert pinning TOFU
- [x] **Phase 16: Home Authority Core** - Ports, RPC Unix idempotente, política y auditoría

## Phase Details

<details>
<summary>✅ v0.1 Demo técnica (Phases 1-8) — SHIPPED 2026-07-10 (tag v0.1.0)</summary>

### Phase 1: Fundaciones
**Goal**: Núcleo hexagonal puro — dominio, ports, auditoría, política cognitiva A/D sin IO.
**Requirements**: POL-01..05, AUD-01
**Plans**: 6/6 complete

### Phase 2: Gateway de Modelos
**Goal**: Único punto de salida a IA externa con minimización de contexto, gate de costo y tracing.
**Requirements**: GATE-01..05, ORCH-06, ORCH-07
**Plans**: complete

### Phase 3: Pipeline de Ingesta
**Goal**: Escanear/extraer/indexar archivos en FTS5 + vectores, incremental y con secretos excluidos.
**Requirements**: KNOW-01, KNOW-02, KNOW-03, KNOW-06, KNOW-07, KNOW-08, KNOW-09, KNOW-11
**Plans**: 7/7 complete

### Phase 4: Búsqueda Híbrida
**Goal**: Encontrar cualquier archivo en segundos — FTS5 + semántica fusionadas (RRF).
**Requirements**: KNOW-04, KNOW-05, KNOW-10, AUD-03
**Plans**: 3/3 complete

### Phase 5: Orquestador Daemon
**Goal**: Proceso persistente que recibe lenguaje natural, clasifica intención, genera planes y gestiona confirmaciones.
**Requirements**: ORCH-01..05, POL-06, AUD-02
**Plans**: 5 plans (05-05 HermesOrchestrator BLOQUEADO por A2 — sin imagen Hermes publicada)

### Phase 6: Capa de Ejecución
**Goal**: Acciones reales (archivos, shell, git) con verificación posterior, undo y segunda muralla.
**Requirements**: EXEC-01..04
**Plans**: 5/5 complete

### Phase 7: Modelo de Agentes
**Goal**: AgentBase + registro config-driven + permisos estructurales — instanciar agentes sin código nuevo.
**Requirements**: AGENT-01..06, AGENT-08, POL-07
**Plans**: 5/5 complete

### Phase 8: Primer Agente de Dominio (Finanzas) — Pellegrini
**Goal**: Owner carga ingresos/gastos (CLI + conversacional) y Pellegrini los analiza.
**Requirements**: AGENT-07, AGENT-09
**Plans**: 4/4 complete (checkpoint owner APROBADO 2026-06-17; deuda: calibración de prosa advisory con LLM real)

</details>

### 🚧 v1.0 Producto final (Phases 9-15)

**Milestone Goal:** Wyss deja de ser demo técnica: APK Android instalable + web PC pulida + asistente diario real (rutinas, Notion, memoria, intake automático), sin introducir un segundo camino de ejecución.

> Nota de historial: las viejas fases 9 (Multi-agente y Rutinas) y 10 (Modo Equipo) del roadmap v0.1 nunca se construyeron. Su parte de rutinas se absorbe en la nueva **Phase 9 (Routine Scheduler)** sin multi-agente pleno (cierra MULTI-02); Modo Equipo (TEAM-01/02) queda **fuera de scope** de v1.0 (post-v1.0).

#### Phase 9: Routine Scheduler
**Goal**: El owner puede programar rutinas recurrentes que disparan Planes por el mismo gate de política — las propuestas B/C caen a la bandeja, jamás auto-ejecutan.
**Depends on**: Phase 5 (daemon + dispatch), Phase 6 (ejecución), Phase 8 (existente)
**Requirements**: SCHED-01, SCHED-02, SCHED-03, SCHED-04, SCHED-05
**Success Criteria** (what must be TRUE):
  1. El owner crea una rutina (cron u hora fija) desde CLI o web y ve un preview legible del schedule antes de guardar
  2. Cuando una rutina dispara, las acciones A ejecutan directo y las B/C caen a la bandeja como propuesta — nunca auto-ejecución (cierra MULTI-02)
  3. El owner lista, pausa, reanuda y borra rutinas, y ve el último resultado de cada una
  4. Tras downtime del daemon, las rutinas perdidas se coalescen con catch-up explícito — jamás doble-fire
  5. Cada disparo queda auditado: trigger, plan, decisión de política y resultado
**Plans**: 5/5 complete
Plans:
- [x] 09-01-PLAN.md — apscheduler dep (gate de legitimidad) + AuditEventType.ROUTINE_TRIGGERED
- [x] 09-02-PLAN.md — RoutineStore (SQLite WAL, CRUD, mark_fired atómico) [SCHED-03]
- [x] 09-03-PLAN.md — RoutineScheduler: gate de política + TTL 24h + catch-up + auditoría [SCHED-01/02/04/05]
- [x] 09-04-PLAN.md — handlers routine.* del daemon + sub-app CLI `wyss routine` [SCHED-01/03]
- [x] 09-05-PLAN.md — checkpoint: smoke de reloj real (rutina → bandeja, sin auto-exec, auditada)
**Research flags**: catch-up policy post-downtime (planning), timezone entre máquinas (testing)

#### Phase 10: Notion Adapter
**Goal**: El owner puede leer y escribir contenido de Notion como acciones gateadas por política, con preview de writes.
**Depends on**: Phase 9 (patrón de dispatch), gateway/política existentes
**Requirements**: NOTION-01, NOTION-02, NOTION-03, NOTION-04
**Success Criteria** (what must be TRUE):
  1. El owner pide en lenguaje natural leer una página/database de Notion y ve el contenido (nivel A con base_levels explícito para notion.*)
  2. El owner pide crear/editar en Notion y el write cae como propuesta B/C con preview del cambio antes de confirmar
  3. El adapter respeta rate limits (retry/backoff en 429) y pagina resultados completos
  4. El token de Notion vive en config/.env (nunca en repo) y toda llamada queda auditada
**Plans**: 4 plans
- [ ] 10-01-PLAN.md — Paquete src/notion/ (client/tool/markdown/pagination) + dep + tests sin red
- [ ] 10-02-PLAN.md — Registro en política/planner: _BASE_LEVELS + 5 conftests + _ACTION_TYPES + minimizer token
- [ ] 10-03-PLAN.md — Dispatch en PlanExecutor + inyección desde composition root + preview de writes
- [ ] 10-04-PLAN.md — Checkpoint: smoke real contra el workspace del owner (token real)
**Research flags**: base_levels específicos de notion.* (planning), paginación/429 testear temprano

#### Phase 11: Owner Memory
**Goal**: El owner tiene una memoria persistente, editable y trust-tiered que alimenta al planner como DATO, no como instrucción.
**Depends on**: Phase 9. Debe existir ANTES de la Phase 13 (intake externo) — el trust-tiering previene laundering de prompt-injection.
**Requirements**: MEM-01, MEM-02, MEM-03, MEM-04
**Success Criteria** (what must be TRUE):
  1. El owner le dice a wyss que recuerde un hecho/preferencia y persiste (write = acción gateada ≥B)
  2. El owner ve, edita y borra su memoria — legible, nunca un blob opaco
  3. La memoria distingue trust tiers (owner-stated vs ingested-external); el contenido externo jamás se recuerda sin confirmación
  4. El contenido recordado se inyecta como DATO (no instrucción) en los prompts del planner — un fact con instrucciones inyectadas no altera el plan (test anti-injection)
**Plans**: 5 plans
  - [ ] 11-01-PLAN.md — Fundación: MemoryFact + MemoryPort/MemoryAdmin + MemoryStore SQLite + registro import-linter
  - [ ] 11-02-PLAN.md — Write-path: MemoryTool (tier hardcodeado) + base_level memory.remember=B + 5 conftests
  - [ ] 11-03-PLAN.md — Anti-injection: _format_memory_safe + inyección en _draft_prompt + test MEM-04
  - [ ] 11-04-PLAN.md — Cableado: 5ta rama executor + RPC memory.list/edit/forget en el daemon
  - [ ] 11-05-PLAN.md — Composition root + CLI memory list/edit/rm + smoke real (human-verify)
**Research flags**: formato de trust-tier markers (planning)

#### Phase 12: Daily Assistant
**Goal**: El owner recibe un digest diario proactivo y de solo lectura que compone bandeja + Pellegrini + fallas de rutinas.
**Depends on**: Phase 9 (rutina programada 08:00), Phase 11 (memoria), Phase 8 (ledger Pellegrini)
**Requirements**: DAILY-01, DAILY-02, DAILY-03
**Success Criteria** (what must be TRUE):
  1. El owner recibe un digest diario a hora configurable con pendientes de bandeja, snapshot Pellegrini y fallas de rutinas
  2. El digest es solo lectura (nivel A) — nunca ejecuta ni propone writes por sí solo
  3. El owner ve el digest del día en la web y puede pedirlo on-demand
**Plans**: 4 plans
Plans:
- [ ] 12-01-PLAN.md — Composer puro compose_digest() + seccion [digest] en config + AuditEventType.DIGEST_GENERATED [DAILY-01/02]
- [ ] 12-02-PLAN.md — RPC digest.today (LedgerPort inyectado) + job interno del scheduler que materializa data/digests/*.md [DAILY-01/03]
- [ ] 12-03-PLAN.md — CLI `wyss digest` (thin RPC client) + composition root (ledger real + digest job) [DAILY-01/03]
- [ ] 12-04-PLAN.md — Checkpoint: digest real on-demand + archivo programado, solo lectura verificada [DAILY-01..03]
**Decisiones de planning**: fallas de rutinas desde RoutineStore.last_outcome (no audit read port); ledger via core.ports.ledger.LedgerPort (independence); digest programado = job interno del scheduler (no Routine ni action type — minima superficie, MULTI-02 intacto); materializa a archivo data/digests/YYYY-MM-DD.md; web (WEB-02) llega en fase 14, fase 12 deja el RPC listo.

#### Phase 13: Intake n8n
**Goal**: Workflows n8n externos pueden postear propuestas que rutean por el gate de política hasta la bandeja, con bearer token dedicado.
**Depends on**: Phase 11 (trust-tiering de memoria debe existir antes del intake externo), Phase 9 (dispatch)
**Requirements**: INTAKE-01, INTAKE-02, INTAKE-03
**Success Criteria** (what must be TRUE):
  1. Un workflow n8n postea a `POST /api/intake` con bearer token dedicado — nunca la cookie del pairing
  2. Toda propuesta de intake pasa por la política y cae a la bandeja como B/C — jamás auto-ejecuta
  3. El endpoint tiene rate limit propio y rechaza sin token válido (401 auditado, sin loguear el token)
**Plans**: 3 plans
- [ ] 13-01-PLAN.md — Config [intake] opt-in + RPC daemon intake.propose con floor B forzado (sin tocar dispatcher.py) [INTAKE-02]
- [ ] 13-02-PLAN.md — Endpoint POST /api/intake: bearer dedicado (data/intake_token) + rate limit propio + exencion de cookie acotada [INTAKE-01, INTAKE-03]
- [ ] 13-03-PLAN.md — Checkpoint: smoke real curl-como-n8n (bearer->bandeja, sin bearer->401, flood->429, cero auto-ejecucion) [INTAKE-01..03]
**Decisiones de planning**: floor B via RPC nuevo reusando dispatch intacto (max(risk,B)+outcome_for antes de dispatch); origen auditado SYSTEM/intake distinguible de owner; intake JAMAS escribe a memoria (anti memory-poisoning); bearer estatico espeja _load_or_create_web_token; exencion de cookie SOLO para /api/intake (host+origin siguen); 401/429 via _LOG.warning sin loguear el token; rate limit en memoria por minuto; enabled=false default -> endpoint 404.

#### Phase 14: Web PC Polish
**Goal**: El owner gestiona rutinas, digest y memoria desde una web desktop cohesiva y con glow-up de página entera.
**Depends on**: Phase 9 (rutinas), Phase 11 (memoria), Phase 12 (digest)
**Requirements**: WEB-01, WEB-02, WEB-03, WEB-04
**Success Criteria** (what must be TRUE):
  1. El owner ve y gestiona rutinas desde la web (lista, estado, pausar/reanudar)
  2. El owner ve el digest diario en la web
  3. El owner edita su memoria desde la web
  4. La UI desktop recibe un glow-up cohesivo de página entera: aprovecha la pantalla grande, jerarquía clara, sin huecos de layout
**Plans**: 5 plans
- [ ] 14-01-PLAN.md — Endpoints bridge + api.ts client + tests backend (codex)
- [ ] 14-02-PLAN.md — Superficie Rutinas (claude)
- [ ] 14-03-PLAN.md — Superficies Digest + Memoria (claude)
- [ ] 14-04-PLAN.md — Nav shell agrupada + glow-up + gates front (claude/codex)
- [ ] 14-05-PLAN.md — Smoke visual desktop + celu (checkpoint owner)
**UI hint**: yes

#### Phase 15: Mobile APK
**Goal**: El owner instala un APK Android que abre wyss como app nativa contra el bridge, pareado por QR con cert pinning, con paridad de confirmación B/C.
**Depends on**: Phase 14 (paridad de superficie web)
**Requirements**: APK-01, APK-02, APK-03, APK-04, APK-05, APK-06
**Success Criteria** (what must be TRUE):
  1. El owner instala un APK que abre wyss como app nativa apuntando al mismo origen del bridge (`server.url`) — sin bundle local, sin aflojar allowlist de Host/Origin ni CORS
  2. Pairing por QR: la app escanea un QR con URL del bridge + fingerprint del cert y queda pareada sin tipear nada
  3. La app confía SOLO en el cert cuya huella vino en el QR (TOFU pinning en `onReceivedSslError`); cert distinto = bloqueo con aviso, jamás proceed ciego
  4. El owner confirma propuestas B/C desde la app con paridad funcional respecto a la web (gate CONFIRMAR incluido)
  5. Ante server caído o IP cambiada, la app muestra un error accionable y permite re-pairing
**Plans**: 6 plans
Plans:
- [x] 15-01-PLAN.md — SPIKE device obligatorio: scaffold Capacitor mobile/ + loadUrl handoff + pinning hardcodeado (valida A1/A2) [APK-01/03/04]
- [x] 15-02-PLAN.md — Backend GET /api/pair + wiring cli.py + tests Wave 0 (api_pair auth + regresion Origin-collision) [APK-02/04]
- [x] 15-03-PLAN.md — Native pinning real + PairingPlugin core + funciones puras + unit tests JVM [APK-03/04]
- [x] 15-04-PLAN.md — Pantalla pairing bundled: escaneo ML Kit + handoff + error accionable/re-pair [APK-02/06]
- [x] 15-05-PLAN.md — SPA seccion "Parear telefono": QR SVG client-side desde /api/pair + vitest [APK-02]
- [x] 15-06-PLAN.md — Checkpoint E2E device: instala + pairing QR + confirma B/C + cert rotado/server caido [APK-01/05/06]
**Waves**: W1 {15-01 spike, 15-02 backend} · W2 {15-03 native, 15-05 SPA} · W3 {15-04 bundle UI} · W4 {15-06 device E2E}
**Research flags**: HIGH — spike de cert pinning + schema del QR payload ANTES de construir (spike = 15-01, gate de wave)
**UI hint**: yes

#### Phase 16: Home Authority Core
**Goal**: Yo convierto a Wyss en la única autoridad pública para intenciones, planes,
confirmaciones y auditoría consumidas por Home Edge.
**Depends on**: Phase 5 (daemon), Phase 6 (segunda muralla), Phase 15 (clientes existentes)
**Requirements**: HOME-CORE-01..06
**Success Criteria**:
  1. Yo expongo ports puros antes de cada adapter Home
  2. Yo acepto intenciones por socket Unix `0600` con identidad, correlación e idempotencia durable
  3. Yo mantengo B simple, C literal, D absoluto y re-evaluación antes de resolver
  4. Yo hago que la primera respuesta válida gane de forma atómica
  5. Yo completo audit RPC mediante un port sin acceso directo a SQLite desde aplicación
  6. Yo mantengo Python, web y Android como gates bloqueantes
**Plans**: ejecución incremental mediante PR #3–#7; el siguiente corte conecta el adapter de Home Edge.

## Coverage

**v1.0: 25/25 requirements mapeados a exactamente una fase.**

- SCHED-01..05 → Phase 9
- NOTION-01..04 → Phase 10
- MEM-01..04 → Phase 11
- DAILY-01..03 → Phase 12
- INTAKE-01..03 → Phase 13
- WEB-01..04 → Phase 14
- APK-01..06 → Phase 15

Sin orphans, sin duplicados. MULTI-02 (nada B/C se auto-ejecuta) se cierra en Phase 9. TEAM-01/02, PUSH-01, REMOTE-01, NSYNC-01 = fuera de scope v1.0 (ver REQUIREMENTS.md).

## Progress

**Execution Order:** 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Fundaciones | v0.1 | 6/6 | Complete | 2026-06-11 |
| 2. Gateway de Modelos | v0.1 | complete | Complete | 2026-06-12 |
| 3. Pipeline de Ingesta | v0.1 | 7/7 | Complete | 2026-06-12 |
| 4. Búsqueda Híbrida | v0.1 | 3/3 | Complete | 2026-06-13 |
| 5. Orquestador Daemon | v0.1 | 4/5 | Complete (05-05 blocked) | 2026-06-13 |
| 6. Capa de Ejecución | v0.1 | 5/5 | Complete | 2026-06-13 |
| 7. Modelo de Agentes | v0.1 | 5/5 | Complete | 2026-06-16 |
| 8. Primer Agente (Finanzas) | v0.1 | 4/4 | Complete | 2026-06-17 |
| 9. Routine Scheduler | v1.0 | 0/5 | Planned | - |
| 10. Notion Adapter | v1.0 | 0/TBD | Not started | - |
| 11. Owner Memory | v1.0 | 0/TBD | Not started | - |
| 12. Daily Assistant | v1.0 | 0/TBD | Not started | - |
| 13. Intake n8n | v1.0 | 0/TBD | Not started | - |
| 14. Web PC Polish | v1.0 | complete | Complete | 2026-07-11 |
| 15. Mobile APK | v1.0 | 6/6 | Complete | 2026-07-11 |
| 16. Home Authority Core | v1.0 | incremental | Complete | 2026-07-20 |

## Milestones del research (v1.0)

- **Foundation** (fin Phase 9): todo lo autónomo (Daily, Intake) depende del scheduler probado
- **Trust boundary** (fin Phase 11): memoria trust-tiered ANTES de que Notion/n8n escriban contenido recordable
- **Producto final** (fin Phase 15): APK instalado + web pulida + asistente diario operativo
