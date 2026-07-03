"""Bridge HTTP local para Wyss: FastAPI como composition root web."""

import json
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from secrets import compare_digest
from typing import Any
from urllib.parse import urlsplit

import httpx
import typer
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from starlette import status

from audit.sqlite_logger import SqliteAuditLogger
from bootstrap.cli import (
    _ACCION_CONFIG,
    _ACCION_INTEGRIDAD,
    _build_embedder,
    _hit_to_json,
    _json_rpc_call,
    _ledger_db_path,
    _now_iso,
    _pending_db_path,
    _socket_path,
    _today_iso,
    _validate_monto,
    build_retrieval,
    query_audit_events,
)
from core.domain import Query, TipoTransaccion, Transaccion
from core.domain.audit import ActorType
from core.domain.config import WyssSettings
from core.domain.errors import AuditIntegrityError, ConfigError, IndexIntegrityError
from core.domain.security import Subject
from knowledge.state_store import BcFreshness, StateStore
from ledger.sqlite_store import SqliteLedgerStore
from orchestrator.pending_store import PendingProposal, PendingStore

_TOKEN_COOKIE = "wyss_token"
_HTTP_422 = 422

type ASGIHandler = Callable[[Request], Awaitable[Response]]


class WebError(Exception):
    """Error HTTP esperado, serializable con el shape estable de la API."""

    def __init__(self, code: int, *, error: str, accion: str) -> None:
        self.code = code
        self.error = error
        self.accion = accion


class AskBody(BaseModel):
    """Body de POST /api/ask."""

    model_config = ConfigDict(extra="forbid")

    instruction: str


class ConfirmBody(BaseModel):
    """Body de POST /api/confirm/{pending_id}."""

    model_config = ConfigDict(extra="forbid")

    approve: bool


class TransaccionBody(BaseModel):
    """Body de POST /api/fin/transaccion."""

    model_config = ConfigDict(extra="forbid")

    tipo: str
    monto: float
    fuente: str | None = None
    categoria: str | None = None
    fecha: str | None = None


def build_web_app(settings: WyssSettings, *, token: str) -> FastAPI:
    """Construye la app HTTP local autenticada para la UI web."""
    web_app = FastAPI()

    @web_app.middleware("http")
    async def local_security_middleware(request: Request, call_next: ASGIHandler) -> Response:
        host = request.headers.get("host", "")
        if not _is_allowed_host(host):
            return _error_response(
                status.HTTP_403_FORBIDDEN,
                error="host no permitido",
                accion="abrí la URL local que imprime wyss web",
            )

        origin = request.headers.get("origin")
        if origin is not None and not _is_allowed_origin(origin):
            return _error_response(
                status.HTTP_403_FORBIDDEN,
                error="origen no permitido",
                accion="usá la interfaz local servida por wyss web",
            )

        auth_response = _authenticate_request(request, token)
        if auth_response is not None:
            return auth_response

        return await call_next(request)

    @web_app.exception_handler(WebError)
    async def web_error_handler(_request: Request, exc: WebError) -> JSONResponse:
        return _error_response(exc.code, error=exc.error, accion=exc.accion)

    @web_app.exception_handler(ConfigError)
    async def config_error_handler(_request: Request, exc: ConfigError) -> JSONResponse:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            error=str(exc),
            accion=_ACCION_CONFIG,
        )

    @web_app.exception_handler(AuditIntegrityError)
    async def audit_integrity_error_handler(
        _request: Request, exc: AuditIntegrityError
    ) -> JSONResponse:
        return _integrity_error_response(exc)

    @web_app.exception_handler(IndexIntegrityError)
    async def index_integrity_error_handler(
        _request: Request, exc: IndexIntegrityError
    ) -> JSONResponse:
        return _integrity_error_response(exc)

    def _integrity_error_response(exc: AuditIntegrityError | IndexIntegrityError) -> JSONResponse:
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            error=str(exc),
            accion=_ACCION_INTEGRIDAD,
        )

    @web_app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, (FileNotFoundError, ConnectionRefusedError, PermissionError)):
            return _daemon_down_response()
        if isinstance(exc, (sqlite3.Error, OSError, RuntimeError, ValueError, KeyError)):
            return _error_response(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                error=str(exc),
                accion="revisá los logs del proceso wyss web",
            )
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            error="error interno",
            accion="revisá los logs del proceso wyss web",
        )

    @web_app.get("/api/status")
    async def api_status() -> dict[str, object]:
        index_db = settings.data_dir / "index.db"
        if not index_db.exists():
            return {"kbs": []}
        store: StateStore | None = None
        try:
            store = StateStore(index_db)
            return {"kbs": [_freshness_to_json(item) for item in store.freshness_by_kb()]}
        finally:
            if store is not None:
                store.close()

    @web_app.get("/api/search")
    async def api_search(q: str, kb: str | None = None, limit: int = 10) -> dict[str, object]:
        if not q:
            raise WebError(
                _HTTP_422,
                error="q es obligatorio",
                accion="enviá una consulta en el parámetro q",
            )
        http_client: httpx.AsyncClient | None = None
        audit: SqliteAuditLogger | None = None
        state_store: StateStore | None = None
        try:
            audit = SqliteAuditLogger(settings.audit_db)
            http_client, embedder = await _build_embedder()
            retrieval, state_store = build_retrieval(settings, audit=audit, embedder=embedder)
            available_kb_ids = state_store.list_kb_ids()
            if kb is not None:
                if kb not in available_kb_ids:
                    raise WebError(
                        status.HTTP_404_NOT_FOUND,
                        error=f"base de conocimiento '{kb}' no encontrada",
                        accion=f"indexala primero: wyss index <ruta> --bc {kb}",
                    )
                kb_ids = frozenset({kb})
            else:
                kb_ids = frozenset(available_kb_ids)
            result = await retrieval.search(
                Query(q, kb_ids, limit),
                Subject(subject_id="owner", subject_type=ActorType.OWNER),
            )
            return {
                "hits": [_hit_to_json(hit) for hit in result.hits],
                "degraded": result.degraded,
                "reason": result.reason or None,
                "freshness": [_freshness_to_json(item) for item in state_store.freshness_by_kb()],
            }
        finally:
            if state_store is not None:
                state_store.close()
            if audit is not None:
                audit.close()
            if http_client is not None:
                await http_client.aclose()

    @web_app.get("/api/fin/resumen")
    async def api_fin_resumen(
        desde: str | None = None, hasta: str | None = None
    ) -> dict[str, object]:
        db_path = _ledger_db_path(settings)
        ventana_desde = desde or _first_day_of_current_month()
        ventana_hasta = hasta or _today_iso()
        if not db_path.exists():
            return _empty_fin_resumen()
        store: SqliteLedgerStore | None = None
        try:
            store = SqliteLedgerStore(db_path)
            ingresos, gastos = store.balance(ventana_desde, ventana_hasta)
            return {
                "ingresos": ingresos,
                "gastos": gastos,
                "superavit": store.surplus(ventana_desde, ventana_hasta),
                "por_categoria": dict(store.query_by_category(ventana_desde, ventana_hasta)),
                "dias_cobertura": store.coverage_days(ventana_desde, ventana_hasta),
            }
        finally:
            if store is not None:
                store.close()

    @web_app.post("/api/fin/transaccion", status_code=status.HTTP_201_CREATED)
    async def api_fin_transaccion(body: TransaccionBody) -> dict[str, object]:
        try:
            _validate_monto(body.monto)
        except typer.Exit as exc:
            raise WebError(
                _HTTP_422,
                error=f"el monto debe ser positivo (recibido {body.monto})",
                accion="reintentá con un monto mayor a 0",
            ) from exc
        tipo = _parse_tipo_transaccion(body.tipo)
        transaccion = Transaccion(
            tipo=tipo,
            monto=body.monto,
            fecha=body.fecha or _today_iso(),
            fuente=body.fuente if tipo == TipoTransaccion.INGRESO else None,
            categoria=body.categoria if tipo == TipoTransaccion.GASTO else None,
            created_at=_now_iso(),
        )
        store: SqliteLedgerStore | None = None
        try:
            store = SqliteLedgerStore(_ledger_db_path(settings))
            store.record(transaccion)
            return {"transaccion": _transaccion_to_json(transaccion)}
        finally:
            if store is not None:
                store.close()

    @web_app.get("/api/audit")
    async def api_audit(since: str | None = None, limit: int = 50) -> dict[str, object]:
        if not settings.audit_db.exists():
            return {"events": []}
        rows = query_audit_events(settings.audit_db, since=since, limit=limit)
        return {
            "events": [
                {
                    "created_at": row.created_at,
                    "actor_id": row.actor_id,
                    "event_type": row.event_type,
                    "message": row.message,
                }
                for row in rows
            ]
        }

    @web_app.get("/api/pending")
    async def api_pending() -> dict[str, object]:
        db_path = _pending_db_path(settings)
        if not db_path.exists():
            return {"pending": []}
        store: PendingStore | None = None
        try:
            store = PendingStore(db_path)
            return {
                "pending": [_pending_to_json(proposal) for proposal in store.load_pending()]
            }
        finally:
            if store is not None:
                store.close()

    @web_app.post("/api/ask")
    async def api_ask(body: AskBody) -> dict[str, Any]:
        try:
            return await _json_rpc_call(
                _socket_path(settings),
                "ask",
                {"instruction": body.instruction},
            )
        except (FileNotFoundError, ConnectionRefusedError, PermissionError) as exc:
            raise WebError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                error="el daemon no está corriendo",
                accion="levantalo con: wyss start",
            ) from exc

    @web_app.post("/api/confirm/{pending_id}")
    async def api_confirm(pending_id: str, body: ConfirmBody) -> dict[str, Any]:
        db_path = _pending_db_path(settings)
        if not db_path.exists():
            raise _pending_not_found(pending_id)
        store: PendingStore | None = None
        try:
            store = PendingStore(db_path)
            proposal = store.load(pending_id)
            if proposal is None:
                raise _pending_not_found(pending_id)
            response = _confirm_response(body.approve, proposal.risk_level)
        finally:
            if store is not None:
                store.close()
        try:
            return await _json_rpc_call(
                _socket_path(settings),
                "confirm",
                {"pending_id": pending_id, "response": response},
            )
        except (FileNotFoundError, ConnectionRefusedError, PermissionError) as exc:
            raise WebError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                error="el daemon no está corriendo",
                accion="levantalo con: wyss start",
            ) from exc

    web_app.mount(
        "/",
        StaticFiles(directory=Path(__file__).parent / "webui_dist", html=True),
        name="webui",
    )
    return web_app


def _error_response(code: int, *, error: str, accion: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"error": error, "accion": accion})


def _daemon_down_response() -> JSONResponse:
    return _error_response(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        error="el daemon no está corriendo",
        accion="levantalo con: wyss start",
    )


def _is_allowed_host(value: str) -> bool:
    if not value:
        return False
    host = value.rsplit("@", maxsplit=1)[-1].split(":", maxsplit=1)[0].lower()
    return host in {"127.0.0.1", "localhost"}


def _is_allowed_origin(value: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}


def _authenticate_request(request: Request, token: str) -> Response | None:
    path = request.url.path
    query_token = request.query_params.get("token")
    if request.method == "GET" and path == "/" and query_token is not None:
        if compare_digest(query_token, token):
            response = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
            response.set_cookie(
                _TOKEN_COOKIE,
                query_token,
                httponly=True,
                samesite="strict",
                path="/",
            )
            return response
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            error="no autorizado",
            accion="abrí la URL con token que imprime wyss web",
        )

    # Cookie obligatoria en TODO path (estáticos incluidos): el mount html=True
    # serviría /index.html sin pasar por el check de "/" si esto fuera selectivo.
    cookie_token = request.cookies.get(_TOKEN_COOKIE, "")
    if not compare_digest(cookie_token, token):
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            error="no autorizado",
            accion="abrí la URL con token que imprime wyss web",
        )
    return None


def _freshness_to_json(item: BcFreshness) -> dict[str, object]:
    return {
        "kb_id": item.kb_id,
        "files": item.total,
        "last_indexed": item.last_indexed_at,
        "embedded": item.embedded,
        "pending": item.pending,
        "failed": item.failed,
    }


def _first_day_of_current_month() -> str:
    return datetime.now(UTC).date().replace(day=1).isoformat()


def _empty_fin_resumen() -> dict[str, object]:
    return {
        "ingresos": 0.0,
        "gastos": 0.0,
        "superavit": 0.0,
        "por_categoria": {},
        "dias_cobertura": 0,
    }


def _parse_tipo_transaccion(value: str) -> TipoTransaccion:
    try:
        return TipoTransaccion(value)
    except ValueError as exc:
        raise WebError(
            _HTTP_422,
            error=f"tipo de transacción desconocido: {value}",
            accion="usá tipo ingreso o gasto",
        ) from exc


def _transaccion_to_json(transaccion: Transaccion) -> dict[str, object]:
    return {
        "tipo": transaccion.tipo.value,
        "monto": transaccion.monto,
        "fecha": transaccion.fecha,
        "fuente": transaccion.fuente,
        "categoria": transaccion.categoria,
        "created_at": transaccion.created_at,
    }


def _pending_to_json(proposal: PendingProposal) -> dict[str, object]:
    return {
        "id": proposal.id,
        "task_id": proposal.task_id,
        "plan": json.loads(proposal.plan_json),
        "risk_level": proposal.risk_level,
        "outcome": proposal.outcome,
        "created_at": proposal.created_at,
        "expires_at": proposal.expires_at,
    }


def _pending_not_found(pending_id: str) -> WebError:
    return WebError(
        status.HTTP_404_NOT_FOUND,
        error=f"no hay propuesta pendiente con id '{pending_id}'",
        accion='el id aparece en la respuesta de: wyss ask "<instrucción>"',
    )


def _confirm_response(approve: bool, risk_level: str) -> str:
    if not approve:
        return ""
    if risk_level == "C":
        return "CONFIRMAR"
    return "s"
