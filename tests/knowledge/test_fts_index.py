import sqlite3

from core.domain.knowledge import Chunk, Hit, IndexEntry
from knowledge.fts_index import FTS5Index
from knowledge.fts_schema import apply_fts_schema
from knowledge.index_schema import apply_index_schema


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    apply_index_schema(conn)
    return conn


def _entry(entry_id: str, kb_id: str, text: str, source_path: str = "/docs/a.md") -> IndexEntry:
    return IndexEntry(
        entry_id=entry_id,
        kb_id=kb_id,
        chunk=Chunk(
            chunk_id=entry_id,
            text=text,
            source_path=source_path,
            position=0,
        ),
    )


def test_apply_fts_schema_is_idempotent() -> None:
    conn = _connect()

    apply_fts_schema(conn)
    apply_fts_schema(conn)

    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
    ).fetchone()
    assert row is not None
    assert "content='chunks'" in str(row[0]) or "content=chunks" in str(row[0])


def test_upsert_then_search_returns_hit() -> None:
    index = FTS5Index(_connect())
    index.upsert((_entry("chunk-1", "A", "alpha needle beta", "/docs/a.md"),))

    hits = index.search("needle", frozenset({"A"}), 10)

    assert hits == (
        Hit(
            entry_id="chunk-1",
            score=hits[0].score,
            snippet=hits[0].snippet,
            source_path="/docs/a.md",
        ),
    )
    assert "needle" in hits[0].snippet


def test_search_filters_by_kb_ids() -> None:
    index = FTS5Index(_connect())
    index.upsert(
        (
            _entry("chunk-a", "A", "shared token", "/docs/a.md"),
            _entry("chunk-b", "B", "shared token", "/docs/b.md"),
        )
    )

    hits = index.search("shared", frozenset({"A"}), 10)

    assert [hit.entry_id for hit in hits] == ["chunk-a"]


def test_fts_uses_external_content_table() -> None:
    conn = _connect()
    FTS5Index(conn)

    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='chunks_fts'"
    ).fetchone()

    assert row is not None
    assert "content='chunks'" in str(row[0]) or "content=chunks" in str(row[0])


def test_delete_from_chunks_cleans_fts_index() -> None:
    conn = _connect()
    index = FTS5Index(conn)
    index.upsert((_entry("chunk-1", "A", "delete-marker searchable", "/docs/a.md"),))
    assert index.search("delete-marker", frozenset({"A"}), 10)

    conn.execute("DELETE FROM chunks WHERE chunk_id=?", ("chunk-1",))
    conn.commit()

    assert index.search("delete-marker", frozenset({"A"}), 10) == ()
