---
phase: 10-notion-adapter
plan: 01
status: complete
completed: 2026-07-10
requirements: [NOTION-01, NOTION-03, NOTION-04]
builder: codex (codex-gsd-exec) — verificado y commiteado por Claude
---

# 10-01 Summary — Package src/notion/

## Qué se hizo

- `src/notion/` (capa nueva independiente, registrada en los contratos import-linter): `client.py` (build con `RetryOptions` del SDK — 429 resuelto), `pagination.py` (query de data_sources COMPLETA antes de devolver; `has_more` sin cursor → falla explícita, jamás parcial silencioso), `markdown.py` (API 2025-09 server-side, cero recursión de blocks), `tool.py` (NotionTool: 4 action types, errores API → ToolResult legible, salida markdown con truncado honesto patrón PR-11).
- GOTCHA del SDK 3.1 aplicado: `databases.retrieve → data_sources[0] → data_sources.query` (grep `databases.query` = 0).
- Higiene de token: NotionTool no guarda el token (vive en el client); jamás en payload/audit/errores — testeado.
- `tests/notion/` (12 tests, respx sin red): read markdown, paginación multi-página, 429→retry→éxito, 404/permiso legible, token nunca en payload.
- notion-client 3.1.0 instalado con OK del owner (pin uv.lock); respx ya era dev-dep.

## Verificación (fuera del sandbox)

**585 passed** (+12) / mypy 0 / ruff 0 / import-linter 2/2 con la capa nueva registrada.

## Deviations

`ClientOptions` se importa de `notion_client.client` (no exportado top-level) — detalle del SDK, sin impacto.
