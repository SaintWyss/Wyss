---
phase: 06-capa-de-ejecuci-n
plan: "04"
subsystem: execution
tags: [filesystem, second-wall, send2trash, sha256, journal, tool-port, security]
dependency_graph:
  requires: [06-01, 06-02]
  provides: [FileSystemAdapter, _resolve_target, _sha256]
  affects: [tests/ports/test_conformance.py, src/execution/__init__.py]
tech_stack:
  added: [send2trash]
  patterns:
    - "Second wall: expanduser+resolve → rebuild Action+Plan → re-run CognitivePolicyEngine.evaluate"
    - "journal.record() BEFORE any mutation (D-65 invariant)"
    - "send2trash for delete, shutil.move for cross-FS moves"
    - "chunked sha256 (64 KiB) for write verification"
    - "mypy strict: _get_str/_get_int helpers for Mapping[str, object]"
key_files:
  created:
    - src/execution/filesystem.py
    - tests/execution/test_second_wall.py
    - tests/execution/test_filesystem.py
  modified:
    - tests/ports/test_conformance.py
decisions:
  - "os.rename prohibited — shutil.move handles EXDEV (cross-FS NTFS↔ext4); grep gate enforced"
  - "_get_str/_get_int helpers avoid mypy strict overload errors on Mapping[str, object]"
  - "audit event logged synchronously in _second_wall via self._audit.log() (same pattern as FakeAudit)"
  - "trash_path determined pre-delete via _expected_trash_path(); actual path re-checked via _find_actual_trash_path()"
  - "asyncio.run() used in sync test wrapper instead of deprecated get_event_loop().run_until_complete()"
metrics:
  duration: "~25 minutes"
  completed_date: "2026-06-13"
  tasks_completed: 2
  files_modified: 4
---

# Phase 06 Plan 04: FileSystemAdapter (Second Wall + Verify + send2trash) Summary

FileSystemAdapter con segunda muralla (D-68), verificacion post-ejecucion por tipo (D-67), journal-antes-de-mutar (D-65) y borrado via send2trash (D-64). Implementa el puerto Tool completo para operaciones de sistema de archivos.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Second-wall failing tests | fae83ab | tests/execution/test_second_wall.py |
| 1 (GREEN) | FileSystemAdapter second wall + stubs | 9d20fc1 | src/execution/filesystem.py |
| 2 (GREEN) | Execute/verify/send2trash/journal + conformance | 6b60ca3 | tests/execution/test_filesystem.py, tests/ports/test_conformance.py |

## What Was Built

### `src/execution/filesystem.py`

- `_resolve_target(target)`: `expanduser` + `Path.resolve()` — cierra el gap de `CognitivePolicyEngine._normalize()` que solo llama `expanduser`. 5 llamadas a `resolve()`.
- `_second_wall(action)`: reconstruye `Action+Plan` con la ruta resuelta, llama `self._engine.evaluate()`, bloquea si `risk_level > max_risk` OR `resolved != original`. Audita el bloqueo via `AuditEvent.new(...)`.
- `execute()`: gate segunda muralla → dispatch por `action.type` → `_execute_write/_execute_move/_execute_delete`.
- `_execute_write()`: `journal.record()` antes de escribir; captura backup en overwrite; payload `{size, sha256, resolved_target}`.
- `_execute_move()`: `shutil.move()` (EXDEV-safe); `journal.record()` antes; payload `{resolved_target}`.
- `_execute_delete()`: `send2trash()` (no unlink); `journal.record()` con `file.restore_trash` inverse antes; payload `{resolved_target, trash_path}`.
- `verify()`: dispatch por tipo — write→size+sha256; move→dest∧¬src; delete→¬path∧in-trash.
- 160+ lineas; mypy strict clean; lint-imports OK.

### `tests/execution/test_second_wall.py` (5 tests)

- `test_symlink_resolved_before_eval`: ~/Data resuelve a /mnt/hdd/Data via symlink.
- `test_resolve_target_expands_tilde`: resultado absoluto sin `~`.
- `test_recording_engine_called_on_execute`: `RecordingEngine.calls` contiene plan `task_id="second-wall"`.
- `test_tampered_path_blocked`: symlink target != original → `success=False` + audit event con `blocked="second_wall"`.
- `test_resolved_path_above_max_risk_blocked`: symlink a `~/.ssh` → denylist → bloqueado.

### `tests/execution/test_filesystem.py` (13 tests + 1 skip NTFS)

- Write: crea archivo, payload size+sha256, verify OK, verify falla en mismatch, journal registrado.
- Move: dest existe, src ausente; journal registrado con inverse; verify falla en failure.
- Delete: send2trash (no unlink); journal registrado con `file.restore_trash` inverse; original ausente; AST-check no usa `os.unlink`.
- Journal-before-mutation: para archivo nuevo la inversa es `file.delete`.
- NTFS opt-in: `@pytest.mark.ntfs` / `WYSS_TEST_NTFS=1`.

### `tests/ports/test_conformance.py`

- `test_filesystem_adapter_conforms`: `adapter: Tool = FileSystemAdapter(...)` — mypy verifica el protocolo estructuralmente.

## Verification Results

```
uv run pytest tests/execution/test_second_wall.py tests/execution/test_filesystem.py tests/ports/test_conformance.py -q
34 passed, 1 skipped

Full suite: 374 passed, 4 skipped (all NTFS opt-in)

grep gates:
  resolve() count: 5   ✓ (>=1 required)
  os.rename count: 0   ✓ (must be 0)
  send2trash count: 10 ✓ (>=1 required)

uv run lint-imports: 2 contracts KEPT
uv run mypy src/execution/filesystem.py: Success
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Comentario en docstring rompía el grep gate `os.rename count=0`**
- **Found during:** Task 2 acceptance criteria
- **Issue:** El docstring de `_execute_move()` mencionaba `os.rename` como anti-pattern, lo que hacía que `grep -c 'os.rename' src/execution/filesystem.py` devolviera 1 en vez de 0.
- **Fix:** Reescribí el docstring como "shutil.move (EXDEV-safe, cross-FS NTFS↔ext4)" sin mencionar `os.rename`.
- **Files modified:** `src/execution/filesystem.py`
- **Commit:** 6b60ca3

**2. [Rule 2 - Missing] `_get_str/_get_int` helpers para mypy strict**
- **Found during:** Task 1 GREEN — `uv run mypy` rechazó `int(action.parameters.get(...))` porque `parameters: Mapping[str, object]` → `.get()` devuelve `object`, sin overload para `int(object)`.
- **Fix:** Añadí `_get_str()` y `_get_int()` como helpers con `isinstance` guards, pattern consistente con el resto del codebase.
- **Files modified:** `src/execution/filesystem.py`
- **Commit:** 9d20fc1

**3. [Rule 1 - Bug] `asyncio.get_event_loop().run_until_complete()` deprecado**
- **Found during:** Task 1 GREEN — pytest emitía `DeprecationWarning: There is no current event loop`.
- **Fix:** Reemplazado por `asyncio.run()` en `test_second_wall.py`. (Los tests de filesystem ya usaban `asyncio.run()` directamente.)
- **Files modified:** `tests/execution/test_second_wall.py`
- **Commit:** 9d20fc1

## Known Stubs

Ninguno. `FileSystemAdapter` está completamente implementado para los tres tipos de acción (`file.write`, `file.move`, `file.delete`). Los tipos no reconocidos devuelven `ToolResult(success=False)` explicito.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| No nuevas superficies | — | FileSystemAdapter no expone puertos de red ni cambia rutas de autenticación. Cierra el threat T-path-tricks (D-68) documentado en el plan. |

## Self-Check: PASSED

| Check | Status |
|-------|--------|
| src/execution/filesystem.py exists | FOUND |
| tests/execution/test_second_wall.py exists | FOUND |
| tests/execution/test_filesystem.py exists | FOUND |
| .planning/phases/06-capa-de-ejecuci-n/06-04-SUMMARY.md exists | FOUND |
| commit fae83ab (RED) | FOUND |
| commit 9d20fc1 (GREEN Task 1) | FOUND |
| commit 6b60ca3 (GREEN Task 2) | FOUND |
