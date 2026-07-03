# PR-07 — UX pass de CLI

> **EJECUTADO 2026-07-03** directamente por Claude (desvío al plan de executor: UX = juicio,
> convención del repo; no se delegó a modelo barato). Cadena verde: 446 passed / mypy limpio /
> ruff limpio / 2 contratos KEPT.
>
> **SUMMARY — inventario de salidas (pre-PR) y cambios:**
>
> | Comando | Éxito | Vacío (antes → después) | Fallo (antes → después) |
> |---|---|---|---|
> | `index` | `BC:` + progreso + `Resumen BC` | dry-run: "Nada para indexar." → empty state con hint | ruta inexistente: `Error: <ruta>` críptico a stdout → causa+acción a stderr; ConfigError/Integrity → acción concreta |
> | `start` | daemon corre | — | `Error: {exc}` → causa+acción (config / WAL) |
> | `ask` | panel pending/rechazado/encolado | — | daemon caído ya era accionable; ahora también captura `ConnectionRefusedError` (socket huérfano) |
> | `confirm` | prompt B/C + resultado | — | "Pending no encontrado." → id + dónde obtenerlo; **bug fix**: `typer.Exit` hereda de `RuntimeError` y caía en el except sistémico imprimiendo "Error sistémico: " vacío |
> | `audit` | tabla | tabla con headers sin filas (muda) → empty state; audit.db inexistente creaba db vacía y tiraba `no such table` → empty state exit 0 | acción concreta |
> | `search` | panels / JSON | "Sin resultados." → distingue índice vacío vs sin hits, con hint; footer "indexado al nunca indexado" → "índice sin indexaciones" | kb desconocida EN INGLÉS → español + hint `--bc`; `--json` intocado (test de shape vacío agregado) |
> | `status` | tabla | tabla vacía muda → empty state con hint | acción concreta |
> | `fin add-*` | mensaje verde | — | monto ≤ 0 iba a stdout → stderr causa+acción; errores sistémicos a stderr |
> | `fin ver` | tabla + balance | tabla "(sin gastos)" + $0.00 → empty state con hint (solo si cero transacciones) | acción concreta |
>
> Idioma: "not found/Available/(none)" → español; acentos ("Estimación", "indexación"); "skipped" → "omitidos".
> Helpers agregados: `_error_panel(causa, accion)` (stderr, soft_wrap) y `_empty_state(mensaje, siguiente_comando)`.
> Exit codes verificados: 0 éxito/vacío, 1 operativo, 2 mal uso (test agregado).
> Nota fuera de alcance (dominio, prohibido §7): `fin add-* --fecha` no valida formato ISO — se
> almacena tal cual; candidato a PR posterior si molesta.

## 1. Objective
Que la CLI se sienta UN producto: errores accionables, empty states informativos, idioma y formato Rich consistentes en los 10+ comandos.

## 2. Context from the audit
La CLI es la única superficie de producto (no hay UI web). Comandos: `index, start, ask, confirm, audit, search, status` + `fin add-ingreso/add-gasto/ver` (`src/bootstrap/cli.py`, 35.6K). Crecieron por fases distintas (3, 4, 5, 8) con ejecutores distintos — el audit no verificó consistencia de tono/formato entre ellos y ese es exactamente el tipo de drift que produce el desarrollo por fases.

## 3. Exact problem
Riesgo de experiencia fragmentada: mensajes de error crudos (stack traces o `Error: ...` pelado) cuando falta config/.env, daemon caído, índice vacío; empty states mudos (`fin ver` sin transacciones, `search` sin resultados, `audit` sin eventos); mezcla de español/inglés en help y salidas.

## 4. Architectural decision
Toda salida al owner pasa por helpers Rich compartidos (panel de error con causa+acción, tabla vacía con hint del próximo comando). Los errores de dominio se traducen a mensajes de owner; jamás traceback crudo en operación normal.

## 5. Files to read first
- `src/bootstrap/cli.py` COMPLETO (inventario real de salidas por comando)
- `src/core/domain/errors.py` (taxonomía de errores a traducir)
- Salida real de: `wyss status`, `wyss search x` sin índice, `wyss fin ver` sin datos, `wyss ask` sin daemon, `wyss index` sin config

## 6. Files allowed to modify
- `src/bootstrap/cli.py`
- `tests/cli/` (tests nuevos de salidas)

## 7. Files forbidden to modify
- Todo lo demás. En particular: la LÓGICA de los comandos no cambia — solo presentación/manejo de error. Prohibido tocar `src/core/`, `src/gateway/`, `src/orchestrator/` (salvo cero cambios), protegidos D-85.

## 8. Required changes
1. Inventariar (primera tarea, output al SUMMARY): para cada comando, qué imprime en éxito / vacío / cada modo de fallo. Ese inventario define el trabajo real.
2. Helpers privados en `cli.py`: `_error_panel(causa, accion)` y `_empty_state(mensaje, siguiente_comando)` con Rich.
3. Aplicarlos: daemon caído → "El daemon no está corriendo. Levantalo con: wyss start"; sin config/.env → decir QUÉ falta y DÓNDE; índice vacío en search → sugerir `wyss index`; `fin ver` vacío → sugerir `wyss fin add-ingreso`.
4. Unificar idioma: todo help text y mensaje al owner en español (el repo es en español).
5. Exit codes: 0 éxito, 1 error operativo, 2 mal uso (convención Typer); verificar consistencia.
6. Tests con `typer.testing.CliRunner`: por comando, al menos el caso vacío y un caso de fallo verifican mensaje accionable y exit code (sin frases exactas frágiles: asserts por substring clave).

## 9. Contracts and invariants
- Salida `--json` (D-43, search/status) NO cambia de shape — es contrato para scripts.
- Ningún cambio de comportamiento: mismos efectos, misma semántica de confirmación B/C.

## 10. Tests required
```bash
uv run pytest -q tests/cli/ && uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports
```

## 11. Manual verification
Owner corre los 5 escenarios del §5 (sin daemon, sin .env, sin índice, ledger vacío, audit vacío) y confirma que cada salida dice qué pasó y qué hacer, en español, sin traceback.

## 12. Risks
Cambiar textos rompe tests existentes que asserten salidas → correr suite completa; ajustar asserts a substrings estables.

## 13. Rollback plan
Revert del commit; solo presentación cambió.

## 14. Acceptance criteria
- Inventario de salidas documentado en SUMMARY.
- 5 escenarios de fallo/vacío con mensaje accionable + exit code correcto + test.
- `--json` byte-compatible con antes (test lo cubre).

## 15. Executor prompt for cheaper AI
```
Proyecto: Wyss. Root: /mnt/hdd/Data/10_Workspace/projects/wyss. Python 3.12 + uv. NO commitees.
SOLO podés modificar src/bootstrap/cli.py y tests/cli/. La lógica de los comandos NO cambia — solo
presentación de errores, empty states, idioma (español) y exit codes.

1. Lee src/bootstrap/cli.py completo y src/core/domain/errors.py. Armá inventario: por comando
   (index/start/ask/confirm/audit/search/status/fin add-ingreso/fin add-gasto/fin ver), qué imprime
   en éxito, en vacío y en cada fallo. Incluí el inventario en el SUMMARY.
2. Agregá helpers Rich privados _error_panel(causa, accion) y _empty_state(mensaje, siguiente_comando)
   y aplicalos: daemon caído → sugerir "wyss start"; falta config/.env → decir qué archivo y qué key;
   search sin índice → sugerir "wyss index"; fin ver vacío → sugerir "wyss fin add-ingreso";
   audit vacío → decirlo. Nunca traceback crudo en operación normal.
3. Todo help text y mensaje en español. Exit codes: 0 ok, 1 error operativo, 2 mal uso.
4. REGLA DURA: la salida --json de search y status NO cambia de shape (contrato D-43) — agregá un test
   que lo fije.
5. Tests con typer.testing.CliRunner para cada escenario del punto 2 (asserts por substring, no frase exacta).
Verifica: uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports.
SUMMARY: inventario, cambios por comando, salida exacta de verificaciones.
```
