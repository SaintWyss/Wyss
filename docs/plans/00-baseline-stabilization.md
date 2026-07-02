# PR-00 — Baseline stabilization

> **EJECUTADO 2026-07-02 (scope reducido tras verificación).** El audit asumió que los tests NTFS
> actuales escribían residuos en `data/`; la inspección profunda lo refutó — ver §3.

## 1. Objective
Dejar el repo en estado base limpio, etiquetado y sin residuos, como punto de partida verificable para todos los PRs siguientes.

## 2. Context from the audit
Cadena de verificación corrida en vivo el 2026-07-02: 424 passed / 6 skipped, mypy 0 issues, ruff limpio, import-linter 2/2 kept. Residuos en `data/`: `trash_journal_test.db`, `trash_test_sentinel.txt`. `.import_linter_cache/` sin ignorar.

## 3. Exact problem (corregido tras inspección)
- Los residuos eran **huérfanos históricos**: los creó la versión vieja de `tests/execution/test_filesystem.py` (commit `6b60ca3`), que escribía bajo `<repo>/data/`. El fix `8dbcb45` ya movió ese test a tempdir mount-local FUERA de `data/` (con `shutil.rmtree` en finally) — la denylist `wyss-self-modify` bloqueaba `file.*` ahí, y el fix lo documenta.
- `tests/execution/test_wave0_ntfs.py` sí escribe bajo `data/` (deliberado: pitfall sticky-bit /tmp) pero limpia TODO en `finally` (sentinel, trashinfo, db, sidecars WAL/SHM). Riesgo residual: solo kill -9 a mitad de test. **Decisión: no tocar** — el código no está roto; los pasos 1-2 del spec original quedan sin efecto.
- `.import_linter_cache/` faltaba en `.gitignore`.

## 4. Architectural decision
`data/` raíz es territorio de runtime del owner; los tests que necesiten el mount NTFS real limpian tras sí (patrón ya vigente en ambos tests actuales).

## 5-7. Files
- Leídos: `tests/execution/test_wave0_ntfs.py` (completo), `tests/execution/test_filesystem.py` (test NTFS), historia git de los nombres residuales.
- Modificados: `.gitignore` (+`.import_linter_cache/`); borrados los 2 residuos.
- Sin tocar: tests (ya correctos), `src/`, datos reales del owner (`index.db`, `audit.db`, `chroma/`).

## 8. Required changes (ejecutadas)
1. ~~Mover artefactos de tests a `data/tmp_tests/`~~ — N/A: tests actuales ya limpian (evidencia §3).
2. ~~try/finally en tests~~ — N/A: ya existe en ambos.
3. `.gitignore` += `.import_linter_cache/`. ✔
4. Borrados `data/trash_journal_test.db` y `data/trash_test_sentinel.txt`. ✔
5. Tag anotado `audit-baseline-2026-07-02`. ✔

## 9. Contracts and invariants
- Tests NTFS siguen auto-skipeando sin `WYSS_TEST_NTFS=1` y pasando con ella, sin dejar residuos.
- `data/` queda solo con `.gitkeep`, `index.db`, `audit.db`, `chroma/`.

## 10. Tests required / 11. Manual verification
`WYSS_TEST_NTFS=1 uv run pytest -q tests/execution/test_wave0_ntfs.py tests/execution/test_filesystem.py` → verde, y `ls data/` sin residuos post-corrida. (Cadena completa ya verificada mismo día sobre el mismo árbol; ningún archivo de código cambió.)

## 12. Risks
Ninguno: borrado de huérfanos + línea de gitignore.

## 13. Rollback plan
`git revert` del commit; `git tag -d audit-baseline-2026-07-02` si hiciera falta.

## 14. Acceptance criteria
- `data/` sin residuos post-suite NTFS. ✔
- `.gitignore` cubre `.import_linter_cache/`. ✔
- Tag `audit-baseline-2026-07-02` existe. ✔

## 15. Executor prompt for cheaper AI
N/A — ejecutado directamente por el orquestador (scope trivial).
