"""DDL de index.db: estado incremental de archivos + contenido canónico de chunks.

`file_state` es el eje de reanudabilidad del pipeline de ingesta: cada transición se
commitea por archivo desde `StateStore`. `chunks` queda definido acá como tabla de contenido
canónico para el adapter FTS5 de planes posteriores; la virtual table y sus triggers NO viven
en este plan.
"""

import sqlite3

# PRAGMAs ejecutados al abrir la conexión (idénticos a gateway/traces_schema.py).
# - journal_mode=WAL: concurrencia lectura/escritura, verificado fail-fast al abrir.
# - synchronous=FULL: durabilidad por commit; el estado incremental no puede perderse.
# - busy_timeout=5000: tolera bloqueos breves entre conexiones concurrentes.
PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA busy_timeout=5000",
)

CREATE_FILE_STATE = """
CREATE TABLE IF NOT EXISTS file_state (
  path        TEXT NOT NULL,
  kb_id       TEXT NOT NULL,
  size        INTEGER NOT NULL,
  mtime       REAL NOT NULL,
  sha256      TEXT,
  status      TEXT NOT NULL DEFAULT 'pending',
  attempts    INTEGER NOT NULL DEFAULT 0,
  error       TEXT,
  indexed_at  REAL,
  updated_at  REAL NOT NULL,
  PRIMARY KEY (path, kb_id)
)
"""

CREATE_CHUNKS = """
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id     TEXT PRIMARY KEY,
  kb_id        TEXT NOT NULL,
  source_path  TEXT NOT NULL,
  position     INTEGER NOT NULL,
  text         TEXT NOT NULL
)
"""

CREATE_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_file_state_status ON file_state(status)",
    "CREATE INDEX IF NOT EXISTS idx_file_state_kb ON file_state(kb_id)",
)


def apply_index_schema(conn: sqlite3.Connection) -> None:
    """Crea tablas e índices de index.db (idempotente: todo IF NOT EXISTS)."""
    conn.execute(CREATE_FILE_STATE)
    conn.execute(CREATE_CHUNKS)
    for stmt in CREATE_INDEXES:
        conn.execute(stmt)
    conn.commit()
