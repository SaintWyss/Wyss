"""Tests del retry centralizado del ModelGateway (D-25) con respx (sin red).

El retry vive SOLO en `ModelGateway._complete_with_retry` (los providers httpx hacen
raise_for_status sin reintentar, 02-03). Estos tests fijan: transiente (429/5xx) reintenta y
RE-PASA el gate cada intento (D-25); 4xx hace fail-fast (1 sola llamada, Pitfall 1); y agotar
los retries re-raise el error auditando TASK_FAILED.
"""

from pathlib import Path

import httpx
import pytest
import respx

from core.domain.audit import AuditEventType
from core.domain.gateway import AgentModelRequest, TierConfig
from gateway.cost import CostTracker
from gateway.gateway import ModelGateway
from gateway.minimizer import ContextMinimizer
from gateway.providers.litellm import LiteLLMProvider
from gateway.router import ModelRouter
from gateway.traces import TraceStore
from tests.ports.fakes import FakeAuditPort

_LITELLM_URL = "http://litellm.test:4000/v1/chat/completions"
_OK_BODY = {
    "choices": [{"message": {"content": "ok"}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 7},
}


def _build_gateway(
    *,
    db_path: Path,
    audit: FakeAuditPort,
    client: httpx.AsyncClient,
) -> ModelGateway:
    router = ModelRouter(
        {
            "economico": TierConfig(
                provider="litellm", model_alias="gemini-default", max_tokens=64
            )
        }
    )
    minimizer = ContextMinimizer(env_values=frozenset(), config_patterns=())
    cost = CostTracker(
        db_path,
        prices={"gemini-default": 0.001},
        global_budget=1000.0,
        agent_budgets={},
        audit=audit,
    )
    traces = TraceStore(db_path)
    provider = LiteLLMProvider(
        client, base_url="http://litellm.test:4000", master_key="k"
    )
    return ModelGateway(
        router=router,
        minimizer=minimizer,
        cost=cost,
        traces=traces,
        providers={"litellm": provider},
        audit=audit,
        backoff_base=0.0,  # tests rápidos: sin sleep real
    )


async def test_transient_429_then_200_recovers(
    traces_db_path: Path, audit: FakeAuditPort, respx_mock: respx.MockRouter
) -> None:
    """429 en el 1er intento, 200 en el 2do → ask() reintenta y devuelve; gate re-pasado 2x."""
    route = respx_mock.post(_LITELLM_URL)
    route.side_effect = [
        httpx.Response(429, json={"error": "rate limited"}),
        httpx.Response(200, json=_OK_BODY),
    ]
    async with httpx.AsyncClient() as client:
        gw = _build_gateway(db_path=traces_db_path, audit=audit, client=client)
        req = AgentModelRequest(agent_id="a", task_id="t-1", prompt="hola")
        resp = await gw.ask(req)

    assert resp.text == "ok"
    assert route.call_count == 2  # 1 fallo transiente + 1 éxito
    # el gate (record) registró una vez (éxito); el authorize se re-pasó cada intento.
    cost_events = [
        e for e in audit.events if e.event_type is AuditEventType.COST_RECORDED
    ]
    assert cost_events  # registró el costo del intento exitoso


async def test_4xx_fail_fast_no_retry(
    traces_db_path: Path, audit: FakeAuditPort, respx_mock: respx.MockRouter
) -> None:
    """400 → ask() NO reintenta (provider invocado 1 sola vez) y propaga el error."""
    route = respx_mock.post(_LITELLM_URL).mock(
        return_value=httpx.Response(400, json={"error": "bad request"})
    )
    async with httpx.AsyncClient() as client:
        gw = _build_gateway(db_path=traces_db_path, audit=audit, client=client)
        req = AgentModelRequest(agent_id="a", task_id="t-2", prompt="hola")
        with pytest.raises(httpx.HTTPStatusError):
            await gw.ask(req)

    assert route.call_count == 1  # fail-fast, sin retry (Pitfall 1)
    assert any(e.event_type is AuditEventType.TASK_FAILED for e in audit.events)


async def test_transient_exhausts_retries(
    traces_db_path: Path, audit: FakeAuditPort, respx_mock: respx.MockRouter
) -> None:
    """503 siempre → tras 2 retries (3 intentos) re-raise; se audita TASK_FAILED."""
    route = respx_mock.post(_LITELLM_URL).mock(
        return_value=httpx.Response(503, json={"error": "unavailable"})
    )
    async with httpx.AsyncClient() as client:
        gw = _build_gateway(db_path=traces_db_path, audit=audit, client=client)
        req = AgentModelRequest(agent_id="a", task_id="t-3", prompt="hola")
        with pytest.raises(httpx.HTTPStatusError):
            await gw.ask(req)

    assert route.call_count == 3  # 1 + 2 retries (D-25)
    assert any(e.event_type is AuditEventType.TASK_FAILED for e in audit.events)
