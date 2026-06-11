"""Frontera Pydantic→dominio: carga y valida `config.toml` al boot (D-09, D-10).

Este módulo es el ÚNICO lugar donde vive Pydantic. Lee el TOML con `tomllib`, lo valida
con un modelo Pydantic v2 (`extra="forbid"`, fail-closed ante typos/claves extra), y
produce el frozen dataclass `WyssSettings` de `core.domain` — Pydantic muere acá, el
núcleo nunca ve un `BaseModel` (import-linter lo garantiza).

Invariante estructural (regla #2): las reglas `[[policy.deny]]` de config solo AGREGAN a
`BUILTIN_DENY` (`PolicyRules.deny = BUILTIN_DENY + tuple(config_deny)`); no hay ruta para
vaciar la denylist built-in editando un archivo.

Decisión de diseño: ante config inexistente, TOML mal formado o validación fallida se
levanta `ConfigError` (excepción de dominio) con un mensaje legible que nombra el path y,
para errores de validación, el campo (loc). El `sys.exit` se deja al caller CLI de Fase 5,
de modo que el comportamiento sea testeable con `pytest.raises` sin matar el proceso.
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from core.domain.config import WyssSettings
from core.domain.errors import ConfigError
from core.domain.policy import AggregateThresholds, DenyRule, PolicyRules
from core.domain.risk import RiskLevel
from core.policy.builtin_deny import BUILTIN_DENY

# Niveles base por action_type (docs/13). Fail-closed: lo desconocido lo resuelve el engine a C.
_BASE_LEVELS: dict[str, RiskLevel] = {
    "file.read": RiskLevel.A,
    "file.list": RiskLevel.A,
    "file.move": RiskLevel.B,
    "file.rename": RiskLevel.B,
    "file.create": RiskLevel.C,
    "file.write": RiskLevel.C,
    "file.delete": RiskLevel.C,
    "shell.run": RiskLevel.C,
}


class DenyRuleModel(BaseModel):
    """Una regla de denylist adicional desde config. `extra="forbid"` → typo = boot abortado."""

    model_config = ConfigDict(extra="forbid")

    id: str
    match_action: str
    match_target: str | None = None
    description: str = "Regla de denegación definida por el owner en config."


class PolicyConfigModel(BaseModel):
    """Sección [policy]: umbrales de agregación + denylist aditiva. `extra="forbid"` fail-closed."""

    model_config = ConfigDict(extra="forbid")

    file_count_b: int = 10
    file_count_c: int = 100
    dir_count_c: int = 5
    delete_count_d: int = 50
    sensitive_dirs: list[str] = []
    deny: list[DenyRuleModel] = []


class WyssConfigModel(BaseModel):
    """Raíz del config.toml validado. `frozen=True` + `extra="forbid"` (fail-closed total)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    data_dir: Path
    audit_db: Path
    policy: PolicyConfigModel = PolicyConfigModel()


def _to_deny_rule(model: DenyRuleModel) -> DenyRule:
    """Mapea un DenyRuleModel de config al DenyRule de dominio (Pydantic muere acá)."""
    targets: tuple[str, ...] = () if model.match_target is None else (model.match_target,)
    return DenyRule(
        id=model.id,
        description=model.description,
        action_type=model.match_action,
        target_patterns=targets,
    )


def _to_settings(model: WyssConfigModel) -> WyssSettings:
    """Construye el WyssSettings de dominio desde el modelo Pydantic validado.

    `deny` es estrictamente aditivo: `BUILTIN_DENY` + las reglas de config (regla #2).
    """
    config_deny = tuple(_to_deny_rule(rule) for rule in model.policy.deny)
    thresholds = AggregateThresholds(
        file_count_b=model.policy.file_count_b,
        file_count_c=model.policy.file_count_c,
        dir_count_c=model.policy.dir_count_c,
        delete_count_d=model.policy.delete_count_d,
        sensitive_dirs=tuple(model.policy.sensitive_dirs)
        if model.policy.sensitive_dirs
        else AggregateThresholds().sensitive_dirs,
    )
    policy = PolicyRules(
        deny=BUILTIN_DENY + config_deny,
        base_levels=dict(_BASE_LEVELS),
        thresholds=thresholds,
    )
    return WyssSettings(data_dir=model.data_dir, audit_db=model.audit_db, policy=policy)


def load_settings(path: Path) -> WyssSettings:
    """Carga, valida y convierte `config.toml` a `WyssSettings`. Fail-fast con mensaje legible.

    Levanta `ConfigError` (dominio) ante: archivo inexistente, TOML mal formado, o un
    modelo Pydantic inválido (typo, tipo incorrecto, clave extra). El mensaje nombra el
    path y, para validación, el campo (loc) de cada error.
    """
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"no existe el archivo de configuración: {path}") from e
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"TOML inválido en {path}: {e}") from e

    try:
        model = WyssConfigModel.model_validate(raw)
    except ValidationError as e:
        lines = [
            f"  {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()
        ]
        raise ConfigError(
            f"configuración inválida en {path}:\n" + "\n".join(lines)
        ) from e

    return _to_settings(model)


class TomlConfigStore:
    """Adapter que envuelve `load_settings` para cumplir el Protocol `ConfigStore` (D-10)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> WyssSettings:
        """Carga la configuración validada como vocabulario de dominio."""
        return load_settings(self._path)
