"""Tests de los stores Home (contrato exacto que valida el Edge)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from home.reminder_store import ReminderStore
from home.timer_store import TimerStore

_TZ = "America/Argentina/Cordoba"
_DUE = "2026-07-20T09:00:00-03:00"


class _FrozenNow:
    """Reloj congelado inyectable como callable `now`."""

    moment = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)

    @classmethod
    def call(cls) -> datetime:
        return cls.moment


@pytest.fixture
def reminders(tmp_path: Path) -> Iterator[ReminderStore]:
    with ReminderStore(tmp_path / "reminders.db") as store:
        yield store


@pytest.fixture
def timers(tmp_path: Path) -> Iterator[TimerStore]:
    _FrozenNow.moment = datetime(2026, 7, 19, 12, 0, 0, tzinfo=UTC)
    with TimerStore(tmp_path / "timers.db", now=_FrozenNow.call) as store:
        yield store


def test_reminder_snapshot_contract(reminders: ReminderStore) -> None:
    assert reminders.revision() == 1  # el contrato exige revision > 0 aun vacío
    created = reminders.add(text="regar plantas", due_at=_DUE, timezone=_TZ)
    revision, items = reminders.snapshot(_TZ)
    assert revision == 2
    assert [item.reminder_id for item in items] == [created.reminder_id]
    payload = items[0].to_payload()
    assert set(payload) <= {
        "id",
        "text",
        "due_at",
        "timezone",
        "recurrence",
        "status",
        "revision",
        "notification_id",
    }
    assert payload["status"] == "active"
    assert datetime.fromisoformat(str(payload["due_at"])).tzinfo is not None


def test_reminder_snapshot_filters_other_timezones(reminders: ReminderStore) -> None:
    reminders.add(text="uno", due_at=_DUE, timezone=_TZ)
    reminders.add(text="ajeno", due_at=_DUE, timezone="Europe/Madrid")
    _revision, items = reminders.snapshot(_TZ)
    assert [item.text for item in items] == ["uno"]


def test_reminder_rejects_naive_due_at(reminders: ReminderStore) -> None:
    with pytest.raises(ValueError):
        reminders.add(text="x", due_at="2026-07-20T09:00:00", timezone=_TZ)


def test_reminder_complete_bumps_revision(reminders: ReminderStore) -> None:
    created = reminders.add(text="x", due_at=_DUE, timezone=_TZ)
    before = reminders.revision()
    assert reminders.complete(created.reminder_id)
    revision, items = reminders.snapshot(_TZ)
    assert revision > before
    assert items[0].status == "completed"
    assert not reminders.complete(created.reminder_id)  # idempotente: ya completado


def test_timer_lifecycle_contract(timers: TimerStore) -> None:
    timer = timers.start(label="pasta", duration_seconds=600)
    assert timer.status == "running"
    assert timer.deadline_at is not None
    assert datetime.fromisoformat(timer.deadline_at).tzinfo is not None
    assert timer.remaining_seconds == 600

    _FrozenNow.moment += timedelta(seconds=100)
    _revision, items = timers.snapshot()
    assert items[0].remaining_seconds == 500

    assert timers.pause(timer.timer_id)
    _FrozenNow.moment += timedelta(seconds=1000)
    _revision, items = timers.snapshot()
    assert items[0].status == "paused"
    assert items[0].remaining_seconds == 500
    assert items[0].deadline_at is None

    assert timers.resume(timer.timer_id)
    _revision, items = timers.snapshot()
    assert items[0].status == "running"
    assert items[0].remaining_seconds == 500


def test_timer_expired_autocompletes_with_completion_id(timers: TimerStore) -> None:
    timer = timers.start(label="corto", duration_seconds=10)
    _FrozenNow.moment += timedelta(seconds=11)
    revision, items = timers.snapshot()
    assert items[0].status == "completed"
    assert items[0].completion_id is not None  # contrato: completed exige identidad durable
    assert items[0].remaining_seconds == 0
    assert items[0].deadline_at is None
    # idempotente: otro snapshot no re-completa ni sube revision
    assert timers.snapshot()[0] == revision
    del timer


def test_timer_cancel_only_active(timers: TimerStore) -> None:
    timer = timers.start(label="x", duration_seconds=60)
    assert timers.cancel(timer.timer_id)
    assert not timers.cancel(timer.timer_id)
