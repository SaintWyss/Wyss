"""Fixtures compartidas de los tests del pipeline de ingesta (Fase 3).

Provee:
- `index_db_path`: ruta a una index.db sobre tmp_path (ext4/tmpfs — WAL OK).
- `make_source_file`: factory de SourceFile con defaults sensatos (espejo de tests/audit/conftest).
- `audit`: FakeAuditPort reusado de tests/ports/fakes (AuditPort inyectado, no importado).
- Re-export de los fakes de knowledge existentes para uso en los tests de la fase.

NO usar pyfakefs — tmp_path real (ext4/tmpfs) para garantizar que WAL funciona correctamente.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from core.domain.knowledge import SourceFile
from tests.ports.fakes import (
    FakeAuditPort,
    FakeChunker,
    FakeEmbeddingProvider,
    FakeExtractor,
    FakeFullTextIndex,
    FakeVectorIndex,
)

# Re-export de los fakes para que los tests de la fase puedan importar directamente
# desde tests.knowledge.conftest sin buscar en tests.ports.fakes.
__all__ = [
    "FakeAuditPort",
    "FakeChunker",
    "FakeEmbeddingProvider",
    "FakeExtractor",
    "FakeFullTextIndex",
    "FakeVectorIndex",
]


@pytest.fixture
def index_db_path(tmp_path: Path) -> Path:
    """Ruta a una index.db sobre tmp_path (ext4/tmpfs — WAL funciona, Pitfall 3 RESEARCH)."""
    return tmp_path / "index.db"


@pytest.fixture
def make_source_file() -> Callable[..., SourceFile]:
    """Factory de SourceFile con defaults sensatos para reuso en tests del pipeline.

    Espejo del patrón `make_event` de tests/audit/conftest y `make_request` de
    tests/gateway/conftest: función con keyword args + defaults razonables.
    """

    def _make(
        *,
        path: str = "/tmp/test.txt",
        media_type: str = "text/plain",
        size: int = 100,
        mtime: float = 1_700_000_000.0,
    ) -> SourceFile:
        return SourceFile(path=path, media_type=media_type, size=size, mtime=mtime)

    return _make


@pytest.fixture
def audit() -> FakeAuditPort:
    """AuditPort en memoria para inspeccionar el rastro emitido por el pipeline."""
    return FakeAuditPort()
