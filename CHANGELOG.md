# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es/1.1.0/).
Versionado semántico.

## [1.0.0] — 2026-07-20

Primera release de la línea v1. Cubre el milestone interno «Producto final — app
móvil + asistente diario» (fases 9–16) sobre la base publicada en `v0.1.0`.

### Añadido

- **Routine Scheduler** (fase 9): rutinas cron/interval con `RoutineStore` SQLite,
  catch-up coalescente y TTL de 24 h. Las rutinas producen propuestas que pasan por
  el gate de política: nada B/C se autoejecuta. CLI `wyss routine`.
- **Notion Adapter** (fase 10): lecturas (`read_page`, `query_database`) como nivel A
  y escrituras (`create_page`, `update_page`) gateadas en nivel C con preview.
  Requiere `NOTION_TOKEN` y páginas compartidas con la integración.
- **Owner Memory** (fase 11): memoria persistente con trust-tiers (`owner` / `external`),
  inyectada al planner como dato delimitado y con test anti prompt-injection.
  CLI `wyss memory list|edit|rm`.
- **Daily Assistant** (fase 12): digest diario de solo lectura (memoria, pendientes,
  finanzas y rutinas), RPC `digest.today`, CLI `wyss digest`. Programación opt-in
  desde `[digest]`.
- **Intake n8n** (fase 13): `POST /api/intake` con bearer dedicado (`data/intake_token`,
  nunca la cookie de pairing), floor de riesgo B forzado, rate limit y opt-in `[intake]`.
- **Web PC polish** (fase 14): sidebar agrupada en desktop y superficies de Rutinas,
  Digest y Memoria; bandeja en grilla; aside de digest en el chat.
- **Cliente Android** (fase 15): APK Capacitor con pairing por QR, pinning TOFU
  fail-closed sobre la huella del certificado y pantalla de pairing sin red propia.
  Endpoint `GET /api/pair` y sección «Parear teléfono» en la SPA.
- **Home Authority Core** (fase 16): ports de autoridad del hogar, RPC Unix idempotente
  con `SO_PEERCRED`, política y auditoría propias; unidad de sistema aislada
  (`wyss.service`) y bridge del panel bajo usuario separado.
- **Home Edge APIs**: reminders, timers, agenda Google Calendar (solo lectura) y
  Spotify, expuestos en `/api/home/*` y `/api/media/*` detrás de un bearer propio
  (`data/home_edge_token`). CLI `wyss reminder|timer|calendar auth|spotify auth`.
- **CI**: pipeline con jobs bloqueantes de Python, web y Android.

### Cambiado

- El paquete pasa de `0.1.0` a `1.0.0`; `web` y el cliente Android quedan alineados
  en la misma versión.
- El núcleo compartido se extrajo al paquete `wyss-core`; Pellegrini vive en su
  propio repositorio y lo consume como dependencia.
- La segunda muralla de ejecución quedó unificada y determinista para todos los
  adapters.
- `docs/RELEASE_STATUS.md` es el estado canónico; los artefactos de planificación
  quedan como historia.

### Corregido

- El RPC `audit` dejó de ser un stub: devuelve consultas acotadas reales.
- La confirmación revalida la política contra el plan fresco y exige la palabra del
  nivel resultante si el riesgo subió.
- `file.delete` calcula la papelera por punto de montaje real, evitando abortos
  falsos con el archivo ya movido.
- El error JSON-RPC del daemon en intake devuelve 502 legible en vez de 500 con traza.
- Drift de pantalla del panel ESP32-S3 mitigado (bounce buffer y PCLK).

### Seguridad

- Nivel D sigue siendo absoluto y no confirmable en ningún path.
- Las fuentes externas (intake, memoria `external`) nunca ejecutan directo: floor B.
- El pinning del cliente Android nunca continúa ante mismatch, tampoco en builds debug.
- Los tokens de bearer viven en archivos propios y jamás se registran en logs.

### Límites conocidos

- `undo` cubre solo operaciones `file.*`; shell y Git no son reversibles.
- Los permisos `0600` no se aplican sobre NTFS/FUSE.
- El modo `deterministic` sigue siendo el default de la plantilla de configuración.
- La distribución del APK usa firma debug del owner; no hay canal de actualización.

## [0.1.0] — 2026-07-10

Ver `docs/releases/`. Bridge web LAN con HTTPS local y pairing, política A–D,
ejecución real con verificación, undo de archivos, auditoría SQLite, indexación
híbrida, gateway de modelos y Pellegrini con ledger.
