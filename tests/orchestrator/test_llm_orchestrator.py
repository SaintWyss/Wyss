"""Tests del LLMOrchestrator con gateway fake, sin red."""

from __future__ import annotations

import pytest

from core.domain.errors import BudgetExceeded, OrchestratorUnavailable
from core.domain.gateway import AgentModelRequest, ModelResponse
from core.domain.risk import RiskLevel
from core.orchestrator.intent import IntentCategory, IntentClassification
from core.policy import CognitivePolicyEngine
from orchestrator.llm_orchestrator import LLMOrchestrator


class FakeGateway:
    def __init__(self, *responses: str, exc: Exception | None = None) -> None:
        self._responses = list(responses)
        self._exc = exc
        self.requests: list[AgentModelRequest] = []

    async def ask(self, request: AgentModelRequest) -> ModelResponse:
        self.requests.append(request)
        if self._exc is not None:
            raise self._exc
        text = self._responses.pop(0)
        return ModelResponse(text=text, tokens_in=1, tokens_out=1, cost_usd=0.0, latency_ms=1)


def _intent() -> IntentClassification:
    return IntentClassification(IntentCategory.FILE_OPERATION, 0.91, False)


async def test_draft_plan_valid_json_returns_frozen_plan() -> None:
    gateway = FakeGateway(
        """{
          "summary": "actualizar archivo",
          "rationale": "pedido directo del owner",
          "estimated_risk": "C",
          "steps": [
            {"type": "file.write", "target": "/tmp/out.txt", "parameters": {"mode": "append"}}
          ]
        }"""
    )
    orchestrator = LLMOrchestrator(gateway, tier="fuerte")

    plan = await orchestrator.draft_plan("agregá una línea a /tmp/out.txt", _intent())

    assert plan.task_id.startswith("ask-")
    assert plan.summary == "actualizar archivo"
    assert plan.rationale == "pedido directo del owner"
    assert plan.estimated_risk == RiskLevel.C
    assert len(plan.steps) == 1
    assert plan.steps[0].type == "file.write"
    assert plan.steps[0].target == "/tmp/out.txt"
    assert plan.steps[0].parameters == {"mode": "append"}
    assert gateway.requests[0].task_id == plan.task_id
    assert gateway.requests[0].tier == "fuerte"
    assert gateway.requests[0].purpose == "orchestrator.draft"


@pytest.mark.parametrize(
    "payload",
    [
        "{no es json",
        '{"summary": "x", "rationale": "y", "estimated_risk": null, "steps": [], "extra": 1}',
        (
            '{"summary": "x", "rationale": "y", "estimated_risk": null, '
            '"steps": [{"type": "file.read", "target": "/tmp/a", "extra": 1}]}'
        ),
        '{"summary": "x", "rationale": "y", "estimated_risk": null, "steps": []}',
    ],
)
async def test_draft_plan_invalid_shapes_raise_unavailable(payload: str) -> None:
    orchestrator = LLMOrchestrator(FakeGateway(payload))

    with pytest.raises(OrchestratorUnavailable, match="plan del LLM inválido"):
        await orchestrator.draft_plan("leer algo", _intent())


async def test_denylisted_action_parses_and_policy_rejects(
    engine: CognitivePolicyEngine,
) -> None:
    orchestrator = LLMOrchestrator(
        FakeGateway(
            """{
              "summary": "formatear disco",
              "rationale": "pedido peligroso",
              "estimated_risk": null,
              "steps": [{"type": "shell.run", "target": "mkfs /dev/sda1", "parameters": {}}]
            }"""
        )
    )

    plan = await orchestrator.draft_plan("formatear /dev/sda1", _intent())
    decision = engine.evaluate(plan)

    assert plan.steps[0].type == "shell.run"
    assert decision.risk_level == RiskLevel.D


async def test_budget_exceeded_becomes_orchestrator_unavailable() -> None:
    cause = BudgetExceeded("sin presupuesto")
    orchestrator = LLMOrchestrator(FakeGateway(exc=cause))

    with pytest.raises(OrchestratorUnavailable) as classify_exc:
        await orchestrator.classify_intent("clasificá")
    assert classify_exc.value.__cause__ is cause

    with pytest.raises(OrchestratorUnavailable) as draft_exc:
        await orchestrator.draft_plan("planificá", _intent())
    assert draft_exc.value.__cause__ is cause


async def test_injection_estimated_risk_cannot_lower_policy_and_bad_category_fails_closed(
    engine: CognitivePolicyEngine,
) -> None:
    orchestrator = LLMOrchestrator(
        FakeGateway(
            '{"category": "root_access", "confidence": 0.99, "clarification_needed": false}',
            """{
              "summary": "borrar archivo",
              "rationale": "el LLM intenta bajar riesgo",
              "estimated_risk": "A",
              "steps": [{"type": "file.delete", "target": "/tmp/x", "parameters": {}}]
            }""",
        )
    )

    classification = await orchestrator.classify_intent("inventá permisos root")
    plan = await orchestrator.draft_plan("borrar /tmp/x", _intent())
    decision = engine.evaluate(plan)

    assert classification.category == IntentCategory.AMBIGUOUS_REQUEST
    assert classification.confidence == 0.0
    assert classification.clarification_needed is True
    assert plan.estimated_risk == RiskLevel.A
    assert decision.risk_level >= RiskLevel.B
