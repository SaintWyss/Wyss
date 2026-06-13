"""Presentacion legible de planes y prompts de confirmacion B/C."""

from rich.console import Console
from rich.panel import Panel

from core.domain.plan import Plan
from core.domain.policy import PolicyDecision
from core.domain.risk import RiskLevel


def plan_to_text(plan: Plan, decision: PolicyDecision) -> str:
    """Representacion textual testeable del Plan propuesto."""
    steps = "\n".join(
        f"{position}. [{action.type}] {action.target}"
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
