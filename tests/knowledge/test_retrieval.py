from pathlib import Path

import pytest

from knowledge.state_store import StateStore


def test_freshness(index_db_path: Path) -> None:
    with StateStore(index_db_path) as store:
        assert store.freshness_by_kb() == []
        assert store.list_kb_ids() == []

        store.mark_embedded(
            "/docs/personal-embedded.md",
            "personal",
            size=10,
            mtime=100.0,
            sha256="sha-personal",
        )
        store.mark_pending("/docs/personal-pending.md", "personal", size=20, mtime=200.0)
        store.mark_extracted("/docs/personal-extracted.md", "personal", size=30, mtime=300.0)
        store.mark_failed("/docs/personal-failed.md", "personal", "boom")
        store.mark_extracted("/docs/ragcorp-extracted.md", "ragcorp", size=40, mtime=400.0)

        freshness = store.freshness_by_kb()
        kb_ids = store.list_kb_ids()

    assert kb_ids == ["personal", "ragcorp"]
    assert len(freshness) == 2

    personal = freshness[0]
    assert personal.kb_id == "personal"
    assert personal.last_indexed_at is not None
    assert personal.last_indexed_at > 0.0
    assert personal.total == 4
    assert personal.embedded == 1
    assert personal.pending == 2
    assert personal.failed == 1

    ragcorp = freshness[1]
    assert ragcorp.kb_id == "ragcorp"
    assert ragcorp.last_indexed_at is None
    assert ragcorp.total == 1
    assert ragcorp.embedded == 0
    assert ragcorp.pending == 1
    assert ragcorp.failed == 0


def test_mtime_by_path(index_db_path: Path) -> None:
    mtime = 1_700_000_123.5
    with StateStore(index_db_path) as store:
        store.mark_extracted("/docs/a.md", "personal", size=10, mtime=mtime)

        assert store.mtime_by_path("/docs/a.md", "personal") == mtime
        assert store.mtime_by_path("/docs/a.md", "other") is None
        assert store.mtime_by_path("/no", "personal") is None


@pytest.mark.skip(reason="Wave 2: HybridRetrieval — plan 04-02")
def test_hybrid_returns_merged() -> None:
    pass


@pytest.mark.skip(reason="Wave 2: HybridRetrieval — plan 04-02")
def test_degraded_mode() -> None:
    pass


@pytest.mark.skip(reason="Wave 2: HybridRetrieval — plan 04-02")
def test_hit_fields() -> None:
    pass


@pytest.mark.skip(reason="Wave 2: HybridRetrieval — plan 04-02")
def test_degraded_audit() -> None:
    pass
