"""Extractor de metadatos para imágenes."""

from pathlib import Path

import exifread
from PIL import Image, UnidentifiedImageError

from core.domain.errors import ExtractionError
from core.domain.knowledge import ExtractedContent, SourceFile


class ImageExtractor:
    """Retorna solo metadatos de imágenes; no hace OCR en v0.1."""

    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"image/"})

    def extract(self, source: SourceFile) -> ExtractedContent:
        try:
            metadata: dict[str, object] = {}
            with Image.open(source.path) as image:
                metadata.update(
                    {
                        "width": image.width,
                        "height": image.height,
                        "mode": image.mode,
                        "format": image.format or "",
                    }
                )
            metadata["exif"] = _read_exif(source.path)
            return ExtractedContent(source=source, text="", metadata=metadata)
        except (OSError, UnidentifiedImageError) as exc:
            raise ExtractionError(source.path, type(exc).__name__) from exc


def _read_exif(path: str) -> dict[str, str]:
    with Path(path).open("rb") as handle:
        tags = exifread.process_file(handle, details=False)
    return {key: str(value) for key, value in tags.items()}
