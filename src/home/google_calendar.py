"""Cliente Google Calendar para la proyección de agenda del Home Edge.

Habla OAuth2 (refresh token) y la REST v3 de Calendar con httpx puro —
sin SDK de Google. Los tokens viven SOLO en Wyss: el payload que sale
de acá cumple el contrato del bridge (`events` + un único cursor
`next_page_token` XOR `next_sync_token`) y jamás incluye secretos.
"""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
_MAX_RESULTS = 250

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events.owned.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"


class GoogleCalendarError(RuntimeError):
    """Fallo del proveedor con el status HTTP que el endpoint reexpone."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


def load_refresh_token(data_dir: Path) -> str | None:
    token_file = data_dir / "google_calendar_token"
    if not token_file.exists():
        return None
    stored = token_file.read_text(encoding="utf-8").strip()
    return stored or None


def save_refresh_token(data_dir: Path, refresh_token: str) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    token_file = data_dir / "google_calendar_token"
    token_file.write_text(refresh_token, encoding="utf-8")
    token_file.chmod(0o600)


def client_credentials() -> tuple[str, str] | None:
    """(client_id, client_secret) desde env, o None si faltan."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    return client_id, client_secret


class GoogleCalendarClient:
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

    async def events_page(
        self,
        *,
        timezone: str,
        window_days: int,
        sync_token: str | None,
        page_token: str | None,
    ) -> dict[str, Any]:
        """Página de eventos con el shape exacto del contrato del Edge."""
        token = await self._access_token_fresh()
        params: dict[str, str] = {
            "singleEvents": "true",
            "maxResults": str(_MAX_RESULTS),
        }
        if page_token:
            params["pageToken"] = page_token
        if sync_token:
            params["syncToken"] = sync_token
        elif not page_token:
            now = datetime.now(tz=UTC)
            params["timeMin"] = now.isoformat()
            params["timeMax"] = (now + timedelta(days=window_days)).isoformat()
        try:
            response = await self._http.get(
                _EVENTS_URL,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        except httpx.HTTPError as error:
            raise GoogleCalendarError(502, "Google Calendar no respondió") from error
        if response.status_code in {401, 403, 410, 429}:
            raise GoogleCalendarError(response.status_code, "Google Calendar rechazó la consulta")
        if response.is_error:
            raise GoogleCalendarError(502, "Google Calendar devolvió un error")
        decoded = response.json()
        if not isinstance(decoded, dict):
            raise GoogleCalendarError(502, "Google Calendar devolvió una respuesta inválida")
        return _to_contract(decoded, timezone)

    async def _access_token_fresh(self) -> str:
        if self._access_token is not None and datetime.now(tz=UTC) < self._expires_at:
            return self._access_token
        try:
            response = await self._http.post(
                _TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "refresh_token": self._refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        except httpx.HTTPError as error:
            raise GoogleCalendarError(502, "OAuth de Google no respondió") from error
        if response.status_code in {400, 401}:
            # invalid_grant: refresh token revocado/vencido → revincular
            raise GoogleCalendarError(401, "la vinculación con Google venció")
        if response.is_error:
            raise GoogleCalendarError(502, "OAuth de Google devolvió un error")
        payload = response.json()
        access_token = payload.get("access_token")
        expires_in = payload.get("expires_in", 3600)
        if not isinstance(access_token, str) or not access_token:
            raise GoogleCalendarError(502, "OAuth de Google no devolvió access_token")
        self._access_token = access_token
        self._expires_at = datetime.now(tz=UTC) + timedelta(seconds=max(60, int(expires_in) - 60))
        return access_token


async def exchange_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    """Canjea el authorization code por un refresh token (flujo instalado)."""
    async with httpx.AsyncClient(timeout=15.0, transport=transport) as http:
        response = await http.post(
            _TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
        )
    if response.is_error:
        raise GoogleCalendarError(502, f"el canje OAuth falló ({response.status_code})")
    payload = response.json()
    refresh_token = payload.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise GoogleCalendarError(
            502,
            "Google no devolvió refresh_token (revocá el acceso previo y reintentá "
            "con prompt=consent)",
        )
    return refresh_token


def _to_contract(decoded: dict[str, Any], timezone: str) -> dict[str, Any]:
    zone = ZoneInfo(timezone)
    events = [
        _event_to_contract(item, timezone, zone)
        for item in decoded.get("items", [])
        if isinstance(item, dict)
    ]
    payload: dict[str, Any] = {"events": events}
    next_page = decoded.get("nextPageToken")
    next_sync = decoded.get("nextSyncToken")
    if isinstance(next_page, str) and next_page:
        payload["next_page_token"] = next_page
    elif isinstance(next_sync, str) and next_sync:
        payload["next_sync_token"] = next_sync
    else:
        raise GoogleCalendarError(502, "Google Calendar no devolvió cursor")
    return payload


def _event_to_contract(item: dict[str, Any], timezone: str, zone: ZoneInfo) -> dict[str, Any]:
    status = item.get("status", "confirmed")
    event_id = str(item.get("id", ""))
    if status == "cancelled":
        return {"id": event_id, "status": "cancelled"}
    start_raw = item.get("start", {})
    end_raw = item.get("end", {})
    all_day = "date" in start_raw
    if all_day:
        start = str(start_raw.get("date", ""))
        end = str(end_raw.get("date", ""))
    else:
        start = _localize(str(start_raw.get("dateTime", "")), zone)
        end = _localize(str(end_raw.get("dateTime", "")), zone)
    event: dict[str, Any] = {
        "id": event_id,
        "etag": str(item.get("etag", "")).strip('"') or "-",
        "title": str(item.get("summary") or "(sin título)")[:300],
        "start": start,
        "end": end,
        "timezone": timezone,
        "all_day": all_day,
        "status": status if status in {"confirmed", "tentative"} else "confirmed",
        "updated_at": str(item.get("updated") or "1970-01-01T00:00:00Z")[:64],
    }
    recurring = item.get("recurringEventId")
    if isinstance(recurring, str) and recurring:
        event["recurring_event_id"] = recurring
    original = item.get("originalStartTime")
    if isinstance(original, dict):
        original_value = original.get("dateTime") or original.get("date")
        if isinstance(original_value, str) and original_value:
            event["original_start"] = original_value[:64]
    return event


def _localize(value: str, zone: ZoneInfo) -> str:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone).isoformat()
