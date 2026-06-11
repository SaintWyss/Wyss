"""Puerto de persistencia de tareas."""

from typing import Protocol

from core.domain import Task


class TaskRepository(Protocol):
    """Guarda y recupera tareas por id."""

    def save(self, task: Task) -> None: ...

    def get(self, task_id: str) -> Task: ...
