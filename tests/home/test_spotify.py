"""Tests del cliente Spotify (mapeo al contrato del Edge, sin red)."""

from typing import Any

import httpx
import pytest

from home.spotify import SpotifyClient, SpotifyError

_PLAYER = {
    "is_playing": True,
    "progress_ms": 61_000,
    "device": {
        "id": "dev-1",
        "name": "Parlante living",
        "type": "speaker",
        "is_active": True,
        "is_restricted": False,
        "supports_volume": True,
        "volume_percent": 40,
    },
    "item": {
        "id": "track-1",
        "uri": "spotify:track:track-1",
        "name": "Zamba de mi esperanza",
        "duration_ms": 180_000,
        "artists": [{"name": "Los Chalchaleros"}],
    },
}


class _Recorder:
    def __init__(self, routes: dict[str, httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self._routes = routes

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host == "accounts.spotify.com":
            return httpx.Response(200, json={"access_token": "at", "expires_in": 3600})
        for prefix, response in self._routes.items():
            if request.url.path.startswith(prefix):
                return response
        return httpx.Response(200, json={})


def _client(recorder: _Recorder) -> SpotifyClient:
    return SpotifyClient("cid", "csecret", "rtok", transport=httpx.MockTransport(recorder.handler))


async def test_state_contract_shape() -> None:
    recorder = _Recorder(
        {
            "/v1/me/player": httpx.Response(200, json=_PLAYER),
            "/v1/me/tracks/contains": httpx.Response(200, json=[True]),
        }
    )
    client = _client(recorder)
    try:
        state = await client.state()
    finally:
        await client.aclose()
    assert state is not None
    assert state["linked"] is True and state["available"] is True
    assert state["playing"] is True
    assert state["title"] == "Zamba de mi esperanza"
    assert state["artist"] == "Los Chalchaleros"
    assert state["favorite"] is True
    assert state["device"]["id"] == "dev-1"
    assert state["device"]["supports_volume"] is True
    # jamás tokens en el payload
    assert "access_token" not in str(state)


async def test_state_204_means_no_playback() -> None:
    recorder = _Recorder({"/v1/me/player": httpx.Response(204)})
    client = _client(recorder)
    try:
        assert await client.state() is None
    finally:
        await client.aclose()


async def test_set_volume_requires_range() -> None:
    recorder = _Recorder({})
    client = _client(recorder)
    try:
        with pytest.raises(SpotifyError) as excinfo:
            await client.execute(action="set_volume", value=150)
    finally:
        await client.aclose()
    assert excinfo.value.status_code == 422


async def test_rate_limit_maps_429_with_retry_after() -> None:
    recorder = _Recorder({"/v1/me/player": httpx.Response(429, headers={"Retry-After": "17"})})
    client = _client(recorder)
    try:
        with pytest.raises(SpotifyError) as excinfo:
            await client.state()
    finally:
        await client.aclose()
    assert excinfo.value.status_code == 429
    assert excinfo.value.retry_after == 17


async def test_revoked_refresh_maps_401() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "accounts.spotify.com":
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(200, json={})

    client = SpotifyClient("cid", "cs", "rt", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(SpotifyError) as excinfo:
            await client.state()
    finally:
        await client.aclose()
    assert excinfo.value.status_code == 401


async def test_execute_pause_hits_endpoint_and_returns_state() -> None:
    recorder = _Recorder(
        {
            "/v1/me/player/pause": httpx.Response(204),
            "/v1/me/player": httpx.Response(200, json=_PLAYER),
            "/v1/me/tracks/contains": httpx.Response(200, json=[False]),
        }
    )
    client = _client(recorder)
    try:
        state = await client.execute(action="pause")
    finally:
        await client.aclose()
    assert state is not None and state["favorite"] is False
    paths = [request.url.path for request in recorder.requests]
    assert "/v1/me/player/pause" in paths


async def test_toggle_favorite_saves_unsaved_track(recorder_check: Any = None) -> None:
    del recorder_check
    recorder = _Recorder(
        {
            "/v1/me/player/currently-playing": httpx.Response(
                200, json={"item": {"id": "track-1"}}
            ),
            "/v1/me/tracks/contains": httpx.Response(200, json=[False]),
            "/v1/me/tracks": httpx.Response(200, json={}),
            "/v1/me/player": httpx.Response(204),
        }
    )
    client = _client(recorder)
    try:
        await client.execute(action="toggle_favorite")
    finally:
        await client.aclose()
    saves = [
        request
        for request in recorder.requests
        if request.url.path == "/v1/me/tracks" and request.method == "PUT"
    ]
    assert len(saves) == 1


async def test_state_includes_queue() -> None:
    recorder = _Recorder(
        {
            "/v1/me/player/queue": httpx.Response(
                200,
                json={
                    "queue": [
                        {"name": "Nikes", "artists": [{"name": "Frank Ocean"}]},
                        {"name": "", "artists": []},
                        {"name": "Self Control", "artists": [{"name": "Frank Ocean"}]},
                    ]
                },
            ),
            "/v1/me/player": httpx.Response(200, json=_PLAYER),
            "/v1/me/tracks/contains": httpx.Response(200, json=[False]),
        }
    )
    client = _client(recorder)
    try:
        state = await client.state()
    finally:
        await client.aclose()
    assert state is not None
    assert state["queue"] == [
        {"title": "Nikes", "artist": "Frank Ocean"},
        {"title": "Self Control", "artist": "Frank Ocean"},
    ]


async def test_queue_failure_never_breaks_state() -> None:
    recorder = _Recorder(
        {
            "/v1/me/player/queue": httpx.Response(500),
            "/v1/me/player": httpx.Response(200, json=_PLAYER),
            "/v1/me/tracks/contains": httpx.Response(200, json=[False]),
        }
    )
    client = _client(recorder)
    try:
        state = await client.state()
    finally:
        await client.aclose()
    assert state is not None
    assert state["queue"] == []
