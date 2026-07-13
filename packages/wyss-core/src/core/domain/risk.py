"""Niveles de riesgo y outcomes de la política cognitiva (POL-02, POL-04, D-03)."""

from enum import IntEnum
from typing import assert_never


class RiskLevel(IntEnum):
    """Orden total: A < B < C < D. max() implementa 'subir sí, bajar jamás' (POL-04)."""

    A = 1
    B = 2
    C = 3
    D = 4


class Outcome(IntEnum):
    """Paso siguiente que dicta el nivel de riesgo (semántica D-03)."""

    EXECUTE = 1
    CONFIRM_SIMPLE = 2
    CONFIRM_STRONG = 3
    REJECT = 4


def outcome_for(level: RiskLevel) -> Outcome:
    """Mapea cada nivel a su outcome. `assert_never` hace que mypy detecte variantes nuevas."""
    match level:
        case RiskLevel.A:
            return Outcome.EXECUTE
        case RiskLevel.B:
            return Outcome.CONFIRM_SIMPLE
        case RiskLevel.C:
            return Outcome.CONFIRM_STRONG
        case RiskLevel.D:
            return Outcome.REJECT
    assert_never(level)
