from datetime import UTC, datetime

import pytest

from core.domain.home import ProjectionEvent, ProjectionSnapshot


def _event(*, event_id: int, revision: int) -> ProjectionEvent:
    return ProjectionEvent(
        event_id=event_id,
        revision=revision,
        message_id="msg-1",
        correlation_id="corr-1",
        causation_id=None,
        aggregate_id="assistant:owner",
        event_type="assistant.state.changed",
        source="wyss:authority",
        payload={"state": "idle"},
        occurred_at=datetime.now(UTC),
    )


def test_projection_event_requires_positive_global_and_aggregate_revisions() -> None:
    with pytest.raises(ValueError, match="event_id"):
        _event(event_id=0, revision=1)
    with pytest.raises(ValueError, match="revision"):
        _event(event_id=1, revision=0)


def test_projection_timestamps_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="zona horaria"):
        ProjectionSnapshot(
            schema_version=1,
            last_event_id=0,
            state={},
            generated_at=datetime(2026, 7, 18),
        )


def test_empty_projection_starts_before_first_event() -> None:
    snapshot = ProjectionSnapshot.empty(schema_version=2)

    assert snapshot.schema_version == 2
    assert snapshot.last_event_id == 0
    assert snapshot.state == {}
    assert snapshot.generated_at.tzinfo is UTC
