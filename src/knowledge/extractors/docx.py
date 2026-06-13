"""Extractor DOCX basado en python-docx."""

from docx import Document

from core.domain.errors import ExtractionError
from core.domain.knowledge import ExtractedContent, SourceFile


class DocxExtractor:
    """Extrae texto de párrafos en documentos Word OpenXML."""

    @property
    def media_types(self) -> frozenset[str]:
        return frozenset(
            {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            }
        )

    def extract(self, source: SourceFile) -> ExtractedContent:
        try:
            document = Document(source.path)
            text = "\n".join(paragraph.text for paragraph in document.paragraphs)
            metadata: dict[str, object] = {"paragraph_count": len(document.paragraphs)}
            return ExtractedContent(source=source, text=text, metadata=metadata)
        except Exception as exc:
            raise ExtractionError(source.path, type(exc).__name__) from exc
