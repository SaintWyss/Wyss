"""Reglas de política y decisión: DenyRule, AggregateThresholds, PolicyRules, PolicyDecision."""

from collections.abc import Mapping
from dataclasses import dataclass, field

from core.domain.risk import Outcome, RiskLevel

# Directorios sensibles default (RESEARCH §3.2) — escribir bajo ellos escala el nivel.
DEFAULT_SENSITIVE_DIRS: tuple[str, ...] = (
    "~/.ssh",
    "/etc",
    "/boot",
    "**/.env*",
    "**/*.key",
    "**/id_rsa*",
)


@dataclass(frozen=True, slots=True)
class DenyRule:
    """Una regla de denylist (nivel D incondicional al matchear).

    `action_type` y `target_patterns` son patterns fnmatch; `params_equal` matchea
    igualdad de parámetros (ej. `{"recursive": True, "to_trash": False}`). Una tupla
    vacía de `target_patterns` matchea cualquier target.
    """

    id: str
    description: str
    action_type: str
    target_patterns: tuple[str, ...] = ()
    params_equal: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AggregateThresholds:
    """Umbrales de agregación anti-bypass (POL-05) — configurables por TOML."""

    file_count_b: int = 10
    file_count_c: int = 100
    dir_count_c: int = 5
    delete_count_d: int = 50
    sensitive_dirs: tuple[str, ...] = DEFAULT_SENSITIVE_DIRS


@dataclass(frozen=True, slots=True)
class PolicyRules:
    """Las reglas que evalúa el engine. `deny` = BUILTIN_DENY + reglas de config (solo aditivas)."""

    deny: tuple[DenyRule, ...]
    base_levels: Mapping[str, RiskLevel]
    unknown_action_level: RiskLevel = RiskLevel.C
    thresholds: AggregateThresholds = field(default_factory=AggregateThresholds)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Resultado de evaluar un plan. Toda decisión, incluida REJECT, se audita."""

    task_id: str
    risk_level: RiskLevel
    outcome: Outcome
    matched_rules: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
