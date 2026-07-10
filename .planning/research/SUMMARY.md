# Project Research Summary

**Project:** Wyss v1.0
**Domain:** Local-first personal operational AI agent (single-owner, LAN-bound, human-gated execution)
**Researched:** 2026-07-10
**Confidence:** HIGH (architecture + bridge auth directly read from codebase); MEDIUM (Capacitor/Notion/n8n integration patterns, verified against official docs)

## Executive Summary

Wyss v1.0 es una expansión controlada del daemon hexagonal existente — agregando seis features estrictamente acotados (Routine Scheduler, adapter Notion, Memory persistente, Daily Assistant, cliente APK móvil, intake webhook n8n) **sin introducir un segundo camino de ejecución**. La investigación confirma que las seis features se mapean limpias sobre patrones arquitectónicos existentes: Scheduler y Daily Assistant son tareas asyncio dentro del loop del daemon; Notion y Memory son adapters Tool o puertos nuevos que fluyen a través del mismo gate `CognitivePolicyEngine` que las acciones manuales; n8n es un nuevo endpoint con su propio bearer token (no un problema de reutilización de cookies); Capacitor es un WebView apuntando al bridge existente (no un cliente API separado).

El enfoque recomendado es **fases ordenadas por dependencia** (Scheduler → Notion → Memory → Daily Assistant → Intake n8n → Web polish → APK) porque cada una depende de infraestructura anterior ya construida o probada estable. El stack es conservador y maduro: Capacitor 7 (SDK 35, exactamente acoplado al entorno actual), APScheduler 3.11 (no la alpha v4), notion-client 3.1 (SDK oficial, AsyncClient), todo sin dependencias externas más allá de lo que está shipping. El riesgo se concentra en tres áreas: (1) la regeneración del cert TLS auto-firmado en cambios de IP de LAN requiere fingerprint pinning TOFU a nivel app (no el enfoque static-XML de Android), (2) el scheduler debe anclarse a wall-clock time, no sleep relativo (o usar APScheduler's drift-handling), (3) la memoria escrita por adapters no confiables (Notion/n8n) debe ser trust-tiered para prevenir prompt-injection laundering en planes futuros.

## Key Findings

### Recommended Stack

**Core technologies:**
- **Capacitor 7.6.7** — Envuelve SPA React en un WebView Android. Elegido por match exacto con SDK 35 (proyecto ya instalado), compatibilidad con auth de bridge existente (same-origin via `server.url`), y madurez (v8 agrega fricción de SDK 36 sin beneficio para v1.0).
- **APScheduler 3.11.3** — Motor de routine scheduler, variante `AsyncIOScheduler` se integra al loop de eventos del daemon sin threads. Elegido sobre v4.0 alpha (sin garantía de release estable) y sobre DIY `while True: sleep(...)` (que drifta y no puede expresar cron). Provee persistencia de jobs, misfire handling, y expresiones cron.
- **notion-client 3.1.0** — SDK oficial Python (ramnes/notion-sdk-py), async-native via `AsyncClient`, retry/backoff automático en 429 y 5xx.
- **@capacitor-mlkit/barcode-scanning** — QR decoder para pairing flow. Pairing es evento raro one-time; ML Kit nativo agrega robustez sin preocupación de bloat para una app LAN-only.

**Stack Confidence:** HIGH.

### Expected Features

**Must have:**
- **Routine Scheduler** — Fire tasks en schedule (cron-like), proposals van por la misma bandeja + CONFIRMAR gate que acciones manuales. Sin auto-execution; MULTI-02 inviolable.
- **Notion adapter** — Read pages/databases; writes clasificados por riesgo (A read, B/C edits). Extender base_levels para `notion.*` (sin entrada explícita, todo cae fail-closed a C).
- **Persistent Memory (owner)** — Structured fact store editable por el owner, trust-tiered (owner-stated vs ingested-external), consumido por Daily Assistant.
- **Daily Assistant** — Rutina programada (08:00) que compone digest estructurado (agenda + Pellegrini + bandeja pendiente + fallas de rutinas); puramente advisory (nivel A, sin writes).
- **Mobile APK** — QR pairing (encodea URL del bridge + fingerprint del cert), WebView navegando al bridge (same-origin, cookie HttpOnly), CONFIRMAR desde el teléfono.
- **Intake n8n** — `POST /api/intake` con bearer token dedicado (no cookie), propuestas de workflows n8n rutean por el mismo CognitivePolicyEngine + bandeja.

**Defer to v1.x/v2+:**
- Push notifications background (LAN-only sin cloud relay — tensión de diseño abierta)
- Notion bidirectional sync (no resuelto ni en integraciones comerciales maduras)
- Acceso remoto fuera de LAN

### Architecture Approach

Dos patrones existentes cubren todo:
1. **"New producer of Plan, same dispatch()"** — Scheduler, Daily Assistant, Intake n8n: construyen un `Plan` y llaman el `dispatch()` existente (B/C → PendingStore, A directo). Scheduler corre como `asyncio.create_task` junto al `ttl_reaper`.
2. **"New Action type + Tool adapter"** — Notion (`notion/` package) y Memory (`memory/` package + `core/ports/memory.py`): implementan el protocol `Tool`, se registran en el executor por prefijo, gateados por política.

**Capacitor APK** NO reimplementa el cliente API: navega el WebView al origin real del bridge vía `server.url` (mismo modelo single-origin del browser, mismo cookie jar, mismos checks de Origin). Sin cross-origin fetch, sin aflojar CORS.

### Critical Pitfalls (Top 5)

1. **Capacitor bundled-asset origin collision** — bundle local presenta `Origin: https://localhost` que YA está en la allowlist del bridge (pensada para el loopback del PC). Prevention: siempre `server.url` a `https://<lan-ip>:<port>`; test de regresión.
2. **Cert TOFU pinning no es XML estático** — `networkSecurityConfig` se compila en el APK; el cert de Wyss regenera al cambiar la IP LAN. Prevention: `onReceivedSslError` compara SHA-256 contra el fingerprint capturado en pairing (la CLI ya lo imprime); `proceed()` solo si matchea.
3. **Memory poisoning** — contenido de Notion/n8n resumido a memoria y releído como contexto confiable = laundering de prompt-injection. Prevention: memory writes = Action type gateado (≥B), trust tiers separados, diseñar ANTES de los intakes.
4. **Scheduler drift** — copiar el patrón `while True: sleep()` del ttl_reaper drifta y no expresa hora absoluta. Prevention: APScheduler con `misfire_grace_time`/`coalesce` desde el diseño.
5. **n8n auth con cookie model** — clientes headless no tienen cookie-jar semántico. Prevention: endpoint dedicado con bearer token estático propio, rate limit separado; jamás tocar el middleware de cookies existente.

## Implications for Roadmap

### Suggested Phase Structure (7 phases, orden por dependencia)

1. **Routine Scheduler** (foundation — todo lo autónomo depende de esto). Research flag: none.
2. **Notion Adapter** (self-contained; base_levels explícitos para notion.*). Research flag: MEDIUM (paginación/429 testear temprano).
3. **Memory** (owner-level, trust-tiered ANTES de que Notion/n8n escriban). Research flag: MEDIUM (diseño de trust-tiers).
4. **Daily Assistant** (rutina que compone knowledge + ledger + memory). Research flag: none.
5. **Intake n8n** (valida "external producer → plan → dispatch" con bearer token). Research flag: none.
6. **Web SPA Polish** (rutinas, digest, editor de memoria, preview Notion, bandeja mejorada). Research flag: none.
7. **Mobile APK** (Capacitor 7, PairingActivity QR, fingerprint pinning). Research flag: HIGH (spike de cert pinning + schema del QR payload antes de construir).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versiones verificadas contra docs oficiales + Context7; sin alphas. |
| Features | MEDIUM-HIGH | Scope y MVP claros; base_levels de Notion a confirmar en planning de esa fase. |
| Architecture | HIGH | Daemon loop, dispatch, Tool adapter, ports verificados por lectura directa de código. |
| Pitfalls | HIGH | Mitigaciones concretas; falta diseño exacto del QR payload (fase 7). |
| **Overall** | **HIGH** | Sin unknowns bloqueantes. Listo para requirements. |

### Gaps to Address

1. Notion base_levels específicos → planning de la fase Notion.
2. Formato de trust-tier markers de memoria → planning de la fase Memory.
3. Schema del QR pairing payload → research de la fase APK.
4. Catch-up policy post-downtime por rutina → planning de la fase Scheduler.
5. Timezone handling entre máquinas → testing de la fase Scheduler.

---

**Research completed:** 2026-07-10
**Ready for roadmap:** YES
