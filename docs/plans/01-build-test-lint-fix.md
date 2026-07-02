# PR-01 — CI: la cadena de verificación como gate automático

## 1. Objective
Que cada push a `main` (y cada PR) corra automáticamente la cadena completa `pytest + mypy + ruff + import-linter` en GitHub Actions y bloquee en rojo.

## 2. Context from the audit
La cadena existe, está documentada (README §Verificación) y HOY está verde (verificado en vivo: 424 passed / mypy 0 / ruff limpio / 2 contratos kept). Pero no existe `.github/` — el gate es pura disciplina del orquestador. El proyecto delega construcción a modelos baratos (Codex/Gemini, runbook CLAUDE.md): sin CI, una regresión no detectada por el humano entra silenciosa.

## 3. Exact problem
Cero automatización de verificación. Riesgo P0 del audit: "regresión silenciosa el día que un ejecutor barato no corra la cadena".

## 4. Architectural decision
CI reproduce EXACTAMENTE la cadena local, con `uv`. No agrega herramientas nuevas (no coverage gates, no pre-commit, no matrix multi-OS) — el gate es la cadena existente, nada más.

## 5. Files to read first
- `pyproject.toml` (dependency-groups dev, markers pytest, contratos import-linter)
- `README.md` §Verificación
- `tests/execution/test_wave0_ntfs.py` líneas 1-30 (confirmar auto-skip sin `WYSS_TEST_NTFS`)

## 6. Files allowed to modify
- `.github/workflows/ci.yml` (crear)
- `README.md` (solo agregar badge/nota de CI en la sección Verificación)

## 7. Files forbidden to modify
- `pyproject.toml`, `src/`, `tests/`, `config/`, `.planning/`

## 8. Required changes
1. Crear `.github/workflows/ci.yml`:
   - trigger: `push` a `main` + `pull_request`.
   - runner: `ubuntu-latest`, Python 3.12.
   - pasos: checkout → `astral-sh/setup-uv` → `uv sync` → `uv run pytest -q` → `uv run mypy` → `uv run ruff check src tests` → `uv run lint-imports`.
   - Instalar `libmagic1` vía apt antes de `uv sync` (dep de `python-magic`; sin ella la ingesta no importa).
   - NO definir `WYSS_TEST_NTFS` (los tests NTFS se auto-skipean) ni secretos (ningún test requiere API keys: providers testeados con fakes/respx).
2. Nota de una línea en README §Verificación: "Esta cadena corre en CI en cada push".

## 9. Contracts and invariants
- CI verde == cadena local verde. Cero divergencia de comandos.
- El workflow no necesita secretos; si en el futuro un test los requiere, ese test debe ser opt-in por marker (patrón `integration` existente).

## 10. Tests required
La propia corrida del workflow. Local: `uv run pytest -q` sigue verde (nada de src cambió).

## 11. Manual verification
Push a una rama → abrir Actions en github.com/SaintWyss/Wyss → workflow verde con los 4 pasos. Romper un test a propósito en la rama → workflow rojo.

## 12. Risks
- ChromaDB en runner limpio puede tardar/descargar; mitigación: cache de uv (`enable-cache: true` en setup-uv).
- Tests que asuman rutas de esta máquina fallarían en runner — si ocurre, es un hallazgo real a arreglar (test no hermético), no a silenciar.

## 13. Rollback plan
Borrar `.github/workflows/ci.yml`. Cero impacto en runtime.

## 14. Acceptance criteria
- Workflow corre en push/PR y ejecuta los 4 comandos exactos.
- Corrida verde visible en Actions sobre `main`.
- Una rotura provocada en rama produce corrida roja.

## 15. Executor prompt for cheaper AI
```
Proyecto: Wyss. Root: /mnt/hdd/Data/10_Workspace/projects/wyss. Python 3.12, gestor uv. NO commitees.
Crea EXACTAMENTE un archivo: .github/workflows/ci.yml. No toques ningún otro archivo salvo agregar
una línea a README.md en la sección "Verificación" diciendo que la cadena corre en CI.

Workflow requerido:
- name: ci · on: push (branches: [main]) y pull_request
- job único "verify" en ubuntu-latest:
  1. actions/checkout@v4
  2. sudo apt-get update && sudo apt-get install -y libmagic1
  3. astral-sh/setup-uv@v5 con enable-cache: true y python-version "3.12"
  4. uv sync
  5. uv run pytest -q
  6. uv run mypy
  7. uv run ruff check src tests
  8. uv run lint-imports
No agregues WYSS_TEST_NTFS, secretos, coverage, matrix ni pasos extra. La cadena es esa y nada más.
Verifica localmente que el YAML parsea (python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"
usando uv run --with pyyaml python ...) y reporta SUMMARY con el contenido final del archivo.
```
