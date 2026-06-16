"""Paquete `ledger` — adapter de persistencia del ledger de finanzas (Fase 8).

Capa de infraestructura independiente: implementa `core.ports.ledger.LedgerPort` con un
store SQLite propio (WAL fail-fast, espejo de `gateway.db`). El núcleo NUNCA importa este
paquete — el contrato import-linter `core es puro` lo garantiza, y la independencia entre
capas impide que `ledger` importe otra infra (solo `core`).

Wave 0: el paquete existe vacío para que import-linter resuelva el root_package y los
contratos se evalúen (se llenan en Plan 02 con `sqlite_store.SqliteLedgerStore`).
"""
