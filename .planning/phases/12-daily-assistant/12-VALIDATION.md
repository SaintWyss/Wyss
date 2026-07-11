---
phase: 12
slug: daily-assistant
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-11
---

# Phase 12 — Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (asyncio strict) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/orchestrator -q` |
| **Full suite command** | `uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports` |
| **Estimated runtime** | ~15 s (quick) / ~70 s (full) |

## Sampling Rate

- After every task commit: quick command
- After every plan wave: full suite
- Before verify-work: full suite green
- Max feedback latency: 70 seconds

## Per-Task Verification Map

(La completa el planner.)

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| — | — | — | DAILY-01..03 | — | digest solo lectura, jamás propone writes | unit | quick command | ✅ | ⬜ pending |

## Wave 0 Requirements

- [ ] Tests del composer del digest (bandeja + ledger + fallas de rutinas, formato estable)
- [ ] Framework ya instalado

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Digest real con datos vivos + rutina 08:00 | DAILY-01 | reloj + datos reales | checkpoint: wyss digest on-demand + rutina programada |

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity OK
- [ ] Wave 0 covers MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 70s
- [ ] nyquist_compliant: true set in frontmatter

**Approval:** pending
