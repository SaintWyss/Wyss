"""Tests del plan_renderer (ORCH-05)."""

from rich.console import Console

from core.domain.plan import Action, Plan
from core.domain.policy import PolicyDecision
from core.domain.risk import Outcome, RiskLevel
from orchestrator.plan_renderer import plan_to_text, prompt_confirmation, render_plan


class InputConsole(Console):
    def __init__(self, response: str) -> None:
        super().__init__(record=True)
        self.prompt: str | None = None
        self._response = response

    def input(
        self,
        prompt: object = "",
        *,
        markup: bool = True,
        emoji: bool = True,
        password: bool = False,
        stream: object | None = None,
    ) -> str:
        self.prompt = str(prompt)
        return self._response


def _plan() -> Plan:
    return Plan(
        task_id="task-render",
        summary="actualizar archivos",
        steps=(
            Action(type="file.write", target="/tmp/a.txt"),
            Action(type="file.move", target="/tmp/b.txt"),
        ),
        rationale="test",
    )


def _decision(level: RiskLevel) -> PolicyDecision:
    outcomes: dict[RiskLevel, Outcome] = {
        RiskLevel.B: Outcome.CONFIRM_SIMPLE,
        RiskLevel.C: Outcome.CONFIRM_STRONG,
    }
    return PolicyDecision(
        task_id="task-render",
        risk_level=level,
        outcome=outcomes[level],
    )


def test_render_plan_panel() -> None:
    plan = _plan()
    decision = _decision(RiskLevel.C)
    console = Console(record=True, width=100)

    text = plan_to_text(plan, decision)
    render_plan(plan, decision, console)
    rendered = console.export_text()

    assert "Nivel: C" in text
    assert "Pasos: 2" in text
    assert "/tmp/a.txt" in text
    assert "/tmp/b.txt" in text
    assert "Plan propuesto" in rendered
    assert "/tmp/a.txt" in rendered


def test_notion_write_preview_shows_proposed_content() -> None:
    plan = Plan(
        task_id="task-notion",
        summary="crear pagina Notion",
        steps=(
            Action(
                type="notion.create_page",
                target="database-123",
                parameters={
                    "title": "Reunion semanal",
                    "markdown": "# Reunion semanal\n\n- revisar roadmap\n- cerrar pendientes",
                    "properties": {"Name": {"title": "Reunion semanal"}},
                },
            ),
        ),
        rationale="test",
    )
    decision = _decision(RiskLevel.C)

    text = plan_to_text(plan, decision)

    assert "[notion.create_page] database-123" in text
    assert "title: Reunion semanal" in text
    assert "# Reunion semanal" in text
    assert "revisar roadmap" in text
    assert "properties:" in text


def test_notion_write_preview_marks_truncated_content() -> None:
    long_content = "x" * 1300
    plan = Plan(
        task_id="task-notion",
        summary="actualizar pagina Notion",
        steps=(
            Action(
                type="notion.update_page",
                target="page-123",
                parameters={"type": "update_content", "update_content": long_content},
            ),
        ),
        rationale="test",
    )

    text = plan_to_text(plan, _decision(RiskLevel.C))

    assert "[notion.update_page] page-123" in text
    assert "type: update_content" in text
    assert "truncado:" in text
    assert "caracteres omitidos" in text


def test_prompt_b_accepts_only_s() -> None:
    assert prompt_confirmation(_decision(RiskLevel.B), InputConsole("s")) is True
    assert prompt_confirmation(_decision(RiskLevel.B), InputConsole("n")) is False


def test_prompt_c_requires_confirmar_literal() -> None:
    accepted = InputConsole("CONFIRMAR")
    rejected = InputConsole("confirmar")

    assert prompt_confirmation(_decision(RiskLevel.C), accepted) is True
    assert prompt_confirmation(_decision(RiskLevel.C), rejected) is False
    assert accepted.prompt is not None
    assert "CONFIRMAR" in accepted.prompt
