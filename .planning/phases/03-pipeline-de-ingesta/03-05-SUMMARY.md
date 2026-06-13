---
plan: 03-05
status: complete
---

# Plan 03-05 Summary

**One-liner:** Se construyeron el chunker configurable, el índice FTS5 external-content y el índice vectorial ChromaDB con colección aislada por kb_id.

## What was built
Task 1: `TokenChunker` fragmenta texto/código/markdown en ventanas aproximadas por caracteres usando los tamaños de tokens configurados, con overlap de 10% por default, posiciones secuenciales e ids determinísticos. Para CSV/XLSX usa grupos de filas sin overlap y descarta texto vacío o whitespace-only.

Task 2: `apply_fts_schema` crea `chunks_fts` como FTS5 external content sobre `chunks` y agrega triggers `chunks_ai`, `chunks_ad`, `chunks_au`. `FTS5Index` hace upsert parametrizado en `chunks`, busca con `MATCH`, filtra por `kb_ids`, devuelve `Hit` de dominio y mantiene el índice sincronizado por triggers.

Task 3: `ChromaVectorIndex` agrupa upserts por `kb_id`, usa `client.get_or_create_collection(name=kb_id, metadata=...)`, guarda embeddings precomputados y consulta colecciones separadas para preservar el aislamiento KNOW-11.

## Key files
### Created
- `src/knowledge/chunker.py` — `TokenChunker` implementando el port `Chunker`.
- `src/knowledge/fts_schema.py` — DDL idempotente de FTS5 external content + triggers.
- `src/knowledge/fts_index.py` — `FTS5Index` implementando el port `FullTextIndex`.
- `src/knowledge/vector_index.py` — `ChromaVectorIndex` implementando el port `VectorIndex`.
- `tests/knowledge/test_chunker.py` — cobertura del chunker: overlap, vacío, ids, posiciones y tabular.
- `tests/knowledge/test_fts_index.py` — cobertura de FTS5: upsert/search, filtro por kb_id, external content, triggers e idempotencia.
- `tests/knowledge/test_vector_index.py` — cobertura ChromaDB: colecciones separadas, búsqueda, upsert idempotente y metadata.
- `.planning/phases/03-pipeline-de-ingesta/03-05-SUMMARY.md` — resumen de ejecución del plan.
### Modified
- Ninguno.

## Decisions
- El chunker usa la aproximación indicada por research: 1 token ~= 4 caracteres, evitando dependencias externas.
- La búsqueda FTS normaliza la consulta a términos quoted para que puntuación como guiones no rompa la gramática de `MATCH`, manteniendo SQL parametrizado.
- `ChromaVectorIndex` tipa el cliente como `chromadb.api.ClientAPI` porque `chromadb.PersistentClient` es una factory que devuelve esa interfaz.

## Self-Check
- pytest: 243 passed / 2 skipped
- mypy: Success: no issues found in 113 source files
- ruff: All checks passed!
- lint-imports: Contracts: 2 kept, 0 broken
