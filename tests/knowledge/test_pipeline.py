"""Tests del orquestador de ingesta: secretos, resume, estimación y extensibilidad."""

import re
import sqlite3
from collections.abc import Iterator, Sequence
from pathlib import Path

import httpx
import pytest

from core.domain.errors import ExtractionError
from core.domain.knowledge import (
    EstimateResult,
    ExtractedContent,
    FileRecord,
    FileStatus,
    Hit,
    IndexEntry,
    IngestSettings,
    SourceFile,
    Vector,
)
from core.ports.knowledge import FullTextIndex
from knowledge.db import open_index_db
from knowledge.extractors.registry import ExtractorRegistry
from knowledge.fts_index import FTS5Index
from knowledge.pipeline import IngestPipeline, StateStoreLike
from knowledge.scanner import ScanItem
from knowledge.secret_filter import SecretFilter
from knowledge.state_store import StateStore
from tests.ports.fakes import FakeAuditPort, FakeChunker, FakeFullTextIndex

_SECRET = "sk-ant-api03-FAKE_KEY_FOR_TEST_abc123def456"
_PATTERNS = (("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),)


class FakeScanner:
    def __init__(self, items: Sequence[ScanItem] | None = None) -> None:
        self.items = tuple(items or ())

    def scan(
        self,
        root: Path,
        *,
        max_file_bytes: int,
        dir_denylist: frozenset[str],
    ) -> Iterator[ScanItem]:
        if not root.is_dir():
            raise NotADirectoryError(str(root))
        yield from self.items


class RecordingExtractor:
    def __init__(
        self,
        *,
        media_types: frozenset[str] = frozenset({"text/plain"}),
        text: str = "clean text",
        fail_paths: frozenset[str] = frozenset(),
    ) -> None:
        self._media_types = media_types
        self._text = text
        self._fail_paths = fail_paths
        self.calls: list[str] = []

    @property
    def media_types(self) -> frozenset[str]:
        return self._media_types

    def extract(self, source: SourceFile) -> ExtractedContent:
        self.calls.append(source.path)
        if source.path in self._fail_paths:
            raise ExtractionError(source.path, "Boom")
        return ExtractedContent(source=source, text=self._text, metadata={})


class PathTextExtractor:
    @property
    def media_types(self) -> frozenset[str]:
        return frozenset({"text/plain"})

    def extract(self, source: SourceFile) -> ExtractedContent:
        return ExtractedContent(
            source=source,
            text=Path(source.path).read_text(encoding="utf-8"),
            metadata={},
        )


class RecordingEmbeddingProvider:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, ...]] = []

    async def embed(self, texts: Sequence[str]) -> Sequence[Vector]:
        self.calls.append(tuple(texts))
        if self.fail:
            raise httpx.ConnectError("ollama down")
        return [tuple(float(len(text)) for _ in range(3)) for text in texts]


class RecordingVectorIndex:
    def __init__(self) -> None:
        self.upserts: list[tuple[tuple[IndexEntry, Vector], ...]] = []

    def upsert(self, entries: Sequence[tuple[IndexEntry, Vector]]) -> None:
        self.upserts.append(tuple(entries))

    def search(self, vector: Vector, kb_ids: frozenset[str], limit: int) -> Sequence[Hit]:
        return ()


class SpyStateStore:
    def __init__(self, *, existing: dict[str, FileRecord] | None = None) -> None:
        self.existing = existing or {}
        self.writes = 0

    def needs_reindex(self, path: Path | str, kb_id: str, size: int, mtime: float) -> bool:
        return True

    def get(self, path: Path | str, kb_id: str) -> FileRecord | None:
        return self.existing.get(str(path))

    def mark_extracted(self, *args: object, **kwargs: object) -> None:
        self.writes += 1

    def mark_embedded(self, *args: object, **kwargs: object) -> None:
        self.writes += 1

    def mark_failed(self, *args: object, **kwargs: object) -> None:
        self.writes += 1

    def mark_excluded_secret(self, *args: object, **kwargs: object) -> None:
        self.writes += 1

    def mark_skipped(self, *args: object, **kwargs: object) -> None:
        self.writes += 1


def _source(path: Path, media_type: str = "text/plain") -> SourceFile:
    stat = path.stat()
    return SourceFile(
        path=str(path),
        media_type=media_type,
        size=stat.st_size,
        mtime=stat.st_mtime,
    )


def _registry(*extractors: RecordingExtractor | PathTextExtractor) -> ExtractorRegistry:
    registry = ExtractorRegistry()
    for extractor in extractors:
        registry.register(extractor)
    return registry


def _pipeline(
    *,
    scanner: FakeScanner,
    state_store: StateStoreLike,
    fts_index: FullTextIndex,
    registry: ExtractorRegistry,
    vector_index: RecordingVectorIndex | None = None,
    embedder: RecordingEmbeddingProvider | None = None,
    audit: FakeAuditPort | None = None,
) -> IngestPipeline:
    return IngestPipeline(
        scanner=scanner,
        secret_filter=SecretFilter(builtin_patterns=_PATTERNS),
        registry=registry,
        chunker=FakeChunker(),
        state_store=state_store,
        fts_index=fts_index,
        embedder=embedder if embedder is not None else RecordingEmbeddingProvider(),
        vector_index=vector_index if vector_index is not None else RecordingVectorIndex(),
        audit=audit if audit is not None else FakeAuditPort(),
        settings=IngestSettings(),
    )


def _count_secret_chunks(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE text LIKE ?",
            (f"%{_SECRET}%",),
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    return int(row[0])


@pytest.mark.asyncio
async def test_planted_secret_not_indexed(index_db_path: Path, tmp_path: Path) -> None:
    secret_file = tmp_path / "trap.txt"
    secret_file.write_text(f"never index {_SECRET}", encoding="utf-8")
    vector_index = RecordingVectorIndex()
    audit = FakeAuditPort()
    state_store = StateStore(index_db_path)
    fts_conn = open_index_db(index_db_path)
    try:
        pipeline = _pipeline(
            scanner=FakeScanner((ScanItem(path=str(secret_file), source=_source(secret_file)),)),
            state_store=state_store,
            fts_index=FTS5Index(fts_conn),
            registry=_registry(PathTextExtractor()),
            vector_index=vector_index,
            audit=audit,
        )

        await pipeline.run(tmp_path, "personal")

        record = state_store.get(secret_file, "personal")
    finally:
        state_store.close()
        fts_conn.close()

    assert _count_secret_chunks(index_db_path) == 0
    assert vector_index.upserts == []
    assert record is not None
    assert record.status == FileStatus.excluded_secret
    assert len(audit.events) == 1
    payload_text = repr(audit.events[0].payload)
    assert "anthropic_key" in payload_text
    assert "pattern_name" in audit.events[0].payload
    assert _SECRET not in payload_text
    assert _SECRET not in audit.events[0].message


@pytest.mark.asyncio
async def test_env_file_excluded_by_path(index_db_path: Path, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=secret", encoding="utf-8")
    extractor = RecordingExtractor(text="should not be read")
    state_store = StateStore(index_db_path)
    try:
        pipeline = _pipeline(
            scanner=FakeScanner((ScanItem(path=str(env_file), source=_source(env_file)),)),
            state_store=state_store,
            fts_index=FakeFullTextIndex(),
            registry=_registry(extractor),
        )

        await pipeline.run(tmp_path, "personal")

        record = state_store.get(env_file, "personal")
    finally:
        state_store.close()

    assert extractor.calls == []
    assert record is not None
    assert record.status == FileStatus.excluded_secret


@pytest.mark.asyncio
async def test_extraction_error_does_not_abort(index_db_path: Path, tmp_path: Path) -> None:
    broken = tmp_path / "broken.txt"
    healthy = tmp_path / "healthy.txt"
    broken.write_text("broken", encoding="utf-8")
    healthy.write_text("healthy", encoding="utf-8")
    extractor = RecordingExtractor(text="safe content", fail_paths=frozenset({str(broken)}))
    state_store = StateStore(index_db_path)
    try:
        pipeline = _pipeline(
            scanner=FakeScanner(
                (
                    ScanItem(path=str(broken), source=_source(broken)),
                    ScanItem(path=str(healthy), source=_source(healthy)),
                )
            ),
            state_store=state_store,
            fts_index=FakeFullTextIndex(),
            registry=_registry(extractor),
        )

        result = await pipeline.run(tmp_path, "personal")

        broken_record = state_store.get(broken, "personal")
        healthy_record = state_store.get(healthy, "personal")
    finally:
        state_store.close()

    assert result.failed == 1
    assert broken_record is not None
    assert broken_record.status == FileStatus.failed
    assert healthy_record is not None
    assert healthy_record.status == FileStatus.embedded


@pytest.mark.asyncio
async def test_ollama_down_leaves_extracted(index_db_path: Path, tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("healthy", encoding="utf-8")
    state_store = StateStore(index_db_path)
    try:
        pipeline = _pipeline(
            scanner=FakeScanner((ScanItem(path=str(source), source=_source(source)),)),
            state_store=state_store,
            fts_index=FakeFullTextIndex(),
            registry=_registry(RecordingExtractor(text="safe content")),
            embedder=RecordingEmbeddingProvider(fail=True),
        )

        result = await pipeline.run(tmp_path, "personal")

        record = state_store.get(source, "personal")
    finally:
        state_store.close()

    assert record is not None
    assert record.status == FileStatus.extracted
    assert result.failed == 0
    assert result.warnings


@pytest.mark.asyncio
async def test_crash_resume(index_db_path: Path, tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    state_store = StateStore(index_db_path)
    try:
        state_store.mark_embedded(
            first,
            "personal",
            size=first.stat().st_size,
            mtime=first.stat().st_mtime,
        )
    finally:
        state_store.close()

    extractor = PathTextExtractor()
    reopened = StateStore(index_db_path)
    try:
        pipeline = _pipeline(
            scanner=FakeScanner(
                (
                    ScanItem(path=str(first), source=_source(first)),
                    ScanItem(path=str(second), source=_source(second)),
                )
            ),
            state_store=reopened,
            fts_index=FakeFullTextIndex(),
            registry=_registry(extractor),
        )

        result = await pipeline.run(tmp_path, "personal")

        first_record = reopened.get(first, "personal")
        second_record = reopened.get(second, "personal")
    finally:
        reopened.close()

    assert result.indexed == 1
    assert first_record is not None
    assert first_record.status == FileStatus.embedded
    assert second_record is not None
    assert second_record.status == FileStatus.embedded


@pytest.mark.asyncio
async def test_systemic_error_propagates(index_db_path: Path, tmp_path: Path) -> None:
    state_store = StateStore(index_db_path)
    try:
        pipeline = _pipeline(
            scanner=FakeScanner(),
            state_store=state_store,
            fts_index=FakeFullTextIndex(),
            registry=_registry(RecordingExtractor()),
        )
        with pytest.raises(NotADirectoryError):
            await pipeline.run(tmp_path / "missing", "personal")
    finally:
        state_store.close()


def test_estimate_no_extraction(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("estimate only", encoding="utf-8")
    extractor = RecordingExtractor(text="must not run")
    pipeline = _pipeline(
        scanner=FakeScanner((ScanItem(path=str(source), source=_source(source)),)),
        state_store=SpyStateStore(),
        fts_index=FakeFullTextIndex(),
        registry=_registry(extractor),
    )

    estimate = pipeline.estimate(tmp_path, "personal")

    assert isinstance(estimate, EstimateResult)
    assert extractor.calls == []
    assert estimate.files == 1
    assert estimate.cost_usd == 0.0


def test_estimate_does_not_write(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("estimate only", encoding="utf-8")
    db_path = tmp_path / "index.db"
    state_store = SpyStateStore()
    pipeline = _pipeline(
        scanner=FakeScanner((ScanItem(path=str(source), source=_source(source)),)),
        state_store=state_store,
        fts_index=FakeFullTextIndex(),
        registry=_registry(RecordingExtractor()),
    )

    pipeline.estimate(tmp_path, "personal")

    assert state_store.writes == 0
    assert not db_path.exists()


def test_dry_run_lists_reasons(tmp_path: Path) -> None:
    new_file = tmp_path / "new.txt"
    modified_file = tmp_path / "modified.txt"
    new_file.write_text("new", encoding="utf-8")
    modified_file.write_text("modified", encoding="utf-8")
    modified_source = _source(modified_file)
    existing_record = FileRecord(
        path=str(modified_file),
        kb_id="personal",
        size=modified_source.size,
        mtime=modified_source.mtime - 1,
        sha256=None,
        status=FileStatus.embedded,
        attempts=0,
        error=None,
    )
    state_store = SpyStateStore(existing={str(modified_file): existing_record})
    pipeline = _pipeline(
        scanner=FakeScanner(
            (
                ScanItem(path=str(new_file), source=_source(new_file)),
                ScanItem(path=str(modified_file), source=modified_source),
            )
        ),
        state_store=state_store,
        fts_index=FakeFullTextIndex(),
        registry=_registry(RecordingExtractor()),
    )

    result = pipeline.dry_run(tmp_path, "personal")

    assert result == [(str(new_file), "nuevo"), (str(modified_file), "modificado")]
    assert state_store.writes == 0


@pytest.mark.asyncio
async def test_new_extractor_no_pipeline_change(index_db_path: Path, tmp_path: Path) -> None:
    source = tmp_path / "sample.new"
    source.write_text("new format", encoding="utf-8")
    extractor = RecordingExtractor(
        media_types=frozenset({"application/x-new-format"}),
        text="future format content",
    )
    state_store = StateStore(index_db_path)
    try:
        pipeline = _pipeline(
            scanner=FakeScanner(
                (ScanItem(path=str(source), source=_source(source, "application/x-new-format")),)
            ),
            state_store=state_store,
            fts_index=FakeFullTextIndex(),
            registry=_registry(extractor),
        )

        await pipeline.run(tmp_path, "personal")

        record = state_store.get(source, "personal")
    finally:
        state_store.close()

    assert extractor.calls == [str(source)]
    assert record is not None
    assert record.status == FileStatus.embedded
