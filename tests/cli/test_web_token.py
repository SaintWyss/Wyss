"""Token del bridge web persistente entre reinicios (data/web_token).

Antes se regeneraba en cada `wyss web` y cada reinicio invalidaba la cookie
del teléfono (re-pairing forzado).
"""

import stat
from pathlib import Path

from bootstrap.cli import _load_or_create_intake_token, _load_or_create_web_token


def test_token_estable_entre_reinicios(tmp_path: Path) -> None:
    primero = _load_or_create_web_token(tmp_path)
    segundo = _load_or_create_web_token(tmp_path)

    assert primero == segundo
    assert len(primero) >= 32


def test_token_archivo_solo_owner(tmp_path: Path) -> None:
    _load_or_create_web_token(tmp_path)

    mode = stat.S_IMODE((tmp_path / "web_token").stat().st_mode)
    assert mode == 0o600


def test_token_corrupto_se_regenera(tmp_path: Path) -> None:
    """Archivo demasiado corto (truncado/corrupto) no se acepta como token."""
    (tmp_path / "web_token").write_text("corto", encoding="utf-8")

    token = _load_or_create_web_token(tmp_path)

    assert token != "corto"
    assert len(token) >= 32
    # y quedó persistido: la próxima carga devuelve el mismo
    assert _load_or_create_web_token(tmp_path) == token


def test_intake_token_estable_entre_reinicios(tmp_path: Path) -> None:
    primero = _load_or_create_intake_token(tmp_path)
    segundo = _load_or_create_intake_token(tmp_path)

    assert primero == segundo
    assert len(primero) >= 32


def test_intake_token_archivo_solo_owner(tmp_path: Path) -> None:
    _load_or_create_intake_token(tmp_path)

    mode = stat.S_IMODE((tmp_path / "intake_token").stat().st_mode)
    assert mode == 0o600


def test_intake_token_corrupto_se_regenera(tmp_path: Path) -> None:
    """Archivo demasiado corto (truncado/corrupto) no se acepta como token."""
    (tmp_path / "intake_token").write_text("corto", encoding="utf-8")

    token = _load_or_create_intake_token(tmp_path)

    assert token != "corto"
    assert len(token) >= 32
    assert _load_or_create_intake_token(tmp_path) == token
