"""Tests del TraceStore: WAL fail-fast, persistencia D-22, query por task/purpose, purga.

A diferencia de audit (append-only forever), traces NO tiene triggers de inmutabilidad:
soporta purga por retención (default 90d). Replica el patrón SQLite WAL fail-fast de Fase 1.
"""

import os
import sqlite3
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.domain.errors import TraceIntegrityError
from gateway.traces import TraceStore


def _read_conn(db_path: Path) -> sqlite3.Connection:
    """Conexión independiente de solo lectura para verificar persistencia."""
    return sqlite3.connect(db_path)


def test_wal_active(traces_db_path: Path) -> None:
    """(0) El TraceStore deja journal_mode=WAL sobre tmp_path (ext4/tmpfs)."""
    store = TraceStore(traces_db_path)
    try:
        conn = _read_conn(traces_db_path)
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert str(mode).lower() == "wal"
        finally:
            conn.close()
    finally:
        store.close()


def test_write_persists_all_d22_fields(traces_db_path: Path) -> None:
    """(1) write() persiste una fila consultable por task_id con todos los campos D-22."""
    store = TraceStore(traces_db_path)
    try:
        store.write(
            trace_id="trace-1",
            task_id="task-1",
            agent_id="belgrano",
            tier="economico",
            purpose="general",
            prompt="prompt post-minimizer",
            output="respuesta del modelo",
            tokens_in=100,
            tokens_out=50,
            cost_usd=0.0012,
            latency_ms=345,
        )
        rows = store.query_by_task("task-1")
    finally:
        store.close()

    assert len(rows) == 1
    row = rows[0]
    assert row["trace_id"] == "trace-1"
    assert row["task_id"] == "task-1"
    assert row["agent_id"] == "belgrano"
    assert row["tier"] == "economico"
    assert row["purpose"] == "general"
    assert row["prompt"] == "prompt post-minimizer"
    assert row["output"] == "respuesta del modelo"
    assert row["tokens_in"] == 100
    assert row["tokens_out"] == 50
    assert row["cost_usd"] == pytest.approx(0.0012)
    assert row["latency_ms"] == 345
    assert row["created_at"]  # ISO timestamp poblado


def test_query_by_task_and_purpose_filter(traces_db_path: Path) -> None:
    """(2) query por task_id y por purpose filtran correctamente (índices D-22)."""
    store = TraceStore(traces_db_path)
    try:
        store.write(
            trace_id="t-a",
            task_id="task-a",
            agent_id="belgrano",
            tier="economico",
            purpose="estudio",
            prompt="p",
            output="o",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
            latency_ms=1,
        )
        store.write(
            trace_id="t-b",
            task_id="task-a",
            agent_id="belgrano",
            tier="economico",
            purpose="resumen",
            prompt="p",
            output="o",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
            latency_ms=1,
        )
        store.write(
            trace_id="t-c",
            task_id="task-b",
            agent_id="belgrano",
            tier="economico",
            purpose="estudio",
            prompt="p",
            output="o",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
            latency_ms=1,
        )

        by_task = store.query_by_task("task-a")
        by_purpose = store.query_by_purpose("estudio")
    finally:
        store.close()

    assert {r["trace_id"] for r in by_task} == {"t-a", "t-b"}
    assert {r["trace_id"] for r in by_purpose} == {"t-a", "t-c"}


def test_purge_older_than_deletes_old_traces(traces_db_path: Path) -> None:
    """(3) traces NO es append-only: purge_older_than borra filas viejas sin abortar."""
    store = TraceStore(traces_db_path)
    try:
        old = (datetime.now(UTC) - timedelta(days=120)).isoformat()
        recent = datetime.now(UTC).isoformat()
        store.write(
            trace_id="old",
            task_id="task-old",
            agent_id="a",
            tier="economico",
            purpose="general",
            prompt="p",
            output="o",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
            latency_ms=1,
            created_at=old,
        )
        store.write(
            trace_id="new",
            task_id="task-new",
            agent_id="a",
            tier="economico",
            purpose="general",
            prompt="p",
            output="o",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
            latency_ms=1,
            created_at=recent,
        )

        deleted = store.purge_older_than(90)
        remaining = store.query_by_task("task-old") + store.query_by_task("task-new")
    finally:
        store.close()

    assert deleted == 1
    assert {r["trace_id"] for r in remaining} == {"new"}


def test_no_append_only_triggers(traces_db_path: Path) -> None:
    """(3b) traces NO tiene triggers append-only: UPDATE/DELETE directos no abortan."""
    store = TraceStore(traces_db_path)
    try:
        store.write(
            trace_id="t1",
            task_id="task-1",
            agent_id="a",
            tier="economico",
            purpose="general",
            prompt="p",
            output="o",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
            latency_ms=1,
        )
    finally:
        store.close()

    conn = _read_conn(traces_db_path)
    try:
        conn.execute("UPDATE traces SET output='x'")
        conn.commit()
        conn.execute("DELETE FROM traces")
        conn.commit()
        (count,) = conn.execute("SELECT COUNT(*) FROM traces").fetchone()
    finally:
        conn.close()
    assert count == 0  # a diferencia de audit, el DELETE no abortó


def test_preexisting_db_perms_corrected_to_0600(traces_db_path: Path) -> None:
    """(5) WR-09: un archivo preexistente con 0644 se corrige a 0600 al abrir el store."""
    traces_db_path.touch()
    os.chmod(traces_db_path, 0o644)

    TraceStore(traces_db_path).close()

    mode = stat.S_IMODE(traces_db_path.stat().st_mode)
    assert mode == 0o600, f"esperaba 0600, fue {oct(mode)}"


def test_fail_fast_when_journal_not_wal(
    traces_db_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(4) journal_mode != wal -> TraceIntegrityError con el path en el mensaje (Pitfall 6).

    Los PRAGMAs viven en `gateway.db.open_gateway_db` (apertura compartida, WR-08).
    """
    import gateway.db as mod

    monkeypatch.setattr(mod, "PRAGMAS", ("PRAGMA journal_mode=DELETE",))
    with pytest.raises(TraceIntegrityError) as excinfo:
        TraceStore(traces_db_path)
    assert str(traces_db_path) in str(excinfo.value)
