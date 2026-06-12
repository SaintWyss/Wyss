---
plan: 03-02
status: complete
---

# Plan 03-02 Summary

**One-liner:** Se construyó el `index.db` WAL fail-fast y el `StateStore` incremental/reanudable para el pipeline de ingesta.

## What was built
Task 1: `open_index_db` replica el patrón de gateway sin importar gateway: pre-crea `index.db` con modo 0600, aplica chmod best-effort con warning, ejecuta PRAGMAs y falla rápido con `IndexIntegrityError` si `journal_mode` no queda en `wal`. También se agregó DDL idempotente para `file_state`, `chunks` e índices.

Task 2: `StateStore` abre vía `open_index_db`, calcula sha256 en bloques, implementa `needs_reindex` con fast path size+mtime sin recalcular hash para archivos `embedded`, re-hash solo cuando cambian size/mtime, transiciones con commit inmediato, reintentos `failed` hasta `max_attempts`, `list_resumable`, `counts_by_status`, context manager y lookup de registros.

## Key files
### Created
- `src/knowledge/db.py` — apertura de `index.db` con WAL fail-fast, permisos 0600 y `IndexIntegrityError`.
- `src/knowledge/index_schema.py` — PRAGMAs y DDL idempotente de `file_state`, `chunks` e índices.
- `src/knowledge/state_store.py` — store SQLite incremental/reanudable con commits por transición.
- `tests/knowledge/test_state_store.py` — cobertura de WAL, schema, fast path incremental, rehash, crash-resume, reintentos y aislamiento `(path, kb_id)`.
- `.planning/phases/03-pipeline-de-ingesta/03-02-SUMMARY.md` — resumen de ejecución del plan.

### Modified
- Ninguno.

## Decisions
- `StateStore` acepta `Path | str` y persiste paths como texto para que el pipeline pueda usar objetos `Path` sin acoplar el schema.
- Las transiciones que no reciben `size`/`mtime` usan la fila existente o `stat()` del archivo; si no existe, insertan `0`/`0.0` para conservar el contrato de transición simple.
- `mark_failed` guarda solo el mensaje truncado a 500 caracteres e incrementa `attempts` en SQLite.
- `counts_by_status` acepta un scope opcional de paths para resúmenes de corrida, además del conteo completo por `kb_id`.

## Self-Check
- pytest: 207 passed / 2 skipped
- mypy: Success: no issues found in 93 source files
- ruff: All checks passed
- lint-imports: Contracts: 2 kept, 0 broken
