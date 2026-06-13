"""Extractor de metadatos para video y audio usando ffprobe."""

import json
import subprocess
from typing import Any

from core.domain.errors import ExtractionError
from core.domain.knowledge import ExtractedContent, SourceFile


class VideoExtractor:
    """Retorna solo metadatos de audio/video; nunca ejecuta shell."""

    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"video/", "audio/"})

    def extract(self, source: SourceFile) -> ExtractedContent:
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    source.path,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            payload = json.loads(result.stdout)
            metadata = _metadata_from_probe(payload)
            return ExtractedContent(source=source, text="", metadata=metadata)
        except Exception as exc:
            raise ExtractionError(source.path, type(exc).__name__) from exc


def _metadata_from_probe(payload: dict[str, Any]) -> dict[str, object]:
    format_data = payload.get("format")
    streams_data = payload.get("streams")
    streams = streams_data if isinstance(streams_data, list) else []
    first_stream = streams[0] if streams and isinstance(streams[0], dict) else {}

    metadata: dict[str, object] = {
        "stream_count": len(streams),
        "codec": first_stream.get("codec_name", ""),
        "codec_type": first_stream.get("codec_type", ""),
    }
    if isinstance(format_data, dict):
        metadata["duration"] = _float_or_none(format_data.get("duration"))
        metadata["format_name"] = format_data.get("format_name", "")
        metadata["bit_rate"] = _int_or_none(format_data.get("bit_rate"))
    return metadata


def _float_or_none(value: object) -> float | None:
    try:
        return float(str(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value)) if value is not None else None
    except (TypeError, ValueError):
        return None
