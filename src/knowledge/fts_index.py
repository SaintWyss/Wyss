"""Adapter FullTextIndex sobre SQLite FTS5."""

import re
import sqlite3
from collections.abc import Sequence

from core.domain.knowledge import Hit, IndexEntry
from knowledge.fts_schema import apply_fts_schema

_TOKEN_RE = re.compile(r"\w+")

_UPSERT_CHUNK = """
INSERT INTO chunks (chunk_id, kb_id, source_path, position, text)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT(chunk_id) DO UPDATE SET
  kb_id=excluded.kb_id,
  source_path=excluded.source_path,
  position=excluded.position,
  text=excluded.text
"""


class FTS5Index:
    """Implementa FullTextIndex con FTS5 external content."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        apply_fts_schema(conn)

    def upsert(self, entries: Sequence[IndexEntry]) -> None:
        for entry in entries:
            self._conn.execute(
                _UPSERT_CHUNK,
                (
                    entry.chunk.chunk_id,
                    entry.kb_id,
                    entry.chunk.source_path,
                    entry.chunk.position,
                    entry.chunk.text,
                ),
            )
        self._conn.commit()

    def search(self, query: str, kb_ids: frozenset[str], limit: int) -> Sequence[Hit]:
        match_query = self._match_query(query)
        if match_query == "" or not kb_ids or limit <= 0:
            return ()

        kb_values = tuple(sorted(kb_ids))
        placeholders = ", ".join("?" for _ in kb_values)
        sql = f"""
        SELECT
          chunks.chunk_id,
          bm25(chunks_fts) AS rank,
          snippet(chunks_fts, 0, '', '', '...', 12) AS snippet,
          chunks.source_path
        FROM chunks_fts
        JOIN chunks ON chunks_fts.rowid = chunks.rowid
        WHERE chunks_fts MATCH ?
          AND chunks.kb_id IN ({placeholders})
        ORDER BY rank
        LIMIT ?
        """
        rows = self._conn.execute(sql, (match_query, *kb_values, limit)).fetchall()
        return tuple(
            Hit(
                entry_id=str(entry_id),
                score=float(rank),
                snippet=str(snippet),
                source_path=str(source_path),
            )
            for entry_id, rank, snippet, source_path in rows
        )

    @staticmethod
    def _match_query(query: str) -> str:
        terms = _TOKEN_RE.findall(query)
        return " ".join(f'"{term}"' for term in terms)
