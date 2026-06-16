"""DDL del ledger de finanzas: tabla `transacciones` + índice de fecha + PRAGMAs.

El esquema lo crea el propio adapter al construir (todo IF NOT EXISTS — idempotente);
no hay migración externa. Espejo estructural de `audit/schema.py`, pero con
`synchronous=NORMAL` (no FULL): el ledger no es un log append-only de auditoría, así que
el costo de fsync-por-commit no se justifica (AI-SPEC §3 / PATTERNS).
"""

import sqlite3

# PRAGMAs ejecutados al abrir la conexión.
# - journal_mode=WAL: concurrencia lectura/escritura (verificado fail-fast por el store).
# - synchronous=NORMAL: durabilidad razonable sin fsync por commit (no es audit append-only).
# - busy_timeout=5000: tolera bloqueos breves entre conexiones concurrentes.
PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS transacciones (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo        TEXT NOT NULL,
  monto       REAL NOT NULL,
  fecha       TEXT NOT NULL,
  fuente      TEXT,
  categoria   TEXT,
  created_at  TEXT NOT NULL
)
"""

CREATE_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_transacciones_fecha ON transacciones(fecha)",
)


def apply_schema(conn: sqlite3.Connection) -> None:
    """Crea la tabla `transacciones` y su índice de fecha (idempotente — todo IF NOT EXISTS)."""
    conn.execute(CREATE_TABLE)
    for stmt in CREATE_INDEXES:
        conn.execute(stmt)
    conn.commit()
