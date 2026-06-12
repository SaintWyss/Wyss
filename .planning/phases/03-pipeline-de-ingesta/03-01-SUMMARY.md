---
plan: 03-01
status: complete
---

# Plan 03-01 Summary

**One-liner:** Se construyó la fundación de ingesta: dependencias, vocabulario de dominio, errores, config `[ingest]` Pydantic→frozen y scaffolding de tests.

## What was built
Task 1: Se agregaron y verificaron las 9 dependencias de extracción/indexación: `pymupdf`, `python-docx`, `openpyxl`, `python-magic`, `chromadb`, `rich`, `typer`, `pillow`, `exifread`. No se agregaron `pymediainfo` ni `detect-secrets`.

Task 2: Se agregaron `FileStatus`, `IngestSettings`, `FileRecord`, `EstimateResult` e `IngestRunResult` como tipos de dominio frozen/stdlib-only. También se agregaron `IndexIntegrityError`, `ExtractionError`, `UnsupportedFileError` y `SecretFileExcluded`, con metadata segura y sin aceptar contenido sensible.

Task 3: Se agregó la sección `[ingest]` en bootstrap con `IngestConfigModel(extra="forbid")`, conversión a `IngestSettings` con tuplas, `WyssSettings.ingest`, y los paquetes/fixtures base para tests de ingesta y CLI.

## Key files
### Created
- `tests/knowledge/__init__.py` — paquete de tests de ingesta.
- `tests/knowledge/conftest.py` — fixtures `index_db_path`, `make_source_file`, `audit` y re-export de fakes.
- `tests/knowledge/extractors/__init__.py` — paquete de tests para extractores.
- `tests/knowledge/test_scaffolding.py` — smoke test mínimo para validar fixtures y hacer pasar el collect-only del plan.
- `tests/cli/__init__.py` — paquete de tests CLI.

### Modified
- `pyproject.toml` — dependencias de extracción/indexación agregadas.
- `uv.lock` — lockfile actualizado por `uv add`.
- `src/core/domain/knowledge.py` — `FileStatus` y dataclasses frozen de ingesta.
- `src/core/domain/errors.py` — excepciones de dominio de ingesta.
- `src/core/domain/__init__.py` — re-export de nuevos símbolos.
- `src/core/domain/config.py` — `WyssSettings.ingest` con `default_factory=IngestSettings`.
- `src/bootstrap/config.py` — `IngestConfigModel`, `_to_ingest_settings()` y wiring en `_to_settings()`.

## Decisions
- Se usó `UV_CACHE_DIR=/tmp/wyss-uv-cache` para las verificaciones porque el cache default de `uv` bajo `/home/saintwyss/.cache/uv` es read-only en este executor.
- Se agregó un smoke test mínimo en `tests/knowledge` porque `pytest tests/knowledge tests/cli --collect-only -q` falla con exit 5 si esos paquetes solo contienen `conftest.py` y `__init__.py`.

## Self-Check
- pytest: 196 passed / 2 skipped
- mypy: Success: no issues found in 89 source files
- ruff: All checks passed
- lint-imports: Contracts: 2 kept, 0 broken