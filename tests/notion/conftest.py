"""Fixtures HTTP sin red para Notion."""

from collections.abc import Iterator

import httpx
import pytest
import respx

from tests.ports.fakes import FakeAuditPort


@pytest.fixture
def respx_mock() -> Iterator[respx.MockRouter]:
    """Router respx activo para interceptar el SDK Notion."""
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def http_client() -> Iterator[httpx.AsyncClient]:
    """Cliente httpx inyectable en notion-client."""
    client = httpx.AsyncClient()
    try:
        yield client
    finally:
        pass


@pytest.fixture
def audit() -> FakeAuditPort:
    """AuditPort en memoria para inspeccionar eventos emitidos por NotionTool."""
    return FakeAuditPort()
