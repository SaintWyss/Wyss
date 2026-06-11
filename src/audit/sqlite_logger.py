"""SqliteAuditLogger — adapter de AuditPort sobre SQLite stdlib (D-06, D-08, AUD-01).

DB SEPARADA de los datos de usuario (D-06). SQL directo con `sqlite3` (SQLAlchemy
prohibido por STACK). Append-only estructural (triggers) y WAL verificado fail-fast
al construir — nunca degrada silencioso a journal sin garantías para un audit log
(Pitfall 6: el repo vive sobre NTFS/fuseblk donde WAL puede fallar).
"""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from core.domain import ActorType, AuditEvent, AuditEventType, Span
from core.domain.errors import AuditIntegrityError

from audit.schema import PRAGMAS, apply_schema

_INSERT = (
    "INSERT INTO audit_events "
    "(event_id, task_id, actor_type, actor_id, event_type, message, payload, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)


class SqliteAuditLogger:
    """Implementa AuditPort. DB separada de datos de usuario (D-06). Append-only.

    Sin métodos de mutación o borrado en la API pública — append-only también en la
    interfaz, no solo en el esquema.
    """

    def __init__(self, db_path: Path) -> None:
        """Abre la DB, verifica WAL fail-fast y aplica el esquema.

        Raisea ``AuditIntegrityError`` si ``PRAGMA journal_mode`` no retorna ``"wal"``:
        sobre NTFS/fuseblk WAL puede degradar y un audit log no puede correr sin las
        garantías de durabilidad (Pitfall 6).
        """
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        journal_mode: str | None = None
        for pragma in PRAGMAS:
            row = self._conn.execute(pragma).fetchone()
            if pragma.endswith("WAL") and row is not None:
                journal_mode = str(row[0]).lower()
        if journal_mode != "wal":
            self._conn.close()
            raise AuditIntegrityError(
                f"audit log en {db_path}: PRAGMA journal_mode retornó "
                f"{journal_mode!r}, se esperaba 'wal'. WAL no está disponible sobre "
                "este filesystem (probablemente NTFS/fuseblk). Mové data/ a un "
                "filesystem ext4 para garantizar durabilidad del audit log."
            )
        apply_schema(self._conn)

    def log(self, event: AuditEvent) -> None:
        """Inserta un evento (parametrizado — nunca interpolación de strings en SQL).

        commit por evento: con synchronous=FULL fsyncea cada commit; el costo es
        aceptable a esta escala y la durabilidad es no-negociable para auditoría.
        """
        self._conn.execute(
            _INSERT,
            (
                event.event_id,
                event.task_id,
                event.actor_type.value,
                event.actor_id,
                event.event_type.value,
                event.message,
                json.dumps(dict(event.payload)),
                event.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def span(
        self, task_id: str, actor: str, event: str
    ) -> AbstractContextManager[Span]:
        """Context manager que audita inicio, fin (con duración ms) y excepción."""
        return self._span_impl(task_id, actor, event)

    @contextmanager
    def _span_impl(self, task_id: str, actor: str, event: str) -> Iterator[Span]:
        started_at = datetime.now(UTC)
        span = Span(task_id=task_id, actor=actor, event=event, started_at=started_at)
        self.log(
            AuditEvent.new(
                task_id=task_id,
                actor_type=ActorType.SYSTEM,
                actor_id=actor,
                event_type=AuditEventType.SPAN_STARTED,
                message=event,
            )
        )
        try:
            yield span
        except Exception as exc:
            self.log(
                AuditEvent.new(
                    task_id=task_id,
                    actor_type=ActorType.SYSTEM,
                    actor_id=actor,
                    event_type=AuditEventType.SPAN_FAILED,
                    message=event,
                    payload={
                        "error_type": type(exc).__name__,
                        "duration_ms": self._elapsed_ms(started_at),
                    },
                )
            )
            raise
        self.log(
            AuditEvent.new(
                task_id=task_id,
                actor_type=ActorType.SYSTEM,
                actor_id=actor,
                event_type=AuditEventType.SPAN_COMPLETED,
                message=event,
                payload={"duration_ms": self._elapsed_ms(started_at)},
            )
        )

    @staticmethod
    def _elapsed_ms(started_at: datetime) -> float:
        return (datetime.now(UTC) - started_at).total_seconds() * 1000.0

    def close(self) -> None:
        """Cierra la conexión subyacente."""
        self._conn.close()

    def __enter__(self) -> "SqliteAuditLogger":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
