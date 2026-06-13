"""DDL FTS5 para chunks: external content table + triggers de sincronización."""

import sqlite3

CREATE_CHUNKS_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text,
  content=chunks,
  content_rowid=rowid,
  tokenize='unicode61'
)
"""

CREATE_CHUNKS_AI = """
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END
"""

CREATE_CHUNKS_AD = """
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END
"""

CREATE_CHUNKS_AU = """
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
  INSERT INTO chunks_fts(rowid, text) VALUES (new.rowid, new.text);
END
"""


def apply_fts_schema(conn: sqlite3.Connection) -> None:
    """Crea índice FTS5 y triggers sobre la tabla canónica `chunks`."""
    conn.execute(CREATE_CHUNKS_FTS)
    conn.execute(CREATE_CHUNKS_AI)
    conn.execute(CREATE_CHUNKS_AD)
    conn.execute(CREATE_CHUNKS_AU)
    conn.commit()
