from pathlib import Path

import chromadb
import pytest

from core.domain.knowledge import Chunk, IndexEntry
from knowledge.vector_index import ChromaVectorIndex


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


@pytest.fixture
def vector_index(tmp_path: Path) -> ChromaVectorIndex:
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    return ChromaVectorIndex(client, embedding_model="test-model", embedding_dim=3)


@pytest.mark.integration
def test_separate_collections(vector_index: ChromaVectorIndex) -> None:
    vector_index.upsert(((_entry("entry-a", "personal", "personal text"), (1.0, 0.0, 0.0)),))

    assert vector_index.search((1.0, 0.0, 0.0), frozenset({"ragcorp"}), 10) == ()


@pytest.mark.integration
def test_upsert_idempotent(vector_index: ChromaVectorIndex) -> None:
    entry = _entry("entry-a", "personal", "personal text")

    vector_index.upsert(((entry, (1.0, 0.0, 0.0)),))
    vector_index.upsert(((entry, (1.0, 0.0, 0.0)),))

    collection = vector_index._client.get_or_create_collection(name="personal")
    assert collection.count() == 1


@pytest.mark.integration
def test_search_returns_hits(vector_index: ChromaVectorIndex) -> None:
    vector_index.upsert(
        (
            (_entry("entry-a", "personal", "personal text", "/docs/personal.md"), (1.0, 0.0, 0.0)),
            (_entry("entry-b", "personal", "other text", "/docs/other.md"), (0.0, 1.0, 0.0)),
        )
    )

    hits = vector_index.search((1.0, 0.0, 0.0), frozenset({"personal"}), 1)

    assert len(hits) == 1
    assert hits[0].entry_id == "entry-a"
    assert hits[0].source_path == "/docs/personal.md"
    assert hits[0].snippet == "personal text"


@pytest.mark.integration
def test_collection_metadata_records_embedding_model_and_dim(
    vector_index: ChromaVectorIndex,
) -> None:
    vector_index.upsert(((_entry("entry-a", "personal", "personal text"), (1.0, 0.0, 0.0)),))

    collection = vector_index._client.get_or_create_collection(name="personal")

    assert collection.metadata is not None
    assert collection.metadata["hnsw:space"] == "cosine"
    assert collection.metadata["embedding_model"] == "test-model"
    assert collection.metadata["embedding_dim"] == 3
