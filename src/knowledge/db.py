"""Apertura de index.db: permisos restrictivos + WAL fail-fast + esquema.

Replica el patrón de `gateway/db.py` sin importar de gateway para mantener la independencia de
capas. Cualquier consumidor de la DB de conocimiento debe pasar por `open_index_db`: crea el
archivo con 0600, verifica que WAL quedó activo y aplica el DDL idempotente.
"""

import logging
import os
import sqlite3
from pathlib import Path

from core.domain.errors import IndexIntegrityError
from knowledge.index_schema import PRAGMAS, apply_index_schema

_log = logging.getLogger(__name__)


def open_index_db(db_path: Path) -> sqlite3.Connection:
    """Abre index.db con permisos 0600, WAL verificado fail-fast y esquema aplicado."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Pre-crear con 0600 antes del connect evita una ventana umask 0644 -> chmod.
    fd = os.open(db_path, os.O_CREAT, 0o600)
    os.close(fd)
    conn = sqlite3.connect(db_path)
    try:
        # Corrige permisos si el archivo ya existía con otro modo. En FS sin modos POSIX
        # puede fallar; se loguea, pero no se oculta el evento.
        os.chmod(db_path, 0o600)
    except OSError as exc:
        _log.warning("no se pudo aplicar 0600 a %s: %s", db_path, exc)
    journal_mode: str | None = None
    for pragma in PRAGMAS:
        row = conn.execute(pragma).fetchone()
        if pragma.endswith("WAL") and row is not None:
            journal_mode = str(row[0]).lower()
    if journal_mode != "wal":
        conn.close()
        raise IndexIntegrityError(
            f"index db en {db_path}: PRAGMA journal_mode retornó "
            f"{journal_mode!r}, se esperaba 'wal'. WAL no está disponible sobre "
            "este filesystem (probablemente NTFS/fuseblk). Mové data/ a un "
            "filesystem ext4 para garantizar durabilidad del índice."
        )
    apply_index_schema(conn)
    return conn
