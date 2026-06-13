---
phase: 05-orquestador-daemon
plan: 01
type: execute
status: complete
wave: 0
veredicto: STOP-PARCIAL
---

# 05-01 SUMMARY — Wave 0 empírico + scaffolding

**VEREDICTO EMPÍRICO: STOP PARCIAL.** A1 PASS; A2 FAIL (resoluble: build local); A3 PARCIAL;
A4 PARCIAL-PASS (regla UFW). Fallos confinados al deployment de Hermes (Plan 05-05).
Decisión del owner (2026-06-13): **proceder Waves 1-2 (05-02/03/04), diferir 05-05.**

## Qué se hizo

### Task 1+2 — Verificación empírica (ver `05-EMPIRICAL.md` para detalle)
- **A1 FastMCP API — PASS.** Pinneado `mcp==1.27.2`, `fastmcp==2.14.7` (<3). Firma real:
  `run(transport, **transport_kwargs)` + **`run_http_async(transport, host, port, path, ...)`**
  para el daemon asyncio. Round-trip MCP tool→`engine.evaluate` diferencia outcomes por
  riesgo (file.read→A, shell.run/file.write→C). Gating end-to-end confirmado.
- **A2 imagen Hermes — FAIL.** `docker pull ghcr.io/nousresearch/hermes-agent:latest` →
  `unauthorized`. El compose oficial **buildea local** (`image: hermes-agent`, `build: .`).
  Resolución: clonar repo + `docker build`. (afecta solo deployment de 05-05)
- **A3 disabled_toolsets — PARCIAL.** Docs confirman `mcp_servers: {url, headers}`; la key
  exacta de disable se cierra al tener la imagen buildeada.
- **A4 networking CachyOS — PARCIAL-PASS.** `host.docker.internal:host-gateway` resuelve a
  172.17.0.1; UFW (policy DROP) bloquea el bridge. Fix: `ufw allow from 172.17.0.0/16 to
  any port <MCP> proto tcp`.

### Task 3 — Scaffolding de tests (Nyquist Wave 0)
10 archivos creados con stubs `skip`/parametrize, razón = plan que los implementa:
`tests/orchestrator/{__init__,conftest,test_daemon,test_intent_router,test_pending_store,
test_plan_renderer,test_audit_query}.py`, `tests/domain/test_plan_on_error.py`,
`tests/policy/test_golden_nl_plans.py` (gate POL-06 con `NLGolden` + literal
`" — FALSO-A CATASTROFICO"`, poblado en 05-02).

## Cadena verde
- `uv run pytest tests/ -q` → **284 passed, 16 skipped** (286 base + scaffold_present, 13 stubs skip)
- `uv run mypy` → 136 files clean
- `uv run ruff check` → All checks passed
- `uv run lint-imports` → 2 kept (core puro, capas no cruzan)

## Revisiones pendientes para 05-05 (antes de ejecutarlo)
1. Compose con `build:` desde repo Hermes clonado (no `image: ghcr.io/...`).
2. Confirmar key real de disable de toolsets contra la imagen buildeada (cerrar A3/T-05-02).
3. Daemon sirve MCP con `run_http_async(transport="http", host="127.0.0.1", port, path="/mcp")`.
4. Añadir regla UFW `from 172.17.0.0/16` al runbook de deployment (op de sistema, no sincroniza).

## Archivos
- `pyproject.toml`, `uv.lock` (deps mcp+fastmcp)
- `.planning/phases/05-orquestador-daemon/05-EMPIRICAL.md` (nuevo, veredicto por ítem)
- 10 archivos de test scaffolding (arriba)
