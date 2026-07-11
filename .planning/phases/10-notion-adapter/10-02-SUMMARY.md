---
phase: 10-notion-adapter
plan: 02
status: complete
completed: 2026-07-10
requirements: [NOTION-01, NOTION-02, NOTION-04]
builder: codex (codex-gsd-exec) — verificado y commiteado por Claude
---

# 10-02 Summary — Registro en política, planner y minimizer

## Qué se hizo

- `_BASE_LEVELS` (bootstrap/config.py): notion.read_page/query_database = **A**, notion.create_page/update_page = **C** — replicado idéntico en los **5 conftests espejo** (agents/execution/orchestrator/policy/security; grep 1 vez por archivo verificado).
- `_ACTION_TYPES` + guidance del prompt (llm_orchestrator.py): los 4 notion.* con instrucción explícita "nunca shell.run para Notion" (targets = ID o URL).
- `NOTION_TOKEN` en `_GATEWAY_ENV_KEYS` → barrido por el minimizer (jamás viaja a un LLM); documentado en config/.env.example.
- Tests: golden plans de policy (notion A/C + tipo desconocido C fail-closed), minimizer (token barrido), config (secret keys completos vs .env.example — el contrato de test_gateway_config exige cobertura de todos los secretos documentados).

## Verificación (fuera del sandbox)

**592 passed** (+7) / mypy 0 / ruff 0 / import-linter 2/2.

## Deviations

`tests/policy/test_engine.py` del plan no existe en el repo → el guard equivalente se extendió en `tests/policy/test_golden_plans.py` (desviación menor, mismo objetivo).
