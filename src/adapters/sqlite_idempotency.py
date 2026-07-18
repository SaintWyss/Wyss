"""Adapter SQLite de claims idempotentes para clientes Home."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import cast

from core.domain.errors import AuditIntegrityError
from core.domain.home import ClaimStatus, IdempotencyClaim, JsonValue

_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA busy_timeout=5000",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS client_requests (
  request_key   TEXT PRIMARY KEY,
  fingerprint   TEXT NOT NULL,
  status        TEXT NOT NULL CHECK(status IN ('in_progress', 'completed')),
  response_json TEXT,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
)
"""


class SqliteIdempotencyStore:
    """Yo conservo resultados durables y cierro en ambiguo tras un crash."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        journal_mode: str | None = None
        for pragma in _PRAGMAS:
            row = self._conn.execute(pragma).fetchone()
            if pragma.endswith("WAL") and row is not None:
                journal_mode = str(row[0]).lower()
        if journal_mode != "wal":
            self._conn.close()
            raise AuditIntegrityError(
                f"client_requests en {db_path}: WAL no disponible; rechazo claims no durables"
            )
        self._conn.execute(_SCHEMA)
        self.prune_completed(datetime.now(UTC) - timedelta(hours=24))

    def claim(self, key: str, fingerprint: str) -> IdempotencyClaim:
        """Crea un claim o devuelve replay/conflicto sin reabrir efectos ambiguos."""
        if not key or not fingerprint:
            raise ValueError("key y fingerprint son requeridos")
        now = datetime.now(UTC).isoformat()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT fingerprint, status, response_json FROM client_requests "
                "WHERE request_key=?",
                (key,),
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO client_requests "
                    "(request_key, fingerprint, status, response_json, created_at, updated_at) "
                    "VALUES (?, ?, 'in_progress', NULL, ?, ?)",
                    (key, fingerprint, now, now),
                )
                self._conn.execute("COMMIT")
                return IdempotencyClaim(ClaimStatus.NEW)
            if str(row["fingerprint"]) != fingerprint:
                self._conn.execute("COMMIT")
                return IdempotencyClaim(ClaimStatus.CONFLICT)
            if str(row["status"]) != "completed":
                self._conn.execute("COMMIT")
                return IdempotencyClaim(ClaimStatus.IN_PROGRESS)
            response = _decode_response(row["response_json"])
            self._conn.execute("COMMIT")
            return IdempotencyClaim(ClaimStatus.REPLAY, response)
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise

    def complete(self, key: str, response: Mapping[str, JsonValue]) -> None:
        encoded = json.dumps(dict(response), ensure_ascii=False, separators=(",", ":"))
        cursor = self._conn.execute(
            "UPDATE client_requests SET status='completed', response_json=?, updated_at=? "
            "WHERE request_key=? AND status='in_progress'",
            (encoded, datetime.now(UTC).isoformat(), key),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("claim idempotente inexistente o ya completado")

    def prune_completed(self, older_than: datetime) -> int:
        """Elimina sólo respuestas completadas fuera de la ventana contractual de 24 h."""
        if older_than.tzinfo is None:
            raise ValueError("older_than debe incluir zona horaria")
        cursor = self._conn.execute(
            "DELETE FROM client_requests WHERE status='completed' AND updated_at < ?",
            (older_than.astimezone(UTC).isoformat(),),
        )
        return cursor.rowcount

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqliteIdempotencyStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def _decode_response(raw: object) -> Mapping[str, JsonValue]:
    if not isinstance(raw, str):
        raise AuditIntegrityError("claim completado sin respuesta")
    decoded = json.loads(raw)
    if not isinstance(decoded, dict):
        raise AuditIntegrityError("respuesta idempotente no es un objeto JSON")
    return cast(dict[str, JsonValue], decoded)
