"""ModelGateway — la fachada que orquesta Flow 4 (GATE-01..05): único punto de salida a IA.

`ask(AgentModelRequest) -> ModelResponse` compone los componentes de las olas 02-02/03/04 en
el orden EXACTO de Flow 4, fail-closed:

  1. router.resolve(tier)       → TierConfig | UnknownTier (sin fallback, D-17)
  2. minimizer.scan(prompt)     → clean_prompt | SecretDetected ANTES de cualquier egress (D-20)
  3. construir ModelRequest      con model_alias + max_tokens del TIER, no del caller (D-16)
  4. loop de retry (D-25):       authorize() RE-PASA el gate cada intento → provider.complete;
                                 transiente (timeout/429/5xx) → backoff y reintenta (2x);
                                 4xx → fail-fast; sin fallback de tier
  5. cost.record (costo LOCAL, D-24)
  6. traces.write (prompt POST-min, D-22)
  7. audit.log COST_RECORDED
  8. devolver ModelResponse con el costo LOCAL (no el 0.0 del provider)

El retry vive ACÁ, nunca en los providers (que hacen raise_for_status sin reintentar, 02-03):
así el gate de presupuesto no se descontrola por doble-retry (Pitfall 1). El `AuditPort` se
inyecta por constructor — este módulo JAMÁS importa el paquete `audit` (contrato import-linter
`independence`, Pitfall 4): solo `core.ports.audit` y `core.domain.audit`.

D-23: sin streaming — `ask()` devuelve la respuesta completa; no existe `ask_stream()` (regla #9).
"""

import asyncio
import dataclasses
import uuid
from collections.abc import Mapping

import httpx

from core.domain.audit import ActorType, AuditEvent, AuditEventType
from core.domain.errors import (
    BudgetExceeded,
    ConfigError,
    CostLedgerError,
    SecretDetected,
    UnknownTier,
)
from core.domain.gateway import AgentModelRequest, ModelRequest, ModelResponse
from core.ports.audit import AuditPort
from core.ports.gateway import ModelProvider
from gateway.cost import CostTracker
from gateway.minimizer import ContextMinimizer
from gateway.router import ModelRouter
from gateway.traces import TraceStore

# Heurística simple de estimación de tokens de entrada para el gate de pre-autorización:
# ~4 chars por token (D-25 deja la heurística a discreción). El costo REAL del trace usa los
# tokens reportados por el provider; esto solo alimenta authorize() antes de la llamada.
_CHARS_PER_TOKEN = 4


def _is_transient(exc: httpx.HTTPStatusError) -> bool:
    """True si el status HTTP es transiente (429 o 5xx) — candidato a retry (D-25).

    4xx (excepto 429) son fatales: fail-fast sin reintentar (un 400/401/403 no mejora
    reintentando y solo gasta el presupuesto re-autorizando).
    """
    status = exc.response.status_code
    return status == 429 or status >= 500


class ModelGateway:
    """Implementa `ModelGatewayPort`: orquesta Flow 4 con retry centralizado (D-25)."""

    def __init__(
        self,
        *,
        router: ModelRouter,
        minimizer: ContextMinimizer,
        cost: CostTracker,
        traces: TraceStore,
        providers: Mapping[str, ModelProvider],
        audit: AuditPort,
        max_retries: int = 2,
        backoff_base: float = 0.5,
    ) -> None:
        self._router = router
        self._minimizer = minimizer
        self._cost = cost
        self._traces = traces
        self._providers = providers
        self._audit = audit
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    async def ask(self, request: AgentModelRequest) -> ModelResponse:
        """Orquesta Flow 4 y devuelve la ModelResponse con el costo LOCAL (D-24)."""
        # Paso 1: resolver tier (sin fallback, D-17).
        try:
            tier_cfg = self._router.resolve(request.tier)
        except UnknownTier as exc:
            self._audit_failed(request, f"tier desconocido: {exc.tier}")
            raise

        # Paso 2: minimizar — fail-closed ANTES de cualquier egress (D-20).
        try:
            clean_prompt = self._minimizer.scan(request.prompt)
        except SecretDetected as exc:
            # SOLO el pattern_name viaja al audit; NUNCA el secreto ni el prompt crudo (D-20).
            self._audit_failed(
                request,
                "payload bloqueado por secreto detectado",
                extra={"pattern": exc.pattern_name},
            )
            raise

        # Paso 3: ModelRequest con model_alias + max_tokens del TIER (D-16).
        est_in = max(1, len(clean_prompt) // _CHARS_PER_TOKEN)
        est_out = tier_cfg.max_tokens
        model_request = ModelRequest(
            prompt=clean_prompt,
            model_alias=tier_cfg.model_alias,
            max_tokens=tier_cfg.max_tokens,
        )

        # Paso 4: loop de retry (D-25) — el gate se RE-PASA en cada intento.
        resp = await self._complete_with_retry(
            request, tier_cfg.provider, tier_cfg.model_alias, est_in, est_out, model_request
        )

        # Paso 5: costo LOCAL + record durable (D-24). Un fallo acá es GRAVE (WR-07): el
        # provider YA consumió dinero y el ledger no lo refleja — el gate subcuenta de ahí
        # en adelante. Se audita TASK_FAILED y se convierte en CostLedgerError de dominio.
        try:
            cost = self._cost.record(
                request.agent_id,
                tier_cfg.model_alias,
                resp.tokens_in,
                resp.tokens_out,
                provider_reported_cost=resp.cost_usd or None,
            )
        except Exception as exc:
            self._audit_failed(
                request,
                "fallo grave: gasto real del provider SIN registrar en spend_ledger",
                extra={"error": type(exc).__name__},
            )
            raise CostLedgerError(
                "el gasto real del provider no pudo registrarse en spend_ledger; "
                "el gate de presupuesto queda subcontando — requiere intervención"
            ) from exc

        # Pasos 6-7 (WR-07): si el trace/audit falla DESPUÉS del record, el gasto ya quedó
        # registrado — se audita TASK_FAILED (con task_id correlacionable) y se re-raise:
        # un retry del caller gastaría dinero real de nuevo, el motivo debe quedar trazado.
        try:
            # Paso 6: trace consultable, prompt POST-min (D-22).
            self._traces.write(
                trace_id=uuid.uuid4().hex,
                task_id=request.task_id,
                agent_id=request.agent_id,
                tier=request.tier,
                purpose=request.purpose,
                prompt=clean_prompt,
                output=resp.text,
                tokens_in=resp.tokens_in,
                tokens_out=resp.tokens_out,
                cost_usd=cost,
                latency_ms=resp.latency_ms,
            )

            # Paso 7: auditar el costo registrado (cost.record ya emite COST_RECORDED; este
            # evento del gateway correlaciona el costo con tier/model/tokens por task_id).
            self._audit.log(
                AuditEvent.new(
                    actor_type=ActorType.SYSTEM,
                    actor_id="gateway",
                    event_type=AuditEventType.COST_RECORDED,
                    message=f"llamada completada tier={request.tier}",
                    task_id=request.task_id,
                    payload={
                        "tier": request.tier,
                        "model": tier_cfg.model_alias,
                        "cost_usd": cost,
                        "tokens_in": resp.tokens_in,
                        "tokens_out": resp.tokens_out,
                    },
                )
            )
        except Exception as exc:
            self._audit_failed(
                request,
                "fallo post-record: trace/audit no escrito (gasto YA registrado)",
                extra={"error": type(exc).__name__},
            )
            raise

        # Paso 8: la respuesta lleva el costo LOCAL, no el 0.0 del provider.
        return dataclasses.replace(resp, cost_usd=cost)

    async def _complete_with_retry(
        self,
        request: AgentModelRequest,
        provider_name: str,
        model_alias: str,
        est_in: int,
        est_out: int,
        model_request: ModelRequest,
    ) -> ModelResponse:
        """Autoriza+llama con retry transiente (D-25). El gate se re-pasa cada intento."""
        # Defensa en profundidad (WR-04): el bootstrap valida los providers al boot, pero si
        # este gateway se cableó a mano con un provider faltante, el fallo debe ser un error
        # de dominio AUDITADO, no un KeyError crudo sin rastro.
        provider = self._providers.get(provider_name)
        if provider is None:
            self._audit_failed(request, f"provider no construido: {provider_name}")
            raise ConfigError(
                f"provider '{provider_name}' del tier no está construido en el gateway; "
                f"disponibles: {', '.join(sorted(self._providers)) or '(ninguno)'}"
            )
        last_exc: httpx.HTTPStatusError | httpx.TransportError | None = None
        for attempt in range(self._max_retries + 1):
            # (a) gate pre-autorización RE-PASADO en cada intento (D-18/D-25).
            try:
                self._cost.authorize(request.agent_id, model_alias, est_in, est_out)
            except BudgetExceeded:
                self._audit_failed(request, "presupuesto agotado")
                raise
            # Reserva en vuelo (WR-06): mientras el provider corre (punto de suspensión),
            # otras corutinas concurrentes ven este estimado en authorize() y no pueden
            # exceder el presupuesto. Se libera al terminar el intento; en el camino de
            # éxito no hay await entre release y cost.record (sin ventana de subconteo).
            reserved = self._cost.reserve(request.agent_id, model_alias, est_in, est_out)
            # (b)+(c) llamada al provider; clasificar el error.
            try:
                return await provider.complete(model_request)
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if not _is_transient(exc):
                    # 4xx fatal: fail-fast sin retry (Pitfall 1).
                    self._audit_failed(
                        request, f"error fatal del provider: {exc.response.status_code}"
                    )
                    raise
            except httpx.TransportError as exc:
                # TransportError cubre timeout/ConnectError/RemoteProtocolError (WR-05):
                # transientes por naturaleza (ej. LiteLLM caído) → retry y, agotado,
                # TASK_FAILED auditado — el fallo de red nunca queda sin rastro.
                last_exc = exc
            finally:
                # Liberar SIEMPRE la reserva del intento (éxito, fatal o transiente):
                # en éxito, record() registra el gasto real inmediatamente después sin
                # ceder el control; en fallo, el próximo intento re-reserva (WR-06).
                self._cost.release(request.agent_id, reserved)
            # transiente: backoff antes de reintentar (mismo provider, sin fallback de tier).
            if attempt < self._max_retries:
                await asyncio.sleep(self._backoff_base * 2**attempt)
        # Agotados los retries en transiente: auditar y re-raise el último error.
        self._audit_failed(request, "transiente persistente: retries agotados")
        assert last_exc is not None  # invariante: el loop solo sale acá tras un transiente
        raise last_exc

    def _audit_failed(
        self,
        request: AgentModelRequest,
        reason: str,
        *,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        """Emite TASK_FAILED con el MOTIVO (nunca el prompt crudo ni el secreto, D-20/V7)."""
        payload: dict[str, object] = {"tier": request.tier, "reason": reason}
        if extra is not None:
            payload.update(extra)
        self._audit.log(
            AuditEvent.new(
                actor_type=ActorType.SYSTEM,
                actor_id="gateway",
                event_type=AuditEventType.TASK_FAILED,
                message=reason,
                task_id=request.task_id,
                payload=payload,
            )
        )
