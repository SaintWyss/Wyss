"""Reciprocal Rank Fusion para resultados de búsqueda híbrida."""

from collections.abc import Sequence

from core.domain.knowledge import Hit


def rrf_merge(
    *hit_lists: Sequence[Hit],
    k: int = 60,
    limit: int = 10,
) -> list[Hit]:
    """Fusiona listas rankeadas de hits usando Reciprocal Rank Fusion.

    Las listas de entrada ya deben venir ordenadas best-first: FTS5 por `ORDER BY rank`
    y vector por similitud descendente (`1.0 - distance`). Esta función no reordena por
    BM25/cosine ni normaliza scores.

    El `Hit.score` de salida es el score RRF (`sum(1/(k+rank))`), no el BM25 ni cosine
    original. Downstream no debe aplicar umbrales sobre este score.
    """
    if limit <= 0:
        return []

    scores: dict[str, float] = {}
    best_hit: dict[str, Hit] = {}
    for hit_list in hit_lists:
        for rank, hit in enumerate(hit_list, start=1):
            scores[hit.entry_id] = scores.get(hit.entry_id, 0.0) + 1.0 / (k + rank)
            best_hit.setdefault(hit.entry_id, hit)

    merged = sorted(best_hit.values(), key=lambda hit: scores[hit.entry_id], reverse=True)
    return [
        Hit(
            entry_id=hit.entry_id,
            score=scores[hit.entry_id],
            snippet=hit.snippet,
            source_path=hit.source_path,
            date=hit.date,
        )
        for hit in merged[:limit]
    ]
