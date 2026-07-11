# Phase 14 — UI Design Contract (Web PC Polish)

**Autor:** Claude (regla del owner: UX = Claude, Codex solo construcción mecánica)
**Fecha:** 2026-07-11 · **Requirements:** WEB-01..04

## Sistema existente (NO reinventar — extender)

- **Tokens**: `tinta` (fondo), `papel` (cards), `borde`, `humo` (texto secundario), `hueso` (texto), `celeste` (acción/acento), `riesgo-a..d`. Tailwind config existente.
- **Tipografía**: Archivo (display, clase `display`), IBM Plex Mono (datos/ids/metadatos).
- **Componentes**: `RiskChip`, `Sello` (aprobado/rechazado/expirada), `EmptyState`, `ErrorNote`, `Salidas` (pre monospace), `ResultadoEjecucion`. Reusar SIEMPRE antes de crear.
- **Concepto**: "mesa de despacho" — documentos que se sellan. Sobrio, papel/tinta, sin gradientes ni glassmorphism. Density media, espaciado generoso.

## Arquitectura de navegación (WEB-04)

- **Desktop (≥ lg)**: reemplazar la bottom-tab-bar por **sidebar izquierda persistente** (w-56): logo WYSS + estado daemon arriba; grupos: *Operar* (Chat, Bandeja con badge de pendientes), *Automatizar* (Rutinas, Digest), *Saber* (Buscar, Memoria), *Cuentas* (Pellegrini, Auditoría). Item activo: borde izquierdo celeste + texto hueso; inactivo humo. Contenido: `max-w-5xl` centrado con padding lateral — **sin huecos muertos** (regla del owner: glow-up = página entera).
- **Mobile (< lg)**: bottom-tab-bar actual INTACTA (UX ya aprobada en smoke físico; fase 15 la envuelve en APK). Las 3 superficies nuevas entran en una fila scrolleable horizontal de tabs (overflow-x-auto, sin wrap).

## Superficie: Rutinas (WEB-01)

- Lista de cards (patrón Bandeja): header = nombre (display) + `RiskChip`-like chip de estado (`active` celeste / `paused` humo) + schedule en mono (`interval 120s` / `cron 0 8 * * *`).
- Cuerpo: última corrida (`last_fired_at` relativo + `last_outcome` con color: executed=riesgo-a, pending=humo, failed=riesgo-d).
- Acciones por card: Pausar/Reanudar (botón secundario borde) + Borrar (ghost rojo al hover, patrón Rechazar). Sin creación desde la web en v1.0 (CLI) — EmptyState lo dice: "Creá una con: wyss routine add …".
- RPCs: `routine.list/pause/resume/delete` vía endpoints nuevos `/api/routines*` (espejo de /api/pending).

## Superficie: Digest (WEB-02)

- Panel del día: el markdown de `digest.today` renderizado como texto plano estructurado (whitespace-pre-wrap, mono para datos) dentro de un card `papel` grande con header "Digest — {fecha}" + botón "Generar ahora" (celeste).
- El contenido del digest es DATO: render plano, jamás interpretar markdown activo.
- Desktop bonus: en el home (Chat) un mini-card lateral derecho (solo ≥ xl) con el resumen del digest (primeras N líneas) + link a la superficie completa. Si no hay digest/daemon caído: EmptyState.
- Endpoint nuevo `/api/digest/today` → RPC `digest.today`.

## Superficie: Memoria (WEB-03)

- Tabla/lista legible: cada fact = fila con value (hueso), category chip (mono humo), tier badge (`owner` celeste — único hoy), updated_at relativo.
- Acciones: Editar inline (input + guardar/cancelar, patrón gate de Bandeja) y Borrar (confirmación inline simple, no modal).
- Header explica el contrato: "Lo que wyss recuerda de vos. Cada plan nuevo lo recibe como dato."
- EmptyState: 'Decile en el chat: "guardá en tu memoria que…"'.
- Endpoints nuevos `/api/memory*` → RPCs `memory.list/edit/forget`.

## Glow-up desktop (WEB-04) — página entera, no solo lo nuevo

- Chat: en ≥ lg el input y los mensajes aprovechan `max-w-3xl` actual pero el contenedor gana el sidebar; mensajes del owner mantienen alineación derecha.
- Bandeja: en ≥ xl grid de 2 columnas para las cards pendientes (hoy stack single).
- Buscar/Pellegrini/Auditoría: mismo contenedor `max-w-5xl`, headers consistentes (display + subtítulo humo) — auditar que ninguna vista quede con max-w chico flotando en un mar de tinta.
- Transiciones: hover/focus sutiles ya existentes; NADA de animación nueva pesada (gsap solo si una micro-transición del sidebar lo pide — criterio Claude en ejecución).

## Reglas duras de ejecución

1. **División de trabajo**: JSX/layout/estética = **Claude a mano**; api.ts types, endpoints FastAPI, tests, wiring mecánico = Codex.
2. Auth/middleware del bridge NO se toca (los endpoints nuevos son GET/POST con cookie, mismo patrón /api/pending).
3. Los endpoints web de rutinas/memoria son de GESTIÓN del owner (cookie auth) — sin gate de política (espejo del contrato RPC).
4. Light mode: no existe en la SPA (tinta always-dark es identidad) — mantener.
5. Gates front: `npm run test`, `npx oxlint`, `npm run build` (bundle a webui_dist se sirve desde disco sin reiniciar).

## Success criteria observables

1. Desktop ≥ lg muestra sidebar con los 8 destinos agrupados; mobile conserva bottom tabs.
2. /rutinas lista, pausa, reanuda y borra contra el daemon real.
3. /digest muestra el digest del día y lo regenera on-demand.
4. /memoria lista, edita y borra facts reales.
5. Ninguna vista desktop queda como columna angosta perdida (página entera, sin huecos).
