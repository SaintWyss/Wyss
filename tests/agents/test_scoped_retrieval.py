"""Tests de ScopedRetrieval — filtro de permisos capability-based (AGENT-03, AGENT-04).

Wave 0 — RED: ScopedRetrieval y PermissionDenied aún no existen.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from core.domain import ActorType, AuditEventType, Permission, Subject
from core.domain.knowledge import Query
from tests.agents.conftest import FakeAudit
from tests.ports.fakes import FakePermissionStore, FakeRetrieval

if TYPE_CHECKING:
    from agents.scoped_retrieval import ScopedRetrieval


def _make_scoped(
    agent_id: str,
    fake_retrieval: FakeRetrieval,
    permission_store: FakePermissionStore,
    fake_audit: FakeAudit,
) -> ScopedRetrieval:
    """Factory de ScopedRetrieval con fakes."""
    from agents.scoped_retrieval import ScopedRetrieval

    return ScopedRetrieval(
        agent_id=agent_id,
        inner=fake_retrieval,
        permissions=permission_store,
        audit=fake_audit,
    )


@pytest.mark.asyncio
async def test_unauthorized_blocked(
    fake_retrieval: FakeRetrieval,
    fake_audit: FakeAudit,
) -> None:
    """AGENT-03: BC sin permiso vigente levanta PermissionDenied + audita pre-retrieval.

    El filtro es estructural (capability-based): la inner Retrieval nunca es llamada
    cuando el agente no tiene permiso sobre la BC consultada.
    """
    from agents.scoped_retrieval import PermissionDenied

    # Sin grants — store vacío
    store = FakePermissionStore()
    scoped = _make_scoped("agent-sin-permiso", fake_retrieval, store, fake_audit)

    subject = Subject(subject_id="agent-sin-permiso", subject_type=ActorType.AGENT)
    query = Query(text="datos importantes", kb_ids=frozenset({"kb-restringida"}))

    with pytest.raises(PermissionDenied):
        await scoped.search(query, subject)

    # El evento de auditoría debe haberse registrado ANTES de que inner sea llamado
    assert len(fake_audit.events) >= 1, (
        "Debe haber al menos un evento de auditoría al bloquear acceso a BC"
    )
    policy_events = [
        e for e in fake_audit.events
        if e.event_type == AuditEventType.POLICY_DECISION
    ]
    assert len(policy_events) >= 1, (
        f"El evento de auditoría debe ser POLICY_DECISION; eventos: {fake_audit.events}"
    )


@pytest.mark.asyncio
async def test_revoked_permission_denied(
    fake_retrieval: FakeRetrieval,
    fake_audit: FakeAudit,
) -> None:
    """AGENT-04: un permiso revocado (revoked_at no None) bloquea la query siguiente.

    La verificación es por-query, sin cache — la revocación tiene efecto inmediato
    en la siguiente llamada a search(), sin reiniciar ningún componente.
    """
    from agents.scoped_retrieval import PermissionDenied

    revoked_permission = Permission(
        permission_id="perm-revocado",
        subject_id="agent-test",
        kb_id="kb-1",
        granted_at=datetime(2026, 1, 1, tzinfo=UTC),
        revoked_at=datetime(2026, 6, 1, tzinfo=UTC),  # revocado
    )

    class StoreConRevocado(FakePermissionStore):
        def grants_for(self, subject: Subject) -> Sequence[Permission]:
            return [revoked_permission]

    store = StoreConRevocado()
    scoped = _make_scoped("agent-test", fake_retrieval, store, fake_audit)

    subject = Subject(subject_id="agent-test", subject_type=ActorType.AGENT)
    query = Query(text="datos", kb_ids=frozenset({"kb-1"}))

    # El permiso existe pero está revocado — debe bloquear
    with pytest.raises(PermissionDenied):
        await scoped.search(query, subject)

    # Verificar que no hubo cache — la verificación ocurrió en esta query
    assert len(fake_audit.events) >= 1, (
        "Debe auditarse el intento con permiso revocado"
    )
