"""CostTracker — gate de presupuesto pre-autorización + registro de gasto (GATE-04, D-18/D-24).

`authorize()` veta con `BudgetExceeded` ANTES de cada llamada al provider: lee el gasto
acumulado del mes (durable en spend_ledger), suma el costo estimado LOCAL y compara contra el
presupuesto global y el cap por-agente. Si excede, levanta — la llamada nunca sale (Pitfall 2:
un presupuesto que solo registra después es advisory, no enforced).

El costo SIEMPRE se calcula local (`(in+out)/1000 * precio_config`, D-24): el costo reportado
por el provider se guarda comparativo en `cost_usd_provider` pero NUNCA gobierna el gate. No
existe API runtime para mutar el presupuesto (D-19, regla #6) — destrabe solo editando config
+ reload; esta clase no expone setters de límites.

El estado de gasto vive en una tabla `spend_ledger` dentro de traces.db (una sola DB de
gateway, Open Question 3); el DDL lo aporta `traces_schema.apply_schema`.
"""

from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from core.domain.audit import ActorType, AuditEvent, AuditEventType
from core.domain.errors import BudgetExceeded
from core.ports.audit import AuditPort
from gateway.db import open_gateway_db

_INSERT = (
    "INSERT INTO spend_ledger "
    "(agent_id, model_alias, tokens_in, tokens_out, "
    "cost_usd_local, cost_usd_provider, created_at) "
    "VALUES (?, ?, ?, ?, ?, ?, ?)"
)


class CostTracker:
    """Gate de presupuesto: veta pre-autorización (D-18) + registra gasto local durable (D-24).

    Sin setters de límites: el presupuesto solo cambia editando config + reload (D-19, regla #6).
    """

    def __init__(
        self,
        db_path: Path,
        prices: dict[str, float],
        global_budget: float,
        agent_budgets: dict[str, float],
        audit: AuditPort,
    ) -> None:
        """Abre la DB de gateway (0600 + WAL fail-fast vía `open_gateway_db`, WR-08) y fija
        límites inmutables. Un CostTracker standalone tiene las MISMAS garantías de
        durabilidad/permisos que TraceStore — no dependen del orden de construcción."""
        self._db_path = db_path
        self._prices = dict(prices)
        self._global_budget = global_budget
        self._agent_budgets = dict(agent_budgets)
        self._audit = audit
        # Reservas en vuelo (WR-06): estimados de llamadas autorizadas cuyo gasto real aún
        # no se registró. Sin esto, N asks concurrentes con presupuesto para 1 pasan TODOS
        # el gate (TOCTOU entre authorize() y record() a través del await del provider).
        # No requiere asyncio.Lock: reserve/release/authorize son síncronos y el event loop
        # no suspende dentro de ellos — son atómicos respecto a otras corutinas.
        self._inflight_global: float = 0.0
        self._inflight_agent: dict[str, float] = {}
        self._conn = open_gateway_db(db_path)

    def estimate_cost(self, model_alias: str, est_tokens_in: int, est_tokens_out: int) -> float:
        """Costo local estimado: (in+out)/1000 * precio del alias (D-24).

        `KeyError` si el alias no tiene precio en config — fail-fast, config incompleta.
        """
        price = self._prices[model_alias]
        return (est_tokens_in + est_tokens_out) / 1000 * price

    def authorize(self, agent_id: str, model_alias: str, est_in: int, est_out: int) -> None:
        """Veta con `BudgetExceeded` si gasto + en-vuelo + estimado excede global o cap.

        Se llama ANTES de `provider.complete()` (Pitfall 2). Cada retry (D-25) re-llama esto.
        El gasto en vuelo (reservas de llamadas concurrentes aún sin record) cuenta contra
        ambos límites (WR-06): el presupuesto es enforced también bajo concurrencia.
        """
        est = self.estimate_cost(model_alias, est_in, est_out)
        if self.month_spend() + self._inflight_global + est > self._global_budget:
            raise BudgetExceeded("presupuesto global mensual agotado")
        cap = self._agent_budgets.get(agent_id)
        if cap is not None:
            inflight_agent = self._inflight_agent.get(agent_id, 0.0)
            if self.month_spend_agent(agent_id) + inflight_agent + est > cap:
                raise BudgetExceeded(f"presupuesto del agente {agent_id} agotado")

    def reserve(self, agent_id: str, model_alias: str, est_in: int, est_out: int) -> float:
        """Reserva el estimado como gasto EN VUELO hasta `release()` (WR-06).

        El gateway reserva tras pasar `authorize()` y libera al terminar el intento
        (éxito o fallo): mientras el provider corre, otras corutinas concurrentes ven
        la reserva en `authorize()` y no pueden exceder el presupuesto. Devuelve el
        monto reservado, que DEBE pasarse a `release()`.
        """
        est = self.estimate_cost(model_alias, est_in, est_out)
        self._inflight_global += est
        self._inflight_agent[agent_id] = self._inflight_agent.get(agent_id, 0.0) + est
        return est

    def release(self, agent_id: str, amount: float) -> None:
        """Libera una reserva en vuelo hecha con `reserve()` (piso en 0.0, nunca negativo)."""
        self._inflight_global = max(0.0, self._inflight_global - amount)
        remaining = self._inflight_agent.get(agent_id, 0.0) - amount
        if remaining <= 0.0:
            self._inflight_agent.pop(agent_id, None)
        else:
            self._inflight_agent[agent_id] = remaining

    def record(
        self,
        agent_id: str,
        model_alias: str,
        tokens_in: int,
        tokens_out: int,
        provider_reported_cost: float | None = None,
        created_at: str | None = None,
    ) -> float:
        """Persiste el gasto real (costo LOCAL, D-24) y sube el acumulado del mes.

        `provider_reported_cost` se guarda solo comparativo — NUNCA gobierna el gate (D-24).
        Devuelve el costo local registrado. Emite un evento COST_RECORDED al audit (nunca con
        el secreto, solo metadatos de costo).
        """
        cost_local = self.estimate_cost(model_alias, tokens_in, tokens_out)
        ts = created_at if created_at is not None else datetime.now(UTC).isoformat()
        self._conn.execute(
            _INSERT,
            (
                agent_id,
                model_alias,
                tokens_in,
                tokens_out,
                cost_local,
                provider_reported_cost,
                ts,
            ),
        )
        self._conn.commit()
        self._audit.log(
            AuditEvent.new(
                actor_type=ActorType.SYSTEM,
                actor_id=agent_id,
                event_type=AuditEventType.COST_RECORDED,
                message=f"costo registrado para {model_alias}",
                payload={
                    "model_alias": model_alias,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "cost_usd_local": cost_local,
                    "cost_usd_provider": provider_reported_cost,
                },
            )
        )
        return cost_local

    def month_spend(self) -> float:
        """Gasto local acumulado en el mes calendario actual (ventana sobre created_at)."""
        (total,) = self._conn.execute(
            "SELECT COALESCE(SUM(cost_usd_local), 0.0) FROM spend_ledger WHERE created_at >= ?",
            (self._month_start_iso(),),
        ).fetchone()
        return float(total)

    def month_spend_agent(self, agent_id: str) -> float:
        """Gasto local del agente en el mes calendario actual."""
        (total,) = self._conn.execute(
            "SELECT COALESCE(SUM(cost_usd_local), 0.0) FROM spend_ledger "
            "WHERE agent_id = ? AND created_at >= ?",
            (agent_id, self._month_start_iso()),
        ).fetchone()
        return float(total)

    @staticmethod
    def _month_start_iso() -> str:
        """ISO del primer instante del mes calendario actual en UTC."""
        now = datetime.now(UTC)
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()

    def close(self) -> None:
        """Cierra la conexión subyacente."""
        self._conn.close()

    def __enter__(self) -> "CostTracker":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
