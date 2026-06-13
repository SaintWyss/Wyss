"""Extractor RTF que convierte documentos enriquecidos a texto plano."""

import importlib
from collections.abc import Callable
from pathlib import Path
from typing import cast

from core.domain.errors import ExtractionError
from core.domain.knowledge import ExtractedContent, SourceFile


def _load_striprtf() -> Callable[[str], str] | None:
    try:
        module = importlib.import_module("striprtf.striprtf")
    except ImportError:
        return None
    return cast("Callable[[str], str]", module.rtf_to_text)


_striprtf_to_text = _load_striprtf()


class RtfExtractor:
    """Decodifica RTF a texto plano antes de que corra el filtro de secretos."""

    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"text/rtf", "application/rtf"})

    def extract(self, source: SourceFile) -> ExtractedContent:
        try:
            raw = Path(source.path).read_text(encoding="utf-8", errors="replace")
            if _striprtf_to_text is not None:
                text = _striprtf_to_text(raw)
                parser = "striprtf"
            else:
                text = _fallback_rtf_to_text(raw)
                parser = "fallback"
            metadata: dict[str, object] = {"encoding": "utf-8", "parser": parser}
            return ExtractedContent(source=source, text=" ".join(text.split()), metadata=metadata)
        except Exception as exc:
            raise ExtractionError(source.path, type(exc).__name__) from exc


def _fallback_rtf_to_text(rtf: str) -> str:
    """Fallback chico para tests offline; la dependencia real es `striprtf`."""
    output: list[str] = []
    index = 0
    ignored_depth = 0

    while index < len(rtf):
        char = rtf[index]

        if ignored_depth > 0:
            if char == "{":
                ignored_depth += 1
            elif char == "}":
                ignored_depth -= 1
            index += 1
            continue

        if char == "{":
            if _starts_ignored_group(rtf, index):
                ignored_depth = 1
            index += 1
            continue

        if char == "}":
            index += 1
            continue

        if char == "\\":
            index = _consume_control(rtf, index, output)
            continue

        output.append(char)
        index += 1

    return "".join(output)


def _starts_ignored_group(rtf: str, index: int) -> bool:
    return rtf.startswith(r"{\pict", index) or rtf.startswith(r"{\object", index)


def _consume_control(rtf: str, index: int, output: list[str]) -> int:
    index += 1
    if index >= len(rtf):
        return index

    symbol = rtf[index]
    if symbol in "{}\\":
        output.append(symbol)
        return index + 1

    if symbol == "'" and index + 2 < len(rtf):
        hex_value = rtf[index + 1 : index + 3]
        try:
            output.append(bytes.fromhex(hex_value).decode("latin-1"))
        except ValueError:
            return index + 3
        return index + 3

    if not symbol.isalpha():
        return index + 1

    word_start = index
    while index < len(rtf) and rtf[index].isalpha():
        index += 1
    word = rtf[word_start:index]

    if index < len(rtf) and rtf[index] in "-+":
        index += 1
    while index < len(rtf) and rtf[index].isdigit():
        index += 1
    if index < len(rtf) and rtf[index] == " ":
        index += 1

    if word in {"par", "line"}:
        output.append("\n")
    elif word == "tab":
        output.append("\t")

    return index
