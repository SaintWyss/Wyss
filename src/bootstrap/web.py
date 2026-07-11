"""Bridge HTTP local para Wyss: FastAPI como composition root web."""

import json
import logging
import os
import sqlite3
import subprocess
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from secrets import compare_digest
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import httpx
import typer
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
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
from bootstrap.config import WyssSettings
from core.domain import Query, TipoTransaccion, Transaccion
from core.domain.audit import ActorType
from core.domain.errors import AuditIntegrityError, ConfigError, IndexIntegrityError
from core.domain.security import Subject
from knowledge.state_store import BcFreshness, StateStore
from ledger.sqlite_store import SqliteLedgerStore
from orchestrator.pending_store import PendingProposal, PendingStore

_TOKEN_COOKIE = "wyss_token"
# Cookie persistente: sin max_age era de sesión y el teléfono perdía el pairing
# al cerrar el browser. 30 días = re-parear una vez al mes, no una vez por día.
_TOKEN_COOKIE_MAX_AGE = 30 * 24 * 3600
_HTTP_422 = 422

# Rechazos del middleware van al log (visible con el log_level=warning de uvicorn):
# sin esto el server es mudo ante un 403/401 y el teléfono es indiagnosticable.
_LOG = logging.getLogger("wyss.web")

# Lanzador de apps de escritorio: SOLO rutas fijas, jamás input del cliente.
# borjes-toggle maneja running/no-running (SIGUSR1 o launch+reveal).
_BORJES_TOGGLE = Path.home() / ".local" / "bin" / "borjes-toggle"

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


class IntakeBody(BaseModel):
    """Body de POST /api/intake."""

    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(min_length=1, max_length=2000)


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


def build_web_app(
    settings: WyssSettings,
    *,
    token: str,
    intake_token: str | None = None,
    lan_hosts: frozenset[str] = frozenset(),
    tls: bool = False,
) -> FastAPI:
    """Construye la app HTTP local autenticada para la UI web.

    `lan_hosts` extiende la allowlist de Host/Origin SOLO a los hosts exactos
    pasados (el IP LAN detectado por `wyss web --lan`). Nunca es un wildcard:
    un Host ajeno sigue en 403 aunque el server esté bindeado a 0.0.0.0
    (mitiga DNS rebinding). La autenticación por token/cookie no cambia.

    Con `tls=True` (PR-10) el server se sirve por HTTPS: el Origin permitido pasa
    a ser `https://` (el `http://` deja de aceptarse — un solo esquema, el que se
    sirve) y la cookie del token lleva el flag `Secure`.
    """
    web_app = FastAPI()
    allowed_hosts = frozenset({"127.0.0.1", "localhost"} | lan_hosts)
    allowed_scheme = "https" if tls else "http"
    intake_limiter = _IntakeRateLimiter(settings.intake.max_per_minute)

    @web_app.middleware("http")
    async def local_security_middleware(request: Request, call_next: ASGIHandler) -> Response:
        host = request.headers.get("host", "")
        if not _is_allowed_host(host, allowed_hosts):
            _LOG.warning(
                "403 host no permitido: Host=%r (permitidos: %s) en %s %s",
                host, sorted(allowed_hosts), request.method, request.url.path,
            )
            return _error_response(
                status.HTTP_403_FORBIDDEN,
                error="host no permitido",
                accion="abrí la URL local que imprime wyss web",
            )

        origin = request.headers.get("origin")
        sec_fetch_site = request.headers.get("sec-fetch-site", "")
        if not _origin_allowed(origin, sec_fetch_site, allowed_hosts, allowed_scheme):
            _LOG.warning(
                "403 origen no permitido: Origin=%r Sec-Fetch-Site=%r "
                "(esquema esperado %s, hosts: %s) en %s %s",
                origin, sec_fetch_site, allowed_scheme, sorted(allowed_hosts),
                request.method, request.url.path,
            )
            return _error_response(
                status.HTTP_403_FORBIDDEN,
                error="origen no permitido",
                accion="usá la interfaz local servida por wyss web",
            )

        if request.url.path == "/api/intake":
            # Única exención de cookie: n8n no tiene cookie jar y usa bearer dedicado.
            auth_response = _authenticate_intake(
                request,
                intake_token=intake_token,
                enabled=settings.intake.enabled,
                limiter=intake_limiter,
            )
            if auth_response is not None:
                return auth_response
            return await call_next(request)

        auth_response = _authenticate_request(request, token, secure_cookie=tls)
        if auth_response is not None:
            # jamás loguear el token/cookie: solo el hecho del rechazo
            if auth_response.status_code == status.HTTP_401_UNAUTHORIZED:
                _LOG.warning(
                    "401 sin token válido en %s %s (¿cookie perdida o server "
                    "reiniciado con token nuevo?)",
                    request.method, request.url.path,
                )
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

    @web_app.post("/api/apps/borjes")
    async def api_borjes() -> dict[str, object]:
        if not _BORJES_TOGGLE.exists():
            raise WebError(
                status.HTTP_404_NOT_FOUND,
                error="borjes-toggle no está instalado",
                accion=f"esperado en {_BORJES_TOGGLE}",
            )
        env = dict(os.environ)
        env.setdefault("DISPLAY", ":0")
        subprocess.Popen(  # ruta fija, sin input del cliente
            [str(_BORJES_TOGGLE)],
            env=env,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"lanzado": True}

    @web_app.get("/api/daemon")
    async def api_daemon() -> dict[str, object]:
        try:
            await _json_rpc_call(_socket_path(settings), "status", {})
        except (FileNotFoundError, ConnectionRefusedError, PermissionError, RuntimeError):
            # el strip de la UI renderiza estado, no error: 200 con alive=false
            return {"alive": False}
        return {"alive": True}

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

    @web_app.post("/api/intake")
    async def api_intake(body: IntakeBody) -> dict[str, Any]:
        try:
            return await _json_rpc_call(
                _socket_path(settings),
                "intake.propose",
                {"instruction": body.instruction},
            )
        except (FileNotFoundError, ConnectionRefusedError, PermissionError) as exc:
            raise WebError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                error="el daemon no está corriendo",
                accion="levantalo con: wyss start",
            ) from exc
        except RuntimeError as exc:
            # error JSON-RPC del daemon (p.ej. plan del LLM inválido): respuesta
            # legible para el workflow, no un 500 con traceback
            raise WebError(
                status.HTTP_502_BAD_GATEWAY,
                error=f"el daemon rechazó la propuesta: {exc}",
                accion="revisá la instruction o reintentá",
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


def _is_allowed_host(value: str, allowed: frozenset[str]) -> bool:
    if not value:
        return False
    host = value.rsplit("@", maxsplit=1)[-1].split(":", maxsplit=1)[0].lower()
    return host in allowed


def _is_allowed_origin(value: str, allowed: frozenset[str], scheme: str) -> bool:
    parsed = urlsplit(value)
    return parsed.scheme == scheme and parsed.hostname in allowed


def _origin_allowed(
    origin: str | None, sec_fetch_site: str, allowed: frozenset[str], scheme: str
) -> bool:
    """Política de Origin del bridge.

    - Sin header Origin → permitido (los GET same-origin no lo mandan; la capa de
      auth es la cookie SameSite=Strict, que jamás viaja cross-site).
    - Origin presente → debe matchear esquema servido + host de la allowlist.
    - Origin literal "null": los browsers reales (Chrome Android con certificado
      self-signed aceptado, WebViews) lo serializan así incluso en POSTs
      same-origin — el smoke físico del teléfono murió acá. Se acepta SOLO si
      `Sec-Fetch-Site: same-origin` lo respalda: es un header prohibido que el
      JS de un atacante no puede setear. Un iframe sandboxeado o un form
      cross-site también mandan Origin null, pero llegan con Sec-Fetch-Site
      cross-site/nested → 403 (y además sin la cookie Strict → 401 antes de
      tocar nada). Esto NO relaja el caso cross-site.
    """
    if origin is None:
        return True
    if _is_allowed_origin(origin, allowed, scheme):
        return True
    return origin == "null" and sec_fetch_site == "same-origin"


def _authenticate_request(
    request: Request, token: str, *, secure_cookie: bool = False
) -> Response | None:
    path = request.url.path
    query_token = request.query_params.get("token")
    if request.method == "GET" and path == "/" and query_token is not None:
        if compare_digest(query_token, token):
            response = RedirectResponse("/", status_code=status.HTTP_302_FOUND)
            response.set_cookie(
                _TOKEN_COOKIE,
                query_token,
                max_age=_TOKEN_COOKIE_MAX_AGE,
                httponly=True,
                samesite="strict",
                path="/",
                secure=secure_cookie,
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


class _IntakeRateLimiter:
    def __init__(self, max_per_minute: int) -> None:
        self._max_per_minute = max_per_minute
        self._hits: deque[float] = deque()

    def allow(self) -> bool:
        now = monotonic()
        window_start = now - 60.0
        while self._hits and self._hits[0] <= window_start:
            self._hits.popleft()
        if len(self._hits) >= self._max_per_minute:
            return False
        self._hits.append(now)
        return True


def _authenticate_intake(
    request: Request,
    *,
    intake_token: str | None,
    enabled: bool,
    limiter: _IntakeRateLimiter,
) -> Response | None:
    if not enabled or intake_token is None:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            error="intake deshabilitado",
            accion="habilitá [intake].enabled en config.toml",
        )

    authorization = request.headers.get("authorization", "")
    prefix = "Bearer "
    presented = authorization.removeprefix(prefix) if authorization.startswith(prefix) else ""
    if not presented or not compare_digest(presented, intake_token):
        _LOG.warning(
            "401 bearer de intake inválido en %s %s",
            request.method,
            request.url.path,
        )
        return _error_response(
            status.HTTP_401_UNAUTHORIZED,
            error="no autorizado",
            accion="enviá Authorization: Bearer <token de data/intake_token>",
        )

    if not limiter.allow():
        _LOG.warning(
            "429 rate limit de intake excedido en %s %s",
            request.method,
            request.url.path,
        )
        return _error_response(
            status.HTTP_429_TOO_MANY_REQUESTS,
            error="rate limit excedido",
            accion="reintentá más tarde o ajustá [intake].max_per_minute",
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
