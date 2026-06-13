---
phase: 03-pipeline-de-ingesta
plan: 03-06
status: complete
requirements_covered:
  - KNOW-01
  - KNOW-03
  - KNOW-06
  - KNOW-07
  - KNOW-08
---

# Plan 03-06 Summary

**One-liner:** Se construyó `IngestPipeline` como orquestador async de scan, extracción, secret-gate, FTS5, embeddings, estado reanudable, `estimate()` y `dry_run()`.

## What was built
Task 1: `IngestPipeline.run()` compone scanner, state store, secret filter, registry, chunker, FTS, embedder, vector index y audit por DI keyword-only. El flujo aplica `check_path` antes de abrir archivos y `check_content` antes de tocar FTS/vector; las exclusiones quedan `excluded_secret` y generan `AuditEvent` con `pattern_name`/`layer`, nunca con el secreto.

Task 1 tambien cubre reanudabilidad e incrementalidad con `needs_reindex` y commits por archivo del `StateStore`: archivos ya `embedded` no se reprocesan, errores `ExtractionError` quedan `failed` sin abortar, formatos no soportados quedan `skipped_unsupported`, y errores sistemicos como root inexistente propagan. Si el embedder falla por `httpx.TransportError`, la corrida no aborta, el archivo queda `extracted`, FTS queda poblado y el resultado incluye un aviso.

Task 2: `estimate()` recorre via scanner/state-check sin resolver ni invocar extractores, proyecta archivos, bytes, chunks, tiempo de embedding local y `cost_usd=0.0`. `dry_run()` lista `(path, "nuevo"|"modificado")` sin escribir estado ni indices. La extensibilidad queda verificada registrando un extractor nuevo para `application/x-new-format` sin cambios en `pipeline.py`.

## Key files
### Created
- `src/knowledge/pipeline.py` - `IngestPipeline`, protocolos locales para scanner/state store, `run`, `estimate` y `dry_run`.
- `tests/knowledge/test_pipeline.py` - cobertura dirigida de secretos, errores por archivo, Ollama caido, crash-resume, errores sistemicos, estimate/dry-run y extractor nuevo.
- `.planning/phases/03-pipeline-de-ingesta/03-06-SUMMARY.md` - resumen de ejecucion del plan.

### Modified
- `src/core/domain/knowledge.py` - `IngestRunResult.warnings: tuple[str, ...] = ()` para reportar degradacion no fatal de embeddings sin romper constructores existentes.

## Deviations From Plan
- Se agrego un campo defaulted `warnings` a `IngestRunResult`. El plan pedia que Ollama caido dejara el archivo `extracted` y devolviera un aviso en el resultado; el contrato existente no tenia donde transportarlo. El cambio es aditivo y mantiene compatibilidad con los tests existentes.
- La verificacion se ejecuto con `UV_CACHE_DIR=/tmp/uv-cache` porque el sandbox no permite escribir en el cache default de `uv` bajo `/home`.

## Verification Evidence
Command:
```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/knowledge/test_pipeline.py -x -q && UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q && UV_CACHE_DIR=/tmp/uv-cache uv run mypy && UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests && UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
```

Output:
```text
10 passed in 0.42s
253 passed, 2 skipped in 1.59s
Success: no issues found in 115 source files
All checks passed!
Contracts: 2 kept, 0 broken.
```

## Acceptance Coverage
- `test_planted_secret_not_indexed`: secreto `sk-ant-...` no aparece en `chunks`, no llega al `FakeVectorIndex`, estado `excluded_secret`, audit con `pattern_name` sin valor secreto.
- `test_env_file_excluded_by_path`: `.env` se excluye por capa path sin llamar extractor.
- `test_extraction_error_does_not_abort`: un archivo falla `failed` y otro queda procesado.
- `test_ollama_down_leaves_extracted`: `httpx.ConnectError` del embedder deja estado `extracted` y no aborta.
- `test_crash_resume`: rerun con estado persistido no reprocesa archivos ya `embedded`.
- `test_systemic_error_propagates`: root inexistente propaga `NotADirectoryError`.
- `test_estimate_no_extraction`: `estimate()` no llama extractores y retorna `cost_usd=0.0`.
- `test_estimate_does_not_write`: `estimate()` no escribe estado ni crea `index.db`.
- `test_dry_run_lists_reasons`: `dry_run()` devuelve razones `nuevo`/`modificado` sin escribir.
- `test_new_extractor_no_pipeline_change`: registrar un extractor nuevo procesa el media type sin tocar el pipeline.
