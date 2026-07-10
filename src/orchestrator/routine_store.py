"""SQLite store para rutinas programadas (SCHED-03)."""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from core.domain.errors import AuditIntegrityError

ROUTINE_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS routines (
  id              TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  schedule_kind   TEXT NOT NULL,
  schedule_expr   TEXT NOT NULL,
  plan_json       TEXT NOT NULL,
  catch_up        INTEGER NOT NULL DEFAULT 1,
  status          TEXT NOT NULL DEFAULT 'active',
  created_at      TEXT NOT NULL,
  last_fired_at   TEXT,
  last_outcome    TEXT
)
"""

CREATE_INDEX = "CREATE INDEX IF NOT EXISTS idx_routines_status ON routines(status)"

_INSERT = (
    "INSERT INTO routines "
    "(id, name, schedule_kind, schedule_expr, plan_json, catch_up, status, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, 'active', ?)"
)


@dataclass(frozen=True, slots=True)
class Routine:
    """Fila durable de `routines`."""

    id: str
    name: str
    schedule_kind: str
    schedule_expr: str
    plan_json: str
    catch_up: bool
    status: str
    created_at: str
    last_fired_at: str | None
    last_outcome: str | None


class RoutineStore:
    """Store durable de rutinas sobre SQLite con WAL fail-fast."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        journal_mode: str | None = None
        for pragma in ROUTINE_PRAGMAS:
            row = self._conn.execute(pragma).fetchone()
            if pragma.endswith("WAL") and row is not None:
                journal_mode = str(row[0]).lower()
        if journal_mode != "wal":
            self._conn.close()
            raise AuditIntegrityError(
                f"routine_store en {db_path}: PRAGMA journal_mode retorno "
                f"{journal_mode!r}, se esperaba 'wal'. WAL no esta disponible "
                "sobre este filesystem."
            )
        self._apply_schema()

    def add(
        self,
        name: str,
        schedule_kind: str,
        schedule_expr: str,
        plan_json: str,
        catch_up: bool = True,
    ) -> str:
        """Persiste una rutina activa y devuelve su routine_id."""
        routine_id = uuid.uuid4().hex
        created_at = datetime.now(UTC).isoformat()
        self._conn.execute(
            _INSERT,
            (
                routine_id,
                name,
                schedule_kind,
                schedule_expr,
                plan_json,
                int(catch_up),
                created_at,
            ),
        )
        self._conn.commit()
        return routine_id

    def get(self, routine_id: str) -> Routine | None:
        """Carga una rutina por id, o None si no existe."""
        row = self._conn.execute(
            "SELECT * FROM routines WHERE id=?", (routine_id,)
        ).fetchone()
        return _row_to_routine(row)

    def list_all(self) -> list[Routine]:
        """Devuelve todas las rutinas ordenadas por creacion."""
        rows = self._conn.execute(
            "SELECT * FROM routines ORDER BY created_at, id"
        ).fetchall()
        return [_routine_from_row(row) for row in rows]

    def list_active(self) -> list[Routine]:
        """Devuelve todas las rutinas con status active."""
        rows = self._conn.execute(
            "SELECT * FROM routines WHERE status='active' ORDER BY created_at, id"
        ).fetchall()
        return [_routine_from_row(row) for row in rows]

    def pause(self, routine_id: str) -> bool:
        """Pausa una rutina existente."""
        cur = self._conn.execute(
            "UPDATE routines SET status='paused' WHERE id=?", (routine_id,)
        )
        self._conn.commit()
        return cur.rowcount == 1

    def resume(self, routine_id: str) -> bool:
        """Reanuda una rutina existente."""
        cur = self._conn.execute(
            "UPDATE routines SET status='active' WHERE id=?", (routine_id,)
        )
        self._conn.commit()
        return cur.rowcount == 1

    def delete(self, routine_id: str) -> bool:
        """Borra una rutina por id."""
        cur = self._conn.execute("DELETE FROM routines WHERE id=?", (routine_id,))
        self._conn.commit()
        return cur.rowcount == 1

    def mark_fired(self, routine_id: str, fired_at: str, outcome: str) -> bool:
        """Registra el ultimo disparo en una unica escritura atomica."""
        cur = self._conn.execute(
            "UPDATE routines SET last_fired_at=?, last_outcome=? WHERE id=?",
            (fired_at, outcome, routine_id),
        )
        self._conn.commit()
        return cur.rowcount == 1

    def close(self) -> None:
        """Cierra la conexion SQLite subyacente."""
        self._conn.close()

    def __enter__(self) -> "RoutineStore":
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


def _row_to_routine(row: sqlite3.Row | None) -> Routine | None:
    if row is None:
        return None
    return _routine_from_row(row)


def _routine_from_row(row: sqlite3.Row) -> Routine:
    return Routine(
        id=str(row["id"]),
        name=str(row["name"]),
        schedule_kind=str(row["schedule_kind"]),
        schedule_expr=str(row["schedule_expr"]),
        plan_json=str(row["plan_json"]),
        catch_up=bool(row["catch_up"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        last_fired_at=row["last_fired_at"],
        last_outcome=row["last_outcome"],
    )
