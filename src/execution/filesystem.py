"""FileSystemAdapter (EXEC-02, EXEC-03 mutating side, EXEC-04): Tool-port adapter con
segunda muralla de resolución de paths, verificación post-ejecución y journal ANTES de mutar.

Diseño (D-64 .. D-68):
- D-64: file.delete usa send2trash, NO unlink (recuperable).
- D-65: journal.record() se llama ANTES de cualquier mutación (para rollback en ABORT).
- D-67: verify() por tipo: write→size+sha256; move→dest∧¬src; delete→¬path∧in-trash.
- D-68: Segunda muralla — _resolve_target() llama Path.resolve() (expanduser+symlinks),
  reconstruye la Action con la ruta real y re-corre CognitivePolicyEngine.evaluate.
  CognitivePolicyEngine._normalize() solo llama expanduser (NO resolve); el adapter
  cierra ese gap. Si risk_level > max_risk OR resolved != original → bloquea + audita.

Constraint de imports (import-linter independence):
  PERMITIDO: core.*, stdlib, send2trash, execution.journal
  PROHIBIDO: orchestrator, agents, knowledge, gateway, audit (no cruzar entre capas)
"""

import hashlib
import os
import shutil
from pathlib import Path

from send2trash import send2trash  # type: ignore[import-untyped]

from core.domain.audit import ActorType, AuditEvent, AuditEventType
from core.domain.execution import ToolResult, Verification
from core.domain.plan import Action, Plan
from core.domain.risk import RiskLevel
from core.policy.engine import CognitivePolicyEngine
from execution.journal import UndoJournal


def _resolve_target(target: str) -> str:
    """Expande ~ Y resuelve symlinks. ~/Data -> /mnt/hdd/Data en este entorno.

    Diferencia crítica vs CognitivePolicyEngine._normalize():
    engine solo llama os.path.expanduser; este helper también llama Path.resolve()
    para seguir symlinks. Esa es la brecha que cierra la segunda muralla (D-68).
    """
    return str(Path(os.path.expanduser(target)).resolve())


def _get_str(params: object, key: str, default: str = "") -> str:
    """Extrae un string de un Mapping[str, object] para mypy strict."""
    from collections.abc import Mapping as _Mapping

    if isinstance(params, _Mapping):
        val = params.get(key, default)
        return str(val) if val is not None else default
    return default


def _get_int(params: object, key: str, default: int = 0) -> int:
    """Extrae un int de un Mapping[str, object] para mypy strict."""
    from collections.abc import Mapping as _Mapping

    if isinstance(params, _Mapping):
        val = params.get(key, default)
        if isinstance(val, int):
            return val
        try:
            return int(str(val))
        except (ValueError, TypeError):
            return default
    return default


def _sha256(path: Path) -> str:
    """SHA-256 en chunks de 64 KiB. NUNCA hashear 2 TB entero (RESEARCH Anti-Patterns)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class FileSystemAdapter:
    """Adapter del port Tool para operaciones de sistema de archivos.

    Implementa los 5 miembros del protocolo Tool (src/core/ports/execution.py):
    name, max_risk, describe(), execute(), verify().

    Inyección de dependencias (constructor):
      - engine: CognitivePolicyEngine — para la segunda muralla (D-68)
      - audit: objeto con método .log(AuditEvent) — para bloqueos + eventos
      - journal: UndoJournal — para registrar inversa ANTES de mutar (D-65)
    """

    def __init__(
        self,
        engine: CognitivePolicyEngine,
        audit: object,
        journal: UndoJournal,
    ) -> None:
        self._engine = engine
        self._audit = audit
        self._journal = journal

    @property
    def name(self) -> str:
        return "filesystem"

    @property
    def max_risk(self) -> RiskLevel:
        # Maneja file.delete (nivel C) → max_risk = C
        return RiskLevel.C

    def describe(self, action: Action) -> str:
        return f"{action.type}({action.target})"

    # ------------------------------------------------------------------
    # Segunda muralla (D-68)
    # ------------------------------------------------------------------

    def _second_wall(
        self, action: Action
    ) -> tuple[bool, str, str]:
        """Resuelve el path real y re-evalúa con el engine de política.

        Returns:
            (allowed, resolved_target, reason)
            allowed=False significa BLOQUEAR antes de cualquier I/O.
        """
        resolved_target = _resolve_target(action.target)

        # Reconstruir Action con la ruta resuelta (frozen — no mutar)
        resolved_action = Action(
            type=action.type,
            target=resolved_target,
            parameters=action.parameters,
            on_error=action.on_error,
            retry_params=action.retry_params,
        )
        resolved_plan = Plan(
            task_id="second-wall",
            summary="second-wall check",
            steps=(resolved_action,),
            rationale="path-resolution re-eval",
        )
        decision = self._engine.evaluate(resolved_plan)

        # Condición de bloqueo: riesgo excede max_risk OR path cambió (path tricks)
        if decision.risk_level > self.max_risk:
            reason = f"risk_level={decision.risk_level.name} > max_risk={self.max_risk.name}"
            self._audit_blocked(action.target, resolved_target, str(decision.risk_level), reason)
            return False, resolved_target, reason

        if resolved_target != action.target:
            reason = f"resolved path differs from original (path tricks): {action.target!r} -> {resolved_target!r}"
            self._audit_blocked(action.target, resolved_target, str(decision.risk_level), reason)
            return False, resolved_target, reason

        return True, resolved_target, ""

    def _audit_blocked(
        self,
        original: str,
        resolved: str,
        level: str,
        reason: str,
    ) -> None:
        """Registra evento de auditoría para bloqueo por segunda muralla."""
        event = AuditEvent.new(
            actor_type=ActorType.SYSTEM,
            actor_id="filesystem",
            event_type=AuditEventType.ACTION_COMPLETED,
            message=f"blocked: second wall — {reason}",
            payload={
                "blocked": "second_wall",
                "original": original,
                "resolved": resolved,
                "level": level,
                "reason": reason,
            },
        )
        self._audit.log(event)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def execute(self, action: Action) -> ToolResult:
        """Ejecuta la acción tras pasar la segunda muralla y registrar en journal.

        Orden obligatorio (D-65, D-68):
        1. Segunda muralla: resolver path + re-evaluar engine → bloquear si falla.
        2. journal.record() ANTES de la mutación.
        3. Mutación real (write / move / delete via send2trash).
        """
        allowed, resolved_target, reason = self._second_wall(action)
        if not allowed:
            return ToolResult(
                success=False,
                detail="blocked: second wall",
                payload={"reason": reason, "resolved": resolved_target},
            )

        resolved_path = Path(resolved_target)

        try:
            if action.type == "file.write":
                return await self._execute_write(action, resolved_path)
            elif action.type == "file.move":
                return await self._execute_move(action, resolved_path)
            elif action.type == "file.delete":
                return await self._execute_delete(action, resolved_path)
            else:
                return ToolResult(
                    success=False,
                    detail=f"unsupported action type: {action.type!r}",
                    payload={"resolved_target": resolved_target},
                )
        except Exception as exc:
            return ToolResult(
                success=False,
                detail=f"execution error: {exc}",
                payload={"resolved_target": resolved_target},
            )

    async def _execute_write(self, action: Action, resolved_path: Path) -> ToolResult:
        """file.write: journal antes de mutar, luego escribe y computa size+sha256."""
        content = action.parameters.get("content", "")

        if resolved_path.exists():
            # Sobrescritura: capturar backup antes del journal.record
            entry_id = self._journal.record(
                task_id=_get_str(action.parameters, "task_id", "unknown"),
                step_index=_get_int(action.parameters, "step_index", 0),
                action_type=action.type,
                origin=str(resolved_path),
                destination=None,
                inverse_op={
                    "type": "file.write",
                    "target": str(resolved_path),
                    "parameters": {},  # backup_path se añade luego
                },
            )
            # Capturar backup DESPUÉS de obtener entry_id (necesitamos el id para el nombre)
            try:
                self._journal.capture_overwrite_backup(entry_id, resolved_path)
            except Exception:
                pass  # Si falla el backup, continuamos — la entrada ya está en journal
        else:
            # Archivo nuevo: la inversa es borrarlo
            entry_id = self._journal.record(
                task_id=_get_str(action.parameters, "task_id", "unknown"),
                step_index=_get_int(action.parameters, "step_index", 0),
                action_type=action.type,
                origin=str(resolved_path),
                destination=None,
                inverse_op={
                    "type": "file.delete",
                    "target": str(resolved_path),
                    "parameters": {},
                },
            )

        # Mutación real
        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            resolved_path.write_bytes(content)
        else:
            resolved_path.write_text(str(content), encoding="utf-8")

        size = resolved_path.stat().st_size
        sha256 = _sha256(resolved_path)

        self._journal.mark_applied(entry_id)
        return ToolResult(
            success=True,
            detail=f"wrote {size} bytes to {resolved_path}",
            payload={
                "resolved_target": str(resolved_path),
                "size": size,
                "sha256": sha256,
            },
        )

    async def _execute_move(self, action: Action, resolved_src: Path) -> ToolResult:
        """file.move: shutil.move (EXDEV-safe, cross-FS NTFS↔ext4), journal antes."""
        dest_str = str(action.parameters.get("destination", ""))
        if not dest_str:
            return ToolResult(
                success=False,
                detail="file.move requires 'destination' parameter",
                payload={},
            )
        dest_path = Path(_resolve_target(dest_str))

        # journal ANTES de mover
        entry_id = self._journal.record(
            task_id=_get_str(action.parameters, "task_id", "unknown"),
            step_index=_get_int(action.parameters, "step_index", 0),
            action_type=action.type,
            origin=str(resolved_src),
            destination=str(dest_path),
            inverse_op={
                "type": "file.move",
                "target": str(dest_path),
                "parameters": {"destination": str(resolved_src)},
            },
        )

        # Mutación — shutil.move maneja EXDEV (cross-FS NTFS↔ext4)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(resolved_src), str(dest_path))

        self._journal.mark_applied(entry_id)
        return ToolResult(
            success=True,
            detail=f"moved {resolved_src} -> {dest_path}",
            payload={"resolved_target": str(dest_path)},
        )

    async def _execute_delete(self, action: Action, resolved_path: Path) -> ToolResult:
        """file.delete: send2trash (no unlink — D-64); journal con trashinfo path antes."""
        if not resolved_path.exists():
            return ToolResult(
                success=False,
                detail=f"file not found: {resolved_path}",
                payload={},
            )

        # Determinar la ruta de trash esperada para el journal y verify()
        trash_path = self._expected_trash_path(resolved_path)
        trashinfo_path = self._expected_trashinfo_path(resolved_path)

        # journal ANTES de send2trash (D-65)
        entry_id = self._journal.record(
            task_id=_get_str(action.parameters, "task_id", "unknown"),
            step_index=_get_int(action.parameters, "step_index", 0),
            action_type=action.type,
            origin=str(resolved_path),
            destination=str(trash_path),
            inverse_op={
                "type": "file.restore_trash",
                "target": str(resolved_path),
                "parameters": {
                    "trashinfo_path": str(trashinfo_path),
                    "trash_path": str(trash_path),
                },
            },
        )

        # Mutación — send2trash (NO unlink — recoverable)
        send2trash(str(resolved_path))

        # Determinar la ruta real del archivo en trash post-delete
        # send2trash puede elegir el nombre final (añade sufijo si colisión)
        actual_trash_path = self._find_actual_trash_path(resolved_path)

        self._journal.mark_applied(entry_id)
        return ToolResult(
            success=True,
            detail=f"trashed {resolved_path}",
            payload={
                "resolved_target": str(resolved_path),
                "trash_path": str(actual_trash_path or trash_path),
            },
        )

    # ------------------------------------------------------------------
    # Trash path helpers
    # ------------------------------------------------------------------

    def _expected_trash_path(self, path: Path) -> Path:
        """Determina la ruta esperada en trash según el volumen (RESEARCH Pattern 3).

        Files en /mnt/hdd van a /mnt/hdd/.Trash-1000/files/
        Files en ~ van a ~/.local/share/Trash/files/
        """
        path_str = str(path.resolve())
        if path_str.startswith("/mnt/hdd"):
            trash_dir = Path("/mnt/hdd/.Trash-1000/files")
        else:
            trash_dir = Path.home() / ".local" / "share" / "Trash" / "files"
        return trash_dir / path.name

    def _expected_trashinfo_path(self, path: Path) -> Path:
        """Determina la ruta esperada del .trashinfo para el archivo."""
        path_str = str(path.resolve())
        if path_str.startswith("/mnt/hdd"):
            trashinfo_dir = Path("/mnt/hdd/.Trash-1000/info")
        else:
            trashinfo_dir = Path.home() / ".local" / "share" / "Trash" / "info"
        return trashinfo_dir / f"{path.name}.trashinfo"

    def _find_actual_trash_path(self, original_path: Path) -> Path | None:
        """Busca el archivo real en trash tras el send2trash (puede tener sufijo numérico)."""
        expected = self._expected_trash_path(original_path)
        if expected.exists():
            return expected
        # Buscar con sufijo numérico (colisiones en trash)
        parent = expected.parent
        stem = original_path.stem
        suffix = original_path.suffix
        if parent.exists():
            for candidate in parent.iterdir():
                name = candidate.name
                if name == original_path.name or (
                    name.startswith(stem) and name.endswith(suffix)
                ):
                    return candidate
        return None

    # ------------------------------------------------------------------
    # Verify (D-67)
    # ------------------------------------------------------------------

    async def verify(self, action: Action, result: ToolResult) -> Verification:
        """Verificación post-ejecución por tipo de acción (D-67).

        write → size + sha256 coinciden
        move  → dest existe & src ausente
        delete→ original ausente & trash_path presente
        else  → pasa si result.success
        """
        if not result.success:
            return Verification(passed=False, detail="execute failed")

        resolved = Path(str(result.payload.get("resolved_target", action.target)))

        if action.type == "file.write":
            expected_hash = str(result.payload.get("sha256", ""))
            expected_size = result.payload.get("size")
            if not resolved.exists():
                return Verification(passed=False, detail="file not found after write")
            actual_size = resolved.stat().st_size
            actual_hash = _sha256(resolved)
            passed = actual_size == expected_size and actual_hash == expected_hash
            return Verification(
                passed=passed,
                detail=f"sha256={'ok' if passed else 'mismatch'} size={'ok' if actual_size == expected_size else 'mismatch'}",
            )

        if action.type == "file.move":
            src = Path(os.path.expanduser(action.target))
            passed = resolved.exists() and not src.exists()
            return Verification(
                passed=passed,
                detail="dest exists & src absent" if passed else "move verify failed",
            )

        if action.type == "file.delete":
            trash_path = Path(str(result.payload.get("trash_path", "")))
            passed = not resolved.exists() and (trash_path.exists() if str(trash_path) else False)
            return Verification(
                passed=passed,
                detail="absent & in trash" if passed else "delete verify failed",
            )

        return Verification(passed=result.success, detail="no type-specific verify")
