"""Puerto de herramientas de ejecución — execute pareado con verify (doc 11)."""

from typing import Protocol

from core.domain import Action, RiskLevel, ToolResult, Verification


class Tool(Protocol):
    """Adapter de ejecución. Declara su techo de riesgo; toda ejecución se verifica."""

    @property
    def name(self) -> str: ...

    @property
    def max_risk(self) -> RiskLevel: ...

    def describe(self, action: Action) -> str: ...

    async def execute(self, action: Action) -> ToolResult: ...

    async def verify(self, action: Action, result: ToolResult) -> Verification: ...
