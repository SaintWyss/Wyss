"""Entidades de conocimiento (mínimas) — solo lo que las firmas de los ports necesitan.

Expandir en Fases 3-4 es aditivo, no breaking.
"""

from collections.abc import Mapping
from dataclasses import dataclass

# Un vector de embedding: tupla de floats (inmutable, hashable).
type Vector = tuple[float, ...]


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
