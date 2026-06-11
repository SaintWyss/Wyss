"""Entidades de seguridad (mínimas) — sujeto y permiso sobre una base de conocimiento."""

from dataclasses import dataclass
from datetime import datetime

from core.domain.audit import ActorType


@dataclass(frozen=True, slots=True)
class Subject:
    """Identidad que origina una consulta (owner, agente, trabajador…)."""

    subject_id: str
    subject_type: ActorType


@dataclass(frozen=True, slots=True)
class Permission:
    """Habilitación de un sujeto sobre una base de conocimiento (revocable)."""

    permission_id: str
    subject_id: str
    kb_id: str
    granted_at: datetime
    revoked_at: datetime | None = None
