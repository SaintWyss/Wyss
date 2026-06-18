"""LedgerRetrieval — adapter del puerto Retrieval sobre LedgerPort (AGENT-09, D-73).

Verifica que el adapter:
1. Es estructuralmente un `Retrieval` (satisface el Protocol — mypy + assert de tipado).
2. Devuelve un `SearchResult` cuyos hits codifican los HECHOS pre-agregados (no filas crudas):
   los totales coinciden centavo a centavo con el ground truth de tests/ledger/conftest.py.
3. Ante ledger vacío declara escasez (degraded=True, cobertura 0) en vez de proyectar.

Sin IA: solo el adapter + un SqliteLedgerStore tmp.
"""

from __future__ import annotations

from pathlib import Path

from agents.ledger_retrieval import LedgerRetrieval
from core.domain import Query, Subject
from core.domain.audit import ActorType
from core.ports.knowledge import Retrieval
from ledger.sqlite_store import SqliteLedgerStore
from tests.ledger.conftest import DESDE, HASTA, HECHOS_VERIFICADOS

_SUBJECT = Subject(subject_id="pellegrini", subject_type=ActorType.AGENT)
_QUERY = Query(text="¿dónde se me va la plata?", kb_ids=frozenset())


def test_ledger_retrieval_is_structural_retrieval(ledger_retrieval: LedgerRetrieval) -> None:
    """El adapter satisface el Protocol `Retrieval` (conformidad estructural)."""
    adapter: Retrieval = ledger_retrieval
    assert callable(adapter.search)


async def test_search_encodes_preaggregated_facts(
    ledger_retrieval: LedgerRetrieval,
) -> None:
    """Los hits codifican los totales pre-agregados (no filas crudas) — coinciden con el GT."""
    result = await ledger_retrieval.search(_QUERY, _SUBJECT)
    assert result.hits, "debe devolver al menos un hit con los hechos"
    snippet = result.hits[0].snippet

    # Los montos del ground truth (ingresos/gastos/superávit/categorías) aparecen en el snippet.
    assert f"${HECHOS_VERIFICADOS['ingresos_total']:.2f}" in snippet  # 3500.00
    assert f"${HECHOS_VERIFICADOS['gastos_total']:.2f}" in snippet  # 2300.00
    assert f"${HECHOS_VERIFICADOS['surplus']:.2f}" in snippet  # 1200.00
    for categoria, monto in HECHOS_VERIFICADOS["gastos_por_categoria"].items():
        assert categoria in snippet
        assert f"${monto:.2f}" in snippet
    # 8 días de cobertura → no escaso → no degradado.
    assert result.degraded is False


async def test_empty_ledger_declares_scarcity(tmp_path: Path) -> None:
    """Ledger vacío → declara cobertura 0 y degradación, nunca proyecta sin datos (D3)."""
    store = SqliteLedgerStore(tmp_path / "empty.db")
    try:
        adapter = LedgerRetrieval(store, desde=DESDE, hasta=HASTA)
        result = await adapter.search(_QUERY, _SUBJECT)
    finally:
        store.close()

    assert result.degraded is True
    assert result.hits
    snippet = result.hits[0].snippet.lower()
    assert "0 días" in snippet or "cobertura: 0" in snippet
