"""Puerto del ledger de finanzas (AGENT-09, D-82) — Protocol puro, sin infra.

`LedgerPort` es el contrato que el adapter SQLite (`ledger.sqlite_store.SqliteLedgerStore`)
satisface estructuralmente. Toda agregación (balance/surplus/categorías/cobertura) se calcula
SQL-side en el adapter — el núcleo nunca importa `sqlite3` (contrato import-linter `core puro`).
Esto previene estructuralmente el modo de falla #1 de la AI-SPEC: el LLM no computa totales.
"""

from collections.abc import Mapping
from typing import Protocol

from core.domain import Transaccion


class LedgerPort(Protocol):
    """Persiste transacciones y expone agregaciones deterministas sobre una ventana de fechas."""

    def record(self, transaccion: Transaccion) -> None:
        """Persiste una transacción."""
        ...

    def query_by_category(self, desde: str, hasta: str) -> Mapping[str, float]:
        """Gastos totales por categoría dentro de la ventana `[desde, hasta]` (inclusive)."""
        ...

    def balance(self, desde: str, hasta: str) -> tuple[float, float]:
        """`(ingresos_total, gastos_total)` dentro de la ventana `[desde, hasta]`."""
        ...

    def surplus(self, desde: str, hasta: str) -> float:
        """`ingresos_total - gastos_total` dentro de la ventana `[desde, hasta]`."""
        ...

    def coverage_days(self, desde: str, hasta: str) -> int:
        """Nº de fechas distintas con datos dentro de la ventana `[desde, hasta]`."""
        ...
