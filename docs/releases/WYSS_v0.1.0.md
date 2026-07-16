# Wyss v0.1.0 — Release Notes

> **Documento histórico.** Describe el cierre de v0.1.0 del 10 de julio de 2026. El código actual incorporó después rutinas, Notion, memoria, digest, intake, web PC y APK Android. Ver [`../RELEASE_STATUS.md`](../RELEASE_STATUS.md) para el estado vigente.

**Fecha:** 2026-07-10
**Estado:** primer release estable. Loop completo ask→plan→política→confirmar→ejecutar→auditar verificado E2E, y bridge móvil aprobado en **smoke físico real** (teléfono Android, Chrome, LAN, HTTPS).

Continúa desde `WYSS_v0.1_RC.md`. Todo lo de abajo se agregó/endureció entre el RC y este release.

## Seguridad (PR-08 re-audit)

- **13 reglas deny built-in** (`Final`, la config solo agrega): se sumaron firewall-tamper (ufw/firewalld/nftables/iptables por verbo — leer estado no matchea), rm/rmdir/shred, `rm -rf` recursivo y chmod/chown destructivos.
- **Re-evaluación al confirmar**: la política se corre de nuevo ANTES de validar la palabra; si el riesgo subió, la palabra exigida es la del nivel más alto (`max(stored, fresh)`) y la escalación se explica.
- **PendingStore atómico**: doble-confirm y carreras resueltas con `UPDATE … WHERE status='pending'`; TTL fail-closed.
- **Segunda muralla**: traversal (`../`×N) y symlinks maliciosos bloqueados post-resolución; symlinks de infraestructura (p.ej. `~/Data`→`/mnt/hdd/Data`) permitidos.
- **Shell fail-closed**: pipes peligrosos, `curl|bash`, sudo/systemctl destructivo bloqueados; suite de prompts peligrosos ampliada.

## Capacidades nuevas

- **`wyss undo` (PR-09)**: deshace lo aplicado de una task — orden inverso, dry-run con clasificación de reversibilidad, y el plan inverso pasa por el MISMO engine de política (confirmación al nivel del inverso; D no se bypasea). Solo inversas `file.*`.
- **Lecturas del operador (PR-11)**: `file.read/list/stat` + `git status/log/diff`. Salidas capadas (256 KiB / 500 entradas) y honestas al truncar; leer secretos lo bloquea la segunda muralla; flags de escritura de git (`-o/--output`) bloqueados pre-spawn.
- **HTTPS local + voz (PR-10)**: `wyss web --lan --tls` — cert self-signed EC P-256 auto-generado (openssl, regen si cambia la IP), huella SHA-256 impresa para TOFU, cookie `Secure`, dictado por voz gated a secure context.
- **App web (cierre v0.1)**: PWA instalable (manifest + íconos, "Agregar a pantalla de inicio" → standalone), cookie de auth persistente 30 días, token estable entre reinicios (`data/web_token`, rotable borrándolo).

## Fixes del smoke físico (PR-14)

El re-audit de escritorio no alcanzó: el teléfono real destapó bugs que curl no reproduce.

- **`Origin: null` de Chrome Android** con cert self-signed aceptado en POSTs same-origin → se acepta SOLO junto a `Sec-Fetch-Site: same-origin` (header no forjable desde JS). Sin relajar allowlist ni auth.
- **Rechazos logueados**: el server ahora explica cada 401/403 en su log (sin jamás loguear el token); la SPA muestra los errores de polling en una franja visible.
- **`wyss start` con daemon vivo** = panel accionable, no traceback de 80 líneas.
- **Salidas visibles en la SPA**: las lecturas muestran su contenido en el teléfono (Chat, confirmación inline y Bandeja).
- **Trash por volumen real**: `file.delete` verificaba contra rutas de papelera hardcodeadas → ABORT falso en volúmenes no contemplados (p.ej. tmpfs). Ahora resuelve el punto de montaje real (misma regla XDG que send2trash).
- **`risk_level` en el outcome pending**: la SPA mostraba chip B en propuestas C y salteaba el gate visual de tipear CONFIRMAR (el gate server-side nunca dependió de esto).
- **Detalle honesto**: si la verificación post-paso falla, el ABORT dice qué verificación falló (antes mostraba el mensaje de éxito del execute).

## Verificación

539 tests (unit/integración/seguridad/CLI/web) · mypy strict 0 · ruff 0 · import-linter 2/2 contratos · CI verde en cada commit · smoke físico: pairing + PWA + lectura A con salida + delete C con gate CONFIRMAR, desde teléfono real.

## Límites conocidos en el momento de v0.1.0

- RPC `audit` del daemon devuelve `[]` (stub); `wyss audit` CLI lee la DB directo.
- Sin service worker/offline (cert self-signed lo bloquea; mkcert en el device lo destraba).
- Modo LLM es opt-in y requiere gateway propio arriba; sin config, modo deterministic (demo).
- `wyss undo` no cubre shell/git.
- `chmod 0600` no aplica en mounts NTFS (token/key TLS quedan a merced de los permisos del mount).
