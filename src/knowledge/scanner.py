"""Scanner de filesystem para la ingesta de conocimiento.

Recorre directorios con `os.scandir`, no sigue symlinks y detecta MIME por
contenido con libmagic. La salida distingue archivos procesables de skips
permanentes para que el pipeline pueda registrar estado sin abrir extractores.
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import magic

from core.domain.knowledge import FileStatus, SourceFile


@dataclass(frozen=True, slots=True)
class ScanItem:
    """Resultado del scanner: un archivo regular o un skip con metadatos disponibles."""

    path: str
    status: FileStatus | None = None
    source: SourceFile | None = None


class Scanner:
    """Recorre una raíz local aplicando D-41/D-42 antes del pipeline."""

    def scan(
        self,
        root: Path,
        *,
        max_file_bytes: int,
        dir_denylist: frozenset[str],
    ) -> Iterator[ScanItem]:
        """Produce `ScanItem` para archivos regulares y skips permanentes.

        `root` se resuelve antes de recorrer. Si no es un directorio real, el
        error es sistémico y se levanta como `NotADirectoryError`.
        """

        resolved_root = root.resolve()
        if not resolved_root.is_dir():
            raise NotADirectoryError(str(resolved_root))

        yield from self._scan_dir(
            resolved_root,
            max_file_bytes=max_file_bytes,
            dir_denylist=dir_denylist,
        )

    def _scan_dir(
        self,
        current: Path,
        *,
        max_file_bytes: int,
        dir_denylist: frozenset[str],
    ) -> Iterator[ScanItem]:
        with os.scandir(current) as entries:
            for entry in entries:
                path = Path(entry.path)

                if entry.is_symlink():
                    yield ScanItem(path=str(path), status=FileStatus.skipped_symlink)
                    continue

                if entry.is_dir(follow_symlinks=False):
                    if entry.name in dir_denylist:
                        continue
                    yield from self._scan_dir(
                        path,
                        max_file_bytes=max_file_bytes,
                        dir_denylist=dir_denylist,
                    )
                    continue

                if not entry.is_file(follow_symlinks=False):
                    continue

                stat_result = entry.stat(follow_symlinks=False)
                media_type = str(magic.from_file(str(path), mime=True))
                source = SourceFile(
                    path=str(path),
                    media_type=media_type,
                    size=stat_result.st_size,
                    mtime=stat_result.st_mtime,
                )
                if stat_result.st_size > max_file_bytes:
                    yield ScanItem(
                        path=str(path),
                        status=FileStatus.skipped_size,
                        source=source,
                    )
                    continue

                yield ScanItem(path=str(path), source=source)
