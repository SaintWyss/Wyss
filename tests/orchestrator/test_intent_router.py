"""Stubs del IntentRouter (ORCH-03/04) — Planes 05-02 (modelo) y 05-05 (router) implementan.

Scaffolding Wave 0. `test_nueve_categorias` verifica las ≥9 categorías de intención
(ORCH-03); `test_ambiguous` verifica que lo ambiguo cae en clarification (ORCH-04, D-60).
"""

import pytest


@pytest.mark.skip(reason="Wave 1: 05-02 define el modelo de ≥9 categorías de intención (ORCH-03)")
def test_nueve_categorias() -> None:
    """ORCH-03: el modelo de intención cubre ≥9 categorías distintas."""
    raise NotImplementedError


@pytest.mark.skip(reason="Wave 3: 05-05 implementa IntentRouter (ORCH-04 ambiguo→clarification)")
def test_ambiguous() -> None:
    """ORCH-04: input ambiguo enruta a clarification, no a una acción (D-60)."""
    raise NotImplementedError
