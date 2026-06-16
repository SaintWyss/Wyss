"""Tests de SQLitePermissionStore — grants persistidos D-72."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from core.domain import ActorType, Permission, Subject


def test_permission_store_roundtrip_save_grants_for_revoke(tmp_path: Path) -> None:
    from agents.permission_store import SQLitePermissionStore

    store = SQLitePermissionStore(tmp_path / "permissions.db")
    subject = Subject(subject_id="agent-test", subject_type=ActorType.AGENT)
    permission = Permission(
        permission_id="perm-1",
        subject_id="agent-test",
        kb_id="kb-1",
        granted_at=datetime(2026, 1, 1, 12, 30, tzinfo=UTC),
    )

    store.save(permission)

    grants = store.grants_for(subject)
    assert grants == [permission]

    store.revoke("perm-1")

    revoked_grants = store.grants_for(subject)
    assert len(revoked_grants) == 1
    revoked = revoked_grants[0]
    assert revoked.permission_id == permission.permission_id
    assert revoked.subject_id == permission.subject_id
    assert revoked.kb_id == permission.kb_id
    assert revoked.granted_at == permission.granted_at
    assert revoked.revoked_at is not None
