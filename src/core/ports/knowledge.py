"""Puertos de conocimiento: extracción, chunking, embeddings, índices y retrieval."""

from collections.abc import Sequence
from typing import Protocol

from core.domain import (
    Chunk,
    ExtractedContent,
    Hit,
    IndexEntry,
    Query,
    SearchResult,
    SourceFile,
    Subject,
    Vector,
)


class Extractor(Protocol):
    """Convierte un archivo de origen en texto. Nuevo tipo de archivo = nueva clase."""

    @property
    def media_types(self) -> frozenset[str]: ...

    def extract(self, source: SourceFile) -> ExtractedContent: ...


class Chunker(Protocol):
    """Fragmenta contenido extraído en chunks indexables."""

    def chunk(self, content: ExtractedContent) -> Sequence[Chunk]: ...


class EmbeddingProvider(Protocol):
    """Genera vectores de embedding. Async: cruza la red."""

    async def embed(self, texts: Sequence[str]) -> Sequence[Vector]: ...


class FullTextIndex(Protocol):
    """Índice full-text (FTS5). `kb_ids` es parámetro del port: filtrar por BC no es opcional."""

    def upsert(self, entries: Sequence[IndexEntry]) -> None: ...

    def search(self, query: str, kb_ids: frozenset[str], limit: int) -> Sequence[Hit]: ...


class VectorIndex(Protocol):
    """Índice vectorial. `kb_ids` es parámetro del port — filtrado estructural por BC."""

    def upsert(self, entries: Sequence[tuple[IndexEntry, Vector]]) -> None: ...

    def search(self, vector: Vector, kb_ids: frozenset[str], limit: int) -> Sequence[Hit]: ...


class Retrieval(Protocol):
    """Lo que ven agentes/orquestador: resultados ya fusionados y filtrados por permiso. Async."""

    async def search(self, query: Query, subject: Subject) -> SearchResult: ...
