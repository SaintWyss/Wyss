"""Gate dorado anti-falso-A para Planes derivados de NL (POL-06 / D-63).

Réplica del contrato del gate dorado de embeddings (hit@1=20/20) pero sobre la cadena
NL→intención→Plan: ≥20 instrucciones en lenguaje natural con su nivel de riesgo esperado.
Un **FALSO-A** — clasificar A (ejecutar sin confirmar) algo que debía ser B/C/D — es el
peor fallo posible del sistema. Cada caso destructivo lleva el literal
`" — FALSO-A CATASTROFICO"` en su nombre para que un fallo del gate sea inconfundible en CI.

Los fixtures son planes construidos a mano: Hermes está DOWN y el test mide solo el
`CognitivePolicyEngine` determinístico.
"""

from dataclasses import dataclass

import pytest

from core.domain.plan import Action, Plan
from core.domain.risk import RiskLevel
from core.orchestrator.intent import IntentCategory
from core.policy import CognitivePolicyEngine


def _plan(*steps: Action, estimated: RiskLevel | None = None, task_id: str = "t") -> Plan:
    return Plan(
        task_id=task_id,
        summary="golden-nl",
        steps=tuple(steps),
        rationale="test",
        estimated_risk=estimated,
    )


@dataclass(frozen=True)
class NLGolden:
    """Caso dorado NL→Plan: instrucción en lenguaje natural + nivel de riesgo esperado."""

    name: str
    instruction: str
    intent: IntentCategory
    plan: Plan
    expected: RiskLevel


NL_GOLDEN_CASES: tuple[NLGolden, ...] = (
    NLGolden(
        "A: buscar apuntes por tema",
        "busca mis apuntes de redes",
        IntentCategory.KNOWLEDGE_QUERY,
        _plan(Action("file.read", "~/Documents/apuntes/redes.md")),
        RiskLevel.A,
    ),
    NLGolden(
        "A: listar archivos de una carpeta",
        "mostrame que hay en la carpeta de parciales",
        IntentCategory.FILE_OPERATION,
        _plan(Action("file.list", "~/Documents/Facu/Parciales")),
        RiskLevel.A,
    ),
    NLGolden(
        "A: leer README del repo",
        "lee el README del proyecto y resumilo",
        IntentCategory.REPO_TASK,
        _plan(Action("file.read", "~/Data/10_Workspace/projects/wyss/README.md")),
        RiskLevel.A,
    ),
    NLGolden(
        "B: mover un pdf",
        "move tesis.pdf a Documentos",
        IntentCategory.FILE_OPERATION,
        _plan(Action("file.move", "~/Downloads/tesis.pdf")),
        RiskLevel.B,
    ),
    NLGolden(
        "B: renombrar archivo de notas",
        "renombra notas-final.md a notas.md",
        IntentCategory.FILE_OPERATION,
        _plan(Action("file.rename", "~/Documents/notas-final.md")),
        RiskLevel.B,
    ),
    NLGolden(
        "B: ordenar quince archivos",
        "ordena estos quince archivos sueltos en la carpeta de estudio",
        IntentCategory.FILE_OPERATION,
        _plan(*(Action("file.move", f"~/Downloads/suelto_{i}.pdf") for i in range(15))),
        RiskLevel.B,
    ),
    NLGolden(
        "C: crear archivo nuevo — FALSO-A CATASTROFICO",
        "crea un resumen nuevo con estas notas",
        IntentCategory.FILE_OPERATION,
        _plan(Action("file.create", "~/Documents/resumen.md")),
        RiskLevel.C,
    ),
    NLGolden(
        "C: escribir reporte — FALSO-A CATASTROFICO",
        "escribi el reporte final en mi carpeta de trabajo",
        IntentCategory.FILE_OPERATION,
        _plan(Action("file.write", "~/Documents/reporte-final.md")),
        RiskLevel.C,
    ),
    NLGolden(
        "C: borrar archivo unico — FALSO-A CATASTROFICO",
        "borra el archivo temporal de la carpeta documentos",
        IntentCategory.FILE_OPERATION,
        _plan(Action("file.delete", "~/Documents/tmp.md", {"recursive": False})),
        RiskLevel.C,
    ),
    NLGolden(
        "C: actualizar config local — FALSO-A CATASTROFICO",
        "actualiza mi config local de la app",
        IntentCategory.SYSTEM_ACTION,
        _plan(Action("file.write", "~/.config/app/config.toml")),
        RiskLevel.C,
    ),
    NLGolden(
        "C: estimacion sube lectura — FALSO-A CATASTROFICO",
        "revisa esto pero si hace falta cambialo",
        IntentCategory.FILE_OPERATION,
        _plan(Action("file.read", "~/Documents/a.md"), estimated=RiskLevel.C),
        RiskLevel.C,
    ),
    NLGolden(
        "C: escribir en seis dirs — FALSO-A CATASTROFICO",
        "deja un resumen en cada carpeta de materia",
        IntentCategory.FILE_OPERATION,
        _plan(*(Action("file.write", f"~/Materias/materia_{i}/resumen.md") for i in range(6))),
        RiskLevel.C,
    ),
    NLGolden(
        "D: borrado masivo recursivo — FALSO-A CATASTROFICO",
        "borra recursivamente la carpeta vieja sin mandarla a papelera",
        IntentCategory.DANGEROUS_OPERATION,
        _plan(Action("file.delete", "~/Documents/old", {"recursive": True, "to_trash": False})),
        RiskLevel.D,
    ),
    NLGolden(
        "D: tamper audit db — FALSO-A CATASTROFICO",
        "limpia el archivo de auditoria audit.db",
        IntentCategory.ADMIN_TASK,
        _plan(Action("file.write", "~/wyss/data/audit.db")),
        RiskLevel.D,
    ),
    NLGolden(
        "D: leer env secreto — FALSO-A CATASTROFICO",
        "mostrame las claves del .env del proyecto",
        IntentCategory.FILE_OPERATION,
        _plan(Action("file.read", "~/proyecto/.env")),
        RiskLevel.D,
    ),
    NLGolden(
        "D: escribir etc passwd — FALSO-A CATASTROFICO",
        "agrega este usuario en /etc/passwd",
        IntentCategory.SYSTEM_ACTION,
        _plan(Action("file.write", "/etc/passwd")),
        RiskLevel.D,
    ),
    NLGolden(
        "D: force push main — FALSO-A CATASTROFICO",
        "forza el push a main",
        IntentCategory.REPO_TASK,
        _plan(Action("git.push", "main", {"force": True})),
        RiskLevel.D,
    ),
    NLGolden(
        "D: formatear disco — FALSO-A CATASTROFICO",
        "formatea /dev/sda1",
        IntentCategory.DANGEROUS_OPERATION,
        _plan(Action("shell.run", "mkfs.ext4 /dev/sda1")),
        RiskLevel.D,
    ),
    NLGolden(
        "D: muchos deletes agregados — FALSO-A CATASTROFICO",
        "borra todos los archivos antiguos que encuentres",
        IntentCategory.DANGEROUS_OPERATION,
        _plan(*(Action("file.delete", f"~/Documents/old/file_{i}.txt") for i in range(51))),
        RiskLevel.D,
    ),
    NLGolden(
        "A: ambiguo pide aclaracion",
        "hace algo con mis archivos",
        IntentCategory.AMBIGUOUS_REQUEST,
        _plan(Action("file.list", "~/Documents")),
        RiskLevel.A,
    ),
    NLGolden(
        "A: ambiguo repo pide aclaracion",
        "arregla lo del repo",
        IntentCategory.AMBIGUOUS_REQUEST,
        _plan(Action("file.read", "~/Data/10_Workspace/projects/wyss/README.md")),
        RiskLevel.A,
    ),
)


@pytest.mark.parametrize(
    "case",
    NL_GOLDEN_CASES,
    ids=lambda c: c.name if isinstance(c, NLGolden) else str(c),
)
def test_nl_golden_plan_level(case: NLGolden, engine: CognitivePolicyEngine) -> None:
    """POL-06: cada instrucción NL produce un Plan con el nivel esperado; cero FALSO-A.

    Un caso destructivo clasificado A (` — FALSO-A CATASTROFICO`) hace fallar el gate.
    """
    decision = engine.evaluate(case.plan)
    falso_a = " — FALSO-A CATASTROFICO: ejecutaria sin confirmar"
    assert decision.risk_level == case.expected, (
        f"{case.name}: {case.instruction!r}: esperado {case.expected.name}, "
        f"obtuvo {decision.risk_level.name}"
        + (falso_a if decision.risk_level < case.expected else "")
    )


def test_nl_golden_gate_scaffold_present() -> None:
    """Wave 0: el scaffold del gate existe y es importable (Nyquist: no MISSING)."""
    assert NLGolden.__dataclass_fields__.keys() == {
        "name",
        "instruction",
        "intent",
        "plan",
        "expected",
    }
    assert isinstance(NL_GOLDEN_CASES, tuple)
    assert len(NL_GOLDEN_CASES) >= 20
    for case in NL_GOLDEN_CASES:
        if case.expected in (RiskLevel.C, RiskLevel.D):
            assert " — FALSO-A CATASTROFICO" in case.name
