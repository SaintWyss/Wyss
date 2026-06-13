"""Extractor HTML que entrega texto escaneable sin markup ni atributos."""

import re
from html.parser import HTMLParser
from pathlib import Path

from core.domain.errors import ExtractionError
from core.domain.knowledge import ExtractedContent, SourceFile

_DATA_URI_RE = re.compile(r"data:[^\s\"')>]+", re.IGNORECASE)


class HtmlExtractor:
    """Extrae texto visible de HTML e incluye comentarios para el filtro de secretos."""

    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"text/html"})

    def extract(self, source: SourceFile) -> ExtractedContent:
        try:
            raw = Path(source.path).read_text(encoding="utf-8", errors="replace")
            parser = _VisibleTextParser()
            parser.feed(raw)
            parser.close()
            text = _normalize_text(" ".join(parser.chunks))
            metadata: dict[str, object] = {
                "encoding": "utf-8",
                "comments_included": True,
            }
            return ExtractedContent(source=source, text=text, metadata=metadata)
        except Exception as exc:
            raise ExtractionError(source.path, type(exc).__name__) from exc


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._ignored_depth > 0:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self.chunks.append(data)

    def handle_comment(self, data: str) -> None:
        if self._ignored_depth == 0:
            self.chunks.append(data)


def _normalize_text(text: str) -> str:
    text = _DATA_URI_RE.sub("", text)
    return " ".join(text.split())
