---
phase: 01-fundaciones
plan: 03
subsystem: audit
tags: [audit, sqlite, wal, append-only, adapter, hexagonal, mypy-strict, conformance, AUD-01]

# Dependency graph
requires:
  - "01-01: proyecto uv instalable, toolchain verde, paquete src/audit con stub"
  - "01-02: AuditPort (Protocol), AuditEvent/Span/ActorType/AuditEventType (dominio), AuditIntegrityError"
provides:
  - "SqliteAuditLogger: primer adapter del sistema — AuditPort sobre sqlite3 stdlib, DB separada (D-06)"
  - "Esquema audit_events append-only estructural (triggers RAISE ABORT en UPDATE/DELETE)"
  - "Smoke test WAL fail-fast al construir → AuditIntegrityError (mitiga riesgo NTFS/fuseblk, Pitfall 6/T4)"
  - "span() con duración ms (SPAN_STARTED/COMPLETED/FAILED) inyectable por constructor (D-08)"
  - "Conformance estática del adapter real verificada por mypy strict (Pattern 5)"
affects: [01-04, 01-05, fundaciones, audit, gateway, orchestrator, agents, execution]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Adapter de port con sqlite3 stdlib (SQL directo, SQLAlchemy prohibido por STACK)"
    - "DDL como constantes en schema.py + apply_schema() idempotente (todo IF NOT EXISTS)"
    - "Append-only en dos capas: triggers en el esquema + API pública sin mutación/borrado"
    - "Fail-fast de integridad al construir (smoke test WAL) — nunca degradar silencioso un audit log"
    - "Solo placeholders ? en SQL — cero interpolación de strings (T-1-INJ)"
    - "Marker pytest opcional vía skipif por env var (WYSS_TEST_NTFS) sin alterar addopts globales"

key-files:
  created:
    - src/audit/schema.py
    - src/audit/sqlite_logger.py
    - tests/audit/__init__.py
    - tests/audit/conftest.py
    - tests/audit/test_sqlite_logger.py
  modified:
    - src/audit/__init__.py
    - tests/ports/test_conformance.py
    - pyproject.toml

key-decisions:
  - "span() usa AuditEvent.new directo (no helpers span_started/failed del esqueleto research): el dominio frozen solo expone new() — adaptación fiel sin inventar API en el dominio"
  - "commit por evento con synchronous=FULL (fsync): durabilidad no-negociable para auditoría; costo aceptable a esta escala"
  - "verificación WAL recorre PRAGMAS y captura el resultado del PRAGMA journal_mode; comparación case-insensitive contra 'wal'"
  - "test ntfs vía @pytest.mark.skipif por WYSS_TEST_NTFS!=1 (no addopts -m 'not ntfs') para no romper la corrida default global"

patterns-established:
  - "Primer adapter concreto del sistema: plantilla para gateway/knowledge/execution (port + fakes en 01-02 → adapter real + conformance aquí)"
  - "Tests de adapter leen con conexión independiente para probar persistencia real (no estado en memoria)"

requirements-completed: [AUD-01]

# Metrics
duration: ~6min
completed: 2026-06-11
---

# Phase 1 Plan 03: SqliteAuditLogger Summary

**Primer adapter del sistema: `SqliteAuditLogger` (puerto `AuditPort`) sobre una DB SQLite separada de los datos de usuario (D-06), con esquema append-only estructural (triggers `RAISE(ABORT)`), `synchronous=FULL` y smoke test WAL fail-fast al construir que convierte el riesgo NTFS/fuseblk en `AuditIntegrityError` accionable — nunca degrada silencioso un audit log.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-11
- **Completed:** 2026-06-11
- **Tasks:** 2
- **Files modified:** 8 (5 creados, 3 modificados)

## Accomplishments

- **schema.py (Task 1):** DDL `audit_events` (9 columnas, `event_id` UNIQUE, `payload` JSON), índices `idx_audit_task` + `idx_audit_type_time`, los dos triggers append-only `audit_no_update`/`audit_no_delete` con `RAISE(ABORT, 'audit log is append-only')`, PRAGMAs (`journal_mode=WAL`, `synchronous=FULL`, `busy_timeout=5000`). `apply_schema()` idempotente.
- **sqlite_logger.py (Task 1):** `SqliteAuditLogger` implementa `AuditPort` con `sqlite3` stdlib. `__init__` crea el directorio padre, ejecuta PRAGMAs y verifica que `journal_mode` retorne `"wal"` — si no, cierra y raisea `AuditIntegrityError` con path + sugerencia ext4 (Pitfall 6/T4). `log()` parametrizado (placeholders `?`, `json.dumps` del payload, ISO-8601 UTC, commit por evento). `span()` con `@contextmanager`: SPAN_STARTED al entrar, SPAN_FAILED (con `error_type` + duración) y re-raise ante excepción, SPAN_COMPLETED con duración ms. `close()` + context manager.
- **Tests (Task 2):** 9 tests — WAL activo, roundtrip D-07 (payload con los 8 campos), append-only (UPDATE/DELETE abortan + evento intacto), span feliz, span fallido (propaga + registra), correlación por task_id (verifica índice), concurrencia (2 loggers, 100 eventos sin lock), fail-fast (journal≠wal → AuditIntegrityError con path), y el test opcional `@pytest.mark.ntfs` sobre el `data/` real (skip sin `WYSS_TEST_NTFS=1`).
- **Conformance (Task 2):** asignación tipada `logger: AuditPort = SqliteAuditLogger(...)` agregada a `test_conformance.py` — mypy strict verifica el contrato del adapter real (Pattern 5). Marker `ntfs` registrado en `pyproject.toml` (sin warnings de marker desconocido).

## Task Commits

Cada tarea se commiteó atómicamente:

1. **Task 1: schema.py + SqliteAuditLogger con WAL fail-fast** - `bb9fef1` (feat)
2. **Task 2: tests del logger + conformance AuditPort** - `5356b9f` (test)

**Plan metadata:** (este commit — docs: complete plan)

## Files Created/Modified

- `src/audit/schema.py` - DDL audit_events + 2 índices + 2 triggers append-only + PRAGMAs; `apply_schema()` idempotente
- `src/audit/sqlite_logger.py` - SqliteAuditLogger (AuditPort): WAL fail-fast, log() parametrizado, span() temporizado, close/context manager
- `src/audit/__init__.py` - re-exporta `SqliteAuditLogger`
- `tests/audit/conftest.py` - fixtures `logger` (sobre tmp_path) + `make_event` (factory)
- `tests/audit/test_sqlite_logger.py` - 9 tests (8 obligatorios + 1 ntfs opcional)
- `tests/ports/test_conformance.py` - asignación tipada AuditPort = SqliteAuditLogger (Pattern 5)
- `pyproject.toml` - marker `ntfs` registrado en `[tool.pytest.ini_options]`

## Decisions Made

- **`span()` usa `AuditEvent.new` directo:** el esqueleto del research (§Code Examples) invocaba helpers `AuditEvent.span_started/span_failed/span_completed` que no existen — el dominio frozen de 01-02 solo expone la factory `new()`. Adaptación fiel: el adapter compone los eventos SPAN_* con `new()`, sin inventar API en el dominio puro. Comportamiento idéntico al esqueleto.
- **commit por evento con `synchronous=FULL`:** durabilidad no-negociable para auditoría; el fsync por commit es el costo correcto a esta escala (el daemon de Fase 5 puede envolver en `asyncio.to_thread` si hace falta).
- **Verificación WAL recorriendo PRAGMAS:** el `__init__` captura el resultado del `PRAGMA journal_mode` durante la aplicación de PRAGMAs y compara case-insensitive contra `"wal"`, cerrando la conexión antes de raisear.
- **Test ntfs vía `skipif`+env var (no `addopts -m`):** se usó `@pytest.mark.skipif(WYSS_TEST_NTFS != "1")` en lugar de `addopts = "-m 'not ntfs'"` para no alterar la selección de tests global del proyecto (el plan lo pedía explícitamente).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Lint cleanup] I001 import block + SIM117 nested with**
- **Found during:** Task 2 (verificación ruff)
- **Issue:** ruff `I001` (orden de imports en `sqlite_logger.py`: `audit.schema` debía ir antes de `core.domain` por orden alfabético de first-party) y `SIM117` (dos `with` anidados en `test_span_failure_records_and_propagates` combinables en uno).
- **Fix:** `uv run ruff check --fix src tests` aplicó ambos. Cero cambio de comportamiento (reordenamiento de imports + combinación sintáctica de context managers).
- **Files modified:** src/audit/sqlite_logger.py, tests/audit/test_sqlite_logger.py
- **Verification:** `uv run ruff check src tests` → "All checks passed!"; pytest siguió verde (23 passed).
- **Committed in:** `5356b9f` (commit de Task 2)

---

**Total deviations:** 1 auto-fixed (lint cleanup, cero cambio de comportamiento)
**Impact on plan:** Ninguno funcional — el plan se ejecutó tal como está escrito. Sin scope creep, sin Rule 4.

## Verification

Cadena canónica completa verde tras cada task y al cierre:

```
uv run pytest                                →  35 passed, 1 skipped (audit: 8 passed + 1 ntfs skipped)
uv run mypy                                  →  Success: no issues found in 45 source files
uv run ruff check src tests                  →  All checks passed!
uv run lint-imports                          →  Contracts: 2 kept, 0 broken (audit→core OK, core sin audit)
```

Smoke de construcción + escritura del logger imprimió `ok`. El marker `ntfs` no genera warnings (verificado con `-W error::pytest.PytestUnknownMarkWarning`).

## Threat Mitigations (del threat_model del plan)

- **T4 (Repudiation — WAL/NTFS):** `synchronous=FULL` + smoke test WAL fail-fast → `AuditIntegrityError`. Test 7 (`test_fail_fast_when_journal_not_wal`) lo verifica con monkeypatch del PRAGMA.
- **T4-b (Repudiation/Tampering — audit_events):** triggers `RAISE(ABORT)` en UPDATE/DELETE + API sin métodos de mutación. Test 3 (`test_append_only_update_and_delete_abort`) verifica ambos abortan y el evento persiste.
- **T-1-INJ (Tampering — SQL):** solo placeholders `?` parametrizados; cero interpolación de strings en SQL (`_INSERT` constante, `log()` pasa tupla de parámetros).
- **T5 (Information Disclosure — payload):** aceptado para v0.1 (DB local, gitignoreada, single-owner) per el threat model.

## Known Stubs

None. El `SqliteAuditLogger` está completo y funcional. El test `@pytest.mark.ntfs` no es un stub: es un test de integración opt-in deliberadamente skipped por default (corre solo con `WYSS_TEST_NTFS=1` sobre el mount real).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **01-04 (CognitivePolicyEngine):** el engine es función pura `Plan -> PolicyDecision`; el AuditLogger ya disponible para inyectar cuando el wiring lo conecte.
- **01-05 (config + bootstrap):** `audit_db` en `config.example.toml` apunta al path del logger; el composition root construirá `SqliteAuditLogger(settings.audit_db)` e inyectará el adapter a todo componente (D-08).
- Criterio de fase #4 (mitad adapter) cumplido: AuditLogger escribe eventos a SQLite separada; firma AuditPort verificada estáticamente; append-only probado; pérdida-en-crash mitigada con FULL + fail-fast WAL.
- Sin blockers.

## Threat Flags

None — el plan no introdujo superficie de red/auth nueva fuera de su threat_model. La única IO nueva (escritura a `data/audit.db`) está cubierta por T4/T4-b/T-1-INJ y mitigada/aceptada según el register.

## Self-Check: PASSED

Archivos creados verificados en disco; commits `bb9fef1`, `5356b9f` verificados en git log.

---
*Phase: 01-fundaciones*
*Completed: 2026-06-11*
