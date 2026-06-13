"""Fixtures de la suite orchestrator (Fase 05).

`engine` replica el fixture de tests/policy/conftest.py (BUILTIN_DENY + DEFAULT_BASE_LEVELS
+ AggregateThresholds()) para los tests que gatean acciones por política. Los fixtures
`fake_orchestrator`, `pending_store` y `daemon_client` son placeholders marcados skip hasta
que las clases reales existan (Planes 05-02..05-05): el archivo existe desde Wave 0
(Nyquist: no MISSING), pero solo se activan cuando hay implementación que verificar.
"""

import pytest

from core.domain.policy import AggregateThresholds, PolicyRules
from core.domain.risk import RiskLevel
from core.policy import BUILTIN_DENY, CognitivePolicyEngine

DEFAULT_BASE_LEVELS: dict[str, RiskLevel] = {
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
            base_levels=DEFAULT_BASE_LEVELS,
            thresholds=AggregateThresholds(),
        )
    )


@pytest.fixture
def fake_orchestrator() -> object:
    """Placeholder: FakeOrchestrator determinístico (OrchestratorPort) — Plan 05-04."""
    pytest.skip("Wave 2: 05-04 implementa FakeOrchestrator")


@pytest.fixture
def pending_store(tmp_path: object) -> object:
    """Placeholder: PendingStore SQLite sobre tmp_path (ext4) — Plan 05-03."""
    pytest.skip("Wave 1: 05-03 implementa PendingStore")


@pytest.fixture
def daemon_client() -> object:
    """Placeholder: cliente del daemon sobre Unix socket JSON-RPC — Plan 05-04."""
    pytest.skip("Wave 2: 05-04 implementa el daemon")
