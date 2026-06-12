"""DDL de traces.db: tabla consultable + índices + PRAGMAs (espejo de audit/schema.py).

A diferencia del audit log, traces NO es append-only: se purga por retención (default 90d,
D-22). Por eso COPIA los PRAGMAS y el patrón `apply_schema` de `audit/schema.py`, pero OMITE
los triggers de inmutabilidad. DB separada de audit.db y de los datos de usuario (D-22).

También define la tabla `spend_ledger` que alimenta el gate de costo (GATE-04): el estado de
gasto mensual vive en la misma DB de gateway (Open Question 3) — una sola DB para traces+gasto.
"""

import sqlite3

# PRAGMAs ejecutados al abrir la conexión (idénticos a audit/schema.py).
# - journal_mode=WAL: concurrencia lectura/escritura (verificado fail-fast por TraceStore).
# - synchronous=FULL: durabilidad por commit (fsync); el trace de costo no puede perderse.
# - busy_timeout=5000: tolera bloqueos breves entre conexiones concurrentes.
PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA busy_timeout=5000",
)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS traces (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  trace_id    TEXT NOT NULL UNIQUE,
  task_id     TEXT,
  agent_id    TEXT,
  tier        TEXT,
  purpose     TEXT,
  prompt      TEXT NOT NULL,
  output      TEXT NOT NULL,
  tokens_in   INTEGER NOT NULL,
  tokens_out  INTEGER NOT NULL,
  cost_usd    REAL NOT NULL,
  latency_ms  INTEGER NOT NULL,
  created_at  TEXT NOT NULL
)
"""

CREATE_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_traces_task ON traces(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_traces_purpose_time "
    "ON traces(purpose, created_at)",
)

# Estado durable del gate de costo (GATE-04): un asiento por llamada registrada.
# cost_usd_local gobierna el gate (D-24); cost_usd_provider se guarda solo comparativo.
CREATE_SPEND_LEDGER = """
CREATE TABLE IF NOT EXISTS spend_ledger (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id           TEXT NOT NULL,
  model_alias        TEXT NOT NULL,
  tokens_in          INTEGER NOT NULL,
  tokens_out         INTEGER NOT NULL,
  cost_usd_local     REAL NOT NULL,
  cost_usd_provider  REAL,
  created_at         TEXT NOT NULL
)
"""

CREATE_SPEND_INDEXES: tuple[str, ...] = (
    "CREATE INDEX IF NOT EXISTS idx_spend_time ON spend_ledger(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_spend_agent_time "
    "ON spend_ledger(agent_id, created_at)",
)


def apply_schema(conn: sqlite3.Connection) -> None:
    """Crea tablas e índices de traces + spend_ledger (idempotente — todo IF NOT EXISTS).

    Sin triggers append-only: traces se purga por retención (D-22), a diferencia de audit.
    """
    conn.execute(CREATE_TABLE)
    for stmt in CREATE_INDEXES:
        conn.execute(stmt)
    conn.execute(CREATE_SPEND_LEDGER)
    for stmt in CREATE_SPEND_INDEXES:
        conn.execute(stmt)
    conn.commit()
