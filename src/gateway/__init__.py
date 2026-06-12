"""Gateway de Modelos — único punto de salida a IA externa (GATE-01..05).

Componentes: ModelRouter, ContextMinimizer, CostTracker, TraceStore, providers (adapters httpx)
y la fachada `ModelGateway` que los orquesta (Flow 4). El composition root vive en
`bootstrap.gateway` (arma el ModelGateway desde GatewaySettings con AuditPort inyectado).
"""

from gateway.gateway import ModelGateway

__all__ = ["ModelGateway"]
