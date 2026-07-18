from datetime import UTC, datetime, timedelta
from pathlib import Path

from adapters.sqlite_idempotency import SqliteIdempotencyStore
from core.domain.home import ClaimStatus


def test_claim_replay_and_payload_conflict_are_durable(tmp_path: Path) -> None:
    path = tmp_path / "client_requests.db"
    store = SqliteIdempotencyStore(path)
    assert store.claim("panel:msg-1", "fingerprint-a").status is ClaimStatus.NEW
    store.complete("panel:msg-1", {"outcome": "pending", "pending_id": "p-1"})
    store.close()

    reopened = SqliteIdempotencyStore(path)
    try:
        replay = reopened.claim("panel:msg-1", "fingerprint-a")
        conflict = reopened.claim("panel:msg-1", "fingerprint-b")
    finally:
        reopened.close()

    assert replay.status is ClaimStatus.REPLAY
    assert replay.response == {"outcome": "pending", "pending_id": "p-1"}
    assert conflict.status is ClaimStatus.CONFLICT


def test_database_and_sidecars_are_private(tmp_path: Path) -> None:
    path = tmp_path / "client_requests.db"
    store = SqliteIdempotencyStore(path)
    try:
        store.claim("panel:private", "fingerprint")
        store.complete("panel:private", {"outcome": "completed"})
        paths = [path, Path(f"{path}-wal"), Path(f"{path}-shm")]
        assert all((item.stat().st_mode & 0o777) == 0o600 for item in paths if item.exists())
    finally:
        store.close()


def test_in_progress_claim_is_fail_closed(tmp_path: Path) -> None:
    store = SqliteIdempotencyStore(tmp_path / "client_requests.db")
    try:
        assert store.claim("edge:msg-2", "fingerprint").status is ClaimStatus.NEW
        assert store.claim("edge:msg-2", "fingerprint").status is ClaimStatus.IN_PROGRESS
    finally:
        store.close()


def test_in_progress_claim_survives_process_reopen(tmp_path: Path) -> None:
    path = tmp_path / "client_requests.db"
    first = SqliteIdempotencyStore(path)
    assert first.claim("edge:crash", "fingerprint").status is ClaimStatus.NEW
    first.close()

    reopened = SqliteIdempotencyStore(path)
    try:
        assert reopened.claim("edge:crash", "fingerprint").status is ClaimStatus.IN_PROGRESS
    finally:
        reopened.close()


def test_completed_claims_can_expire_after_contract_window(tmp_path: Path) -> None:
    store = SqliteIdempotencyStore(tmp_path / "client_requests.db")
    try:
        store.claim("panel:old", "fingerprint")
        store.complete("panel:old", {"outcome": "resolved"})

        removed = store.prune_completed(datetime.now(UTC) + timedelta(seconds=1))

        assert removed == 1
        assert store.claim("panel:old", "fingerprint").status is ClaimStatus.NEW
    finally:
        store.close()


def test_capacity_fails_closed_without_pruning_ambiguous_claims(tmp_path: Path) -> None:
    store = SqliteIdempotencyStore(
        tmp_path / "client_requests.db",
        max_rows=2,
        max_completed_rows=1,
        maintenance_interval=100,
    )
    try:
        assert store.claim("edge:one", "one").status is ClaimStatus.NEW
        assert store.claim("edge:two", "two").status is ClaimStatus.NEW
        try:
            store.claim("edge:three", "three")
        except RuntimeError as exc:
            assert "capacidad" in str(exc)
        else:
            raise AssertionError("el store debía fallar cerrado al alcanzar la cuota")
        assert store.claim("edge:one", "one").status is ClaimStatus.IN_PROGRESS
    finally:
        store.close()
