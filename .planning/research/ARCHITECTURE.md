# Architecture Research

**Domain:** Integración de features nuevas (Scheduler, Notion adapter, Memory, Daily Assistant, Intake n8n, Capacitor APK) en un operador local hexagonal existente (Wyss v0.1.0)
**Researched:** 2026-07-10
**Confidence:** HIGH (basado en lectura directa del repo: `daemon.py`, `dispatcher.py`, `pending_store.py`, `ttl_reaper.py`, `core/policy/engine.py`, `core/ports/*`, `bootstrap/web.py`, `bootstrap/tls.py`, `agents/memory.py`, `docs/architecture/WYSS_TARGET_ARCHITECTURE.md`, `docs/security/SECURITY_MODEL.md`) + MEDIUM para las partes de Android WebView / Notion SDK (verificadas por WebSearch, no por código propio)

## Principio rector

Ninguna feature nueva introduce un segundo camino de ejecución. Las seis features se resuelven **sin tocar el molde**: todas caen en uno de dos patrones ya existentes en el repo —

1. **Nueva Action type + adapter** (el patrón `file.*` / `shell.*` / `git.*`): Notion y Memory-write son esto.
2. **Nuevo productor de Plan que entra por el mismo `dispatch()`** (el patrón que ya usa `daemon._ask`): Scheduler, Daily Assistant e Intake n8n son esto.

Capacitor no es una feature de backend: es un cliente más del bridge existente, igual que el browser del teléfono hoy.

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CLIENTES                                                                 │
│  CLI Typer · Web PC (browser) · Web móvil (browser) · APK Capacitor      │
│  (Capacitor = WebView navegando al MISMO origin del bridge, no un        │
│   cliente API aparte)                                    n8n (Docker,    │
│                                                            localhost)     │
└───────────┬───────────────────────────────────────┬──────────────────────┘
            │ HTTPS + cookie pairing                │ POST /api/intake
            │ (owner)                               │ (bearer token propio,
            ▼                                        │  jamás /api/confirm)
┌──────────────────────────────────────────────────────────────────────────┐
│  bootstrap/web.py (bridge FastAPI, composition root — NUNCA decide riesgo)│
│  NUEVO: POST /api/intake  ·  GET /api/digest/today (lee audit)           │
└───────────┬────────────────────────────────────────────────────────────┘
            │ Unix socket JSON-RPC ("ask" / "confirm" / "status")
            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  orchestrator/daemon.py  (DaemonServer, asyncio.start_unix_server)       │
│                                                                           │
│  RunningDaemon (tasks vivas junto al server):                            │
│    - reaper_task     = ttl_reaper(pending_store, audit)      [existe]   │
│    - NUEVO scheduler_task = RoutineScheduler.run(...)                    │
│                                                                           │
│  _ask()/_confirm() [existentes]  ←──── NUEVO: RoutineScheduler arma un   │
│         │                               Plan de rutina y llama el MISMO  │
│         ▼                               dispatch(), nunca un path propio │
│  LLMOrchestrator.draft_plan() → Plan                                     │
│         ▼                                                                │
│  CognitivePolicyEngine.evaluate(plan)   (core/policy — sin tocar)        │
│    NUEVO: base_levels["notion.read"]=A, ["notion.write"]=C,              │
│           ["memory.write"]=B, ["assistant.digest"]=A                    │
│         ▼                                                                │
│  dispatch() → PendingStore (B/C) | ejecuta directo (A)                  │
└───────────┬────────────────────────────────────────────────────────────┘
            │ PlanRunner.run(plan)  (Tool protocol, prefijo de action.type)
            ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  execution/executor.py — despacha por prefijo:                          │
│    "file"→FileSystemAdapter  "shell"→ShellAdapter  "git"→GitAdapter      │
│    NUEVO "notion"→NotionTool (paquete notion/, nuevo)                    │
│    NUEVO "memory"→MemoryTool (paquete memory/, nuevo)                    │
└──────────────────────────────────────────────────────────────────────────┘

  Capas nuevas, independientes entre sí (import-linter):
  notion/  → NotionTool (Tool protocol) + cliente notion-client, solo importa core
  memory/  → MemoryPort impl (SQLite hechos/preferencias) + MemoryTool, solo importa core
```

### Component Responsibilities

| Component | Responsibility | Nuevo/Modificado |
|-----------|----------------|-------------------|
| `orchestrator/scheduler.py` (nuevo) | `RoutineScheduler`: task asyncio en el loop del daemon; por cada rutina vencida construye un `Plan`, llama `engine.evaluate()` + `dispatch()` — **nunca ejecuta directo si sale B/C** | Nuevo, vive en `orchestrator/` (ya legítimo ahí) |
| `notion/` (nuevo paquete top-level) | Adapter `NotionTool` (implementa `Tool`): `notion.read_page`, `notion.query_database`, `notion.write_page`, `notion.append_block`. Envuelve `notion-client` SDK | Nuevo, capa independiente (import-linter) |
| `memory/` (nuevo paquete top-level) | `MemoryStore` (SQLite: hechos/preferencias con `key, value, category, source, updated_at`) + `MemoryTool` (`memory.write` como Action) + función pura `recall_for_prompt()` que devuelve texto ya envuelto como dato-no-instrucción | Nuevo, capa independiente |
| `agents/memory.py` (`AgentMemory`) | Memoria **por-agente** (MEMORY.md), sigue existiendo sin cambios — es un dominio distinto (preferencias que un agente concreto aprendió sobre SU tarea, no el owner en general) | Sin cambios |
| `orchestrator/daily_assistant.py` (nuevo, o función dentro de `scheduler.py`) | Rutina especial: lee (nivel A, directo) knowledge.query + ledger + memory.recall, arma un resumen (opcionalmente vía gateway/LLM como advisory), lo persiste como `AuditEventType.DIGEST_GENERATED` | Nuevo |
| `bootstrap/web.py` | Bridge FastAPI. **NUEVO** `POST /api/intake` (auth por bearer token de servicio, no cookie), **NUEVO** `GET /api/digest/today` | Modificado (aditivo) |
| `core/policy/engine.py` / config | `base_levels` para `notion.*`, `memory.write`, `assistant.digest`; posible regla deny nueva `notion-outside-workspace` | Modificado (aditivo, config + tabla, sin tocar el algoritmo) |
| Capacitor APK (`android/`, nuevo) | WebView que navega al origin del bridge (mismo modelo que el browser del teléfono). Pantalla de pairing propia (`capacitor://` origin) con QR scanner | Nuevo proyecto, no toca Python |

## Recommended Project Structure

```
src/
├── core/
│   └── ports/
│       ├── memory.py          # NUEVO: Protocol MemoryPort (recall/write_supervised)
│       └── (execution.py, orchestrator.py sin cambios — Notion/Memory reusan Tool)
├── notion/                    # NUEVO paquete top-level (independence contract)
│   ├── __init__.py
│   ├── client.py              # wrapper delgado sobre notion-client
│   └── tool.py                # NotionTool(Tool): notion.read_page/write_page/query_database
├── memory/                    # NUEVO paquete top-level (independence contract)
│   ├── __init__.py
│   ├── store.py                # MemoryStore: SQLite hechos/preferencias
│   └── tool.py                 # MemoryTool(Tool): memory.write (Action, pasa por policy)
├── orchestrator/
│   ├── scheduler.py            # NUEVO: RoutineScheduler (APScheduler AsyncIOScheduler o loop propio)
│   ├── daily_assistant.py      # NUEVO: compone digest desde knowledge+ledger+memory
│   └── (daemon.py modificado: registra scheduler_task en RunningDaemon)
├── execution/
│   └── executor.py             # MODIFICADO: mapa de adapters += {"notion": NotionTool, "memory": MemoryTool}
├── bootstrap/
│   └── web.py                  # MODIFICADO: += POST /api/intake, GET /api/digest/today
└── (agents/, knowledge/, gateway/, audit/, ledger/ sin cambios estructurales)

android/                        # NUEVO — proyecto Capacitor
├── app/src/main/.../PairingActivity.kt   # scanner QR + persistencia server URL
├── app/src/main/.../CertPinningClient.kt # onReceivedSslError con fingerprint pinning
└── app/src/main/res/xml/network_security_config.xml  # fallback: user CA (mkcert)
web/
└── src/pairing/                # NUEVO: pantalla mínima capacitor:// (solo se ve la 1ª vez)
```

### Structure Rationale

- **`notion/` y `memory/` como paquetes top-level nuevos, no submódulos de `execution/`:** cada uno trae su propia dependencia externa (`notion-client`, nada para memory) y su propio import-linter contract de independencia — igual que `gateway/providers/` está separado de `execution/`. Meterlos dentro de `execution/` mezclaría un adapter con dependencia de red (Notion) con adapters de disco/proceso local, que hoy están diseñados asumiendo I/O local (2ª muralla de paths, journal de filesystem). Separar deja claro que Notion NO pasa por `execution/journal.py` (su "undo" es el trash/archive nativo de Notion, no nuestro `UndoJournal`).
- **`core/ports/memory.py` nuevo, no reusar `agents/memory.py`:** `AgentMemory` es memoria **por-agente** (ya resuelto, D-71, no tocar). La memoria del owner (nueva, MULTI-01/AGENT-04 no cubre esto) es transversal — la necesitan el Daily Assistant, el LLMOrchestrator y potencialmente cualquier agente. Es "una capa dueña" distinta: mezclarla con `AgentMemory` rompería esa regla del roadmap (`docs/architecture/WYSS_MASTER_ARCHITECTURE_AND_ROADMAP.md` §7: "cada dato tiene UNA capa dueña").
- **`orchestrator/scheduler.py` dentro de `orchestrator/`, no un paquete nuevo:** ya importa legítimamente `core.policy`, `core.domain`, `PendingStore` — exactamente lo que necesita. Crear un paquete `scheduler/` aparte solo para respetar el import-linter sería ceremonia sin beneficio: el scheduler ES parte del orquestador (misma responsabilidad que `dispatcher.py`/`ttl_reaper.py`).
- **`android/` fuera de `src/`:** proyecto Gradle/Kotlin independiente del árbol Python; Capacitor lo genera con `npx cap add android` a partir de `web/`.

## Architectural Patterns

### Pattern (a): Scheduler como task asyncio del daemon, nunca loop propio separado

**What:** `RoutineScheduler` se integra en `start_daemon()` exactamente como `ttl_reaper`: se crea con `asyncio.create_task(...)` dentro del MISMO event loop del `DaemonServer`, y su handle se guarda en `RunningDaemon` (nuevo campo `scheduler_task`) para poder cancelarlo en `aclose()`. **No** es un proceso separado, ni un segundo Unix socket, ni un `systemd timer` corriendo `wyss ask` por fuera del daemon — eso duplicaría el ciclo de vida y complicaría el apagado limpio.

**When to use:** Cualquier trabajo periódico que necesite tocar `PendingStore`/`CognitivePolicyEngine` debe vivir DENTRO del proceso daemon, porque `PendingStore` es SQLite con `journal_mode=WAL` abierto por una sola conexión por proceso (ver `pending_store.py` — no está diseñado para multi-proceso concurrente sin coordinar).

**Trade-offs:** Correr dentro del daemon significa que si el daemon está caído, las rutinas no disparan (aceptable: es exactamente la garantía que ya existe — "el owner debe arrancar `wyss start`" — no un motivo para bifurcar el modelo).

**Implementación recomendada — motor de scheduling:**
`docs/architecture/WYSS_TARGET_ARCHITECTURE.md` §5 dice "APScheduler ya en stack", pero **no está en `pyproject.toml`** (verificado — no aparece en `[project].dependencies`). Es una promesa de doc no cumplida, agregarla es parte de este build. Usar `APScheduler>=3.11` con `AsyncIOScheduler`: corre jobs en el MISMO event loop (no crea threads propios), soporta `CronTrigger`/`IntervalTrigger` (necesario para "Daily Assistant a las 8am" sin reinventar parsing de cron), y es lo bastante aburrido (maduro desde 2011, API estable) para no violar el principio "aburrido a propósito" del roadmap. Alternativa más minimalista (loop propio estilo `ttl_reaper`, comparando `datetime.now()` contra `next_run_at` en una tabla `routines`) es válida si se prefiere cero dependencias nuevas — pero pierde soporte de cron-expressions y hay que escribirlo a mano.

```python
# orchestrator/scheduler.py (esqueleto)
async def scheduler_task(
    routines: RoutineStore,
    *,
    engine: CognitivePolicyEngine,
    pending_store: PendingStore,
    audit: AuditPort,
    plan_builder: Callable[[Routine], Plan],  # arma el Plan desde la config de la rutina
    interval_s: float = 30.0,
) -> None:
    while True:
        for routine in routines.due_now():
            plan = plan_builder(routine)
            decision = engine.evaluate(plan)          # MISMO engine, sin excepciones
            await dispatch(plan, decision, pending_store=pending_store, audit=audit)
            routines.mark_fired(routine.id)            # idempotencia por ventana (ya escrito en target arch §5)
        await asyncio.sleep(interval_s)
```

**Invariante no negociable:** una rutina que resuelve B/C **quedan en `PendingStore` exactamente igual que un `ask()` del owner** — el scheduler jamás llama `_execute_plan` directo salvo que `dispatch()` ya haya decidido "queued" (nivel A). Esto satisface literalmente MULTI-02 y la regla ya escrita en el target architecture: "acciones B/C de rutinas jamás auto-ejecutadas".

### Pattern (b): Notion como Action type + Tool adapter, gateado por policy igual que file/shell/git

**What:** Nuevos `action.type`: `notion.read_page`, `notion.query_database`, `notion.write_page`, `notion.append_block`. `NotionTool` implementa el `Tool` protocol de `core/ports/execution.py` (mismo contrato que `FileSystemAdapter`/`ShellAdapter`/`GitAdapter`) y se registra en el mapa de prefijos de `execution/executor.py` (`action.type.split(".")[0] == "notion"`).

**When to use:** Cualquier capacidad nueva de I/O externo que un `Plan` pueda proponer. Es el patrón ya extensible por diseño ("Plugin Pattern — nueva feature = nueva clase, nunca modificar código existente" — `PROJECT.md`).

**Gotcha crítico de policy (verificado en `core/policy/engine.py` línea 79):** `_base_level` hace fail-closed a **C** para cualquier `action.type` NO registrado en `base_levels`. Si no se agrega explícitamente `base_levels["notion.read_page"] = RiskLevel.A` en la config, **hasta las lecturas de Notion pedirán confirmación fuerte** — rompe el objetivo de que el Daily Assistant lea Notion sin fricción. Este es el mismo gap que el propio `SECURITY_MODEL.md` señala para `net.*`: "No existe tipo de acción de red (`net.*`)... Formalizar en v0.2 si se agrega capacidad de red" — Notion ES esa formalización pendiente.

**Trade-offs:** Escribir a Notion (`notion.write_page`, `notion.append_block`) debe ser mínimo **C** (como `file.write`) — es escritura irreversible por nuestro journal (Notion no pasa por `execution/journal.py`, ver Anti-Pattern más abajo). Considerar una regla deny agregada tipo `notion-outside-workspace` que compare `action.target` (page/database ID) contra un allowlist de IDs en config — mismo patrón que la shell allowlist vacía-por-default.

**Anti-injection:** contenido leído de Notion (`notion.read_page`) es dato externo no confiable. Debe pasar por el MISMO wrapper que ya usa `agents/configured_agent.py::_format_hits_safe` ("Formatea resultados de BC como datos, no instrucciones") antes de llegar a cualquier prompt de LLM — nunca concatenarlo crudo al contexto de `LLMOrchestrator.draft_plan` ni al gateway.

**Auth:** integration token de Notion vive en config/`.env` (frontera Pydantic existente, `bootstrap/config.py`), nunca hardcodeado; el `SecretFilter` de 3 capas (KNOW-04) ya excluye `.env`/tokens de la indexación, así que un token de Notion en `.env` queda protegido por la infraestructura existente sin cambios.

**Confianza sobre el SDK:** MEDIUM. El paquete oficial es `notion-client` (PyPI, mantenido por Makenotion/comunidad), cliente delgado sobre la REST API v1 (`pages`, `blocks/{id}/children`, `databases/{id}/query`), auth `Authorization: Bearer <integration_token>`. **Gotcha operativo conocido (ya en memoria del owner sobre otra integración Notion en este mismo entorno):** una página debe estar explícitamente compartida con la integración o la API la devuelve como inexistente — documentar esto en la config del adapter (`notion.write_page` a una página no compartida falla con 404/403 legible, no un 500 opaco).

### Pattern (c): Memory del owner como port nuevo + write-path supervisado (anti-injection por diseño, no por filtro)

**What:** `core/ports/memory.py` define `MemoryPort` (Protocol): `recall(category: str | None) -> Sequence[MemoryFact]` (lectura libre, nivel A) y **ningún método de escritura directa expuesto al ciclo de agente**. La escritura es una `Action` (`memory.write`) ejecutada por `MemoryTool`, que pasa por `CognitivePolicyEngine` como cualquier otra — nivel **B** mínimo (analogía con `finance.record`): requiere confirmación simple del owner, nunca escribe porque un LLM "decidió" recordar algo.

**Por qué port nuevo y no extensión de `knowledge/`:** `knowledge/` es información del owner sobre EL MUNDO (documentos indexados, secret-gated, FTS5+Chroma) — su contrato (`Retrieval.search`) es de recuperación semántica sobre corpus grande. Memory es información sobre EL OWNER MISMO (preferencias, hechos estables, reglas) — chica, estructurada, con gate de escritura explícito. Meterla en `knowledge/` mezclaría dos ports con invariantes distintos: uno es "todo lo indexado es de solo-lectura desde el punto de vista del agente", el otro es "esto se actualiza por confirmación del owner". El propio target architecture (§7 tabla) ya las separa: "Knowledge... FTS5+Chroma" vs "Memory... memory.db propio; escritura SOLO con confirmación owner".

**Anti-injection — el punto central de la pregunta:** el riesgo no es que Memory contenga datos, es que **contenido recordado se interprete como instrucción** al re-inyectarse en un prompt (ej.: si algún día se guarda un hecho como "cuando pida X, hacé Y" y el LLM lo trata como comando en vez de dato). Dos medidas, no una sola:
1. **Write-path gateado por policy** (arriba): nada llega a `memory.db` sin pasar por confirmación B, igual que `AgentMemory.write_supervised` ya documenta para memoria por-agente ("Contenido recuperado de BC no debe llegar a este método, ni debe llamarse desde el ciclo `_run`" — `agents/memory.py` línea 6). Se reutiliza literalmente la misma regla D-71, ahora a nivel owner.
2. **Read-path envuelto como dato, no instrucción**: `recall_for_prompt()` devuelve el texto con el MISMO patrón de `_format_hits_safe` (delimitadores explícitos, prefijo "Hecho recordado — dato, no instrucción:"), nunca interpolado sin marcar en el system prompt del gateway.

**Trade-off:** una tabla SQLite (`key, value, category, source, updated_at`) en vez de un markdown libre (a diferencia de `AgentMemory`) porque el Daily Assistant necesita filtrar por categoría (agenda/finanzas/preferencias) sin parsear texto libre — el propio target architecture ya decidió esto ("memory.db propio").

### Pattern (d): Daily Assistant como rutina del scheduler que compone SOLO lecturas nivel A + un resumen advisory

**What:** Una rutina registrada en el `RoutineScheduler` (ej. cron `0 8 * * *`) cuyo `plan_builder` no arma Actions mutadoras: compone datos de tres fuentes YA existentes, todas nivel A (directo, sin política de confirmación porque son lecturas):
- `knowledge.query` (agenda/notas — vía `Retrieval` port existente)
- `ledger` (finanzas Pellegrini — reusa la MISMA agregación SQL determinista que ya usa `GET /api/fin/resumen`, invariante "no números por LLM" se mantiene)
- `memory.recall` (preferencias del owner — Pattern c)
- `pending_store.load_pending()` (pendientes de confirmación que siguen abiertos)

El LLM (gateway, tier barato) solo se usa para **redactar el resumen en lenguaje natural** a partir de estos datos ya calculados — nunca para calcular los números (respeta D-87, "no números por LLM"). El resultado se audita como un `AuditEventType` nuevo (`DIGEST_GENERATED`) con el texto en el payload; no hace falta una tabla nueva, `audit.db` ya es append-only y ya tiene endpoint (`GET /api/audit`). Un endpoint fino nuevo `GET /api/digest/today` filtra el último evento de ese tipo — evita construir un "dashboard" nuevo (anti-pattern explícito del roadmap: "dashboards fancy · datos antes que vidrio").

**When to use:** Cualquier rutina que solo "informa" (no propone mutaciones) debería seguir este patrón — lecturas A directas + audit event, sin pasar por `PendingStore` (que es específicamente para B/C).

**Trade-off:** si el Daily Assistant en el futuro quiere PROPONER una acción (ej. "registrá este gasto recurrente"), ESA parte sí es un `Plan` normal que pasa por `dispatch()` como cualquier rutina — no mezclar "informar" con "proponer" en el mismo Action.

### Pattern (e): Intake n8n como endpoint nuevo en el bridge, con auth de servicio separada de la del owner

**What:** `POST /api/intake` en `bootstrap/web.py`, autenticado con un bearer token de servicio DISTINTO del token de pairing del owner (`_TOKEN_COOKIE`) — nunca el mismo secreto. Internamente reusa el MISMO camino que `_ask` del daemon (RPC `ask` vía `_json_rpc_call`, el helper que `web.py` ya usa para `/api/ask`): clasifica intención → `draft_plan` → `CognitivePolicyEngine.evaluate` → `dispatch`. Si sale B/C, cae en `PendingStore` exactamente igual que un `ask()` humano.

**Por qué "n8n nunca confirma" se resuelve por AUSENCIA de ruta, no por permisos:** el token de servicio de n8n simplemente no tiene acceso a `POST /api/confirm/{pending_id}` — no existe un rol/scope framework, es más simple: esa ruta solo acepta la cookie de pairing del owner (`_authenticate_request` ya usa un token distinto). Dado el threat model single-owner-LAN existente, esto es proporcional; documentarlo explícitamente como decisión (no como omisión) porque si algún día se comparte el token de n8n con más de un flujo, hay que revisar esto.

**Auth — recomendación concreta:** dado que n8n corre en Docker en el MISMO host (`localhost:5678`, confirmado por contexto del owner), `/api/intake` puede seguir bindeado a `127.0.0.1` (sin necesitar `--lan`), con su propio bearer token via `Authorization: Bearer <token>` + `compare_digest` (mismo patrón anti-timing-attack que ya usa `_authenticate_request`). Esto evita exponer el intake a la LAN — reduce superficie vs. reusar el puerto `--lan`.

**Auditoría:** cada intake debe auditar `actor_type=SYSTEM, actor_id="n8n"` (no `"owner"`) para que la traza distinga claramente "esto lo disparó una automatización" de "esto lo pidió el owner" — importante para el Riesgo ya documentado en el roadmap ("Sobre-automatización (n8n confirmando)").

### Pattern (f): Capacitor como WebView que navega al bridge existente, no un cliente API separado

**What:** El APK NO reimplementa el consumo de `/api/*` en Kotlin/Java ni hace fetch cross-origin desde un bundle local — **navega el WebView al origin real del bridge** (`https://<ip-lan>:<port>/?token=...`), exactamente como el browser del teléfono hoy. Esto es la única opción consistente con el modelo de seguridad existente: `bootstrap/web.py` valida `Origin`/`Sec-Fetch-Site`/`Host` asumiendo que el cliente ES el mismo origin servido (`docs/mobile/WYSS_MOBILE_BRIDGE_MVP.md` — el caso ya documentado de `Origin: null` + `Sec-Fetch-Site: same-origin` en Chrome Android). Si el bundle de Capacitor sirviera el HTML desde `capacitor://localhost` y llamara a la API en otro origin, HABRÍA que abrir CORS cross-origin en el bridge — exactamente lo que el modelo actual evita a propósito.

**Flujo runtime:**
1. Primer arranque: el WebView carga un mini-bundle propio (`capacitor://localhost/pairing.html`, dentro de `web/src/pairing/`) con un scanner QR (`@capacitor/camera` + una lib de decode, o el plugin comunitario `capacitor-mlkit/barcode-scanning`).
2. El QR, generado en el PC (ver abajo), decodifica a la MISMA URL de pairing que hoy se imprime en la CLI (`https://<ip-lan>:<port>/?token=<token>`) — nada nuevo que inventar en el payload.
3. La app guarda esa URL con `@capacitor/preferences` y hace `window.location.replace(url)` — el WebView pasa a vivir en el origin del bridge, cookie HttpOnly se setea igual que en browser.
4. Reinicios posteriores: si hay URL guardada, se navega directo ahí (mismo trade-off que el browser: si el server reinició o cambió de IP, falla y hay que re-escanear).

**Quién genera el QR — recomendación:** en el PC, NO agregar un endpoint HTTP para servir el QR (aumentaría superficie de red por una conveniencia). Generarlo en la CLI (`wyss web --lan --tls` ya imprime la URL — agregar el QR como ASCII art en la misma terminal, con una lib pura-Python tipo `qrcode`) o, si se quiere algo visual, abrirlo como imagen local (`xdg-open` a un PNG temporal, mismo patrón que ya usa `borjes-toggle` para lanzar apps de escritorio con rutas fijas). El contenido del QR es el secreto (la URL con token) — tratar su generación con la misma disciplina que loggear el token: nunca en logs, nunca en un endpoint no autenticado.

**Cert self-signed en Android WebView — el gotcha real (MEDIUM confidence, verificado por WebSearch):** a diferencia de Chrome-navegador (que hoy muestra "Avanzado > Continuar" y el owner ya lo acepta una vez), **el WebView de Android NO tiene ese diálogo interactivo** — falla el load con `net::ERR_CERT_AUTHORITY_INVALID` sin opción de bypass del usuario. Dos caminos, en orden de robustez:
1. **Recomendado — pinning por fingerprint (TOFU real, no bypass ciego):** un plugin Capacitor nativo pequeño (Kotlin) que overridea `WebViewClient.onReceivedSslError` y llama `handler.proceed()` SOLO si el SHA-256 del cert presentado coincide con el fingerprint capturado durante el pairing (el mismo que ya imprime `bootstrap/tls.py::fingerprint_sha256` — se puede transportar en el QR junto a la URL, o pedirlo la primera vez). Esto es más seguro que un `proceed()` incondicional (que sería un agujero MITM real, no aceptable dado que el propio `SECURITY_MODEL.md` ya trata el cert self-signed como TOFU con verificación de huella).
2. **Alternativa más simple pero menos confiable — `network_security_config.xml` con `<certificates src="user"/>`:** confía en CAs instaladas por el usuario (ej. la CA raíz de `mkcert` instalada manualmente en el teléfono). Riesgo documentado (WebSearch, MEDIUM confidence): hay reportes de que WebView NO siempre honra una user CA de la misma forma que Chrome-app, incluso con esta config — recomendar esto como fallback/documentación para quien instale `mkcert`, no como el mecanismo principal.

**Server URL runtime config:** nunca hardcodear la IP LAN en `capacitor.config.ts` (`server.url` estático) — se rompe con cada cambio de DHCP y obliga a recompilar el APK. La URL vive en `@capacitor/preferences`, re-pareable por QR sin rebuild.

## Data Flow

### Scheduler → PendingStore (rutina genérica)

```
RoutineScheduler.tick() [cada N s, dentro del loop del daemon]
    ↓ (rutina vencida)
plan_builder(routine) → Plan (task_id="routine-<id>-<ts>", steps=(...))
    ↓
CognitivePolicyEngine.evaluate(plan) → PolicyDecision
    ↓
dispatch(plan, decision, pending_store, audit)
    ├─ A → ejecuta directo (PlanRunner.run) → audit
    └─ B/C → PendingStore.save() → aparece en Bandeja (SPA/APK) → owner confirma
             → daemon._confirm() [YA EXISTENTE, re-evalúa antes de ejecutar]
```

### Daily Assistant (solo lecturas + advisory)

```
scheduler dispara "daily_assistant" (cron 08:00)
    ↓ (plan_builder especial: no arma Actions mutadoras)
knowledge.query(...) + ledger.balance(...) + memory.recall(...) + pending_store.load_pending()
    ↓ (todo nivel A, SQL determinista para números)
gateway.ask(AgentModelRequest)  — SOLO para redactar texto, jamás calcular
    ↓
audit.log(AuditEventType.DIGEST_GENERATED, payload={"text": ..., "sources": [...]})
    ↓
GET /api/digest/today (bridge) → SPA/APK renderiza el último digest
```

### Intake n8n → misma bandeja que el owner

```
n8n workflow (webhook externo) → POST /api/intake  {"instruction": "..."}
    Authorization: Bearer <n8n_service_token>   (≠ cookie del owner)
    ↓
bootstrap/web.py valida bearer token (compare_digest) — actor_type=SYSTEM, actor_id="n8n"
    ↓ (mismo RPC "ask" del daemon)
classify_intent → draft_plan → policy.evaluate → dispatch
    ├─ A → ejecuta (poco frecuente para intake automático — revisar qué action types se permiten desde n8n)
    └─ B/C → PendingStore — el owner confirma desde CUALQUIER cliente (web/APK), n8n nunca ve /api/confirm
```

### Capacitor pairing

```
PC: wyss web --lan --tls  → imprime URL + fingerprint + QR (ASCII o PNG local)
    ↓
APK (1ª vez): pairing.html (capacitor://) → scan QR → decodifica URL(+fingerprint)
    ↓
Preferences.set("bridge_url", url) + Preferences.set("cert_fingerprint", fp)
    ↓
window.location.replace(url)  → WebView navega al origin real del bridge
    ↓ (TLS handshake)
onReceivedSslError → compara fingerprint presentado vs guardado → proceed() solo si matchea
    ↓
GET /?token=... → 302 + cookie HttpOnly (MISMO flujo que browser) → SPA normal
```

## Anti-Patterns

### Anti-Pattern 1: Meter el scheduler en un proceso/systemd-timer separado que llama `wyss ask` por CLI

**What people do:** correr `systemd --user timer` que dispara `wyss ask "rutina X"` como subproceso periódico, evitando tocar el daemon.
**Why it's wrong:** duplica el ciclo de vida (dos procesos que pueden desincronizarse), y sobre todo **cada invocación de `wyss ask` abriría su PROPIA conexión a `pending_store.db`** — WAL soporta múltiples lectores pero la app está diseñada asumiendo un único proceso dueño del daemon (ver comentario `busy_timeout=5000` en `pending_store.py`: pensado para contención dentro del MISMO proceso, no como estrategia de multi-proceso). Además reintroduce el riesgo de auto-ejecución si alguien arma el timer con `--yes`/flags de bypass.
**Do this instead:** `scheduler_task` dentro del daemon, mismo loop asyncio, mismas instancias de `PendingStore`/`CognitivePolicyEngine` inyectadas.

### Anti-Pattern 2: Reusar `execution/journal.py` (UndoJournal) para Notion o Memory

**What people do:** por consistencia, intentar que `NotionTool`/`MemoryTool` registren entradas en el mismo `undo_entries` que usa `file.*`.
**Why it's wrong:** `execution/` es una capa independiente por import-linter — `notion/`/`memory/` NO pueden importarla sin violar el contrato de independencia. Además Notion y Memory no comparten el modelo de "inversa" de filesystem (backup de bytes, trash de OS): Notion tiene su propio archive/trash nativo vía API, Memory es una fila SQLite trivialmente re-escribible.
**Do this instead:** cada paquete nuevo maneja su propia reversibilidad con sus propias primitivas (Notion: usar el endpoint de archive de la API en vez de delete; Memory: un `memory.write` que sobreescribe es su propia "inversa" auditada). Si se necesita un contrato compartido de "undo", promoverlo a `core/ports/` como una nueva interfaz — pero NO está justificado para este milestone.

### Anti-Pattern 3: `network_security_config` con confianza ciega (`<certificates src="user"/>` sin más) como ÚNICA defensa

**What people do:** confiar en que instalar la CA de mkcert en el teléfono alcanza, sin pinning de fingerprint.
**Why it's wrong:** un usuario que instala una CA de terceros para hacer funcionar OTRA app queda con esa CA confiada globalmente por el WebView también — es una superficie de confianza más ancha que la que hoy tiene el modelo (fingerprint TOFU explícito, verificado a mano una vez).
**Do this instead:** pinning explícito por fingerprint (Pattern f) como mecanismo primario; `network_security_config` documentado como opción para quien prefiera cero-warnings a costa de una CA de terceros instalada, no como default.

### Anti-Pattern 4: Un endpoint HTTP para servir el QR/URL de pairing

**What people do:** exponer `GET /api/pairing/qr.png` para que "cualquier dispositivo en la LAN lo escanee cómodo".
**Why it's wrong:** el contenido del QR ES el secreto de pairing (la URL con token). Servirlo por HTTP —aunque sea detrás de auth— agrega una ruta más a auditar y un vector nuevo (¿y si ese endpoint queda sin auth por error?) para un problema que ya se resuelve mostrando el QR en la terminal/CLI del propio PC del owner.
**Do this instead:** generar el QR localmente en el proceso de la CLI (misma superficie de confianza que imprimir la URL hoy), nunca por red.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Notion API | `NotionTool` (Tool protocol) en paquete `notion/` nuevo, vía SDK `notion-client` (PyPI, MEDIUM confidence) | Integration token en `.env` (protegido por SecretFilter existente); páginas deben compartirse explícitamente con la integración o la API responde como inexistente |
| n8n (Docker local, `localhost:5678`) | `POST /api/intake` nuevo en `bootstrap/web.py`, bearer token de servicio propio | n8n produce, nunca confirma — sin ruta a `/api/confirm` para ese token |
| APScheduler (nueva dependencia) | `AsyncIOScheduler` integrado al event loop del daemon vía `orchestrator/scheduler.py` | Agregar a `pyproject.toml` — el doc de target architecture asume que ya está pero no lo está |
| Capacitor / Android WebView | WebView navega al origin real del bridge (no cliente API separado) | Requiere plugin nativo pequeño para pinning de fingerprint (self-signed cert) |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `orchestrator/scheduler.py` ↔ `orchestrator/pending_store.py` + `core/policy` | Llamada directa (mismo proceso, mismo import ya permitido) | Reusa `dispatch()` tal cual, cero API nueva |
| `execution/executor.py` ↔ `notion/`, `memory/` | Duck-typed vía `Tool` protocol (mismo mecanismo que file/shell/git) | El executor NO importa `notion`/`memory` directamente en su lógica de negocio — recibe instancias ya construidas por `bootstrap` (composition root) igual que hoy con `FileSystemAdapter` |
| `bootstrap/web.py` ↔ `orchestrator/daemon.py` | JSON-RPC sobre Unix socket, MISMO método "ask" reusado para `/api/intake` | El bridge no gana un segundo protocolo, solo una ruta HTTP más con auth distinta |
| APK (`android/`) ↔ bridge | HTTPS directo al mismo origin que el browser del teléfono | Cero cambios de backend; el "contrato nuevo" es 100% del lado cliente (pairing, pinning) |

## Build Order Sugerido

1. **Scheduler** (`orchestrator/scheduler.py` + `AsyncIOScheduler` + campo `scheduler_task` en `RunningDaemon`) — usando SOLO action types existentes (ej. una rutina de recordatorio con `file.read`) para validar el patrón daemon-task + `dispatch()` sin todavía necesitar Notion/Memory. Es la pieza fundacional: todo lo demás que "corre solo" depende de esto.
2. **Notion adapter** — nuevo `action.type` + `Tool`, capa independiente nueva. Se valida en aislamiento (CLI/ask manual) antes de que el scheduler o el Daily Assistant lo consuman.
3. **Memory (owner)** — port + store + `memory.write` gateado. También se valida en aislamiento.
4. **Daily Assistant** — primera rutina REAL del scheduler, compone knowledge+ledger+memory(+notion si aplica). Depende de 1-3 ya construidos; es el punto de integración que las ejercita juntas.
5. **Intake n8n** — endpoint nuevo en el bridge; no depende de 1-4, pero conviene hacerlo después de validar que el patrón "productor externo de Plan → dispatch()" funciona con el scheduler (mismo camino, distinto disparador) — reduce el riesgo de descubrir un problema de concurrencia/auth en dos lugares a la vez.
6. **Web PC pulida** — el glow-up de la SPA debe cubrir TODAS las superficies nuevas (digest, estado de Notion, bandeja con rutinas) — hacerlo antes dejaría fuera lo que se construye en 1-5.
7. **APK Capacitor** — último, porque envuelve la SPA ya estable y no debería haber más cambios de auth/rutas después de este punto (pairing + pinning se construyen contra un contrato de bridge que ya no se mueve).

**Nota:** el roadmap existente (`WYSS_MASTER_ARCHITECTURE_AND_ROADMAP.md` §11) lista PR-15 Scheduler · PR-16 Notion · PR-17 Daily Assistant · PR-12 Memory · PR-13 Intake sin orden estricto declarado (misma fila de tabla). El orden acá propuesto (Scheduler → Notion → Memory → Daily Assistant → Intake → Web → APK) es una recomendación de dependencias reales, no una contradicción del roadmap.

## Sources

- Lectura directa del repo (HIGH): `src/orchestrator/daemon.py`, `dispatcher.py`, `pending_store.py`, `ttl_reaper.py`; `src/core/policy/engine.py`, `builtin_deny.py`; `src/core/ports/execution.py`, `agent.py`, `orchestrator.py`, `knowledge.py`, `gateway.py`; `src/agents/memory.py`, `registry.py`, `configured_agent.py`; `src/bootstrap/web.py`, `tls.py`; `src/execution/executor.py`, `filesystem.py`; `pyproject.toml`; `web/package.json`, `web/vite.config.ts`
- `docs/architecture/WYSS_MASTER_ARCHITECTURE_AND_ROADMAP.md` (HIGH — doc de arquitectura shippeada del propio repo)
- `docs/architecture/WYSS_TARGET_ARCHITECTURE.md` (HIGH — decisiones ya tomadas por el owner sobre memoria/scheduler)
- `docs/security/SECURITY_MODEL.md` (HIGH — modelo de niveles, denylist, huecos conocidos incluyendo `net.*`)
- `docs/mobile/WYSS_MOBILE_BRIDGE_MVP.md` (HIGH — modelo de pairing/TLS ya implementado y smoke-testeado)
- WebSearch: APScheduler `AsyncIOScheduler` (MEDIUM — confirma que 3.11.x es estable y corre en el mismo loop, sin fecha 2026 específica) — https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html
- WebSearch: Android WebView self-signed cert / `onReceivedSslError` / `network_security_config` (MEDIUM — confirma que WebView no tiene el diálogo interactivo de Chrome y que la user-CA config tiene inconsistencias reportadas) — https://sslinsights.com/how-to-handle-self-signed-certificates-in-android-webview/, https://github.com/react-native-webview/react-native-webview/issues/2147
- Context7 `notion-client`/SDKs oficiales: no se encontró un match exacto del paquete Python `notion-client` en el índice consultado — la referencia al SDK oficial y su modelo de auth/compartir-página queda en MEDIUM confidence (conocimiento de entrenamiento + consistente con nota operativa propia del owner sobre otra integración Notion en este mismo entorno)

---
*Architecture research for: integración de features v1.0 en Wyss (arquitectura hexagonal existente)*
*Researched: 2026-07-10*
