"""Gate dorado anti-falso-A para Planes derivados de NL (POL-06 / D-63) — Plan 05-02 puebla.

Réplica del contrato del gate dorado de embeddings (hit@1=20/20) pero sobre la cadena
NL→intención→Plan: ≥20 instrucciones en lenguaje natural con su nivel de riesgo esperado.
Un **FALSO-A** — clasificar A (ejecutar sin confirmar) algo que debía ser B/C/D — es el
peor fallo posible del sistema. Cada caso destructivo lleva el literal
`" — FALSO-A CATASTROFICO"` en su nombre para que un fallo del gate sea inconfundible en CI.

Scaffolding Wave 0: la estructura existe y se recolecta; los ≥20 fixtures se pueblan en
Plan 05-02 (necesita el modelo de intención + IntentRouter). Marcado skip hasta entonces.
"""

from dataclasses import dataclass

import pytest

from core.domain.risk import RiskLevel


@dataclass(frozen=True)
class NLGolden:
    """Caso dorado NL→Plan: instrucción en lenguaje natural + nivel de riesgo esperado."""

    name: str
    instruction: str
    expected: RiskLevel


# Poblado en Plan 05-02 con ≥20 casos cubriendo A/B/C/D. Cada caso destructivo (C/D)
# debe incluir el literal " — FALSO-A CATASTROFICO" en `name`.
NL_GOLDEN_CASES: tuple[NLGolden, ...] = ()


@pytest.mark.skip(reason="Wave 1: 05-02 puebla los ≥20 fixtures NL del gate POL-06/D-63")
@pytest.mark.parametrize(
    "case",
    NL_GOLDEN_CASES,
    ids=lambda c: c.name if isinstance(c, NLGolden) else str(c),
)
def test_nl_golden_plan_level(case: NLGolden) -> None:
    """POL-06: cada instrucción NL produce un Plan con el nivel esperado; cero FALSO-A.

    Un caso destructivo clasificado A (` — FALSO-A CATASTROFICO`) hace fallar el gate.
    """
    raise NotImplementedError


def test_nl_golden_gate_scaffold_present() -> None:
    """Wave 0: el scaffold del gate existe y es importable (Nyquist: no MISSING)."""
    assert NLGolden.__dataclass_fields__.keys() == {"name", "instruction", "expected"}
    assert isinstance(NL_GOLDEN_CASES, tuple)
