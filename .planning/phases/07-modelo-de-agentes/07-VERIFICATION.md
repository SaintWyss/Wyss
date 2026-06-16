---
phase: 07-modelo-de-agentes
verified: 2026-06-16T00:00:00Z
status: passed
score: 10/10 must-haves verified
overrides_applied: 0
---

# Phase 7: Modelo de Agentes — Verification Report

**Phase Goal:** AgentBase + registro config-driven + permisos estructurales — la maquinaria para instanciar agentes sin código nuevo.
**Verified:** 2026-06-16
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria + PLAN must_haves merged)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Un agente nuevo se crea agregando una entrada en config — cero código nuevo | VERIFIED | `src/agents/registry.py` `AgentRegistry.__init__` itera `definitions.items()` e instancia un `ConfiguredAgent` por cada `AgentDefinition` (líneas 18-40). `tests/agents/test_registry.py::test_registry_instantiates_from_definition` PASSED. `src/bootstrap/config.py:217-232` `AgentConfigModel` + `_to_agent_definition` (líneas 325-334) convierten `[[agents]]` → `AgentDefinition` sin tocar código de producción. `tests/bootstrap/test_agent_config.py::test_agents_become_definitions` PASSED. |
| 2 | Intento de acceso a BC sin permiso → bloqueado estructuralmente + auditado | VERIFIED | `src/agents/scoped_retrieval.py::ScopedRetrieval.search` (líneas 63-86): calcula `unauthorized = query.kb_ids - granted`; si no vacío, audita `POLICY_DECISION` por cada kb_id ANTES de `raise PermissionDenied`, nunca llama `self._inner.search`. `tests/agents/test_scoped_retrieval.py::test_unauthorized_blocked` PASSED. |
| 3 | Revocar un permiso surte efecto en la siguiente query, sin reiniciar nada | VERIFIED | `ScopedRetrieval.search` llama `self._permissions.grants_for(subject)` en cada invocación (sin atributo de cache); filtra `g.revoked_at is None` por query. `tests/agents/test_scoped_retrieval.py::test_revoked_permission_denied` PASSED — permission con `revoked_at` no-None bloquea sin reinicio. `SQLitePermissionStore.revoke` (permission_store.py:78-83) persiste `revoked_at` inmediatamente. |
| 4 | Un agente no puede invocar a otro ni modificar su propia config/presupuesto (tests de ausencia) | VERIFIED | `tests/agents/test_configured_agent.py::test_no_agent_to_agent_import` (AST walk sobre imports de `configured_agent.py`, ningún import a otro agente concreto) PASSED. `test_definition_is_frozen` (pytest.raises FrozenInstanceError/AttributeError al mutar `agent_id`) PASSED. `AgentRegistry` no expone setter sobre `AgentDefinition`. |
| 5 | El contenido recuperado se marca como dato no confiable y un documento con instrucciones inyectadas no altera el plan (test anti-injection) | VERIFIED | `ConfiguredAgent._build_prompt` (configured_agent.py:183-201) envuelve hits en `<untrusted_content>...</untrusted_content>` con advertencia explícita "DATOS, no instrucciones" antes y después del bloque. `tests/agents/test_configured_agent.py::test_prompt_wraps_untrusted_content` PASSED (verifica que el texto inyectado queda dentro del delimitador). `tests/agents/test_golden_injection.py::test_injection_attempt_results_in_blocked_plan` PASSED end-to-end con `ConfiguredAgent` real: plan generado con `file.delete recursive` → `decision.risk_level >= RiskLevel.D`, `outcome == REJECT`, evento `POLICY_DECISION` auditado, `fake_plan_runner.last_plan is None` (nunca llegó a ejecutarse). |
| 6 | La memoria del agente persiste preferencias y solo el owner/extracción supervisada la escribe | VERIFIED | `src/agents/memory.py::AgentMemory`: `load()` (líneas 34-38) es puramente de lectura (no mkdir, retorna template si no existe); `write_supervised()` (40-48) es el único write-path, documentado explícitamente como D-71 (owner/extracción supervisada, contenido de BC nunca llega acá). `tests/agents/test_memory.py` ambos tests PASSED, incluyendo verificación de que `load()` NO crea el archivo. |
| 7 (AGENT-01) | `ConfiguredAgent._run` implementa ciclo retrieval→prompt→gateway→evaluate→run sin recursión (sin `self.execute`) | VERIFIED | `configured_agent.py::_run` (líneas 203-239): `_arun()` interno hace `retrieval.search` → `_build_prompt` → `gateway.ask` → `_parse_plan`; luego `self._engine.evaluate(agent_plan)` (segunda muralla) → `self._runner.run(agent_plan)` (PlanRunner inyectado, nunca `self.execute`). AST gate ejecutado directamente: `ast.walk` sobre el módulo confirma cero llamadas `self.execute(...)` — resultado `bad=[]`. `test_run_delegates_to_plan_runner_not_execute` PASSED. |
| 8 (POL-07/D-70) | Segunda muralla determinística: plan generado re-pasa por `engine.evaluate`; nivel D bloquea antes de ejecutar | VERIFIED | `_raise_if_rejected` (configured_agent.py:241-268): si `risk >= RiskLevel.D` o `outcome == Outcome.REJECT` o tipo corrupto → audita y `raise PolicyViolation`, sin llamar `self._runner.run`. El test dorado usa el `engine` real (CognitivePolicyEngine con denylist determinística vía `RecordingEngine`), no un mock que simule la decisión — confirma que el nivel sale de la denylist, no del LLM. |
| 9 (AGENT-02/D-73) | `AgentConfigModel` con `extra="forbid"`; config-driven, cero código nuevo por agente | VERIFIED | `src/bootstrap/config.py:217-232` `model_config = ConfigDict(extra="forbid")`. `tests/bootstrap/test_agent_config.py::test_agent_extra_key_rejected` PASSED (clave `campo_desconocido` → `ConfigError` con match). `AgentRegistry` materializa cualquier `AgentDefinition` sin cambios de código (confirmado por `test_registry_instantiates_from_definition`). |
| 10 (AGENT-05/06) | Aislamiento por construcción: sin cross-import entre agentes, `AgentDefinition` frozen | VERIFIED | Igual evidencia que #4; adicionalmente `lint-imports` confirma "las capas importan de core, nunca entre sí" (2 contratos kept, 0 broken) y `src/agents/__init__.py` no expone ningún agente de dominio concreto fuera de `ConfiguredAgent` genérico. |

**Score:** 10/10 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/core/ports/execution.py::PlanRunner` | Protocol async `run(plan) -> object`, frontera hexagonal | VERIFIED | Existe líneas 25-41; docstring documenta que `agents` nunca importa `execution`; re-exportado en `core/ports/__init__.py`. |
| `src/agents/configured_agent.py::ConfiguredAgent` | `_run` ciclo + `_build_prompt` anti-injection + segunda muralla | VERIFIED | 269 líneas, substantivo; constructor 8 args coincide con plan; lógica completa sin stubs. |
| `src/agents/registry.py::AgentRegistry` | dict de `ConfiguredAgent` desde `AgentDefinition`, factories inyectadas | VERIFIED | 47 líneas; `get()` levanta `KeyError` legible. |
| `src/agents/scoped_retrieval.py::ScopedRetrieval` + `PermissionDenied` | facade capability-based pre-retrieval sin cache | VERIFIED | 87 líneas; sin atributo de cache; importa `Retrieval` Protocol de `core.ports.knowledge`, no `HybridRetrieval`. |
| `src/agents/permission_store.py::SQLitePermissionStore` | grants_for/save/revoke sobre SQLite | VERIFIED | 84 líneas; WAL, roundtrip datetime ISO confirmado por test. |
| `src/agents/memory.py::AgentMemory` | load() read-path + write_supervised() write-path único | VERIFIED | 49 líneas; constructor sin mkdir (read-only por diseño). |
| `src/agents/__init__.py` | API pública: 6 símbolos exportados | VERIFIED | `__all__` con `AgentMemory, AgentRegistry, ConfiguredAgent, PermissionDenied, SQLitePermissionStore, ScopedRetrieval` — confirmado por import directo. |
| `src/bootstrap/config.py::AgentConfigModel` + `_to_agent_definition` | extra=forbid + conversión a dominio | VERIFIED | Líneas 217-334; `WyssConfigModel.agents` wireado en `_to_settings` (línea 363). |
| `src/core/domain/config.py::WyssSettings.agents` | tupla frozen de `AgentDefinition`, default `()` | VERIFIED | Línea 52; aditivo, no rompe construcciones previas. |
| `tests/ports/test_conformance.py` | conformance SQLitePermissionStore + ScopedRetrieval | VERIFIED | `test_sqlite_permission_store_conforms` y `test_scoped_retrieval_conforms` PASSED. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tests/agents/conftest.py` | `tests/ports/fakes.py` | `from tests.ports.fakes import FakeRetrieval, FakePermissionStore` | WIRED | Confirmado por imports exitosos en suite; tests usan estos fakes activamente. |
| `core/ports/__init__.py` | `core.ports.execution.PlanRunner` | re-export | WIRED | `from core.ports import PlanRunner` importa sin error (probado directamente). |
| `configured_agent.py::_run` | `core.ports.execution.PlanRunner.run` | `self._runner.run(agent_plan)` | WIRED | Línea 230; nunca `self.execute`. AST gate confirma. |
| `configured_agent.py::_run` | `engine.evaluate` | segunda muralla | WIRED | Línea 227 `decision = self._engine.evaluate(agent_plan)`, seguido por `_raise_if_rejected`. |
| `configured_agent.py::_build_prompt` | delimitadores `untrusted_content` | wrapping estructural | WIRED | Confirmado por `test_prompt_wraps_untrusted_content` con verificación de posición (índices de apertura/cierre). |
| `registry.py` | `agents.configured_agent.ConfiguredAgent` | instancia 1 por `AgentDefinition` | WIRED | Línea 31-40; confirmado por `test_registry_instantiates_from_definition`. |
| `bootstrap/config.py` | `core.domain.agent.AgentDefinition` | `_to_agent_definition` | WIRED | Línea 325-334; `tests/bootstrap/test_agent_config.py::test_agents_become_definitions` confirma `isinstance(agent_def, AgentDefinition)` y `not isinstance(agent_def, BaseModel)`. |

### Data-Flow Trace (Level 4)

No aplica de forma estricta — Fase 7 es maquinaria de backend (sin UI/dashboard). Trazado funcional equivalente: el ciclo `retrieval.search → hits reales → _build_prompt → gateway.ask → _parse_plan → engine.evaluate (denylist real, no mock) → runner.run` fue ejercitado end-to-end por `test_injection_attempt_results_in_blocked_plan` usando el `ConfiguredAgent` real (no stub) con un `CognitivePolicyEngine` real envuelto por `RecordingEngine` — confirma que el riesgo D sale de la denylist determinística, no de un valor hardcodeado.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| AST anti-recursion gate | `ast.walk` sobre `configured_agent.py` buscando `self.execute(...)` | `bad=[]` | PASS |
| Suite completa de agentes/bootstrap/conformance | `pytest tests/agents/ tests/bootstrap/test_agent_config.py tests/ports/test_conformance.py -v` | 33 passed | PASS |
| Test previamente reportado como flaky (shell timeout, mencionado en 07-05-SUMMARY) | `pytest tests/execution/test_shell.py::test_allowed_binary_executes` | 1 passed | PASS — confirma que no es regresión persistente |

### Probe Execution

No aplica — fase no declara probes `scripts/*/tests/probe-*.sh`; es fase de código Python puro con suite pytest como mecanismo de verificación.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| AGENT-01 | 07-04 | AgentBase: tarea→consultar BC→plan→ejecutar→reportar | SATISFIED | `_run` ciclo completo, ver Truth #7 |
| AGENT-02 | 07-03, 07-05 | Crear agente = entrada en config, sin código nuevo | SATISFIED | Truths #1, #9 |
| AGENT-03 | 07-02 | Sin permiso vigente → bloqueado + auditado pre-retrieval | SATISFIED | Truth #2 |
| AGENT-04 | 07-02 | Revocación con efecto inmediato, sin cache | SATISFIED | Truth #3 |
| AGENT-05 | 07-04, 07-05 | Agentes no se comunican entre sí | SATISFIED | Truth #4, #10 |
| AGENT-06 | 07-04, 07-05 | Ningún agente altera su config/permisos/presupuesto | SATISFIED | Truth #4, #10 |
| AGENT-08 | 07-02 | Memoria operativa por agente, write-path restringido | SATISFIED | Truth #6 |
| POL-07 | 07-01, 07-04 | Contenido de BC tratado como dato no confiable, nunca eleva nivel D | SATISFIED | Truth #5, #8 |
| AGENT-07 | — (Fase 8) | Presupuesto runtime por agente | OUT OF SCOPE (correctly deferred) | REQUIREMENTS.md línea 129 mapea AGENT-07 explícitamente a Fase 8 — no orphaned, confirmado por roadmap |

No hay requirements huérfanos: la fila de mapeo en REQUIREMENTS.md (`AGENT (modelo) | AGENT-01..06, 08 · POL-07 | Phase 7`) coincide exactamente con los `requirements:` declarados en los 5 PLAN.md.

### Anti-Patterns Found

Ninguno. Escaneo de `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER|placeholder|coming soon|not yet implemented` sobre los 8 archivos de producción de la fase (`configured_agent.py`, `registry.py`, `scoped_retrieval.py`, `permission_store.py`, `memory.py`, `agents/__init__.py`, `core/ports/execution.py`, `core/ports/agent.py`) → cero coincidencias.

El parser de planes en `_parse_plan` (configured_agent.py:138-161) está documentado explícitamente como "parser mínimo v0.1; el parser robusto queda para Fase 8" — esto es una limitación de alcance declarada en el propio PLAN.md (07-04, Task 2: "v0.1 del parser: parseo minimo determinista... documentar que el parser robusto es trabajo de Fase 8"), no una omisión oculta. No constituye stub porque el ciclo completo (retrieval→prompt→gateway→evaluate→run) está implementado; solo la sofisticación del parseo de texto a `Plan` está deliberadamente acotada y trazada a la fase siguiente.

### Human Verification Required

Ninguno. Toda la fase es maquinaria de backend verificable mediante tests automatizados, AST gates, mypy, ruff y lint-imports. No hay UI, comportamiento en tiempo real, ni integración con servicio externo que requiera testing manual.

### Comandos ejecutados (evidencia directa, no SUMMARY)

```
cd /mnt/hdd/Data/10_Workspace/projects/wyss
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q
  → 399 passed, 6 skipped in 2.63s

UV_CACHE_DIR=/tmp/uv-cache uv run mypy src tests
  → Success: no issues found in 174 source files

UV_CACHE_DIR=/tmp/uv-cache uv run ruff check src tests
  → All checks passed!

UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports
  → core es puro: stdlib only KEPT
  → las capas importan de core, nunca entre sí KEPT
  → Contracts: 2 kept, 0 broken.
```

### Gaps Summary

Ningún gap encontrado. Los 10 truths derivados de ROADMAP Success Criteria + PLAN must_haves verifican VERIFIED contra código real (no contra afirmaciones de SUMMARY.md). El conteo de tests (399 passed/6 skipped) coincide exactamente con el baseline esperado declarado en 07-VALIDATION.md y 07-05-PLAN.md. mypy strict, ruff y lint-imports están limpios. El único punto de alcance acotado (parser de plan v0.1) está documentado explícitamente en el PLAN.md como deferred a Fase 8 — no es un gap, es scope declarado.

---

_Verified: 2026-06-16_
_Verifier: Claude (gsd-verifier)_
