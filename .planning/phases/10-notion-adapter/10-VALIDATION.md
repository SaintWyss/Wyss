---
phase: 10
slug: notion-adapter
status: draft
nyquist_compliant: false
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
| **Quick run command** | `uv run pytest tests/execution tests/policy -q` |
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

(La completa el planner por tarea.)

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | — | — | NOTION-01..04 | — | writes jamás sin confirmación; token jamás logueado | unit/integration | quick command | ✅ | ⬜ pending |

---

## Wave 0 Requirements

- [ ] Tests del adapter Notion con HTTP mockeado (sin red): reads, paginación completa, 429
- [ ] Tests de policy: notion.* base levels en los 5 conftests espejo
- [ ] Framework ya instalado

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Round-trip real contra el workspace del owner | NOTION-01/02 | requiere token real + página compartida con la integración | smoke final: leer página real; write B/C confirmado desde bandeja |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 70s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
