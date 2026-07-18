"""RED/E2E — el gate de presupuesto bloquea a Pellegrini ANTES del provider (AGENT-07, D4).

AI-SPEC D4 / failure mode #4: con `agent_budgets["pellegrini"]` agotado, la siguiente
`gateway.ask(AgentModelRequest(agent_id="pellegrini", ...))` levanta `BudgetExceeded` y el
provider NO se invoca (el gasto sin tope es el fallo que esto previene).

Usa el ModelGateway REAL (router + minimizer + cost + traces reales, DB en tmp_path) con un
`FakeModelProvider` que cuenta invocaciones (`.calls`). El gate vive en `gateway/cost.py`
(DO NOT MODIFY) — este test asierta su comportamiento end-to-end para el agent_id pellegrini.

Marcado `gateway` (suite del gateway). DB en tmp_path (ext4/tmpfs — WAL OK).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.domain.errors import BudgetExceeded
from core.domain.gateway import AgentModelRequest, ModelResponse, TierConfig
from gateway.cost import CostTracker
from gateway.gateway import ModelGateway
from gateway.minimizer import ContextMinimizer
from gateway.providers.fakes import FakeModelProvider
from gateway.router import ModelRouter
from gateway.traces import TraceStore
from tests.ports.fakes import FakeAuditPort

pytestmark = pytest.mark.gateway

# El alias económico de Pellegrini (D-81) y su precio local de test.
_ALIAS = "gemini-default"
_PRICE_PER_1K = 1.0


def _pellegrini_gateway(
    db_path: Path,
    *,
    provider: FakeModelProvider,
    pellegrini_budget: float,
) -> ModelGateway:
    """ModelGateway real con tier economico → provider litellm y tope por-agente de Pellegrini."""
    router = ModelRouter(
        {"economico": TierConfig(provider="litellm", model_alias=_ALIAS, max_tokens=64)}
    )
    minimizer = ContextMinimizer(env_values=frozenset(), config_patterns=())
    cost = CostTracker(
        db_path,
        prices={_ALIAS: _PRICE_PER_1K},
        global_budget=1000.0,
        agent_budgets={"pellegrini": pellegrini_budget},
        audit=FakeAuditPort(),
    )
    traces = TraceStore(db_path)
    return ModelGateway(
        router=router,
        minimizer=minimizer,
        cost=cost,
        traces=traces,
        providers={"litellm": provider},
        audit=FakeAuditPort(),
    )


def _ask(prompt: str = "¿cómo voy de plata?") -> AgentModelRequest:
    return AgentModelRequest(
        agent_id="pellegrini", task_id="fin-1", prompt=prompt, tier="economico"
    )


async def test_budget_exhaustion_blocks_before_provider(tmp_path: Path) -> None:
    """D4: agotado el tope de pellegrini, la próxima ask() veta SIN tocar al provider.

    El gate estima el costo de pre-autorización con la heurística del prompt (D-25), pero
    `cost.record` persiste el costo REAL de los tokens de la respuesta (500+500 → 1.0 USD).
    Con el tope = 1.0, tras la 1ra llamada el gasto registrado iguala el tope; la 2da
    `authorize()` (gasto 1.0 + estimado > 1.0) veta ANTES de `provider.complete()` — el
    contador `.calls` NO aumenta en la llamada vetada (failure mode #4 / AGENT-07).
    """
    provider = FakeModelProvider(
        response=ModelResponse(
            text="consejo", tokens_in=500, tokens_out=500, cost_usd=0.0, latency_ms=1
        )
    )
    # tope = 1.0 USD; la 1ra llamada registra 1.0 (costo real) → la 2da veta.
    gw = _pellegrini_gateway(
        tmp_path / "ledger-traces.db", provider=provider, pellegrini_budget=1.0
    )

    await gw.ask(_ask())  # 1ra: registra 1.0 (gasto real) → gasto == tope
    calls_after_first = len(provider.calls)
    assert calls_after_first == 1

    with pytest.raises(BudgetExceeded, match="pellegrini"):
        await gw.ask(_ask())  # 2da: 1.0 (gasto) + est > 1.0 → veta antes del provider

    # el provider NO fue invocado en la llamada vetada
    assert len(provider.calls) == calls_after_first


async def test_other_agent_unaffected_by_pellegrini_cap(tmp_path: Path) -> None:
    """D4 (aislamiento): el tope de pellegrini no afecta a otro agent_id bajo el global."""
    provider = FakeModelProvider(
        response=ModelResponse(text="x", tokens_in=500, tokens_out=500, cost_usd=0.0, latency_ms=1)
    )
    gw = _pellegrini_gateway(tmp_path / "t.db", provider=provider, pellegrini_budget=1.0)

    # agotar el tope de pellegrini con una llamada (registra 1.0 == tope)
    await gw.ask(_ask())
    with pytest.raises(BudgetExceeded, match="pellegrini"):
        await gw.ask(_ask())  # pellegrini ya agotado → veta
    # belgrano (sin cap por-agente) sigue pasando bajo el global
    otro = AgentModelRequest(agent_id="belgrano", task_id="b-1", prompt="hola", tier="economico")
    resp = await gw.ask(otro)
    assert resp.text == "x"
