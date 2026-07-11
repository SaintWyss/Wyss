---
phase: 11-owner-memory
plan: 04
status: complete
completed: 2026-07-10
requirements: [MEM-01, MEM-02]
builder: codex (codex-gsd-exec) — verificado y commiteado por Claude
---

# 11-04 Summary — Cableado: executor + daemon + composition root + CLI (incluye 11-05 T1)

## Qué se hizo

- **Executor**: 5ta rama `memory` (kwarg `memory: Tool | None` por protocol — execution jamás importa src/memory; `_UnavailableTool` legible sin configurar).
- **Daemon**: RPCs `memory.list/edit/forget` espejo routine.* (`memory_store: MemoryAdmin` por port; list serializa MemoryFact legible con tier; edit/forget {"ok": bool} por rowcount). Propagado por start_daemon/run_daemon.
- **Composition root** (11-05 T1 adelantada): `MemoryStore(data_dir/"memory.db")` always-on → MemoryTool al executor + `memory=` al LLMOrchestrator (recall del planner) + run_daemon; close en finally.
- **CLI**: sub-app `wyss memory list/edit/rm` thin RPC (tabla Rich con tier, empty-state, panel accionable con daemon caído; jamás abre memory.db).
- Tests: daemon round-trip, executor dispatch/fallo legible, CLI (4).

## Verificación (fuera del sandbox)

**626 passed** (+7) / mypy 0 / ruff 0 / import-linter 2/2.

## Deviations

11-05 Task 1 (composition root + CLI) ejecutada junto a 11-04 en la misma pasada (mismo cableado, archivos disjuntos de lo pendiente). 11-05 Task 2 = checkpoint owner, pendiente.
