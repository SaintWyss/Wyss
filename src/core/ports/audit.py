"""Puerto de auditoría — transversal, inyectado por constructor a todo componente (D-08)."""

from contextlib import AbstractContextManager
from typing import Protocol

from core.domain import AuditEvent, Span


class AuditPort(Protocol):
    """Contrato del sink de auditoría. Sync: el log debe ser durable y barato a esta escala."""

    def log(self, event: AuditEvent) -> None: ...

    def span(
        self, task_id: str, actor: str, event: str
    ) -> AbstractContextManager[Span]: ...
