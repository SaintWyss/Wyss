---
phase: 01-fundaciones
plan: 06
subsystem: bootstrap
tags: [config, pydantic, fail-fast, composition-root, denylist, gap-closure]
requires:
  - core.domain.config (WyssSettings)
  - core.domain.policy (PolicyRules, DenyRule, AggregateThresholds)
  - core.domain.errors (WyssError)
  - core.policy.builtin_deny (BUILTIN_DENY)
provides:
  - bootstrap.config.load_settings (config.toml -> WyssSettings, fail-fast)
  - bootstrap.config.WyssConfigModel (frontera Pydantic, extra=forbid)
  - bootstrap.config.TomlConfigStore (adapter del Protocol ConfigStore)
  - core.domain.errors.ConfigError (excepción de dominio de fail-fast)
affects:
  - Fase 5 (CLI/daemon): consume load_settings al boot; decide el sys.exit ante ConfigError
  - Todas las fases: reciben WyssSettings inyectado desde el composition root
tech-stack:
  added: []
  patterns:
    - "frontera Pydantic→dominio: BaseModel muere en bootstrap, core recibe dataclass"
    - "extra=forbid en todos los modelos → typo/clave extra aborta el boot (fail-closed)"
    - "denylist aditiva: PolicyRules.deny = BUILTIN_DENY + tuple(config_deny) (regla #2)"
    - "ConfigError de dominio en vez de sys.exit → testeable con pytest.raises"
key-files:
  created:
    - src/bootstrap/config.py
    - tests/bootstrap/__init__.py
    - tests/bootstrap/conftest.py
    - tests/bootstrap/test_config.py
  modified:
    - src/bootstrap/__init__.py
    - src/core/domain/errors.py
    - src/core/domain/__init__.py
decisions:
  - "Fail-fast levanta ConfigError (subclase WyssError) con mensaje legible, no sys.exit — el caller CLI de Fase 5 decide el exit; así es testeable sin matar el proceso"
  - "deny rules de config mapean match_action→action_type y match_target→target_patterns; un match_target ausente = tupla vacía (matchea cualquier target)"
  - "sensitive_dirs vacío en config preserva los DEFAULT_SENSITIVE_DIRS de dominio (no se degrada a sin protección)"
  - "TomlConfigStore cumple ConfigStore por duck typing del Protocol; no se importa el Protocol (evita acoplamiento innecesario)"
metrics:
  duration: "~2 min"
  completed: 2026-06-11
  tasks: 2
  files: 7
---

# Phase 1 Plan 6: Config Bootstrap (frontera Pydantic→dominio) Summary

`load_settings(path) -> WyssSettings` valida `config.toml` al boot con Pydantic v2 (`extra="forbid"`, fail-closed), produce el frozen dataclass de dominio (Pydantic muere en bootstrap), concatena las reglas `[[policy.deny]]` de config a `BUILTIN_DENY` (solo aditivas) y levanta `ConfigError` legible ante config inexistente/mal formada/inválida — cierra SC5 y el gap raíz del stub `bootstrap/__init__.py`.

## What Was Built

- **`src/bootstrap/config.py`** — la frontera Pydantic→dominio (único lugar con Pydantic):
  - `DenyRuleModel`, `PolicyConfigModel`, `WyssConfigModel` (todos `ConfigDict(extra="forbid")`; el root además `frozen=True`).
  - `load_settings(path)`: `tomllib.load` → `WyssConfigModel.model_validate`; mapea `FileNotFoundError`/`tomllib.TOMLDecodeError`/`pydantic.ValidationError` a `ConfigError` con mensaje legible que nombra el path y, para validación, el `loc` de cada campo.
  - `_to_settings`: construye `PolicyRules(deny=BUILTIN_DENY + config_deny, base_levels=<defaults docs/13>, thresholds=AggregateThresholds(...))` y retorna `WyssSettings`.
  - `_BASE_LEVELS`: niveles base por action_type (file.read/list→A, move/rename→B, create/write/delete→C, shell.run→C).
  - `TomlConfigStore`: adapter que envuelve `load_settings` para cumplir el Protocol `ConfigStore` (D-10).
- **`src/bootstrap/__init__.py`** — reemplaza el stub de docstring por re-export de `load_settings` y `TomlConfigStore` con `__all__`.
- **`src/core/domain/errors.py`** — nueva `ConfigError(WyssError)`, excepción de fail-fast del boot (añadida a `core.domain.__init__` y `__all__`).
- **`tests/bootstrap/`** — 9 tests: carga válida, config inexistente, TOML mal formado, claves extra (top-level/policy/deny-rule), tipo inválido, denylist aditiva, y `not isinstance(WyssSettings, BaseModel)`.

## Verification Results

- `uv run pytest` → **69 passed, 1 skipped** (9 nuevos en tests/bootstrap + 60 previos)
- `uv run mypy` → **no issues found in 55 source files**
- `uv run ruff check src tests` → **All checks passed!**
- `uv run lint-imports` → **2 kept, 0 broken** (pydantic SOLO en bootstrap, core stdlib-only)
- `from bootstrap.config import load_settings` → carga `config/config.example.toml` a `WyssSettings` con 7 reglas deny (BUILTIN_DENY + 0, deny del ejemplo comentada)

## Success Criteria

- **SC5** ✓ — config.toml se valida con Pydantic al boot; config inválida = fail-fast con error legible que nombra el campo (loc).
- **POL-04/POL-05** ✓ — los umbrales de agregación (`file_count_b/c`, `dir_count_c`, `delete_count_d`, `sensitive_dirs`) llegan desde config validada a `AggregateThresholds`.
- **Denylist aditiva (regla #2)** ✓ — `PolicyRules.deny = BUILTIN_DENY + config`; sin ruta para vaciar built-ins; `test_denylist_is_additive` lo verifica.
- **Pydantic contenido** ✓ — `import-linter` 2 kept 0 broken; `test_no_pydantic_in_settings` asserta que el dominio no es `BaseModel`.

## Threat Model Coverage

| Threat ID | Disposition | Evidencia |
|-----------|-------------|-----------|
| T-01-06-T (tampering: typo en config) | mitigate ✓ | `extra="forbid"` en todos los modelos; tests `test_extra_key_*` y `test_deny_rule_extra_key_rejected` (typo en deny rule aborta el boot, error nombra el campo) |
| T-01-06-EoP (vaciar denylist desde config) | mitigate ✓ | `deny = BUILTIN_DENY + config`; `test_denylist_is_additive` asserta que todos los ids built-in persisten |
| T-01-06-DoS (config inexistente/mal formada) | mitigate ✓ | `ConfigError` con mensaje accionable; tests `test_config_not_found` y `test_malformed_toml` (no traceback crudo) |

## Deviations from Plan

None - plan executed exactly as written.

Notas de implementación dentro de lo previsto por el plan:
- **[Decisión de diseño, ya prevista en config_spec]** Se levanta `ConfigError` (nueva subclase de `WyssError`) en vez de `sys.exit`, para que el fail-fast sea testeable con `pytest.raises`. El `sys.exit` queda para el caller CLI de Fase 5.
- `TomlConfigStore` cumple el Protocol `ConfigStore` por duck typing — no se importa el Protocol, evitando acoplamiento.

## Known Stubs

None — el stub previo (`src/bootstrap/__init__.py` de 1 línea de docstring) quedó resuelto: ahora re-exporta `load_settings` y `TomlConfigStore` reales.

## Commits

- `e8f6ba9` feat(01-06): load_settings — frontera Pydantic->dominio fail-fast
- `612ec25` test(01-06): bootstrap config — carga válida, fail-fast legible, denylist aditiva

## Self-Check: PASSED

Todos los archivos creados existen en disco; los 2 commits (e8f6ba9, 612ec25) están en el historial.
