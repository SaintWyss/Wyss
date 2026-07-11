"""Tests del NotionTool."""

from collections.abc import Mapping

import httpx
import respx

from core.domain.plan import Action
from core.domain.risk import RiskLevel
from notion.client import build_notion_client
from notion.tool import NotionTool
from tests.ports.fakes import FakeAuditPort

_PAGE_ID = "12345678-1234-1234-1234-123456789abc"
_DB_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _tool(http_client: httpx.AsyncClient, audit: FakeAuditPort) -> NotionTool:
    return NotionTool(
        client=build_notion_client("secret-token-for-tests", http_client=http_client),
        audit=audit,
    )


async def test_read_page_devuelve_markdown(
    http_client: httpx.AsyncClient,
    respx_mock: respx.MockRouter,
    audit: FakeAuditPort,
) -> None:
    """read_page usa pages.retrieve_markdown y expone output legible."""
    respx_mock.get(f"https://api.notion.com/v1/pages/{_PAGE_ID}/markdown").mock(
        return_value=httpx.Response(
            200,
            json={"markdown": "# Reunion\n\nNotas", "truncated": False},
        )
    )

    result = await _tool(http_client, audit).execute(
        Action(type="notion.read_page", target=_PAGE_ID)
    )

    assert result.success is True
    assert result.payload["output"] == "# Reunion\n\nNotas"
    assert result.payload["truncated"] is False
    assert audit.events[-1].payload["page_id"] == _PAGE_ID


async def test_read_page_anota_contenido_truncado(
    http_client: httpx.AsyncClient,
    respx_mock: respx.MockRouter,
    audit: FakeAuditPort,
) -> None:
    """Si Notion reporta truncated=True, el output lo declara."""
    respx_mock.get(f"https://api.notion.com/v1/pages/{_PAGE_ID}/markdown").mock(
        return_value=httpx.Response(200, json={"markdown": "# Largo", "truncated": True})
    )

    result = await _tool(http_client, audit).execute(
        Action(type="notion.read_page", target=_PAGE_ID)
    )

    assert result.success is True
    assert "contenido truncado" in str(result.payload["output"])
    assert result.payload["truncated"] is True


async def test_query_database_resuelve_data_source_y_pagina(
    http_client: httpx.AsyncClient,
    respx_mock: respx.MockRouter,
    audit: FakeAuditPort,
) -> None:
    """query_database usa databases.retrieve y pagina data_sources.query completo."""
    respx_mock.get(f"https://api.notion.com/v1/databases/{_DB_ID}").mock(
        return_value=httpx.Response(200, json={"id": _DB_ID, "data_sources": [{"id": "ds-1"}]})
    )
    route = respx_mock.post("https://api.notion.com/v1/data_sources/ds-1/query")
    route.side_effect = [
        httpx.Response(
            200,
            json={
                "results": [{"id": "row-1", "properties": {"Name": {"title": []}}}],
                "has_more": True,
                "next_cursor": "next",
            },
        ),
        httpx.Response(
            200,
            json={
                "results": [{"id": "row-2", "properties": {"Name": {"title": []}}}],
                "has_more": False,
                "next_cursor": None,
            },
        ),
    ]

    result = await _tool(http_client, audit).execute(
        Action(type="notion.query_database", target=_DB_ID)
    )

    assert result.success is True
    assert result.payload["rows"] == 2
    assert "row-1" in str(result.payload["output"])
    assert "row-2" in str(result.payload["output"])
    assert route.call_count == 2
    assert audit.events[-1].payload["database_id"] == _DB_ID


async def test_create_page_construye_request_markdown(
    http_client: httpx.AsyncClient,
    respx_mock: respx.MockRouter,
    audit: FakeAuditPort,
) -> None:
    """create_page envia parent/properties/markdown al endpoint pages.create."""
    route = respx_mock.post("https://api.notion.com/v1/pages").mock(
        return_value=httpx.Response(200, json={"id": _PAGE_ID})
    )
    action = Action(
        type="notion.create_page",
        target=_PAGE_ID,
        parameters={
            "parent": {"database_id": _DB_ID},
            "properties": {"Name": {"title": []}},
            "markdown": "# Nueva",
        },
    )

    result = await _tool(http_client, audit).execute(action)

    assert result.success is True
    assert result.payload["page_id"] == _PAGE_ID
    assert route.calls.last.request.read() == (
        b'{"parent":{"database_id":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},'
        b'"properties":{"Name":{"title":[]}},"markdown":"# Nueva"}'
    )


async def test_update_page_construye_request_update_markdown(
    http_client: httpx.AsyncClient,
    respx_mock: respx.MockRouter,
    audit: FakeAuditPort,
) -> None:
    """update_page usa pages.update_markdown con type=update_content por defecto."""
    route = respx_mock.patch(f"https://api.notion.com/v1/pages/{_PAGE_ID}/markdown").mock(
        return_value=httpx.Response(200, json={"id": _PAGE_ID})
    )

    result = await _tool(http_client, audit).execute(
        Action(
            type="notion.update_page",
            target=_PAGE_ID,
            parameters={"update_content": "Texto nuevo"},
        )
    )

    assert result.success is True
    assert route.calls.last.request.read() == (
        b'{"type":"update_content","update_content":"Texto nuevo"}'
    )


async def test_pagina_no_compartida_devuelve_error_legible(
    http_client: httpx.AsyncClient,
    respx_mock: respx.MockRouter,
    audit: FakeAuditPort,
) -> None:
    """404/object_not_found no propaga excepcion y explica el permiso."""
    respx_mock.get(f"https://api.notion.com/v1/pages/{_PAGE_ID}/markdown").mock(
        return_value=httpx.Response(
            404,
            json={
                "object": "error",
                "status": 404,
                "code": "object_not_found",
                "message": "Could not find page.",
            },
        )
    )

    result = await _tool(http_client, audit).execute(
        Action(type="notion.read_page", target=_PAGE_ID)
    )

    assert result.success is False
    assert "no compartida" in result.detail
    assert audit.events[-1].payload["success"] is False


async def test_target_malformado_no_hace_request(
    http_client: httpx.AsyncClient,
    respx_mock: respx.MockRouter,
    audit: FakeAuditPort,
) -> None:
    """Una URL no Notion se rechaza antes del SDK."""
    result = await _tool(http_client, audit).execute(
        Action(type="notion.read_page", target="https://example.com/nope")
    )

    assert result.success is False
    assert "invalido" in result.detail
    assert respx_mock.calls.call_count == 0


async def test_token_never_in_audit_payload(
    http_client: httpx.AsyncClient,
    respx_mock: respx.MockRouter,
    audit: FakeAuditPort,
) -> None:
    """El token no aparece en payloads ni detalles aunque el request falle."""
    token = "secret-token-for-tests"
    respx_mock.get(f"https://api.notion.com/v1/pages/{_PAGE_ID}/markdown").mock(
        return_value=httpx.Response(
            404,
            json={
                "object": "error",
                "status": 404,
                "code": "restricted_resource",
                "message": token,
            },
        )
    )

    result = await _tool(http_client, audit).execute(
        Action(type="notion.read_page", target=_PAGE_ID)
    )

    assert token not in result.detail
    assert token not in _flatten(result.payload)
    for event in audit.events:
        assert token not in event.message
        assert token not in _flatten(event.payload)


def test_max_risk_c_y_describe_legible(
    http_client: httpx.AsyncClient,
    audit: FakeAuditPort,
) -> None:
    """El techo del adapter cubre writes nivel C y describe action types."""
    tool = _tool(http_client, audit)

    assert tool.max_risk == RiskLevel.C
    assert "actualizar" in tool.describe(Action(type="notion.update_page", target=_PAGE_ID))


def _flatten(value: object) -> str:
    if isinstance(value, Mapping):
        return " ".join(_flatten(item) for pair in value.items() for item in pair)
    if isinstance(value, list | tuple):
        return " ".join(_flatten(item) for item in value)
    return str(value)
