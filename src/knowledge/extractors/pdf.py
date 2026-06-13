"""Extractor PDF basado en PyMuPDF."""

from typing import Any, cast

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover - compatibilidad con PyMuPDF viejo
    import fitz  # type: ignore[import-untyped,no-redef]

from core.domain.errors import ExtractionError, UnsupportedFileError
from core.domain.knowledge import ExtractedContent, SourceFile


class PdfExtractor:
    """Extrae texto de PDF y rechaza PDFs encriptados sin pedir password."""

    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"application/pdf"})

    def extract(self, source: SourceFile) -> ExtractedContent:
        doc: Any | None = None
        try:
            doc = cast(Any, fitz.open(source.path))  # type: ignore[no-untyped-call]
            if doc.is_encrypted:
                raise UnsupportedFileError(source.path)
            text = "\n\n".join(doc.load_page(index).get_text() for index in range(len(doc)))
            raw_metadata = doc.metadata or {}
            metadata: dict[str, object] = {
                "page_count": len(doc),
                "title": raw_metadata.get("title", ""),
                "author": raw_metadata.get("author", ""),
            }
            return ExtractedContent(source=source, text=text, metadata=metadata)
        except UnsupportedFileError:
            raise
        except Exception as exc:
            raise ExtractionError(source.path, type(exc).__name__) from exc
        finally:
            if doc is not None:
                doc.close()
