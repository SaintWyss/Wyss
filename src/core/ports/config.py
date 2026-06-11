"""Puerto de configuración — retorna el dataclass de dominio, NUNCA el modelo Pydantic."""

from typing import Protocol

from core.domain import WyssSettings


class ConfigStore(Protocol):
    """Carga la configuración validada como vocabulario de dominio."""

    def load(self) -> WyssSettings: ...
