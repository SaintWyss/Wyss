"""Ports de Home definidos por Wyss antes de sus adapters."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Protocol

from core.domain.home import (
    CameraFrame,
    CapabilityCommand,
    CapabilityPage,
    CapabilityState,
    DeliveryReceipt,
    JsonValue,
    Notification,
    ProjectionEvent,
    ProjectionSnapshot,
    Transcript,
)


class HomePort(Protocol):
    """Salida autorizada de Wyss hacia capacidades domésticas."""

    async def snapshot(self) -> ProjectionSnapshot: ...

    async def execute(self, command: CapabilityCommand) -> ProjectionEvent: ...


class ProjectionPort(Protocol):
    """Lectura pública de la única proyección compartida."""

    async def snapshot(self, client_id: str) -> ProjectionSnapshot: ...

    async def deltas(self, after_event_id: int, limit: int) -> Sequence[ProjectionEvent]: ...


class ClientEventPort(Protocol):
    """Publicación y suscripción de eventos, sin acoplarse al transporte."""

    async def publish(self, event: ProjectionEvent) -> None: ...

    def subscribe(self, client_id: str, after_event_id: int) -> AsyncIterator[ProjectionEvent]: ...


class MediaPort(Protocol):
    async def state(self) -> CapabilityState: ...

    async def execute(self, command: CapabilityCommand) -> CapabilityState: ...


class CalendarPort(Protocol):
    async def page(self, sync_token: str | None, page_token: str | None) -> CapabilityPage: ...


class ReminderPort(Protocol):
    async def snapshot(self) -> CapabilityState: ...

    async def execute(self, command: CapabilityCommand) -> CapabilityState: ...


class TimerPort(Protocol):
    async def snapshot(self) -> CapabilityState: ...

    async def execute(self, command: CapabilityCommand) -> CapabilityState: ...


class NotificationPort(Protocol):
    async def deliver(self, notification: Notification) -> DeliveryReceipt: ...


class SpeechPort(Protocol):
    async def transcribe(self, audio: memoryview, content_type: str) -> Transcript: ...


class CameraPort(Protocol):
    async def list(self) -> Sequence[CapabilityState]: ...

    async def state(self, camera_id: str) -> CapabilityState: ...

    async def capture(self, camera_id: str) -> CameraFrame: ...

    async def health(self, camera_id: str) -> Mapping[str, JsonValue]: ...
