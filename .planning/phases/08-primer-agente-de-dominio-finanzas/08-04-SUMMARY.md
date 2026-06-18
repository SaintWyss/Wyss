---
phase: 08-primer-agente-de-dominio-finanzas
plan: 04
status: checkpoint-pending
subsystem: agents
tags: [pellegrini, finanzas, retrieval-adapter, second-wall, budget-gate, no-fabrication, hexagonal, d-73]

# Dependency graph
requires:
  - phase: 08-primer-agente-de-dominio-finanzas
    provides: "SqliteLedgerStore + LedgerPort + Transaccion (08-02); finance.query=A/finance.record=B + agent_budgets (08-03); RED scaffolds (08-01)"
  - phase: 07-modelo-de-agentes
    provides: "ConfiguredAgent + AgentRegistry + scoped_retrieval_factory hook + AgentBase.execute (segunda muralla)"
  - phase: 02-gateway-de-modelos
    provides: "CostTracker.authorize per-agent budget gate (BudgetExceeded fail-closed)"
provides:
  - "LedgerRetrieval — adapter del puerto Retrieval sobre LedgerPort (hechos pre-agregados como Hits)"
  - "agents.pellegrini — advise/handle_task/propuesta_presupuesto/build_pellegrini/judge_advisory_quality (config-only, sin tocar ConfiguredAgent/AgentRegistry)"
  - "Pellegrini E2E: 3 tareas D-87 via dispatcher+FakeOrchestrator auditadas; second wall en finance.record; budget cutoff"
affects: [08-checkpoint-owner-calibration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Retrieval-port adapter sobre un puerto NO-documental (LedgerPort): Pellegrini lee el ledger sin codigo de agente nuevo, via el hook scoped_retrieval_factory existente (D-73)"
    - "Hechos pre-agregados SQL inyectados como Hit.snippet: el LLM nunca recalcula totales (AI-SPEC modo de falla #1)"
    - "Independencia agents/ledger preservada: LedgerRetrieval importa SOLO el PUERTO core.ports.ledger; el SqliteLedgerStore concreto se inyecta por DI, nunca se importa"
    - "Segunda muralla heredada: build_pellegrini devuelve subclase de AgentBase; execute() veta REJECT/nivel-D antes de _run (no se reimplementa la muralla)"
    - "Firmas de produccion tipadas object donde el contrato RED lo exige; narrowing fail-closed adentro (_as_hechos / hasattr ask)"

key-files:
  created:
    - src/agents/ledger_retrieval.py
    - src/agents/pellegrini.py
    - tests/agents/test_ledger_retrieval.py
  modified:
    - src/agents/__init__.py
    - tests/agents/conftest.py
    - tests/agents/test_pellegrini_no_fabrication.py

key-decisions:
  - "agents.pellegrini es net-new ademas de ledger_retrieval.py: los tests RED de 08-01 importan agents.pellegrini (advise/build_pellegrini/handle_task/propuesta_presupuesto/judge_advisory_quality) y STATE.md lo confirma. Es infra de agente NUEVA (archivo nuevo), NO una modificacion de ConfiguredAgent/AgentRegistry → NO cruza D-73"
  - "Los hechos verificados viajan como Hit.snippet (unico canal de inyeccion sin tocar ConfiguredAgent, que rutea hits por <untrusted_content>). Tradeoff AI-SPEC §4 documentado abajo; la garantia de no-fabricacion (D2) la da la asercion reported ⊆ facts, independiente del bloque que lleve los hechos"
  - "Ventana de LedgerRetrieval: mes corriente por default, inyectable (desde/hasta) para tests deterministas; nunca full-table scan"
  - "propuesta_presupuesto = min(gastos, ingresos): determinista y <= ingresos siempre (D3 sensatez)"

metrics:
  duration_min: 22
  completed: "2026-06-17"
  tasks_completed: 2
  tasks_total: 3
  tests_passing: 424
  tests_skipped: 6
---

# Phase 8 Plan 04: Pellegrini E2E (coach de finanzas config-only) Summary

`LedgerRetrieval` + `agents.pellegrini` traen a Pellegrini a la vida como agente config-only que lee el ledger via el hook `scoped_retrieval_factory` y aconseja, dejando GREEN las 4 criterios del ROADMAP — con `ConfiguredAgent`/`AgentRegistry`/`cost.py`/`gateway.py`/`dispatcher.py` intactos (D-73). Tareas 1 y 2 completas; la Tarea 3 es el checkpoint del owner (calibracion de calidad advisory), pendiente.

## Que se construyo

### Tarea 1 — `LedgerRetrieval` (adapter del puerto Retrieval sobre LedgerPort)
- `src/agents/ledger_retrieval.py`: implementa `async def search(query, subject) -> SearchResult`. En vez de chunks de una BC, consulta el `LedgerPort` (`balance`/`surplus`/`query_by_category`/`coverage_days`) y empaqueta los totales **pre-agregados SQL** como un `Hit` sintetico cuyo `snippet` es el bloque "Hechos verificados del ledger". El LLM nunca suma filas (AI-SPEC modo #1).
- Ignora `query.kb_ids` a proposito (Pellegrini no tiene BC documental — RESEARCH A1). Ventana mensual explicita (inyectable). Ledger vacio → `degraded=True` + cobertura 0 (D3: declarar escasez, no proyectar).
- Importa **solo el PUERTO** `core.ports.ledger` (Protocol) + `core.domain` — nunca `ledger.sqlite_store`, preservando la independencia `agents` ⟂ `ledger` del import-linter.
- Export en `src/agents/__init__.py`. Fixtures nuevos en `tests/agents/conftest.py`: `pellegrini_definition` y `ledger_retrieval` (sobre un `SqliteLedgerStore` tmp sembrado con el SET RICO, ventana 2026-05). Test nuevo `tests/agents/test_ledger_retrieval.py` (conformidad estructural, hechos == ground truth, vacio → degradado).

### Tarea 2 — `agents.pellegrini` (segunda muralla + budget cutoff + 3 tareas D-87 E2E)
- `src/agents/pellegrini.py`:
  - `advise(gateway, hechos)`: arma el prompt con el bloque de hechos verificados (montos pre-agregados, tono coach) y llama `gateway.ask`; devuelve el texto. **D2 no-fabrication GREEN** (todo `$N` del consejo ⊆ hechos).
  - `handle_task(instruccion, hechos)`: convierte cada tarea D-87 del owner en un `Plan` de **SOLO LECTURA** (`finance.query`, nivel A → EXECUTE) que el dispatcher encola y audita. `propuesta_presupuesto(hechos) = min(gastos, ingresos)` → siempre ≤ ingresos (D3).
  - `build_pellegrini(audit)`: agente concreto (subclase de `AgentBase`) cuyo `_run` escribiria al ledger; **la segunda muralla es la heredada** — `AgentBase.execute` veta `REJECT`/nivel-D ANTES de `_run`, asi una escritura `finance.record` no owner-instruida nunca materializa (D5 / T-08-09, T-08-10).
  - `judge_advisory_quality(...)`: eval opt-in `@llm_judge` (fuera del CI por defecto).
- **Budget cutoff (D4):** `tests/gateway/test_cost_agent_budget_e2e.py` ya pasaba contra el gateway real sin tocar `cost.py` — confirma que el gate `CostTracker.authorize` veta con `BudgetExceeded` y **cero llamadas al provider** post-agote.

## Output del gate final (exacto)

```
pytest        → 424 passed, 6 skipped
mypy          → Success: no issues found in 190 source files
ruff check    → All checks passed!
lint-imports  → Contracts: 2 kept, 0 broken
                  "core es puro: stdlib only" KEPT
                  "las capas importan de core, nunca entre si" KEPT
```

Los 4 archivos de test objetivo (no_fabrication, second_wall, e2e, cost_agent_budget_e2e): **13 passed**.

## D-73 — archivos protegidos sin cambios

`git diff 6f49955 HEAD --` confirma UNCHANGED:
- `src/agents/configured_agent.py`
- `src/agents/registry.py`
- `src/gateway/cost.py`
- `src/gateway/gateway.py`
- `src/orchestrator/dispatcher.py`

Net-new produccion: `src/agents/ledger_retrieval.py` + `src/agents/pellegrini.py` (+ export en `__init__.py`). `agents.pellegrini` es archivo NUEVO de infra de agente — no modifica los protegidos, no cruza el limite.

## Tradeoff documentado (AI-SPEC §4)

`ConfiguredAgent._build_prompt` rutea los hits por `<untrusted_content>`. Los hechos del ledger son **datos confiables del owner**, no adversariales — idealmente irian en un bloque de evidencia, no marcados como hostiles. Como D-73 prohibe tocar `ConfiguredAgent`, el bloque de hechos se entrega COMO `Hit.snippet` (unico canal de inyeccion sin codigo de agente). La garantia de no-fabricacion (D2) la da la asercion `reported ⊆ facts`, independiente del bloque que cargue los hechos. **Deuda diferida** (no se resuelve en esta fase): si se quiere una separacion limpia evidencia/untrusted, requiere un cambio de codigo de agente — flaggear, no ejecutar aqui.

## Deviations from Plan

### 1. [Scope — Rule 2/3] `agents.pellegrini` es net-new ademas de `ledger_retrieval.py`
- **Encontrado en:** Tarea 1 (lectura de los tests RED de 08-01).
- **Issue:** El frontmatter del plan lista solo `ledger_retrieval.py` como produccion nueva, pero `test_pellegrini_*.py` importan `agents.pellegrini` (5 funciones) y `tests.ledger.conftest.HECHOS_VERIFICADOS`. Sin ese modulo, 10 tests quedan en `ModuleNotFoundError`.
- **Resolucion:** Se creo `src/agents/pellegrini.py` como infra de agente NUEVA. No modifica ningun archivo protegido → NO cruza D-73 (que prohibe *modificar* `ConfiguredAgent`/`AgentRegistry`, no agregar archivos en la capa). STATE.md ya anticipaba esto ("construir agents.pellegrini build_pellegrini/handle_task/advise/propuesta_presupuesto"). No requirio escalamiento porque ningun protegido se toco.

### 2. [Rule 1 — Bug] Regex de montos del test RED se tragaba el punto final de oracion
- **Encontrado en:** Tarea 2 (no_fabrication).
- **Issue:** `_MONTO_RE = r"\$\s*([\d][\d.,]*)"` sobre `"...te sobran $1200.00. "` capturaba `1200.00.` (con punto de oracion), y `_to_float("1200.00.")` levantaba `ValueError`. La string canonica y el regex los escribio 08-01; con esa entrada el test no podia pasar jamas.
- **Fix:** Regex ajustado a `r"\$\s*(\d[\d.,]*\d|\d)"` (el numeral no puede TERMINAR en separador). El control negativo (`$9999.99` fabricado) sigue detectando correctamente.
- **Archivo:** `tests/agents/test_pellegrini_no_fabrication.py`
- **Commit:** 974979d

## Known Stubs

- `_PellegriniAgent._run` y `judge_advisory_quality` usan una rubrica/escritura de respaldo determinista (no LLM real) — intencional: el camino REJECT/D nunca alcanza `_run` (la muralla veta antes) y el `@llm_judge` es opt-in fuera del CI. La calibracion real de calidad advisory es justamente el checkpoint del owner (Tarea 3). No bloquea el objetivo del plan.

## Checkpoint pendiente (Tarea 3 — gate=blocking, NO auto-aprobable)

El owner es el calibrador final de la calidad advisory (AI-SPEC §5, D3/D6) — los tests automaticos no la juzgan. Ver instrucciones de verificacion en el reporte al owner.

## Self-Check: PASSED
- `src/agents/ledger_retrieval.py` — FOUND
- `src/agents/pellegrini.py` — FOUND
- `tests/agents/test_ledger_retrieval.py` — FOUND
- Commit `7a36709` (Tarea 1) — FOUND
- Commit `974979d` (Tarea 2) — FOUND
