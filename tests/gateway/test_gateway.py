"""Tests de la fachada ModelGateway.ask() — orquestación de Flow 4 (02-05, GATE-01..05).

`ModelGateway` compone los componentes de las olas 02-02/03/04 en el orden EXACTO de Flow 4:
router.resolve → minimizer.scan (fail-closed) → cost.authorize → provider.complete (retry D-25)
→ cost.record → traces.write → audit.log. Estos tests fijan ese orden y sus garantías de
seguridad: el secreto/budget bloquean ANTES de cualquier provider.complete (provider invocado
0 veces), el secreto nunca entra al audit, y el ModelResponse devuelto lleva el costo LOCAL.
"""

import re
from pathlib import Path

import pytest

from core.domain.audit import AuditEventType
from core.domain.errors import (
    BudgetExceeded,
    ConfigError,
    SecretDetected,
    UnknownTier,
)
from core.domain.gateway import (
    AgentModelRequest,
    ModelRequest,
    ModelResponse,
    TierConfig,
)
from gateway.cost import CostTracker
from gateway.gateway import ModelGateway
from gateway.minimizer import ContextMinimizer
from gateway.providers.fakes import FakeModelProvider
from gateway.router import ModelRouter
from gateway.traces import TraceStore
from tests.ports.fakes import FakeAuditPort


def _tiers() -> dict[str, TierConfig]:
    return {
        "economico": TierConfig(
            provider="litellm", model_alias="gemini-default", max_tokens=512
        ),
        "fuerte": TierConfig(
            provider="anthropic", model_alias="claude-opus", max_tokens=1024
        ),
    }


def _build_gateway(
    *,
    db_path: Path,
    audit: FakeAuditPort,
    provider: FakeModelProvider,
    env_values: frozenset[str] = frozenset(),
    global_budget: float = 1000.0,
    prices: dict[str, float] | None = None,
) -> ModelGateway:
    """Arma un ModelGateway con un único provider 'litellm' y todo lo demás real (DB en tmp)."""
    router = ModelRouter(_tiers())
    minimizer = ContextMinimizer(env_values=env_values, config_patterns=())
    cost = CostTracker(
        db_path,
        prices=prices or {"gemini-default": 1.0, "claude-opus": 5.0},
        global_budget=global_budget,
        agent_budgets={},
        audit=audit,
    )
    traces = TraceStore(db_path)
    return ModelGateway(
        router=router,
        minimizer=minimizer,
        cost=cost,
        traces=traces,
        providers={"litellm": provider, "anthropic": provider},
        audit=audit,
    )


async def test_happy_path_returns_response_with_local_cost(
    traces_db_path: Path, audit: FakeAuditPort
) -> None:
    """ask() resuelve, minimiza, autoriza, llama, registra costo, escribe trace y audita."""
    provider = FakeModelProvider(
        response=ModelResponse(
            text="respuesta", tokens_in=100, tokens_out=200, cost_usd=0.0, latency_ms=42
        )
    )
    gw = _build_gateway(db_path=traces_db_path, audit=audit, provider=provider)
    req = AgentModelRequest(
        agent_id="belgrano", task_id="t-1", prompt="hola mundo", tier="economico"
    )

    resp = await gw.ask(req)

    # cost_usd LOCAL (D-24): (100+200)/1000 * 1.0 = 0.3, NO el 0.0 del provider.
    assert resp.cost_usd == pytest.approx(0.3)
    assert resp.text == "respuesta"
    # trace consultable (D-22)
    rows = TraceStore(traces_db_path).query_by_task("t-1")
    assert len(rows) == 1
    assert rows[0]["cost_usd"] == pytest.approx(0.3)
    assert rows[0]["output"] == "respuesta"
    # audita COST_RECORDED (del cost.record) y un evento del gateway
    assert any(e.event_type is AuditEventType.COST_RECORDED for e in audit.events)


async def test_secret_blocks_before_any_egress(
    traces_db_path: Path, audit: FakeAuditPort
) -> None:
    """scan() corre ANTES del provider: SecretDetected → provider invocado 0 veces (D-20)."""
    provider = FakeModelProvider()
    secret = "sk-ant-aaaaaaaaaaaaaaaaaaaaaaaa"
    gw = _build_gateway(db_path=traces_db_path, audit=audit, provider=provider)
    req = AgentModelRequest(
        agent_id="a", task_id="t-2", prompt=f"mi clave es {secret}", tier="economico"
    )

    with pytest.raises(SecretDetected):
        await gw.ask(req)

    assert provider.calls == []  # NINGÚN egress


async def test_secret_audit_never_contains_value(
    traces_db_path: Path, audit: FakeAuditPort
) -> None:
    """El AuditEvent del bloqueo lleva pattern_name, nunca el valor del secreto (D-20)."""
    provider = FakeModelProvider()
    secret = "sk-ant-bbbbbbbbbbbbbbbbbbbbbbbb"
    gw = _build_gateway(db_path=traces_db_path, audit=audit, provider=provider)
    req = AgentModelRequest(
        agent_id="a", task_id="t-3", prompt=f"token: {secret}", tier="economico"
    )

    with pytest.raises(SecretDetected):
        await gw.ask(req)

    failed = [e for e in audit.events if e.event_type is AuditEventType.TASK_FAILED]
    assert failed, "debe auditarse TASK_FAILED al bloquear el secreto"
    for e in failed:
        assert secret not in e.message
        assert secret not in str(e.payload)
        assert e.payload.get("pattern") == "anthropic_key"


async def test_budget_exceeded_blocks_pre_call(
    traces_db_path: Path, audit: FakeAuditPort
) -> None:
    """authorize() veta ANTES del provider: BudgetExceeded → provider invocado 0 veces (D-18)."""
    provider = FakeModelProvider(
        response=ModelResponse(
            text="x", tokens_in=10, tokens_out=10, cost_usd=0.0, latency_ms=1
        )
    )
    gw = _build_gateway(
        db_path=traces_db_path, audit=audit, provider=provider, global_budget=0.0
    )
    req = AgentModelRequest(agent_id="a", task_id="t-4", prompt="hola", tier="economico")

    with pytest.raises(BudgetExceeded):
        await gw.ask(req)

    assert provider.calls == []  # bloqueo pre-call
    assert any(e.event_type is AuditEventType.TASK_FAILED for e in audit.events)


async def test_provider_receives_tier_model_and_max_tokens(
    traces_db_path: Path, audit: FakeAuditPort
) -> None:
    """El ModelRequest usa model_alias + max_tokens del TierConfig, no del caller (D-16)."""
    provider = FakeModelProvider(
        response=ModelResponse(
            text="ok", tokens_in=1, tokens_out=1, cost_usd=0.0, latency_ms=1
        )
    )
    gw = _build_gateway(db_path=traces_db_path, audit=audit, provider=provider)
    req = AgentModelRequest(agent_id="a", task_id="t-5", prompt="hola", tier="fuerte")

    await gw.ask(req)

    assert len(provider.calls) == 1
    sent: ModelRequest = provider.calls[0]
    assert sent.model_alias == "claude-opus"
    assert sent.max_tokens == 1024


async def test_unknown_tier_propagates_without_fallback(
    traces_db_path: Path, audit: FakeAuditPort
) -> None:
    """tier inexistente → UnknownTier propagado, sin fallback; se audita TASK_FAILED (D-17)."""
    provider = FakeModelProvider()
    gw = _build_gateway(db_path=traces_db_path, audit=audit, provider=provider)
    req = AgentModelRequest(
        agent_id="a", task_id="t-6", prompt="hola", tier="inexistente"
    )

    with pytest.raises(UnknownTier):
        await gw.ask(req)

    assert provider.calls == []
    assert any(e.event_type is AuditEventType.TASK_FAILED for e in audit.events)


async def test_missing_provider_raises_domain_error_audited(
    traces_db_path: Path, audit: FakeAuditPort
) -> None:
    """WR-04: tier que apunta a un provider no construido → ConfigError de dominio AUDITADO
    (TASK_FAILED), nunca un KeyError crudo sin rastro."""
    gw = ModelGateway(
        router=ModelRouter(_tiers()),
        minimizer=ContextMinimizer(env_values=frozenset(), config_patterns=()),
        cost=CostTracker(
            traces_db_path,
            prices={"gemini-default": 1.0},
            global_budget=1000.0,
            agent_budgets={},
            audit=audit,
        ),
        traces=TraceStore(traces_db_path),
        providers={},  # cableado a mano sin el provider del tier
        audit=audit,
    )
    req = AgentModelRequest(agent_id="a", task_id="t-7", prompt="hola", tier="economico")

    with pytest.raises(ConfigError, match="litellm"):
        await gw.ask(req)

    assert any(e.event_type is AuditEventType.TASK_FAILED for e in audit.events)


def test_module_does_not_import_audit_package() -> None:
    """gateway.gateway depende SOLO de core.ports.audit / core.domain.audit (Pitfall 4)."""
    src = Path("src/gateway/gateway.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*from audit\b", src, re.MULTILINE)
    assert not re.search(r"^\s*import audit\b", src, re.MULTILINE)
