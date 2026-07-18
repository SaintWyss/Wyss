"""UndoJournal (EXEC-03 / D-65): SQLite-WAL reversible store bajo src/execution/.

Registra una operación inversa por cada acción mutante ANTES de que ocurra la
mutación. El executor (plan 05) llama restore(entry_id) durante ABORT para revertir
los pasos ya ejecutados en orden inverso.

Patrón estructural: espejo exacto de src/orchestrator/pending_store.py.
NO importa PendingStore — la capa execution/ solo puede importar core.* y stdlib
(import-linter contrato 'independence', pyproject ~línea 90+).
"""

import json
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from core.domain.errors import AuditIntegrityError

JOURNAL_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",  # NORMAL (no FULL): journal es operacional, no audit log
    "PRAGMA busy_timeout=5000",
)

CREATE_JOURNAL = """
CREATE TABLE IF NOT EXISTS undo_entries (
  id           TEXT PRIMARY KEY,
  task_id      TEXT NOT NULL,
  step_index   INTEGER NOT NULL,
  action_type  TEXT NOT NULL,
  origin       TEXT NOT NULL,
  destination  TEXT,
  inverse_op   TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending',
  created_at   TEXT NOT NULL,
  resolved_at  TEXT
)
"""
# inverse_op es JSON: {"type": "file.move", "target": "...", "parameters": {...}}
# Para file.write overwrite: inverse_op["parameters"]["backup_path"] apunta a
# data/undo_backups/{entry_id} (NO BLOB SQLite — RESEARCH Pitfall 5).

_INSERT = (
    "INSERT INTO undo_entries "
    "(id, task_id, step_index, action_type, origin, destination, inverse_op, "
    "status, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)"
)

_DEFAULT_BACKUP_DIR = Path("data") / "undo_backups"


@dataclass(frozen=True, slots=True)
class UndoEntry:
    """Fila durable de `undo_entries`."""

    id: str
    task_id: str
    step_index: int
    action_type: str
    origin: str
    destination: str | None
    inverse_op: str  # JSON crudo; parsear con json.loads()
    status: str
    created_at: str
    resolved_at: str | None


def _row_to_entry(row: sqlite3.Row) -> UndoEntry:
    return UndoEntry(
        id=row["id"],
        task_id=row["task_id"],
        step_index=row["step_index"],
        action_type=row["action_type"],
        origin=row["origin"],
        destination=row["destination"],
        inverse_op=row["inverse_op"],
        status=row["status"],
        created_at=row["created_at"],
        resolved_at=row["resolved_at"],
    )


class UndoJournal:
    """Cola durable de operaciones reversibles sobre SQLite con WAL fail-fast.

    Patrón: espejo de PendingStore (src/orchestrator/pending_store.py).
    Constructor falla rápido con AuditIntegrityError si WAL no está disponible
    en el filesystem (D-65 / T-06-UNDO-2).
    """

    def __init__(
        self,
        db_path: Path,
        backup_base_dir: Path | None = None,
    ) -> None:
        self._db_path = db_path
        self._backup_base_dir = backup_base_dir or _DEFAULT_BACKUP_DIR
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        journal_mode: str | None = None
        for pragma in JOURNAL_PRAGMAS:
            row = self._conn.execute(pragma).fetchone()
            if pragma.endswith("WAL") and row is not None:
                journal_mode = str(row[0]).lower()
        if journal_mode != "wal":
            self._conn.close()
            raise AuditIntegrityError(
                f"undo journal en {db_path}: PRAGMA journal_mode retorno "
                f"{journal_mode!r}, se esperaba 'wal'. WAL no esta disponible "
                "sobre este filesystem."
            )
        self._apply_schema()

    # ------------------------------------------------------------------
    # Escritura (llamar ANTES de la mutación — D-65 / T-06-UNDO-3)
    # ------------------------------------------------------------------

    def record(
        self,
        task_id: str,
        step_index: int,
        action_type: str,
        origin: str,
        destination: str | None,
        inverse_op: dict[str, object],
    ) -> str:
        """Persiste una entrada undo y devuelve su entry_id.

        IMPORTANTE: llamar ANTES de la mutación (D-65). Si la mutación falla, el
        caller puede ignorar la entrada (no se pierde nada). Si la mutación tiene
        éxito, el entry_id se guarda para poder llamar restore() en un ABORT.
        """
        entry_id = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            _INSERT,
            (
                entry_id,
                task_id,
                step_index,
                action_type,
                origin,
                destination,
                json.dumps(inverse_op),
                now,
            ),
        )
        self._conn.commit()
        return entry_id

    def capture_overwrite_backup(self, entry_id: str, source_path: Path) -> Path:
        """Captura el contenido actual de source_path en data/undo_backups/{entry_id}.

        Llamar ANTES de sobrescribir el archivo (D-65). Devuelve la ruta del backup.
        El contenido se almacena como archivo real, NO como BLOB SQLite (RESEARCH Pitfall 5).
        """
        backup_path = self._backup_base_dir / entry_id
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(source_path), str(backup_path))
        return backup_path

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    def load(self, entry_id: str) -> UndoEntry | None:
        """Carga una entrada por id, o None si no existe."""
        row = self._conn.execute("SELECT * FROM undo_entries WHERE id=?", (entry_id,)).fetchone()
        if row is None:
            return None
        return _row_to_entry(row)

    def load_applied_for_task(self, task_id: str) -> list[UndoEntry]:
        """Entradas 'applied' de una tarea en orden INVERSO de ejecución (PR-09).

        Es la vista que consume `wyss undo`: solo mutaciones que llegaron a
        aplicarse (las 'pending' pertenecen a un plan en vuelo; las 'rolled_back'
        ya fueron revertidas) y en orden inverso, que es el único orden seguro
        para deshacer.
        """
        rows = self._conn.execute(
            "SELECT * FROM undo_entries WHERE task_id=? AND status='applied' "
            "ORDER BY step_index DESC, created_at DESC",
            (task_id,),
        ).fetchall()
        return [_row_to_entry(row) for row in rows]

    def backup_path(self, entry_id: str) -> Path:
        """Ruta del backup de sobreescritura de una entrada (exista o no)."""
        return self._backup_base_dir / entry_id

    # ------------------------------------------------------------------
    # Restauración
    # ------------------------------------------------------------------

    def restore(self, entry_id: str, *, expected_status: str = "pending") -> bool:
        """Aplica la operación inversa de una entrada.

        Retorna True si se revirtió; False si la entrada no existe o su status no
        es `expected_status`. NO lanza excepción en esos casos. El default
        ('pending') es el rollback intra-plan del executor (ABORT); `wyss undo`
        (PR-09) pasa expected_status='applied' para revertir mutaciones ya
        aplicadas de tareas completadas.

        Tipos de inversa soportados:
        - file.move  → shutil.move(dest, origin)
        - file.delete → Path(target).unlink (elimina archivo recién escrito)
        - file.write  → copia data/undo_backups/{entry_id} de vuelta a origin
        - file.restore_trash → lee .trashinfo y mueve files/<name> de vuelta a origin
        """
        entry = self.load(entry_id)
        if entry is None or entry.status != expected_status:
            return False

        op = json.loads(entry.inverse_op)
        op_type: str = op.get("type", "")
        parameters: dict[str, object] = op.get("parameters", {})

        if op_type == "file.move":
            # inverse: mueve destination→origin
            dest = str(op.get("target", entry.destination or ""))
            origin = str(parameters.get("destination", entry.origin))
            shutil.move(dest, origin)

        elif op_type == "file.delete":
            # inverse: elimina el archivo recién escrito (new-file write undo)
            target = str(op.get("target", entry.origin))
            Path(target).unlink(missing_ok=True)

        elif op_type == "file.write":
            # inverse: restaura desde el backup de sobreescritura
            backup_path = self._backup_base_dir / entry_id
            dest_path = Path(str(op.get("target", entry.origin)))
            shutil.copy2(str(backup_path), str(dest_path))

        elif op_type == "file.restore_trash":
            # inverse: lee el .trashinfo y mueve files/<name> de vuelta a origin
            trashinfo_path = Path(str(parameters.get("trashinfo_path", "")))
            # Leer el field Path= del .trashinfo
            trashinfo_content = trashinfo_path.read_text(encoding="utf-8")
            trash_origin: str | None = None
            for line in trashinfo_content.splitlines():
                if line.startswith("Path="):
                    trash_origin = line[len("Path=") :]
                    break
            if trash_origin is None:
                return False
            # El archivo en trash está en .../files/<basename>
            files_dir = trashinfo_path.parent.parent / "files"
            trashed_file = files_dir / trashinfo_path.stem
            shutil.move(str(trashed_file), entry.origin)

        else:
            # Tipo no reconocido — no revertir, retornar False
            return False

        self.mark_rolled_back(entry_id)
        return True

    # ------------------------------------------------------------------
    # Transiciones de estado
    # ------------------------------------------------------------------

    def mark_applied(self, entry_id: str) -> None:
        """Tras ejecución exitosa, marca status='applied'."""
        resolved_at = datetime.now(UTC).isoformat()
        self._conn.execute(
            "UPDATE undo_entries SET status='applied', resolved_at=? WHERE id=?",
            (resolved_at, entry_id),
        )
        self._conn.commit()

    def mark_rolled_back(self, entry_id: str) -> None:
        """Tras restore(), marca status='rolled_back'."""
        resolved_at = datetime.now(UTC).isoformat()
        self._conn.execute(
            "UPDATE undo_entries SET status='rolled_back', resolved_at=? WHERE id=?",
            (resolved_at, entry_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Context manager + lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Cierra la conexion SQLite subyacente."""
        self._conn.close()

    def __enter__(self) -> "UndoJournal":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _apply_schema(self) -> None:
        self._conn.execute(CREATE_JOURNAL)
        self._conn.commit()
