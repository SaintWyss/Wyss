"""Tests e2e de seguridad — las anclas de aceptación de la Fase 2 (GATE-01..05).

Cada test arma el gateway COMPLETO (build_gateway o ModelGateway con todas las piezas reales,
DB en tmp, FakeAuditPort) y verifica de punta a punta las garantías de seguridad de la fase:

1. Un secreto trampa (env-value/sk-ant-/AKIA/ghp_/JWT/PEM) NUNCA produce egress: el provider se
   invoca 0 veces y el audit lleva el pattern_name, jamás el valor (GATE-03, T-02-secret-egress).
2. Presupuesto agotado bloquea ANTES de la llamada: provider 0 veces, TASK_FAILED (GATE-04).
3. Happy path deja una fila consultable en traces.db con todos los campos D-22 y costo local > 0
   (GATE-05); intercambiabilidad de providers sin tocar el ModelGateway (GATE-01).
"""

import stat
from pathlib import Path

import httpx
import pytest
import respx

from bootstrap.config import load_settings
from bootstrap.gateway import build_gateway
from core.domain.audit import AuditEventType
from core.domain.config import GatewaySettings
from core.domain.errors import BudgetExceeded, SecretDetected
from core.domain.gateway import AgentModelRequest, ModelResponse, TierConfig
from gateway.cost import CostTracker
from gateway.gateway import ModelGateway
from gateway.minimizer import ContextMinimizer
from gateway.providers.fakes import FakeModelProvider
from gateway.router import ModelRouter
from gateway.traces import TraceStore
from tests.ports.fakes import FakeAuditPort

# Secretos trampa multi-formato (D-21). El env-value se inyecta como env_values del settings;
# el resto son formatos built-in. NINGUNO debe producir egress.
_FORMAT_TRAPS: list[tuple[str, str]] = [
    ("anthropic_key", "sk-ant-aaaaaaaaaaaaaaaaaaaaaaaa"),
    # Shape real moderno de OpenAI (sk-proj- CON guión) y Google (AIza+35) — CR-01.
    ("openai_proj", "sk-proj-Ab12Cd34Ef56Gh78Ij90Kl12"),
    ("google_api", "AIzaSyA1234567890abcdefghijklmnopqrstuv"),
    ("aws_access", "AKIAIOSFODNN7EXAMPLE"),
    ("github_pat", "ghp_" + "a" * 36),
    ("jwt", "eyJhbGciOiJI.eyJzdWIiOiJ.SflKxwRJSMeKK"),  # shape JWT
    (
        "pem_private",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIabc\n-----END RSA PRIVATE KEY-----",
    ),
]


def _settings(
    *, global_budget: float = 1000.0, env_values: tuple[str, ...] = ()
) -> GatewaySettings:
    return GatewaySettings(
        tiers={
            "economico": TierConfig(
                provider="litellm", model_alias="gemini-default", max_tokens=64
            )
        },
        prices={"gemini-default": 0.001},
        global_budget=global_budget,
        agent_budgets={},
        env_values=env_values,
    )


@pytest.mark.parametrize("pattern_name,secret", _FORMAT_TRAPS)
async def test_format_secret_never_egresses(
    pattern_name: str,
    secret: str,
    tmp_path: Path,
    audit: FakeAuditPort,
    respx_mock: respx.MockRouter,
) -> None:
    """Cada formato trampa → SecretDetected, provider 0 llamadas, audit con pattern_name."""
    # respx con assert_all_called=False: si se hace CUALQUIER request, el test lo detecta
    # porque no hay ruta registrada (respx levantaría). No registramos ninguna ruta → 0 egress.
    async with httpx.AsyncClient() as client:
        gw = build_gateway(
            _settings(), client=client, audit=audit, data_dir=str(tmp_path)
        )
        req = AgentModelRequest(
            agent_id="a", task_id="t", prompt=f"esto filtra {secret}", tier="economico"
        )
        with pytest.raises(SecretDetected):
            await gw.ask(req)

    assert respx_mock.calls.call_count == 0  # NINGÚN egress
    failed = [e for e in audit.events if e.event_type is AuditEventType.TASK_FAILED]
    assert failed
    for e in failed:
        assert secret not in e.message
        assert secret not in str(e.payload)
    assert any(e.payload.get("pattern") == pattern_name for e in failed)


async def test_env_value_secret_never_egresses(
    tmp_path: Path, audit: FakeAuditPort, respx_mock: respx.MockRouter
) -> None:
    """Un valor real del .env (env-value) en el prompt → bloqueo sin egress (D-21)."""
    secret = "litellm-master-key-supersecreta-9f3a"
    async with httpx.AsyncClient() as client:
        gw = build_gateway(
            _settings(env_values=(secret,)),
            client=client,
            audit=audit,
            data_dir=str(tmp_path),
        )
        req = AgentModelRequest(
            agent_id="a", task_id="t", prompt=f"la key es {secret}", tier="economico"
        )
        with pytest.raises(SecretDetected):
            await gw.ask(req)

    assert respx_mock.calls.call_count == 0
    failed = [e for e in audit.events if e.event_type is AuditEventType.TASK_FAILED]
    assert failed
    for e in failed:
        assert secret not in str(e.payload)
        assert secret not in e.message
    assert any(e.payload.get("pattern") == "env_value" for e in failed)


@pytest.mark.parametrize("env_key", ["GOOGLE_API_KEY", "OPENAI_API_KEY"])
async def test_documented_env_key_value_never_egresses(
    env_key: str,
    tmp_path: Path,
    audit: FakeAuditPort,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-01: el VALOR de GOOGLE_API_KEY/OPENAI_API_KEY exportado entra a la red env-value
    vía bootstrap (load_settings) y bloquea sin egress aunque su formato no sea built-in."""
    secret = f"valor-real-de-{env_key.lower()}-zz9912"
    monkeypatch.setenv(env_key, secret)
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'data_dir = "data"\n'
        'audit_db = "data/audit.db"\n'
        "\n"
        "[gateway]\n"
        "global_budget = 10.0\n"
        "\n"
        "[gateway.tiers.economico]\n"
        'provider = "litellm"\n'
        'model_alias = "gemini-default"\n'
        "max_tokens = 64\n"
        "\n"
        "[gateway.prices]\n"
        "gemini-default = 0.001\n",
        encoding="utf-8",
    )
    settings = load_settings(config_path)
    assert secret in settings.gateway.env_values  # bootstrap SÍ carga la clave (CR-01)
    async with httpx.AsyncClient() as client:
        gw = build_gateway(
            settings.gateway, client=client, audit=audit, data_dir=str(tmp_path)
        )
        req = AgentModelRequest(
            agent_id="a", task_id="t", prompt=f"la clave es {secret}", tier="economico"
        )
        with pytest.raises(SecretDetected):
            await gw.ask(req)

    assert respx_mock.calls.call_count == 0  # NINGÚN egress
    failed = [e for e in audit.events if e.event_type is AuditEventType.TASK_FAILED]
    assert failed
    for e in failed:
        assert secret not in e.message
        assert secret not in str(e.payload)
    assert any(e.payload.get("pattern") == "env_value" for e in failed)


async def test_budget_exhausted_blocks_pre_call(
    tmp_path: Path, audit: FakeAuditPort, respx_mock: respx.MockRouter
) -> None:
    """Presupuesto en 0 → BudgetExceeded ANTES de la llamada: provider 0 veces, TASK_FAILED."""
    async with httpx.AsyncClient() as client:
        gw = build_gateway(
            _settings(global_budget=0.0),
            client=client,
            audit=audit,
            data_dir=str(tmp_path),
        )
        req = AgentModelRequest(
            agent_id="a", task_id="t", prompt="hola sin secreto", tier="economico"
        )
        with pytest.raises(BudgetExceeded):
            await gw.ask(req)

    assert respx_mock.calls.call_count == 0  # bloqueo pre-call
    assert any(e.event_type is AuditEventType.TASK_FAILED for e in audit.events)


async def test_build_gateway_purges_expired_traces(
    tmp_path: Path, audit: FakeAuditPort
) -> None:
    """WR-02: build_gateway purga al boot los traces más viejos que trace_retention_days.

    trace_retention_days (D-22) no es config muerta: el default (90d) borra el trace de
    200 días y conserva el reciente.
    """
    from datetime import UTC, datetime, timedelta

    db_path = tmp_path / "traces.db"
    store = TraceStore(db_path)
    old = (datetime.now(UTC) - timedelta(days=200)).isoformat()

    def _write(trace_id: str, task_id: str, created_at: str | None) -> None:
        store.write(
            trace_id=trace_id,
            task_id=task_id,
            agent_id="a",
            tier="economico",
            purpose="general",
            prompt="p",
            output="o",
            tokens_in=1,
            tokens_out=1,
            cost_usd=0.0,
            latency_ms=1,
            created_at=created_at,
        )

    _write("viejo", "task-old", old)
    _write("nuevo", "task-new", None)
    store.close()

    async with httpx.AsyncClient() as client:
        build_gateway(_settings(), client=client, audit=audit, data_dir=str(tmp_path))

    survivor = TraceStore(db_path)
    assert survivor.query_by_task("task-old") == []  # purgado (200d > 90d)
    assert len(survivor.query_by_task("task-new")) == 1  # conservado
    survivor.close()


def _gateway_with_fake(
    db_path: Path, audit: FakeAuditPort, provider: FakeModelProvider
) -> ModelGateway:
    """Arma un ModelGateway con un provider fake intercambiable (GATE-01)."""
    return ModelGateway(
        router=ModelRouter(
            {
                "economico": TierConfig(
                    provider="litellm", model_alias="gemini-default", max_tokens=64
                )
            }
        ),
        minimizer=ContextMinimizer(env_values=frozenset(), config_patterns=()),
        cost=CostTracker(
            db_path,
            prices={"gemini-default": 0.002},
            global_budget=1000.0,
            agent_budgets={},
            audit=audit,
        ),
        traces=TraceStore(db_path),
        providers={"litellm": provider},
        audit=audit,
    )


async def test_happy_path_leaves_queryable_trace(
    tmp_path: Path, audit: FakeAuditPort
) -> None:
    """Happy path → fila consultable por task_id con todos los campos D-22 y costo local > 0."""
    db_path = tmp_path / "traces.db"
    provider = FakeModelProvider(
        response=ModelResponse(
            text="resultado", tokens_in=50, tokens_out=150, cost_usd=0.0, latency_ms=12
        )
    )
    gw = _gateway_with_fake(db_path, audit, provider)
    req = AgentModelRequest(
        agent_id="belgrano",
        task_id="task-x",
        prompt="resumime esto por favor",
        tier="economico",
        purpose="summarize",
    )

    resp = await gw.ask(req)

    assert resp.cost_usd > 0  # costo LOCAL: (50+150)/1000 * 0.002 = 0.0004
    rows = TraceStore(db_path).query_by_task("task-x")
    assert len(rows) == 1
    row = rows[0]
    assert row["agent_id"] == "belgrano"
    assert row["tier"] == "economico"
    assert row["purpose"] == "summarize"
    assert row["output"] == "resultado"
    assert row["tokens_in"] == 50
    assert row["tokens_out"] == 150
    cost = row["cost_usd"]
    assert isinstance(cost, float) and cost > 0
    assert row["latency_ms"] == 12
    # prompt POST-minimizer (sin secretos), igual al prompt limpio enviado
    assert row["prompt"] == "resumime esto por favor"


async def test_provider_interchangeability(
    tmp_path: Path, audit: FakeAuditPort
) -> None:
    """GATE-01: cambiar el provider fake por otro no cambia el flujo del ModelGateway."""
    db_path = tmp_path / "traces.db"
    other = FakeModelProvider(
        response=ModelResponse(
            text="otro provider", tokens_in=1, tokens_out=1, cost_usd=0.0, latency_ms=1
        ),
        name="otro",
    )
    gw = _gateway_with_fake(db_path, audit, other)
    req = AgentModelRequest(
        agent_id="a", task_id="task-y", prompt="hola", tier="economico"
    )

    resp = await gw.ask(req)

    assert resp.text == "otro provider"
    assert len(TraceStore(db_path).query_by_task("task-y")) == 1


async def test_traces_db_has_restrictive_permissions(
    tmp_path: Path, audit: FakeAuditPort
) -> None:
    """traces.db (prompts completos) se crea con permisos 0600 (T-02-trace-file-perms)."""
    db_path = tmp_path / "traces.db"
    TraceStore(db_path).close()
    mode = stat.S_IMODE(db_path.stat().st_mode)
    assert mode == 0o600, f"esperaba 0600, fue {oct(mode)}"
