---
phase: 07
slug: modelo-de-agentes
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-13
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Derived from 07-RESEARCH.md § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9+ con pytest-asyncio (asyncio_mode=auto) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/agents/ -x -q` |
| **Full suite command** | `uv run pytest && uv run mypy src tests && uv run ruff check src tests && uv run lint-imports` |
| **Estimated runtime** | ~25 segundos (full) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/agents/ -x -q`
- **After every plan wave:** full suite (pytest + mypy + ruff + lint-imports)
- **Before `/gsd:verify-work`:** full suite verde (baseline actual 383 passed/2 skipped — debe crecer)
- **Max feedback latency:** ~25s

---

## Per-Task Verification Map

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| AGENT-01 | `ConfiguredAgent._run` invoca ciclo (consultar BC→plan→ejecutar) — delega a PlanExecutor, NO a self.execute (anti-recursión) | unit | `uv run pytest tests/agents/test_configured_agent.py -x` | ❌ W0 | ⬜ pending |
| AGENT-02 | `AgentRegistry` instancia desde config sin código nuevo | unit | `uv run pytest tests/agents/test_registry.py -x` | ❌ W0 | ⬜ pending |
| AGENT-03 | Agente sin permiso → bloqueado + auditado ANTES del retrieval | unit | `uv run pytest tests/agents/test_scoped_retrieval.py::test_unauthorized_blocked -x` | ❌ W0 | ⬜ pending |
| AGENT-04 | Permiso revocado → denegado en query siguiente (sin cache) | unit | `uv run pytest tests/agents/test_scoped_retrieval.py::test_revoked_permission_denied -x` | ❌ W0 | ⬜ pending |
| AGENT-05 | `ConfiguredAgent` no importa/referencia otros agentes — ausencia | structural | `uv run pytest tests/agents/test_configured_agent.py::test_no_agent_to_agent_import -x` | ❌ W0 | ⬜ pending |
| AGENT-06 | `AgentDefinition` frozen; sin write-path a config en runtime | structural | `uv run pytest tests/agents/test_configured_agent.py::test_definition_is_frozen -x` | ❌ W0 | ⬜ pending |
| AGENT-08 | `AgentMemory.load()` template si no existe; `write_supervised` crea archivo | unit | `uv run pytest tests/agents/test_memory.py -x` | ❌ W0 | ⬜ pending |
| POL-07 | Doc con instrucciones inyectadas → plan evaluado D/REJECT + auditado | integration | `uv run pytest tests/agents/test_golden_injection.py -x` | ❌ W0 | ⬜ pending |
| POL-07 + D-70 | `_build_prompt` envuelve hits en `<untrusted_content>` | unit | `uv run pytest tests/agents/test_configured_agent.py::test_prompt_wraps_untrusted_content -x` | ❌ W0 | ⬜ pending |
| D-73 | `AgentConfigModel` con `extra="forbid"` rechaza claves desconocidas | unit | `uv run pytest tests/bootstrap/test_agent_config.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/agents/__init__.py`
- [ ] `tests/agents/conftest.py` — fixtures: `FakePermissionStore`, engine + `RecordingEngine`, `FakeAudit`, `FakeHybridRetrieval`
- [ ] `tests/agents/test_configured_agent.py` — AGENT-01, AGENT-05, AGENT-06, D-70
- [ ] `tests/agents/test_registry.py` — AGENT-02, D-73
- [ ] `tests/agents/test_scoped_retrieval.py` — AGENT-03, AGENT-04
- [ ] `tests/agents/test_memory.py` — AGENT-08
- [ ] `tests/agents/test_golden_injection.py` — POL-07 end-to-end
- [ ] `tests/agents/golden/injection_doc.md` — fixture con instrucciones inyectadas
- [ ] `tests/bootstrap/test_agent_config.py` — D-73

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
