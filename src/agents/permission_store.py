"""SQLitePermissionStore — grants agente/sujeto a BC persistidos (D-72)."""

import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from core.domain import Permission, Subject


class SQLitePermissionStore:
    """Implementa PermissionStore sobre SQLite stdlib."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS permissions (
                permission_id TEXT PRIMARY KEY,
                subject_id TEXT NOT NULL,
                kb_id TEXT NOT NULL,
                granted_at TEXT NOT NULL,
                revoked_at TEXT
            );
            """
        )
        self._conn.commit()

    def grants_for(self, subject: Subject) -> Sequence[Permission]:
        rows = self._conn.execute(
            """
            SELECT permission_id, subject_id, kb_id, granted_at, revoked_at
            FROM permissions
            WHERE subject_id = ?
            ORDER BY permission_id
            """,
            (subject.subject_id,),
        ).fetchall()
        return [
            Permission(
                permission_id=str(permission_id),
                subject_id=str(subject_id),
                kb_id=str(kb_id),
                granted_at=datetime.fromisoformat(str(granted_at)),
                revoked_at=(
                    datetime.fromisoformat(str(revoked_at))
                    if revoked_at is not None
                    else None
                ),
            )
            for permission_id, subject_id, kb_id, granted_at, revoked_at in rows
        ]

    def save(self, permission: Permission) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO permissions
                (permission_id, subject_id, kb_id, granted_at, revoked_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                permission.permission_id,
                permission.subject_id,
                permission.kb_id,
                permission.granted_at.isoformat(),
                (
                    permission.revoked_at.isoformat()
                    if permission.revoked_at is not None
                    else None
                ),
            ),
        )
        self._conn.commit()

    def revoke(self, permission_id: str) -> None:
        self._conn.execute(
            "UPDATE permissions SET revoked_at = ? WHERE permission_id = ?",
            (datetime.now(UTC).isoformat(), permission_id),
        )
        self._conn.commit()
