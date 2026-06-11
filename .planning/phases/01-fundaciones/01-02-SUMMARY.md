---
phase: 01-fundaciones
plan: 02
subsystem: domain
tags: [domain, ports, protocol, abc, frozen-dataclass, hexagonal, mypy-strict, conformance]

# Dependency graph
requires:
  - "01-01: proyecto uv instalable, toolchain verde (pytest+mypy strict+ruff+lint-imports), esqueleto core/domain·ports"
provides:
  - "~24 entidades de dominio frozen (stdlib only) en core/domain con __all__ público"
  - "Los 14 contratos de core/ports (13 typing.Protocol + AgentBase ABC) — interfaces primero (D-11)"
  - "RiskLevel(IntEnum) A<B<C<D + Outcome + outcome_for con match exhaustivo (POL-02/04)"
  - "AgentBase con template method: rechazo D + audit no salteables (base estructural de POL-03/D-08)"
  - "Fakes tipados de los 13 Protocols + FakeAgent — conformidad verificada por mypy strict (Pattern 5)"
affects: [01-03, 01-04, 01-05, fundaciones, domain, ports, policy, audit, gateway, knowledge, agents]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Entidades como @dataclass(frozen=True, slots=True), stdlib only (Mapping/tuple, nunca dict/list en firmas)"
    - "Ports como typing.Protocol sin @runtime_checkable; miembros read-only como @property (Pitfall 4)"
    - "AgentBase ABC con template method — la única clase base heredable del núcleo"
    - "Conformance assignments tipadas como verificación estática de Protocols (Pattern 5)"
    - "async exactamente donde cruza red/disco (embed, retrieval, model, tool.execute/verify); resto sync"

key-files:
  created:
    - src/core/domain/risk.py
    - src/core/domain/plan.py
    - src/core/domain/policy.py
    - src/core/domain/audit.py
    - src/core/domain/task.py
    - src/core/domain/knowledge.py
    - src/core/domain/gateway.py
    - src/core/domain/execution.py
    - src/core/domain/security.py
    - src/core/domain/agent.py
    - src/core/domain/config.py
    - src/core/domain/errors.py
    - src/core/ports/audit.py
    - src/core/ports/config.py
    - src/core/ports/knowledge.py
    - src/core/ports/security.py
    - src/core/ports/gateway.py
    - src/core/ports/execution.py
    - src/core/ports/persistence.py
    - src/core/ports/agent.py
    - tests/domain/__init__.py
    - tests/domain/test_entities.py
    - tests/ports/__init__.py
    - tests/ports/fakes.py
    - tests/ports/test_conformance.py
    - tests/ports/test_agent_base.py
  modified:
    - src/core/domain/__init__.py
    - src/core/ports/__init__.py

key-decisions:
  - "AgentBase vive en core/ports/agent.py (Open Question 1) — satisface '14 ports en core/ports/' y es puro"
  - "execute(plan, decision) recibe ambos: Plan es frozen y solo lleva estimated_risk; el nivel FINAL viaja en PolicyDecision"
  - "Vector como type alias (PEP 695 `type Vector = tuple[float, ...]`), no NewType — mínimo viable para los ports"
  - "Default mutable (Mapping/thresholds) vía field(default_factory=...) — instancia de dataclass como default dispara ValueError"

patterns-established:
  - "Re-export de vocabulario público con __all__ ordenado (RUF022) en core/domain y core/ports"
  - "Fakes de test respetan la firma EXACTA del Protocol — primer cliente real que detecta Pitfall 4"
  - "Tests de seguridad explícitos (D-12): test de ausencia (_run no invocado) + inspect.signature para audit obligatorio"

requirements-completed: [POL-02, AUD-01]

# Metrics
duration: ~10min
completed: 2026-06-11
---

# Phase 1 Plan 02: Vocabulario del Sistema (dominio + ports) Summary

**~24 entidades de dominio frozen (stdlib only) y los 14 contratos de `core/ports` (13 `typing.Protocol` + la ABC `AgentBase` con template method que hace el rechazo D y la auditoría no salteables), con fakes tipados que verifican la conformidad de cada port por mypy strict — interfaces primero (D-11), antes de cualquier implementación.**

## Performance

- **Duration:** ~10 min
- **Completed:** 2026-06-11
- **Tasks:** 3
- **Files modified:** 28 (26 creados, 2 modificados)

## Accomplishments
- **Dominio completo (Task 1):** `RiskLevel(IntEnum)` A<B<C<D + `Outcome` + `outcome_for` con `match`/`assert_never` (POL-02/04); `Action`/`Plan` frozen con `Mapping` params y `tuple` steps (tampering imposible post-evaluación, T-1-T); `AuditEvent.new()` con `uuid4().hex` + `datetime.now(UTC)` tz-aware (Pitfall 5, cubre D-07); `PolicyRules`/`DenyRule`/`AggregateThresholds`/`PolicyDecision`, entidades mínimas de knowledge/gateway/execution/security/agent, `WyssSettings` frozen y jerarquía `WyssError`/`PolicyViolation`/`AuditIntegrityError`.
- **14 ports (Task 2):** 13 `typing.Protocol` (sin `@runtime_checkable`) + `AgentBase(ABC)`. Miembros read-only como `@property` (Pitfall 4: `Extractor.media_types`, `ModelProvider.name`, `Tool.name`, `Tool.max_risk`). `async` exactamente donde la tabla de research lo marca. `AgentBase.execute(plan, decision)`: REJECT o nivel D → audita el rechazo y raisea `PolicyViolation` SIN llamar `_run()` (T1, belt-and-suspenders); `audit: AuditPort` obligatorio sin default (D-08).
- **Conformance + seguridad (Task 3):** 13 fakes (uno por Protocol) + `FakeAgent` que espía `_run`; 14 asignaciones tipadas `port: <Port> = Fake()` verificadas por mypy strict (Pattern 5); tests de AgentBase: `inspect.signature` confirma `audit` sin default (T4), `TypeError` al omitirlo, decisión D → `PolicyViolation` + `_run` no invocado + rechazo en `events` (T1), decisión A → `_run` corre y audita inicio/completado.

## Task Commits

Cada tarea se commiteó atómicamente:

1. **Task 1: entidades de dominio frozen + tests de inmutabilidad** - `7c7a1cc` (feat)
2. **Task 2: los 14 ports — 13 Protocols + AgentBase ABC** - `efc21f6` (feat)
3. **Task 3: conformance fakes tipados + tests de AgentBase** - `449d8ce` (test)

**Plan metadata:** (este commit — docs: complete plan)

## Files Created/Modified
- `src/core/domain/*.py` (12 módulos) - vocabulario frozen: risk, plan, policy, audit, task, knowledge, gateway, execution, security, agent, config, errors
- `src/core/domain/__init__.py` - re-export del vocabulario público con `__all__` (38 nombres, ordenado RUF022)
- `src/core/ports/*.py` (8 módulos) - audit, config, knowledge (6 ports), security, gateway (2), execution, persistence, agent (ABC)
- `src/core/ports/__init__.py` - re-export de los 14 contratos con `__all__`
- `tests/domain/test_entities.py` - inmutabilidad (FrozenInstanceError), orden total, mapeo de outcomes, audit tz-aware
- `tests/ports/fakes.py` - 13 fakes + FakeAgent (firma exacta de cada Protocol)
- `tests/ports/test_conformance.py` - 14 asignaciones tipadas (Pattern 5)
- `tests/ports/test_agent_base.py` - semántica de seguridad de AgentBase (D-08, D-12, T1, T4)

## Decisions Made
- **AgentBase en `core/ports/agent.py`** (Open Question 1 del research): satisface literalmente "14 ports en core/ports/", es puro (solo importa domain + ports hermanos) y mantiene "vecinos importan de core/ports". import-linter lo confirma verde.
- **`execute(plan, decision)` toma ambos argumentos**: el snippet de ARCHITECTURE.md usaba `plan.risk_level`, pero `Plan` es frozen y solo lleva `estimated_risk` (estimación del LLM). El nivel FINAL lo decide la política y viaja en `PolicyDecision` — por eso el template method recibe los dos. Discreción documentada, ya anticipada por el plan.
- **`Vector` como `type Vector = tuple[float, ...]`** (PEP 695): alias mínimo viable para tipar los ports de embeddings/índices; expandible en Fase 3.
- **Defaults mutables vía `field(default_factory=...)`**: tanto `Mapping` params como `AggregateThresholds` en `PolicyRules.thresholds` — pasar una instancia de dataclass como default literal dispara `ValueError` de mutable default.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Lint cleanup] `datetime.UTC` en lugar de `timezone.utc`**
- **Found during:** Tasks 1 y 3
- **Issue:** ruff `UP017` exige el alias moderno `datetime.UTC` (Python 3.11+) sobre `timezone.utc`.
- **Fix:** `uv run ruff check --fix` aplicó la conversión en `audit.py`, `test_entities.py` y `fakes.py`. Semánticamente idénticos (`UTC is timezone.utc`).
- **Files modified:** src/core/domain/audit.py, tests/domain/test_entities.py, tests/ports/fakes.py
- **Committed in:** `7c7a1cc`, `449d8ce`

**2. [Rule 1 - Lint cleanup] `__all__` sin ordenar / imports / import sin usar**
- **Found during:** Tasks 1-3
- **Issue:** RUF022 (`__all__` no ordenado), I001 (import block) y F401 (`dataclasses.field` sin usar en audit tras refactor del factory).
- **Fix:** `uv run ruff check --fix` (+ `--unsafe-fixes` solo para el sort cosmético de `__all__`). Sin cambio de comportamiento.
- **Files modified:** src/core/domain/__init__.py, src/core/domain/audit.py, tests/ports/*.py
- **Committed in:** `7c7a1cc`, `449d8ce`

---

**Total deviations:** 2 auto-fixed (ambos lint cleanup, cero cambio de comportamiento)
**Impact on plan:** Ninguno funcional — el plan se ejecutó tal como está escrito. Sin scope creep, sin Rule 4.

## Verification

Cadena canónica completa verde tras cada task y al cierre:

```
uv run pytest tests/domain tests/ports -x -q   →  25 passed
uv run mypy                                     →  Success: no issues found in 40 source files
uv run ruff check src tests                     →  All checks passed!
uv run lint-imports                             →  Contracts: 2 kept, 0 broken (core stdlib-only)
```

Los 14 nombres importables desde `core.ports`; `grep "import pydantic" src/core/` y `grep "runtime_checkable" src/core/ports/` sin resultados.

## Known Stubs
None. Las entidades de knowledge/gateway/execution/security/agent son **mínimas por diseño** (solo los campos que las firmas de los ports necesitan, per Open Question 2 del research) — expandirlas en Fases 2-4 es aditivo, no breaking. No son placeholders que fluyan a UI. Los fakes de `tests/ports/fakes.py` retornan valores vacíos a propósito: son test doubles, no código de producción.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- **01-03 (AuditLogger):** `AuditPort`, `AuditEvent`, `AuditEventType`, `Span` y `AuditIntegrityError` definidos — el `SqliteAuditLogger` solo debe implementar el contrato y pasar el conformance assignment.
- **01-04 (CognitivePolicyEngine):** `Plan`, `Action`, `RiskLevel`, `Outcome`, `outcome_for`, `PolicyRules`, `DenyRule`, `AggregateThresholds`, `PolicyDecision` listos — el engine es función pura `Plan -> PolicyDecision` sobre este vocabulario.
- **01-05 (config + bootstrap):** `WyssSettings` frozen es el destino de la validación Pydantic; `ConfigStore` es el contrato.
- Sin blockers.

## Threat Flags
None — esta fase no introduce superficie de red/auth/IO; es vocabulario puro y contratos. Las mitigaciones T1/T2/T4/T-1-T del threat model del plan están implementadas y testeadas.

## Self-Check: PASSED

Archivos creados verificados en disco; commits `7c7a1cc`, `efc21f6`, `449d8ce` verificados en git log.

---
*Phase: 01-fundaciones*
*Completed: 2026-06-11*
