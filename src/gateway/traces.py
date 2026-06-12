"""TraceStore — persistencia consultable de traces sobre SQLite stdlib (GATE-05, D-22).

DB SEPARADA de audit.db y de los datos de usuario (D-22). Replica EXACTO el patrón probado
de `SqliteAuditLogger`: mkdir parent, PRAGMAS, smoke test WAL fail-fast (Pitfall 6: el repo
vive sobre NTFS/fuseblk donde WAL puede degradar). A diferencia de audit, traces NO es
append-only: `purge_older_than` borra traces vencidos por retención (default 90d).

El `prompt` guardado es POST-minimizer (sin secretos, D-22). Vive en `gateway/`, no en
`audit/`: traces != audit (Pitfall 4 — no rompe el contrato de independencia de import-linter).
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType

from gateway.db import open_gateway_db

_INSERT = (
    "INSERT INTO traces "
    "(trace_id, task_id, agent_id, tier, purpose, prompt, output, "
    "tokens_in, tokens_out, cost_usd, latency_ms, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_COLUMNS = (
    "trace_id",
    "task_id",
    "agent_id",
    "tier",
    "purpose",
    "prompt",
    "output",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "latency_ms",
    "created_at",
)
_SELECT = f"SELECT {', '.join(_COLUMNS)} FROM traces"


class TraceStore:
    """Store SQLite de traces consultables (D-22). WAL fail-fast; NO append-only (purga 90d)."""

    def __init__(self, db_path: Path) -> None:
        """Abre la DB de gateway vía `open_gateway_db` (0600 + WAL fail-fast + esquema).

        Raisea ``TraceIntegrityError`` si WAL no está disponible (Pitfall 6). La apertura
        es COMPARTIDA con `CostTracker` (WR-08/WR-09): las garantías no dependen del orden
        de construcción de los stores.
        """
        self._db_path = db_path
        self._conn = open_gateway_db(db_path)

    def write(
        self,
        *,
        trace_id: str,
        task_id: str,
        agent_id: str,
        tier: str,
        purpose: str,
        prompt: str,
        output: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float,
        latency_ms: int,
        created_at: str | None = None,
    ) -> None:
        """Persiste un trace (INSERT parametrizado — nunca interpolación de strings).

        `prompt` es POST-minimizer (D-22). `created_at` por default es el ahora UTC ISO;
        se acepta explícito para tests de retención.
        """
        ts = created_at if created_at is not None else datetime.now(UTC).isoformat()
        self._conn.execute(
            _INSERT,
            (
                trace_id,
                task_id,
                agent_id,
                tier,
                purpose,
                prompt,
                output,
                tokens_in,
                tokens_out,
                cost_usd,
                latency_ms,
                ts,
            ),
        )
        self._conn.commit()

    def query_by_task(self, task_id: str) -> list[dict[str, object]]:
        """Devuelve los traces de una tarea (índice idx_traces_task, D-22)."""
        rows = self._conn.execute(
            f"{_SELECT} WHERE task_id=? ORDER BY id", (task_id,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def query_by_purpose(self, purpose: str) -> list[dict[str, object]]:
        """Filtra traces por purpose (índice idx_traces_purpose_time, D-22)."""
        rows = self._conn.execute(
            f"{_SELECT} WHERE purpose=? ORDER BY id", (purpose,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def purge_older_than(self, days: int) -> int:
        """Borra traces más viejos que `days` (default de retención: 90d, D-22).

        Devuelve la cantidad de filas borradas. Esto NO existe en audit (forever); traces
        expira por retención y por eso el esquema no lleva triggers append-only.
        """
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        cur = self._conn.execute("DELETE FROM traces WHERE created_at < ?", (cutoff,))
        self._conn.commit()
        return cur.rowcount

    @staticmethod
    def _row_to_dict(row: tuple[object, ...]) -> dict[str, object]:
        return dict(zip(_COLUMNS, row, strict=True))

    def close(self) -> None:
        """Cierra la conexión subyacente."""
        self._conn.close()

    def __enter__(self) -> "TraceStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
