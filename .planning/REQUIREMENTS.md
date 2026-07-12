# Wyss — Requirements (Milestone v1.0 — Producto final)

**Defined:** 2026-07-10 · **Research:** `.planning/research/SUMMARY.md` (confidence HIGH)
**Requirements de v0.1:** ver git history de este archivo + sección Validated de PROJECT.md.

Regla transversal inviolable: **nada B/C se auto-ejecuta** — todo productor de planes (rutinas, intake, agentes) pasa por CognitivePolicyEngine y cae a la bandeja; el owner sella. Nivel D absoluto.

## v1.0 Requirements

### Scheduler / Rutinas (SCHED)

- [x] **SCHED-01**: Owner puede crear una rutina programada (cron u hora fija) desde CLI o web, con preview legible del schedule antes de guardar
- [x] **SCHED-02**: Una rutina que dispara genera un Plan que pasa por la política: A ejecuta directo, B/C caen a la bandeja como propuesta — jamás auto-ejecución (cierra MULTI-02)
- [x] **SCHED-03**: Owner puede listar, pausar, reanudar y borrar rutinas, y ver el último resultado de cada una
- [x] **SCHED-04**: Tras downtime del daemon, las rutinas perdidas se manejan con política de catch-up explícita (coalesce; jamás doble-fire)
- [x] **SCHED-05**: Toda ejecución de rutina queda auditada: trigger, plan, decisión de política, resultado

### Notion adapter (NOTION)

- [x] **NOTION-01**: Owner puede pedir en lenguaje natural leer una página/database de Notion y ver el contenido (nivel A con base_levels explícito para notion.*)
- [x] **NOTION-02**: Owner puede pedir crear/editar contenido en Notion; el write cae como propuesta B/C con preview del cambio antes de confirmar
- [x] **NOTION-03**: El adapter respeta rate limits (retry/backoff en 429) y pagina resultados completos
- [x] **NOTION-04**: El token de Notion vive en config/.env (jamás en repo) y toda llamada queda auditada

### Memoria del owner (MEM)

- [x] **MEM-01**: Owner puede decirle a wyss que recuerde un hecho/preferencia y persiste (write = acción gateada ≥B)
- [x] **MEM-02**: Owner puede ver, editar y borrar su memoria — legible, nunca blob opaco
- [x] **MEM-03**: La memoria distingue trust tiers (owner-stated vs ingested-external); contenido externo jamás se recuerda sin confirmación
- [x] **MEM-04**: El contenido recordado se inyecta como DATO (no instrucción) en los prompts del planner — anti prompt-injection laundering

### Daily Assistant (DAILY)

- [x] **DAILY-01**: Owner recibe un digest diario a hora configurable: pendientes de bandeja, snapshot Pellegrini, fallas de rutinas
- [x] **DAILY-02**: El digest es solo lectura (nivel A) — nunca ejecuta ni propone writes por sí solo
- [x] **DAILY-03**: Owner puede ver el digest del día en la web y pedirlo on-demand

### Intake n8n (INTAKE)

- [x] **INTAKE-01**: Un workflow n8n puede postear una propuesta a `POST /api/intake` con bearer token dedicado (nunca la cookie del pairing)
- [x] **INTAKE-02**: Toda propuesta de intake pasa por la política y cae a la bandeja como B/C — jamás auto-ejecuta
- [x] **INTAKE-03**: El endpoint tiene rate limit propio y rechaza sin token válido (401 auditado, sin loguear el token)

### Web PC (WEB)

- [x] **WEB-01**: Owner ve y gestiona rutinas desde la web (lista, estado, pausar/reanudar)
- [x] **WEB-02**: Owner ve el digest diario en la web
- [x] **WEB-03**: Owner edita su memoria desde la web
- [x] **WEB-04**: La UI desktop recibe glow-up cohesivo de página entera (aprovecha pantalla grande, jerarquía clara, sin huecos de layout)

### App móvil Android (APK)

- [x] **APK-01**: Owner instala un APK en Android que abre wyss como app nativa
- [x] **APK-02**: Pairing por QR: la web/CLI muestra un QR con URL del bridge + fingerprint del cert; la app lo escanea y queda pareada sin tipear nada
- [x] **APK-03**: La app confía SOLO en el cert cuya huella vino en el QR (TOFU pinning en onReceivedSslError); cert distinto = bloqueo con aviso, jamás proceed ciego
- [x] **APK-04**: La app usa el mismo origen del bridge (`server.url`) — sin bundle local, sin aflojar allowlist de Host/Origin ni CORS
- [x] **APK-05**: Owner puede confirmar propuestas B/C desde la app (paridad funcional con la web, gate CONFIRMAR incluido)
- [x] **APK-06**: Ante server caído o IP cambiada, la app muestra error accionable y permite re-pairing

## Future Requirements (diferidas — decisión owner 2026-07-10)

- **PUSH-01**: Notificaciones push con la app cerrada (requiere decidir FCM/cloud relay vs foreground-only — tensión con local-first)
- **REMOTE-01**: Acceso remoto fuera de LAN (VPN/túnel; cambia modelo de cert y auth)
- **NSYNC-01**: Notion sync bidireccional automático (no resuelto ni en integraciones comerciales; read+write confirmado alcanza)
- TEAM-01/02: modo equipo (vieja fase 10)

## Out of Scope

- Auto-ejecución de B/C por cualquier productor (violaría el modelo de confianza)
- App iOS (owner usa Android; sin hardware de build Apple)
- Play Store (distribución sideload personal)
- Multi-usuario / multiempresa

## Traceability

Mapeado por el roadmapper 2026-07-10 · 25/25 requirements v1.0 cubiertos (sin orphans, sin duplicados).

| REQ | Phase | Status |
|-----|-------|--------|
| SCHED-01 | Phase 9 — Routine Scheduler | Complete |
| SCHED-02 | Phase 9 — Routine Scheduler | Complete |
| SCHED-03 | Phase 9 — Routine Scheduler | Complete |
| SCHED-04 | Phase 9 — Routine Scheduler | Complete |
| SCHED-05 | Phase 9 — Routine Scheduler | Complete |
| NOTION-01 | Phase 10 — Notion Adapter | Complete |
| NOTION-02 | Phase 10 — Notion Adapter | Complete |
| NOTION-03 | Phase 10 — Notion Adapter | Complete |
| NOTION-04 | Phase 10 — Notion Adapter | Complete |
| MEM-01 | Phase 11 — Owner Memory | Complete |
| MEM-02 | Phase 11 — Owner Memory | Complete |
| MEM-03 | Phase 11 — Owner Memory | Complete |
| MEM-04 | Phase 11 — Owner Memory | Complete |
| DAILY-01 | Phase 12 — Daily Assistant | Complete |
| DAILY-02 | Phase 12 — Daily Assistant | Complete |
| DAILY-03 | Phase 12 — Daily Assistant | Complete |
| INTAKE-01 | Phase 13 — Intake n8n | Complete |
| INTAKE-02 | Phase 13 — Intake n8n | Complete |
| INTAKE-03 | Phase 13 — Intake n8n | Complete |
| WEB-01 | Phase 14 — Web PC Polish | Complete |
| WEB-02 | Phase 14 — Web PC Polish | Complete |
| WEB-03 | Phase 14 — Web PC Polish | Complete |
| WEB-04 | Phase 14 — Web PC Polish | Complete |
| APK-01 | Phase 15 — Mobile APK | Complete |
| APK-02 | Phase 15 — Mobile APK | Complete |
| APK-03 | Phase 15 — Mobile APK | Complete |
| APK-04 | Phase 15 — Mobile APK | Complete |
| APK-05 | Phase 15 — Mobile APK | Complete |
| APK-06 | Phase 15 — Mobile APK | Complete |
