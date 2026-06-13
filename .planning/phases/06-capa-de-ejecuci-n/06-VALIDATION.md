---
phase: 6
slug: capa-de-ejecuci-n
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-13
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/execution -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~30 seconds |

NTFS-dependent tests gated by `WYSS_TEST_NTFS=1` + `@pytest.mark.ntfs` (mirror existing journal/trash pattern from research).

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/execution -q`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 0 | EXEC-03 | — | send2trash lands file in `.Trash-1000/` on NTFS; WAL=`wal` on `/mnt/hdd` | empirical | `uv run pytest tests/execution/test_wave0_ntfs.py -q -m ntfs` | ❌ W0 | ⬜ pending |
| 06-02-01 | 02 | 1 | EXEC-03 | — | journal records origin→dest + inverse; `restore(id)` applies inverse | unit | `uv run pytest tests/execution/test_journal.py -q` | ❌ W0 | ⬜ pending |
| 06-03-01 | 03 | 1 | EXEC-01 | T-shell-injection | binary off allowlist → reject + audit; exec by argv, never `shell=True` | unit | `uv run pytest tests/execution/test_shell_adapter.py -q` | ❌ W0 | ⬜ pending |
| 06-04-01 | 04 | 1 | EXEC-02 | — | per-type verify: write→size+sha256, move→dest∧¬src, delete→¬path∧in-trash | unit | `uv run pytest tests/execution/test_fs_adapter.py -q` | ❌ W0 | ⬜ pending |
| 06-05-01 | 05 | 2 | EXEC-04 | T-path-tricks | resolved path raises risk > Tool.max_risk → block + audit | unit | `uv run pytest tests/execution/test_second_wall.py -q` | ❌ W0 | ⬜ pending |
| 06-06-01 | 06 | 2 | EXEC-03 | — | `Action.on_error` ABORT→rollback via journal; RETRY; ESCALATE→audit | unit | `uv run pytest tests/execution/test_executor_onerror.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Plan IDs / wave assignment are provisional — planner finalizes in PLAN.md frontmatter.*

---

## Wave 0 Requirements

- [ ] `tests/execution/conftest.py` — shared fixtures (tmp NTFS path, fake Plan/Action, audit spy)
- [ ] `tests/execution/test_wave0_ntfs.py` — empirical send2trash + WAL stubs on `/mnt/hdd` (gated `@pytest.mark.ntfs`)
- [ ] `uv add send2trash>=2.1.0` — only new runtime dependency
- [ ] `@pytest.mark.ntfs` marker registered in pyproject (if not already from prior phases)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| End-to-end real plan execution with confirmación B | EXEC-01..04 | Touches live filesystem + daemon confirmation loop | Dispatch a real file.write+move plan through the Phase 5 daemon; confirm B; verify trash + journal + audit entries exist |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
