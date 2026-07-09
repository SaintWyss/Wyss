"""Fixtures para la suite de policy: engine con defaults docs/13 y engine sin config.

`DEFAULT_BASE_LEVELS` reproduce la tabla de docs/13 §2 (lecturas → A, mover/renombrar → B,
crear/escribir/borrar/instalar → C). `engine_sin_config` construye el engine con
`base_levels` vacío para probar el Pitfall 3 de RESEARCH: aun sin reglas de config, la
denylist built-in sigue clasificando D los golden plans de denylist.
"""

import pytest

from core.domain.policy import AggregateThresholds, PolicyRules
from core.domain.risk import RiskLevel
from core.policy import BUILTIN_DENY, CognitivePolicyEngine

DEFAULT_BASE_LEVELS: dict[str, RiskLevel] = {
    "file.read": RiskLevel.A,
    "file.list": RiskLevel.A,
    "file.stat": RiskLevel.A,
    "git.status": RiskLevel.A,
    "git.log": RiskLevel.A,
    "git.diff": RiskLevel.A,
    "file.move": RiskLevel.B,
    "file.rename": RiskLevel.B,
    "file.create": RiskLevel.C,
    "file.write": RiskLevel.C,
    "file.delete": RiskLevel.C,
    "shell.run": RiskLevel.C,
    "git.push": RiskLevel.C,
}


@pytest.fixture
def engine() -> CognitivePolicyEngine:
    return CognitivePolicyEngine(
        PolicyRules(
            deny=BUILTIN_DENY,
            base_levels=DEFAULT_BASE_LEVELS,
            thresholds=AggregateThresholds(),
        )
    )


@pytest.fixture
def engine_sin_config() -> CognitivePolicyEngine:
    """Engine con base_levels vacío: la denylist built-in debe seguir clasificando D."""
    return CognitivePolicyEngine(
        PolicyRules(deny=BUILTIN_DENY, base_levels={}, thresholds=AggregateThresholds())
    )
