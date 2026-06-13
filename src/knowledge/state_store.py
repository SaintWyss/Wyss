"""StateStore SQLite para ingesta incremental y reanudable.

La tabla `file_state` permite saltar archivos sin cambios por size+mtime sin recalcular hash
(KNOW-02) y retomar corridas tras un kill porque cada transición commitea inmediatamente
(KNOW-03). Todo SQL usa parámetros `?`; los paths son datos, nunca código.
"""

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import cast

from core.domain.knowledge import FileRecord, FileStatus
from knowledge.db import open_index_db

_ERROR_MAX_LEN = 500
_BLOCK_SIZE = 1024 * 1024

_COLUMNS = ("path", "kb_id", "size", "mtime", "sha256", "status", "attempts", "error")


@dataclass(frozen=True, slots=True)
class BcFreshness:
    """Frescura del índice por base de conocimiento."""

    kb_id: str
    last_indexed_at: float | None
    total: int
    embedded: int
    pending: int
    failed: int


class StateStore:
    """Store SQLite del estado por archivo: incremental, reanudable y aislado por kb_id."""

    def __init__(self, db_path: Path, *, max_attempts: int = 3) -> None:
        self._db_path = db_path
        self._conn = open_index_db(db_path)
        self._max_attempts = max_attempts

    @staticmethod
    def compute_sha256(path: Path) -> str:
        """Calcula sha256 leyendo en bloques para no cargar archivos grandes en memoria."""
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(_BLOCK_SIZE), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def needs_reindex(self, path: Path | str, kb_id: str, size: int, mtime: float) -> bool:
        """Decide si un archivo debe reprocesarse con filtro rápido size+mtime -> hash."""
        path_text = self._path_text(path)
        row = cast(
            tuple[object, ...] | None,
            self._conn.execute(
            "SELECT size, mtime, sha256, status FROM file_state WHERE path=? AND kb_id=?",
            (path_text, kb_id),
            ).fetchone(),
        )
        if row is None:
            return True

        stored_size, stored_mtime, stored_sha256, status_text = row
        status = FileStatus(str(status_text))
        if status != FileStatus.embedded:
            return True

        if self._as_int(stored_size) == size and self._as_float(stored_mtime) == mtime:
            return False

        current_sha256 = self.compute_sha256(Path(path_text))
        return (None if stored_sha256 is None else str(stored_sha256)) != current_sha256

    def mark_pending(
        self,
        path: Path | str,
        kb_id: str,
        *,
        size: int | None = None,
        mtime: float | None = None,
        sha256: str | None = None,
    ) -> None:
        """Registra o resetea un archivo como pendiente de procesamiento."""
        self._upsert_state(
            path,
            kb_id,
            status=FileStatus.pending,
            size=size,
            mtime=mtime,
            sha256=sha256,
            attempts=0,
            error=None,
            indexed=False,
        )

    def mark_extracted(
        self,
        path: Path | str,
        kb_id: str,
        *,
        size: int | None = None,
        mtime: float | None = None,
        sha256: str | None = None,
    ) -> None:
        """Marca extracción/FTS completada; queda reanudable para embedding posterior."""
        self._upsert_state(
            path,
            kb_id,
            status=FileStatus.extracted,
            size=size,
            mtime=mtime,
            sha256=sha256,
            error=None,
            indexed=False,
        )

    def mark_embedded(
        self,
        path: Path | str,
        kb_id: str,
        *,
        size: int | None = None,
        mtime: float | None = None,
        sha256: str | None = None,
    ) -> None:
        """Marca embedding completado y guarda sha256 para la comparación incremental."""
        path_obj = Path(path)
        stored_size, stored_mtime = self._metadata_or_existing(path_obj, kb_id, size, mtime)
        stored_sha256 = sha256 if sha256 is not None else self.compute_sha256(path_obj)
        self._upsert_state(
            path_obj,
            kb_id,
            status=FileStatus.embedded,
            size=stored_size,
            mtime=stored_mtime,
            sha256=stored_sha256,
            attempts=0,
            error=None,
            indexed=True,
        )

    def mark_failed(self, path: Path | str, kb_id: str, error: str) -> None:
        """Marca fallo por archivo, incrementando attempts y truncando el mensaje guardado."""
        path_text = self._path_text(path)
        size, mtime = self._metadata_or_existing(Path(path_text), kb_id, None, None)
        truncated = error[:_ERROR_MAX_LEN]
        self._conn.execute(
            """
            INSERT INTO file_state
              (path, kb_id, size, mtime, sha256, status, attempts, error, indexed_at, updated_at)
            VALUES (?, ?, ?, ?, NULL, ?, 1, ?, NULL, unixepoch())
            ON CONFLICT(path, kb_id) DO UPDATE SET
              size=excluded.size,
              mtime=excluded.mtime,
              status=excluded.status,
              attempts=file_state.attempts + 1,
              error=excluded.error,
              indexed_at=NULL,
              updated_at=unixepoch()
            """,
            (path_text, kb_id, size, mtime, FileStatus.failed.value, truncated),
        )
        self._conn.commit()

    def mark_excluded_secret(self, path: Path | str, kb_id: str) -> None:
        """Marca archivo excluido entero por secreto detectado."""
        self._upsert_state(path, kb_id, status=FileStatus.excluded_secret, indexed=False)

    def mark_skipped(self, path: Path | str, kb_id: str, status: FileStatus) -> None:
        """Marca un skip permanente del pipeline."""
        if status not in (
            FileStatus.skipped_unsupported,
            FileStatus.skipped_symlink,
            FileStatus.skipped_size,
        ):
            raise ValueError(f"status no es skipped_*: {status.value}")
        self._upsert_state(path, kb_id, status=status, indexed=False)

    def list_resumable(self, kb_id: str) -> list[FileRecord]:
        """Lista archivos pendientes/reanudables para una BC, aplicando el cap D-39."""
        rows = self._conn.execute(
            f"""
            SELECT {", ".join(_COLUMNS)}
            FROM file_state
            WHERE kb_id=?
              AND (
                status IN (?, ?)
                OR (status=? AND attempts < ?)
              )
            ORDER BY path
            """,
            (
                kb_id,
                FileStatus.pending.value,
                FileStatus.extracted.value,
                FileStatus.failed.value,
                self._max_attempts,
            ),
        ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def counts_by_status(
        self, kb_id: str, paths: Iterable[Path | str] | None = None
    ) -> Mapping[FileStatus, int]:
        """Devuelve contadores por estado para una BC, opcionalmente acotados a paths."""
        if paths is not None:
            path_values = tuple(self._path_text(path) for path in paths)
            if not path_values:
                return {}
            placeholders = ", ".join("?" for _ in path_values)
            rows = self._conn.execute(
                f"""
                SELECT status, COUNT(*)
                FROM file_state
                WHERE kb_id=? AND path IN ({placeholders})
                GROUP BY status
                """,
                (kb_id, *path_values),
            ).fetchall()
            return {FileStatus(str(status)): int(count) for status, count in rows}

        rows = self._conn.execute(
            "SELECT status, COUNT(*) FROM file_state WHERE kb_id=? GROUP BY status",
            (kb_id,),
        ).fetchall()
        return {FileStatus(str(status)): int(count) for status, count in rows}

    def freshness_by_kb(self) -> list[BcFreshness]:
        """Devuelve frescura y contadores de `file_state`, agrupados por BC."""
        rows = self._conn.execute(
            """
            SELECT
              kb_id,
              MAX(indexed_at),
              COUNT(*),
              SUM(CASE WHEN status='embedded' THEN 1 ELSE 0 END),
              SUM(CASE WHEN status IN ('pending','extracted') THEN 1 ELSE 0 END),
              SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END)
            FROM file_state
            GROUP BY kb_id
            ORDER BY kb_id
            """
        ).fetchall()
        return [
            BcFreshness(
                kb_id=str(row[0]),
                last_indexed_at=None if row[1] is None else self._as_float(row[1]),
                total=self._as_int(row[2]),
                embedded=self._as_int(row[3]),
                pending=self._as_int(row[4]),
                failed=self._as_int(row[5]),
            )
            for row in rows
        ]

    def list_kb_ids(self) -> list[str]:
        """Lista BCs distintas presentes en `file_state`, ordenadas por id."""
        rows = self._conn.execute(
            "SELECT DISTINCT kb_id FROM file_state ORDER BY kb_id"
        ).fetchall()
        return [str(row[0]) for row in rows]

    def mtime_by_path(self, source_path: str, kb_id: str) -> float | None:
        """mtime del archivo de origen para enriquecer Hit.date; None si no está indexado."""
        row = cast(
            tuple[object, ...] | None,
            self._conn.execute(
                "SELECT mtime FROM file_state WHERE path = ? AND kb_id = ?",
                (source_path, kb_id),
            ).fetchone(),
        )
        if row is None:
            return None
        return self._as_float(row[0])

    def get(self, path: Path | str, kb_id: str) -> FileRecord | None:
        """Devuelve una fila de `file_state`; helper útil para tests y pipeline."""
        row = cast(
            tuple[object, ...] | None,
            self._conn.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM file_state WHERE path=? AND kb_id=?",
            (self._path_text(path), kb_id),
            ).fetchone(),
        )
        if row is None:
            return None
        return self._row_to_record(row)

    def _upsert_state(
        self,
        path: Path | str,
        kb_id: str,
        *,
        status: FileStatus,
        size: int | None = None,
        mtime: float | None = None,
        sha256: str | None = None,
        attempts: int | None = None,
        error: str | None = None,
        indexed: bool,
    ) -> None:
        path_text = self._path_text(path)
        stored_size, stored_mtime = self._metadata_or_existing(Path(path_text), kb_id, size, mtime)
        indexed_expr = "unixepoch()" if indexed else "NULL"
        attempts_expr = "excluded.attempts" if attempts is not None else "file_state.attempts"
        self._conn.execute(
            f"""
            INSERT INTO file_state
              (path, kb_id, size, mtime, sha256, status, attempts, error, indexed_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, {indexed_expr}, unixepoch())
            ON CONFLICT(path, kb_id) DO UPDATE SET
              size=excluded.size,
              mtime=excluded.mtime,
              sha256=excluded.sha256,
              status=excluded.status,
              attempts={attempts_expr},
              error=excluded.error,
              indexed_at={indexed_expr},
              updated_at=unixepoch()
            """,
            (
                path_text,
                kb_id,
                stored_size,
                stored_mtime,
                sha256,
                status.value,
                attempts if attempts is not None else 0,
                error,
            ),
        )
        self._conn.commit()

    def _metadata_or_existing(
        self,
        path: Path,
        kb_id: str,
        size: int | None,
        mtime: float | None,
    ) -> tuple[int, float]:
        if size is not None and mtime is not None:
            return size, mtime

        row = cast(
            tuple[object, ...] | None,
            self._conn.execute(
            "SELECT size, mtime FROM file_state WHERE path=? AND kb_id=?",
            (str(path), kb_id),
            ).fetchone(),
        )
        if row is not None:
            return self._as_int(row[0]), self._as_float(row[1])

        try:
            stat = path.stat()
        except OSError:
            return size or 0, mtime or 0.0
        resolved_size = size if size is not None else stat.st_size
        resolved_mtime = mtime if mtime is not None else stat.st_mtime
        return resolved_size, resolved_mtime

    @staticmethod
    def _path_text(path: Path | str) -> str:
        return str(path)

    @staticmethod
    def _as_int(value: object) -> int:
        if isinstance(value, int):
            return value
        return int(str(value))

    @staticmethod
    def _as_float(value: object) -> float:
        if isinstance(value, float):
            return value
        if isinstance(value, int):
            return float(value)
        return float(str(value))

    @staticmethod
    def _row_to_record(row: tuple[object, ...]) -> FileRecord:
        return FileRecord(
            path=str(row[0]),
            kb_id=str(row[1]),
            size=StateStore._as_int(row[2]),
            mtime=StateStore._as_float(row[3]),
            sha256=None if row[4] is None else str(row[4]),
            status=FileStatus(str(row[5])),
            attempts=StateStore._as_int(row[6]),
            error=None if row[7] is None else str(row[7]),
        )

    def close(self) -> None:
        """Cierra la conexión subyacente."""
        self._conn.close()

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
