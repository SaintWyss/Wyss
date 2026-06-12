"""Test trivial de sanidad del scaffolding tests/gateway/ (Nyquist: al menos un verde).

Verifica que las fixtures compartidas del conftest están sanas y que la factory
`make_request` produce un `AgentModelRequest` válido con tier/purpose. Los tests de
comportamiento real (minimizer, cost gate, traces) los escriben las olas siguientes.
"""

from collections.abc import Callable
from pathlib import Path

from core.domain.gateway import AgentModelRequest
from tests.ports.fakes import FakeAuditPort


def test_make_request_produces_valid_agent_request(
    make_request: Callable[..., AgentModelRequest],
) -> None:
    """La factory devuelve un AgentModelRequest con tier/purpose por default."""
    req = make_request()
    assert isinstance(req, AgentModelRequest)
    assert req.agent_id == "belgrano"
    assert req.tier == "economico"
    assert req.purpose == "general"


def test_make_request_honours_overrides(
    make_request: Callable[..., AgentModelRequest],
) -> None:
    """La factory respeta overrides de tier/purpose."""
    req = make_request(tier="fuerte", purpose="plan")
    assert req.tier == "fuerte"
    assert req.purpose == "plan"


def test_audit_fixture_is_fake_audit_port(audit: FakeAuditPort) -> None:
    """El fixture `audit` devuelve un FakeAuditPort vacío listo para inspección."""
    assert isinstance(audit, FakeAuditPort)
    assert audit.events == []


def test_traces_db_path_under_tmp(traces_db_path: Path) -> None:
    """`traces_db_path` apunta a un traces.db bajo tmp_path (ext4 — WAL OK)."""
    assert traces_db_path.name == "traces.db"
    assert not traces_db_path.exists()
