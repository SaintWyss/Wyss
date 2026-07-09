"""Fixture del engine con la denylist real (BUILTIN_DENY + base_levels de docs/13).

Réplica del fixture de tests/policy/conftest.py: la suite de seguridad monta el mismo
engine que producción arma en bootstrap, para que la clasificación de riesgo probada
acá sea la que corre de verdad.
"""

import pytest

from core.domain.policy import AggregateThresholds, PolicyRules
from core.domain.risk import RiskLevel
from core.policy import BUILTIN_DENY, CognitivePolicyEngine

_BASE_LEVELS: dict[str, RiskLevel] = {
    "file.read": RiskLevel.A,
    "file.list": RiskLevel.A,
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
            base_levels=_BASE_LEVELS,
            thresholds=AggregateThresholds(),
        )
    )
