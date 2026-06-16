"""RED — cero cifras fabricadas en el consejo de Pellegrini (AGENT-09, AI-SPEC D2).

D2 / trazabilidad: todo numeral ($N) que Pellegrini reporta DEBE pertenecer al bloque
"Hechos verificados del ledger" que el adapter le inyectó (`reported_numbers ⊆ ledger_facts`).
Un monto que el agente inventó o recalculó mal NO está en los hechos → FAIL.

Estos tests FALLAN hasta que Plan 03 implemente `agents.pellegrini.advise(...)`, que arma el
prompt con el bloque de hechos verificados y llama al gateway (stub acá). El import es diferido
dentro del helper: el fallo correcto es `ModuleNotFoundError`.

El gateway stub devuelve una respuesta canónica fija; el test extrae los montos con regex y
asierta el subconjunto. No consume IA real (CI-safe, sin budget).
"""

from __future__ import annotations

import re

from core.domain.gateway import ModelResponse
from tests.ledger.conftest import HECHOS_VERIFICADOS

# Regex de montos en dólares: $1.234,56 / $1234.56 / $1,234 / $800 — captura el numeral crudo.
_MONTO_RE = re.compile(r"\$\s*([\d][\d.,]*)")


def _to_float(raw: str) -> float:
    """Normaliza un monto string (quita separadores de miles) a float comparable."""
    if raw.count(",") == 1:
        cleaned = raw.replace(".", "").replace(",", ".")
    else:
        cleaned = raw.replace(",", "")
    return float(cleaned)


def _facts_amounts() -> set[float]:
    """Conjunto de montos válidos del bloque de hechos verificados."""
    amounts: set[float] = {
        float(HECHOS_VERIFICADOS["ingresos_total"]),
        float(HECHOS_VERIFICADOS["gastos_total"]),
        float(HECHOS_VERIFICADOS["surplus"]),
    }
    amounts.update(float(v) for v in HECHOS_VERIFICADOS["gastos_por_categoria"].values())
    return amounts


class _StubGateway:
    """ModelGatewayPort stub: devuelve una respuesta advisory canónica fija (sin red)."""

    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: int = 0

    async def ask(self, request: object) -> ModelResponse:
        self.calls += 1
        return ModelResponse(
            text=self._text, tokens_in=10, tokens_out=20, cost_usd=0.0, latency_ms=1
        )


async def _advise(gateway: object) -> str:
    """Corre Pellegrini.advise con hechos verificados inyectados (import diferido: RED)."""
    import agents.pellegrini as pellegrini  # type: ignore[import-untyped,import-not-found,unused-ignore]

    texto: str = await pellegrini.advise(gateway=gateway, hechos=HECHOS_VERIFICADOS)
    return texto


async def test_reported_amounts_subset_of_facts() -> None:
    """D2: todo monto del consejo ⊆ montos del bloque de hechos verificados.

    La respuesta canónica solo cita montos reales (3500, 2300, 1200, 600...). Si Pellegrini
    (Plan 03) reinyecta esos hechos sin recalcular, todos los $N de la salida cuadran.
    """
    # respuesta canónica que SOLO usa montos del ledger (caso PASS de referencia)
    canned = (
        "Tenés $3500.00 de ingresos y $2300.00 de gastos este mes, te sobran $1200.00. "
        "Lo más pesado es alquiler ($600.00) y delivery ($600.00)."
    )
    gw = _StubGateway(canned)
    respuesta = await _advise(gw)

    reported = {_to_float(m) for m in _MONTO_RE.findall(respuesta)}
    facts = _facts_amounts()
    fabricados = reported - facts
    assert not fabricados, f"cifras fabricadas (no en hechos): {fabricados}"


async def test_fabricated_amount_is_detected() -> None:
    """D2 (control negativo): un monto inventado NO está en los hechos → el assert lo detecta.

    Verifica que el detector es real: si Pellegrini devolviera un $9999.99 que no sale de
    ninguna agregación, `reported - facts` no es vacío.
    """
    canned = "Te recomiendo ahorrar $9999.99 el mes que viene."  # monto fabricado
    gw = _StubGateway(canned)
    respuesta = await _advise(gw)

    reported = {_to_float(m) for m in _MONTO_RE.findall(respuesta)}
    facts = _facts_amounts()
    assert reported - facts, "el detector debe marcar el monto fabricado como fuera de hechos"
