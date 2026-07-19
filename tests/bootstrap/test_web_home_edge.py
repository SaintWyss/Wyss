"""Tests de la superficie bearer del Home Edge en bootstrap.web."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from bootstrap.config import WyssSettings, load_settings
from bootstrap.web import build_web_app
from home.reminder_store import ReminderStore
from home.timer_store import TimerStore

_TOKEN = "token-test"
_EDGE_TOKEN = "home-edge-token-test-abcdefghijklmnopqrstuvwxyz"
_EDGE_AUTH = {"Authorization": f"Bearer {_EDGE_TOKEN}"}
_TZ = "America/Argentina/Cordoba"


@pytest.fixture
def settings(tmp_path: Path) -> WyssSettings:
    config = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config.write_text(
        f'data_dir = "{data_dir}"\naudit_db = "{data_dir}/audit.db"\n',
        encoding="utf-8",
    )
    return load_settings(config)


@pytest.fixture
def app(settings: WyssSettings) -> FastAPI:
    return build_web_app(settings, token=_TOKEN, home_edge_token=_EDGE_TOKEN)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as async_client:
        yield async_client


def _payload(response: httpx.Response) -> dict[str, Any]:
    decoded = response.json()
    assert isinstance(decoded, dict)
    return decoded


async def test_home_paths_reject_cookie_auth(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/home/timers", headers={"Cookie": f"wyss_token={_TOKEN}"})
    assert response.status_code == 401


async def test_home_paths_reject_wrong_bearer(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/home/timers", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


async def test_home_disabled_is_404(settings: WyssSettings) -> None:
    app = build_web_app(settings, token=_TOKEN)  # sin home_edge_token
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
        response = await client.get("/api/home/timers", headers=_EDGE_AUTH)
    assert response.status_code == 404


async def test_reminders_contract_shape(client: httpx.AsyncClient, settings: WyssSettings) -> None:
    with ReminderStore(settings.data_dir / "reminders.db") as store:
        store.add(text="regar", due_at="2026-07-20T09:00:00-03:00", timezone=_TZ)
    response = await client.get("/api/home/reminders", params={"timezone": _TZ}, headers=_EDGE_AUTH)
    assert response.status_code == 200
    payload = _payload(response)
    assert set(payload) == {"revision", "reminders"}  # el Edge exige exactamente esto
    assert isinstance(payload["revision"], int) and payload["revision"] > 0
    (reminder,) = payload["reminders"]
    assert reminder["timezone"] == _TZ
    assert reminder["status"] == "active"


async def test_reminders_requires_timezone(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/home/reminders", headers=_EDGE_AUTH)
    assert response.status_code == 422  # FastAPI: query param obligatorio


async def test_timers_contract_shape(client: httpx.AsyncClient, settings: WyssSettings) -> None:
    with TimerStore(settings.data_dir / "timers.db") as store:
        store.start(label="pasta", duration_seconds=600)
    response = await client.get("/api/home/timers", headers=_EDGE_AUTH)
    assert response.status_code == 200
    payload = _payload(response)
    assert set(payload) == {"revision", "timers"}
    (timer,) = payload["timers"]
    assert timer["status"] == "running"
    assert timer["deadline_at"] is not None
    assert 0 <= timer["remaining_seconds"] <= timer["duration_seconds"]


async def test_timers_empty_still_valid_revision(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/home/timers", headers=_EDGE_AUTH)
    assert response.status_code == 200
    payload = _payload(response)
    assert payload["timers"] == []
    assert payload["revision"] >= 1
