"""Auditoría — adapter del AuditPort (D-06, D-08, AUD-01).

Componentes: SqliteAuditLogger (DB SQLite separada, append-only estructural).
"""

from audit.sqlite_logger import SqliteAuditLogger

__all__ = ["SqliteAuditLogger"]
