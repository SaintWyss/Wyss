"""Extractor para texto plano, markdown y código detectado como texto."""

from pathlib import Path

from core.domain.errors import ExtractionError
from core.domain.knowledge import ExtractedContent, SourceFile


class TextExtractor:
    """Lee archivos textuales como UTF-8 tolerante."""

    @property
    def media_types(self) -> frozenset[str]:
        return frozenset(
            {
                "text/",
                "text/plain",
                "text/markdown",
                "text/x-python",
                "application/javascript",
                "application/typescript",
                "application/x-javascript",
            }
        )

    def extract(self, source: SourceFile) -> ExtractedContent:
        try:
            text = Path(source.path).read_text(encoding="utf-8", errors="replace")
            return ExtractedContent(source=source, text=text, metadata={"encoding": "utf-8"})
        except Exception as exc:
            raise ExtractionError(source.path, type(exc).__name__) from exc
