"""Frontera Pydantic→dominio: carga y valida `config.toml` al boot (D-09, D-10).

Este módulo es el ÚNICO lugar donde vive Pydantic. Lee el TOML con `tomllib`, lo valida
con un modelo Pydantic v2 (`extra="forbid"`, fail-closed ante typos/claves extra), y
produce el frozen dataclass `WyssSettings` de `core.domain` — Pydantic muere acá, el
núcleo nunca ve un `BaseModel` (import-linter lo garantiza).

Invariante estructural (regla #2): las reglas `[[policy.deny]]` de config solo AGREGAN a
`BUILTIN_DENY` (`PolicyRules.deny = BUILTIN_DENY + tuple(config_deny)`); no hay ruta para
vaciar la denylist built-in editando un archivo.

Decisión de diseño: ante config inexistente, TOML mal formado o validación fallida se
levanta `ConfigError` (excepción de dominio) con un mensaje legible que nombra el path y,
para errores de validación, el campo (loc). El `sys.exit` se deja al caller CLI de Fase 5,
de modo que el comportamiento sea testeable con `pytest.raises` sin matar el proceso.
"""

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from core.domain.agent import AgentDefinition
from core.domain.config import GatewaySettings
from core.domain.config import WyssSettings as DomainWyssSettings
from core.domain.errors import ConfigError
from core.domain.gateway import TierConfig
from core.domain.knowledge import IngestSettings
from core.domain.policy import AggregateThresholds, DenyRule, PolicyRules
from core.domain.risk import RiskLevel
from core.policy.builtin_deny import BUILTIN_DENY

# Variables del .env que el gateway conoce: sus valores se cargan al boot como `env_values`
# del minimizer (D-21), para el bloqueo por substring exacto. Sus NOMBRES viven acá; los
# VALORES salen de os.environ y nunca se loguean ni entran a config.toml/traces (V2/V7).
# Cubre TODOS los secretos documentados en config/.env.example (CR-01): si una clave nueva
# se documenta ahí, DEBE agregarse acá para que entre a la red de substring del minimizer.
_GATEWAY_ENV_KEYS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "LITELLM_MASTER_KEY",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
)

# Providers que `bootstrap.gateway.build_gateway` sabe construir. Un tier que apunte a otro
# string (typo: "antropic", "ollama") es error de config y debe abortar el BOOT con ConfigError
# legible — no un KeyError crudo en runtime tras pasar router y minimizer (WR-04).
_KNOWN_PROVIDERS: frozenset[str] = frozenset({"litellm", "anthropic"})

# Niveles base por action_type (docs/13). Fail-closed: lo desconocido lo resuelve el engine a C.
_BASE_LEVELS: dict[str, RiskLevel] = {
    "file.read": RiskLevel.A,
    "file.list": RiskLevel.A,
    "file.move": RiskLevel.B,
    "file.rename": RiskLevel.B,
    "file.create": RiskLevel.C,
    "file.write": RiskLevel.C,
    "file.delete": RiskLevel.C,
    "shell.run": RiskLevel.C,
    # Acciones de dominio financiero (Fase 8). Confirmado contra docs/10 §7: ninguna
    # escritura financiera es nivel D (§7 enumera las prohibiciones D y no las incluye).
    # query = lectura → A; record = mutación owner-instruida → B (segunda muralla, no D).
    "finance.query": RiskLevel.A,
    "finance.record": RiskLevel.B,
}


def _strip_env_comment(value: str) -> str:
    """Quita comentarios inline no quoteados de un valor .env."""
    in_single = False
    in_double = False
    escaped = False
    for i, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_double:
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "#" and not in_single and not in_double and (
            i == 0 or value[i - 1].isspace()
        ):
            return value[:i].rstrip()
    return value.strip()


def _parse_env_value(raw: str) -> str:
    """Parsea el lado derecho de una línea KEY=VALUE de .env."""
    value = _strip_env_comment(raw.strip())
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
        if raw.strip().startswith('"'):
            value = bytes(value, "utf-8").decode("unicode_escape")
    return value


def _load_dotenv(dotenv_path: Path) -> None:
    """Carga `config/.env` en os.environ antes de convertir settings (WR-10).

    Bootstrap es la frontera de parsing: el core sigue sin IO ni dependencias externas. No
    pisa variables ya exportadas, para preservar el entorno explícito del proceso.
    """
    try:
        lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return
    except OSError as e:
        raise ConfigError(f"no se pudo leer el .env: {dotenv_path}") from e

    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()
        if "=" not in line:
            raise ConfigError(f"línea inválida en {dotenv_path}:{line_no}")
        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ConfigError(f"clave inválida en {dotenv_path}:{line_no}: {key!r}")
        os.environ.setdefault(key, _parse_env_value(raw_value))


class DenyRuleModel(BaseModel):
    """Una regla de denylist adicional desde config. `extra="forbid"` → typo = boot abortado."""

    model_config = ConfigDict(extra="forbid")

    id: str
    match_action: str
    match_target: str | None = None
    description: str = "Regla de denegación definida por el owner en config."


class PolicyConfigModel(BaseModel):
    """Sección [policy]: umbrales de agregación + denylist aditiva. `extra="forbid"` fail-closed."""

    model_config = ConfigDict(extra="forbid")

    file_count_b: int = 10
    file_count_c: int = 100
    dir_count_c: int = 5
    delete_count_d: int = 50
    sensitive_dirs: list[str] = []
    deny: list[DenyRuleModel] = []


class TierConfigModel(BaseModel):
    """Un tier de la sección [gateway.tiers]: provider + alias + tope de tokens (D-16)."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    model_alias: str
    max_tokens: int


class SecretPatternModel(BaseModel):
    """Patrón de secreto ADICIONAL por config (D-21): se agrega a los built-in, no los vacía."""

    model_config = ConfigDict(extra="forbid")

    name: str
    regex: str


class GatewayConfigModel(BaseModel):
    """Sección [gateway]: tiers, precios, presupuesto, timeout, retención, patrones extra.

    `extra="forbid"` fail-closed (un typo aborta el boot). Mapea a `GatewaySettings` frozen
    en `_to_gateway_settings` (Pydantic muere ahí). Defaults de timeout/retención por D-25/D-22.
    """

    model_config = ConfigDict(extra="forbid")

    tiers: dict[str, TierConfigModel] = {}
    prices: dict[str, float] = {}
    global_budget: float = 0.0
    agent_budgets: dict[str, float] = {}
    timeout_s: float = 120.0
    trace_retention_days: int = 90
    secret_patterns: list[SecretPatternModel] = []


class IngestConfigModel(BaseModel):
    """Sección [ingest]: configuración del pipeline de ingesta (D-33/D-42).

    `extra="forbid"` fail-closed: un typo en la clave aborta el boot con ConfigError legible
    (T-03-01). Mapea a `IngestSettings` frozen en `_to_ingest_settings` (Pydantic muere ahí).
    Las listas se convierten a tuplas en la conversión — IngestSettings es frozen (no listas).
    """

    model_config = ConfigDict(extra="forbid")

    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 51  # ~10% de 512
    max_file_bytes: int = 104_857_600  # 100 MB (D-41)
    dir_denylist: list[str] = [
        ".git",
        "node_modules",
        ".cache",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".tox",
    ]
    entropy_allowlist: list[str] = []  # D-30: globs que desactivan capa 3
    default_kb_id: str = "default"  # Open Question 2: default si no se especifica --bc
    max_attempts: int = 3  # D-39: reintentos automáticos antes de --retry-failed


class AgentConfigModel(BaseModel):
    """Entrada [[agents]]: configuración declarativa de agentes (D-73).

    `extra="forbid"` fail-closed: un typo en la config de un agente aborta el boot con
    ConfigError legible. Mapea a `AgentDefinition` frozen en `_to_agent_definition`.
    """

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    name: str
    domain: str
    knowledge_bases: list[str] = []
    model_tier: str = "economico"
    budget_usd: float = 0.0


class OrchestratorConfigModel(BaseModel):
    """Sección [orchestrator]: modo del planner y tope opcional del agente interno."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["deterministic", "llm"] = "deterministic"
    tier: str = "economico"
    budget_usd: float | None = None


class WyssConfigModel(BaseModel):
    """Raíz del config.toml validado. `frozen=True` + `extra="forbid"` (fail-closed total)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    data_dir: Path
    audit_db: Path
    policy: PolicyConfigModel = PolicyConfigModel()
    gateway: GatewayConfigModel = GatewayConfigModel()
    ingest: IngestConfigModel = IngestConfigModel()
    orchestrator: OrchestratorConfigModel = OrchestratorConfigModel()
    agents: list[AgentConfigModel] = []


@dataclass(frozen=True, slots=True)
class OrchestratorSettings:
    """Config del orquestador usada por bootstrap sin ampliar el dominio protegido."""

    mode: Literal["deterministic", "llm"] = "deterministic"
    tier: str = "economico"
    budget_usd: float | None = None


@dataclass(frozen=True, slots=True)
class WyssSettings(DomainWyssSettings):
    """WyssSettings extendido por bootstrap; sigue siendo instancia del tipo de dominio."""

    orchestrator: OrchestratorSettings = field(default_factory=OrchestratorSettings)


def _to_deny_rule(model: DenyRuleModel) -> DenyRule:
    """Mapea un DenyRuleModel de config al DenyRule de dominio (Pydantic muere acá)."""
    targets: tuple[str, ...] = () if model.match_target is None else (model.match_target,)
    return DenyRule(
        id=model.id,
        description=model.description,
        action_type=model.match_action,
        target_patterns=targets,
    )


def _gateway_env_values() -> tuple[str, ...]:
    """Valores reales del .env que el gateway conoce (D-21), leídos de os.environ al boot.

    Solo los VALORES (para el bloqueo por substring del minimizer); los nombres viven en
    `_GATEWAY_ENV_KEYS`. Un valor ausente se omite — no se inventa ni se loguea (V2/V7).
    """
    return tuple(
        value for key in _GATEWAY_ENV_KEYS if (value := os.environ.get(key))
    )


def _derive_agent_budgets(
    explicit: dict[str, float],
    agents: list[AgentConfigModel],
    orchestrator: OrchestratorConfigModel,
) -> dict[str, float]:
    """Cierra RESEARCH Pitfall 1: deriva el tope del gate desde `[[agents]].budget_usd`.

    El gate (`CostTracker.authorize`) solo lee `agent_budgets[agent_id]`; `[[agents]].budget_usd`
    era informativo y dejaba el tope sin cablear (footgun para todo agente futuro). Acá cada
    entrada `[[agents]]` con `budget_usd > 0` puebla `agent_budgets[agent_id]` SI NO fue seteado
    explícitamente en `[gateway.agent_budgets]`.

    Precedencia (decisión de diseño, Open Question 2 / Opción b): el valor explícito de
    `[gateway.agent_budgets]` GANA sobre el derivado de `[[agents]].budget_usd` — sin override
    silencioso. `budget_usd == 0.0` (default) no deriva nada (0 = "sin tope por-agente").
    """
    derived = dict(explicit)
    for agent in agents:
        if agent.budget_usd > 0.0 and agent.agent_id not in derived:
            derived[agent.agent_id] = agent.budget_usd
    if orchestrator.budget_usd is not None and "orchestrator" not in derived:
        derived["orchestrator"] = orchestrator.budget_usd
    return derived


def _to_gateway_settings(
    model: GatewayConfigModel,
    agents: list[AgentConfigModel],
    orchestrator: OrchestratorConfigModel,
) -> GatewaySettings:
    """Mapea la sección [gateway] Pydantic → GatewaySettings frozen (Pydantic muere acá).

    Los regex de secret_patterns se compilan/validan acá: un regex inválido → ConfigError
    legible al boot (fail-fast). Los patrones son ADITIVOS — el GatewaySettings lleva SOLO los
    de config; el merge con `BUILTIN_SECRET_PATTERNS` lo hace el minimizer en runtime (D-21).

    `agent_budgets` se deriva de `[[agents]].budget_usd` (Pitfall 1) y de
    `[orchestrator].budget_usd` con `_derive_agent_budgets`; el valor explícito de
    `[gateway.agent_budgets]` tiene precedencia.
    """
    for tier_name, tier in model.tiers.items():
        if tier.provider not in _KNOWN_PROVIDERS:
            raise ConfigError(
                f"provider desconocido '{tier.provider}' en [gateway.tiers.{tier_name}]; "
                f"válidos: {', '.join(sorted(_KNOWN_PROVIDERS))}"
            )
    config_patterns: list[tuple[str, str]] = []
    for sp in model.secret_patterns:
        try:
            re.compile(sp.regex)
        except re.error as e:
            raise ConfigError(
                f"regex inválido en [gateway.secret_patterns] '{sp.name}': {e}"
            ) from e
        config_patterns.append((sp.name, sp.regex))
    return GatewaySettings(
        tiers={
            name: TierConfig(
                provider=t.provider, model_alias=t.model_alias, max_tokens=t.max_tokens
            )
            for name, t in model.tiers.items()
        },
        prices=dict(model.prices),
        global_budget=model.global_budget,
        agent_budgets=_derive_agent_budgets(
            dict(model.agent_budgets),
            agents,
            orchestrator,
        ),
        timeout_s=model.timeout_s,
        trace_retention_days=model.trace_retention_days,
        env_values=_gateway_env_values(),
        config_patterns=tuple(config_patterns),
    )


def _to_ingest_settings(model: IngestConfigModel) -> IngestSettings:
    """Mapea la sección [ingest] Pydantic → IngestSettings frozen (Pydantic muere acá).

    Las listas Pydantic se convierten a tuplas porque IngestSettings es frozen (no puede tener
    listas mutables). Espejo de `_to_gateway_settings`.
    """
    return IngestSettings(
        chunk_size_tokens=model.chunk_size_tokens,
        chunk_overlap_tokens=model.chunk_overlap_tokens,
        max_file_bytes=model.max_file_bytes,
        dir_denylist=tuple(model.dir_denylist),
        entropy_allowlist=tuple(model.entropy_allowlist),
        default_kb_id=model.default_kb_id,
        max_attempts=model.max_attempts,
    )


def _to_agent_definition(model: AgentConfigModel) -> AgentDefinition:
    """Mapea una entrada [[agents]] Pydantic → AgentDefinition frozen (Pydantic muere acá)."""
    return AgentDefinition(
        agent_id=model.agent_id,
        name=model.name,
        domain=model.domain,
        kb_ids=frozenset(model.knowledge_bases),
        model_alias=model.model_tier,
        budget_usd=model.budget_usd,
    )


def _to_orchestrator_settings(model: OrchestratorConfigModel) -> OrchestratorSettings:
    """Mapea [orchestrator] Pydantic → OrchestratorSettings frozen."""
    return OrchestratorSettings(
        mode=model.mode,
        tier=model.tier,
        budget_usd=model.budget_usd,
    )


def _to_settings(model: WyssConfigModel) -> WyssSettings:
    """Construye el WyssSettings de dominio desde el modelo Pydantic validado.

    `deny` es estrictamente aditivo: `BUILTIN_DENY` + las reglas de config (regla #2).
    """
    config_deny = tuple(_to_deny_rule(rule) for rule in model.policy.deny)
    thresholds = AggregateThresholds(
        file_count_b=model.policy.file_count_b,
        file_count_c=model.policy.file_count_c,
        dir_count_c=model.policy.dir_count_c,
        delete_count_d=model.policy.delete_count_d,
        sensitive_dirs=tuple(model.policy.sensitive_dirs)
        if model.policy.sensitive_dirs
        else AggregateThresholds().sensitive_dirs,
    )
    policy = PolicyRules(
        deny=BUILTIN_DENY + config_deny,
        base_levels=dict(_BASE_LEVELS),
        thresholds=thresholds,
    )
    return WyssSettings(
        data_dir=model.data_dir,
        audit_db=model.audit_db,
        policy=policy,
        gateway=_to_gateway_settings(model.gateway, model.agents, model.orchestrator),
        ingest=_to_ingest_settings(model.ingest),
        orchestrator=_to_orchestrator_settings(model.orchestrator),
        agents=tuple(_to_agent_definition(agent) for agent in model.agents),
    )


def load_settings(path: Path) -> WyssSettings:
    """Carga, valida y convierte `config.toml` a `WyssSettings`. Fail-fast con mensaje legible.

    Levanta `ConfigError` (dominio) ante: archivo inexistente, TOML mal formado, o un
    modelo Pydantic inválido (typo, tipo incorrecto, clave extra). El mensaje nombra el
    path y, para validación, el campo (loc) de cada error.
    """
    _load_dotenv(path.with_name(".env"))

    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"no existe el archivo de configuración: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"TOML inválido en {path}: {e}") from e

    try:
        model = WyssConfigModel.model_validate(raw)
    except ValidationError as e:
        lines = [
            f"  {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()
        ]
        raise ConfigError(
            f"configuración inválida en {path}:\n" + "\n".join(lines)
        ) from e

    return _to_settings(model)


class TomlConfigStore:
    """Adapter que envuelve `load_settings` para cumplir el Protocol `ConfigStore` (D-10)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> WyssSettings:
        """Carga la configuración validada como vocabulario de dominio."""
        return load_settings(self._path)
