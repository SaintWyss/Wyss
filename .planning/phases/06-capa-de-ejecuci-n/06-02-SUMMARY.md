---
phase: 06-capa-de-ejecuci-n
plan: "02"
subsystem: execution
tags: [sqlite, wal, undo-journal, tdd, restore, overwrite-backup, import-linter]

# Dependency graph
requires:
  - phase: 06-capa-de-ejecuci-n
    plan: "01"
    provides: tests/execution/conftest.py (engine/FakeAudit/RecordingEngine fixtures)
  - phase: 01-fundaciones
    provides: core.domain.errors.AuditIntegrityError
provides:
  - src/execution/journal.py: UndoJournal SQLite-WAL store (record/restore/mark_applied/mark_rolled_back)
  - tests/execution/conftest.py: journal fixture (UndoJournal en tmp_path)
  - tests/execution/test_journal.py: 13 tests verdes (WAL active, durability, round-trips)
affects:
  - 06-03 (executor puede importar UndoJournal para D-65 record-before-mutation)
  - 06-04 (second-wall adapter usa journal para on_error=abort rollback)
  - 06-05 (executor usa restore() en ABORT path)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "UndoJournal mirrors PendingStore exactly: JOURNAL_PRAGMAS, WAL fail-fast constructor, context manager triple"
    - "backup_base_dir param en constructor para testability (apunta a tmp_path en tests, data/undo_backups en prod)"
    - "capture_overwrite_backup() pre-mutation: copia archivo antes de la mutacion, NO BLOB SQLite (RESEARCH Pitfall 5)"
    - "restore() dispatch por op_type: file.move/file.delete/file.write/file.restore_trash"
    - "TDD RED→GREEN: test file commiteado antes de la implementacion"

key-files:
  created:
    - src/execution/journal.py
    - tests/execution/test_journal.py
  modified:
    - tests/execution/conftest.py (journal fixture + Path import + docstring actualizado)

key-decisions:
  - "backup_base_dir inyectable en constructor: permite tests usar tmp_path sin tocar data/ real"
  - "restore() retorna False (no raise) para entry_id missing o status != pending: safe no-op para doble-restore"
  - "file.restore_trash inverse: lee .trashinfo Path= field + mueve files/<name> de vuelta; no se usa API de send2trash (no la tiene)"
  - "import-linter independence contract mantenido: journal.py importa solo core.* + stdlib"

# Metrics
duration: 20min
completed: "2026-06-13"
---

# Phase 06 Plan 02: UndoJournal SQLite-WAL Reversible Store Summary

**UndoJournal WAL fail-fast con record/restore round-trip, backup de sobreescritura en data/undo_backups, 13 tests verdes, lint-imports y mypy limpios**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-06-13T~21:00Z
- **Completed:** 2026-06-13T~21:20Z
- **Tasks:** 2 (Task 1 + Task 2 implementados secuencialmente con TDD RED→GREEN)
- **Files modified:** 3 (journal.py new, conftest.py updated, test_journal.py new)

## Accomplishments

- `src/execution/journal.py` (218 lineas): WAL fail-fast constructor (AuditIntegrityError), JOURNAL_PRAGMAS, CREATE_JOURNAL schema, UndoEntry frozen dataclass, record/load/mark_applied/mark_rolled_back, capture_overwrite_backup, restore() con dispatch por tipo, context manager
- `tests/execution/conftest.py`: journal fixture agrego (TODO del plan 01 resuelto); Path import; docstring actualizado
- `tests/execution/test_journal.py`: 13 tests verdes — test_wal_active, test_record_returns_hex_string, test_load_returns_pending_entry, test_load_missing_returns_none, test_mark_applied/rolled_back, test_constructor_raises_on_non_wal_fs, test_journal_context_manager, test_entry_survives_reopen, test_record_then_restore_move, test_restore_overwrite_from_backup, test_restore_missing_returns_false, test_restore_already_rolled_back_returns_false

## Task Commits

1. **RED: Failing tests for UndoJournal** - `75bb64b` (test)
2. **GREEN: UndoJournal implementation + conftest fixture** - `8f3b46a` (feat)

## Files Created/Modified

- `src/execution/journal.py` - UndoJournal completo (WAL fail-fast + record + restore + backup)
- `tests/execution/conftest.py` - journal fixture agregado; Path import; docstring actualizado
- `tests/execution/test_journal.py` - 13 tests TDD

## Decisions Made

- `backup_base_dir` inyectable en constructor: permite tests apuntar a `tmp_path` sin escribir en `data/` real; produccion usa `data/undo_backups` por defecto
- `restore()` retorna `False` (no lanza excepcion) para entry_id desconocido o status != 'pending' — safe no-op para doble-restore o rollback parcial
- `file.restore_trash` inverse implementado via lectura de `.trashinfo` (campo `Path=`) — send2trash no tiene API de restore programatico
- `import-linter independence` contract mantenido: `journal.py` importa solo `core.domain.errors` + stdlib

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test de overwrite con orden incorrecto de mutacion**
- **Found during:** Task 2 primera ejecucion
- **Issue:** El test `test_restore_overwrite_from_backup` llamaba `write_bytes(new_content)` antes de capturar el backup, asi que el backup tenia `new_content` en vez de `original_content`
- **Fix:** Reordenado el test: write original → record → capture_backup → overwrite con new_content → restore → assert original_content
- **Files modified:** tests/execution/test_journal.py
- **Commit:** 8f3b46a (incluido en GREEN phase)

**2. [Rule 3 - Blocker] `Path` no importado en conftest al agregar journal fixture**
- **Found during:** Task 2 fixture addition
- **Issue:** `NameError: name 'Path' is not defined` al agregar el fixture con type hint `tmp_path: Path`
- **Fix:** Agrego `from pathlib import Path` al conftest
- **Files modified:** tests/execution/conftest.py
- **Commit:** 8f3b46a

---

**Total deviations:** 2 auto-fixed (Rule 1 — test logic error; Rule 3 — missing import)
**Impact on plan:** Correcciones menores sin scope creep; ambas resueltas dentro del mismo ciclo GREEN.

## TDD Gate Compliance

- RED gate: commit `75bb64b` (test) — tests failing por ModuleNotFoundError
- GREEN gate: commit `8f3b46a` (feat) — 13 tests pasan, lint-imports + mypy clean
- REFACTOR: no requerido (implementacion limpia en primer intento)

## Known Stubs

None — este plan no introduce stubs de datos ni placeholders de UI.

## Threat Flags

None — UndoJournal implementa las mitigaciones del threat model del plan:
- T-06-UNDO-1: restore() mueve solo al `origin` grabado en record-time (path ya validado por segunda muralla en plan 04)
- T-06-UNDO-2: WAL fail-fast constructor (AuditIntegrityError), backups como archivos reales (no BLOBs)
- T-06-UNDO-3: record() debe llamarse ANTES de la mutacion (contrato documentado en docstring + D-65)

No se introdujeron nuevos endpoints de red, paths de auth ni surface fuera del threat model.

## Self-Check: PASSED

- [x] `src/execution/journal.py` existe y contiene `class UndoJournal`
- [x] `tests/execution/test_journal.py` existe y contiene 13 `def test_`
- [x] `tests/execution/conftest.py` contiene `def journal`
- [x] Commit `75bb64b` (RED) verificado en git log
- [x] Commit `8f3b46a` (GREEN) verificado en git log
- [x] `uv run pytest tests/execution/test_journal.py -q` → 13 passed
- [x] `uv run lint-imports` → Contracts: 2 kept, 0 broken
- [x] `uv run mypy src/execution/journal.py` → no issues found

---
*Phase: 06-capa-de-ejecuci-n*
*Completed: 2026-06-13*
