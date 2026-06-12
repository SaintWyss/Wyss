"""WyssSettings — destino frozen de la validación Pydantic del plan 01-05.

Pydantic NO entra acá: bootstrap convierte el modelo validado a este dataclass de dominio.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from core.domain.gateway import TierConfig
from core.domain.knowledge import IngestSettings
from core.domain.policy import PolicyRules


@dataclass(frozen=True, slots=True)
class GatewaySettings:
    """Config del gateway de modelos ya validada, como vocabulario de dominio (02-05).

    Pydantic muere en bootstrap: este es el frozen dataclass que consume el composition root
    (`bootstrap.gateway.build_gateway`). `TierConfig` vive en `core.domain.gateway` (02-03), así
    que importarla acá NO crea ciclo. `config_patterns` lleva SOLO los patrones extra del config
    (nombre, regex-string); el merge con `BUILTIN_SECRET_PATTERNS` lo hace el minimizer en runtime
    (D-21, aditivo). `env_values` son los valores del `.env` cargados al boot (D-21) para el
    bloqueo por substring exacto del minimizer.
    """

    tiers: Mapping[str, TierConfig]
    prices: Mapping[str, float]
    global_budget: float
    agent_budgets: Mapping[str, float] = field(default_factory=dict)
    timeout_s: float = 120.0  # D-25 default
    trace_retention_days: int = 90  # D-22 default
    # repr=False: env_values lleva los VALORES reales de las API keys — un repr()/print/
    # f-string de debugging o un mensaje de excepción que incluya el settings NO debe
    # imprimirlas (WR-01: "secrets never appear in exceptions/logs").
    env_values: tuple[str, ...] = field(default=(), repr=False)
    config_patterns: tuple[tuple[str, str], ...] = ()  # (nombre, regex-string)


@dataclass(frozen=True, slots=True)
class WyssSettings:
    """Configuración del sistema ya validada, como vocabulario de dominio."""

    data_dir: Path
    audit_db: Path
    policy: PolicyRules
    gateway: GatewaySettings = field(
        default_factory=lambda: GatewaySettings(tiers={}, prices={}, global_budget=0.0)
    )
    ingest: IngestSettings = field(default_factory=IngestSettings)
