"""ShellAdapter — adapter de ejecución de shell (D-66, EXEC-01).

Implementa el puerto `Tool` para ejecutar binarios arbitrarios de forma controlada:
  - Allowlist fail-closed: binarios fuera de `allowed_binaries` son rechazados y auditados
    sin spawnar ningún proceso (T-06-ALLOW-1).
  - argv exec: siempre usa `asyncio.create_subprocess_exec` (shell=False — nunca shell=True).
    No hay expansión de metacaracteres de shell (T-shell-injection).
  - Timeout: `asyncio.wait_for` + `proc.kill()` + `communicate()` drain para evitar zombies
    (T-06-ALLOW-2).

Las mutaciones de archivos deben ir por `FileSystemAdapter`, no aquí — los comandos de shell
no son reversibles y ShellAdapter no genera entradas en el UndoJournal.

Importaciones: solo `core.*` + stdlib (invariante de import-linter).
"""

import asyncio
import shutil
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from core.domain.audit import ActorType, AuditEvent, AuditEventType
from core.domain.execution import ToolResult, Verification
from core.domain.plan import Action
from core.domain.risk import RiskLevel
from core.ports.audit import AuditPort


class ShellAdapter:
    """Adapter de shell que ejecuta solo binarios en el allowlist, vía argv (shell=False).

    Constructor acepta `allowed_binaries` directamente (para tests) o `config_path` para
    cargar la allowlist desde TOML (`allowed_binaries = ["echo", "grep", ...]`). Si ambos
    se proveen, `allowed_binaries` tiene precedencia. Si ninguno se provee, la allowlist
    queda vacía (todo bloqueado — fail-closed por diseño).

    `action.target` contiene el binario; `action.parameters["args"]` contiene la lista de
    argumentos adicionales (taxonomía: target=comando, parameters=opciones/argumentos).
    """

    def __init__(
        self,
        audit: AuditPort,
        *,
        allowed_binaries: set[str] | None = None,
        config_path: str | Path | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._audit = audit
        self._timeout_s = timeout_s

        if allowed_binaries is not None:
            self._allowed_binaries: set[str] = set(allowed_binaries)
        elif config_path is not None:
            self._allowed_binaries = self._load_allowlist(Path(config_path))
        else:
            self._allowed_binaries = set()  # fail-closed: nada permitido por defecto

    @staticmethod
    def _load_allowlist(config_path: Path) -> set[str]:
        """Carga `allowed_binaries` desde un archivo TOML (stdlib tomllib)."""
        with open(config_path, "rb") as f:
            cfg = tomllib.load(f)
        return set(cfg.get("allowed_binaries", []))

    # ------------------------------------------------------------------
    # Tool protocol — cinco miembros obligatorios
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "shell"

    @property
    def max_risk(self) -> RiskLevel:
        return RiskLevel.B  # side-effects de shell; deletes/writes van por FileSystemAdapter

    def describe(self, action: Action) -> str:
        raw_args = cast(Sequence[object], action.parameters.get("args", []))
        args_str = " ".join(str(a) for a in raw_args) if raw_args else ""
        return f"shell: {action.target} {args_str}".strip()

    async def execute(self, action: Action) -> ToolResult:
        """Ejecuta `action.target` con `action.parameters['args']` vía argv (shell=False).

        Si el binario no está en el allowlist: loguea un AuditEvent y retorna
        ToolResult(success=False) sin spawnar ningún proceso (D-66, fail-closed).
        """
        binary = action.target
        raw_args = cast(Sequence[object], action.parameters.get("args", []))
        args: list[str] = [str(a) for a in raw_args]

        # --- Allowlist check (fail-closed, D-66) ---
        if binary not in self._allowed_binaries:
            self._audit.log(
                AuditEvent.new(
                    actor_type=ActorType.SYSTEM,
                    actor_id=self.name,
                    event_type=AuditEventType.ACTION_COMPLETED,
                    message=f"binario '{binary}' bloqueado por allowlist",
                    payload={"blocked": "allowlist", "binary": binary},
                )
            )
            return ToolResult(
                success=False,
                detail=f"binario '{binary}' no está en el allowlist (blocked)",
                payload={"blocked": "allowlist", "binary": binary},
            )

        # --- argv exec (shell=False, D-66) ---
        try:
            returncode, stdout, stderr = await self._exec_allowed(
                binary=binary, args=args, timeout_s=self._timeout_s
            )
        except FileNotFoundError as exc:
            return ToolResult(
                success=False,
                detail=str(exc),
                payload={"returncode": -1, "stdout": "", "stderr": str(exc)},
            )
        except TimeoutError:
            return ToolResult(
                success=False,
                detail=f"timeout ({self._timeout_s}s) ejecutando '{binary}'",
                payload={"returncode": -1, "stdout": "", "stderr": "timeout"},
            )

        success = returncode == 0
        return ToolResult(
            success=success,
            detail=f"returncode={returncode}",
            payload={"returncode": returncode, "stdout": stdout, "stderr": stderr},
        )

    async def verify(self, action: Action, result: ToolResult) -> Verification:
        """Pasa solo cuando la ejecución fue exitosa Y el returncode es 0."""
        returncode = result.payload.get("returncode")
        passed = result.success and returncode == 0
        return Verification(passed=passed, detail=f"returncode={returncode}")

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    async def _exec_allowed(
        self, binary: str, args: list[str], timeout_s: float
    ) -> tuple[int, str, str]:
        """Resuelve y ejecuta `binary` vía argv. NUNCA usa shell=True (D-66).

        El binary ya fue validado contra el allowlist por el llamador.
        Raises FileNotFoundError si `shutil.which` no lo encuentra en PATH.
        Raises asyncio.TimeoutError si el proceso supera `timeout_s`; el proceso
        es matado y drenado para evitar zombies (T-06-ALLOW-2).
        """
        resolved = shutil.which(binary)
        if resolved is None:
            raise FileNotFoundError(f"binario no encontrado en PATH: '{binary}'")

        proc = await asyncio.create_subprocess_exec(
            resolved,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError:
            proc.kill()
            await proc.communicate()  # drain para evitar zombie
            raise

        rc = proc.returncode if proc.returncode is not None else -1
        return rc, stdout_b.decode(errors="replace"), stderr_b.decode(errors="replace")
