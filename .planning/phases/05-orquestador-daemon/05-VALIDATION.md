---
phase: 5
slug: orquestador-daemon
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-13
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x con `pytest-asyncio` (`asyncio_mode="auto"`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths=["tests"]) |
| **Quick run command** | `uv run pytest tests/orchestrator/ tests/policy/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~25 seconds (full suite ~290 tests) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/orchestrator/ tests/policy/ -x -q && uv run mypy src/orchestrator && uv run ruff check src tests && uv run lint-imports`
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green + `tests/policy/test_golden_nl_plans.py` green (0 falsos-A)
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 0 | ORCH-01/03 | T-05-01/02 | host.docker.internal solo desde container; toolsets off | manual (empirical) | `docker run ... && curl host.docker.internal:7420` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 0 | ORCH-01 | T-05-SC | mcp/fastmcp legítimos, pin <3; round-trip MCP→engine | manual (empirical) | `uv add ... && python -c "from fastmcp import FastMCP; help(FastMCP.run)"` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 0 | (scaffold) | — | N/A | unit (scaffold) | `uv run pytest tests/ -q` (stubs skipped) | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | ORCH-07 | T-05-05 | on_error default ABORT fail-safe; retro-compat | unit | `uv run pytest tests/domain/test_plan_on_error.py -q` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 1 | ORCH-03/04 | T-05-06 | port no asigna nivel; ≥9 categorías | unit | `uv run pytest tests/orchestrator/test_intent_router.py -q` | ❌ W0 | ⬜ pending |
| 05-02-03 | 02 | 1 | POL-06 | T-05-04 | falso-A rompe build (≥20 fixtures, engine determinístico) | unit (golden gate) | `uv run pytest tests/policy/test_golden_nl_plans.py -q` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 1 | ORCH-06 | T-05-07/09 | sobrevive restart; rechaza confirm stale; WAL fail-fast | unit | `uv run pytest tests/orchestrator/test_pending_store.py -q` | ❌ W0 | ⬜ pending |
| 05-03-02 | 03 | 1 | ORCH-05 | — | Plan legible; B=[s/N] C=CONFIRMAR | unit | `uv run pytest tests/orchestrator/test_plan_renderer.py -q` | ❌ W0 | ⬜ pending |
| 05-03-03 | 03 | 1 | ORCH-06 | T-05-08 | expiración auditada (CONFIRMATION_ANSWERED) | unit | `uv run pytest tests/orchestrator/test_pending_store.py -q` | ❌ W0 | ⬜ pending |
| 05-04-01 | 04 | 2 | ORCH-01/02 | T-05-12 | socket 0600; stale cleanup; round-trip | unit/integration | `uv run pytest tests/orchestrator/test_daemon.py -q` | ❌ W0 | ⬜ pending |
| 05-04-02 | 04 | 2 | ORCH-05/06 | T-05-11/13/15/16 | D nunca ejecuta; engine única compuerta; fail-closed | unit | `uv run pytest tests/orchestrator/test_daemon.py -q` | ❌ W0 | ⬜ pending |
| 05-04-03 | 04 | 2 | ORCH-02/AUD-02 | T-05-14 | confirm no bloquea (D-57); audit lista historial | unit/integration | `uv run pytest tests/orchestrator/test_audit_query.py -q` | ❌ W0 | ⬜ pending |
| 05-05-01 | 05 | 3 | ORCH-03/04 | T-05-18/21 | Hermes no asigna nivel; degradación D-60 | unit | `uv run pytest tests/orchestrator/test_intent_router.py -q` | ❌ W0 | ⬜ pending |
| 05-05-02 | 05 | 3 | ORCH-01/POL-06 | T-05-17/20/22 | toda tool MCP → engine.evaluate; bind 127.0.0.1 | unit | `uv run pytest tests/orchestrator/test_mcp_server.py -q` | ❌ W0 | ⬜ pending |
| 05-05-03 | 05 | 3 | ORCH-01 | T-05-21 | daemon cliente-only Hermes; MCP background; degrada | integration | `uv run pytest tests/orchestrator/ -q` | ❌ W0 | ⬜ pending |
| — | — | all | regression | — | 286 tests existentes siguen verdes | regression | `uv run pytest tests/ -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/orchestrator/__init__.py`
- [ ] `tests/orchestrator/conftest.py` — fixtures `engine`, `fake_orchestrator`, `pending_store`, `daemon_client`
- [ ] `tests/orchestrator/test_daemon.py` — ORCH-01, ORCH-02 (stubs)
- [ ] `tests/orchestrator/test_intent_router.py` — ORCH-03, ORCH-04 (stubs)
- [ ] `tests/orchestrator/test_pending_store.py` — ORCH-06 (stubs)
- [ ] `tests/orchestrator/test_plan_renderer.py` — ORCH-05 (stubs)
- [ ] `tests/orchestrator/test_audit_query.py` — AUD-02 (stubs)
- [ ] `tests/orchestrator/test_mcp_server.py` — D-59 gating (creado en Plan 05)
- [ ] `tests/domain/test_plan_on_error.py` — ORCH-07 (stubs)
- [ ] `tests/policy/test_golden_nl_plans.py` — POL-06 (scaffold, poblado en Plan 02)
- [ ] `uv add "mcp>=1.27,<2" "fastmcp>=2.14,<3"` — instalar deps nuevas

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Imagen Hermes Docker pull+run | ORCH-01/03 | Requiere docker daemon + red; no automatizable en pytest | Plan 01 Task 1: `docker pull <image>` + `docker run` health |
| host.docker.internal container→host | ORCH-01 | Requiere container vivo + networking CachyOS | Plan 01 Task 1: listener host + curl desde container |
| FastMCP `mcp.run` firma real | ORCH-01 | Verificación de API de dep recién instalada | Plan 01 Task 2: `python -c "...help(FastMCP.run)"` |
| systemd reinicia el daemon ante fallo | ORCH-01/D-61 | Requiere systemd user unit instalado | Plan 04 Task 3 (documentado): `systemctl --user enable --now wyss` + kill + verificar restart |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (empirical tasks documented manual + scaffold)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-13
