"""Adapter SQLite de claims idempotentes para clientes Home."""

from __future__ import annotations

import json
import os
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

    def __init__(
        self,
        db_path: Path,
        *,
        max_rows: int = 10_000,
        max_completed_rows: int = 5_000,
        maintenance_interval: int = 100,
    ) -> None:
        if min(max_rows, max_completed_rows, maintenance_interval) < 1:
            raise ValueError("límites de idempotencia deben ser positivos")
        if max_completed_rows > max_rows:
            raise ValueError("max_completed_rows no puede superar max_rows")
        self._db_path = db_path
        self._max_rows = max_rows
        self._max_completed_rows = max_completed_rows
        self._maintenance_interval = maintenance_interval
        self._claims_since_maintenance = 0
        db_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(db_path, os.O_CREAT, 0o600)
        os.close(fd)
        os.chmod(db_path, 0o600)
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
        self._secure_files()

    def claim(self, key: str, fingerprint: str) -> IdempotencyClaim:
        """Crea un claim o devuelve replay/conflicto sin reabrir efectos ambiguos."""
        if not key or not fingerprint:
            raise ValueError("key y fingerprint son requeridos")
        self._claims_since_maintenance += 1
        if self._claims_since_maintenance >= self._maintenance_interval:
            self._maintain()
            self._claims_since_maintenance = 0
        now = datetime.now(UTC).isoformat()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT fingerprint, status, response_json FROM client_requests "
                "WHERE request_key=?",
                (key,),
            ).fetchone()
            if row is None:
                count_row = self._conn.execute("SELECT COUNT(*) FROM client_requests").fetchone()
                count = int(count_row[0])
                completed_row = self._conn.execute(
                    "SELECT COUNT(*) FROM client_requests WHERE status='completed'"
                ).fetchone()
                completed = int(completed_row[0])
                if count >= self._max_rows or completed >= self._max_completed_rows:
                    raise RuntimeError("capacidad idempotente agotada; claim rechazado")
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
        self._secure_files()

    def prune_completed(self, older_than: datetime) -> int:
        """Elimina sólo respuestas completadas fuera de la ventana contractual de 24 h."""
        if older_than.tzinfo is None:
            raise ValueError("older_than debe incluir zona horaria")
        cursor = self._conn.execute(
            "DELETE FROM client_requests WHERE status='completed' AND updated_at < ?",
            (older_than.astimezone(UTC).isoformat(),),
        )
        self._secure_files()
        return cursor.rowcount

    def _secure_files(self) -> None:
        """Mantiene 0600 en la DB y en sidecars WAL/SHM si existen."""
        for path in (
            self._db_path,
            Path(f"{self._db_path}-wal"),
            Path(f"{self._db_path}-shm"),
        ):
            if path.exists():
                os.chmod(path, 0o600)

    def _maintain(self) -> None:
        """Poda completados con ventana y cuota; nunca borra claims ambiguos."""
        self.prune_completed(datetime.now(UTC) - timedelta(hours=24))
        self._secure_files()

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
