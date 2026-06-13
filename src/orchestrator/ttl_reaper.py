"""Reaper de TTL para propuestas pendientes vencidas."""

import asyncio

from core.domain import ActorType, AuditEvent, AuditEventType
from core.ports.audit import AuditPort
from orchestrator.pending_store import PendingStore


def reap_once(pending_store: PendingStore, audit: AuditPort) -> int:
    """Expira propuestas vencidas y audita una entrada por cada una."""
    expired = pending_store.expire_old()
    for proposal in expired:
        audit.log(
            AuditEvent.new(
                task_id=proposal.task_id,
                actor_type=ActorType.SYSTEM,
                actor_id="ttl_reaper",
                event_type=AuditEventType.CONFIRMATION_ANSWERED,
                message="propuesta expirada por TTL - auto-rechazada",
                payload={"pending_id": proposal.id, "risk_level": proposal.risk_level},
            )
        )
    return len(expired)


async def ttl_reaper(
    pending_store: PendingStore, audit: AuditPort, interval_s: float = 30.0
) -> None:
    """Loop asyncio de expiracion periodica para el daemon."""
    while True:
        reap_once(pending_store, audit)
        await asyncio.sleep(interval_s)
