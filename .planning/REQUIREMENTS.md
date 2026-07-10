# Wyss — Requirements (Milestone v1.0 — Producto final)

**Defined:** 2026-07-10 · **Research:** `.planning/research/SUMMARY.md` (confidence HIGH)
**Requirements de v0.1:** ver git history de este archivo + sección Validated de PROJECT.md.

Regla transversal inviolable: **nada B/C se auto-ejecuta** — todo productor de planes (rutinas, intake, agentes) pasa por CognitivePolicyEngine y cae a la bandeja; el owner sella. Nivel D absoluto.

## v1.0 Requirements

### Scheduler / Rutinas (SCHED)

- [ ] **SCHED-01**: Owner puede crear una rutina programada (cron u hora fija) desde CLI o web, con preview legible del schedule antes de guardar
- [ ] **SCHED-02**: Una rutina que dispara genera un Plan que pasa por la política: A ejecuta directo, B/C caen a la bandeja como propuesta — jamás auto-ejecución (cierra MULTI-02)
- [ ] **SCHED-03**: Owner puede listar, pausar, reanudar y borrar rutinas, y ver el último resultado de cada una
- [ ] **SCHED-04**: Tras downtime del daemon, las rutinas perdidas se manejan con política de catch-up explícita (coalesce; jamás doble-fire)
- [ ] **SCHED-05**: Toda ejecución de rutina queda auditada: trigger, plan, decisión de política, resultado

### Notion adapter (NOTION)

- [ ] **NOTION-01**: Owner puede pedir en lenguaje natural leer una página/database de Notion y ver el contenido (nivel A con base_levels explícito para notion.*)
- [ ] **NOTION-02**: Owner puede pedir crear/editar contenido en Notion; el write cae como propuesta B/C con preview del cambio antes de confirmar
- [ ] **NOTION-03**: El adapter respeta rate limits (retry/backoff en 429) y pagina resultados completos
- [ ] **NOTION-04**: El token de Notion vive en config/.env (jamás en repo) y toda llamada queda auditada

### Memoria del owner (MEM)

- [ ] **MEM-01**: Owner puede decirle a wyss que recuerde un hecho/preferencia y persiste (write = acción gateada ≥B)
- [ ] **MEM-02**: Owner puede ver, editar y borrar su memoria — legible, nunca blob opaco
- [ ] **MEM-03**: La memoria distingue trust tiers (owner-stated vs ingested-external); contenido externo jamás se recuerda sin confirmación
- [ ] **MEM-04**: El contenido recordado se inyecta como DATO (no instrucción) en los prompts del planner — anti prompt-injection laundering

### Daily Assistant (DAILY)

- [ ] **DAILY-01**: Owner recibe un digest diario a hora configurable: pendientes de bandeja, snapshot Pellegrini, fallas de rutinas
- [ ] **DAILY-02**: El digest es solo lectura (nivel A) — nunca ejecuta ni propone writes por sí solo
- [ ] **DAILY-03**: Owner puede ver el digest del día en la web y pedirlo on-demand

### Intake n8n (INTAKE)

- [ ] **INTAKE-01**: Un workflow n8n puede postear una propuesta a `POST /api/intake` con bearer token dedicado (nunca la cookie del pairing)
- [ ] **INTAKE-02**: Toda propuesta de intake pasa por la política y cae a la bandeja como B/C — jamás auto-ejecuta
- [ ] **INTAKE-03**: El endpoint tiene rate limit propio y rechaza sin token válido (401 auditado, sin loguear el token)

### Web PC (WEB)

- [ ] **WEB-01**: Owner ve y gestiona rutinas desde la web (lista, estado, pausar/reanudar)
- [ ] **WEB-02**: Owner ve el digest diario en la web
- [ ] **WEB-03**: Owner edita su memoria desde la web
- [ ] **WEB-04**: La UI desktop recibe glow-up cohesivo de página entera (aprovecha pantalla grande, jerarquía clara, sin huecos de layout)

### App móvil Android (APK)

- [ ] **APK-01**: Owner instala un APK en Android que abre wyss como app nativa
- [ ] **APK-02**: Pairing por QR: la web/CLI muestra un QR con URL del bridge + fingerprint del cert; la app lo escanea y queda pareada sin tipear nada
- [ ] **APK-03**: La app confía SOLO en el cert cuya huella vino en el QR (TOFU pinning en onReceivedSslError); cert distinto = bloqueo con aviso, jamás proceed ciego
- [ ] **APK-04**: La app usa el mismo origen del bridge (`server.url`) — sin bundle local, sin aflojar allowlist de Host/Origin ni CORS
- [ ] **APK-05**: Owner puede confirmar propuestas B/C desde la app (paridad funcional con la web, gate CONFIRMAR incluido)
- [ ] **APK-06**: Ante server caído o IP cambiada, la app muestra error accionable y permite re-pairing

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

(La completa el roadmapper.)

| REQ | Phase |
|-----|-------|
| — | — |
