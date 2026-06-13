"""Orquestador del pipeline de ingesta de conocimiento.

El orden es deliberado: scan -> state-check -> secret-gate -> extract -> secret-gate
-> chunk -> FTS -> embed -> vector. Un archivo excluido por secreto nunca toca los índices.
"""

import math
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

import httpx

from core.domain.audit import ActorType, AuditEvent, AuditEventType
from core.domain.errors import ExtractionError, UnsupportedFileError
from core.domain.knowledge import (
    EstimateResult,
    ExtractedContent,
    FileRecord,
    FileStatus,
    IndexEntry,
    IngestRunResult,
    IngestSettings,
)
from core.ports.audit import AuditPort
from core.ports.knowledge import Chunker, EmbeddingProvider, FullTextIndex, VectorIndex
from knowledge.extractors.registry import ExtractorRegistry
from knowledge.scanner import ScanItem
from knowledge.secret_filter import SecretFilter

_CHARS_PER_TOKEN = 4
_EMBED_SECONDS_PER_CHUNK = 0.002


class ScannerLike(Protocol):
    def scan(
        self,
        root: Path,
        *,
        max_file_bytes: int,
        dir_denylist: frozenset[str],
    ) -> Iterator[ScanItem]: ...


class StateStoreLike(Protocol):
    def needs_reindex(self, path: Path | str, kb_id: str, size: int, mtime: float) -> bool: ...

    def mark_extracted(
        self,
        path: Path | str,
        kb_id: str,
        *,
        size: int | None = None,
        mtime: float | None = None,
        sha256: str | None = None,
    ) -> None: ...

    def mark_embedded(
        self,
        path: Path | str,
        kb_id: str,
        *,
        size: int | None = None,
        mtime: float | None = None,
        sha256: str | None = None,
    ) -> None: ...

    def mark_failed(self, path: Path | str, kb_id: str, error: str) -> None: ...

    def mark_excluded_secret(self, path: Path | str, kb_id: str) -> None: ...

    def mark_skipped(self, path: Path | str, kb_id: str, status: FileStatus) -> None: ...

    def get(self, path: Path | str, kb_id: str) -> FileRecord | None: ...


class IngestPipeline:
    """Compone los adapters de ingesta con DI explícita y flujo reanudable."""

    def __init__(
        self,
        *,
        scanner: ScannerLike,
        secret_filter: SecretFilter,
        registry: ExtractorRegistry,
        chunker: Chunker,
        state_store: StateStoreLike,
        fts_index: FullTextIndex,
        embedder: EmbeddingProvider | None,
        vector_index: VectorIndex,
        audit: AuditPort,
        settings: IngestSettings,
    ) -> None:
        self._scanner = scanner
        self._secret_filter = secret_filter
        self._registry = registry
        self._chunker = chunker
        self._state_store = state_store
        self._fts_index = fts_index
        self._embedder = embedder
        self._vector_index = vector_index
        self._audit = audit
        self._settings = settings

    async def run(self, root: Path, kb_id: str) -> IngestRunResult:
        """Ejecuta una corrida de ingesta; los fallos por archivo no abortan."""
        run_id = uuid.uuid4().hex
        indexed = 0
        failed = 0
        excluded_secret = 0
        skipped = 0
        warnings: list[str] = []

        for item in self._scan(root):
            if item.status is not None:
                self._state_store.mark_skipped(item.path, kb_id, item.status)
                skipped += 1
                continue

            source = item.source
            if source is None:
                continue
            if not self._state_store.needs_reindex(
                source.path, kb_id, source.size, source.mtime
            ):
                continue

            path_match = self._secret_filter.check_path(source.path)
            if path_match is not None:
                self._exclude_secret(source.path, kb_id, path_match, run_id=run_id)
                excluded_secret += 1
                continue

            extractor = self._registry.resolve(source.media_type)
            if extractor is None:
                self._state_store.mark_skipped(
                    source.path, kb_id, FileStatus.skipped_unsupported
                )
                skipped += 1
                continue

            try:
                content = extractor.extract(source)
            except UnsupportedFileError:
                self._state_store.mark_skipped(
                    source.path, kb_id, FileStatus.skipped_unsupported
                )
                skipped += 1
                continue
            except ExtractionError as exc:
                self._state_store.mark_failed(source.path, kb_id, type(exc).__name__)
                failed += 1
                continue

            content_match = self._secret_filter.check_content(content.text, source.path)
            if content_match is not None:
                self._exclude_secret(source.path, kb_id, content_match, run_id=run_id)
                excluded_secret += 1
                continue

            entries = self._index_entries(content, kb_id)
            if entries:
                self._fts_index.upsert(entries)
            self._state_store.mark_extracted(
                source.path, kb_id, size=source.size, mtime=source.mtime
            )

            if not entries or self._embedder is None:
                indexed += 1
                continue

            try:
                vectors = await self._embedder.embed([entry.chunk.text for entry in entries])
            except httpx.TransportError as exc:
                warning = f"embedding omitido para {source.path}: {type(exc).__name__}"
                warnings.append(warning)
                self._audit_embedding_failed(source.path, run_id, type(exc).__name__)
                indexed += 1
                continue

            self._vector_index.upsert(tuple(zip(entries, vectors, strict=True)))
            self._state_store.mark_embedded(
                source.path, kb_id, size=source.size, mtime=source.mtime
            )
            indexed += 1

        return IngestRunResult(
            indexed=indexed,
            failed=failed,
            excluded_secret=excluded_secret,
            skipped=skipped,
            run_id=run_id,
            warnings=tuple(warnings),
        )

    def estimate(self, root: Path, kb_id: str) -> EstimateResult:
        """Proyecta trabajo con stat-only: no resuelve ni llama extractores y no escribe."""
        files = 0
        total_bytes = 0
        for item in self._scan(root):
            source = item.source
            if item.status is not None or source is None:
                continue
            if not self._state_store.needs_reindex(
                source.path, kb_id, source.size, source.mtime
            ):
                continue
            files += 1
            total_bytes += source.size

        approx_chunk_bytes = max(1, self._settings.chunk_size_tokens * _CHARS_PER_TOKEN)
        projected_chunks = math.ceil(total_bytes / approx_chunk_bytes) if total_bytes else 0
        return EstimateResult(
            files=files,
            total_bytes=total_bytes,
            projected_chunks=projected_chunks,
            embed_time_s=projected_chunks * _EMBED_SECONDS_PER_CHUNK,
            cost_usd=0.0,
        )

    def dry_run(self, root: Path, kb_id: str) -> list[tuple[str, str]]:
        """Lista archivos que se procesarían y la razón, sin tocar índices ni estado."""
        result: list[tuple[str, str]] = []
        for item in self._scan(root):
            source = item.source
            if item.status is not None or source is None:
                continue
            if not self._state_store.needs_reindex(
                source.path, kb_id, source.size, source.mtime
            ):
                continue
            reason = "nuevo" if self._state_store.get(source.path, kb_id) is None else "modificado"
            result.append((source.path, reason))
        return result

    def _scan(self, root: Path) -> Iterator[ScanItem]:
        yield from self._scanner.scan(
            root,
            max_file_bytes=self._settings.max_file_bytes,
            dir_denylist=frozenset(self._settings.dir_denylist),
        )

    def _index_entries(
        self, content: ExtractedContent, kb_id: str
    ) -> tuple[IndexEntry, ...]:
        return tuple(
            IndexEntry(entry_id=chunk.chunk_id, kb_id=kb_id, chunk=chunk)
            for chunk in self._chunker.chunk(content)
        )

    def _exclude_secret(
        self,
        path: str,
        kb_id: str,
        match: tuple[str, str],
        *,
        run_id: str,
    ) -> None:
        pattern_name, layer = match
        self._state_store.mark_excluded_secret(path, kb_id)
        self._audit.log(
            AuditEvent.new(
                actor_type=ActorType.SYSTEM,
                actor_id="knowledge.pipeline",
                event_type=AuditEventType.ACTION_COMPLETED,
                message="archivo excluido por secreto detectado",
                task_id=run_id,
                payload={
                    "path": path,
                    "pattern": pattern_name,
                    "pattern_name": pattern_name,
                    "layer": layer,
                },
            )
        )

    def _audit_embedding_failed(self, path: str, run_id: str, error_type: str) -> None:
        self._audit.log(
            AuditEvent.new(
                actor_type=ActorType.SYSTEM,
                actor_id="knowledge.pipeline",
                event_type=AuditEventType.TASK_FAILED,
                message="embedding omitido por error transiente",
                task_id=run_id,
                payload={"path": path, "reason": "embedding_unavailable", "error": error_type},
            )
        )
