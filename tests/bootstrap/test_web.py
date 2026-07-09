"""Tests del bridge HTTP local de bootstrap.web."""

import asyncio
import json
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
from bootstrap.config import load_settings
from bootstrap.web import build_web_app
from core.domain.config import WyssSettings
from core.domain.plan import Action, Plan
from core.domain.policy import PolicyDecision
from core.domain.risk import Outcome, RiskLevel
from knowledge.state_store import StateStore
from orchestrator.pending_store import PendingStore

_TOKEN = "token-test"
_AUTH = {"Cookie": f"wyss_token={_TOKEN}"}


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


@pytest.fixture
def app(settings: WyssSettings) -> FastAPI:
    return build_web_app(settings, token=_TOKEN)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
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

    rejected = await client.get("/?token=mal")
    assert rejected.status_code == 401
    assert _json(rejected)["error"] == "no autorizado"


async def test_host_check(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/status", headers={"Host": "evil.com", **_AUTH})

    assert response.status_code == 403
    assert _json(response)["error"] == "host no permitido"


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
