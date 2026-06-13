from core.domain.knowledge import Hit, SearchResult
from knowledge.rrf import rrf_merge


def _hit(
    entry_id: str,
    *,
    score: float = 0.0,
    snippet: str = "",
    source_path: str | None = None,
    date: float | None = None,
) -> Hit:
    return Hit(
        entry_id=entry_id,
        score=score,
        snippet=snippet,
        source_path=source_path or f"/docs/{entry_id}.md",
        date=date,
    )


def test_rrf_merge_single_list_preserves_order() -> None:
    hits = [_hit("a"), _hit("b"), _hit("c")]

    result = rrf_merge(hits)

    assert [hit.entry_id for hit in result] == ["a", "b", "c"]


def test_rrf_merge_repeated_good_rank_in_both_lists_wins() -> None:
    fts_hits = [_hit("shared"), _hit("fts-only")]
    vector_hits = [_hit("vec-only"), _hit("shared")]

    result = rrf_merge(fts_hits, vector_hits)

    assert result[0].entry_id == "shared"


def test_rrf_merge_empty_lists_returns_empty_list() -> None:
    assert rrf_merge((), ()) == []


def test_rrf_merge_output_score_is_rrf_score() -> None:
    result = rrf_merge([_hit("a", score=-10.0)], [_hit("a", score=0.99)], k=60)

    assert result == [
        Hit(
            entry_id="a",
            score=(1.0 / 61.0) + (1.0 / 61.0),
            snippet="",
            source_path="/docs/a.md",
        )
    ]


def test_rrf_merge_respects_limit() -> None:
    result = rrf_merge([_hit("a"), _hit("b"), _hit("c")], limit=2)

    assert [hit.entry_id for hit in result] == ["a", "b"]


def test_rrf_merge_preserves_first_seen_metadata_for_duplicate() -> None:
    result = rrf_merge(
        [_hit("same", snippet="fts snippet", source_path="/fts.md", date=10.0)],
        [_hit("same", snippet="vector snippet", source_path="/vector.md", date=20.0)],
    )

    assert result == [
        Hit(
            entry_id="same",
            score=(1.0 / 61.0) + (1.0 / 61.0),
            snippet="fts snippet",
            source_path="/fts.md",
            date=10.0,
        )
    ]


def test_hit_date_is_additive_default_none() -> None:
    hit = Hit(entry_id="x", score=0.0, snippet="", source_path="/a")

    assert hit.date is None


def test_search_result_defaults_and_explicit_values() -> None:
    hit = _hit("a")

    default = SearchResult(hits=[hit])
    degraded = SearchResult(hits=(), degraded=True, reason="ollama unavailable")

    assert default.hits == [hit]
    assert default.degraded is False
    assert default.reason == ""
    assert degraded.hits == ()
    assert degraded.degraded is True
    assert degraded.reason == "ollama unavailable"
