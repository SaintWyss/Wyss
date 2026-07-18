"""Capa de Ejecución — re-exportaciones públicas del paquete.

Adapters: FileSystemAdapter, ShellAdapter, GitAdapter
Journal:  UndoJournal
Executor: PlanExecutor

Adapters pendientes (deferred, fases futuras):
  CalendarAdapter, MessagingAdapter, AppAdapter
"""

from execution.executor import PlanExecutor
from execution.filesystem import FileSystemAdapter
from execution.git import GitAdapter
from execution.guard import DeterministicExecutionGuard
from execution.journal import UndoJournal
from execution.shell import ShellAdapter

__all__ = [
    "DeterministicExecutionGuard",
    "FileSystemAdapter",
    "GitAdapter",
    "PlanExecutor",
    "ShellAdapter",
    "UndoJournal",
]
