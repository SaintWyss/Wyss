"""Composición pura del Daily Assistant.

Decisiones estructurales:
- Las fallas salen de `Routine.last_outcome == "failed"` en RoutineStore, no del audit.db.
- El snapshot financiero usa `LedgerPort`; orchestrator no importa adapters de `ledger`.
- `compose_digest` es puro y solo-lectura: no hace IO, no consulta reloj, no usa LLM y
  no importa rutas de ejecución. DAILY-02 queda protegido por construcción.
"""

from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

from core.domain.memory import MemoryFact
from core.ports.ledger import LedgerPort
from orchestrator.pending_store import PendingProposal
from orchestrator.routine_store import Routine


def compose_digest(
    *,
    today: date,
    pending: Sequence[PendingProposal],
    ledger: LedgerPort,
    window: tuple[str, str],
    routines: Sequence[Routine],
    memory: Sequence[MemoryFact] = (),
) -> str:
    """Devuelve markdown estable para el digest diario."""
    desde, hasta = window
    ingresos, gastos = ledger.balance(desde, hasta)
    surplus = ledger.surplus(desde, hasta)
    by_category = ledger.query_by_category(desde, hasta)
    coverage_days = ledger.coverage_days(desde, hasta)

    lines: list[str] = [
        f"# Digest diario - {today.isoformat()}",
    ]
    owner_greeting = _owner_greeting(memory)
    if owner_greeting is not None:
        lines.append(owner_greeting)
    lines.extend(
        [
            "",
            "## Pendientes de bandeja",
            f"Total: {len(pending)}",
        ]
    )
    lines.extend(_pending_lines(pending))
    lines.extend(
        [
            "",
            "## Finanzas Pellegrini",
            f"Ventana: {desde} -> {hasta}",
        ]
    )
    lines.extend(_finance_lines(ingresos, gastos, surplus, coverage_days, by_category))
    lines.extend(
        [
            "",
            "## Rutinas",
            "### Rutinas: fallas",
        ]
    )
    failures = [routine for routine in routines if routine.last_outcome == "failed"]
    latest = [routine for routine in routines if routine.last_outcome != "failed"]
    lines.extend(_routine_lines(failures, empty="Sin fallas"))
    lines.append("### Rutinas: ultimas corridas")
    lines.extend(_routine_lines(latest, empty="Sin rutinas"))
    return "\n".join(lines).rstrip() + "\n"


def write_digest_file(dir_path: Path, day: date, markdown: str) -> Path:
    """Materializa un digest diario en `dir_path/YYYY-MM-DD.md`."""
    dir_path.mkdir(parents=True, exist_ok=True)
    output = dir_path / f"{day.isoformat()}.md"
    output.write_text(markdown, encoding="utf-8")
    return output


def _owner_greeting(memory: Sequence[MemoryFact]) -> str | None:
    owner_facts = sorted(
        (fact for fact in memory if fact.tier == "owner"),
        key=lambda fact: (fact.category, fact.id),
    )
    if not owner_facts:
        return None
    fact = owner_facts[0]
    return f"Hola. Memoria owner: {_plain(fact.value)}"


def _pending_lines(pending: Sequence[PendingProposal]) -> list[str]:
    if not pending:
        return ["Sin pendientes"]
    lines: list[str] = []
    for item in sorted(pending, key=lambda proposal: (proposal.created_at, proposal.id)):
        lines.append(
            "- "
            f"{_plain(item.task_id)} | riesgo={_plain(item.risk_level)} | "
            f"outcome={_plain(item.outcome)} | creado={_plain(item.created_at)}"
        )
    return lines


def _finance_lines(
    ingresos: float,
    gastos: float,
    surplus: float,
    coverage_days: int,
    by_category: Mapping[str, float],
) -> list[str]:
    if ingresos == 0 and gastos == 0 and not by_category:
        return [
            "Sin movimientos en la ventana",
            "Ingresos: $0.00",
            "Gastos: $0.00",
            "Surplus: $0.00",
            f"Coverage days: {coverage_days}",
        ]
    lines = [
        f"Ingresos: {_money(ingresos)}",
        f"Gastos: {_money(gastos)}",
        f"Surplus: {_money(surplus)}",
        f"Coverage days: {coverage_days}",
    ]
    if by_category:
        lines.append("Gastos por categoria:")
        for category, amount in sorted(by_category.items()):
            lines.append(f"- {_plain(category)}: {_money(amount)}")
    return lines


def _routine_lines(routines: Sequence[Routine], *, empty: str) -> list[str]:
    if not routines:
        return [empty]
    lines: list[str] = []
    for routine in sorted(routines, key=_routine_sort_key):
        last_fired = routine.last_fired_at or "nunca"
        outcome = routine.last_outcome or "-"
        lines.append(
            "- "
            f"{_plain(routine.id)} | {_plain(routine.name)} | "
            f"last_fired_at={_plain(last_fired)} | outcome={_plain(outcome)}"
        )
    return lines


def _routine_sort_key(routine: Routine) -> tuple[int, str, str]:
    if routine.last_fired_at is None:
        return (1, "", routine.id)
    return (0, _reverse_text_key(routine.last_fired_at), routine.id)


def _reverse_text_key(value: str) -> str:
    return "".join(chr(0x10FFFF - ord(char)) for char in value)


def _money(value: float) -> str:
    return f"${value:.2f}"


def _plain(value: object) -> str:
    text = " ".join(str(value).split())
    escaped = text.replace("\\", "\\\\")
    for char in ("`", "*", "_", "[", "]", "(", ")", "#", ">", "|"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped
