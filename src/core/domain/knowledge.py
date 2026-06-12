"""Entidades de conocimiento (mínimas) — solo lo que las firmas de los ports necesitan.

Expandir en Fases 3-4 es aditivo, no breaking.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

# Un vector de embedding: tupla de floats (inmutable, hashable).
type Vector = tuple[float, ...]


class FileStatus(StrEnum):
    """Estado de un archivo en el pipeline de ingesta (D-42)."""

    pending = "pending"
    extracted = "extracted"
    embedded = "embedded"
    failed = "failed"
    excluded_secret = "excluded_secret"
    skipped_unsupported = "skipped_unsupported"
    skipped_symlink = "skipped_symlink"
    skipped_size = "skipped_size"


@dataclass(frozen=True, slots=True)
class IngestSettings:
    """Configuración del pipeline de ingesta — frozen, stdlib only (D-33).

    `dir_denylist` y `entropy_allowlist` son tuplas, no listas, porque el dataclass es frozen.
    Los defaults replican lo que `IngestConfigModel` de bootstrap construye.
    """

    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 51  # ~10% de 512
    max_file_bytes: int = 104_857_600  # 100 MB (D-41)
    dir_denylist: tuple[str, ...] = field(
        default=(
            ".git", "node_modules", ".cache", "__pycache__",
            ".venv", "venv", "dist", "build", ".tox",
        )
    )
    entropy_allowlist: tuple[str, ...] = ()  # D-30: globs que desactivan capa 3 de entropía
    default_kb_id: str = "default"
    max_attempts: int = 3  # D-39: reintentos automáticos antes de --retry-failed


@dataclass(frozen=True, slots=True)
class SourceFile:
    """Un archivo de origen registrado para indexación."""

    path: str
    media_type: str
    size: int
    mtime: float


@dataclass(frozen=True, slots=True)
class ExtractedContent:
    """Texto extraído de un SourceFile más metadatos."""

    source: SourceFile
    text: str
    metadata: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class Chunk:
    """Un fragmento indexable con referencia exacta a su origen."""

    chunk_id: str
    text: str
    source_path: str
    position: int


@dataclass(frozen=True, slots=True)
class IndexEntry:
    """Una entrada catalogada en una base de conocimiento (kb_id)."""

    entry_id: str
    kb_id: str
    chunk: Chunk


@dataclass(frozen=True, slots=True)
class Hit:
    """Un resultado de búsqueda: ubicación exacta + extracto + score."""

    entry_id: str
    score: float
    snippet: str
    source_path: str


@dataclass(frozen=True, slots=True)
class Query:
    """Consulta de retrieval, acotada a un conjunto de bases de conocimiento."""

    text: str
    kb_ids: frozenset[str]
    limit: int


@dataclass(frozen=True, slots=True)
class FileRecord:
    """Espejo de una fila de `file_state` en SQLite — estado por archivo en el pipeline."""

    path: str
    kb_id: str
    size: int
    mtime: float
    sha256: str | None
    status: FileStatus
    attempts: int
    error: str | None


@dataclass(frozen=True, slots=True)
class EstimateResult:
    """Proyección de `wyss index --estimate` (D-34): archivos, chunks, tiempo, costo."""

    files: int
    total_bytes: int
    projected_chunks: int
    embed_time_s: float
    cost_usd: float  # D-34: Ollama local → siempre 0.0


@dataclass(frozen=True, slots=True)
class IngestRunResult:
    """Resumen al final de una corrida de ingesta (D-36/D-37)."""

    indexed: int
    failed: int
    excluded_secret: int
    skipped: int
    run_id: str
