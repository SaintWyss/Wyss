"""Scaffold del gate dorado de retrieval: hit@1 >= 0.80 (16/20)."""

import json
from pathlib import Path
from typing import TypedDict, cast

import pytest

from tests.knowledge.golden.corpus import CORPUS


class GoldenQuery(TypedDict):
    query: str
    kb_id: str
    expected_source_path: str


QUERIES_PATH = Path(__file__).parent / "golden" / "queries.json"
GOLDEN_QUERIES = cast(list[GoldenQuery], json.loads(QUERIES_PATH.read_text(encoding="utf-8")))


@pytest.mark.skip(reason="Wave 3: requiere HybridRetrieval + indices reales — plan 04-03")
def test_golden_queries_hit_at_one_gate() -> None:
    """Plan 04-03 reemplaza este scaffold por el gate real de hit@1."""
    assert len(CORPUS) >= 8
    assert len(GOLDEN_QUERIES) == 20
    assert 16 / 20 == 0.80
