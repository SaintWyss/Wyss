"""WyssSettings — destino frozen de la validación Pydantic del plan 01-05.

Pydantic NO entra acá: bootstrap convierte el modelo validado a este dataclass de dominio.
"""

from dataclasses import dataclass
from pathlib import Path

from core.domain.policy import PolicyRules


@dataclass(frozen=True, slots=True)
class WyssSettings:
    """Configuración del sistema ya validada, como vocabulario de dominio."""

    data_dir: Path
    audit_db: Path
    policy: PolicyRules
