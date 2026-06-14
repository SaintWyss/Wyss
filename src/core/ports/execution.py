"""Puerto de herramientas de ejecución — execute pareado con verify (doc 11)."""

from typing import Protocol

from core.domain import Action, RiskLevel, ToolResult, Verification
from core.domain.plan import Plan


class Tool(Protocol):
    """Adapter de ejecución. Declara su techo de riesgo; toda ejecución se verifica."""

    @property
    def name(self) -> str: ...

    @property
    def max_risk(self) -> RiskLevel: ...

    def describe(self, action: Action) -> str: ...

    async def execute(self, action: Action) -> ToolResult: ...

    async def verify(self, action: Action, result: ToolResult) -> Verification: ...


class PlanRunner(Protocol):
    """Frontera de ejecución que `agents` consume sin importar el paquete `execution`.

    `PlanExecutor` (Fase 6, `execution/executor.py`) ya satisface esta firma:
        async def run(self, plan: Plan) -> ExecutorResult

    El retorno se tipa `object` deliberadamente: `ExecutorResult` vive en `execution/`,
    que `core` no puede importar (import-linter, contrato de independencia de capas).
    `ConfiguredAgent` inspecciona `.success` y `.detail` vía duck typing — nunca
    hace `isinstance(result, ExecutorResult)`.

    El bootstrap (composition root) inyecta la impl concreta; `agents` nunca
    importa de `execution`. Resuelve la Open Question 1 de RESEARCH respetando el
    hexágono.
    """

    async def run(self, plan: Plan) -> object: ...
