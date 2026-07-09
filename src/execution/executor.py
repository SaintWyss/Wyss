"""PlanExecutor (D-69, EXEC-03 rollback + EXEC-02 enforcement).

Step loop que conduce un Plan confirmado a través de los adapters:
- Despacha cada Action al adapter correcto por prefijo de action.type
- Verifica cada paso post-ejecución; verify.passed=False es falla del paso
- Enforcea Action.on_error (ABORT / RETRY / ESCALATE):
  - ABORT (default): para y llama journal.restore en orden INVERSO sobre los
    pasos ya aplicados (D-65 / T-undo-corruption).
  - RETRY: re-ejecuta hasta RetryParams.max_attempts con backoff exponencial
    capped en backoff_max_s (T-06-EXEC-2).
  - ESCALATE: registra evento TASK_FAILED/escalate en AuditPort y propaga la
    falla SIN rollback (T-06-EXEC-1 / ORCH-07).

Constraint de imports (import-linter independence):
  PERMITIDO: core.*, execution.*, asyncio, dataclasses
  PROHIBIDO: orchestrator, agents, knowledge, gateway, audit (no cruzar capas)
"""

import asyncio
from dataclasses import dataclass, field

from core.domain.audit import ActorType, AuditEvent, AuditEventType
from core.domain.execution import ToolResult, Verification
from core.domain.plan import Action, ErrorPolicy, Plan, RetryParams
from execution.filesystem import FileSystemAdapter
from execution.git import GitAdapter
from execution.journal import UndoJournal
from execution.shell import ShellAdapter


@dataclass(frozen=True, slots=True)
class ExecutorResult:
    """Resultado del loop de ejecución del PlanExecutor.

    `success=True` solo si todos los pasos completaron y verificaron correctamente.
    `detail` resume el resultado (o la causa de fallo).
    `applied_entries` lista los entry_ids del journal que fueron aplicados
    (útil para auditoría post-ejecución).
    `failed_step` es el índice (base-0) del paso que falló, o None en éxito.
    `outputs` (PR-11) son las salidas visibles de los pasos de lectura
    (payload "output" de file.read/list/stat, o "stdout" de git/shell) — es lo
    que el daemon devuelve al owner para que un operador que lee pueda mostrar.
    """

    success: bool
    detail: str
    applied_entries: tuple[str, ...] = field(default_factory=tuple)
    failed_step: int | None = None
    outputs: tuple[str, ...] = field(default_factory=tuple)


def _visible_output(result: ToolResult) -> str | None:
    """Salida visible de un paso: 'output' (lecturas de fs) o 'stdout' (git/shell)."""
    try:
        output = result.payload.get("output")
        if isinstance(output, str) and output:
            return output
        stdout = result.payload.get("stdout")
        if isinstance(stdout, str) and stdout:
            return stdout
    except AttributeError:
        pass
    return None


class PlanExecutor:
    """Ejecuta un Plan confirmado paso a paso, enforcando on_error por Action.

    Constructor requiere los tres adapters (filesystem, shell, git), el UndoJournal
    (para grabar/restaurar entradas) y el AuditPort (para eventos ESCALATE).

    Uso típico (dentro del dispatcher del daemon, Fase 05):
        executor = PlanExecutor(filesystem=..., shell=..., git=...,
                                journal=..., audit=...)
        result = await executor.run(plan)
    """

    def __init__(
        self,
        *,
        filesystem: FileSystemAdapter,
        shell: ShellAdapter,
        git: GitAdapter,
        journal: UndoJournal,
        audit: object,  # AuditPort — Protocol, tipado como object para evitar import circular
    ) -> None:
        self._filesystem = filesystem
        self._shell = shell
        self._git = git
        self._journal = journal
        self._audit = audit

    # ------------------------------------------------------------------
    # Dispatch por prefijo
    # ------------------------------------------------------------------

    def _adapter_for(self, action: Action) -> FileSystemAdapter | ShellAdapter | GitAdapter:
        """Devuelve el adapter correcto basado en el prefijo de action.type.

        Taxonomía de prefijos:
          "file.*" → FileSystemAdapter
          "shell.*" → ShellAdapter
          "git.*"  → GitAdapter

        Levanta ValueError para prefijos desconocidos (fail-closed, D-69).
        """
        prefix = action.type.split(".")[0]
        if prefix == "file":
            return self._filesystem
        if prefix == "shell":
            return self._shell
        if prefix == "git":
            return self._git
        raise ValueError(f"no adapter for action type: {action.type!r}")

    # ------------------------------------------------------------------
    # Retry helper con backoff exponencial (PATTERNS lines 365-378)
    # ------------------------------------------------------------------

    async def _retry_with_backoff(
        self,
        adapter: FileSystemAdapter | ShellAdapter | GitAdapter,
        action: Action,
        params: RetryParams,
    ) -> ToolResult:
        """Re-ejecuta action en adapter hasta params.max_attempts veces.

        Backoff: empieza en backoff_base_s, se dobla en cada intento fallido,
        capped en backoff_max_s. El sleep se omite en el último intento.
        Devuelve el primer ToolResult exitoso, o la última falla si se agota.
        """
        attempt = 0
        delay = params.backoff_base_s
        last_result: ToolResult | None = None
        while attempt < params.max_attempts:
            result = await adapter.execute(action)
            if result.success:
                return result
            last_result = result
            attempt += 1
            if attempt < params.max_attempts:
                await asyncio.sleep(min(delay, params.backoff_max_s))
                delay *= 2
        # Retorna la última falla (last_result nunca es None aquí porque
        # params.max_attempts >= 1 y siempre hay al menos un intento)
        assert last_result is not None
        return last_result

    # ------------------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------------------

    async def run(self, plan: Plan) -> ExecutorResult:
        """Ejecuta todos los pasos del plan en orden, enforcando on_error.

        Registra en `applied_entries` cada entry_id de journal devuelto por
        el payload de ToolResult (clave "journal_entry_id"). Usa estos ids
        para el rollback ABORT en orden inverso.

        Retorna ExecutorResult(success=True) si todos los pasos completaron
        y verificaron; de lo contrario ExecutorResult(success=False, ...).
        """
        # Lista mutable de (step_index, entry_id) para rollback en orden inverso
        applied_entry_ids: list[str] = []
        step_outputs: list[str] = []

        for step_index, action in enumerate(plan.steps):
            adapter = self._adapter_for(action)

            # --- Ejecutar paso (con RETRY el backoff loop lo maneja todo) ---
            if action.on_error == ErrorPolicy.RETRY:
                params = action.retry_params or RetryParams()
                result = await self._retry_with_backoff(adapter, action, params)
            else:
                result = await adapter.execute(action)

            # --- Registrar entry_id si el adapter lo devolvió ---
            entry_id: str | None = None
            if isinstance(result.payload, dict):
                raw = result.payload.get("journal_entry_id")
                if isinstance(raw, str):
                    entry_id = raw
            else:
                # Mapping genérico — acceder vía .get si disponible
                try:
                    raw = result.payload.get("journal_entry_id")
                    if isinstance(raw, str):
                        entry_id = raw
                except AttributeError:
                    pass

            # --- Verificar paso (solo si execute tuvo éxito) ---
            step_failed = not result.success
            if result.success:
                verification: Verification = await adapter.verify(action, result)
                if not verification.passed:
                    step_failed = True

            # --- Si el paso pasó, acumular entry_id ---
            if not step_failed and entry_id is not None:
                applied_entry_ids.append(entry_id)

            # --- Aflorar salida visible del paso (PR-11: lecturas) ---
            if not step_failed:
                output = _visible_output(result)
                if output:
                    step_outputs.append(output)

            # --- Manejar falla del paso según on_error ---
            if step_failed:
                return await self._handle_failure(
                    plan=plan,
                    action=action,
                    step_index=step_index,
                    applied_entry_ids=applied_entry_ids,
                    result=result,
                )

        # --- Todos los pasos completaron con éxito ---
        for eid in applied_entry_ids:
            self._journal.mark_applied(eid)

        return ExecutorResult(
            success=True,
            detail=f"plan {plan.task_id!r} completado ({len(plan.steps)} pasos)",
            applied_entries=tuple(applied_entry_ids),
            failed_step=None,
            outputs=tuple(step_outputs),
        )

    # ------------------------------------------------------------------
    # Manejo de fallas por política
    # ------------------------------------------------------------------

    async def _handle_failure(
        self,
        *,
        plan: Plan,
        action: Action,
        step_index: int,
        applied_entry_ids: list[str],
        result: ToolResult,
    ) -> ExecutorResult:
        """Despacha la falla de un paso según action.on_error."""

        if action.on_error == ErrorPolicy.RETRY:
            # Si llegamos aquí desde run(), el _retry_with_backoff ya se agotó
            # (el loop llamó execute max_attempts veces sin éxito).
            # Tratar como ABORT terminal.
            return self._abort_and_rollback(
                plan=plan,
                step_index=step_index,
                applied_entry_ids=applied_entry_ids,
                detail=f"RETRY exhausted para paso {step_index} ({action.type}): {result.detail}",
            )

        elif action.on_error == ErrorPolicy.ESCALATE:
            # Auditar el fallo + propagar SIN rollback (T-06-EXEC-1)
            self._audit.log(  # type: ignore[attr-defined]
                AuditEvent.new(
                    actor_type=ActorType.SYSTEM,
                    actor_id="executor",
                    event_type=AuditEventType.TASK_FAILED,
                    message=(
                        f"ESCALATE: plan {plan.task_id!r} "
                        f"paso {step_index} ({action.type}): {result.detail}"
                    ),
                    task_id=plan.task_id,
                    payload={"escalate": True, "step": step_index},
                )
            )
            return ExecutorResult(
                success=False,
                detail=f"ESCALATE: fallo en paso {step_index} ({action.type}), sin rollback",
                applied_entries=tuple(applied_entry_ids),
                failed_step=step_index,
            )

        else:
            # ErrorPolicy.ABORT (default): rollback inverso
            return self._abort_and_rollback(
                plan=plan,
                step_index=step_index,
                applied_entry_ids=applied_entry_ids,
                detail=f"ABORT: fallo en paso {step_index} ({action.type}): {result.detail}",
            )

    def _abort_and_rollback(
        self,
        *,
        plan: Plan,
        step_index: int,
        applied_entry_ids: list[str],
        detail: str,
    ) -> ExecutorResult:
        """Restaura entradas aplicadas en orden INVERSO (T-undo-corruption)."""
        for entry_id in reversed(applied_entry_ids):
            self._journal.restore(entry_id)
        return ExecutorResult(
            success=False,
            detail=detail,
            applied_entries=tuple(applied_entry_ids),
            failed_step=step_index,
        )
