# Verificación — Fase 06: Capa de Ejecución

**Veredicto:** ✅ PASS
**Fecha:** 2026-06-13
**Commit verificado:** `8dbcb45`
**Método:** goal-backward (requisito → código → tests)

## Resumen

5/5 planes ejecutados con SUMMARY.md. Suite completa **383 passed, 2 skipped** (con `WYSS_TEST_NTFS=1`); `tests/execution/ + tests/ports/` = **77 passed**. `lint-imports`: 2 contratos KEPT (capas importan de `core`, nunca entre sí). `mypy --strict` y `ruff` verdes.

## Cobertura por requisito

| Req | Definición | Evidencia (código) | Tests | Estado |
|-----|-----------|--------------------|-------|--------|
| **EXEC-01** | Adaptadores desacoplados (FileSystem, Shell, Git) con allowlist | `src/execution/shell.py` (allowlist binarios fail-closed, `subprocess_exec` shell=False), `git.py` (allowlist subcomandos), `filesystem.py` (Tool port) | `test_shell.py`, `test_git.py`, `test_conformance.py` | ✅ |
| **EXEC-02** | Toda acción modificadora se verifica post-ejecución (conteos/hashes/estados) | `filesystem.py::verify()` (sha256 + estado), `executor.py::run()` (verify por step, falla→on_error) | `test_filesystem.py`, `test_executor.py` | ✅ |
| **EXEC-03** | Undo: papelera en vez de borrado + journal origen→destino con op inversa | `journal.py` UndoJournal (SQLite-WAL, `record`/`restore`/`capture_overwrite_backup`), `filesystem.py` send2trash + journal antes de mutar, `executor.py` rollback ABORT vía `journal.restore` | `test_journal.py`, `test_filesystem.py`, `test_executor.py` | ✅ |
| **EXEC-04** | Segunda muralla: re-verificar riesgo antes de ejecutar | `filesystem.py::_second_wall()` (resuelve path real, re-`engine.evaluate`, bloquea si `risk_level > max_risk` OR path cambió) | `test_second_wall.py` | ✅ |

## Decisiones implementadas

- **D-65** UndoJournal SQLite-WAL fail-fast (espejo de PendingStore) — 06-02
- **D-66** Adapters tras puerto `Tool` con allowlist — 06-03
- **D-68** Segunda muralla anti path-tricks — 06-04
- **D-69** PlanExecutor loop con retry/abort/escalate — 06-05

## Hallazgos

1. **[Resuelto]** `test_send2trash_on_ntfs_mount` (opt-in NTFS) fallaba: ubicaba el sentinel bajo `<repo>/data/`, vetado por la denylist `wyss-self-modify` (`**/wyss/data/**`) antes de ejercer send2trash. Era bug del test, no del código — la regla de seguridad es correcta. Fix en `8dbcb45`: tempdir mount-local fuera de `wyss/data`. La denylist quedó **validada en el acto**.

## Notas de ejecución

- Worktree isolation no usable: cwd del orquestador (`/home/saintwyss`) fuera del repo NTFS. Ejecutado secuencial en main tree, plan por plan. Sin race (un escritor por vez).
- Repo en mount NTFS/fuseblk (`/mnt/hdd`); pins empíricos de 06-01 (`WYSS_TEST_NTFS=1`) ejercen send2trash sobre fuseblk real (sin EXDEV).
