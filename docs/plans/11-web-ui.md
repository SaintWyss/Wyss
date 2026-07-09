# PR-11 — UX Web: `wyss web` + SPA "mesa de despacho"

**Estado:** Sección 1 (bridge) hecha en `9de262d`. Secciones 2-4 aprobadas por el owner 2026-07-03.
**Rama:** `feature/web-ui`.

## Decisión de arquitectura (Sección 1 — hecha)

Opción A: `wyss web` como proceso separado en bootstrap (hermano de la CLI), nunca dentro del daemon.

- `src/bootstrap/web.py` — `build_web_app(settings, token=)`: FastAPI servido por uvicorn,
  bind exclusivo `127.0.0.1`.
- REST por DI reusando helpers de `cli.py`: `/api/status`, `/api/search`, `/api/fin/resumen`,
  `/api/fin/transaccion`, `/api/audit`, `/api/pending`.
- `ask`/`confirm` = cliente JSON-RPC del socket Unix del daemon. **La web nunca decide nivel
  de riesgo ni ejecuta** — dispatcher → engine A-D → segunda muralla, idéntico a la CLI.
- Bandeja: lectura read-only del PendingStore; el daemon sigue siendo único escritor.
- Seguridad: token de sesión por arranque (`secrets.token_urlsafe(32)`) entregado una vez por
  URL, cookie `HttpOnly SameSite=Strict`, `compare_digest`, check de Host y Origin contra DNS
  rebinding, sin CORS, auth exigida en TODO path (estáticos incluidos).
- Errores JSON accionables `{"error", "accion"}`, espejo del `_error_panel` de la CLI:
  503 daemon caído, 500 config/integridad, 404 recurso, 422 validación.

## Sección 2 — SPA: identidad y superficies

**Concepto:** mesa de despacho. El owner revisa lo que sus agentes proponen y estampa
decisiones. Documentos, sellos, niveles de riesgo como sistema semántico central.

**Tokens:**

| Token | Valor | Uso |
|---|---|---|
| `tinta` | `#101917` | fondo (verde-negro profundo) |
| `papel` | `#1A2422` | superficie de cards |
| `hueso` | `#E8E4D8` | texto principal |
| `celeste` | `#86B9D6` | acento de marca: links, acciones, foco |
| riesgo A | `#5FA97C` | semántico, presente en toda la app |
| riesgo B | `#C9A227` | |
| riesgo C | `#D07A3F` | |
| riesgo D | `#B0413E` | |

**Tipografía** (bundled vía fontsource, cero CDN): Archivo Expanded (display; Omnibus-Type,
Buenos Aires) · Archivo (UI/body) · IBM Plex Mono (ids, montos, audit, paths — todo lo trazable).

**Layout:** sidebar fina fija (Chat, Bandeja, Buscar, Finanzas, Auditoría) + strip de estado
(daemon vivo/caído, frescura índice). Navegación por hash, sin router lib. Badge numérico en
Bandeja (polling 5s).

**Firma — el sello:** cada plan propuesto es un documento: card papel, acciones numeradas
(orden real de ejecución), chip de riesgo A-D. Aprobar/rechazar estampa un sello (APROBADO
celeste / RECHAZADO rojo, rotación leve, golpe corto con gsap). Nivel C exige tipear
`CONFIRMAR` dentro de la card.

**Superficies:**

1. **Chat** (home): historial de sesión en memoria del browser (v1 sin persistencia), input
   abajo. Plan en respuesta → documento embebido con sello inline. Orquestador degradado →
   aviso sutil.
2. **Bandeja:** pendientes como documentos, countdown TTL en mono, vacío accionable.
3. **Buscar:** input grande + chips de BC (desde `/api/status`), snippet + path mono + score,
   banner ámbar si degradado a FTS-only, footer de frescura.
4. **Finanzas:** fila KPI (ingresos/gastos/superávit del período, superávit en color
   semántico), barras por categoría, alta rápida inline, período seleccionable.
5. **Auditoría:** timeline mono, filtro por tipo de evento y `--since`.

**Stack:** React + Vite + TS + Tailwind v4 en `web/`; build → `src/bootstrap/webui_dist/`.
Node solo dev. Estado: fetch + hooks propios, sin Redux/Query. Motion: gsap
(`prefers-reduced-motion` respetado).

## Sección 3 — Errores y estados

- Daemon caído (503): strip rojo persistente; chat/bandeja deshabilitados con
  "el daemon no está corriendo — levantalo con: wyss start". Search/finanzas/audit siguen.
- 401 (server reiniciado, token nuevo): pantalla completa "Sesión vencida. Volvé a abrir la
  URL que imprime wyss web." Sin retry loop.
- Search degradado: banner ámbar "búsqueda solo texto (FTS5)".
- Empty states en toda superficie: qué está vacío + acción siguiente (patrón PR-07).
- Propuesta expirada al confirmar: card gris "expirada", no error.
- Errores de red: toast con `{error, accion}` del bridge; nunca stacktrace.

## Sección 4 — Testing y proceso

- Frontend: vitest + testing-library solo para lógica no trivial (polling, countdown TTL,
  gate CONFIRMAR, estados). Sin suite exhaustiva de componentes en v1.
- Contrato: los tests Python del bridge son la fuente de verdad del API shape; el front
  espeja tipos a mano en `api.ts` único.
- QA visual: gstack headless contra `wyss web` vivo.
- CI: build de SPA fuera del CI Python en v1; `webui_dist/` buildeado se commitea
  (app local single-owner; si molesta, mover a CI después).
- Proceso: UX/visual a mano por Claude; grunt mecánico delegable a Codex puntualmente.
