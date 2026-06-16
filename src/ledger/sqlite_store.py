"""SqliteLedgerStore — adapter de persistencia del ledger (implementa `LedgerPort`).

Capa de infraestructura: importa `core.ports.ledger` y `core.domain`, nunca al revés
(contrato import-linter). DB propia (`ledger.db`) con WAL fail-fast espejo de
`orchestrator.pending_store`. TODA la aritmética (balance/surplus/categorías/cobertura) se
calcula SQL-side con `COALESCE(SUM(...),0.0)` / `GROUP BY` / `COUNT(DISTINCT ...)` sobre una
ventana explícita `WHERE fecha BETWEEN ? AND ?` — el LLM nunca suma filas (AI-SPEC modo #1).
Todos los valores (incluida la `categoria` de texto libre, D-83) entran por placeholders `?`
exclusivamente: nunca interpolación de strings en SQL (STRIDE T-08-03).
"""

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType

from core.domain import Transaccion
from core.domain.errors import AuditIntegrityError
from core.ports.ledger import LedgerPort
from ledger.schema import PRAGMAS, apply_schema

_INSERT = (
    "INSERT INTO transacciones "
    "(tipo, monto, fecha, fuente, categoria, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)


class SqliteLedgerStore:
    """Store SQLite del ledger con WAL fail-fast y agregaciones SQL-side (implementa LedgerPort)."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        journal_mode: str | None = None
        for pragma in PRAGMAS:
            row = self._conn.execute(pragma).fetchone()
            if pragma.endswith("WAL") and row is not None:
                journal_mode = str(row[0]).lower()
        if journal_mode != "wal":
            self._conn.close()
            raise AuditIntegrityError(
                f"ledger store en {db_path}: PRAGMA journal_mode retorno "
                f"{journal_mode!r}, se esperaba 'wal'. WAL no esta disponible "
                "sobre este filesystem."
            )
        apply_schema(self._conn)

    def record(self, transaccion: Transaccion) -> None:
        """Persiste una transacción (INSERT parametrizado — categoria libre nunca interpolada)."""
        self._conn.execute(
            _INSERT,
            (
                transaccion.tipo.name,
                transaccion.monto,
                transaccion.fecha,
                transaccion.fuente,
                transaccion.categoria,
                transaccion.created_at,
            ),
        )
        self._conn.commit()

    def query_by_category(self, desde: str, hasta: str) -> Mapping[str, float]:
        """Gastos por categoría en `[desde, hasta]` — SUM/GROUP BY SQL-side, sin fuga de período."""
        rows = self._conn.execute(
            "SELECT categoria, COALESCE(SUM(monto), 0.0) AS total "
            "FROM transacciones "
            "WHERE tipo = ? AND fecha BETWEEN ? AND ? "
            "GROUP BY categoria",
            ("GASTO", desde, hasta),
        ).fetchall()
        return {str(row["categoria"]): float(row["total"]) for row in rows}

    def balance(self, desde: str, hasta: str) -> tuple[float, float]:
        """`(ingresos_total, gastos_total)` en `[desde, hasta]` — SUM condicional SQL-side."""
        (ingresos, gastos) = self._conn.execute(
            "SELECT "
            "COALESCE(SUM(CASE WHEN tipo = 'INGRESO' THEN monto END), 0.0) AS ingresos, "
            "COALESCE(SUM(CASE WHEN tipo = 'GASTO' THEN monto END), 0.0) AS gastos "
            "FROM transacciones "
            "WHERE fecha BETWEEN ? AND ?",
            (desde, hasta),
        ).fetchone()
        return (float(ingresos), float(gastos))

    def surplus(self, desde: str, hasta: str) -> float:
        """`ingresos_total - gastos_total` en `[desde, hasta]`."""
        ingresos, gastos = self.balance(desde, hasta)
        return ingresos - gastos

    def coverage_days(self, desde: str, hasta: str) -> int:
        """Nº de fechas distintas con datos en `[desde, hasta]` — COUNT(DISTINCT) SQL-side."""
        (total,) = self._conn.execute(
            "SELECT COUNT(DISTINCT fecha) FROM transacciones "
            "WHERE fecha BETWEEN ? AND ?",
            (desde, hasta),
        ).fetchone()
        return int(total)

    def close(self) -> None:
        """Cierra la conexión SQLite subyacente."""
        self._conn.close()

    def __enter__(self) -> "SqliteLedgerStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


# Conformidad estructural verificada en build-time por mypy (no afecta runtime).
_: type[LedgerPort] = SqliteLedgerStore
