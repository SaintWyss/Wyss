"""Task y su máquina de estados (backbone de la auditabilidad, doc 11 §4)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class TaskStatus(StrEnum):
    """Estados de una tarea a lo largo del flujo de comando."""

    PENDING = "pending"
    PLANNED = "planned"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class Task:
    """Unidad de trabajo del owner. Mínima en F1; se expande en fases posteriores."""

    task_id: str
    instruction: str
    status: TaskStatus
    created_at: datetime
