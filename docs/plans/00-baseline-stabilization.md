# PR-00 — Baseline stabilization

## 1. Objective
Dejar el repo en estado base limpio, etiquetado y sin residuos, como punto de partida verificable para todos los PRs siguientes.

## 2. Context from the audit
Cadena de verificación corrida en vivo el 2026-07-02: 424 passed / 6 skipped, mypy 0 issues, ruff limpio, import-linter 2/2 kept. El repo está sincronizado con origin. Quedan residuos menores: artefactos de tests NTFS en `data/` real y `.import_linter_cache/` sin ignorar.

## 3. Exact problem
1. `data/trash_journal_test.db` y `data/trash_test_sentinel.txt` — residuos de `tests/execution/test_wave0_ntfs.py` y `tests/execution/test_filesystem.py` (tests opt-in `WYSS_TEST_NTFS=1` que escriben deliberadamente bajo `data/` por el pitfall sticky-bit de /tmp) conviven con datos reales del owner (`index.db`, `audit.db`) y no se limpian nunca.
2. `.import_linter_cache/` existe en la raíz y no figura en `.gitignore`.
3. No existe marca del estado verde auditado.

## 4. Architectural decision
Los tests que necesitan el filesystem NTFS real escriben SOLO bajo `data/tmp_tests/` y limpian tras sí. `data/` raíz es territorio exclusivo de runtime del owner.

## 5. Files to read first
- `tests/execution/test_wave0_ntfs.py` (completo — docstring explica el pitfall /tmp)
- `tests/execution/test_filesystem.py` línea ~404 y su contexto (uso de sentinel)
- `.gitignore`

## 6. Files allowed to modify
- `tests/execution/test_wave0_ntfs.py`
- `tests/execution/test_filesystem.py`
- `.gitignore`
- borrar: `data/trash_journal_test.db`, `data/trash_test_sentinel.txt` (residuos, no datos del owner)

## 7. Files forbidden to modify
- `data/index.db`, `data/audit.db`, `data/chroma/` (datos reales del owner)
- todo `src/`, `pyproject.toml`, `.planning/`
- `config/`

## 8. Required changes
1. En ambos tests, cambiar el directorio base de artefactos de `_REPO_ROOT / "data"` a `_REPO_ROOT / "data" / "tmp_tests"` (crearlo con `mkdir(parents=True, exist_ok=True)`).
2. Envolver la creación de sentinels/DBs en `try/finally` (o fixture con `yield`) que borre el artefacto al terminar, aun si el test falla. Mantener intacta la semántica del test (send2trash debe seguir operando sobre el mount NTFS real).
3. Agregar a `.gitignore`: `.import_linter_cache/` y `data/tmp_tests/`.
4. Borrar los dos residuos actuales de `data/`.
5. Crear tag anotado: `git tag -a audit-baseline-2026-07-02 -m "estado verde auditado: 424 passed, mypy/ruff/lint-imports OK"`.

## 9. Contracts and invariants
- Los dos tests NTFS siguen pasando con `WYSS_TEST_NTFS=1` sobre `/mnt/hdd` y siguen auto-skipeándose sin la variable.
- Ningún test del repo escribe fuera de `tmp_path` o `data/tmp_tests/`.
- `data/` raíz queda solo con `.gitkeep`, `index.db`, `audit.db`, `chroma/`.

## 10. Tests required
```bash
uv run pytest -q
WYSS_TEST_NTFS=1 uv run pytest -q tests/execution/test_wave0_ntfs.py tests/execution/test_filesystem.py
uv run mypy && uv run ruff check src tests && uv run lint-imports
```

## 11. Manual verification
`ls data/` tras correr la suite NTFS: no debe quedar ningún archivo `trash_*` ni `wave0_*`; `data/tmp_tests/` vacío o inexistente.

## 12. Risks
Cambiar el path base podría romper la aserción del trash FreeDesktop (busca en `/mnt/hdd/.Trash-1000/files/`) — no cambia, porque `data/tmp_tests/` sigue en la misma partición.

## 13. Rollback plan
`git revert` del commit; los tests vuelven al comportamiento anterior. El tag se borra con `git tag -d` si hiciera falta.

## 14. Acceptance criteria
- Cadena completa verde (incluida corrida NTFS opt-in).
- `data/` sin residuos post-suite.
- `.gitignore` cubre `.import_linter_cache/` y `data/tmp_tests/`.
- Tag `audit-baseline-2026-07-02` existe.

## 15. Executor prompt for cheaper AI
```
Proyecto: Wyss. Root absoluto: /mnt/hdd/Data/10_Workspace/projects/wyss. Python 3.12 + uv.
NO toques nada fuera de los archivos listados. NO commitees (el orquestador commitea).

Tarea:
1. Lee tests/execution/test_wave0_ntfs.py y tests/execution/test_filesystem.py (busca "sentinel").
2. En ambos, los artefactos temporales que hoy se crean bajo <repo>/data/ deben crearse bajo
   <repo>/data/tmp_tests/ (mkdir parents=True exist_ok=True) y borrarse en try/finally o fixture,
   aunque el test falle. NO cambies la lógica de los tests (send2trash sobre NTFS real, PRAGMA WAL).
   Estos tests corren solo con WYSS_TEST_NTFS=1; sin la variable se skipean — mantené eso.
3. Agrega a .gitignore dos líneas: ".import_linter_cache/" y "data/tmp_tests/".
4. Borra data/trash_journal_test.db y data/trash_test_sentinel.txt (residuos de test).
   PROHIBIDO tocar data/index.db, data/audit.db, data/chroma/.
5. Verifica: uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports
   y además WYSS_TEST_NTFS=1 uv run pytest -q tests/execution/test_wave0_ntfs.py
Reporta un SUMMARY con: archivos tocados, resultado exacto de cada comando de verificación.
```
