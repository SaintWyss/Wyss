"""Scaffold del gate dorado de retrieval: hit@1 >= 0.80 (16/20)."""

import asyncio
import json
from pathlib import Path
from typing import TypedDict, cast

from core.domain.audit import ActorType
from core.domain.knowledge import Chunk, IndexEntry, Query
from core.domain.security import Subject
from knowledge.fts_index import FTS5Index
from knowledge.retrieval import HybridRetrieval
from knowledge.state_store import StateStore
from knowledge.vector_index import ChromaVectorIndex, chromadb
from tests.knowledge.golden.corpus import CORPUS
from tests.ports.fakes import FakeAuditPort, FakeEmbeddingProvider


class GoldenQuery(TypedDict):
    query: str
    kb_id: str
    expected_source_path: str


QUERIES_PATH = Path(__file__).parent / "golden" / "queries.json"
GOLDEN_QUERIES = cast(list[GoldenQuery], json.loads(QUERIES_PATH.read_text(encoding="utf-8")))


def test_golden_queries_hit_at_one_gate(tmp_path: Path) -> None:
    """Gate CI determinista: hit@1 debe quedar >= 0.80 sobre corpus sintetico."""
    assert len(CORPUS) >= 8
    assert len(GOLDEN_QUERIES) == 20

    state_store = StateStore(tmp_path / "index.db")
    try:
        fts_index = FTS5Index(state_store._conn)
        vector_index = ChromaVectorIndex(
            chromadb.PersistentClient(path=str(tmp_path / "chroma")),
            embedding_model="fake-golden",
            embedding_dim=3,
        )
        embedder = FakeEmbeddingProvider()
        entries = _golden_entries()
        fts_index.upsert(entries)
        vectors = asyncio.run(embedder.embed([entry.chunk.text for entry in entries]))
        vector_index.upsert(tuple(zip(entries, vectors, strict=True)))
        for idx, entry in enumerate(entries):
            state_store.mark_embedded(
                entry.chunk.source_path,
                entry.kb_id,
                size=len(entry.chunk.text),
                mtime=1_700_000_000.0 + idx,
                sha256=f"sha256-{idx}",
            )

        retrieval = HybridRetrieval(
            fts_index=fts_index,
            vector_index=vector_index,
            embedder=embedder,
            audit=FakeAuditPort(),
            state_store=state_store,
        )
        subject = Subject(subject_id="owner", subject_type=ActorType.OWNER)

        failures: list[str] = []
        for case in GOLDEN_QUERIES:
            result = asyncio.run(
                retrieval.search(
                    Query(case["query"], frozenset({case["kb_id"]}), limit=5),
                    subject,
                )
            )
            actual = result.hits[0].source_path if result.hits else "<no hits>"
            if actual != case["expected_source_path"]:
                failures.append(
                    f"{case['query']!r} ({case['kb_id']}): "
                    f"expected {case['expected_source_path']}, got {actual}"
                )

        hit_at_one = (len(GOLDEN_QUERIES) - len(failures)) / len(GOLDEN_QUERIES)
        assert hit_at_one >= 0.80, f"hit@1={hit_at_one:.2f}; failures:\n" + "\n".join(failures)
    finally:
        state_store.close()


def _golden_entries() -> tuple[IndexEntry, ...]:
    return tuple(
        IndexEntry(
            entry_id=f"golden-{idx}",
            kb_id=kb_id,
            chunk=Chunk(
                chunk_id=f"golden-{idx}",
                text=text,
                source_path=source_path,
                position=0,
            ),
        )
        for idx, (source_path, text, kb_id) in enumerate(CORPUS)
    )
