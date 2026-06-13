---
phase: 3
slug: pipeline-de-ingesta
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-12
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (via uv) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports` |
| **Estimated runtime** | ~30 seconds (quick) / ~90 seconds (full) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-07-T1 | 03-07 | 4 | KNOW-01, KNOW-09, KNOW-11 | T-03-26, T-03-28, T-03-29 | CLI composition root wires concrete adapters, injects gateway secret patterns only from bootstrap, reports kb_id/progress, and exits nonzero only on systemic errors | unit/static | `uv run mypy src/bootstrap/cli.py && uv run ruff check src/bootstrap/cli.py && uv run lint-imports` | ✅ `src/bootstrap/cli.py` | ✅ green |
| 03-07-T2 | 03-07 | 4 | KNOW-08, KNOW-09, KNOW-11 | T-03-27, T-03-28 | `--estimate`/`--dry-run` do not write index state, output includes chunks/files/kb_id, non-interactive progress degrades to log lines, failed files keep exit 0 | unit | `uv run pytest tests/cli/test_index_command.py -x -q && uv run mypy tests/cli/test_index_command.py && uv run ruff check tests/cli` | ✅ `tests/cli/test_index_command.py` | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] Test stubs for KNOW-01, KNOW-02, KNOW-03, KNOW-06, KNOW-07, KNOW-08, KNOW-09, KNOW-11 (filled by planner)
- [x] Shared fixtures in tests/conftest.py (existing infrastructure — extend as needed)
- [x] Ollama + nomic-embed-text available (D-32: degrade gracefully if down; real test opt-in via `WYSS_TEST_OLLAMA=1`)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Kill -9 mid-scan resume | KNOW-03 | Process kill timing is non-deterministic in CI | Run `wyss index <ruta>` on large corpus, kill mid-scan, relaunch, verify continuation from file_state |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready
