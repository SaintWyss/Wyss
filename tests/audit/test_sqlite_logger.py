"""Tests del SqliteAuditLogger: WAL, persistencia D-07, append-only T4, span, concurrencia."""

import json
import os
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from audit import SqliteAuditLogger
from core.domain.audit import ActorType, AuditEvent, AuditEventType, AuditQuery
from core.domain.errors import AuditIntegrityError


def _read_conn(db_path: Path) -> sqlite3.Connection:
    """Conexión independiente de solo lectura para verificar persistencia."""
    return sqlite3.connect(db_path)


def test_wal_active(logger: SqliteAuditLogger, tmp_path: Path) -> None:
    """(1) El logger deja journal_mode=WAL sobre tmp_path."""
    conn = _read_conn(tmp_path / "audit.db")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        conn.close()


def test_roundtrip_persists_all_d07_fields(logger: SqliteAuditLogger, tmp_path: Path) -> None:
    """(2) Roundtrip D-07: payload cubre los 8 campos del registro mínimo."""
    payload: dict[str, object] = {
        "actor": "santiago",
        "instruccion": "indexá la carpeta de estudio",
        "plan": [{"action": "index", "path": "~/Data/estudio"}],
        "decision_politica": "B",
        "confirmacion": True,
        "acciones": ["scan", "extract", "embed"],
        "resultado": "ok",
        "costo_usd": 0.0123,
    }
    event = AuditEvent.new(
        task_id="task-d07",
        actor_type=ActorType.OWNER,
        actor_id="santiago",
        event_type=AuditEventType.TASK_COMPLETED,
        message="tarea completa",
        payload=payload,
    )
    logger.log(event)

    conn = _read_conn(tmp_path / "audit.db")
    try:
        row = conn.execute(
            "SELECT event_id, task_id, actor_type, actor_id, event_type, "
            "message, payload, created_at FROM audit_events WHERE task_id=?",
            ("task-d07",),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row[0] == event.event_id
    assert row[1] == "task-d07"
    assert row[2] == ActorType.OWNER.value
    assert row[3] == "santiago"
    assert row[4] == AuditEventType.TASK_COMPLETED.value
    assert row[5] == "tarea completa"
    assert json.loads(row[6]) == payload
    assert row[7] == event.created_at.isoformat()


def test_append_only_update_and_delete_abort(
    logger: SqliteAuditLogger, tmp_path: Path, make_event: Callable[..., AuditEvent]
) -> None:
    """(3) Append-only (T4): UPDATE y DELETE abortan; el evento original persiste."""
    logger.log(make_event(message="original"))

    conn = _read_conn(tmp_path / "audit.db")
    try:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE audit_events SET message='x'")
            conn.commit()
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM audit_events")
            conn.commit()
        (count,) = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()
        (msg,) = conn.execute("SELECT message FROM audit_events").fetchone()
    finally:
        conn.close()

    assert count == 1
    assert msg == "original"


def test_span_happy_path(logger: SqliteAuditLogger, tmp_path: Path) -> None:
    """(4) Span feliz: SPAN_STARTED + SPAN_COMPLETED en orden."""
    with logger.span("task-span", "orchestrator", "indexar"):
        pass

    conn = _read_conn(tmp_path / "audit.db")
    try:
        types = [
            r[0]
            for r in conn.execute(
                "SELECT event_type FROM audit_events WHERE task_id=? ORDER BY id",
                ("task-span",),
            ).fetchall()
        ]
    finally:
        conn.close()

    assert types == [
        AuditEventType.SPAN_STARTED.value,
        AuditEventType.SPAN_COMPLETED.value,
    ]


def test_span_failure_records_and_propagates(logger: SqliteAuditLogger, tmp_path: Path) -> None:
    """(4b) Span con excepción: SPAN_FAILED registrado y la excepción se propaga."""
    with pytest.raises(ValueError, match="boom"), logger.span("task-fail", "agent", "riesgoso"):
        raise ValueError("boom")

    conn = _read_conn(tmp_path / "audit.db")
    try:
        rows = conn.execute(
            "SELECT event_type, payload FROM audit_events WHERE task_id=? ORDER BY id",
            ("task-fail",),
        ).fetchall()
    finally:
        conn.close()

    types = [r[0] for r in rows]
    assert types == [
        AuditEventType.SPAN_STARTED.value,
        AuditEventType.SPAN_FAILED.value,
    ]
    failed_payload = json.loads(rows[1][1])
    assert failed_payload["error_type"] == "ValueError"


def test_correlation_by_task_id(
    logger: SqliteAuditLogger, tmp_path: Path, make_event: Callable[..., AuditEvent]
) -> None:
    """(5) Correlación: dos eventos con el mismo task_id se recuperan juntos; índice existe."""
    logger.log(make_event(task_id="corr", message="uno"))
    logger.log(make_event(task_id="corr", message="dos"))
    logger.log(make_event(task_id="otro", message="tres"))

    conn = _read_conn(tmp_path / "audit.db")
    try:
        (count,) = conn.execute(
            "SELECT COUNT(*) FROM audit_events WHERE task_id=?", ("corr",)
        ).fetchone()
        indexes = {r[1] for r in conn.execute("PRAGMA index_list('audit_events')")}
    finally:
        conn.close()

    assert count == 2
    assert "idx_audit_task" in indexes


def test_query_filters_and_returns_newest_first(
    logger: SqliteAuditLogger, make_event: Callable[..., AuditEvent]
) -> None:
    logger.log(make_event(task_id="target", message="primero"))
    logger.log(make_event(task_id="other", message="ignorado"))
    logger.log(make_event(task_id="target", message="último"))

    events = logger.query(AuditQuery(task_id="target", limit=2))

    assert [event.message for event in events] == ["último", "primero"]
    assert all(event.task_id == "target" for event in events)


def test_basic_concurrency(tmp_path: Path) -> None:
    """(6) Dos loggers sobre el mismo path escriben 100 eventos sin 'database is locked'."""
    db_path = tmp_path / "audit.db"
    log_a = SqliteAuditLogger(db_path)
    log_b = SqliteAuditLogger(db_path)
    try:
        for i in range(50):
            log_a.log(
                AuditEvent.new(
                    task_id="conc",
                    actor_type=ActorType.SYSTEM,
                    actor_id="a",
                    event_type=AuditEventType.ACTION_STARTED,
                    message=f"a-{i}",
                )
            )
            log_b.log(
                AuditEvent.new(
                    task_id="conc",
                    actor_type=ActorType.SYSTEM,
                    actor_id="b",
                    event_type=AuditEventType.ACTION_STARTED,
                    message=f"b-{i}",
                )
            )
    finally:
        log_a.close()
        log_b.close()

    conn = _read_conn(db_path)
    try:
        (count,) = conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()
    finally:
        conn.close()
    assert count == 100


def test_fail_fast_when_journal_not_wal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """(7) journal_mode ≠ wal → AuditIntegrityError con el path en el mensaje."""
    import audit.sqlite_logger as mod

    monkeypatch.setattr(mod, "PRAGMAS", ("PRAGMA journal_mode=DELETE",))
    db_path = tmp_path / "audit.db"
    with pytest.raises(AuditIntegrityError) as excinfo:
        SqliteAuditLogger(db_path)
    assert str(db_path) in str(excinfo.value)


@pytest.mark.ntfs
@pytest.mark.skipif(
    os.environ.get("WYSS_TEST_NTFS") != "1",
    reason="requiere WYSS_TEST_NTFS=1 (corre sobre el mount NTFS/fuseblk real)",
)
def test_wal_on_real_data_dir() -> None:
    """(8) Opcional: el logger construye sobre data/ real (NTFS/fuseblk) con WAL activo."""
    repo_root = Path(__file__).resolve().parents[2]
    db_path = repo_root / "data" / "audit_ntfs_test.db"
    log = SqliteAuditLogger(db_path)
    try:
        conn = _read_conn(db_path)
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert str(mode).lower() == "wal"
        finally:
            conn.close()
    finally:
        log.close()
        db_path.unlink(missing_ok=True)
        for sidecar in (
            db_path.with_suffix(".db-wal"),
            db_path.with_suffix(".db-shm"),
        ):
            sidecar.unlink(missing_ok=True)
