"""Composition root (DI manual) + frontera Pydantic→dominio (D-02, D-10).

Pydantic vive SOLO en este paquete (`bootstrap.config`): lee y valida `config.toml` al
boot y produce el frozen dataclass `WyssSettings`. El núcleo nunca importa Pydantic
(import-linter lo garantiza). `TomlConfigStore` envuelve `load_settings` para cumplir el
Protocol `ConfigStore` cuando se inyecta por puerto.
"""

from bootstrap.config import TomlConfigStore, load_settings

__all__ = ["TomlConfigStore", "load_settings"]
