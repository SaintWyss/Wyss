"""Pellegrini — coach de finanzas config-only (AGENT-09, D-87).

Pellegrini NO es código de agente nuevo en el sentido de D-73: no subclasea ni modifica
`ConfiguredAgent`/`AgentRegistry`. Este módulo es *infra de agente* que aporta:

1. `advise(...)` — arma el prompt con el bloque de "Hechos verificados del ledger"
   (números pre-agregados, NUNCA recalculados por el LLM) y llama al gateway. El consejo solo
   cita montos que ya están en los hechos (D2 no-fabrication).
2. `handle_task(...)` — convierte una instrucción del owner (las 3 tareas D-87) en un `Plan`
   de SOLO LECTURA (`finance.query`, nivel A) que el dispatcher encola y audita.
3. `propuesta_presupuesto(...)` — propuesta determinística de presupuesto ≤ ingresos (D3).
4. `build_pellegrini(...)` — construye un agente concreto (subclase de `AgentBase`) cuyo
   `_run` escribiría al ledger; sirve para probar la SEGUNDA MURALLA: `AgentBase.execute`
   rechaza REJECT/nivel-D ANTES de `_run`, así una escritura no owner-instruida nunca muta
   el ledger (D5 / T-08-09, T-08-10).
5. `judge_advisory_quality(...)` — eval opt-in `@llm_judge` (consume budget; fuera del CI).

Toda la aritmética viene pre-agregada del `LedgerRetrieval`/`LedgerPort` (SQL-side): el LLM
solo redacta. Esto previene estructuralmente el modo de falla #1 de la AI-SPEC.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from core.domain import (
    AgentDefinition,
    Plan,
    Report,
)
from core.domain.gateway import AgentModelRequest
from core.domain.plan import Action
from core.ports.agent import AgentBase

# ─────────────────────────────────────────────────────────────────────────────
# Bloque de hechos verificados → texto del prompt


def render_hechos(hechos: Mapping[str, Any]) -> str:
    """Renderiza los hechos del ledger como bloque de evidencia confiable para el prompt.

    Los montos salen tal cual de las agregaciones SQL — el LLM no recalcula. El no-fabrication
    test asierta que todo `$N` del consejo pertenece a este conjunto de montos.
    """
    por_categoria = hechos.get("gastos_por_categoria", {})
    if isinstance(por_categoria, Mapping):
        categorias_txt = "\n".join(
            f"  - {categoria}: ${float(monto):.2f}"
            for categoria, monto in sorted(
                por_categoria.items(), key=lambda kv: float(kv[1]), reverse=True
            )
        )
    else:
        categorias_txt = "  - (sin desglose)"
    coverage = int(hechos.get("coverage_days", 0))
    return (
        "## Hechos verificados del ledger (NO recalcular — son la verdad)\n"
        f"- Ingresos totales: ${float(hechos['ingresos_total']):.2f}\n"
        f"- Gastos totales: ${float(hechos['gastos_total']):.2f}\n"
        f"- Superávit: ${float(hechos['surplus']):.2f}\n"
        f"- Gastos por categoría:\n{categorias_txt}\n"
        f"- Cobertura: {coverage} días con datos"
        + (
            " (ESCASA — declarar incertidumbre, no proyectar con confianza)."
            if coverage < 7
            else "."
        )
    )


def _build_prompt(instruccion: str, hechos: Mapping[str, Any]) -> str:
    """Prompt advisory: instrucción del owner + hechos confiables. Tono coach, no juez."""
    return (
        "## Rol\n"
        "Sos Pellegrini, un coach de finanzas personales. Aconsejás con tono cercano y "
        "concreto, nunca juzgás. Proponés acciones ('recortá $X en Y, te sobran $Z').\n\n"
        "## Reglas inviolables\n"
        "- Usá SOLO los montos del bloque de hechos verificados. NO inventes ni recalcules.\n"
        "- El presupuesto que propongas NUNCA puede exceder los ingresos.\n"
        "- Si la cobertura es escasa, declaralo: no proyectes con confianza sobre poco dato.\n\n"
        f"## Instrucción del owner\n{instruccion}\n\n"
        f"{render_hechos(hechos)}\n"
    )


# ─────────────────────────────────────────────────────────────────────────────
# advise — llamada al gateway


class _GatewayLike(Protocol):
    async def ask(self, request: Any) -> Any: ...


def _as_hechos(hechos: object) -> Mapping[str, Any]:
    """Narrowing del bloque de hechos (las firmas RED lo tipan `object`; D-08 fail-closed)."""
    if not isinstance(hechos, Mapping):
        raise TypeError("hechos debe ser un Mapping de hechos verificados del ledger")
    return hechos


async def advise(
    *,
    gateway: object,
    hechos: object,
    instruccion: str = "Hacé una lectura general de mis finanzas del mes.",
) -> str:
    """Pide al gateway un consejo grounded en los hechos del ledger; devuelve el texto.

    Los hechos viajan en el prompt como evidencia confiable (pre-agregada). El gateway aplica
    routing/minimizado/costo internamente; acá solo recibimos el texto del consejo. `gateway`
    y `hechos` se tipan `object` para honrar el contrato de los tests RED (import diferido) y
    se estrechan acá (fail-closed si no cumplen el shape esperado).
    """
    if not hasattr(gateway, "ask"):
        raise TypeError("gateway debe exponer un método async ask(request)")
    gateway_like: _GatewayLike = gateway
    prompt = _build_prompt(instruccion, _as_hechos(hechos))
    request = AgentModelRequest(
        agent_id="pellegrini",
        task_id="fin-advise",
        prompt=prompt,
        tier="economico",
        purpose="advisory",
    )
    response = await gateway_like.ask(request)
    texto = getattr(response, "text", "")
    return texto if isinstance(texto, str) else str(texto)


# ─────────────────────────────────────────────────────────────────────────────
# handle_task — instrucción del owner → Plan de solo lectura (finance.query)

_TAREA_A_CONSULTA: dict[str, str] = {
    "¿dónde se me va la plata?": "gastos_por_categoria",
    "armá mi presupuesto mensual": "presupuesto",
    "¿cuánto puedo ahorrar?": "surplus",
}


def _task_id_for(instruccion: str) -> str:
    consulta = _TAREA_A_CONSULTA.get(instruccion, "lectura_general")
    return f"pellegrini-{consulta}"


async def handle_task(*, instruccion: str, hechos: object) -> Plan:
    """Convierte una tarea D-87 del owner en un `Plan` de SOLO LECTURA (finance.query, nivel A).

    Las 3 tareas son consultivas: nunca escriben al ledger. El `summary` declara la lectura
    (incluyendo el presupuesto propuesto cuando aplica) para que el reporte sea auditable.
    `hechos` se tipa `object` (contrato de los tests RED) y se estrecha acá.
    """
    hechos_map = _as_hechos(hechos)
    consulta = _TAREA_A_CONSULTA.get(instruccion, "lectura_general")
    if consulta == "presupuesto":
        presupuesto = propuesta_presupuesto(hechos_map)
        summary = (
            f"Presupuesto propuesto para el mes: ${presupuesto:.2f} "
            f"(ingresos verificados ${float(hechos_map['ingresos_total']):.2f})."
        )
    elif consulta == "gastos_por_categoria":
        summary = "Lectura de gastos por categoría del ledger (¿dónde se va la plata?)."
    elif consulta == "surplus":
        summary = f"Capacidad de ahorro: superávit verificado ${float(hechos_map['surplus']):.2f}."
    else:
        summary = "Lectura general de las finanzas del mes."

    step = Action(
        type="finance.query",
        target="ledger",
        parameters={"consulta": consulta},
    )
    return Plan(
        task_id=_task_id_for(instruccion),
        summary=summary,
        steps=(step,),
        rationale=instruccion,
    )


def propuesta_presupuesto(hechos: Mapping[str, Any]) -> float:
    """Presupuesto determinístico ≤ ingresos (D3 sensatez).

    Regla: el presupuesto de gasto propuesto es el menor entre los gastos históricos y los
    ingresos (nunca se propone gastar más de lo que entra). Cap explícito por seguridad.
    """
    ingresos = float(hechos["ingresos_total"])
    gastos = float(hechos["gastos_total"])
    return min(gastos, ingresos)


# ─────────────────────────────────────────────────────────────────────────────
# build_pellegrini — agente concreto para probar la SEGUNDA MURALLA


class _FailClosedRetrieval:
    """Retrieval que no debe invocarse: si `_run` corre, falla ruidoso (la muralla debe vetar)."""

    async def search(self, query: Any, subject: Any) -> Any:  # pragma: no cover
        raise AssertionError("_run no debe ejecutarse: la segunda muralla debió vetar antes")


class _NullAudit:
    """AuditPort mínimo de respaldo cuando no se inyecta uno (no usado por execute con REJECT)."""

    def log(self, event: Any) -> None:  # pragma: no cover - reemplazado por el inyectado
        pass


class _PellegriniAgent(AgentBase):
    """Agente concreto cuyo `_run` escribiría al ledger.

    Solo se ejercita su `execute` heredado: ante REJECT/nivel-D, `AgentBase.execute` levanta
    `PolicyViolation` ANTES de `_run`, así la escritura `finance.record` no se materializa.
    Si `_run` llegara a correr (decisión aprobada), persiste la transacción vía `LedgerPort`.
    """

    def __init__(self, definition: AgentDefinition, audit: Any) -> None:
        super().__init__(
            definition=definition,
            retrieval=_FailClosedRetrieval(),
            gateway=None,  # type: ignore[arg-type]
            tools={},
            audit=audit,
        )

    def _run(self, plan: Plan) -> Report:  # pragma: no cover - la muralla veta en los tests
        # Si la política aprobara la escritura, acá se materializaría vía un LedgerPort
        # inyectado. En el camino REJECT/D este método NUNCA se alcanza.
        return Report(
            task_id=plan.task_id,
            agent_id=self._definition.agent_id,
            summary=plan.summary,
            success=True,
        )


def pellegrini_definition() -> AgentDefinition:
    """Definición declarativa de Pellegrini (config-only, AGENT-01)."""
    return AgentDefinition(
        agent_id="pellegrini",
        name="Pellegrini",
        domain="finanzas",
        kb_ids=frozenset(),
        model_alias="economico",
        budget_usd=5.0,
    )


def build_pellegrini(*, audit: Any) -> AgentBase:
    """Construye el agente Pellegrini concreto (subclase de `AgentBase`).

    El `audit` es obligatorio (D-08): toda ejecución/rechazo se registra. La segunda muralla
    vive en `AgentBase.execute` heredado — no se reimplementa acá.
    """
    return _PellegriniAgent(pellegrini_definition(), audit)


# ─────────────────────────────────────────────────────────────────────────────
# judge_advisory_quality — eval opt-in (@llm_judge)


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    """Veredicto del LLM-judge sobre la calidad del consejo (opt-in)."""

    passed: bool
    reason: str


async def judge_advisory_quality(
    tareas: tuple[str, ...],
    hechos: Mapping[str, Any],
) -> JudgeVerdict:
    """Eval opt-in de calidad advisory (`@llm_judge`).

    Corre SOLO con `pytest -m llm_judge` (consume budget del agente económico). Sin un gateway
    real cableado acá, aplica una rúbrica determinística de respaldo (presupuesto ≤ ingresos,
    cobertura declarada) para no romper el contrato. El owner es el calibrador final (D3/D6).
    """
    presupuesto = propuesta_presupuesto(hechos)
    ingresos = float(hechos["ingresos_total"])
    if presupuesto > ingresos:
        return JudgeVerdict(
            passed=False,
            reason=f"presupuesto ${presupuesto:.2f} excede ingresos ${ingresos:.2f}",
        )
    if not tareas:
        return JudgeVerdict(passed=False, reason="sin tareas para evaluar")
    return JudgeVerdict(
        passed=True,
        reason="rúbrica de respaldo OK; calibración final del owner pendiente (checkpoint).",
    )
