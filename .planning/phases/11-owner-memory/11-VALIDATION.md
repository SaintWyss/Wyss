---
phase: 11
slug: owner-memory
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-10
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (asyncio strict); molde SQLite de tests/orchestrator/test_routine_store.py |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/memory tests/policy tests/orchestrator tests/execution -q` |
| **Full suite command** | `uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports` |
| **Estimated runtime** | ~20 s (quick) / ~70 s (full) |
| **Baseline previa** | 596 passed, 0 failed, 6 skipped (2026-07-10) |

---

## Sampling Rate

- **After every task commit:** Run quick command
- **After every plan wave:** Run full suite command
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 70 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01-T1 | 01 | 1 | MEM-03 | T-11-05 | MemoryFact frozen + MemoryPort/MemoryAdmin; docstring ports actualizado | unit | `uv run python -c "from core.domain.memory import MemoryFact; from core.ports.memory import MemoryPort, MemoryAdmin"` + `uv run mypy src/core/domain/memory.py src/core/ports/memory.py` | ❌→Wave0 | ⬜ pending |
| 11-01-T2 | 01 | 1 | MEM-01, MEM-03 | T-11-05, T-11-DUR, T-11-SC | SQLite WAL molde routine_store; queries parametrizadas; memory/ independiente | unit | `uv run pytest tests/memory/test_store.py -x -q && uv run lint-imports && uv run mypy src/memory` | ❌→Wave0 | ⬜ pending |
| 11-02-T1 | 02 | 2 | MEM-01, MEM-03 | T-11-02, T-11-V5 | tier hardcodeado owner (nunca lee parameters.tier); value vacío rechazado; error→ToolResult | unit | `uv run pytest tests/memory/test_tool.py -x -q && uv run mypy src/memory && uv run lint-imports` | ❌→Wave0 | ⬜ pending |
| 11-02-T2 | 02 | 2 | MEM-01 | T-11-01w, T-11-P1 | memory.remember→B/CONFIRM_SIMPLE (no C); 5 conftests espejo sincronizados | unit | `uv run pytest tests/policy/test_engine.py -x -q && uv run pytest tests/policy tests/agents tests/execution tests/orchestrator tests/security -q -k "memory or engine"` | ✅ (extiende) | ⬜ pending |
| 11-03-T1 | 03 | 2 | MEM-04, MEM-01 | T-11-01r, T-11-04 | _format_memory_safe capado; memory.remember en _ACTION_TYPES; orchestrator↛memory | unit | `uv run pytest tests/orchestrator/test_llm_orchestrator.py -x -q && uv run mypy src/orchestrator/llm_orchestrator.py && uv run lint-imports` | ✅ (extiende) | ⬜ pending |
| 11-03-T2 | 03 | 2 | MEM-04 | T-11-01r, T-11-03 | fact malicioso solo dentro del bloque envuelto; Plan inalterado por memoria | unit | `uv run pytest tests/orchestrator/test_llm_orchestrator.py -x -q -k "memory or injection"` | ✅ (extiende) | ⬜ pending |
| 11-04-T1 | 04 | 2 | MEM-01 | T-11-07, T-11-08 | 5ta rama memory en _adapter_for; fallo legible sin tool; execution↛memory | unit | `uv run pytest tests/execution/test_executor.py -x -q -k memory && uv run lint-imports && uv run mypy src/execution/executor.py` | ✅ (extiende) | ⬜ pending |
| 11-04-T2 | 04 | 2 | MEM-02 | T-11-06, T-11-08 | RPC memory.list/edit/forget directo (sin evaluate); legible; daemon↛memory (MemoryAdmin) | unit | `uv run pytest tests/orchestrator/test_daemon.py tests/orchestrator/test_daemon_execution.py -x -q && uv run mypy src/orchestrator/daemon.py && uv run lint-imports` | ❌→Wave0 (RPC memory) | ⬜ pending |
| 11-05-T1 | 05 | 3 | MEM-01, MEM-02 | T-11-09, T-11-10 | MemoryStore always-on (sin token-gate) inyectado a 3 vistas; tabla legible no-blob | unit | `uv run pytest tests/bootstrap/test_cli.py -x -q -k memory && uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports` | ❌→Wave0 (memory CLI) | ⬜ pending |
| 11-05-T2 | 05 | 3 | MEM-01, MEM-02 | T-11-09 | round-trip real: recorda→bandeja B→confirmar→persiste→prompt como dato→list/rm | manual | checkpoint human-verify (daemon LLM, owner) | n/a | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `tests/memory/__init__.py` + `tests/memory/conftest.py` — nuevo package; fixture `memory_store` sobre `tmp_path` + `from tests.ports.fakes import FakeAuditPort` — plan 01 T2
- [ ] `tests/memory/test_store.py` — WAL/pragma/rowcount/round-trip, molde tests/orchestrator/test_routine_store.py — plan 01 T2
- [ ] `tests/memory/test_tool.py` — execute/verify + tier-hardcode (MEM-03) + empty-value reject — plan 02 T1
- [ ] Policy: `memory.remember: RiskLevel.B` en los 5 conftests espejo (agents/execution/orchestrator/security/policy) + test engine B/CONFIRM_SIMPLE — plan 02 T2
- [ ] Test anti-injection MEM-04 en tests/orchestrator/test_llm_orchestrator.py (FakeMemoryPort con fact imperativo) — plan 03 T2
- [ ] Tests RPC memory.list/edit/forget en tests/orchestrator/test_daemon.py + actualizar 4 constructores DaemonServer (Pitfall 5) — plan 04 T2
- [ ] Tests CLI `wyss memory list/edit/rm` en tests/bootstrap/test_cli.py (tabla legible, no JSON) — plan 05 T1
- [ ] `core/ports/__init__.py`: exportar MemoryPort/MemoryAdmin en `__all__` + actualizar conteo docstring (Pitfall 3) — plan 01 T1
- [ ] CERO paquetes nuevos: stdlib `sqlite3` (no slopcheck) — registro `memory/` en pyproject es config, no dependencia

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Round-trip real memoria (recorda→bandeja B→confirmar→persiste→prompt como dato→list/rm) | MEM-01, MEM-02, MEM-04 | Requiere daemon LLM real (qwen/LiteLLM) + juicio del owner sobre que el fact no actuó como instrucción | Ver 11-05 Task 2 `<how-to-verify>` (5 pasos) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (11-05-T2 manual por diseño: round-trip real LLM)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 70s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned
