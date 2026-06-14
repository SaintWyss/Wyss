---
phase: "07"
plan: "01"
subsystem: agents
tags: [tdd, protocol, test-scaffold, wave-0, RED]
dependency_graph:
  requires: []
  provides:
    - core.ports.PlanRunner
    - tests.agents.conftest (FakeAudit, RecordingEngine, FakePlanRunner, fixtures)
    - tests.agents.* (14 tests RED, listos para waves 1-3)
    - tests.bootstrap.test_agent_config
  affects:
    - src/core/ports/execution.py
    - src/core/ports/__init__.py
    - tests/agents/ (paquete nuevo)
    - tests/bootstrap/test_agent_config.py
tech_stack:
  added: []
  patterns:
    - "Protocol PlanRunner con retorno `object` — frontera hexagonal sin importar ExecutorResult"
    - "RecordingEngine wrapping CognitivePolicyEngine — patrón espía para assertions de evaluación"
    - "FakePlanRunner con duck typing (.success/.detail) — evita levantar stack de execution/"
key_files:
  created:
    - src/core/ports/execution.py (ampliado con PlanRunner Protocol)
    - tests/agents/__init__.py
    - tests/agents/conftest.py
    - tests/agents/golden/__init__.py
    - tests/agents/golden/injection_doc.md
    - tests/agents/test_configured_agent.py
    - tests/agents/test_registry.py
    - tests/agents/test_scoped_retrieval.py
    - tests/agents/test_memory.py
    - tests/agents/test_golden_injection.py
    - tests/bootstrap/test_agent_config.py
  modified:
    - src/core/ports/__init__.py (re-exporta PlanRunner; __all__ actualizado)
decisions:
  - "PlanRunner retorna object (no ExecutorResult) — core no puede importar execution/; ConfiguredAgent usa duck typing"
  - "RecordingEngine se define en tests/agents/conftest.py (no importado de tests/execution/) — cada paquete de test es autónomo"
  - "test_golden_injection usa un plan fabricado con file.delete recursive que matchea mass-delete denylist → nivel D garantizado"
  - "3 de 14 tests pasan en Wave 0 (no dependen de impl ausente): test_definition_is_frozen, test_injection_attempt_results_in_blocked_plan, test_injection_doc_fixture_exists"
metrics:
  duration: "~20 min"
  completed: "2026-06-13"
  tasks_completed: 3
  tasks_total: 3
  files_created: 11
  files_modified: 2
---

# Phase 07 Plan 01: PlanRunner Protocol + scaffold tests/agents/ (Wave 0) Summary

**One-liner:** Protocol PlanRunner en core/ports (frontera hexagonal sin ImportError) + paquete tests/agents/ completo con 14 tests RED que cubren AGENT-01..06/08 y POL-07.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Definir Protocol PlanRunner en core/ports | 999d02c | src/core/ports/execution.py, src/core/ports/__init__.py |
| 2 | Scaffold tests/agents/ — conftest + fixtures + fixture documental | 9ba3f3e | tests/agents/__init__.py, tests/agents/conftest.py, tests/agents/golden/ |
| 3 | Escribir los tests RED de toda la fase | 816b30b | tests/agents/test_*.py (5 archivos) + tests/bootstrap/test_agent_config.py |

## What Was Built

### Task 1: PlanRunner Protocol

`src/core/ports/execution.py` ahora contiene `class PlanRunner(Protocol)` con un único método `async def run(self, plan: Plan) -> object`. El retorno es `object` deliberadamente: `ExecutorResult` vive en `execution/`, que `core` no puede importar (import-linter). `ConfiguredAgent` (waves 1-2) inspeccionará `.success`/`.detail` vía duck typing. `PlanRunner` está re-exportado en `core/ports/__init__.__all__` (posición alfabética).

Verificación: `from core.ports import PlanRunner` OK · mypy strict verde · lint-imports verde (2 contracts kept).

### Task 2: Scaffold tests/agents/

Paquete `tests/agents/` creado con:
- `conftest.py` (>100 líneas): `engine` fixture, `FakeAudit` (lista events + contextmanager), `RecordingEngine` (wraps engine real), `FakePlanRunner` (registra plan, devuelve duck-typed result), fixtures `fake_retrieval`/`fake_permission_store` importados de `tests.ports.fakes`, `sample_definition`.
- `golden/injection_doc.md`: texto de apuntes legítimos mezclado con instrucciones inyectadas explícitas (`rm -rf /`, `file.delete recursive con recursive=True to_trash=False`) que mapean a la denylist `mass-delete` (nivel D).

### Task 3: Tests RED

14 tests distribuidos en 6 archivos, todos con `pytest --co` limpio:

| Archivo | Tests | Requirements |
|---------|-------|--------------|
| test_configured_agent.py | 4 | AGENT-01, AGENT-05, AGENT-06, D-70/POL-07 |
| test_registry.py | 2 | AGENT-02, D-73 |
| test_scoped_retrieval.py | 2 | AGENT-03, AGENT-04 |
| test_memory.py | 2 | AGENT-08 |
| test_golden_injection.py | 2 | POL-07, fixture |
| test_agent_config.py | 2 | D-73 |

Estado RED: 11/14 fallan por `ModuleNotFoundError` (agents.configured_agent, agents.memory, agents.registry, agents.scoped_retrieval, AgentDefinition.agents en bootstrap). 3 tests pasan ya porque no dependen de impl ausente.

## Deviations from Plan

### Auto-fixed Issues

None - plan ejecutado exactamente como estaba escrito.

### Decisión de diseño (dentro de scope — Claude's Discretion)

**RecordingEngine redefinida en tests/agents/conftest.py (no importada de tests/execution/conftest.py)**

El plan decía importar desde el análogo; en la práctica cada paquete de test debe ser autónomo para que las waves posteriores no creen dependencias circulares de test. La clase es idéntica al análogo — no es una desviación de comportamiento, sino de organización.

## Known Stubs

Ninguno — este plan es solo scaffold de tests y un Protocol. No hay stubs de producción.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: fixture | tests/agents/golden/injection_doc.md | Fixture con instrucciones de borrado (`rm -rf /`, `file.delete recursive`) — solo para tests, no cruza a producción |

El fixture T-07-01 está en scope del plan (ver `<threat_model>`). No hay superficies de seguridad nuevas en producción.

## Self-Check: PASSED

- [x] src/core/ports/execution.py — existe y contiene `class PlanRunner`
- [x] src/core/ports/__init__.py — `PlanRunner` en `__all__`
- [x] tests/agents/conftest.py — importa limpio, >100 líneas
- [x] tests/agents/golden/injection_doc.md — existe, contiene `rm -rf`
- [x] 14 tests colectan (`pytest --co -q` sin errores)
- [x] lint-imports verde (2 contracts kept, 0 broken)
- [x] Suite existente: 379 passed / 6 skipped (sin regresión)
- [x] Commits: 999d02c, 9ba3f3e, 816b30b — verificados en git log
