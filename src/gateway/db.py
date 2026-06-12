"""Apertura compartida de la DB de gateway (traces.db): perms + WAL fail-fast + esquema.

`TraceStore` y `CostTracker` comparten el mismo archivo (Open Question 3: una sola DB de
gateway para traces + spend_ledger). Antes cada clase abría la conexión por su cuenta y las
garantías dependían del ORDEN de construcción (WR-08/WR-09): solo `TraceStore` verificaba
WAL fail-fast y aplicaba el chmod 0600 — un `CostTracker` standalone degradaba durabilidad
en silencio. CUALQUIER camino de apertura pasa ahora por `open_gateway_db`:

- chmod 0600 best-effort (traces.db lleva prompts/outputs completos, T-02-trace-file-perms);
- PRAGMAs + smoke test WAL fail-fast (Pitfall 6: sobre NTFS/fuseblk WAL puede degradar y el
  estado que gobierna el presupuesto no puede correr sin durabilidad);
- `apply_schema` idempotente (traces + spend_ledger).
"""

import contextlib
import os
import sqlite3
from pathlib import Path

from core.domain.errors import TraceIntegrityError
from gateway.traces_schema import PRAGMAS, apply_schema


def open_gateway_db(db_path: Path) -> sqlite3.Connection:
    """Abre la DB de gateway con perms restrictivos, WAL verificado fail-fast y esquema.

    Raisea ``TraceIntegrityError`` si ``PRAGMA journal_mode`` no retorna ``"wal"`` —
    espejo exacto del smoke test de `SqliteAuditLogger` (Pitfall 6).
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # best-effort: en FS sin modos POSIX (NTFS) chmod puede no aplicar, no aborta el boot.
    with contextlib.suppress(OSError):
        os.chmod(db_path, 0o600)
    journal_mode: str | None = None
    for pragma in PRAGMAS:
        row = conn.execute(pragma).fetchone()
        if pragma.endswith("WAL") and row is not None:
            journal_mode = str(row[0]).lower()
    if journal_mode != "wal":
        conn.close()
        raise TraceIntegrityError(
            f"gateway db en {db_path}: PRAGMA journal_mode retornó "
            f"{journal_mode!r}, se esperaba 'wal'. WAL no está disponible sobre "
            "este filesystem (probablemente NTFS/fuseblk). Mové data/ a un "
            "filesystem ext4 para garantizar durabilidad de traces y spend_ledger."
        )
    apply_schema(conn)
    return conn
