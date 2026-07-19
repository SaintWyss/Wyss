"""Cliente Spotify para la superficie de media del Home Edge.

OAuth2 (refresh token) + Web API con httpx puro. Los tokens viven SOLO
en Wyss; el Edge recibe el estado sanitizado con el shape que valida
`WyssMediaGateway`: `linked/available/playing/track_uri/title/artist/
progress_ms/duration_ms/favorite/device`. Errores del proveedor se
reexponen con el status que el bridge mapea (401 reauth, 403 premium,
404 device, 429 rate con Retry-After).
"""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

_TOKEN_URL = "https://accounts.spotify.com/api/token"
_API = "https://api.spotify.com/v1"

AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_SCOPES = (
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-library-read",
    "user-library-modify",
)

_ACTIONS = {
    "play",
    "pause",
    "previous",
    "next",
    "set_volume",
    "toggle_favorite",
    "transfer_device",
}


class SpotifyError(RuntimeError):
    """Fallo del proveedor con status HTTP + Retry-After opcional."""

    def __init__(self, status_code: int, message: str, *, retry_after: int | None = None) -> None:
        self.status_code = status_code
        self.retry_after = retry_after
        super().__init__(message)


def load_refresh_token(data_dir: Path) -> str | None:
    token_file = data_dir / "spotify_token"
    if not token_file.exists():
        return None
    stored = token_file.read_text(encoding="utf-8").strip()
    return stored or None


def save_refresh_token(data_dir: Path, refresh_token: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    token_file = data_dir / "spotify_token"
    token_file.write_text(refresh_token, encoding="utf-8")
    token_file.chmod(0o600)


def client_credentials() -> tuple[str, str] | None:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


def not_linked_state() -> dict[str, Any]:
    return {"linked": False, "available": False, "title": "", "artist": ""}


class SpotifyClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._access_token: str | None = None
        self._expires_at = datetime.min.replace(tzinfo=UTC)
        self._http = httpx.AsyncClient(timeout=15.0, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def state(self) -> dict[str, Any] | None:
        """Estado del player en shape del contrato; None = 204 sin playback."""
        response = await self._request("GET", "/me/player")
        if response.status_code == 204 or not response.content:
            return None
        payload = response.json()
        if not isinstance(payload, dict):
            raise SpotifyError(502, "Spotify devolvió un estado inválido")
        return await self._to_contract(payload)

    async def execute(
        self,
        *,
        action: str,
        value: int | None = None,
        device_id: str | None = None,
    ) -> dict[str, Any] | None:
        if action not in _ACTIONS:
            raise SpotifyError(422, f"acción de media desconocida: {action}")
        if action == "play":
            await self._request("PUT", "/me/player/play", device=device_id)
        elif action == "pause":
            await self._request("PUT", "/me/player/pause", device=device_id)
        elif action == "next":
            await self._request("POST", "/me/player/next", device=device_id)
        elif action == "previous":
            await self._request("POST", "/me/player/previous", device=device_id)
        elif action == "set_volume":
            if value is None or not 0 <= value <= 100:
                raise SpotifyError(422, "set_volume requiere value 0..100")
            await self._request(
                "PUT", "/me/player/volume", params={"volume_percent": str(value)}, device=device_id
            )
        elif action == "transfer_device":
            if not device_id:
                raise SpotifyError(422, "transfer_device requiere device_id")
            await self._request(
                "PUT", "/me/player", json_body={"device_ids": [device_id], "play": True}
            )
        elif action == "toggle_favorite":
            await self._toggle_favorite()
        return await self.state()

    async def _toggle_favorite(self) -> None:
        current = await self._request("GET", "/me/player/currently-playing")
        if current.status_code == 204 or not current.content:
            raise SpotifyError(404, "no hay pista sonando para marcar favorita")
        item = current.json().get("item") or {}
        track_id = item.get("id")
        if not isinstance(track_id, str) or not track_id:
            raise SpotifyError(404, "la pista actual no admite favoritos")
        contains = await self._request("GET", "/me/tracks/contains", params={"ids": track_id})
        is_saved = bool(contains.json() and contains.json()[0])
        method = "DELETE" if is_saved else "PUT"
        await self._request(method, "/me/tracks", params={"ids": track_id})

    async def _to_contract(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = payload.get("item") or {}
        artists = item.get("artists") or []
        artist = ", ".join(
            str(entry.get("name", "")) for entry in artists if isinstance(entry, dict)
        )
        raw_device = payload.get("device") or {}
        device = None
        if isinstance(raw_device, dict) and raw_device.get("id"):
            device = {
                "id": str(raw_device.get("id")),
                "name": str(raw_device.get("name", "Dispositivo")),
                "type": str(raw_device.get("type", "unknown")),
                "active": raw_device.get("is_active") is True,
                "restricted": raw_device.get("is_restricted") is True,
                "supports_volume": raw_device.get("supports_volume") is True,
                "volume": raw_device.get("volume_percent"),
            }
        favorite = False
        track_id = item.get("id")
        if isinstance(track_id, str) and track_id:
            try:
                contains = await self._request(
                    "GET", "/me/tracks/contains", params={"ids": track_id}
                )
                decoded = contains.json()
                favorite = bool(isinstance(decoded, list) and decoded and decoded[0])
            except SpotifyError:
                favorite = False  # favorito es cosmético: no rompe el estado
        return {
            "linked": True,
            "available": True,
            "playing": payload.get("is_playing") is True,
            "track_uri": item.get("uri"),
            "title": str(item.get("name") or ""),
            "artist": artist,
            "progress_ms": max(0, int(payload.get("progress_ms") or 0)),
            "duration_ms": max(0, int(item.get("duration_ms") or 0)),
            "favorite": favorite,
            "device": device,
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        device: str | None = None,
    ) -> httpx.Response:
        token = await self._access_token_fresh()
        request_params = dict(params or {})
        if device:
            request_params["device_id"] = device
        try:
            response = await self._http.request(
                method,
                f"{_API}{path}",
                params=request_params or None,
                json=json_body,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as error:
            raise SpotifyError(502, "Spotify no respondió") from error
        if response.status_code in {401, 403, 404, 409}:
            raise SpotifyError(response.status_code, "Spotify rechazó la operación")
        if response.status_code == 429:
            retry_raw = response.headers.get("Retry-After", "")
            retry_after = int(retry_raw) if retry_raw.isdigit() else None
            raise SpotifyError(429, "Spotify limitó temporalmente", retry_after=retry_after)
        if response.is_error:
            raise SpotifyError(502, "Spotify devolvió un error")
        return response

    async def _access_token_fresh(self) -> str:
        if self._access_token is not None and datetime.now(tz=UTC) < self._expires_at:
            return self._access_token
        try:
            response = await self._http.post(
                _TOKEN_URL,
                data={"grant_type": "refresh_token", "refresh_token": self._refresh_token},
                auth=(self._client_id, self._client_secret),
            )
        except httpx.HTTPError as error:
            raise SpotifyError(502, "OAuth de Spotify no respondió") from error
        if response.status_code in {400, 401}:
            raise SpotifyError(401, "la vinculación con Spotify venció")
        if response.is_error:
            raise SpotifyError(502, "OAuth de Spotify devolvió un error")
        payload = response.json()
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise SpotifyError(502, "OAuth de Spotify no devolvió access_token")
        # Spotify puede rotar el refresh token; si llega uno nuevo lo adoptamos en memoria
        rotated = payload.get("refresh_token")
        if isinstance(rotated, str) and rotated:
            self._refresh_token = rotated
        self._access_token = access_token
        self._expires_at = datetime.now(tz=UTC) + timedelta(
            seconds=max(60, int(payload.get("expires_in", 3600)) - 60)
        )
        return access_token


async def exchange_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Canjea el authorization code por un refresh token."""
    async with httpx.AsyncClient(timeout=15.0, transport=transport) as http:
        response = await http.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            auth=(client_id, client_secret),
        )
    if response.is_error:
        raise SpotifyError(502, f"el canje OAuth falló ({response.status_code})")
    payload = response.json()
    refresh_token = payload.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise SpotifyError(502, "Spotify no devolvió refresh_token")
    return refresh_token
