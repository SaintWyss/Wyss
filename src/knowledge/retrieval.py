"""Retrieval híbrido FTS5 + vector con degradación auditada."""

from collections.abc import Sequence
from dataclasses import replace

import httpx

from core.domain.audit import ActorType, AuditEvent, AuditEventType
from core.domain.knowledge import Hit, Query, SearchResult
from core.domain.security import Subject
from core.ports.audit import AuditPort
from core.ports.knowledge import EmbeddingProvider, FullTextIndex, VectorIndex
from knowledge.rrf import rrf_merge
from knowledge.state_store import StateStore

_OVER_FETCH_MULTIPLIER = 3


class HybridRetrieval:
    """Fusiona resultados textuales y vectoriales detrás del port Retrieval."""

    def __init__(
        self,
        *,
        fts_index: FullTextIndex,
        vector_index: VectorIndex,
        embedder: EmbeddingProvider | None,
        audit: AuditPort,
        state_store: StateStore,
        rrf_k: int = 60,
    ) -> None:
        self._fts = fts_index
        self._vec = vector_index
        self._embedder = embedder
        self._audit = audit
        self._state_store = state_store
        self._rrf_k = rrf_k

    async def search(self, query: Query, subject: Subject) -> SearchResult:
        """Busca, fusiona por RRF, enriquece fecha y audita exactamente una vez."""
        over_fetch = query.limit * _OVER_FETCH_MULTIPLIER
        fts_hits = self._fts.search(query.text, query.kb_ids, over_fetch)
        vec_hits: Sequence[Hit] = ()
        embedder = self._embedder
        degraded = embedder is None
        reason = "fts-only mode" if degraded else ""

        if embedder is not None:
            try:
                vector = (await embedder.embed([query.text]))[0]
                vec_hits = self._vec.search(vector, query.kb_ids, over_fetch)
            except (httpx.HTTPError, httpx.TransportError) as exc:
                degraded = True
                reason = f"ollama unavailable: {exc}"
                vec_hits = ()

        merged = rrf_merge(fts_hits, vec_hits, k=self._rrf_k, limit=query.limit)
        enriched = self._enrich_dates(merged, query.kb_ids)
        self._audit_search(query, subject, len(enriched), degraded=degraded, reason=reason)
        return SearchResult(hits=enriched, degraded=degraded, reason=reason)

    def _enrich_dates(self, hits: Sequence[Hit], kb_ids: frozenset[str]) -> list[Hit]:
        return [replace(hit, date=self._mtime_for_hit(hit, kb_ids)) for hit in hits]

    def _mtime_for_hit(self, hit: Hit, kb_ids: frozenset[str]) -> float | None:
        if not kb_ids:
            return None
        if len(kb_ids) == 1:
            return self._state_store.mtime_by_path(hit.source_path, next(iter(kb_ids)))

        for kb_id in sorted(kb_ids):
            mtime = self._state_store.mtime_by_path(hit.source_path, kb_id)
            if mtime is not None:
                return mtime
        return None

    def _audit_search(
        self,
        query: Query,
        subject: Subject,
        result_count: int,
        *,
        degraded: bool,
        reason: str,
    ) -> None:
        self._audit.log(
            AuditEvent.new(
                actor_type=ActorType.OWNER,
                actor_id=subject.subject_id,
                event_type=AuditEventType.ACTION_COMPLETED,
                message=f"search: '{query.text}' -> {result_count} results",
                payload={
                    "degraded": degraded,
                    "reason": reason,
                    "kb_ids": sorted(query.kb_ids),
                    "result_count": result_count,
                },
            )
        )
