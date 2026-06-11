---
phase: 01-fundaciones
plan: 01
subsystem: infra
tags: [uv, hatchling, mypy, ruff, import-linter, pytest, pydantic, toml, hexagonal]

# Dependency graph
requires: []
provides:
  - "Proyecto uv instalable con `uv sync` e imports flat (`import core`, `import audit`, `import bootstrap`)"
  - "Toolchain de verificación completa y verde: pytest + mypy strict + ruff + lint-imports"
  - "Contratos import-linter que codifican la arquitectura hexagonal (core puro stdlib-only; capas independientes)"
  - "Esqueleto de paquetes nuevos: core/domain, core/ports, core/policy, bootstrap"
  - "config.example.toml canónico (D-09) reemplazando al YAML obsoleto"
affects: [01-02, 01-03, 01-04, 01-05, fundaciones, domain, ports, policy, audit, bootstrap]

# Tech tracking
tech-stack:
  added: [pydantic 2.13.4, pytest 9.0.3, mypy 2.1.0, ruff 0.15.16, import-linter 2.11, hatchling]
  patterns:
    - "Layout flat multi-paquete bajo src/ con hatchling packages explícitos (D-01)"
    - "Arquitectura hexagonal como contrato de CI vía import-linter (2 contratos)"
    - "mypy strict sobre src+tests; ruff con E,F,I,UP,B,SIM,RUF"
    - "Config en TOML (D-09); secretos solo en .env"

key-files:
  created:
    - pyproject.toml
    - uv.lock
    - src/core/domain/__init__.py
    - src/core/ports/__init__.py
    - src/core/policy/__init__.py
    - src/bootstrap/__init__.py
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_smoke.py
    - config/config.example.toml
  modified:
    - .gitignore
    - README.md

key-decisions:
  - "include_external_packages=true en import-linter para permitir el contrato forbidden sobre pydantic (módulo externo)"
  - "uv.lock commiteado para instalaciones reproducibles"
  - "src/__init__.py eliminado (artefacto del init; rompía imports flat — Assumption A5)"

patterns-established:
  - "Cadena de verificación canónica: uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports"
  - "Paquetes top-level genéricos (core, audit…) bajo venv dedicado — tradeoff D-01 documentado en README"
  - "La config TOML solo AGREGA deny rules; los invariantes D viven en código (regla #2)"

requirements-completed: [POL-01, AUD-01]

# Metrics
duration: ~5min
completed: 2026-06-11
---

# Phase 1 Plan 01: Fundaciones Wave 0 Summary

**Repo convertido de stubs a proyecto Python instalable con `uv` y toolchain hexagonal verde (pytest + mypy strict + ruff + import-linter), esqueleto de paquetes core/domain·ports·policy + bootstrap, y config canónica en TOML.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-11T13:12:44Z
- **Completed:** 2026-06-11T13:17:40Z
- **Tasks:** 2
- **Files modified:** 12 (10 creados, 2 modificados, 2 eliminados)

## Accomplishments
- `pyproject.toml` completo: hatchling multi-package (8 paquetes), mypy strict, ruff, pytest, 2 contratos import-linter — cadena de verificación verde de punta a punta
- Esqueleto hexagonal nuevo creado (`core/domain`, `core/ports`, `core/policy`, `bootstrap`) y `src/__init__.py` eliminado para habilitar imports flat
- `config.example.toml` canónico (D-09) con umbrales de política y `sensitive_dirs`, cero secretos; YAML obsoleto eliminado
- README actualizado (D-02): carpetas nuevas, tradeoff de paquetes top-level y la cadena de verificación documentados

## Task Commits

Cada tarea se commiteó atómicamente:

1. **Task 1: pyproject.toml + esqueleto de paquetes + toolchain verde** - `ecc23f1` (feat)
2. **Task 2: config.example.toml reemplaza al YAML + README documenta D-02** - `d175aa8` (feat)

**Plan metadata:** (este commit — docs: complete plan)

## Files Created/Modified
- `pyproject.toml` - Proyecto uv: deps, hatchling 8 paquetes, mypy strict, ruff, pytest, 2 contratos import-linter
- `uv.lock` - Lockfile reproducible (23 paquetes resueltos)
- `src/core/domain/__init__.py` - Paquete de entidades frozen (docstring)
- `src/core/ports/__init__.py` - Paquete de los 14 contratos (docstring)
- `src/core/policy/__init__.py` - Paquete del CognitivePolicyEngine (docstring)
- `src/bootstrap/__init__.py` - Paquete composition root (docstring)
- `tests/__init__.py`, `tests/conftest.py` - Paquete de tests + fixtures placeholder
- `tests/test_smoke.py` - Importa los 11 paquetes top-level; evita exit code 5 de pytest
- `config/config.example.toml` - Config canónica TOML: data_dir, audit_db, [policy] 4 umbrales + sensitive_dirs
- `.gitignore` - Sidecars WAL/SHM, caches mypy/ruff; eliminada línea `-e ` huérfana
- `README.md` - Carpetas nuevas (D-02), tradeoff top-level, cadena de verificación

**Eliminados:** `src/__init__.py` (Assumption A5), `config/config.example.yaml` (obsoleto)

## Decisions Made
- **include_external_packages=true** en `[tool.importlinter]`: el contrato `forbidden` lista `pydantic` (módulo externo); sin esa opción `lint-imports` aborta. Necesario para que el contrato "core es puro: stdlib only" funcione.
- **uv.lock commiteado**: garantiza instalaciones reproducibles de las dependencias pineadas.
- **src/__init__.py eliminado**: artefacto del init que convertía `src` en paquete y rompía los imports flat (`from core.ports import ...`) — alineado con Assumption A5 del research.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] include_external_packages requerido por import-linter**
- **Found during:** Task 1 (verificación de la toolchain)
- **Issue:** `lint-imports` abortaba con "The top level configuration must have include_external_packages=True when there are external forbidden modules" porque el contrato forbidden de `core` lista `pydantic` (paquete externo).
- **Fix:** Agregado `include_external_packages = true` en `[tool.importlinter]`.
- **Files modified:** pyproject.toml
- **Verification:** `uv run lint-imports` → "Contracts: 2 kept, 0 broken".
- **Committed in:** `ecc23f1` (commit de Task 1)

**2. [Rule 1 - Bug] Línea `-e ` huérfana en .gitignore**
- **Found during:** Task 1 (revisión de .gitignore previa a editarlo)
- **Issue:** El `.gitignore` tenía una línea `-e ` suelta (artefacto de un echo de `uv pip install -e`) que no ignora nada útil y ensucia el archivo.
- **Fix:** Eliminada; se agregaron además `.mypy_cache/`, `.ruff_cache/` y los sidecars `*.db-wal`/`*.db-shm` que pedía el plan.
- **Files modified:** .gitignore
- **Verification:** `git status` limpio salvo los cambios planeados.
- **Committed in:** `ecc23f1` (commit de Task 1)

---

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug)
**Impact on plan:** Ambos fixes necesarios para correctness (toolchain verde + .gitignore limpio). Sin scope creep.

## Issues Encountered
- `uv sync` emitió un warning de hardlink fallback (cache y target en filesystems distintos — NTFS). No bloqueante: cae a copia completa, instalación correcta.
- El check rápido de "no secrets" con grep dio un falso positivo al matchear el comentario que explica que NO debe haber secretos ("NUNCA poner secretos ni API keys aquí"). Verificado manualmente: cero claves/secretos reales en el TOML.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Proyecto instalable y toolchain verde: los planes 01-02..01-05 pueden escribir dominio, ports, política, auditoría y config validando con la cadena canónica.
- Esqueleto de paquetes vacío con docstrings — listo para poblarse (entidades frozen, los 14 ports, CognitivePolicyEngine, SqliteAuditLogger, bootstrap/config).
- `config.example.toml` fija el contrato de claves que `WyssConfigModel` validará en 01-05.
- Sin blockers.

## Self-Check: PASSED

Archivos creados verificados en disco; commits verificados en git log.

---
*Phase: 01-fundaciones*
*Completed: 2026-06-11*
