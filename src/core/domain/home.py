"""Tipos puros del límite entre la autoridad Wyss y sus clientes Home."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True, slots=True)
class CapabilityCommand:
    """Comando correlacionado que Wyss debe autorizar antes de delegar I/O."""

    request_id: str
    message_id: str
    correlation_id: str
    causation_id: str | None
    idempotency_key: str
    source: str
    capability: str
    action: str
    entity_id: str | None = None
    expected_revision: int | None = None
    arguments: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProjectionEvent:
    """Delta durable, globalmente ordenado y monotónico por agregado."""

    event_id: int
    message_id: str
    correlation_id: str
    causation_id: str | None
    aggregate_id: str
    revision: int
    event_type: str
    source: str
    payload: Mapping[str, JsonValue]
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.event_id < 1:
            raise ValueError("event_id debe ser positivo")
        if self.revision < 1:
            raise ValueError("revision debe ser positiva")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at debe incluir zona horaria")


@dataclass(frozen=True, slots=True)
class ProjectionSnapshot:
    """Vista materializada de presentación; nunca contiene secretos ni historial completo."""

    schema_version: int
    last_event_id: int
    state: Mapping[str, JsonValue]
    generated_at: datetime

    def __post_init__(self) -> None:
        if self.schema_version < 1:
            raise ValueError("schema_version debe ser positiva")
        if self.last_event_id < 0:
            raise ValueError("last_event_id no puede ser negativo")
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at debe incluir zona horaria")

    @classmethod
    def empty(cls, *, schema_version: int = 1) -> ProjectionSnapshot:
        return cls(
            schema_version=schema_version,
            last_event_id=0,
            state={},
            generated_at=datetime.now(UTC),
        )


@dataclass(frozen=True, slots=True)
class CapabilityState:
    """Estado actual verificado de una capacidad o entidad."""

    aggregate_id: str
    revision: int
    available: bool
    verified: bool
    data: Mapping[str, JsonValue]


@dataclass(frozen=True, slots=True)
class CapabilityPage:
    """Página estable para proveedores con sincronización incremental."""

    items: tuple[Mapping[str, JsonValue], ...]
    next_page_token: str | None = None
    sync_token: str | None = None


@dataclass(frozen=True, slots=True)
class Notification:
    """Notificación tipada sin detalles del proveedor de entrega."""

    notification_id: str
    kind: str
    title: str
    body: str
    data: Mapping[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeliveryReceipt:
    notification_id: str
    accepted: bool
    provider_reference: str | None = None


@dataclass(frozen=True, slots=True)
class Transcript:
    text: str
    language: str | None = None
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class CameraFrame:
    """Frame interno; el canal de control sólo puede publicar metadatos derivados."""

    camera_id: str
    content_type: str
    data: bytes
    captured_at: datetime
