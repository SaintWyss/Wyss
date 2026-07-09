"""Undo user-facing (PR-09): revierte mutaciones 'applied' usando el UndoJournal.

`wyss undo <task_id>` NO es un bypass de la política: la CLI construye un `Plan`
con las operaciones inversas y lo pasa por el MISMO `CognitivePolicyEngine` antes
de confirmar y aplicar. Este módulo solo prepara (dry-run: pre-chequeos honestos
de estado) y aplica; la evaluación de riesgo, la confirmación y la auditoría viven
en bootstrap (composition root).

Reversibilidad por tipo de inversa (roadmap §6):
- file.delete (write de archivo nuevo) → borrar el archivo creado
- file.write (overwrite) → restaurar el backup capturado antes de sobrescribir
- file.move → mover de vuelta, con check de colisión en el origen
- file.restore_trash (delete) → restaurar desde la papelera vía .trashinfo
- shell/git → irreversibles (no generan entradas de journal; si apareciera un tipo
  desconocido, se marca no-listo y el undo entero se rechaza)

Importaciones: core.* + stdlib + hermanos de execution/ (invariante import-linter).
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from core.domain.plan import Action, Plan
from execution.journal import UndoEntry, UndoJournal

_SUPPORTED_INVERSES: frozenset[str] = frozenset(
    {"file.move", "file.delete", "file.write", "file.restore_trash"}
)


@dataclass(frozen=True, slots=True)
class UndoStep:
    """Una entrada del journal lista para deshacer, con su pre-chequeo de estado."""

    entry: UndoEntry
    inverse: Action
    ready: bool
    detail: str


def plan_undo(journal: UndoJournal, task_id: str) -> list[UndoStep]:
    """Prepara el undo de una tarea: entradas 'applied' en orden inverso + pre-chequeos.

    El pre-chequeo es el check de colisión del roadmap: si el mundo ya no está como
    el journal lo dejó (el archivo movido desapareció, el origen fue re-creado, el
    backup no existe), el paso queda no-listo. El caller rechaza el undo entero ante
    cualquier paso no-listo — mejor no deshacer que deshacer a medias sobre estado
    desconocido.
    """
    steps: list[UndoStep] = []
    for entry in journal.load_applied_for_task(task_id):
        op = _parse_inverse_op(entry)
        inverse = Action(
            type=str(op.get("type", "")),
            target=str(op.get("target", entry.origin)),
            parameters=_parameters_of(op),
        )
        ready, detail = _precheck(journal, entry, inverse)
        steps.append(UndoStep(entry=entry, inverse=inverse, ready=ready, detail=detail))
    return steps


def inverse_plan(task_id: str, steps: Sequence[UndoStep]) -> Plan:
    """Plan con las operaciones inversas, para evaluar con el MISMO engine (no bypass).

    Un tipo de inversa que el engine no conoce (file.restore_trash) cae a C
    fail-closed, que es exactamente lo que queremos: confirmación fuerte.
    """
    return Plan(
        task_id=f"undo-{task_id}",
        summary=f"deshacer las mutaciones aplicadas de la tarea {task_id}",
        steps=tuple(step.inverse for step in steps),
        rationale="undo de mutaciones registradas en el journal (PR-09)",
    )


def apply_undo(journal: UndoJournal, steps: Sequence[UndoStep]) -> tuple[bool, list[str]]:
    """Aplica los pasos en orden (ya vienen en orden inverso de ejecución).

    Aborta en el primer fallo y lo reporta honesto — sin medio-deshacer silencioso.
    Cada restore exitoso marca la entrada 'rolled_back', así un segundo
    `wyss undo` de la misma tarea no encuentra nada que deshacer (idempotencia).
    """
    details: list[str] = []
    for step in steps:
        label = f"{step.inverse.type} -> {step.inverse.target}"
        try:
            ok = journal.restore(step.entry.id, expected_status="applied")
        except OSError as exc:
            details.append(f"FALLO {label}: {exc}")
            return False, details
        if not ok:
            details.append(f"FALLO {label}: la entrada ya no está 'applied' o la inversa no aplicó")
            return False, details
        details.append(f"ok {label}")
    return True, details


# -- helpers privados ---------------------------------------------------------


def _parse_inverse_op(entry: UndoEntry) -> dict[str, object]:
    try:
        parsed = json.loads(entry.inverse_op)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parameters_of(op: dict[str, object]) -> dict[str, object]:
    params = op.get("parameters", {})
    return dict(params) if isinstance(params, dict) else {}


def _precheck(journal: UndoJournal, entry: UndoEntry, inverse: Action) -> tuple[bool, str]:
    """Chequeo honesto de que la inversa PUEDE aplicarse sobre el estado actual."""
    if inverse.type not in _SUPPORTED_INVERSES:
        return False, f"inversa desconocida o irreversible: '{inverse.type or '?'}'"

    if inverse.type == "file.delete":
        if not Path(inverse.target).exists():
            return False, "el archivo creado ya no existe (¿deshecho a mano?)"
        return True, "borra el archivo creado"

    if inverse.type == "file.write":
        if not journal.backup_path(entry.id).exists():
            return False, "backup de sobreescritura no encontrado"
        return True, "restaura el contenido previo desde el backup"

    if inverse.type == "file.move":
        source = Path(inverse.target)
        destination = Path(str(inverse.parameters.get("destination", entry.origin)))
        if not source.exists():
            return False, f"el archivo movido ya no está en {source}"
        if destination.exists():
            return False, f"colisión: ya existe algo en el origen {destination}"
        return True, f"mueve de vuelta a {destination}"

    # file.restore_trash
    trashinfo = Path(str(inverse.parameters.get("trashinfo_path", "")))
    if not trashinfo.exists():
        return False, "no se encontró la entrada en la papelera (.trashinfo)"
    if Path(entry.origin).exists():
        return False, f"colisión: ya existe algo en el origen {entry.origin}"
    return True, "restaura desde la papelera"
