"""Tests del cliente Google Calendar (mapeo al contrato del Edge, sin red)."""

import json
from typing import Any

import httpx
import pytest

from home.google_calendar import GoogleCalendarClient, GoogleCalendarError

_TZ = "America/Argentina/Cordoba"


def _transport(responses: dict[str, httpx.Response]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return responses.get(
                "token",
                httpx.Response(200, json={"access_token": "at", "expires_in": 3600}),
            )
        return responses["events"]

    return httpx.MockTransport(handler)


def _client(responses: dict[str, httpx.Response]) -> GoogleCalendarClient:
    return GoogleCalendarClient("cid", "csecret", "rtok", transport=_transport(responses))


def _google_event(**overrides: Any) -> dict[str, Any]:
    event: dict[str, Any] = {
        "id": "evt-1",
        "etag": '"3400000000000000"',
        "status": "confirmed",
        "summary": "Parcial AdSI",
        "start": {"dateTime": "2026-07-20T09:00:00-03:00"},
        "end": {"dateTime": "2026-07-20T11:00:00-03:00"},
        "updated": "2026-07-19T12:00:00.000Z",
    }
    event.update(overrides)
    return event


async def _page(client: GoogleCalendarClient, **kwargs: Any) -> dict[str, Any]:
    try:
        return await client.events_page(
            timezone=_TZ,
            window_days=7,
            sync_token=kwargs.get("sync_token"),
            page_token=kwargs.get("page_token"),
        )
    finally:
        await client.aclose()


async def test_contract_shape_and_sync_cursor() -> None:
    client = _client(
        {
            "events": httpx.Response(
                200,
                json={"items": [_google_event()], "nextSyncToken": "sync-1"},
            )
        }
    )
    payload = await _page(client)
    assert set(payload) == {"events", "next_sync_token"}
    (event,) = payload["events"]
    assert event["timezone"] == _TZ
    assert event["all_day"] is False
    assert event["title"] == "Parcial AdSI"
    # el contrato exige un solo cursor: nunca ambos
    assert "next_page_token" not in payload
    # nada de secretos en el payload
    assert "access_token" not in json.dumps(payload)


async def test_page_cursor_wins_over_sync() -> None:
    client = _client({"events": httpx.Response(200, json={"items": [], "nextPageToken": "page-2"})})
    payload = await _page(client)
    assert payload == {"events": [], "next_page_token": "page-2"}


async def test_all_day_event_uses_dates() -> None:
    client = _client(
        {
            "events": httpx.Response(
                200,
                json={
                    "items": [
                        _google_event(start={"date": "2026-07-21"}, end={"date": "2026-07-22"})
                    ],
                    "nextSyncToken": "s",
                },
            )
        }
    )
    (event,) = (await _page(client))["events"]
    assert event["all_day"] is True
    assert event["start"] == "2026-07-21"


async def test_cancelled_event_is_minimal() -> None:
    client = _client(
        {
            "events": httpx.Response(
                200,
                json={
                    "items": [{"id": "gone", "status": "cancelled"}],
                    "nextSyncToken": "s",
                },
            )
        }
    )
    (event,) = (await _page(client))["events"]
    assert event == {"id": "gone", "status": "cancelled"}


async def test_expired_sync_token_maps_410() -> None:
    client = _client({"events": httpx.Response(410, json={})})
    with pytest.raises(GoogleCalendarError) as excinfo:
        await _page(client, sync_token="stale")
    assert excinfo.value.status_code == 410


async def test_revoked_refresh_token_maps_401() -> None:
    client = _client(
        {
            "token": httpx.Response(400, json={"error": "invalid_grant"}),
            "events": httpx.Response(200, json={}),
        }
    )
    with pytest.raises(GoogleCalendarError) as excinfo:
        await _page(client)
    assert excinfo.value.status_code == 401


async def test_untitled_event_gets_placeholder() -> None:
    client = _client(
        {
            "events": httpx.Response(
                200,
                json={"items": [_google_event(summary=None)], "nextSyncToken": "s"},
            )
        }
    )
    (event,) = (await _page(client))["events"]
    assert event["title"] == "(sin título)"
