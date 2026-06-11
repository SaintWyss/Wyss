"""DDL del log de auditoría: tabla append-only + índices + triggers + PRAGMAs (Pattern 4).

El esquema lo crea el propio adapter al construir (todo IF NOT EXISTS — idempotente);
no hay migración externa. Append-only estructural: ni un bug puede reescribir historia.
"""

import sqlite3

# PRAGMAs ejecutados al abrir la conexión.
# - journal_mode=WAL: concurrencia lectura/escritura (verificado fail-fast por el logger).
# - synchronous=FULL: audit; pérdida-en-crash inaceptable — fsync por commit.
# - busy_timeout=5000: tolera bloqueos breves entre conexiones concurrentes.
PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA busy_timeout=5000",
)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS audit_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id    TEXT NOT NULL UNIQUE,
  task_id     TEXT,
  actor_type  TEXT NOT NULL,
  actor_id    TEXT NOT NULL,
  event_type  TEXT NOT NULL,
  message     TEXT NOT NULL,
  payload     TEXT NOT NULL DEFAULT '{}',
  created_at  TEXT NOT NULL
)
"""

CREATE_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_events(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_audit_type_time "
    "ON audit_events(event_type, created_at)",
)

# Append-only estructural: ni siquiera un bug puede reescribir o borrar historia.
CREATE_TRIGGERS: tuple[str, ...] = (
    "CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END",
    "CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events "
    "BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END",
)


def apply_schema(conn: sqlite3.Connection) -> None:
    """Crea tabla, índices y triggers append-only (idempotente — todo IF NOT EXISTS)."""
    conn.execute(CREATE_TABLE)
    for stmt in CREATE_INDEXES:
        conn.execute(stmt)
    for stmt in CREATE_TRIGGERS:
        conn.execute(stmt)
    conn.commit()
