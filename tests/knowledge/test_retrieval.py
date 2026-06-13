from collections.abc import Sequence
from pathlib import Path

import httpx

from core.domain.audit import ActorType, AuditEventType
from core.domain.knowledge import Hit, IndexEntry, Query, Vector
from core.domain.security import Subject
from knowledge.retrieval import HybridRetrieval
from knowledge.state_store import StateStore
from tests.ports.fakes import FakeAuditPort, FakeEmbeddingProvider


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


class StaticFullTextIndex:
    def __init__(self, hits: Sequence[Hit]) -> None:
        self.hits = hits
        self.seen_limits: list[int] = []

    def upsert(self, entries: Sequence[IndexEntry]) -> None:
        return None

    def search(self, query: str, kb_ids: frozenset[str], limit: int) -> Sequence[Hit]:
        self.seen_limits.append(limit)
        return self.hits[:limit]


class StaticVectorIndex:
    def __init__(self, hits: Sequence[Hit]) -> None:
        self.hits = hits
        self.seen_limits: list[int] = []

    def upsert(self, entries: Sequence[tuple[IndexEntry, Vector]]) -> None:
        return None

    def search(self, vector: Vector, kb_ids: frozenset[str], limit: int) -> Sequence[Hit]:
        self.seen_limits.append(limit)
        return self.hits[:limit]


class TransportErrorEmbeddingProvider:
    async def embed(self, texts: Sequence[str]) -> Sequence[Vector]:
        raise httpx.TransportError("connection refused")


def _hit(
    entry_id: str,
    *,
    source_path: str | None = None,
    snippet: str | None = None,
    score: float = 1.0,
) -> Hit:
    return Hit(
        entry_id=entry_id,
        score=score,
        snippet=snippet or f"snippet {entry_id}",
        source_path=source_path or f"/docs/{entry_id}.md",
    )


def _subject() -> Subject:
    return Subject(subject_id="owner-1", subject_type=ActorType.OWNER)


def _query(*, limit: int = 3, kb_ids: frozenset[str] = frozenset({"personal"})) -> Query:
    return Query(text="hybrid search", kb_ids=kb_ids, limit=limit)


def _retrieval(
    index_db_path: Path,
    *,
    fts_hits: Sequence[Hit],
    vector_hits: Sequence[Hit] = (),
    embedder: FakeEmbeddingProvider | TransportErrorEmbeddingProvider | None = None,
    audit: FakeAuditPort | None = None,
) -> tuple[HybridRetrieval, StateStore, FakeAuditPort, StaticFullTextIndex, StaticVectorIndex]:
    fts = StaticFullTextIndex(fts_hits)
    vector = StaticVectorIndex(vector_hits)
    audit_port = audit or FakeAuditPort()
    store = StateStore(index_db_path)
    retrieval = HybridRetrieval(
        fts_index=fts,
        vector_index=vector,
        embedder=embedder if embedder is not None else FakeEmbeddingProvider(),
        audit=audit_port,
        state_store=store,
    )
    return retrieval, store, audit_port, fts, vector


async def test_hybrid_returns_merged(index_db_path: Path) -> None:
    retrieval, store, audit, fts, vector = _retrieval(
        index_db_path,
        fts_hits=(_hit("shared"), _hit("fts-only")),
        vector_hits=(_hit("vec-only"), _hit("shared")),
    )

    try:
        result = await retrieval.search(_query(limit=2), _subject())
    finally:
        store.close()

    assert [hit.entry_id for hit in result.hits] == ["shared", "vec-only"]
    assert len(result.hits) <= 2
    assert result.degraded is False
    assert result.reason == ""
    assert fts.seen_limits == [6]
    assert vector.seen_limits == [6]
    assert len(audit.events) == 1


async def test_degraded_mode(index_db_path: Path) -> None:
    retrieval, store, audit, _fts, vector = _retrieval(
        index_db_path,
        fts_hits=(_hit("fts-only"),),
        vector_hits=(_hit("vec-only"),),
        embedder=TransportErrorEmbeddingProvider(),
    )

    try:
        transport_result = await retrieval.search(_query(), _subject())
    finally:
        store.close()

    assert [hit.entry_id for hit in transport_result.hits] == ["fts-only"]
    assert transport_result.degraded is True
    assert transport_result.reason
    assert vector.seen_limits == []
    assert len(audit.events) == 1

    fts = StaticFullTextIndex(())
    vec = StaticVectorIndex((_hit("vec-only"),))
    audit_none = FakeAuditPort()
    with StateStore(index_db_path) as state_store:
        retrieval_none = HybridRetrieval(
            fts_index=fts,
            vector_index=vec,
            embedder=None,
            audit=audit_none,
            state_store=state_store,
        )

        none_result = await retrieval_none.search(_query(), _subject())

    assert none_result.hits == []
    assert none_result.degraded is True
    assert none_result.reason == "fts-only mode"
    assert vec.seen_limits == []
    assert len(audit_none.events) == 1


async def test_hit_fields(index_db_path: Path) -> None:
    expected_mtime = 1_700_123_456.5
    hit = _hit("a", source_path="/docs/a.md", snippet="relevant extract")
    retrieval, store, _audit, _fts, _vector = _retrieval(index_db_path, fts_hits=(hit,))
    store.mark_extracted("/docs/a.md", "personal", size=100, mtime=expected_mtime)

    try:
        result = await retrieval.search(_query(), _subject())
    finally:
        store.close()

    assert len(result.hits) == 1
    returned = result.hits[0]
    assert returned.source_path == "/docs/a.md"
    assert returned.snippet == "relevant extract"
    assert returned.date == expected_mtime


async def test_degraded_audit(index_db_path: Path) -> None:
    audit = FakeAuditPort()
    retrieval, store, _audit, _fts, _vector = _retrieval(
        index_db_path,
        fts_hits=(),
        embedder=TransportErrorEmbeddingProvider(),
        audit=audit,
    )

    try:
        result = await retrieval.search(_query(kb_ids=frozenset({"personal", "work"})), _subject())
    finally:
        store.close()

    assert result.hits == []
    assert result.degraded is True
    assert len(audit.events) == 1
    event = audit.events[0]
    assert event.event_type == AuditEventType.ACTION_COMPLETED
    assert event.actor_type == ActorType.OWNER
    assert event.actor_id == "owner-1"
    assert event.payload["degraded"] is True
    assert event.payload["reason"] == result.reason
    assert event.payload["kb_ids"] == ["personal", "work"]
    assert event.payload["result_count"] == 0
