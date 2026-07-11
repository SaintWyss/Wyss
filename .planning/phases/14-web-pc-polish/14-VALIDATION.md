# Phase 14 — Validation Map (per-task)

Mapa de verificación por task. Cada plan aporta su gate; el smoke final (05) cierra WEB-04.
Builder por task: **claude** = JSX/layout/estética a mano · **codex** = mecánico (endpoints, tipos, tests, gates).

| Plan-Task | Builder | Requirement | Cómo se valida | Gate |
|-----------|---------|-------------|----------------|------|
| 01-1 endpoints web.py | codex | WEB-01/02/03 | rg de las 8 rutas + ast.parse; test_web.py 200/401/503 | `pytest tests/bootstrap/test_web.py` |
| 01-2 api.ts + format.ts | codex | WEB-01/02/03 | `tsc -b --noEmit`; rg de métodos/ helpers | `npx tsc -b` |
| 01-3 tests backend + helpers | codex | WEB-01/02/03 | 8 rutas cubiertas; format.test.ts | `pytest` + `npm run test` |
| 02-1 Rutinas lista | claude | WEB-01 | tsc + oxlint; rg max-w-3xl + helpers | `tsc`/`oxlint` |
| 02-2 Rutinas acciones | claude | WEB-01 | rg deleteRoutine + confirmación inline | `tsc`/`oxlint` |
| 03-1 Digest | claude | WEB-02 | rg whitespace-pre-wrap; `! rg dangerouslySetInnerHTML`; api.digestToday | `tsc`/`oxlint` |
| 03-2 Memoria | claude | WEB-03 | rg editMemory/forgetMemory; sin innerHTML | `tsc`/`oxlint` |
| 04-1 nav shell | claude | WEB-04 | rg grupos + overflow-x-auto + ruteo 3 superficies | `tsc`/`oxlint` |
| 04-2 glow-up | claude | WEB-04 | rg xl:grid-cols-2 (Bandeja) + xl:block Chat; sin innerHTML | `tsc`/`oxlint` |
| 04-3 gates front | codex | WEB-04 | suite completa + bundle | `npm run test/build` + `oxlint` |
| 05-1 smoke visual | owner | WEB-01..04 | recorrido desktop + celu | checkpoint human-verify |

## Notas de verificación

- **Sin testing-library/jsdom** en el repo y **prohibido agregar deps** (regla del owner): la verificación de las superficies visuales se apoya en `tsc -b` (typecheck real), `oxlint`, grep estructural (clases/componentes/breakpoints presentes) y `npm run build`. Los tests unitarios reales cubren la lógica pura (`format.ts`) y el backend (`test_web.py`).
- **Anti-XSS**: gates `! rg dangerouslySetInnerHTML` en Digest, Memoria y Chat (contenido de digest/memoria = dato).
- **Anti-borrado silencioso**: confirmación inline de dos pasos exigida por grep en Rutinas y Memoria.
- **Middleware intacto**: ningún plan toca `local_security_middleware` ni la allowlist; las rutas nuevas heredan la cookie.
