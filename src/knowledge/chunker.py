"""Chunker de ingesta: ventanas aproximadas por tokens y estrategia tabular."""

from collections.abc import Sequence

from core.domain.knowledge import Chunk, ExtractedContent

_CHARS_PER_TOKEN = 4
_TABULAR_ROWS_PER_CHUNK = 10
_CSV_MEDIA_TYPES = frozenset({"text/csv", "application/csv"})
_XLSX_MEDIA_TYPES = frozenset(
    {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    }
)


class TokenChunker:
    """Fragmenta contenido extraído en chunks indexables.

    La estimación usa la aproximación del planner: 1 token ~= 4 caracteres. Esto mantiene
    el chunker stdlib-only y deja los tamaños ajustables por la configuración de ingesta.
    """

    def __init__(self, *, chunk_size_tokens: int, chunk_overlap_tokens: int) -> None:
        if chunk_size_tokens <= 0:
            raise ValueError("chunk_size_tokens debe ser > 0")
        if chunk_overlap_tokens < 0:
            raise ValueError("chunk_overlap_tokens debe ser >= 0")
        if chunk_overlap_tokens >= chunk_size_tokens:
            raise ValueError("chunk_overlap_tokens debe ser menor que chunk_size_tokens")
        self._chunk_size_chars = chunk_size_tokens * _CHARS_PER_TOKEN
        self._chunk_overlap_chars = chunk_overlap_tokens * _CHARS_PER_TOKEN

    def chunk(self, content: ExtractedContent) -> Sequence[Chunk]:
        """Devuelve chunks con ids determinísticos; nunca emite chunks vacíos."""
        if content.text.strip() == "":
            return ()
        if self._is_tabular(content.source.media_type):
            return self._chunk_tabular(content)
        return self._chunk_windowed(content)

    def _chunk_windowed(self, content: ExtractedContent) -> tuple[Chunk, ...]:
        step = self._chunk_size_chars - self._chunk_overlap_chars
        chunks: list[Chunk] = []
        position = 0
        start = 0
        text_len = len(content.text)
        while start < text_len:
            chunk_text = content.text[start : start + self._chunk_size_chars]
            if chunk_text.strip() != "":
                chunks.append(self._make_chunk(content.source.path, position, chunk_text))
                position += 1
            start += step
        return tuple(chunks)

    def _chunk_tabular(self, content: ExtractedContent) -> tuple[Chunk, ...]:
        rows = content.text.splitlines()
        chunks: list[Chunk] = []
        position = 0
        for start in range(0, len(rows), _TABULAR_ROWS_PER_CHUNK):
            chunk_text = "\n".join(rows[start : start + _TABULAR_ROWS_PER_CHUNK])
            if chunk_text.strip() != "":
                chunks.append(self._make_chunk(content.source.path, position, chunk_text))
                position += 1
        return tuple(chunks)

    @staticmethod
    def _make_chunk(source_path: str, position: int, text: str) -> Chunk:
        return Chunk(
            chunk_id=f"{source_path}#{position}",
            text=text,
            source_path=source_path,
            position=position,
        )

    @staticmethod
    def _is_tabular(media_type: str) -> bool:
        normalized = media_type.split(";")[0].strip().lower()
        return normalized in _CSV_MEDIA_TYPES or normalized in _XLSX_MEDIA_TYPES
