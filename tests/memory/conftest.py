"""Fixtures para MemoryStore SQLite."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from memory.store import MemoryStore


@pytest.fixture
def memory_store(tmp_path: Path) -> Iterator[MemoryStore]:
    """Store de memoria aislado por test."""
    store = MemoryStore(tmp_path / "memory.db")
    try:
        yield store
    finally:
        store.close()
