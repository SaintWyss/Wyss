"""Tests de paginacion completa de data_sources.query."""

import httpx
import respx

from notion.client import build_notion_client
from notion.pagination import PaginationError, query_all_rows


async def test_query_all_rows_concatena_todas_las_paginas(
    http_client: httpx.AsyncClient,
    respx_mock: respx.MockRouter,
) -> None:
    """Consume next_cursor hasta has_more=False y preserva el orden."""
    route = respx_mock.post(
        "https://api.notion.com/v1/data_sources/ds-1/query",
    )
    route.side_effect = [
        httpx.Response(
            200,
            json={
                "object": "list",
                "results": [{"id": "row-1"}],
                "has_more": True,
                "next_cursor": "c1",
            },
        ),
        httpx.Response(
            200,
            json={
                "object": "list",
                "results": [{"id": "row-2"}],
                "has_more": True,
                "next_cursor": "c2",
            },
        ),
        httpx.Response(
            200,
            json={
                "object": "list",
                "results": [{"id": "row-3"}],
                "has_more": False,
                "next_cursor": None,
            },
        ),
    ]
    client = build_notion_client("secret_x", http_client=http_client)

    rows = await query_all_rows(client, "ds-1")

    assert [row["id"] for row in rows] == ["row-1", "row-2", "row-3"]
    assert route.call_count == 3
    assert respx_mock.calls[1].request.content == b'{"start_cursor":"c1"}'
    assert respx_mock.calls[2].request.content == b'{"start_cursor":"c2"}'


async def test_query_all_rows_falla_si_falta_next_cursor(
    http_client: httpx.AsyncClient,
    respx_mock: respx.MockRouter,
) -> None:
    """No devuelve resultados parciales si Notion no entrega cursor siguiente."""
    respx_mock.post("https://api.notion.com/v1/data_sources/ds-1/query").mock(
        return_value=httpx.Response(
            200,
            json={"object": "list", "results": [{"id": "row-1"}], "has_more": True},
        )
    )
    client = build_notion_client("secret_x", http_client=http_client)

    try:
        await query_all_rows(client, "ds-1")
    except PaginationError as exc:
        assert "next_cursor" in str(exc)
    else:
        raise AssertionError("query_all_rows devolvio resultados parciales")
