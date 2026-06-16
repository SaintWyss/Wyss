"""Facade de retrieval con permisos capability-based por query (D-72)."""

from typing import overload

from core.domain import ActorType, AuditEvent, AuditEventType, Query, SearchResult, Subject
from core.domain.errors import WyssError
from core.ports.audit import AuditPort
from core.ports.knowledge import Retrieval
from core.ports.security import PermissionStore


class PermissionDenied(WyssError):
    """Un agente intentó consultar una BC sin permiso vigente."""

    def __init__(self, agent_id: str, kb_id: str) -> None:
        super().__init__(f"agente '{agent_id}' sin permiso vigente sobre BC '{kb_id}'")


class ScopedRetrieval:
    """Facade capability-based sobre Retrieval. Verifica permisos sin cache."""

    @overload
    def __init__(
        self,
        inner: Retrieval,
        permission_store: PermissionStore,
        audit: AuditPort,
        agent_id: str,
    ) -> None: ...

    @overload
    def __init__(
        self,
        *,
        inner: Retrieval,
        permissions: PermissionStore,
        audit: AuditPort,
        agent_id: str,
    ) -> None: ...

    def __init__(
        self,
        inner: Retrieval,
        permission_store: PermissionStore | None = None,
        audit: AuditPort | None = None,
        agent_id: str | None = None,
        *,
        permissions: PermissionStore | None = None,
    ) -> None:
        selected_permissions = permission_store if permission_store is not None else permissions
        if selected_permissions is None:
            raise TypeError("permission_store is required")
        if audit is None:
            raise TypeError("audit is required")
        if agent_id is None:
            raise TypeError("agent_id is required")

        self._inner = inner
        self._permissions = selected_permissions
        self._audit = audit
        self._agent_id = agent_id

    async def search(self, query: Query, subject: Subject) -> SearchResult:
        grants = self._permissions.grants_for(subject)
        granted = frozenset(g.kb_id for g in grants if g.revoked_at is None)
        unauthorized = query.kb_ids - granted
        if unauthorized:
            for kb_id in sorted(unauthorized):
                self._audit.log(
                    AuditEvent.new(
                        actor_type=ActorType.AGENT,
                        actor_id=self._agent_id,
                        event_type=AuditEventType.POLICY_DECISION,
                        message=(
                            f"acceso bloqueado: agente '{self._agent_id}' "
                            f"sin permiso vigente sobre BC '{kb_id}'"
                        ),
                        payload={
                            "agent_id": self._agent_id,
                            "kb_id": kb_id,
                            "blocked": "no_permission",
                        },
                    )
                )
            raise PermissionDenied(self._agent_id, next(iter(sorted(unauthorized))))
        return await self._inner.search(query, subject)
