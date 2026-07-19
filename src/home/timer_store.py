"""SQLite store de timers del hogar (contrato Home Edge).

El Edge consume `GET /api/home/timers` con shape estricto
`{"revision": int > 0, "timers": [...]}`:
- `running` exige `deadline_at` tz-aware;
- `completed` exige `completion_id` durable;
- `0 <= remaining_seconds <= duration_seconds`.
Un timer `running` cuyo deadline venció se auto-completa al leer el
snapshot (el Edge nunca ejecuta timers, solo proyecta).
"""

import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType

TIMER_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS timers (
  id               TEXT PRIMARY KEY,
  label            TEXT NOT NULL,
  status           TEXT NOT NULL,
  revision         INTEGER NOT NULL,
  duration_seconds INTEGER NOT NULL,
  deadline_at      TEXT,
  paused_remaining INTEGER,
  preset           TEXT,
  completion_id    TEXT,
  notification_id  TEXT,
  created_at       TEXT NOT NULL
)
"""

_CREATE_META = """
CREATE TABLE IF NOT EXISTS timer_meta (
  key   TEXT PRIMARY KEY,
  value INTEGER NOT NULL
)
"""

_MAX_SNAPSHOT = 500


@dataclass(frozen=True, slots=True)
class Timer:
    timer_id: str
    label: str
    status: str
    revision: int
    duration_seconds: int
    remaining_seconds: int
    deadline_at: str | None
    preset: str | None
    completion_id: str | None
    notification_id: str | None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.timer_id,
            "label": self.label,
            "status": self.status,
            "revision": self.revision,
            "duration_seconds": self.duration_seconds,
            "remaining_seconds": self.remaining_seconds,
        }
        if self.deadline_at is not None:
            payload["deadline_at"] = self.deadline_at
        if self.preset is not None:
            payload["preset"] = self.preset
        if self.completion_id is not None:
            payload["completion_id"] = self.completion_id
        if self.notification_id is not None:
            payload["notification_id"] = self.notification_id
        return payload


class TimerStore:
    def __init__(self, db_path: Path, *, now: Callable[[], datetime] | None = None) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._now = now or (lambda: datetime.now(tz=UTC))
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        for pragma in TIMER_PRAGMAS:
            self._conn.execute(pragma)
        self._apply_schema()

    def start(
        self,
        *,
        label: str,
        duration_seconds: int,
        preset: str | None = None,
    ) -> Timer:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds debe ser positivo")
        if not label or len(label) > 256:
            raise ValueError("label debe tener entre 1 y 256 caracteres")
        timer_id = str(uuid.uuid4())
        moment = self._now()
        deadline = moment + timedelta(seconds=duration_seconds)
        with self._conn:
            revision = self._bump_revision()
            self._conn.execute(
                "INSERT INTO timers "
                "(id, label, status, revision, duration_seconds, deadline_at, preset, created_at) "
                "VALUES (?, ?, 'running', ?, ?, ?, ?, ?)",
                (
                    timer_id,
                    label,
                    revision,
                    duration_seconds,
                    deadline.isoformat(),
                    preset,
                    moment.isoformat(),
                ),
            )
        timer = self.get(timer_id)
        assert timer is not None
        return timer

    def pause(self, timer_id: str) -> bool:
        row = self._row(timer_id)
        if row is None or row["status"] != "running":
            return False
        remaining = self._remaining_of(row)
        with self._conn:
            revision = self._bump_revision()
            self._conn.execute(
                "UPDATE timers SET status='paused', deadline_at=NULL, "
                "paused_remaining=?, revision=? WHERE id=?",
                (remaining, revision, timer_id),
            )
        return True

    def resume(self, timer_id: str) -> bool:
        row = self._row(timer_id)
        if row is None or row["status"] != "paused":
            return False
        remaining = int(row["paused_remaining"] or 0)
        deadline = self._now() + timedelta(seconds=remaining)
        with self._conn:
            revision = self._bump_revision()
            self._conn.execute(
                "UPDATE timers SET status='running', deadline_at=?, "
                "paused_remaining=NULL, revision=? WHERE id=?",
                (deadline.isoformat(), revision, timer_id),
            )
        return True

    def cancel(self, timer_id: str) -> bool:
        with self._conn:
            revision = self._bump_revision()
            cursor = self._conn.execute(
                "UPDATE timers SET status='cancelled', deadline_at=NULL, "
                "paused_remaining=NULL, revision=? "
                "WHERE id=? AND status IN ('running', 'paused')",
                (revision, timer_id),
            )
        return cursor.rowcount == 1

    def get(self, timer_id: str) -> Timer | None:
        row = self._row(timer_id)
        return None if row is None else self._to_timer(row)

    def snapshot(self) -> tuple[int, list[Timer]]:
        """Revision global + timers, auto-completando los vencidos."""
        self._complete_expired()
        rows = self._conn.execute(
            "SELECT * FROM timers ORDER BY created_at DESC LIMIT ?", (_MAX_SNAPSHOT,)
        ).fetchall()
        return self.revision(), [self._to_timer(row) for row in rows]

    def revision(self) -> int:
        row = self._conn.execute("SELECT value FROM timer_meta WHERE key='revision'").fetchone()
        return int(row["value"])

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "TimerStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _complete_expired(self) -> None:
        now_iso = self._now().isoformat()
        expired = self._conn.execute(
            "SELECT id FROM timers WHERE status='running' AND deadline_at <= ?",
            (now_iso,),
        ).fetchall()
        for row in expired:
            with self._conn:
                revision = self._bump_revision()
                self._conn.execute(
                    "UPDATE timers SET status='completed', completion_id=?, revision=? "
                    "WHERE id=? AND status='running'",
                    (str(uuid.uuid4()), revision, row["id"]),
                )

    def _row(self, timer_id: str) -> sqlite3.Row | None:
        row: sqlite3.Row | None = self._conn.execute(
            "SELECT * FROM timers WHERE id=?", (timer_id,)
        ).fetchone()
        return row

    def _remaining_of(self, row: sqlite3.Row) -> int:
        if row["status"] == "paused":
            return max(0, int(row["paused_remaining"] or 0))
        if row["status"] == "running" and row["deadline_at"] is not None:
            deadline = datetime.fromisoformat(row["deadline_at"])
            delta = (deadline - self._now()).total_seconds()
            return max(0, min(int(delta), int(row["duration_seconds"])))
        return 0

    def _to_timer(self, row: sqlite3.Row) -> Timer:
        return Timer(
            timer_id=row["id"],
            label=row["label"],
            status=row["status"],
            revision=row["revision"],
            duration_seconds=row["duration_seconds"],
            remaining_seconds=self._remaining_of(row),
            deadline_at=row["deadline_at"] if row["status"] == "running" else None,
            preset=row["preset"],
            completion_id=row["completion_id"],
            notification_id=row["notification_id"],
        )

    def _bump_revision(self) -> int:
        self._conn.execute("UPDATE timer_meta SET value = value + 1 WHERE key='revision'")
        return self.revision()

    def _apply_schema(self) -> None:
        with self._conn:
            self._conn.execute(_CREATE_TABLE)
            self._conn.execute(_CREATE_META)
            self._conn.execute(
                "INSERT OR IGNORE INTO timer_meta (key, value) VALUES ('revision', 1)"
            )
