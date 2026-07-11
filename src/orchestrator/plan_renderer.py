"""Presentacion legible de planes y prompts de confirmacion B/C."""

import json

from rich.console import Console
from rich.panel import Panel

from core.domain.plan import Action, Plan
from core.domain.policy import PolicyDecision
from core.domain.risk import RiskLevel

_NOTION_WRITE_ACTIONS = {"notion.create_page", "notion.update_page"}
_NOTION_PREVIEW_KEYS = ("title", "type", "parent", "properties", "markdown", "update_content")
_PARAM_PREVIEW_LIMIT = 1200


def _truncate(value: str, *, limit: int = _PARAM_PREVIEW_LIMIT) -> str:
    if len(value) <= limit:
        return value
    omitted = len(value) - limit
    return f"{value[:limit]}\n... [truncado: {omitted} caracteres omitidos]"


def _render_value(value: object) -> str:
    if isinstance(value, str):
        return _truncate(value)
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        rendered = str(value)
    return _truncate(rendered)


def _parameter_preview_lines(key: str, value: object) -> list[str]:
    rendered = _render_value(value)
    if "\n" not in rendered:
        return [f"  {key}: {rendered}"]
    return [f"  {key}:", *(f"    {line}" for line in rendered.splitlines())]


def _notion_write_preview(action: Action) -> list[str]:
    if action.type not in _NOTION_WRITE_ACTIONS:
        return []
    lines: list[str] = []
    for key in _NOTION_PREVIEW_KEYS:
        if key in action.parameters:
            lines.extend(_parameter_preview_lines(key, action.parameters[key]))
    return lines


def _action_to_text(position: int, action: Action) -> str:
    header = f"{position}. [{action.type}] {action.target}"
    preview = _notion_write_preview(action)
    if not preview:
        return header
    return "\n".join([header, *preview])


def plan_to_text(plan: Plan, decision: PolicyDecision) -> str:
    """Representacion textual testeable del Plan propuesto."""
    steps = "\n".join(
        _action_to_text(position, action)
        for position, action in enumerate(plan.steps, start=1)
    )
    return (
        f"Resumen: {plan.summary}\n"
        f"Nivel: {decision.risk_level.name}\n"
        f"Pasos: {len(plan.steps)}\n\n"
        f"{steps}"
    ).rstrip()


def render_plan(plan: Plan, decision: PolicyDecision, console: Console) -> None:
    """Imprime el Plan como Rich Panel."""
    console.print(
        Panel(
            plan_to_text(plan, decision),
            title=f"Plan propuesto - nivel {decision.risk_level.name}",
            expand=False,
        )
    )


def prompt_confirmation(decision: PolicyDecision, console: Console) -> bool:
    """Pide confirmacion: B acepta solo `s`; C exige `CONFIRMAR` exacto."""
    if decision.risk_level == RiskLevel.B:
        response = console.input("[bold yellow]Confirmar? [s/N]: [/]").strip().lower()
        return response == "s"
    response = console.input("[bold red]Escribi CONFIRMAR para continuar: [/]").strip()
    return response == "CONFIRMAR"
