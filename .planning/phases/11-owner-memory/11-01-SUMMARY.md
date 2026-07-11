---
phase: 11-owner-memory
plan: 01
status: complete
completed: 2026-07-10
requirements: [MEM-01, MEM-03]
builder: codex (codex-gsd-exec) — verificado y commiteado por Claude
---

# 11-01 Summary — Fundación: MemoryFact + ports + MemoryStore

## Qué se hizo

- `core/domain/memory.py`: `MemoryFact` frozen+slots con `tier: Literal["owner","external"]` (MEM-03: el tier vive en el dominio desde el día 1).
- `core/ports/memory.py`: DOS protocols — `MemoryPort` (recall, lectura para el orquestador) y `MemoryAdmin` (CRUD para el daemon). Core sigue stdlib-only.
- `src/memory/store.py`: `MemoryStore` — molde exacto routine_store (WAL guard AuditIntegrityError, sqlite3.Row, ISO UTC, rowcount, context manager) + índice `(category, updated_at DESC)` para recall. Satisface ambos protocols por duck typing.
- `pyproject.toml`: `memory` registrado como wheel/root package + contratos import-linter (pureza core + independencia, junto a notion).
- `tests/memory/`: 11 tests (CRUD round-trip con tier, list, forget/edit rowcount, guard WAL).

## Verificación (fuera del sandbox)

**607 passed** (+11) / mypy 0 (228 archivos) / ruff 0 / import-linter 2/2.

## Deviations

Ninguna.
