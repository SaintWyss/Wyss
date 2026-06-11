"""Tests del bootstrap de config: carga válida, fail-fast legible y denylist aditiva.

Cubre la frontera Pydantic→dominio (D-09): el WyssSettings retornado es un dataclass de
dominio (no un BaseModel), config inválida falla cerrado con mensaje legible (no traceback
crudo), y las reglas [[policy.deny]] de config solo AGREGAN a BUILTIN_DENY (regla #2).
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import BaseModel

from bootstrap.config import load_settings
from core.domain.config import WyssSettings
from core.domain.errors import ConfigError
from core.policy.builtin_deny import BUILTIN_DENY


def test_loads_valid_config(valid_config: Path) -> None:
    """Un config válido produce un WyssSettings con Paths y thresholds del TOML."""
    settings = load_settings(valid_config)

    assert isinstance(settings, WyssSettings)
    assert settings.data_dir == Path("data")
    assert settings.audit_db == Path("data/audit.db")
    assert settings.policy.thresholds.file_count_b == 10
    assert settings.policy.thresholds.file_count_c == 100
    assert settings.policy.thresholds.dir_count_c == 5
    assert settings.policy.thresholds.delete_count_d == 50
    assert settings.policy.thresholds.sensitive_dirs == ("~/.ssh", "/etc", "data")


def test_config_not_found(tmp_path: Path) -> None:
    """Un path inexistente levanta ConfigError con el path en el mensaje (no FileNotFoundError)."""
    missing = tmp_path / "no-existe.toml"
    with pytest.raises(ConfigError, match=str(missing)):
        load_settings(missing)


def test_malformed_toml(write_config: Callable[[str], Path]) -> None:
    """Un TOML mal formado levanta ConfigError legible, no un TOMLDecodeError crudo."""
    path = write_config("data_dir = \nesto no es toml válido [[[")
    with pytest.raises(ConfigError, match="TOML inválido"):
        load_settings(path)


def test_extra_key_top_level_rejected(write_config: Callable[[str], Path]) -> None:
    """Una clave extra desconocida a nivel raíz falla (extra=forbid) nombrando el campo."""
    path = write_config(
        'data_dir = "data"\naudit_db = "data/audit.db"\nclave_desconocida = "x"\n'
    )
    with pytest.raises(ConfigError, match="clave_desconocida"):
        load_settings(path)


def test_extra_key_in_policy_rejected(write_config: Callable[[str], Path]) -> None:
    """Una clave extra desconocida bajo [policy] falla nombrando el campo (loc)."""
    path = write_config(
        'data_dir = "data"\naudit_db = "data/audit.db"\n'
        "[policy]\nfile_count_b = 10\ntypo_threshold = 99\n"
    )
    with pytest.raises(ConfigError, match="typo_threshold"):
        load_settings(path)


def test_invalid_type(write_config: Callable[[str], Path]) -> None:
    """Un tipo incorrecto (string donde va int) falla con mensaje legible que nombra el campo."""
    path = write_config(
        'data_dir = "data"\naudit_db = "data/audit.db"\n'
        '[policy]\nfile_count_b = "diez"\n'
    )
    with pytest.raises(ConfigError, match="file_count_b"):
        load_settings(path)


def test_denylist_is_additive(write_config: Callable[[str], Path]) -> None:
    """Un [[policy.deny]] propio AGREGA a BUILTIN_DENY; los built-in nunca se remueven."""
    path = write_config(
        'data_dir = "data"\naudit_db = "data/audit.db"\n'
        "[[policy.deny]]\n"
        'id = "no-tocar-proyectos"\n'
        'match_action = "file.delete"\n'
        'match_target = "~/Data/10_Workspace/projects/**"\n'
    )
    settings = load_settings(path)

    assert len(settings.policy.deny) == len(BUILTIN_DENY) + 1
    builtin_ids = {rule.id for rule in BUILTIN_DENY}
    result_ids = {rule.id for rule in settings.policy.deny}
    assert builtin_ids <= result_ids  # todos los built-in persisten
    assert "no-tocar-proyectos" in result_ids


def test_deny_rule_extra_key_rejected(write_config: Callable[[str], Path]) -> None:
    """Un typo dentro de una [[policy.deny]] aborta el boot (T-01-06-T fail-closed)."""
    path = write_config(
        'data_dir = "data"\naudit_db = "data/audit.db"\n'
        "[[policy.deny]]\n"
        'id = "x"\n'
        'match_action = "file.delete"\n'
        'match_targ = "typo"\n'  # typo: debería ser match_target
    )
    with pytest.raises(ConfigError, match="match_targ"):
        load_settings(path)


def test_no_pydantic_in_settings(valid_config: Path) -> None:
    """El WyssSettings retornado y su policy son dataclasses de dominio, no BaseModel."""
    settings = load_settings(valid_config)

    assert not isinstance(settings, BaseModel)
    assert not isinstance(settings.policy, BaseModel)
    assert type(settings).__name__ == "WyssSettings"
