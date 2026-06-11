---
phase: 1
slug: fundaciones
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-10
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (instalado por Wave 0 vía `uv sync`) |
| **Config file** | none — Wave 0 installs (`pyproject.toml` + `[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -q && uv run mypy src/core/ --strict && uv run ruff check src/ tests/` |
| **Estimated runtime** | ~10 seconds (núcleo puro sin IO de negocio) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run full suite (pytest + mypy strict + ruff)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Completado por el planner al emitir los PLAN.md. Mapeo base por criterio de éxito:

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (planner) | — | — | POL-01..05 | regla #2 | Nivel D nunca ejecuta; falso-A rompe CI | unit | `uv run pytest tests/test_policy.py -q` | ❌ W0 | ⬜ pending |
| (planner) | — | — | POL-04 | regla #2 | `max(deterministic, estimated)` — LLM no baja riesgo | unit | `uv run pytest tests/test_policy.py -k risk_floor -q` | ❌ W0 | ⬜ pending |
| (planner) | — | — | POL-05 | regla #2 | Plan compuesto que agrega a D → D | unit | `uv run pytest tests/test_policy.py -k composition -q` | ❌ W0 | ⬜ pending |
| (planner) | — | — | AUD-01 | regla #1 | Eventos persisten en SQLite separado; WAL activo | integration | `uv run pytest tests/test_audit.py -q` | ❌ W0 | ⬜ pending |
| (planner) | — | — | (ports) | — | 14 ports en core/ports/; mypy strict pasa | static | `uv run mypy src/core/ --strict` | ❌ W0 | ⬜ pending |
| (planner) | — | — | (config) | — | Config inválida = fail-fast con error legible | unit | `uv run pytest tests/test_config.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — uv init, deps (pydantic) + dev deps (pytest, mypy, ruff, import-linter)
- [ ] `tests/conftest.py` — fixtures compartidas (audit DB en tmp_path, config TOML de prueba)
- [ ] `tests/fixtures/golden_plans/` — set dorado ~12-15 planes con nivel A/B/C/D esperado
- [ ] `tests/test_policy.py`, `tests/test_audit.py`, `tests/test_config.py`, `tests/test_ports.py` — stubs

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| WAL real sobre NTFS | AUD-01 | Depende del FS del entorno (fuseblk) | Boot del AuditLogger contra `/mnt/hdd`: `PRAGMA journal_mode=WAL` debe retornar `"wal"`; si falla, fallback documentado |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
