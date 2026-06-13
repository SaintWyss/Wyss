"""Adapter VectorIndex sobre ChromaDB PersistentClient."""

from collections.abc import Sequence
from typing import Any, cast

import chromadb
from chromadb.api import ClientAPI

from core.domain.knowledge import Hit, IndexEntry, Vector

_DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
_DEFAULT_EMBEDDING_DIM = 768


class ChromaVectorIndex:
    """Implementa VectorIndex con una colección ChromaDB por kb_id."""

    def __init__(
        self,
        client: ClientAPI,
        *,
        embedding_model: str = _DEFAULT_EMBEDDING_MODEL,
        embedding_dim: int = _DEFAULT_EMBEDDING_DIM,
    ) -> None:
        self._client = client
        self._embedding_model = embedding_model
        self._embedding_dim = embedding_dim

    def upsert(self, entries: Sequence[tuple[IndexEntry, Vector]]) -> None:
        grouped: dict[str, list[tuple[IndexEntry, Vector]]] = {}
        for entry, vector in entries:
            grouped.setdefault(entry.kb_id, []).append((entry, vector))

        for kb_id, group in grouped.items():
            collection = self._collection(kb_id)
            collection.upsert(
                ids=[entry.entry_id for entry, _ in group],
                embeddings=[list(vector) for _, vector in group],
                documents=[entry.chunk.text for entry, _ in group],
                metadatas=[
                    {
                        "source_path": entry.chunk.source_path,
                        "position": entry.chunk.position,
                        "kb_id": entry.kb_id,
                    }
                    for entry, _ in group
                ],
            )

    def search(self, vector: Vector, kb_ids: frozenset[str], limit: int) -> Sequence[Hit]:
        if not kb_ids or limit <= 0:
            return ()

        hits: list[Hit] = []
        for kb_id in sorted(kb_ids):
            collection = self._collection(kb_id)
            result = cast(
                dict[str, Any],
                collection.query(query_embeddings=[list(vector)], n_results=limit),
            )
            ids = self._first_result_list(result, "ids")
            distances = self._first_result_list(result, "distances")
            documents = self._first_result_list(result, "documents")
            metadatas = self._first_result_list(result, "metadatas")
            for idx, entry_id in enumerate(ids):
                distance = self._optional_float(distances, idx)
                metadata = self._optional_mapping(metadatas, idx)
                hits.append(
                    Hit(
                        entry_id=str(entry_id),
                        score=1.0 - distance,
                        snippet=str(documents[idx]) if idx < len(documents) else "",
                        source_path=str(metadata.get("source_path", "")),
                    )
                )
        hits.sort(key=lambda hit: hit.score, reverse=True)
        return tuple(hits[:limit])

    def _collection(self, kb_id: str) -> Any:
        return self._client.get_or_create_collection(
            name=kb_id,
            metadata={
                "hnsw:space": "cosine",
                "embedding_model": self._embedding_model,
                "embedding_dim": self._embedding_dim,
            },
        )

    @staticmethod
    def _first_result_list(result: dict[str, Any], key: str) -> list[Any]:
        values = result.get(key)
        if not isinstance(values, list) or not values:
            return []
        first = values[0]
        if not isinstance(first, list):
            return []
        return first

    @staticmethod
    def _optional_float(values: list[Any], idx: int) -> float:
        if idx >= len(values):
            return 0.0
        return float(values[idx])

    @staticmethod
    def _optional_mapping(values: list[Any], idx: int) -> dict[str, Any]:
        if idx >= len(values) or not isinstance(values[idx], dict):
            return {}
        return cast(dict[str, Any], values[idx])


__all__ = ["ChromaVectorIndex", "chromadb"]
