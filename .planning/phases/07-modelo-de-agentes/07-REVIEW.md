# Code Review — Fase 07 "Modelo de Agentes"

**Revisor:** Gemini (gemini-2.5-flash) sobre diff completo de la fase.
**Triaje / decisión de fixes:** Claude (Opus 4.8, orquestador — los gates quedan en Claude por CONVENTIONS).
**Veredicto global:** PASS — ningún finding bloqueante. 1 CRITICAL descartado como falso positivo, resto deferido/by-design.

---

## CRITICAL

### C1 — `configured_agent.py:_actions_from_lines` "rm -rf" → `shell.run` = supuesto bypass de la segunda muralla
**Gemini:** el parser crea directamente una acción `shell.run` al detectar "rm -rf", saltando `engine.evaluate`.

**Decisión orquestador: RECHAZADO — falso positivo.**
El parser NO saltea la política. Flujo real en `_run` (configured_agent.py:226-230):
```
226  agent_plan = _run_coro_sync(_arun())     # parsea el output del LLM
227  decision = self._engine.evaluate(agent_plan)   # SEGUNDA MURALLA — siempre corre
228  self._raise_if_rejected(plan, decision)        # bloquea D/REJECT antes de ejecutar
230  result = _run_coro_sync(self._runner.run(agent_plan))  # solo si pasó
```
Todo `agent_plan` —venga del parser que venga— pasa por `engine.evaluate` antes de tocar el runner. El special-case "rm -rf" hace lo OPUESTO a un bypass: convierte el texto peligroso en una `Action(type="shell.run")` tipada y visible, que la denylist determinística (mass-delete) clasifica como D → REJECT → bloqueada + auditada. `test_golden_injection.py` lo prueba con el `CognitivePolicyEngine` real (no mock).

Nota menor (no seguridad): el match por string "rm -rf" es una heurística de code-smell en un parser v0.1; el parser robusto está deferido explícitamente a Fase 8 (07-04-PLAN.md). Sin acción en esta fase.

---

## HIGH

### H1 — `configured_agent.py:_run_coro_sync` crea thread + event loop nuevo por cada call
**Gemini:** overhead por interacción (gateway/runner); posible cuello de botella/deadlock bajo carga.

**Decisión: BACKLOG (no bloqueante para v0.1).**
Real, pero el perfil de v0.1 es single-owner local, API-first, bajo volumen — el costo de un thread+loop por call es irrelevante a esta escala. El puente sync/async está documentado como tradeoff consciente (Pitfall 6 en 07-04-PLAN.md: `_run` debe permanecer sync por contrato de `AgentBase`). Reevaluar si Fase 8+ mete concurrencia real: pool de hilos con loop por hilo, o asincronizar la cadena entera.

---

## MEDIUM

### M1 — `configured_agent.py:_run` mezcla planificación y ejecución; `gateway is None` devuelve el plan original
**Gemini:** el contrato `AgentBase._run(plan)` sugiere ejecutar un plan ya aprobado, no generarlo; gateway None no cumple el ciclo.

**Decisión: BY-DESIGN (cambiarlo = decisión de arquitectura del owner, fuera de scope de fase).**
`_run` ES el entrypoint del ciclo AGENT-01 (retrieval→prompt→gateway→evaluate→run) por diseño del owner — el `plan` entrante aporta `rationale` (instrucción) + `task_id`. El camino `gateway is None` igual pasa por `engine.evaluate` (L227 corre siempre), así que la segunda muralla no se saltea ni en el modo degenerado. Si se quiere separar `plan()` de `execute()`, es una decisión de contrato que escala al owner; no se toca acá.

---

## LOW

### L1 — `permission_store.py:SQLitePermissionStore` sin `close()` explícito
Robustez menor. Conexión vive lo que vive el proceso (daemon single-owner). BACKLOG: agregar `close()` + invocar en shutdown.

### L2 — `permission_store.py` `datetime.fromisoformat(str(granted_at))` sin guard
Robustez menor sobre input controlado (la DB la escribe el propio store). BACKLOG: `try/except ValueError` → excepción de dominio.

---

## Sin findings (validado por Gemini)
- Permisos saltables: `ScopedRetrieval` robusto, golden test lo valida.
- Fugas de contexto a modelos externos: `_build_prompt` usa `<untrusted_content>` correcto.
- Violaciones hexagonales: `PlanRunner` en `core.ports` es sólido; capas correctas.
- Aislamiento de agentes: `AgentRegistry` + `AgentDefinition` frozen + memoria por agente.
