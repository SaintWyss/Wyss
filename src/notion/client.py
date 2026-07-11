"""Construccion del cliente Notion inyectable."""

import httpx
from notion_client import AsyncClient
from notion_client.client import ClientOptions, RetryOptions


def build_notion_client(
    token: str,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> AsyncClient:
    """Crea un AsyncClient con retry del SDK y transporte inyectable para tests."""
    return AsyncClient(
        options=ClientOptions(auth=token, retry=RetryOptions(max_retries=3)),
        client=http_client,
    )
