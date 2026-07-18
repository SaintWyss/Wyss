"""Composition root del gateway de modelos (Pattern 4): WyssSettings → ModelGateway completo.

Este es el ÚNICO módulo que importa juntos los adapters concretos (providers httpx) + la capa
application (router/minimizer/cost/traces) + la fachada `ModelGateway`. El núcleo nunca conoce
httpx ni los adapters; acá se cablea todo por DI manual.

El `AuditPort` se RECIBE inyectado (el caller pasa el `SqliteAuditLogger` concreto) — este módulo
JAMÁS importa el paquete `audit` (contrato import-linter `independence`, Pitfall 4). Las API keys
(ANTHROPIC_API_KEY, LITELLM_MASTER_KEY) salen de `os.environ`, NUNCA de la config ni hardcodeadas
(V2): no entran a config.toml, traces, AuditEvent ni ModelResponse.
"""

import os
import re
from pathlib import Path

import httpx

from core.domain.config import GatewaySettings
from core.ports.audit import AuditPort
from core.ports.gateway import ModelProvider
from gateway.cost import CostTracker
from gateway.gateway import ModelGateway
from gateway.minimizer import ContextMinimizer
from gateway.providers.anthropic import AnthropicProvider
from gateway.providers.litellm import LiteLLMProvider
from gateway.router import ModelRouter
from gateway.traces import TraceStore

# URL base default del proxy LiteLLM del owner (localhost:4000). El override por env
# LITELLM_BASE_URL se lee en build time (no en import) para que el `.env` cargado por
# load_settings() llegue a tiempo.
_LITELLM_DEFAULT_BASE_URL = "http://localhost:4000"


def build_gateway(
    settings: GatewaySettings,
    *,
    client: httpx.AsyncClient,
    audit: AuditPort,
    data_dir: str,
) -> ModelGateway:
    """Arma el ModelGateway completo desde GatewaySettings + deps inyectadas (Pattern 4).

    - `client`: httpx.AsyncClient compartido por los providers. El composition root le APLICA
      `settings.timeout_s` (D-25, WR-03): config gobierna — sin esto el default de httpx es
      5s y las llamadas largas a Claude timeoutearían sistemáticamente.
    - `audit`: AuditPort concreto inyectado (nunca se importa el paquete audit).
    - `data_dir`: directorio de runtime; la traces.db vive en `{data_dir}/traces.db`.

    Las api_key/master_key salen de os.environ (V2). Un valor ausente se pasa como string
    vacío al provider del tier respectivo: el provider solo se invoca si un tier lo enruta, y
    una llamada real sin clave fallará con 401 (auditado), nunca silenciosamente.
    """
    db_path = Path(data_dir) / "traces.db"

    # D-25 (WR-03): el timeout por llamada del TOML se aplica acá — no es config muerta.
    client.timeout = httpx.Timeout(settings.timeout_s)

    router = ModelRouter(dict(settings.tiers))
    minimizer = ContextMinimizer(
        env_values=frozenset(settings.env_values),
        config_patterns=tuple((name, re.compile(rx)) for name, rx in settings.config_patterns),
    )
    traces = TraceStore(db_path)
    # D-22: la retención NO es config muerta — la purga corre en cada boot (WR-02). Hasta que
    # exista el scheduler de Fase 4, este es el único punto donde los traces vencidos expiran.
    traces.purge_older_than(settings.trace_retention_days)
    cost = CostTracker(
        db_path,
        prices=dict(settings.prices),
        global_budget=settings.global_budget,
        agent_budgets=dict(settings.agent_budgets),
        audit=audit,
    )
    providers: dict[str, ModelProvider] = {
        "litellm": LiteLLMProvider(
            client,
            base_url=os.environ.get("LITELLM_BASE_URL", _LITELLM_DEFAULT_BASE_URL),
            master_key=os.environ.get("LITELLM_MASTER_KEY", ""),
        ),
        "anthropic": AnthropicProvider(client, api_key=os.environ.get("ANTHROPIC_API_KEY", "")),
    }
    return ModelGateway(
        router=router,
        minimizer=minimizer,
        cost=cost,
        traces=traces,
        providers=providers,
        audit=audit,
    )
