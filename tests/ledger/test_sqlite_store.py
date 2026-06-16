"""RED — agregación correcta del ledger SQLite (AGENT-09, AI-SPEC D1/D2).

Estos tests FALLAN hasta que Plan 02 implemente `ledger.sqlite_store.SqliteLedgerStore`
(implementación de `core.ports.ledger.LedgerPort`). El fallo correcto es
`ModuleNotFoundError` al construir el store, NO un import roto a nivel de colección
(los imports de los símbolos aún-no-existentes son diferidos dentro de cada test).

D1 (exactitud aritmética): los totales del store cuadran centavo a centavo con el ground
truth precalculado a mano en `conftest.py`.
D2 (sin fuga de período): las transacciones fuera de la ventana DESDE..HASTA no cuentan.

El store usa su PROPIA DB (`tmp_path/'ledger.db'` — ext4/tmpfs, WAL OK; NUNCA bajo el
repo data/ por el denylist NTFS de la segunda muralla).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.ledger.conftest import (
    BALANCE_ESPERADO,
    COVERAGE_DAYS_ESCASO_ESPERADO,
    COVERAGE_DAYS_ESPERADO,
    DESDE,
    GASTOS_POR_CATEGORIA_ESPERADOS,
    HASTA,
    SURPLUS_ESPERADO,
    TxSpec,
    build_transaccion,
)


def _build_store(db_path: Path, transacciones: list[TxSpec]) -> Any:
    """Construye el store y graba las transacciones (import diferido: RED hasta Plan 02).

    Tipado como `Any`: `SqliteLedgerStore` / `LedgerPort` los define Plan 02; acá el contrato
    se asierta en runtime (RED → ModuleNotFoundError), no estáticamente. El fallo RED cae en
    el cuerpo del test (no en setup del fixture), así pytest lo reporta como FAILED, no ERROR.
    """
    import ledger.sqlite_store as store_mod  # type: ignore[import-untyped,import-not-found,unused-ignore]

    store = store_mod.SqliteLedgerStore(db_path)
    for spec in transacciones:
        store.record(build_transaccion(spec))
    return store


def test_query_by_category_matches_ground_truth(
    tmp_path: Path, transacciones_ricas: list[TxSpec]
) -> None:
    """D1: gastos por categoría en la ventana cuadran exacto con el cálculo manual."""
    store = _build_store(tmp_path / "ledger.db", transacciones_ricas)
    resultado = store.query_by_category(DESDE, HASTA)
    assert dict(resultado) == GASTOS_POR_CATEGORIA_ESPERADOS


def test_balance_matches_ground_truth(
    tmp_path: Path, transacciones_ricas: list[TxSpec]
) -> None:
    """D1: (ingresos_total, gastos_total) cuadran exacto con el cálculo manual."""
    store = _build_store(tmp_path / "ledger.db", transacciones_ricas)
    ingresos, gastos = store.balance(DESDE, HASTA)
    assert (ingresos, gastos) == pytest.approx(BALANCE_ESPERADO)


def test_surplus_matches_ground_truth(
    tmp_path: Path, transacciones_ricas: list[TxSpec]
) -> None:
    """D1: surplus = ingresos - gastos cuadra exacto con el cálculo manual."""
    store = _build_store(tmp_path / "ledger.db", transacciones_ricas)
    assert store.surplus(DESDE, HASTA) == pytest.approx(SURPLUS_ESPERADO)


def test_coverage_days_counts_distinct_dates(
    tmp_path: Path, transacciones_ricas: list[TxSpec]
) -> None:
    """D3 (dato): coverage_days = nº de fechas distintas con datos en ventana."""
    store = _build_store(tmp_path / "ledger.db", transacciones_ricas)
    assert store.coverage_days(DESDE, HASTA) == COVERAGE_DAYS_ESPERADO


def test_window_excludes_out_of_range(
    tmp_path: Path, transacciones_ricas: list[TxSpec]
) -> None:
    """D2: una transacción fuera de DESDE..HASTA NO debe filtrarse a ninguna agregación.

    El set rico incluye un gasto 2026-04-28 ($999) y un ingreso 2026-06-01 ($999): si el
    adapter no filtra por ventana, balance/surplus/categorías se inflan y este test cae.
    """
    store = _build_store(tmp_path / "ledger.db", transacciones_ricas)
    ingresos, gastos = store.balance(DESDE, HASTA)
    # 999.0 de cada extremo NO debe aparecer en ningún total.
    assert ingresos == pytest.approx(BALANCE_ESPERADO[0])
    assert gastos == pytest.approx(BALANCE_ESPERADO[1])
    assert "delivery" in store.query_by_category(DESDE, HASTA)
    # el delivery fuera de ventana ($999) no infla la categoría
    assert store.query_by_category(DESDE, HASTA)["delivery"] == pytest.approx(600.00)


def test_coverage_days_sparse_dataset(
    tmp_path: Path, transacciones_escasas: list[TxSpec]
) -> None:
    """D3 (calibración): dataset escaso reporta exactamente 5 fechas distintas."""
    store = _build_store(tmp_path / "ledger.db", transacciones_escasas)
    assert store.coverage_days(DESDE, HASTA) == COVERAGE_DAYS_ESCASO_ESPERADO
