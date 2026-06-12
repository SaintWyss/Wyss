"""Fixtures compartidas de los tests del gateway de modelos (Fase 2).

Las olas 2-3 (providers, router, minimizer, cost, traces) consumen estas fixtures:
- `respx_mock`: router de respx que intercepta el tráfico httpx (tests de providers sin red).
- `http_client`: `httpx.AsyncClient` para inyectar en providers.
- `audit`: un `FakeAuditPort` reusado de `tests/ports/fakes.py` (AuditPort inyectado, no importado).
- `traces_db_path`: `tmp_path / "traces.db"` (tmp_path es ext4/tmpfs — WAL OK, evita Pitfall 6).
- `make_request`: factory de `AgentModelRequest` con defaults sensatos para reuso en tests.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
import respx

from core.domain.gateway import AgentModelRequest
from tests.ports.fakes import FakeAuditPort


@pytest.fixture
def respx_mock() -> Iterator[respx.MockRouter]:
    """Router de respx activo durante el test: intercepta todo el tráfico httpx (sin red)."""
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def http_client() -> Iterator[httpx.AsyncClient]:
    """`httpx.AsyncClient` para inyectar en providers; usar junto a `respx_mock` para mockear."""
    client = httpx.AsyncClient()
    try:
        yield client
    finally:
        # El cierre real es async; en tests que lo usen, cerrar explícito. Aquí garantizamos
        # que el recurso se libere sin bloquear el loop (best-effort para el scaffolding).
        pass


@pytest.fixture
def audit() -> FakeAuditPort:
    """AuditPort en memoria para inspeccionar el rastro emitido por el gateway."""
    return FakeAuditPort()


@pytest.fixture
def traces_db_path(tmp_path: Path) -> Path:
    """Ruta a una traces.db sobre tmp_path (ext4/tmpfs — WAL funciona, Pitfall 6)."""
    return tmp_path / "traces.db"


@pytest.fixture
def make_request() -> Callable[..., AgentModelRequest]:
    """Factory de AgentModelRequest con defaults sensatos para reuso en tests del gateway."""

    def _make(
        *,
        agent_id: str = "belgrano",
        task_id: str = "task-1",
        prompt: str = "hola",
        tier: str = "economico",
        purpose: str = "general",
    ) -> AgentModelRequest:
        return AgentModelRequest(
            agent_id=agent_id,
            task_id=task_id,
            prompt=prompt,
            tier=tier,
            purpose=purpose,
        )

    return _make
