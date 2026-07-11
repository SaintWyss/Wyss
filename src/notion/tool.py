"""Tool adapter para Notion.

El token vive dentro del AsyncClient construido por el composition root. Este adapter
solo audita ids normalizados y outcome, nunca credenciales ni detalles crudos del SDK.
"""

from collections.abc import Mapping
from enum import Enum
from typing import cast

from notion_client import (
    APIErrorCode,
    APIResponseError,
    AsyncClient,
    extract_notion_id,
    extract_page_id,
)

from core.domain.audit import ActorType, AuditEvent, AuditEventType
from core.domain.execution import ToolResult, Verification
from core.domain.plan import Action
from core.domain.risk import RiskLevel
from core.ports.audit import AuditPort
from notion.markdown import markdown_output, rows_output
from notion.pagination import PaginationError, query_all_rows

_PERMISSION_DETAIL = "pagina no compartida con la integracion Wyss, o no existe"


class NotionTool:
    """Adapter Notion para lecturas y escrituras gateadas por politica."""

    def __init__(self, *, client: AsyncClient, audit: AuditPort) -> None:
        self._client = client
        self._audit = audit

    @property
    def name(self) -> str:
        return "notion"

    @property
    def max_risk(self) -> RiskLevel:
        return RiskLevel.C

    def describe(self, action: Action) -> str:
        descriptions = {
            "notion.read_page": "leer pagina Notion",
            "notion.query_database": "consultar base Notion",
            "notion.create_page": "crear pagina Notion",
            "notion.update_page": "actualizar pagina Notion",
        }
        prefix = descriptions.get(action.type, "accion Notion")
        return f"{prefix}: {action.target}"

    async def execute(self, action: Action) -> ToolResult:
        """Ejecuta una action Notion y convierte errores esperables en ToolResult."""
        notion_id = _normalize_target(action)
        if notion_id is None:
            result = ToolResult(
                success=False,
                detail="target Notion invalido",
                payload={"target_valid": False},
            )
            self._audit_result(action, None, result)
            return result

        try:
            if action.type == "notion.read_page":
                result = await self._read_page(notion_id)
            elif action.type == "notion.query_database":
                result = await self._query_database(notion_id)
            elif action.type == "notion.create_page":
                result = await self._create_page(action)
            elif action.type == "notion.update_page":
                result = await self._update_page(action, notion_id)
            else:
                result = ToolResult(
                    success=False,
                    detail=f"unsupported action type: {action.type!r}",
                    payload={"notion_id": notion_id},
                )
        except APIResponseError as exc:
            result = _result_from_api_error(exc, notion_id)
        except PaginationError:
            result = ToolResult(
                success=False,
                detail="Notion no permitio completar la paginacion",
                payload={"notion_id": notion_id, "pagination_complete": False},
            )

        self._audit_result(action, notion_id, result)
        return result

    async def verify(self, action: Action, result: ToolResult) -> Verification:
        """La verificacion del adapter refleja el resultado del SDK."""
        return Verification(passed=result.success, detail=result.detail)

    async def _read_page(self, page_id: str) -> ToolResult:
        response = cast(
            Mapping[str, object],
            await self._client.pages.retrieve_markdown(page_id, include_transcript=False),
        )
        output, truncated = markdown_output(response)
        return ToolResult(
            success=True,
            detail=f"pagina Notion leida: {page_id}",
            payload={"page_id": page_id, "output": output, "truncated": truncated},
        )

    async def _query_database(self, database_id: str) -> ToolResult:
        database = cast(
            Mapping[str, object],
            await self._client.databases.retrieve(database_id),
        )
        data_source_id = _first_data_source_id(database)
        if data_source_id is None:
            return ToolResult(
                success=False,
                detail="la base Notion no expone data_sources consultables",
                payload={"database_id": database_id},
            )

        rows = await query_all_rows(self._client, data_source_id)
        output, truncated = rows_output(rows)
        return ToolResult(
            success=True,
            detail=f"base Notion consultada: {database_id}",
            payload={
                "database_id": database_id,
                "data_source_id": data_source_id,
                "rows": len(rows),
                "output": output,
                "truncated": truncated,
            },
        )

    async def _create_page(self, action: Action) -> ToolResult:
        parent = _mapping_param(action.parameters, "parent")
        properties = _mapping_param(action.parameters, "properties")
        markdown = _str_param(action.parameters, "markdown", "")
        response = cast(
            Mapping[str, object],
            await self._client.pages.create(
                parent=parent,
                properties=properties,
                markdown=markdown,
            ),
        )
        page_id = str(response.get("id", ""))
        return ToolResult(
            success=True,
            detail="pagina Notion creada",
            payload={"page_id": page_id, "output": f"Pagina creada: {page_id}"},
        )

    async def _update_page(self, action: Action, page_id: str) -> ToolResult:
        update_type = _str_param(action.parameters, "type", "update_content")
        update_content = _str_param(action.parameters, "update_content", "")
        response = cast(
            Mapping[str, object],
            await self._client.pages.update_markdown(
                page_id,
                type=update_type,
                update_content=update_content,
            ),
        )
        returned_id = str(response.get("id", page_id))
        return ToolResult(
            success=True,
            detail=f"pagina Notion actualizada: {page_id}",
            payload={"page_id": returned_id, "output": f"Pagina actualizada: {returned_id}"},
        )

    def _audit_result(self, action: Action, notion_id: str | None, result: ToolResult) -> None:
        payload: dict[str, object] = {
            "action_type": action.type,
            "success": result.success,
        }
        if notion_id is not None:
            if action.type == "notion.query_database":
                payload["database_id"] = notion_id
            else:
                payload["page_id"] = notion_id
        self._audit.log(
            AuditEvent.new(
                actor_type=ActorType.SYSTEM,
                actor_id=self.name,
                event_type=AuditEventType.ACTION_COMPLETED,
                message=f"notion action completed: {action.type}",
                payload=payload,
            )
        )


def _normalize_target(action: Action) -> str | None:
    if action.type in {"notion.read_page", "notion.create_page", "notion.update_page"}:
        return extract_page_id(action.target) or extract_notion_id(action.target)
    if action.type == "notion.query_database":
        return extract_notion_id(action.target)
    return extract_notion_id(action.target)


def _first_data_source_id(database: Mapping[str, object]) -> str | None:
    raw_sources = database.get("data_sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        return None
    first = raw_sources[0]
    if not isinstance(first, Mapping):
        return None
    raw_id = first.get("id")
    return str(raw_id) if raw_id else None


def _mapping_param(params: Mapping[str, object], key: str) -> Mapping[str, object]:
    raw = params.get(key, {})
    if isinstance(raw, Mapping):
        return cast(Mapping[str, object], raw)
    return {}


def _str_param(params: Mapping[str, object], key: str, default: str) -> str:
    raw = params.get(key, default)
    return raw if isinstance(raw, str) else default


def _result_from_api_error(exc: APIResponseError, notion_id: str) -> ToolResult:
    code = _code_value(exc.code)
    if code in {APIErrorCode.ObjectNotFound.value, APIErrorCode.RestrictedResource.value}:
        return ToolResult(
            success=False,
            detail=_PERMISSION_DETAIL,
            payload={"notion_id": notion_id, "error_code": code},
        )
    return ToolResult(
        success=False,
        detail=f"error Notion {exc.status}: {code}",
        payload={"notion_id": notion_id, "error_code": code, "status": exc.status},
    )


def _code_value(code: object) -> str:
    if isinstance(code, Enum):
        return str(code.value)
    return str(code)
