"""Hechos recordados por el owner y fuentes externas."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class MemoryFact:
    """Hecho durable de memoria, inmutable dentro del núcleo."""

    id: str
    category: str
    value: str
    tier: Literal["owner", "external"]
    source: str
    created_at: str
    updated_at: str
