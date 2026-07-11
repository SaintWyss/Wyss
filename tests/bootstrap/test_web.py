"""Tests del bridge HTTP local de bootstrap.web."""

import asyncio
import json
import logging
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from httpx import Response

import bootstrap.web as web_mod
from bootstrap.cli import _json_rpc_call
from bootstrap.config import WyssSettings, load_settings
from bootstrap.web import build_web_app
from core.domain.plan import Action, Plan
from core.domain.policy import PolicyDecision
from core.domain.risk import Outcome, RiskLevel
from knowledge.state_store import StateStore
from orchestrator.pending_store import PendingStore

_TOKEN = "token-test"
_AUTH = {"Cookie": f"wyss_token={_TOKEN}"}
_INTAKE_TOKEN = "intake-token-test-abcdefghijklmnopqrstuvwxyz"


@pytest.fixture
def settings(tmp_path: Path) -> WyssSettings:
    config = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config.write_text(
        f'data_dir = "{data_dir.as_posix()}"\n'
        f'audit_db = "{(data_dir / "audit.db").as_posix()}"\n',
        encoding="utf-8",
    )
    return load_settings(config)


def _settings_with_intake(tmp_path: Path, *, max_per_minute: int = 30) -> WyssSettings:
    config = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config.write_text(
        f'data_dir = "{data_dir.as_posix()}"\n'
        f'audit_db = "{(data_dir / "audit.db").as_posix()}"\n'
        "[intake]\n"
        "enabled = true\n"
        f"max_per_minute = {max_per_minute}\n",
        encoding="utf-8",
    )
    return load_settings(config)


@pytest.fixture
def app(settings: WyssSettings) -> FastAPI:
    return build_web_app(settings, token=_TOKEN)


@pytest.fixture
def intake_app(tmp_path: Path) -> FastAPI:
    return build_web_app(
        _settings_with_intake(tmp_path),
        token=_TOKEN,
        intake_token=_INTAKE_TOKEN,
    )


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1",
    ) as async_client:
        yield async_client


@pytest.fixture
async def intake_client(intake_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=intake_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1",
    ) as async_client:
        yield async_client


def _json(response: Response) -> dict[str, Any]:
    data = response.json()
    assert isinstance(data, dict)
    return cast(dict[str, Any], data)


def _plan(task_id: str = "task-web") -> Plan:
    return Plan(
        task_id=task_id,
        summary="mover archivo",
        steps=(Action(type="file.move", target="/tmp/origen.txt"),),
        rationale="test",
    )


def _save_pending(settings: WyssSettings, level: RiskLevel = RiskLevel.C) -> str:
    db_path = settings.data_dir / "pending.db"
    store = PendingStore(db_path)
    try:
        decision = PolicyDecision(
            task_id="task-web",
            risk_level=level,
            outcome=Outcome.CONFIRM_STRONG if level == RiskLevel.C else Outcome.CONFIRM_SIMPLE,
        )
        return store.save(_plan(), decision, ttl_seconds=60)
    finally:
        store.close()


async def test_auth_flow(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/status")).status_code == 401
    assert (await client.get("/api/status", headers=_AUTH)).status_code == 200

    redirect = await client.get("/?token=token-test", follow_redirects=False)
    assert redirect.status_code == 302
    assert "wyss_token=token-test" in redirect.headers["set-cookie"]
    assert redirect.headers["location"] == "/"
    # Cookie persistente (no de sesión): el teléfono no pierde el pairing al
    # cerrar el browser. 30 días.
    assert "max-age=2592000" in redirect.headers["set-cookie"].lower()

    rejected = await client.get("/?token=mal")
    assert rejected.status_code == 401
    assert _json(rejected)["error"] == "no autorizado"


async def test_host_check(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/status", headers={"Host": "evil.com", **_AUTH})

    assert response.status_code == 403
    assert _json(response)["error"] == "host no permitido"


# ---------------------------------------------------------------------------
# PR-14 (smoke físico): Origin "null" de browsers reales — Chrome Android con
# cert self-signed aceptado serializa Origin: null en POSTs same-origin.
# ---------------------------------------------------------------------------


@pytest.fixture
def _fake_rpc(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_rpc(
        _socket_path: Path, _method: str, _params: dict[str, object]
    ) -> dict[str, Any]:
        return {"ok": True}

    monkeypatch.setattr(web_mod, "_json_rpc_call", fake_rpc)


async def test_origin_null_with_sec_fetch_same_origin_allowed(
    client: httpx.AsyncClient, _fake_rpc: None
) -> None:
    """El caso del teléfono real: Origin null + Sec-Fetch-Site same-origin pasa."""
    response = await client.post(
        "/api/ask",
        json={"instruction": "hola"},
        headers={**_AUTH, "Origin": "null", "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 200


async def test_origin_null_without_sec_fetch_rejected(
    client: httpx.AsyncClient, _fake_rpc: None
) -> None:
    """Origin null sin respaldo de Sec-Fetch-Site (iframe sandboxeado viejo) → 403."""
    response = await client.post(
        "/api/ask",
        json={"instruction": "hola"},
        headers={**_AUTH, "Origin": "null"},
    )
    assert response.status_code == 403


async def test_origin_null_cross_site_rejected(
    client: httpx.AsyncClient, _fake_rpc: None
) -> None:
    """Origin null desde otro sitio (Sec-Fetch-Site: cross-site) → 403."""
    response = await client.post(
        "/api/ask",
        json={"instruction": "hola"},
        headers={**_AUTH, "Origin": "null", "Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 403


async def test_evil_origin_rejected_even_with_sec_fetch(
    client: httpx.AsyncClient, _fake_rpc: None
) -> None:
    """Un Origin explícito inválido manda SIEMPRE, aunque Sec-Fetch mienta."""
    response = await client.post(
        "/api/ask",
        json={"instruction": "hola"},
        headers={**_AUTH, "Origin": "http://evil.com", "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 403


async def test_rejections_are_logged(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """El middleware ya no es mudo: los 403 quedan en el log con el motivo."""
    import logging

    with caplog.at_level(logging.WARNING, logger="wyss.web"):
        await client.get("/api/status", headers={"Host": "evil.com", **_AUTH})

    assert any("host no permitido" in rec.getMessage() for rec in caplog.records)


# ---------------------------------------------------------------------------
# PR-10: modo TLS — cookie Secure y Origin https (un solo esquema, el servido)
# ---------------------------------------------------------------------------


@pytest.fixture
def tls_app(settings: WyssSettings) -> FastAPI:
    return build_web_app(settings, token=_TOKEN, tls=True)


@pytest.fixture
async def tls_client(tls_app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=tls_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="https://127.0.0.1",
    ) as async_client:
        yield async_client


async def test_tls_cookie_is_secure(tls_client: httpx.AsyncClient) -> None:
    redirect = await tls_client.get("/?token=token-test", follow_redirects=False)

    assert redirect.status_code == 302
    set_cookie = redirect.headers["set-cookie"]
    assert "wyss_token=token-test" in set_cookie
    assert "secure" in set_cookie.lower()  # el token jamás viaja por http plano


async def test_tls_origin_scheme(tls_client: httpx.AsyncClient) -> None:
    """Con TLS el Origin permitido es https://<host>; http:// deja de aceptarse."""
    accepted = await tls_client.get(
        "/api/status", headers={**_AUTH, "Origin": "https://127.0.0.1"}
    )
    assert accepted.status_code == 200

    downgraded = await tls_client.get(
        "/api/status", headers={**_AUTH, "Origin": "http://127.0.0.1"}
    )
    assert downgraded.status_code == 403


async def test_without_tls_cookie_not_secure(client: httpx.AsyncClient) -> None:
    """Sin --tls (localhost puro) la cookie no lleva Secure — si lo llevara, el
    browser la descartaría sobre http://127.0.0.1 y el pairing local moriría."""
    redirect = await client.get("/?token=token-test", follow_redirects=False)

    assert redirect.status_code == 302
    assert "secure" not in redirect.headers["set-cookie"].lower()


async def test_origin_check(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_rpc(
        _socket_path: Path,
        _method: str,
        _params: dict[str, object],
    ) -> dict[str, Any]:
        return {"ok": True}

    monkeypatch.setattr(web_mod, "_json_rpc_call", fake_rpc)

    rejected = await client.post(
        "/api/ask",
        json={"instruction": "hola"},
        headers={**_AUTH, "Origin": "http://evil.com"},
    )
    assert rejected.status_code == 403

    accepted = await client.post(
        "/api/ask",
        json={"instruction": "hola"},
        headers={**_AUTH, "Origin": "http://127.0.0.1"},
    )
    assert accepted.status_code == 200
    assert _json(accepted) == {"ok": True}


async def test_empty_states_do_not_create_databases(
    client: httpx.AsyncClient,
    settings: WyssSettings,
) -> None:
    assert (await client.get("/api/status", headers=_AUTH)).json() == {"kbs": []}
    assert (await client.get("/api/audit", headers=_AUTH)).json() == {"events": []}
    assert (await client.get("/api/pending", headers=_AUTH)).json() == {"pending": []}
    assert (await client.get("/api/fin/resumen", headers=_AUTH)).json() == {
        "ingresos": 0.0,
        "gastos": 0.0,
        "superavit": 0.0,
        "por_categoria": {},
        "dias_cobertura": 0,
    }

    assert not (settings.data_dir / "index.db").exists()
    assert not settings.audit_db.exists()
    assert not (settings.data_dir / "pending.db").exists()
    assert not (settings.data_dir / "ledger.db").exists()


async def test_fin_round_trip(client: httpx.AsyncClient) -> None:
    ingreso = await client.post(
        "/api/fin/transaccion",
        json={
            "tipo": "ingreso",
            "monto": 1000.0,
            "fuente": "sueldo",
            "fecha": "2026-07-03",
        },
        headers=_AUTH,
    )
    gasto = await client.post(
        "/api/fin/transaccion",
        json={
            "tipo": "gasto",
            "monto": 400.0,
            "categoria": "comida",
            "fecha": "2026-07-03",
        },
        headers=_AUTH,
    )

    assert ingreso.status_code == 201
    assert gasto.status_code == 201

    response = await client.get(
        "/api/fin/resumen?desde=2026-07-01&hasta=2026-07-31",
        headers=_AUTH,
    )
    data = _json(response)

    assert data["ingresos"] == 1000.0
    assert data["gastos"] == 400.0
    assert data["superavit"] == 600.0
    assert data["por_categoria"] == {"comida": 400.0}


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        ({"tipo": "ingreso", "monto": 0.0, "fuente": "sueldo"}, "el monto debe ser positivo"),
        ({"tipo": "otro", "monto": 10.0}, "tipo de transacción desconocido"),
    ],
)
async def test_fin_validation(
    client: httpx.AsyncClient,
    payload: dict[str, object],
    expected_error: str,
) -> None:
    response = await client.post("/api/fin/transaccion", json=payload, headers=_AUTH)

    assert response.status_code == 422
    assert str(_json(response)["error"]).startswith(expected_error)


async def test_search_unknown_kb(
    client: httpx.AsyncClient,
    settings: WyssSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with StateStore(settings.data_dir / "index.db"):
        pass

    class FakeRetrieval:
        async def search(self, _query: object, _subject: object) -> object:
            raise AssertionError("no debe buscar si la BC no existe")

    async def fake_embedder() -> tuple[httpx.AsyncClient, None]:
        return httpx.AsyncClient(), None

    def fake_build_retrieval(
        settings_arg: WyssSettings,
        *,
        audit: object,
        embedder: object,
    ) -> tuple[FakeRetrieval, StateStore]:
        assert settings_arg == settings
        assert audit is not None
        assert embedder is None
        return FakeRetrieval(), StateStore(settings.data_dir / "index.db")

    monkeypatch.setattr(web_mod, "_build_embedder", fake_embedder)
    monkeypatch.setattr(web_mod, "build_retrieval", fake_build_retrieval)

    response = await client.get("/api/search?q=hola&kb=no-existe", headers=_AUTH)

    assert response.status_code == 404
    assert _json(response)["error"] == "base de conocimiento 'no-existe' no encontrada"


async def test_ask_daemon_down(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/ask", json={"instruction": "hola"}, headers=_AUTH)

    assert response.status_code == 503
    assert response.json() == {
        "error": "el daemon no está corriendo",
        "accion": "levantalo con: wyss start",
    }


async def test_ask_and_confirm_use_daemon_contract(
    client: httpx.AsyncClient,
    settings: WyssSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pending_id = _save_pending(settings, RiskLevel.C)
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_rpc(
        _socket_path: Path,
        method: str,
        params: dict[str, object],
    ) -> dict[str, Any]:
        calls.append((method, params))
        return {"method": method, "params": params}

    monkeypatch.setattr(web_mod, "_json_rpc_call", fake_rpc)

    ask = await client.post("/api/ask", json={"instruction": "hola"}, headers=_AUTH)
    approved = await client.post(
        f"/api/confirm/{pending_id}",
        json={"approve": True},
        headers=_AUTH,
    )
    rejected = await client.post(
        f"/api/confirm/{pending_id}",
        json={"approve": False},
        headers=_AUTH,
    )

    assert ask.status_code == 200
    assert approved.status_code == 200
    assert rejected.status_code == 200
    assert calls == [
        ("ask", {"instruction": "hola"}),
        ("confirm", {"pending_id": pending_id, "response": "CONFIRMAR"}),
        ("confirm", {"pending_id": pending_id, "response": ""}),
    ]


async def test_intake_valid_bearer_calls_daemon_contract(
    intake_client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    async def fake_rpc(
        _socket_path: Path,
        method: str,
        params: dict[str, object],
    ) -> dict[str, Any]:
        calls.append((method, params))
        return {"outcome": "pending", "pending_id": "p1", "risk_level": "B"}

    monkeypatch.setattr(web_mod, "_json_rpc_call", fake_rpc)

    response = await intake_client.post(
        "/api/intake",
        json={"instruction": "crear propuesta"},
        headers={"Authorization": f"Bearer {_INTAKE_TOKEN}"},
    )

    assert response.status_code == 200
    assert _json(response)["outcome"] == "pending"
    assert calls == [("intake.propose", {"instruction": "crear propuesta"})]


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer token-incorrecto"}])
async def test_intake_requires_valid_bearer_and_never_logs_token(
    intake_client: httpx.AsyncClient,
    caplog: pytest.LogCaptureFixture,
    headers: dict[str, str],
) -> None:
    with caplog.at_level(logging.WARNING, logger="wyss.web"):
        response = await intake_client.post(
            "/api/intake",
            json={"instruction": "crear propuesta"},
            headers=headers,
        )

    assert response.status_code == 401
    assert _json(response)["error"] == "no autorizado"
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert _INTAKE_TOKEN not in messages
    assert "token-incorrecto" not in messages


async def test_intake_disabled_returns_404_even_with_bearer(
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        "/api/intake",
        json={"instruction": "crear propuesta"},
        headers={"Authorization": f"Bearer {_INTAKE_TOKEN}"},
    )

    assert response.status_code == 404
    assert _json(response)["error"] == "intake deshabilitado"


async def test_intake_does_not_accept_pairing_cookie(
    intake_client: httpx.AsyncClient,
) -> None:
    response = await intake_client.post(
        "/api/intake",
        json={"instruction": "crear propuesta"},
        headers=_AUTH,
    )

    assert response.status_code == 401


async def test_cookie_exemption_is_only_for_intake(
    intake_client: httpx.AsyncClient,
) -> None:
    response = await intake_client.get("/api/status")

    assert response.status_code == 401


async def test_intake_rate_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = build_web_app(
        _settings_with_intake(tmp_path, max_per_minute=2),
        token=_TOKEN,
        intake_token=_INTAKE_TOKEN,
    )

    async def fake_rpc(
        _socket_path: Path,
        _method: str,
        _params: dict[str, object],
    ) -> dict[str, Any]:
        return {"outcome": "pending", "pending_id": "p1", "risk_level": "B"}

    monkeypatch.setattr(web_mod, "_json_rpc_call", fake_rpc)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://127.0.0.1",
    ) as client:
        headers = {"Authorization": f"Bearer {_INTAKE_TOKEN}"}
        assert (
            await client.post("/api/intake", json={"instruction": "uno"}, headers=headers)
        ).status_code == 200
        assert (
            await client.post("/api/intake", json={"instruction": "dos"}, headers=headers)
        ).status_code == 200
        limited = await client.post(
            "/api/intake", json={"instruction": "tres"}, headers=headers
        )

    assert limited.status_code == 429
    assert _json(limited)["error"] == "rate limit excedido"


@pytest.mark.parametrize(
    "payload",
    [
        {"instruction": "x" * 2001},
        {},
        {"instruction": "x", "extra": True},
    ],
)
async def test_intake_body_validation(
    intake_client: httpx.AsyncClient,
    payload: dict[str, object],
) -> None:
    response = await intake_client.post(
        "/api/intake",
        json=payload,
        headers={"Authorization": f"Bearer {_INTAKE_TOKEN}"},
    )

    assert response.status_code == 422


async def test_confirm_unknown_pending(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/confirm/nope", json={"approve": True}, headers=_AUTH)

    assert response.status_code == 404
    assert _json(response)["error"] == "no hay propuesta pendiente con id 'nope'"


@pytest.mark.asyncio
async def test_json_rpc_call_real_unix_socket(tmp_path: Path) -> None:
    captured: list[dict[str, Any]] = []
    socket_path = tmp_path / "wyss.sock"

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        raw = await reader.readline()
        request = json.loads(raw)
        assert isinstance(request, dict)
        captured.append(cast(dict[str, Any], request))
        response = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        writer.write(json.dumps(response).encode() + b"\n")
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    try:
        server = await asyncio.start_unix_server(handle, path=socket_path)
    except PermissionError as exc:
        pytest.skip(f"el sandbox no permite sockets Unix: {exc}")
    try:
        result = await _json_rpc_call(socket_path, "ask", {"instruction": "hola"})
    finally:
        server.close()
        await server.wait_closed()

    assert result == {"ok": True}
    assert captured[0]["method"] == "ask"
    assert captured[0]["params"] == {"instruction": "hola"}


@pytest.mark.asyncio
async def test_daemon_endpoint(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # daemon caído (socket inexistente en settings de tmp_path) → alive false, 200
    down = await client.get("/api/daemon", headers=_AUTH)
    assert down.status_code == 200
    assert _json(down) == {"alive": False}

    async def fake_rpc(
        _socket: Path, method: str, _params: dict[str, object]
    ) -> dict[str, Any]:
        assert method == "status"
        return {"uptime": 1}

    monkeypatch.setattr(web_mod, "_json_rpc_call", fake_rpc)
    up = await client.get("/api/daemon", headers=_AUTH)
    assert up.status_code == 200
    assert _json(up) == {"alive": True}


@pytest.mark.asyncio
async def test_borjes_launcher(
    client: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # script inexistente → 404 accionable, sin spawn
    monkeypatch.setattr(web_mod, "_BORJES_TOGGLE", tmp_path / "no-existe")
    missing = await client.post("/api/apps/borjes", headers=_AUTH)
    assert missing.status_code == 404
    assert "accion" in _json(missing)

    # script presente → Popen con ruta fija, sin input del cliente
    script = tmp_path / "borjes-toggle"
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(web_mod, "_BORJES_TOGGLE", script)
    spawned: list[list[str]] = []

    def fake_popen(cmd: list[str], **kwargs: object) -> object:
        spawned.append(cmd)
        assert kwargs.get("start_new_session") is True
        return object()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    ok = await client.post("/api/apps/borjes", headers=_AUTH)
    assert ok.status_code == 200
    assert _json(ok) == {"lanzado": True}
    assert spawned == [[str(script)]]


# ---------------------------------------------------------------------------
# Modo LAN (mobile bridge): allowlist exacta de hosts, jamás wildcard
# ---------------------------------------------------------------------------

_LAN_IP = "192.168.100.5"


@pytest.fixture
async def lan_client(settings: WyssSettings) -> AsyncIterator[httpx.AsyncClient]:
    lan_app = build_web_app(settings, token=_TOKEN, lan_hosts=frozenset({_LAN_IP}))
    transport = httpx.ASGITransport(app=lan_app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=f"http://{_LAN_IP}",
    ) as async_client:
        yield async_client


async def test_lan_host_permitido_con_cookie(lan_client: httpx.AsyncClient) -> None:
    """El host LAN declarado accede con cookie; el flujo de pairing por token funciona."""
    assert (await lan_client.get("/api/status", headers=_AUTH)).status_code == 200

    redirect = await lan_client.get(f"/?token={_TOKEN}", follow_redirects=False)
    assert redirect.status_code == 302
    assert f"wyss_token={_TOKEN}" in redirect.headers["set-cookie"]


async def test_lan_no_autenticado_401(lan_client: httpx.AsyncClient) -> None:
    """LAN habilitada NO implica ejecución sin auth: sin cookie/token → 401 en todo path."""
    assert (await lan_client.get("/api/status")).status_code == 401
    assert (
        await lan_client.post("/api/ask", json={"instruction": "hola"})
    ).status_code == 401


async def test_lan_host_ajeno_403(lan_client: httpx.AsyncClient) -> None:
    """La allowlist es exacta: otro host (DNS rebinding) sigue en 403 aun autenticado."""
    response = await lan_client.get(
        "/api/status", headers={"Host": "evil.com", **_AUTH}
    )
    assert response.status_code == 403
    assert _json(response)["error"] == "host no permitido"


async def test_lan_origin_permitido_y_ajeno(lan_client: httpx.AsyncClient) -> None:
    """Origin del propio host LAN pasa; un Origin ajeno se corta en 403."""
    ok = await lan_client.get(
        "/api/status", headers={"Origin": f"http://{_LAN_IP}:7777", **_AUTH}
    )
    assert ok.status_code == 200

    rejected = await lan_client.get(
        "/api/status", headers={"Origin": "http://evil.com", **_AUTH}
    )
    assert rejected.status_code == 403
    assert _json(rejected)["error"] == "origen no permitido"


async def test_default_sigue_solo_localhost(client: httpx.AsyncClient) -> None:
    """Sin lan_hosts (default), el host LAN NO está permitido: LAN es opt-in."""
    response = await client.get(
        "/api/status", headers={"Host": f"{_LAN_IP}:7777", **_AUTH}
    )
    assert response.status_code == 403


async def test_intake_rpc_error_es_legible(
    intake_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Smoke fase 13: un error JSON-RPC del daemon (plan LLM inválido) salía
    como 500 con traceback — debe ser 502 legible."""
    async def fake_rpc(
        _socket_path: Path, _method: str, _params: dict[str, object]
    ) -> dict[str, Any]:
        raise RuntimeError("plan del LLM inválido: steps inválidos")

    monkeypatch.setattr(web_mod, "_json_rpc_call", fake_rpc)
    response = await intake_client.post(
        "/api/intake",
        json={"instruction": "ping"},
        headers={"Authorization": f"Bearer {_INTAKE_TOKEN}"},
    )

    assert response.status_code == 502
    assert "plan del LLM inválido" in _json(response)["error"]
