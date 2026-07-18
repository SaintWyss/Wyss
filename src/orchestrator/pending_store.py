"""SQLite store para propuestas pendientes de confirmacion (ORCH-06 / D-54..D-56)."""

import json
import os
import sqlite3
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType

from core.domain.errors import AuditIntegrityError
from core.domain.plan import Action, Plan
from core.domain.policy import PolicyDecision

PENDING_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=FULL",
    "PRAGMA busy_timeout=5000",
)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS pending_proposals (
  id           TEXT PRIMARY KEY,
  task_id      TEXT NOT NULL,
  plan_json    TEXT NOT NULL,
  risk_level   TEXT NOT NULL,
  outcome      TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending',
  created_at   TEXT NOT NULL,
  expires_at   TEXT NOT NULL,
  resolved_at  TEXT,
  resolved_by  TEXT,
  revision     INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1)
)
"""

CREATE_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_proposals(status, expires_at)"
)

_INSERT = (
    "INSERT INTO pending_proposals "
    "(id, task_id, plan_json, risk_level, outcome, status, created_at, expires_at) "
    "VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)"
)


@dataclass(frozen=True, slots=True)
class PendingProposal:
    """Fila durable de `pending_proposals`."""

    id: str
    task_id: str
    plan_json: str
    risk_level: str
    outcome: str
    status: str
    created_at: str
    expires_at: str
    resolved_at: str | None
    resolved_by: str | None
    revision: int


class PendingStore:
    """Cola durable de confirmaciones pendientes sobre SQLite con WAL fail-fast."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(db_path, os.O_CREAT, 0o600)
        os.close(fd)
        os.chmod(db_path, 0o600)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        journal_mode: str | None = None
        for pragma in PENDING_PRAGMAS:
            row = self._conn.execute(pragma).fetchone()
            if pragma.endswith("WAL") and row is not None:
                journal_mode = str(row[0]).lower()
        if journal_mode != "wal":
            self._conn.close()
            raise AuditIntegrityError(
                f"pending_store en {db_path}: PRAGMA journal_mode retorno "
                f"{journal_mode!r}, se esperaba 'wal'. WAL no esta disponible "
                "sobre este filesystem."
            )
        self._apply_schema()
        self._secure_files()

    def save(self, plan: Plan, decision: PolicyDecision, ttl_seconds: int) -> str:
        """Persiste una propuesta pendiente y devuelve su pending_id."""
        pending_id = uuid.uuid4().hex
        now = datetime.now(UTC)
        self._conn.execute(
            _INSERT,
            (
                pending_id,
                plan.task_id,
                json.dumps(_plan_to_dict(plan)),
                decision.risk_level.name,
                decision.outcome.name,
                now.isoformat(),
                (now + timedelta(seconds=ttl_seconds)).isoformat(),
            ),
        )
        self._conn.commit()
        self._secure_files()
        return pending_id

    def load(self, pending_id: str) -> PendingProposal | None:
        """Carga una propuesta por id, o None si no existe."""
        row = self._conn.execute(
            "SELECT * FROM pending_proposals WHERE id=?", (pending_id,)
        ).fetchone()
        return _row_to_proposal(row)

    def load_pending(self) -> list[PendingProposal]:
        """Devuelve todas las propuestas con status pending."""
        rows = self._conn.execute(
            "SELECT * FROM pending_proposals WHERE status='pending' ORDER BY created_at, id"
        ).fetchall()
        return [_proposal_from_row(row) for row in rows]

    def expire_old(self) -> list[PendingProposal]:
        """Marca como expiradas las propuestas vencidas y devuelve las afectadas."""
        now = datetime.now(UTC).isoformat()
        rows = self._conn.execute(
            "SELECT * FROM pending_proposals "
            "WHERE status='pending' AND expires_at < ? ORDER BY expires_at, id",
            (now,),
        ).fetchall()
        proposals = [_proposal_from_row(row) for row in rows]
        if not proposals:
            return []

        resolved_at = datetime.now(UTC).isoformat()
        self._conn.executemany(
            "UPDATE pending_proposals "
            "SET status='expired', resolved_at=?, resolved_by='ttl_reaper', "
            "revision=revision+1 "
            "WHERE id=? AND status='pending' AND expires_at<?",
            [(resolved_at, proposal.id, resolved_at) for proposal in proposals],
        )
        self._conn.commit()
        self._secure_files()
        expired: list[PendingProposal] = []
        for item in proposals:
            loaded = self.load(item.id)
            if loaded is not None:
                expired.append(loaded)
        return expired

    def resolve(
        self,
        pending_id: str,
        resolved_by: str,
        *,
        status: str = "confirmed",
        expected_revision: int | None = None,
    ) -> PendingProposal | None:
        """Resuelve por CAS una propuesta vigente e incrementa su revisión."""
        if status not in {"confirmed", "rejected"}:
            raise ValueError("status de resolución inválido")
        if expected_revision is not None and expected_revision < 1:
            raise ValueError("expected_revision debe ser positiva")
        resolved_at = datetime.now(UTC).isoformat()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            sql = (
                "UPDATE pending_proposals "
                "SET status=?, resolved_at=?, resolved_by=?, revision=revision+1 "
                "WHERE id=? AND status='pending' AND expires_at>=?"
            )
            values: tuple[object, ...] = (
                status,
                resolved_at,
                resolved_by,
                pending_id,
                resolved_at,
            )
            if expected_revision is not None:
                sql += " AND revision=?"
                values += (expected_revision,)
            cur = self._conn.execute(sql, values)
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._secure_files()
        if cur.rowcount != 1:
            return None
        return self.load(pending_id)

    def expire(self, pending_id: str, *, expected_revision: int) -> PendingProposal | None:
        """Terminaliza por CAS un pending vencido y devuelve su revisión nueva."""
        now = datetime.now(UTC).isoformat()
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            cur = self._conn.execute(
                "UPDATE pending_proposals "
                "SET status='expired', resolved_at=?, resolved_by='ttl_reaper', "
                "revision=revision+1 "
                "WHERE id=? AND status='pending' AND expires_at<? AND revision=?",
                (now, pending_id, now, expected_revision),
            )
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        self._secure_files()
        if cur.rowcount != 1:
            return None
        return self.load(pending_id)

    def close(self) -> None:
        """Cierra la conexion SQLite subyacente."""
        self._conn.close()

    def __enter__(self) -> "PendingStore":
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
        columns = {
            str(row[1]) for row in self._conn.execute("PRAGMA table_info(pending_proposals)")
        }
        if "revision" not in columns:
            self._conn.execute(
                "ALTER TABLE pending_proposals ADD COLUMN revision INTEGER NOT NULL DEFAULT 1"
            )
        self._conn.execute(CREATE_INDEX)
        self._conn.commit()

    def _secure_files(self) -> None:
        for path in (
            self._db_path,
            Path(f"{self._db_path}-wal"),
            Path(f"{self._db_path}-shm"),
        ):
            if path.exists():
                os.chmod(path, 0o600)


def _row_to_proposal(row: sqlite3.Row | None) -> PendingProposal | None:
    if row is None:
        return None
    return _proposal_from_row(row)


def _proposal_from_row(row: sqlite3.Row) -> PendingProposal:
    return PendingProposal(
        id=str(row["id"]),
        task_id=str(row["task_id"]),
        plan_json=str(row["plan_json"]),
        risk_level=str(row["risk_level"]),
        outcome=str(row["outcome"]),
        status=str(row["status"]),
        created_at=str(row["created_at"]),
        expires_at=str(row["expires_at"]),
        resolved_at=row["resolved_at"],
        resolved_by=row["resolved_by"],
        revision=int(row["revision"]),
    )


def _plan_to_dict(plan: Plan) -> dict[str, object]:
    return {
        "task_id": plan.task_id,
        "summary": plan.summary,
        "steps": [_action_to_dict(action) for action in plan.steps],
        "rationale": plan.rationale,
        "estimated_risk": plan.estimated_risk.name if plan.estimated_risk else None,
    }


def _action_to_dict(action: Action) -> Mapping[str, object]:
    return {
        "type": action.type,
        "target": action.target,
        "parameters": dict(action.parameters),
        "on_error": action.on_error.value,
        "retry_params": (
            {
                "max_attempts": action.retry_params.max_attempts,
                "backoff_base_s": action.retry_params.backoff_base_s,
                "backoff_max_s": action.retry_params.backoff_max_s,
            }
            if action.retry_params is not None
            else None
        ),
    }
