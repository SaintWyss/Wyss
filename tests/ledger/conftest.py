"""Fixtures de ground-truth para el ledger de finanzas (AGENT-09, AI-SPEC D1/D2/D3).

RED scaffold (Wave 0): los totales se precalculan A MANO acá y son la VERDAD DE TIERRA
(ground truth) contra la que `SqliteLedgerStore` (Plan 02) se asierta centavo a centavo.
NUNCA recalcular los totales en tiempo de test: si la suma manual y el adapter discrepan,
gana esta constante (AI-SPEC D1 — el label es el cálculo manual fijado una vez).

`Transaccion` y `TipoTransaccion` los define Plan 02 en `core.domain.ledger`; acá se importan
de forma diferida dentro de las fixtures (RED: el módulo aún no existe → ModuleNotFoundError
es el fallo correcto, no un import roto a nivel de colección).

La ventana de consulta de los sets es el mes calendario 2026-05 (`DESDE`..`HASTA`); cada set
incluye transacciones FUERA de ventana para verificar que el adapter no tenga fuga de período.
"""

from __future__ import annotations

from typing import Any

import pytest

# Ventana de consulta canónica de los fixtures (mes calendario mayo 2026, inclusive).
DESDE = "2026-05-01"
HASTA = "2026-05-31"

# Una transacción en bruto: (tipo, monto, fecha, fuente, categoria). Los fixtures devuelven
# estas tuplas y `Transaccion` se construye dentro del test (import diferido: el fallo RED
# por `core.domain.ledger` ausente cae en el CUERPO del test, no en setup del fixture).
TxSpec = tuple[str, float, str, "str | None", "str | None"]


def build_transaccion(spec: TxSpec) -> Any:
    """Construye una `Transaccion` desde su tupla (import diferido: RED hasta Plan 02).

    Retorno `Any`: `Transaccion`/`TipoTransaccion` los define Plan 02 en `core.domain.ledger`;
    acá el contrato se ejercita en runtime (RED → ModuleNotFoundError), no estáticamente.
    """
    import core.domain.ledger as ledger_mod  # type: ignore[import-untyped,import-not-found,unused-ignore]

    tipo, monto, fecha, fuente, categoria = spec
    return ledger_mod.Transaccion(
        tipo=ledger_mod.TipoTransaccion[tipo],
        monto=monto,
        fecha=fecha,
        fuente=fuente,
        categoria=categoria,
        created_at=f"{fecha}T12:00:00+00:00",
    )


def _tx(
    tipo: str,
    monto: float,
    fecha: str,
    fuente: str | None = None,
    categoria: str | None = None,
) -> TxSpec:
    """Tupla de transacción en bruto (sin construir el dominio aún)."""
    return (tipo, monto, fecha, fuente, categoria)


# ─────────────────────────────────────────────────────────────────────────────
# SET RICO (D1/D2): varias categorías, varias fechas, dentro y fuera de ventana.
# Las dos últimas transacciones (2026-04-28 y 2026-06-01) están FUERA de la ventana
# DESDE..HASTA y NO deben contar en ninguna agregación (no period leak).


@pytest.fixture
def transacciones_ricas() -> list[TxSpec]:
    return [
        # --- INGRESOS dentro de ventana ---
        _tx("INGRESO", 3000.00, "2026-05-01", fuente="sueldo"),
        _tx("INGRESO", 500.00, "2026-05-10", fuente="freelance"),
        # --- GASTOS dentro de ventana ---
        _tx("GASTO", 800.00, "2026-05-02", categoria="supermercado"),
        _tx("GASTO", 200.00, "2026-05-15", categoria="supermercado"),
        _tx("GASTO", 450.00, "2026-05-05", categoria="delivery"),
        _tx("GASTO", 150.00, "2026-05-20", categoria="delivery"),
        _tx("GASTO", 600.00, "2026-05-03", categoria="alquiler"),
        _tx("GASTO", 100.00, "2026-05-08", categoria="transporte"),
        # --- FUERA de ventana (no deben contar) ---
        _tx("GASTO", 999.00, "2026-04-28", categoria="delivery"),
        _tx("INGRESO", 999.00, "2026-06-01", fuente="sueldo"),
    ]


# Ground truth del SET RICO, calculado A MANO sobre la ventana 2026-05-01..2026-05-31.
# Gastos por categoría:
#   supermercado = 800.00 + 200.00              = 1000.00
#   delivery     = 450.00 + 150.00              =  600.00
#   alquiler     = 600.00                       =  600.00
#   transporte   = 100.00                       =  100.00
GASTOS_POR_CATEGORIA_ESPERADOS: dict[str, float] = {
    "supermercado": 1000.00,
    "delivery": 600.00,
    "alquiler": 600.00,
    "transporte": 100.00,
}

# Balance (ingresos_total, gastos_total):
#   ingresos = 3000.00 + 500.00                          = 3500.00
#   gastos   = 1000.00 + 600.00 + 600.00 + 100.00        = 2300.00
INGRESOS_TOTAL_ESPERADO = 3500.00
GASTOS_TOTAL_ESPERADO = 2300.00
BALANCE_ESPERADO: tuple[float, float] = (INGRESOS_TOTAL_ESPERADO, GASTOS_TOTAL_ESPERADO)

# Surplus = ingresos - gastos = 3500.00 - 2300.00 = 1200.00
SURPLUS_ESPERADO = 1200.00

# coverage_days = nº de FECHAS DISTINTAS con datos dentro de ventana:
#   05-01, 05-02, 05-03, 05-05, 05-08, 05-10, 05-15, 05-20  → 8 fechas distintas
COVERAGE_DAYS_ESPERADO = 8


# ─────────────────────────────────────────────────────────────────────────────
# SET ESCASO (D3 calibración): solo 5 fechas distintas, para verificar que el agente
# declare la cobertura escasa en vez de proyectar con confianza.


@pytest.fixture
def transacciones_escasas() -> list[TxSpec]:
    return [
        _tx("INGRESO", 1000.00, "2026-05-01", fuente="sueldo"),
        _tx("GASTO", 100.00, "2026-05-02", categoria="supermercado"),
        _tx("GASTO", 50.00, "2026-05-03", categoria="delivery"),
        _tx("GASTO", 75.00, "2026-05-04", categoria="transporte"),
        _tx("GASTO", 25.00, "2026-05-05", categoria="varios"),
    ]


# Ground truth del SET ESCASO (ventana 2026-05):
#   coverage_days = 05-01, 05-02, 05-03, 05-04, 05-05 → 5 fechas distintas (dato escaso)
COVERAGE_DAYS_ESCASO_ESPERADO = 5
# surplus = 1000.00 - (100.00 + 50.00 + 75.00 + 25.00) = 1000.00 - 250.00 = 750.00
SURPLUS_ESCASO_ESPERADO = 750.00


# Bloque de "Hechos verificados del ledger" canónico (AI-SPEC §4b + D2): el texto exacto
# que el adapter inyectaría al prompt de Pellegrini. Los tests de no-fabricación asertan que
# todo numeral de la respuesta del agente ⊆ los montos de este bloque.
HECHOS_VERIFICADOS: dict[str, Any] = {
    "ingresos_total": INGRESOS_TOTAL_ESPERADO,
    "gastos_total": GASTOS_TOTAL_ESPERADO,
    "surplus": SURPLUS_ESPERADO,
    "gastos_por_categoria": GASTOS_POR_CATEGORIA_ESPERADOS,
    "coverage_days": COVERAGE_DAYS_ESPERADO,
}
