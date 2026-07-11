---
phase: 11-owner-memory
plan: 02
status: complete
completed: 2026-07-10
requirements: [MEM-01, MEM-03]
builder: codex (codex-gsd-exec) — verificado y commiteado por Claude
---

# 11-02 Summary — MemoryTool + política

## Qué se hizo

- `src/memory/tool.py`: `MemoryTool` (protocol Tool, espejo estructural de NotionTool) para `memory.remember` — **tier="owner" HARDCODEADO** (grep de lectura de tier = 0; test explícito: parameters con tier="external" igual persiste "owner" — MEM-03 imposible de violar). value trimmeado, vacío rechaza legible; auditoría ACTION_COMPLETED; errores como ToolResult.
- `_BASE_LEVELS["memory.remember"] = RiskLevel.B` + réplica idéntica en los 5 conftests espejo (1 entrada exacta por archivo, verificado).
- `tests/policy/test_engine.py` nuevo: memory.remember → B/CONFIRM_SIMPLE; memory.* desconocido → C fail-closed.

## Verificación (fuera del sandbox)

**616 passed** (+9) / mypy 0 / ruff 0 / import-linter 2/2.

## Deviations

`memory.forget` NO es write action gateada — el plan solo gatea remember; forget va como RPC directo del daemon en 11-04 (gestión del owner por socket, precedente routine.delete).
