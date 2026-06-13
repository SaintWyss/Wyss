"""Stubs del PendingStore SQLite (ORCH-06 / D-54..D-56) — Plan 05-03 implementa.

Scaffolding Wave 0. Cubre WAL activo, persistencia tras reopen, expiración TTL (D-56) y
rechazo de confirmación sobre propuesta expirada.
"""

import pytest


@pytest.mark.skip(reason="Wave 1: 05-03 implementa PendingStore (WAL)")
def test_wal_active() -> None:
    """El PendingStore deja journal_mode=WAL sobre su db."""
    raise NotImplementedError


@pytest.mark.skip(reason="Wave 1: 05-03 implementa PendingStore (persistencia D-54)")
def test_pending_survives_reopen() -> None:
    """Una propuesta pendiente sobrevive al cierre+reapertura del store."""
    raise NotImplementedError


@pytest.mark.skip(reason="Wave 1: 05-03 implementa ttl_reaper (D-56 expira stale)")
def test_expire_old_sets_status_expired() -> None:
    """El reaper marca status=expired las propuestas más viejas que el TTL."""
    raise NotImplementedError


@pytest.mark.skip(reason="Wave 1: 05-03 implementa PendingStore (D-56 confirm rechaza expirado)")
def test_confirm_rejects_expired_proposal() -> None:
    """Confirmar una propuesta ya expirada es rechazado (no se ejecuta)."""
    raise NotImplementedError
