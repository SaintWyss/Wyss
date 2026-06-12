"""Smoke tests for Phase 3 ingestion test scaffolding."""

from collections.abc import Callable
from pathlib import Path

from core.domain.knowledge import SourceFile
from tests.ports.fakes import FakeAuditPort


def test_knowledge_scaffolding_fixtures(
    index_db_path: Path,
    make_source_file: Callable[..., SourceFile],
    audit: FakeAuditPort,
) -> None:
    """The shared ingestion fixtures are importable and return the expected fakes."""
    source = make_source_file(path="/tmp/example.md", media_type="text/markdown")

    assert index_db_path.name == "index.db"
    assert source.path == "/tmp/example.md"
    assert source.media_type == "text/markdown"
    assert audit.events == []
