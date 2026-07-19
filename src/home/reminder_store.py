"""SQLite store de recordatorios del hogar (contrato Home Edge).

El Edge consume `GET /api/home/reminders` y valida un shape estricto:
`{"revision": int > 0, "reminders": [...]}` con timezone idéntica a la
configurada en el panel. Este store es la única autoridad de escritura;
el Edge solo proyecta.
"""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import TracebackType

REMINDER_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS reminders (
  id              TEXT PRIMARY KEY,
  text            TEXT NOT NULL,
  due_at          TEXT NOT NULL,
  timezone        TEXT NOT NULL,
  recurrence      TEXT,
  status          TEXT NOT NULL DEFAULT 'active',
  revision        INTEGER NOT NULL,
  notification_id TEXT,
  created_at      TEXT NOT NULL
)
"""

_CREATE_META = """
CREATE TABLE IF NOT EXISTS reminder_meta (
  key   TEXT PRIMARY KEY,
  value INTEGER NOT NULL
)
"""

_MAX_SNAPSHOT = 250


@dataclass(frozen=True, slots=True)
class Reminder:
    reminder_id: str
    text: str
    due_at: str
    timezone: str
    recurrence: str | None
    status: str
    revision: int
    notification_id: str | None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.reminder_id,
            "text": self.text,
            "due_at": self.due_at,
            "timezone": self.timezone,
            "status": self.status,
            "revision": self.revision,
        }
        if self.recurrence is not None:
            payload["recurrence"] = self.recurrence
        if self.notification_id is not None:
            payload["notification_id"] = self.notification_id
        return payload


class ReminderStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        for pragma in REMINDER_PRAGMAS:
            self._conn.execute(pragma)
        self._apply_schema()

    def add(
        self,
        *,
        text: str,
        due_at: str,
        timezone: str,
        recurrence: str | None = None,
    ) -> Reminder:
        parsed = datetime.fromisoformat(due_at)
        if parsed.tzinfo is None:
            raise ValueError("due_at debe incluir zona horaria (ISO-8601 con offset)")
        if not text or len(text) > 500:
            raise ValueError("text debe tener entre 1 y 500 caracteres")
        reminder_id = str(uuid.uuid4())
        with self._conn:
            revision = self._bump_revision()
            self._conn.execute(
                "INSERT INTO reminders "
                "(id, text, due_at, timezone, recurrence, status, revision, created_at) "
                "VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
                (
                    reminder_id,
                    text,
                    due_at,
                    timezone,
                    recurrence,
                    revision,
                    datetime.now(tz=parsed.tzinfo).isoformat(),
                ),
            )
        reminder = self.get(reminder_id)
        assert reminder is not None
        return reminder

    def complete(self, reminder_id: str) -> bool:
        with self._conn:
            revision = self._bump_revision()
            cursor = self._conn.execute(
                "UPDATE reminders SET status='completed', revision=? "
                "WHERE id=? AND status='active'",
                (revision, reminder_id),
            )
        return cursor.rowcount == 1

    def delete(self, reminder_id: str) -> bool:
        with self._conn:
            self._bump_revision()
            cursor = self._conn.execute("DELETE FROM reminders WHERE id=?", (reminder_id,))
        return cursor.rowcount == 1

    def get(self, reminder_id: str) -> Reminder | None:
        row = self._conn.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,)).fetchone()
        return None if row is None else _from_row(row)

    def snapshot(self, timezone: str) -> tuple[int, list[Reminder]]:
        """Revision global + reminders de esa timezone (contrato del Edge)."""
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE timezone=? ORDER BY due_at ASC LIMIT ?",
            (timezone, _MAX_SNAPSHOT),
        ).fetchall()
        return self.revision(), [_from_row(row) for row in rows]

    def list_all(self) -> list[Reminder]:
        rows = self._conn.execute("SELECT * FROM reminders ORDER BY due_at ASC").fetchall()
        return [_from_row(row) for row in rows]

    def revision(self) -> int:
        row = self._conn.execute("SELECT value FROM reminder_meta WHERE key='revision'").fetchone()
        return int(row["value"])

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ReminderStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _bump_revision(self) -> int:
        self._conn.execute("UPDATE reminder_meta SET value = value + 1 WHERE key='revision'")
        return self.revision()

    def _apply_schema(self) -> None:
        with self._conn:
            self._conn.execute(_CREATE_TABLE)
            self._conn.execute(_CREATE_META)
            self._conn.execute(
                "INSERT OR IGNORE INTO reminder_meta (key, value) VALUES ('revision', 1)"
            )


def _from_row(row: sqlite3.Row) -> Reminder:
    return Reminder(
        reminder_id=row["id"],
        text=row["text"],
        due_at=row["due_at"],
        timezone=row["timezone"],
        recurrence=row["recurrence"],
        status=row["status"],
        revision=row["revision"],
        notification_id=row["notification_id"],
    )
