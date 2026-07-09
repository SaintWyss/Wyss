"""GitAdapter — adapter de ejecución git (D-66, EXEC-01).

Implementa el puerto `Tool` para ejecutar subcomandos `git` de forma controlada:
  - Allowlist de subcomandos fail-closed: subcomandos fuera de `allowed_subcommands`
    son rechazados y auditados sin spawnar ningún proceso (T-06-ALLOW-1).
  - argv exec: siempre usa `asyncio.create_subprocess_exec` (shell=False — nunca shell=True).
    No hay expansión de metacaracteres de shell (T-shell-injection).
  - Timeout: `asyncio.wait_for` + `proc.kill()` + `communicate()` drain (T-06-ALLOW-2).
  - No GitPython — invoca el binario `git` directamente (no está en el stack).

`action.target` contiene el subcomando git (ej. "status"); `action.parameters["args"]`
contiene los argumentos adicionales. El `cwd` del proceso es `self._repo_path`.

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

# Subcomandos git permitidos por defecto (pueden sobreescribirse vía TOML o constructor)
DEFAULT_ALLOWED_SUBCOMMANDS: frozenset[str] = frozenset(
    {"status", "diff", "add", "commit", "log"}
)

# Subcomandos de lectura (PR-11): clasifican nivel A en la política, así que NO pueden
# aceptar flags con capacidad de escritura — `git log --output=<archivo>` escribe.
_READ_SUBCOMMANDS: frozenset[str] = frozenset({"status", "log", "diff"})


def _has_write_capable_flag(args: Sequence[str]) -> str | None:
    """Devuelve el flag ofensivo si algún arg puede escribir a disco, o None."""
    for arg in args:
        if arg == "-o" or arg.startswith("--output"):
            return arg
    return None


class GitAdapter:
    """Adapter git que ejecuta solo subcomandos en el allowlist, vía argv (shell=False).

    Constructor acepta `allowed_subcommands` directamente (para tests) o `config_path`
    para cargar desde TOML (`allowed_git_subcommands = ["status", "diff", ...]`). Si
    ninguno se provee, usa `DEFAULT_ALLOWED_SUBCOMMANDS`.

    El binario `git` debe estar en PATH; se resuelve via `shutil.which` una sola vez
    en `_ensure_git_binary`. Si no se encuentra, `execute()` retorna failure.
    """

    def __init__(
        self,
        audit: AuditPort,
        repo_path: str | Path,
        *,
        allowed_subcommands: set[str] | frozenset[str] | None = None,
        config_path: str | Path | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._audit = audit
        self._repo_path = Path(repo_path)
        self._timeout_s = timeout_s
        self._git_binary: str | None = None  # resuelto lazy en primer uso

        if allowed_subcommands is not None:
            self._allowed_subcommands: frozenset[str] = frozenset(allowed_subcommands)
        elif config_path is not None:
            self._allowed_subcommands = self._load_allowlist(Path(config_path))
        else:
            self._allowed_subcommands = DEFAULT_ALLOWED_SUBCOMMANDS

    @staticmethod
    def _load_allowlist(config_path: Path) -> frozenset[str]:
        """Carga `allowed_git_subcommands` desde TOML (stdlib tomllib)."""
        with open(config_path, "rb") as f:
            cfg = tomllib.load(f)
        return frozenset(cfg.get("allowed_git_subcommands", list(DEFAULT_ALLOWED_SUBCOMMANDS)))

    def _resolve_git(self) -> str | None:
        """Resuelve el binario `git` en PATH. Cacheado tras el primer uso."""
        if self._git_binary is None:
            self._git_binary = shutil.which("git")
        return self._git_binary

    # ------------------------------------------------------------------
    # Tool protocol — cinco miembros obligatorios
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "git"

    @property
    def max_risk(self) -> RiskLevel:
        return RiskLevel.B  # operaciones git con side-effects controlados

    def describe(self, action: Action) -> str:
        raw_args = cast(Sequence[object], action.parameters.get("args", []))
        args_str = " ".join(str(a) for a in raw_args) if raw_args else ""
        return f"git: {action.target} {args_str}".strip()

    async def execute(self, action: Action) -> ToolResult:
        """Ejecuta `git <subcommand> <args>` en `repo_path` vía argv (shell=False).

        Si el subcomando no está en el allowlist: loguea AuditEvent y retorna
        ToolResult(success=False) sin spawnar ningún proceso (D-66, fail-closed).
        """
        subcommand = action.target
        raw_args = cast(Sequence[object], action.parameters.get("args", []))
        args: list[str] = [str(a) for a in raw_args]

        # --- Allowlist check (fail-closed, D-66) ---
        if subcommand not in self._allowed_subcommands:
            self._audit.log(
                AuditEvent.new(
                    actor_type=ActorType.SYSTEM,
                    actor_id=self.name,
                    event_type=AuditEventType.ACTION_COMPLETED,
                    message=f"subcomando git '{subcommand}' bloqueado por allowlist",
                    payload={"blocked": "allowlist", "binary": subcommand},
                )
            )
            return ToolResult(
                success=False,
                detail=f"subcomando git '{subcommand}' no está en el allowlist (blocked)",
                payload={"blocked": "allowlist", "binary": subcommand},
            )

        # --- Flags de escritura en subcomandos de lectura (PR-11, fail-closed) ---
        if subcommand in _READ_SUBCOMMANDS:
            offending = _has_write_capable_flag(args)
            if offending is not None:
                self._audit.log(
                    AuditEvent.new(
                        actor_type=ActorType.SYSTEM,
                        actor_id=self.name,
                        event_type=AuditEventType.ACTION_COMPLETED,
                        message=(
                            f"flag con capacidad de escritura '{offending}' bloqueado "
                            f"en subcomando de lectura 'git {subcommand}'"
                        ),
                        payload={"blocked": "write_flag", "flag": offending},
                    )
                )
                return ToolResult(
                    success=False,
                    detail=(
                        f"flag '{offending}' no permitido en 'git {subcommand}' "
                        "(lectura nivel A no puede escribir a disco)"
                    ),
                    payload={"blocked": "write_flag", "flag": offending},
                )

        # --- Resolver binario git ---
        resolved_git = self._resolve_git()
        if resolved_git is None:
            return ToolResult(
                success=False,
                detail="binario 'git' no encontrado en PATH",
                payload={"returncode": -1, "stdout": "", "stderr": "git not found"},
            )

        # --- argv exec (shell=False, D-66) ---
        try:
            returncode, stdout, stderr = await self._exec_git(
                resolved_git=resolved_git,
                subcommand=subcommand,
                args=args,
                timeout_s=self._timeout_s,
            )
        except TimeoutError:
            return ToolResult(
                success=False,
                detail=f"timeout ({self._timeout_s}s) ejecutando 'git {subcommand}'",
                payload={"returncode": -1, "stdout": "", "stderr": "timeout"},
            )

        success = returncode == 0
        return ToolResult(
            success=success,
            detail=f"git returncode={returncode}",
            payload={"returncode": returncode, "stdout": stdout, "stderr": stderr},
        )

    async def verify(self, action: Action, result: ToolResult) -> Verification:
        """Pasa solo cuando la ejecución fue exitosa Y el returncode es 0."""
        returncode = result.payload.get("returncode")
        passed = result.success and returncode == 0
        return Verification(passed=passed, detail=f"git returncode={returncode}")

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    async def _exec_git(
        self,
        resolved_git: str,
        subcommand: str,
        args: list[str],
        timeout_s: float,
    ) -> tuple[int, str, str]:
        """Ejecuta `git <subcommand> <args>` en `repo_path`. NUNCA usa shell=True (D-66).

        Raises asyncio.TimeoutError si supera `timeout_s`; el proceso es matado y
        drenado para evitar zombies (T-06-ALLOW-2).
        """
        proc = await asyncio.create_subprocess_exec(
            resolved_git,
            subcommand,
            *args,
            cwd=str(self._repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except TimeoutError:
            proc.kill()
            await proc.communicate()  # drain para evitar zombie
            raise

        rc = proc.returncode if proc.returncode is not None else -1
        return rc, stdout_b.decode(errors="replace"), stderr_b.decode(errors="replace")
