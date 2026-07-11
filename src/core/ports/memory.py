"""Puertos síncronos para memoria durable del owner."""

from collections.abc import Sequence
from typing import Protocol

from core.domain.memory import MemoryFact


class MemoryPort(Protocol):
    """Lectura nivel A sin gate; escribir memoria ocurre vía `memory.remember` gateada."""

    def recall(self, category: str | None = None) -> Sequence[MemoryFact]: ...


class MemoryAdmin(Protocol):
    """Administración CRUD de memoria para daemon y herramientas internas."""

    def list_all(self) -> Sequence[MemoryFact]: ...

    def edit(self, fact_id: str, value: str) -> bool: ...

    def forget(self, fact_id: str) -> bool: ...
