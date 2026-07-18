"""SQLite store para memoria durable del owner (MEM-01 / MEM-03)."""

import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Literal, cast

from core.domain.errors import AuditIntegrityError
from core.domain.memory import MemoryFact

MEMORY_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS memory_facts (
  id          TEXT PRIMARY KEY,
  category    TEXT NOT NULL,
  value       TEXT NOT NULL,
  tier        TEXT NOT NULL DEFAULT 'owner',
  source      TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
)
"""

CREATE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_memory_facts_category_updated "
    "ON memory_facts(category, updated_at DESC)"
)

_INSERT = (
    "INSERT INTO memory_facts "
    "(id, category, value, tier, source, created_at, updated_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)


class MemoryStore:
    """Store durable de hechos de memoria sobre SQLite con WAL fail-fast."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        journal_mode: str | None = None
        for pragma in MEMORY_PRAGMAS:
            row = self._conn.execute(pragma).fetchone()
            if pragma.endswith("WAL") and row is not None:
                journal_mode = str(row[0]).lower()
        if journal_mode != "wal":
            self._conn.close()
            raise AuditIntegrityError(
                f"memory_store en {db_path}: PRAGMA journal_mode retorno "
                f"{journal_mode!r}, se esperaba 'wal'. WAL no esta disponible "
                "sobre este filesystem."
            )
        self._apply_schema()

    def remember(
        self,
        category: str,
        value: str,
        tier: Literal["owner", "external"],
        source: str,
    ) -> str:
        """Persiste un hecho de memoria y devuelve su fact_id."""
        fact_id = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            _INSERT,
            (
                fact_id,
                category,
                value,
                tier,
                source,
                now,
                now,
            ),
        )
        self._conn.commit()
        return fact_id

    def recall(self, category: str | None = None, limit: int = 50) -> list[MemoryFact]:
        """Recuerda hechos recientes, opcionalmente filtrados por categoria."""
        if category is None:
            rows = self._conn.execute(
                "SELECT * FROM memory_facts ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM memory_facts WHERE category=? ORDER BY updated_at DESC LIMIT ?",
                (category, limit),
            ).fetchall()
        return [_fact_from_row(row) for row in rows]

    def list_all(self) -> list[MemoryFact]:
        """Devuelve todos los hechos ordenados por actualizacion descendente."""
        rows = self._conn.execute("SELECT * FROM memory_facts ORDER BY updated_at DESC").fetchall()
        return [_fact_from_row(row) for row in rows]

    def edit(self, fact_id: str, value: str) -> bool:
        """Edita el valor de un hecho existente."""
        updated_at = datetime.now(UTC).isoformat()
        cur = self._conn.execute(
            "UPDATE memory_facts SET value=?, updated_at=? WHERE id=?",
            (value, updated_at, fact_id),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def forget(self, fact_id: str) -> bool:
        """Borra un hecho de memoria por id."""
        cur = self._conn.execute("DELETE FROM memory_facts WHERE id=?", (fact_id,))
        self._conn.commit()
        return cur.rowcount == 1

    def close(self) -> None:
        """Cierra la conexion SQLite subyacente."""
        self._conn.close()

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _apply_schema(self) -> None:
        self._conn.execute(CREATE_TABLE)
        self._conn.execute(CREATE_INDEX)
        self._conn.commit()


def _fact_from_row(row: sqlite3.Row) -> MemoryFact:
    return MemoryFact(
        id=str(row["id"]),
        category=str(row["category"]),
        value=str(row["value"]),
        tier=cast(Literal["owner", "external"], str(row["tier"])),
        source=str(row["source"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
