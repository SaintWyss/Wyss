"""Fixtures de los tests del bootstrap de configuración."""

from collections.abc import Callable
from pathlib import Path

import pytest

# TOML válido de referencia (basado en config/config.example.toml, sin la deny comentada).
_VALID_TOML = """\
data_dir = "data"
audit_db = "data/audit.db"

[policy]
file_count_b = 10
file_count_c = 100
dir_count_c = 5
delete_count_d = 50
sensitive_dirs = ["~/.ssh", "/etc", "data"]
"""


@pytest.fixture
def valid_config(tmp_path: Path) -> Path:
    """Escribe un config.toml válido en tmp_path y retorna su path."""
    path = tmp_path / "config.toml"
    path.write_text(_VALID_TOML, encoding="utf-8")
    return path


@pytest.fixture
def write_config(tmp_path: Path) -> Callable[[str], Path]:
    """Factory: escribe contenido TOML arbitrario en tmp_path y retorna su path."""

    def _write(content: str) -> Path:
        path = tmp_path / "config.toml"
        path.write_text(content, encoding="utf-8")
        return path

    return _write
