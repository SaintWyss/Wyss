"""Paginacion explicita de data sources Notion."""

from collections.abc import Mapping
from typing import Any, cast

from notion_client import AsyncClient


class PaginationError(RuntimeError):
    """Error de paginacion que impediria devolver resultados completos."""


async def query_all_rows(
    client: AsyncClient,
    data_source_id: str,
    *,
    page_size: int | None = None,
) -> list[Mapping[str, object]]:
    """Consume todas las paginas de `data_sources.query` antes de devolver resultados."""
    rows: list[Mapping[str, object]] = []
    cursor: str | None = None

    while True:
        kwargs: dict[str, object] = {}
        if cursor is not None:
            kwargs["start_cursor"] = cursor
        if page_size is not None:
            kwargs["page_size"] = page_size

        response = cast(
            Mapping[str, Any],
            await client.data_sources.query(data_source_id, **kwargs),
        )
        raw_results = response.get("results", [])
        if isinstance(raw_results, list):
            rows.extend(cast(list[Mapping[str, object]], raw_results))

        if not bool(response.get("has_more", False)):
            break

        next_cursor = response.get("next_cursor")
        cursor = str(next_cursor) if next_cursor is not None else None
        if cursor is None:
            msg = "Notion devolvio has_more=True sin next_cursor"
            raise PaginationError(msg)

    return rows
