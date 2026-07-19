"""Entidades de dominio del ledger de finanzas (AGENT-09) — stdlib frozen, sin Pydantic.

`Transaccion` es el átomo del ledger: un movimiento (ingreso o gasto) con monto, fecha ISO
y categoría libre (D-83). Es un `dataclass(frozen=True, slots=True)` de stdlib — NO Pydantic
en el núcleo (AI-SPEC §4b: Pydantic muere en bootstrap). La aritmética sobre transacciones
vive SIEMPRE en SQL (adapter `ledger.sqlite_store`); el dominio solo modela el dato.
"""

from dataclasses import dataclass
from enum import Enum


class TipoTransaccion(Enum):
    """Naturaleza de un movimiento del ledger."""

    INGRESO = "ingreso"
    GASTO = "gasto"


@dataclass(frozen=True, slots=True)
class Transaccion:
    """Un movimiento del ledger: ingreso o gasto, con fecha ISO y categoría libre (D-83)."""

    tipo: TipoTransaccion
    monto: float
    fecha: str  # fecha ISO `YYYY-MM-DD`
    fuente: str | None
    categoria: str | None  # texto libre (D-83); nunca interpolado en SQL
    created_at: str  # datetime ISO de alta
