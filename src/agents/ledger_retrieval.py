"""LedgerRetrieval — adapter del puerto `Retrieval` sobre `LedgerPort` (AGENT-09, D-73).

Pellegrini lee el ledger SIN código de agente nuevo: este adapter satisface el puerto
`Retrieval` (`async def search(...)`) que `ConfiguredAgent` ya consume vía el hook
`scoped_retrieval_factory` del `AgentRegistry`. En vez de chunks de una BC, devuelve los
HECHOS VERIFICADOS del ledger — totales pre-agregados en SQL (`balance`/`surplus`/
`query_by_category`/`coverage_days`) empaquetados como `Hit`s sintéticos.

Por qué los números van pre-agregados (AI-SPEC modo de falla #1): el LLM NUNCA suma filas.
El adapter consulta `LedgerPort` (cuya aritmética vive SQL-side en `ledger.sqlite_store`) y
entrega el resultado ya calculado. El no-fabrication test (D2) asierta que todo numeral del
consejo ⊆ estos hechos.

Capa: vive en `agents/` (infra de agentes). Importa SOLO el PUERTO `core.ports.ledger`
(Protocol) y `core.domain` — NUNCA `ledger.sqlite_store`, para preservar la independencia
`agents` ⟂ `ledger` del contrato import-linter. La instancia concreta del store se inyecta
por construcción (DI), nunca se importa.

`query.kb_ids` se ignora a propósito (RESEARCH A1): Pellegrini no consulta documentos, su
única fuente es el ledger propio del owner — datos confiables, no `<untrusted_content>`.
"""

from __future__ import annotations

from datetime import date

from core.domain import Hit, Query, SearchResult, Subject
from core.ports.ledger import LedgerPort

# Umbral de cobertura por debajo del cual declaramos dato escaso (D3 calibración):
# con pocas fechas distintas el agente debe avisar escasez, no proyectar con confianza.
_COBERTURA_MINIMA_DIAS = 7


def _ventana_mes(hoy: date | None = None) -> tuple[str, str]:
    """Ventana `[primer_día, último_día]` del mes corriente en ISO `YYYY-MM-DD`.

    Selección explícita de ventana (nunca full-table scan): espeja el windowing mensual del
    ledger. `hoy` es inyectable para tests deterministas.
    """
    referencia = hoy if hoy is not None else date.today()
    desde = referencia.replace(day=1)
    if referencia.month == 12:
        siguiente = referencia.replace(year=referencia.year + 1, month=1, day=1)
    else:
        siguiente = referencia.replace(month=referencia.month + 1, day=1)
    hasta = siguiente.fromordinal(siguiente.toordinal() - 1)
    return (desde.isoformat(), hasta.isoformat())


class LedgerRetrieval:
    """Adapter `Retrieval` que sirve hechos pre-agregados del ledger como `Hit`s sintéticos."""

    def __init__(
        self,
        ledger: LedgerPort,
        *,
        desde: str | None = None,
        hasta: str | None = None,
    ) -> None:
        self._ledger = ledger
        if (desde is None) != (hasta is None):
            raise ValueError("desde y hasta deben darse juntos o ninguno")
        if desde is not None and hasta is not None:
            self._desde, self._hasta = desde, hasta
        else:
            self._desde, self._hasta = _ventana_mes()

    async def search(self, query: Query, subject: Subject) -> SearchResult:
        """Devuelve los hechos del ledger (pre-agregados SQL) como `SearchResult`.

        Ignora `query.kb_ids` (Pellegrini no tiene BC documental). El `query.text` solo
        viaja como contexto; los hechos NO dependen de él: la fuente de verdad es el ledger.
        """
        desde, hasta = self._desde, self._hasta
        ingresos_total, gastos_total = self._ledger.balance(desde, hasta)
        surplus = self._ledger.surplus(desde, hasta)
        por_categoria = self._ledger.query_by_category(desde, hasta)
        coverage = self._ledger.coverage_days(desde, hasta)

        if coverage == 0:
            snippet = (
                f"Hechos verificados del ledger (ventana {desde}..{hasta}):\n"
                "- No hay transacciones registradas en esta ventana. "
                "Cobertura: 0 días con datos.\n"
                "- Dato insuficiente: declarar escasez, no proyectar sin datos."
            )
            hit = Hit(
                entry_id=f"ledger:{desde}:{hasta}",
                score=1.0,
                snippet=snippet,
                source_path="ledger.db",
                date=None,
            )
            return SearchResult(
                hits=(hit,),
                degraded=True,
                reason="ledger sin datos en la ventana consultada",
            )

        categorias_txt = (
            "\n".join(
                f"  - {categoria}: ${monto:.2f}"
                for categoria, monto in sorted(
                    por_categoria.items(), key=lambda kv: kv[1], reverse=True
                )
            )
            or "  - (sin gastos categorizados en la ventana)"
        )
        escasez = coverage < _COBERTURA_MINIMA_DIAS
        nota_cobertura = f"Cobertura: {coverage} días con datos " + (
            "(ESCASA — declarar incertidumbre, no proyectar con confianza)."
            if escasez
            else "(suficiente para una lectura del mes)."
        )
        snippet = (
            f"Hechos verificados del ledger (ventana {desde}..{hasta}):\n"
            f"- Ingresos totales: ${ingresos_total:.2f}\n"
            f"- Gastos totales: ${gastos_total:.2f}\n"
            f"- Superávit (ingresos - gastos): ${surplus:.2f}\n"
            f"- Gastos por categoría:\n{categorias_txt}\n"
            f"- {nota_cobertura}"
        )
        hit = Hit(
            entry_id=f"ledger:{desde}:{hasta}",
            score=1.0,
            snippet=snippet,
            source_path="ledger.db",
            date=None,
        )
        return SearchResult(hits=(hit,), degraded=escasez, reason="")
