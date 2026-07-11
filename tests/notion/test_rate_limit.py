"""Tests del retry 429 provisto por notion-client."""

import httpx
import respx

from notion.client import build_notion_client


async def test_retry_429_y_luego_exito(
    http_client: httpx.AsyncClient,
    respx_mock: respx.MockRouter,
) -> None:
    """RetryOptions honra Retry-After y reintenta el request rate-limited."""
    page_id = "12345678-1234-1234-1234-123456789abc"
    route = respx_mock.get(f"https://api.notion.com/v1/pages/{page_id}/markdown")
    route.side_effect = [
        httpx.Response(
            429,
            headers={"Retry-After": "0"},
            json={"object": "error", "status": 429, "code": "rate_limited", "message": "slow"},
        ),
        httpx.Response(200, json={"markdown": "# ok", "truncated": False}),
    ]
    client = build_notion_client("secret_x", http_client=http_client)

    response = await client.pages.retrieve_markdown(page_id, include_transcript=False)

    assert response["markdown"] == "# ok"
    assert route.call_count == 2

