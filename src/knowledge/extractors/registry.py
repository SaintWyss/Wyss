"""Registro de extractores por MIME type.

El registry implementa el plugin pattern: agregar soporte para un formato nuevo
solo requiere registrar otro objeto que cumpla el Protocol `Extractor`.
"""

from core.ports.knowledge import Extractor


class ExtractorRegistry:
    """Registro en memoria con resolución exacta y por prefijo MIME."""

    def __init__(self) -> None:
        self._by_type: dict[str, Extractor] = {}

    def register(self, extractor: Extractor) -> None:
        """Indexa un extractor por cada media type que declara soportar."""
        for media_type in extractor.media_types:
            self._by_type[media_type] = extractor

    def resolve(self, media_type: str) -> Extractor | None:
        """Resuelve primero por MIME exacto y luego por prefijo, ej. `text/`."""
        if media_type in self._by_type:
            return self._by_type[media_type]
        prefix = media_type.split("/", maxsplit=1)[0] + "/"
        return self._by_type.get(prefix)
