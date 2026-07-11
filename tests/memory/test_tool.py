"""Tests del MemoryTool."""

from typing import Literal

import pytest

from core.domain.plan import Action
from core.domain.risk import RiskLevel
from memory.store import MemoryStore
from memory.tool import MemoryTool
from tests.ports.fakes import FakeAuditPort


def _tool(memory_store: MemoryStore, audit: FakeAuditPort) -> MemoryTool:
    return MemoryTool(store=memory_store, audit=audit)


async def test_remember_valido_persiste_fila(
    memory_store: MemoryStore,
) -> None:
    audit = FakeAuditPort()

    result = await _tool(memory_store, audit).execute(
        Action(
            type="memory.remember",
            target="preferencias",
            parameters={"value": "cafe sin azucar"},
        )
    )

    facts = memory_store.list_all()
    assert result.success is True
    assert result.payload["fact_id"] == facts[0].id
    assert result.payload["output"] == "Recordado: cafe sin azucar"
    assert facts[0].category == "preferencias"
    assert facts[0].value == "cafe sin azucar"
    assert facts[0].tier == "owner"
    assert audit.events[-1].payload["success"] is True


async def test_remember_hardcodea_tier_owner(
    memory_store: MemoryStore,
) -> None:
    result = await _tool(memory_store, FakeAuditPort()).execute(
        Action(
            type="memory.remember",
            target="preferencias",
            parameters={"value": "x", "tier": "external"},
        )
    )

    facts = memory_store.list_all()
    assert result.success is True
    assert facts[0].tier == "owner"


async def test_value_vacio_rechaza_y_no_persiste(
    memory_store: MemoryStore,
) -> None:
    result = await _tool(memory_store, FakeAuditPort()).execute(
        Action(
            type="memory.remember",
            target="preferencias",
            parameters={"value": " \t\n "},
        )
    )

    assert result.success is False
    assert "vacio" in result.detail
    assert memory_store.list_all() == []


async def test_action_type_invalido_devuelve_error(
    memory_store: MemoryStore,
) -> None:
    result = await _tool(memory_store, FakeAuditPort()).execute(
        Action(type="memory.forget", target="fact-id")
    )

    assert result.success is False
    assert "unsupported action type" in result.detail
    assert memory_store.list_all() == []


async def test_error_del_store_devuelve_toolresult_legible(
    memory_store: MemoryStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(
        *,
        category: str,
        value: str,
        tier: Literal["owner", "external"],
        source: str,
    ) -> str:
        raise RuntimeError("sqlite ocupado")

    monkeypatch.setattr(memory_store, "remember", fail)

    result = await _tool(memory_store, FakeAuditPort()).execute(
        Action(
            type="memory.remember",
            target="preferencias",
            parameters={"value": "cafe"},
        )
    )

    assert result.success is False
    assert "sqlite ocupado" in result.detail
    assert memory_store.list_all() == []


async def test_verify_refleja_success(memory_store: MemoryStore) -> None:
    tool = _tool(memory_store, FakeAuditPort())
    result = await tool.execute(
        Action(
            type="memory.remember",
            target="preferencias",
            parameters={"value": "te"},
        )
    )

    verification = await tool.verify(
        Action(type="memory.remember", target="preferencias"),
        result,
    )

    assert verification.passed is True
    assert verification.detail == result.detail


def test_max_risk_b_y_describe_legible(memory_store: MemoryStore) -> None:
    tool = _tool(memory_store, FakeAuditPort())

    assert tool.max_risk == RiskLevel.B
    assert "preferencias" in tool.describe(
        Action(
            type="memory.remember",
            target="preferencias",
            parameters={"value": "cafe sin azucar"},
        )
    )


async def test_remember_con_hecho_en_target(memory_store: MemoryStore) -> None:
    """Smoke físico fase 11: el planner LLM pone el hecho en target sin
    parameters.value — el tool debe recordarlo igual (categoría default)."""
    audit = FakeAuditPort()
    tool = MemoryTool(store=memory_store, audit=audit)

    result = await tool.execute(
        Action(type="memory.remember", target="mi materia activa es AdR", parameters={})
    )

    assert result.success, result.detail
    facts = memory_store.list_all()
    assert len(facts) == 1
    assert facts[0].value == "mi materia activa es AdR"
    assert facts[0].category == "general"
    assert facts[0].tier == "owner"
