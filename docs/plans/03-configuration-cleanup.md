# PR-03 — Configuration cleanup

## 1. Objective
Config honesta y operable: sin dependencias muertas, con `.env` real presente (valores los pone el owner) y documentación de qué servicio provee cada key.

## 2. Context from the audit
- `fastmcp>=2.14` y `mcp>=1.27` declaradas en `pyproject.toml` con **cero imports** en src/tests/scripts (grep verificado) — huérfanas del plan 05-05 (Hermes/MCP) bloqueado.
- `config/.env` no existe (STATE.md 08-04 lo lista como bloqueante de la calibración advisory); `config/.env.example` sí.
- LiteLLM :4000 está down en Santiago-PC (perf-tuning) — el provider `litellm` no tiene endpoint.

## 3. Exact problem
Deps instalan superficie MCP sin consumidor (uv sync más lento, lockfile más grande, señal falsa para ejecutores: "acá hay MCP"). Sin `.env`, providers reales inoperables: toda la evidencia E2E con LLM es de fakes.

## 4. Architectural decision
Ninguna dependencia vive en pyproject sin consumidor en `src/`. Cuando 05-05 (Hermes/MCP) se desbloquee, sus deps vuelven EN ese PR. Secretos: solo en `config/.env` (gitignored), jamás en TOML ni en el repo — regla existente, se reafirma.

## 5. Files to read first
- `pyproject.toml` (sección dependencies)
- `config/.env.example` y `config/config.example.toml` (cabecera: reglas de secretos)
- `src/gateway/providers/litellm.py`, `anthropic.py`, `ollama.py` (qué env vars esperan)
- `src/bootstrap/config.py` (cómo se cargan)

## 6. Files allowed to modify
- `pyproject.toml` (SOLO quitar las dos líneas de deps) + `uv.lock` (regenerado por `uv sync`)
- `config/.env.example` (si falta documentar alguna key que los providers leen)

## 7. Files forbidden to modify
- `src/` completo (en particular los protegidos D-85), `tests/`, `.planning/`
- `config/config.toml` (config personal del owner)
- PROHIBIDO crear `config/.env` con valores: el ejecutor deja instrucciones; las keys las pone el owner a mano.

## 8. Required changes
1. Quitar `fastmcp>=2.14,<3` y `mcp>=1.27,<2` de `[project].dependencies`.
2. `uv sync` para regenerar `uv.lock`.
3. Verificar con grep que ninguna key leída por los providers falta en `config/.env.example`; agregar las que falten con placeholder y comentario de qué servicio la provee.
4. Dejar en el SUMMARY la lista exacta de keys que el owner debe completar a mano en `config/.env`.

## 9. Contracts and invariants
- `uv run python -c "import core, gateway, knowledge, execution, agents, orchestrator, audit, ledger, bootstrap"` sigue funcionando.
- Ningún secreto ni valor real entra al repo.
- El comentario de cabecera de `config.example.toml` ("NUNCA poner secretos aquí") permanece.

## 10. Tests required
```bash
uv sync && uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports
grep -rn "fastmcp\|^import mcp\|^from mcp" src tests   # debe dar vacío
```

## 11. Manual verification
Owner: copiar `.env.example` → `config/.env`, completar keys, levantar LiteLLM (`~/Data/10_Workspace/tools/litellm-local`, localhost:4000) y correr `wyss status` — debe reportar provider alcanzable.

## 12. Risks
Que algo importe mcp de forma dinámica no detectada por grep. Mitigación: la suite completa post-`uv sync` lo detectaría (424 tests importan todo el árbol).

## 13. Rollback plan
`git revert` + `uv sync` restaura el lockfile anterior.

## 14. Acceptance criteria
- pyproject sin fastmcp/mcp; lockfile regenerado; cadena verde.
- `.env.example` cubre todas las keys que los providers leen.
- SUMMARY lista las keys pendientes de completar por el owner.

## 15. Executor prompt for cheaper AI
```
Proyecto: Wyss. Root: /mnt/hdd/Data/10_Workspace/projects/wyss. Python 3.12 + uv. NO commitees.
NUNCA escribas valores de secretos ni crees config/.env — solo tocás pyproject.toml y config/.env.example.

1. En pyproject.toml [project].dependencies borra exactamente dos entradas: "fastmcp>=2.14,<3" y
   "mcp>=1.27,<2". Nada más de esa lista.
2. Corre: uv sync
3. Lee src/gateway/providers/litellm.py, anthropic.py y ollama.py y src/bootstrap/config.py; lista
   qué variables de entorno/keys esperan. Compara contra config/.env.example: si falta alguna,
   agrégala con placeholder (ej: ANTHROPIC_API_KEY=") y un comentario de una línea (qué servicio).
4. Verifica: uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports
   y grep -rn "fastmcp" src tests (vacío) y grep -rnE "^(import|from) mcp" src tests (vacío).
Reporta SUMMARY: diff de pyproject, keys agregadas al example, keys que el owner debe completar a mano,
resultado exacto de cada verificación.
```
