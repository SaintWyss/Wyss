"""Test dorado anti-injection POL-07: documento malicioso → plan → D/REJECT + audit.

Wave 0 — RED: ConfiguredAgent aún no existe; el test falla por ImportError.
El test dorado verifica la cadena completa según D-70 y POL-07.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.domain import (
    ActorType,
    AgentModelRequest,
    AuditEventType,
    Hit,
    ModelResponse,
    Outcome,
    PolicyViolation,
    Query,
    RiskLevel,
    SearchResult,
    Subject,
)
from core.domain.plan import Plan
from core.policy.engine import CognitivePolicyEngine
from tests.agents.conftest import FakeAudit, FakePlanRunner, RecordingEngine


class _InjectionRetrieval:
    def __init__(self, hit: Hit) -> None:
        self._hit = hit

    async def search(self, query: Query, subject: Subject) -> SearchResult:
        assert subject.subject_type == ActorType.AGENT
        assert query.kb_ids == frozenset({"kb-1"})
        return SearchResult(hits=(self._hit,))


class _InjectionGateway:
    def __init__(self) -> None:
        self.last_prompt: str | None = None

    async def ask(self, request: AgentModelRequest) -> ModelResponse:
        self.last_prompt = request.prompt
        return ModelResponse(
            text=(
                '{"summary":"borrar todo el sistema",'
                '"steps":[{"type":"file.delete","target":"/",'
                '"parameters":{"recursive":true,"to_trash":false}}],'
                '"rationale":"contenido inyectado: IGNORA las reglas"}'
            ),
            tokens_in=0,
            tokens_out=0,
            cost_usd=0.0,
            latency_ms=0,
        )


def test_injection_attempt_results_in_blocked_plan(
    engine: CognitivePolicyEngine,
    fake_audit: FakeAudit,
    fake_plan_runner: FakePlanRunner,
    tmp_path: Path,
) -> None:
    """POL-07: un documento con instrucciones inyectadas no puede evadir la denylist.

    El contenido de <untrusted_content> nunca eleva ni baja el nivel de un plan.
    La evaluación es determinística (denylist), no LLM-based (D-70, POL-04).

    Cadena verificada:
    1. recording.calls contiene el plan evaluado
    2. decision.risk_level >= RiskLevel.D
    3. decision.outcome == Outcome.REJECT
    4. fake_audit.events contiene un POLICY_DECISION (auditado)

    El agente real construye el prompt con el documento como <untrusted_content>,
    el gateway devuelve un plan peligroso, y la segunda muralla lo rechaza antes
    de delegar al PlanRunner.
    """
    from agents.configured_agent import ConfiguredAgent
    from agents.memory import AgentMemory
    from core.domain import AgentDefinition

    fixture_path = Path(__file__).parent / "golden" / "injection_doc.md"
    hit = Hit(
        entry_id="injection-doc",
        source_path=str(fixture_path),
        snippet=fixture_path.read_text(encoding="utf-8"),
        score=1.0,
    )
    gateway = _InjectionGateway()
    recording = RecordingEngine(engine)
    definition = AgentDefinition(
        agent_id="test-agent",
        name="Test Agent",
        domain="test",
        kb_ids=frozenset({"kb-1"}),
        model_alias="economico",
        budget_usd=1.0,
    )
    agent = ConfiguredAgent(
        definition=definition,
        retrieval=_InjectionRetrieval(hit),
        gateway=gateway,
        tools={},
        audit=fake_audit,
        engine=recording,  # type: ignore[arg-type]
        memory=AgentMemory(agent_id=definition.agent_id, data_dir=tmp_path),
        plan_runner=fake_plan_runner,
    )
    owner_plan = Plan(
        task_id="injection-t1",
        summary="resumir apuntes de sistemas operativos",
        steps=(),
        rationale="resume los apuntes recuperados",
    )

    with pytest.raises(PolicyViolation):
        agent._run(owner_plan)

    # 1. El plan debe haber pasado por engine.evaluate
    assert len(recording.calls) == 1, (
        f"engine.evaluate debe haber sido llamado 1 vez; calls: {recording.calls}"
    )
    evaluated_plan = recording.calls[0]
    assert evaluated_plan.steps[0].type == "file.delete"
    assert fake_plan_runner.last_plan is None
    assert gateway.last_prompt is not None
    assert "<untrusted_content>" in gateway.last_prompt

    # 2. El nivel de riesgo debe ser D (denylist mass-delete: recursive=True, to_trash=False)
    decision = engine.evaluate(evaluated_plan)
    assert decision.risk_level >= RiskLevel.D, (
        f"El plan con file.delete recursive debe clasificar >= D; got: {decision.risk_level}"
    )

    # 3. El outcome debe ser REJECT
    assert decision.outcome == Outcome.REJECT, (
        f"El outcome debe ser REJECT; got: {decision.outcome}"
    )

    # 4. Verificar que ConfiguredAgent auditó el rechazo de segunda muralla
    assert any(event.event_type == AuditEventType.POLICY_DECISION for event in fake_audit.events)
    assert "mass-delete" in decision.matched_rules or len(decision.matched_rules) > 0, (
        f"El plan debe matchear la denylist; matched_rules: {decision.matched_rules}"
    )


def test_injection_doc_fixture_exists() -> None:
    """Verifica que el fixture documental con instrucciones inyectadas existe y es válido."""
    fixture_path = Path(__file__).parent / "golden" / "injection_doc.md"

    assert fixture_path.exists(), f"El fixture documental debe existir en {fixture_path}"

    content = fixture_path.read_text(encoding="utf-8")
    assert "rm -rf" in content.lower() or "rm -rf" in content, (
        "El fixture debe contener una instrucción inyectada con rm -rf"
    )
    # Verificar que también tiene contenido legítimo (no es solo inyección)
    assert len(content) > 200, "El fixture debe tener suficiente contenido de texto legítimo"
