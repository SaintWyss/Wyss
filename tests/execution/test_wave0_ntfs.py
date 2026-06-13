"""Wave 0 — empirical NTFS environment pins.

Estos dos tests corren únicamente sobre el mount NTFS/fuseblk real (`/mnt/hdd`) cuando
`WYSS_TEST_NTFS=1`. En CI sin esa variable, se saltan.

Test A: send2trash mueve un archivo al trash FreeDesktop en el volumen NTFS
        (el archivo aterriza en /mnt/hdd/.Trash-1000/files/, con .trashinfo en /info/).
Test B: SQLite acepta PRAGMA journal_mode=WAL sobre /mnt/hdd (necesario para el journal
        de undo — D-65).

Pitfall RESEARCH #2 (NO usar /tmp): send2trash lanza TrashPermissionError en /tmp porque
el sticky-bit impide construir el .Trash-$UID del usuario. Por eso los archivos temporales
se crean bajo <repo_root>/data/ (en /mnt/hdd, misma partición).
"""

import os
import sqlite3
from pathlib import Path

import pytest
from send2trash import send2trash  # type: ignore[import-untyped]

_NTFS_SKIP = pytest.mark.skipif(
    os.environ.get("WYSS_TEST_NTFS") != "1",
    reason="requiere WYSS_TEST_NTFS=1 (corre sobre el mount NTFS/fuseblk real)",
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _REPO_ROOT / "data"
_TRASH_FILES = Path("/mnt/hdd/.Trash-1000/files")


@pytest.mark.ntfs
@_NTFS_SKIP
def test_send2trash_lands_in_ntfs_trash() -> None:
    """send2trash mueve un archivo de data/ al trash NTFS — verifica presencia en .Trash-1000."""
    sentinel = _DATA_DIR / "wave0_ntfs_sentinel.txt"
    sentinel.write_text("wyss-wave0-test", encoding="utf-8")
    assert sentinel.exists(), "El archivo centinela debe existir antes de send2trash"

    trash_entry: Path | None = None
    try:
        send2trash(str(sentinel))

        # El archivo original ya no debe existir
        assert not sentinel.exists(), "send2trash debería haber eliminado el archivo original"

        # Debe aparecer una entrada en el trash del volumen NTFS
        candidates = list(_TRASH_FILES.glob("wave0_ntfs_sentinel*"))
        assert candidates, (
            f"No se encontró entrada en {_TRASH_FILES}/ tras send2trash; "
            "verificar que el mount NTFS tiene .Trash-1000/files/ accesible"
        )
        trash_entry = candidates[0]
    finally:
        # Limpieza: eliminar el archivo del trash (si llegó) y el .trashinfo
        if trash_entry is not None and trash_entry.exists():
            trash_entry.unlink(missing_ok=True)
        trash_info = Path("/mnt/hdd/.Trash-1000/info") / (
            (trash_entry.name if trash_entry else "wave0_ntfs_sentinel.txt") + ".trashinfo"
        )
        trash_info.unlink(missing_ok=True)
        # Limpieza fallback: si send2trash no movió el archivo (fallo intermedio)
        sentinel.unlink(missing_ok=True)


@pytest.mark.ntfs
@_NTFS_SKIP
def test_sqlite_wal_on_ntfs() -> None:
    """SQLite WAL funciona sobre /mnt/hdd (requisito del journal de undo D-65)."""
    db_path = _DATA_DIR / "wave0_wal_test.db"
    db_path.unlink(missing_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
        assert row is not None, "PRAGMA journal_mode=WAL no devolvió resultado"
        mode = str(row[0]).lower()
        assert mode == "wal", (
            f"Se esperaba journal_mode='wal' pero se obtuvo '{mode}'. "
            "El journal de undo D-65 requiere WAL en /mnt/hdd."
        )
    finally:
        conn.close()
        db_path.unlink(missing_ok=True)
        for sidecar in (
            db_path.with_suffix(".db-wal"),
            db_path.with_suffix(".db-shm"),
        ):
            sidecar.unlink(missing_ok=True)
