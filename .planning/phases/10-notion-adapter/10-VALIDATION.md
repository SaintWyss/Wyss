---
phase: 10
slug: notion-adapter
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-10
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (asyncio strict) + respx/httpx-mock (patrón tests/gateway) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/notion tests/policy tests/execution -q` |
| **Full suite command** | `uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports` |
| **Estimated runtime** | ~20 s (quick) / ~70 s (full) |

---

## Sampling Rate

- **After every task commit:** Run quick command
- **After every plan wave:** Run full suite command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 70 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-T1 | 01 | 1 | NOTION-03 | T-10-03, T-10-SC | RetryOptions SDK; paginación completa antes de devolver; dep slopcheck OK | unit | `uv run pytest tests/notion/test_pagination.py tests/notion/test_rate_limit.py -x && uv run lint-imports` | ❌→Wave0 | ⬜ pending |
| 10-01-T2 | 01 | 1 | NOTION-01, NOTION-04 | T-10-01, T-10-02, T-10-04, T-10-05 | token jamás en payload/audit/error; error de permiso → ToolResult legible; target normalizado | unit | `uv run pytest tests/notion/ -x && uv run mypy && uv run ruff check src tests && uv run lint-imports` | ❌→Wave0 | ⬜ pending |
| 10-02-T1 | 02 | 1 | NOTION-01, NOTION-02, NOTION-04 | T-10-06, T-10-08 | reads→A, writes→C; NOTION_TOKEN barrido por minimizer; 5 conftests sincronizados | unit | `uv run pytest tests/policy tests/execution tests/agents tests/orchestrator tests/security -q` | ✅ (extiende) | ⬜ pending |
| 10-02-T2 | 02 | 1 | NOTION-01, NOTION-02, NOTION-04 | T-10-07, T-10-08, T-10-09 | notion.* en _ACTION_TYPES; unknown→C fail-closed; token bloqueado | unit | `uv run pytest tests/policy/test_engine.py tests/gateway/test_minimizer.py tests/bootstrap/test_config.py -k notion -x && uv run mypy && uv run ruff check src tests && uv run lint-imports` | ✅ (extiende) | ⬜ pending |
| 10-03-T1 | 03 | 2 | NOTION-01, NOTION-02, NOTION-04 | T-10-11, T-10-13 | dispatch a Tool inyectado sin importar notion/; token de .env; independence intacta | unit | `uv run lint-imports && uv run mypy` | ✅ (extiende) | ⬜ pending |
| 10-03-T2 | 03 | 2 | NOTION-01, NOTION-02 | T-10-10, T-10-12 | dispatch de notion.* al adapter correcto; preview del contenido propuesto en writes | unit | `uv run pytest tests/execution/test_executor.py tests/orchestrator/test_plan_renderer.py -k notion -x && uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports` | ✅ (extiende) | ⬜ pending |
| 10-04-T1 | 04 | 3 | NOTION-01, NOTION-02, NOTION-04 | T-10-14, T-10-15, T-10-16 | round-trip real: read A directo, write C gateado+preview+confirmación, token no leakeado | manual | checkpoint human-verify (token real + página compartida) | n/a | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/notion/__init__.py` + `tests/notion/conftest.py` — nuevo package, fixtures `respx_mock`/`http_client` (espejo de tests/gateway/conftest.py) — plan 01 T1
- [ ] `tests/notion/test_tool.py`, `test_pagination.py`, `test_rate_limit.py` — nuevos, sin cobertura previa — plan 01 T1/T2
- [ ] Tests de policy: notion.* base levels en los 5 conftests espejo — plan 02 T1
- [ ] Framework ya instalado (pytest-asyncio + respx dev deps); `notion-client` se agrega en plan 01 T1

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Round-trip real contra el workspace del owner | NOTION-01/02/04 | requiere token real + página compartida con la integración | plan 04 (checkpoint): leer página real; write B/C confirmado desde bandeja; página no compartida → mensaje legible; token no leakeado en audit/trace |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (10-04 es manual por diseño: round-trip real)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 70s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned
