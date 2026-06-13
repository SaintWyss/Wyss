---
phase: 06-capa-de-ejecuci-n
plan: "01"
subsystem: testing
tags: [send2trash, sqlite, wal, ntfs, pytest, mypy, fixtures, conftest]

# Dependency graph
requires:
  - phase: 05-orquestador-daemon
    provides: CognitivePolicyEngine, PolicyRules, BUILTIN_DENY, AuditEvent, Span
  - phase: 01-fundaciones
    provides: core.domain (Plan, Action, RiskLevel), core.policy (engine)
provides:
  - send2trash>=2.1.0 runtime dependency (D-64)
  - tests/execution/__init__.py package marker
  - tests/execution/conftest.py with engine, FakeAudit, RecordingEngine fixtures
  - tests/execution/test_wave0_ntfs.py empirical NTFS environment pins
affects:
  - 06-02 (journal fixture TODO, imports conftest engine/FakeAudit)
  - 06-03 (adapters tests import conftest engine, RecordingEngine for EXEC-04 wall)
  - 06-04 (executor tests use RecordingEngine to assert second-wall re-evaluation)

# Tech tracking
tech-stack:
  added:
    - send2trash>=2.1.0 (XDG FreeDesktop trash, cross-FS, D-64)
  patterns:
    - "@pytest.mark.ntfs + @skipif WYSS_TEST_NTFS != '1' gating (empirical NTFS tests)"
    - "type: ignore[import-untyped] for third-party libs without stubs (mirrors openpyxl pattern)"
    - "RecordingEngine wrapper pattern: inner engine + .calls list for EXEC-04 second-wall assertions"

key-files:
  created:
    - tests/execution/__init__.py
    - tests/execution/conftest.py
    - tests/execution/test_wave0_ntfs.py
  modified:
    - pyproject.toml (send2trash dependency added)
    - uv.lock (dependency resolved)

key-decisions:
  - "send2trash type stubs absent — use type: ignore[import-untyped] (mirrors existing openpyxl pattern in codebase)"
  - "RecordingEngine.evaluate returns object (not PolicyDecision) to avoid importing PolicyDecision into conftest — keeps fixture generic"

patterns-established:
  - "NTFS empirical gate pattern: files under data/ (same NTFS volume), never /tmp (sticky-bit TrashPermissionError)"
  - "conftest mirror pattern: execution conftest is structural mirror of tests/orchestrator/conftest.py"

requirements-completed: [EXEC-03]

# Metrics
duration: 15min
completed: "2026-06-13"
---

# Phase 06 Plan 01: Wave 0 — Execution Test Infrastructure Summary

**send2trash runtime dep added + execution test scaffold with conftest fixtures (engine/FakeAudit/RecordingEngine) and empirical NTFS pins green on /mnt/hdd**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-06-13T~20:35Z
- **Completed:** 2026-06-13T~20:50Z
- **Tasks:** 3
- **Files modified:** 5 (pyproject.toml, uv.lock, 3 new test files)

## Accomplishments

- send2trash>=2.1.0 installed as runtime dep (D-64) and importable; uv add NTFS hardlink warning non-blocking
- tests/execution/ package with conftest providing engine, FakeAudit, RecordingEngine — structural mirror of tests/orchestrator/conftest.py
- Empirical NTFS stubs: test_send2trash_lands_in_ntfs_trash y test_sqlite_wal_on_ntfs pasan verde con WYSS_TEST_NTFS=1, se saltan sin ella; mypy y lint-imports pasan

## Task Commits

1. **Task 1: Add send2trash dependency and create tests/execution package** - `64583c5` (feat)
2. **Task 2: Create execution conftest with shared fixtures** - `a6e75f7` (feat)
3. **Task 3: Empirical NTFS stub — send2trash + WAL on /mnt/hdd** - `52028be` (feat)

**Plan metadata:** (ver commit final docs)

## Files Created/Modified

- `pyproject.toml` - send2trash>=2.1.0 agregado a [project] dependencies
- `uv.lock` - dependency resuelto (send2trash 2.1.0)
- `tests/execution/__init__.py` - package marker (vacío, espejo de tests/orchestrator/__init__.py)
- `tests/execution/conftest.py` - engine fixture, FakeAudit verbatim, RecordingEngine wrapper
- `tests/execution/test_wave0_ntfs.py` - test_send2trash_lands_in_ntfs_trash + test_sqlite_wal_on_ntfs

## Decisions Made

- send2trash sin type stubs → `# type: ignore[import-untyped]` (mismo patrón que openpyxl en tests/knowledge/)
- `RecordingEngine.evaluate` retorna `object` en vez de `PolicyDecision` para no importar PolicyDecision en conftest; esto mantiene el fixture genérico y se alinea con mypy strict

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] mypy strict falla por send2trash sin type stubs**
- **Found during:** Task 3 (test_wave0_ntfs.py)
- **Issue:** `from send2trash import send2trash` causa `[import-untyped]` bajo mypy strict. El plan no mencionaba esto.
- **Fix:** Agregado `# type: ignore[import-untyped]` al import (patrón ya establecido en tests/knowledge/extractors/test_extractors.py para openpyxl)
- **Files modified:** tests/execution/test_wave0_ntfs.py
- **Verification:** `uv run mypy tests/execution/` pasa con "no issues found in 3 source files"
- **Committed in:** 52028be (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 — missing type ignore)
**Impact on plan:** Fix necesario para mypy strict; no scope creep, patrón ya establecido en codebase.

## Issues Encountered

- `uv run pytest tests/execution -q --collect-only` retorna exit code 5 (no tests collected) en Task 2 — comportamiento correcto antes de agregar test files. No es un error de colección (exit 1 sería error; exit 5 = "no tests found").
- La acceptance criteria del plan decía "exits 0" — se interpretó correctamente como "sin errores de colección", no "con tests encontrados".

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- tests/execution/ completamente scaffolded — planes 06-02..06-05 pueden importar conftest fixtures sin modificación
- Marker `@pytest.mark.ntfs` verificado empíricamente: send2trash lanza a `/mnt/hdd/.Trash-1000/files/`; SQLite WAL activo en NTFS
- TODO en conftest marca `journal` fixture diferido a plan 06-02 (UndoJournal pendiente)
- lint-imports y mypy pasan en suite completa

## Known Stubs

None — este plan no introduce stubs de datos ni placeholders de UI.

## Threat Flags

None — no se introdujeron nuevos endpoints de red, paths de auth ni surface fuera del threat model del plan.

---
*Phase: 06-capa-de-ejecuci-n*
*Completed: 2026-06-13*
