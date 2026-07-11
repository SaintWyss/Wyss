"""Helpers para salidas markdown legibles de Notion."""

import json
from collections.abc import Mapping, Sequence

_READ_OUTPUT_CAP_CHARS = 256 * 1024
_ROWS_OUTPUT_CAP_CHARS = 256 * 1024


def markdown_output(response: Mapping[str, object]) -> tuple[str, bool]:
    """Devuelve markdown visible y marca truncado si Notion lo reporta o si se capa localmente."""
    markdown = str(response.get("markdown", ""))
    notion_truncated = bool(response.get("truncated", False))
    output, locally_truncated = _cap_text(markdown, _READ_OUTPUT_CAP_CHARS)
    if notion_truncated:
        output = f"{output}\n\n[NOTA: contenido truncado por Notion; la pagina excede el limite]"
    return output, notion_truncated or locally_truncated


def rows_output(rows: Sequence[Mapping[str, object]]) -> tuple[str, bool]:
    """Renderiza filas de una data source como markdown acotado para `payload['output']`."""
    lines = [f"# Filas Notion ({len(rows)})"]
    for index, row in enumerate(rows, start=1):
        row_id = str(row.get("id", "sin-id"))
        url = row.get("url")
        lines.append(f"\n## {index}. {row_id}")
        if isinstance(url, str) and url:
            lines.append(f"- url: {url}")
        properties = row.get("properties")
        if isinstance(properties, Mapping):
            lines.append("- properties:")
            pretty = json.dumps(properties, ensure_ascii=False, sort_keys=True, indent=2)
            for line in pretty.splitlines():
                lines.append(f"  {line}")
        else:
            row_text = json.dumps(row, ensure_ascii=False, sort_keys=True, indent=2)
            lines.append("```json")
            lines.append(row_text)
            lines.append("```")
    return _cap_text("\n".join(lines), _ROWS_OUTPUT_CAP_CHARS)


def _cap_text(text: str, cap_chars: int) -> tuple[str, bool]:
    """Aplica un tope local honesto para no volcar respuestas gigantes."""
    if len(text) <= cap_chars:
        return text, False
    clipped = text[:cap_chars]
    return (
        f"{clipped}\n\n[NOTA: contenido truncado localmente; "
        f"{len(text)} caracteres totales, mostrando {cap_chars}]",
        True,
    )

