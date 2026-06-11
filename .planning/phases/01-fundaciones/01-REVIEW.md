---
phase: 01-fundaciones
reviewed: 2026-06-11T13:42:23Z
depth: standard
files_reviewed: 40
files_reviewed_list:
  - config/config.example.toml
  - src/audit/__init__.py
  - src/audit/schema.py
  - src/audit/sqlite_logger.py
  - src/bootstrap/__init__.py
  - src/core/domain/__init__.py
  - src/core/domain/agent.py
  - src/core/domain/audit.py
  - src/core/domain/config.py
  - src/core/domain/errors.py
  - src/core/domain/execution.py
  - src/core/domain/gateway.py
  - src/core/domain/knowledge.py
  - src/core/domain/plan.py
  - src/core/domain/policy.py
  - src/core/domain/risk.py
  - src/core/domain/security.py
  - src/core/domain/task.py
  - src/core/policy/__init__.py
  - src/core/ports/__init__.py
  - src/core/ports/agent.py
  - src/core/ports/audit.py
  - src/core/ports/config.py
  - src/core/ports/execution.py
  - src/core/ports/gateway.py
  - src/core/ports/knowledge.py
  - src/core/ports/persistence.py
  - src/core/ports/security.py
  - tests/__init__.py
  - tests/audit/__init__.py
  - tests/audit/conftest.py
  - tests/audit/test_sqlite_logger.py
  - tests/conftest.py
  - tests/domain/__init__.py
  - tests/domain/test_entities.py
  - tests/ports/__init__.py
  - tests/ports/fakes.py
  - tests/ports/test_agent_base.py
  - tests/ports/test_conformance.py
  - tests/test_smoke.py
findings:
  critical: 1
  warning: 6
  info: 7
  total: 14
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-06-11T13:42:23Z
**Depth:** standard
**Files Reviewed:** 40
**Status:** issues_found

## Summary

Revisión adversarial de la Fase 1 (fundaciones): vocabulario de dominio frozen, 14 ports, AgentBase con template method y SqliteAuditLogger append-only. Los tres invariantes pedidos se verificaron contra el código real:

- **core stdlib-only**: CUMPLE. `grep` de `pydantic` sobre `src/` no encuentra imports; `core/` solo importa stdlib y módulos hermanos. El contrato de import-linter en `pyproject.toml` refuerza esto estáticamente.
- **AgentBase rechaza nivel D sin invocar `_run()`**: CUMPLE en el happy path tipado, pero la comparación usa identidad (`is`) en lugar de orden/igualdad, lo que debilita exactamente la garantía "belt-and-suspenders" que ese check existe para dar (CR-01).
- **SqliteAuditLogger append-only + WAL fail-fast**: CUMPLE en lo estructural (triggers UPDATE/DELETE, verificación de `journal_mode`), con tres debilidades: detección de WAL acoplada a un string literal cuyo test no ejercita el path real (WR-04), fuga de conexión si `apply_schema` falla (WR-03) y `log()` puede crashear con payloads type-correct pero no serializables a JSON (WR-02).

Preocupación transversal principal: la inmutabilidad del dominio es de nivel de tipos, no de runtime — los campos `Mapping` están respaldados por `dict` mutables, lo que abre una ventana TOCTOU entre la evaluación de política y la ejecución (WR-01).

## Critical Issues

### CR-01: El rechazo de nivel D usa comparación por identidad (`is`) — la última línea de defensa falla ante valores no-enum

**File:** `src/core/ports/agent.py:58`
**Issue:** El check estructural es:

```python
if decision.outcome is Outcome.REJECT or decision.risk_level is RiskLevel.D:
```

`is` solo es verdadero para el singleton del enum. Una `PolicyDecision` construida con `risk_level=4` (int crudo) y `outcome=1` pasa el check y `_run()` SE EJECUTA — `4 == RiskLevel.D` es `True` pero `4 is RiskLevel.D` es `False`. `PolicyDecision` es un dataclass frozen **sin validación en runtime**, así que nada impide construirla con ints. El propósito declarado de este check es "belt-and-suspenders, T1, POL-03": defender contra bugs de los componentes upstream. El escenario realista llega con el daemon IPC JSON-RPC (planeado en el stack): decisiones deserializadas de JSON traen ints nativos, y un olvido de reconstruir `RiskLevel(...)` en la frontera convierte este check en un no-op silencioso. mypy strict mitiga en código propio, pero el check existe precisamente para los casos que mypy no cubre. Bajo la constraint del proyecto "Nivel D es absoluto y no tiene excepciones en ningún path de código", una guarda que depende de identidad de objetos no es estructural.
**Fix:**
```python
# Comparación por valor/orden + fail-closed ante tipos corruptos:
risk = decision.risk_level
outcome = decision.outcome
if (
    not isinstance(risk, RiskLevel)
    or not isinstance(outcome, Outcome)
    or outcome == Outcome.REJECT
    or risk >= RiskLevel.D
):
    self._audit.log(...)  # incluir también decision.reasons en el payload
    raise PolicyViolation(...)
```
Agregar un test que construya `PolicyDecision(task_id="t", risk_level=4, outcome=3)` (con `type: ignore`) y asserte que `_run()` no se invoca.

## Warnings

### WR-01: Inmutabilidad solo a nivel de tipos — `Action.parameters` es un `dict` mutable detrás de un frozen dataclass (TOCTOU política→ejecución)

**File:** `src/core/domain/plan.py:20` (también `src/core/domain/policy.py:32,51` y `src/core/domain/audit.py:52`)
**Issue:** `Plan` se documenta como "frozen, sin mutación post-evaluación" y el test `test_plan_is_frozen` afirma "T-1-T: tampering imposible". Eso es falso en runtime: `frozen=True` impide rebindear atributos, pero `Action.parameters` (y `PolicyRules.base_levels`, `DenyRule.params_equal`, `AuditEvent.payload`) son `Mapping` respaldados por `dict`. En runtime, `plan.steps[0].parameters["recursive"] = True` funciona — y puede ocurrir DESPUÉS de que la política evaluó el plan y ANTES de que la Tool lo ejecute. La política podría clasificar B un `file.delete` no recursivo y el ejecutor recibir uno recursivo. mypy strict rechaza la asignación en código tipado, pero el invariante de seguridad no puede depender solo del type checker (mismo razonamiento que CR-01).
**Fix:** Envolver en la construcción con `types.MappingProxyType`, p.ej. vía `__post_init__`:
```python
def __post_init__(self) -> None:
    object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))
```
(con `slots=True` y frozen, `object.__setattr__` funciona porque el slot existe). Alternativa mínima: documentar explícitamente que la inmutabilidad de los Mappings es type-level y agregar un test que lo haga visible.

### WR-02: `SqliteAuditLogger.log()` crashea con payloads type-correct no serializables a JSON

**File:** `src/audit/sqlite_logger.py:75`
**Issue:** `json.dumps(dict(event.payload))` sin `default=`. El contrato de dominio es `payload: Mapping[str, object]` — pasar `{"path": Path(...)}` o `{"at": datetime(...)}` es válido para mypy pero `log()` lanza `TypeError` en runtime. Consecuencias: (a) una operación exitosa se convierte en crash solo por auditarla; (b) si ocurre dentro de `_span_impl` en el handler de excepción (línea 103), el `TypeError` encadena sobre la excepción original y el SPAN_FAILED se pierde — exactamente el evento que más importa registrar.
**Fix:**
```python
json.dumps(dict(event.payload), default=repr)
```
o restringir el tipo del payload a valores JSON-safe en el dominio. Agregar test con un payload que contenga `Path`.

### WR-03: Fuga de conexión en `__init__` si `apply_schema` falla

**File:** `src/audit/sqlite_logger.py:44-58`
**Issue:** El path de fallo de WAL cierra la conexión (línea 51), pero si `apply_schema(self._conn)` lanza (disco lleno, DB corrupta, lock prolongado), la excepción propaga con la conexión abierta y nadie tiene referencia al objeto para cerrarla. Sobre WAL esto deja sidecars `-wal`/`-shm` colgados hasta GC.
**Fix:**
```python
try:
    ...verificación WAL...
    apply_schema(self._conn)
except Exception:
    self._conn.close()
    raise
```
(conservando el mensaje específico de `AuditIntegrityError` para el caso WAL).

### WR-04: El test de fail-fast WAL no ejercita el path real de detección; la detección está acoplada a un string literal

**File:** `tests/audit/test_sqlite_logger.py:205-215` y `src/audit/sqlite_logger.py:46-49`
**Issue:** La detección depende de `pragma.endswith("WAL")` contra el literal de `PRAGMAS`. El test monkeypatchea `PRAGMAS = ("PRAGMA journal_mode=DELETE",)`: como ese string no termina en `"WAL"`, `journal_mode` queda `None` y el constructor raisea — pero por el branch "nunca leí el pragma", NO por el branch real de NTFS donde el pragma WAL retorna `("delete",)` y `journal_mode == "delete"`. El path de producción que motiva el fail-fast (Pitfall 6) no tiene cobertura sin `WYSS_TEST_NTFS=1`. Además, cambiar la capitalización del literal (p.ej. `journal_mode=wal`) rompe la detección silenciosamente (falla cerrado, pero por la razón equivocada y con mensaje engañoso `retornó None`).
**Fix:** Separar la verificación del loop de PRAGMAs:
```python
for pragma in PRAGMAS:
    self._conn.execute(pragma)
row = self._conn.execute("PRAGMA journal_mode").fetchone()
if row is None or str(row[0]).lower() != "wal":
    ...
```
y en el test, mockear para que el pragma retorne `("delete",)` (p.ej. patcheando `sqlite3.connect` o usando una DB con `journal_mode=delete` forzado), de modo que se ejercite el branch `journal_mode == "delete"`.

### WR-05: `AgentBase.execute()` ejecuta planes con outcome CONFIRM_SIMPLE/CONFIRM_STRONG sin ninguna evidencia de confirmación

**File:** `src/core/ports/agent.py:49-87`
**Issue:** El template method solo bloquea D/REJECT. Una `PolicyDecision` con `outcome=Outcome.CONFIRM_STRONG` (nivel C) cae directo al path de ejecución y `_run()` se invoca — no hay campo `confirmed` en `PolicyDecision` ni verificación de que el flujo de confirmación B/C ocurrió. Hoy el contrato implícito es "el orquestador solo llama execute() después de confirmar", pero ese contrato no es estructural: el mismo razonamiento belt-and-suspenders que justifica el check de D aplica a B/C (D-03 exige confirmación, no ejecución directa). Un bug del orquestador en Fase 5+ ejecutaría planes C sin confirmación y nada en el núcleo lo detendría.
**Fix:** Mínimo para F1: documentar la precondición en el docstring de `execute()` y auditar el outcome recibido en el evento ACTION_STARTED (payload con `outcome`/`risk_level`) para que el bypass quede al menos trazado. Estructural (recomendado para la fase que introduzca confirmación): agregar `confirmation_id: str | None` a `PolicyDecision` y rechazar en `execute()` outcomes CONFIRM_* sin confirmación asociada.

### WR-06: `DEFAULT_SENSITIVE_DIRS` no incluye el data dir de Wyss — la auto-protección (regla #6) depende de config opcional

**File:** `src/core/domain/policy.py:9-16` vs `config/config.example.toml:29-37`
**Issue:** El TOML de ejemplo incluye `"data"` en `sensitive_dirs` con el comentario "el data dir de Wyss — regla #6 (auto-protección)". Pero el default en código (`DEFAULT_SENSITIVE_DIRS`, usado por `AggregateThresholds` cuando no hay config) NO lo incluye. Si el owner corre sin config o escribe su propio `sensitive_dirs` sin copiar el ejemplo, el sistema pierde la auto-protección de su propio audit log e índices. Esto contradice el principio que el propio ejemplo enuncia tres líneas más abajo para la denylist: los invariantes viven en código, no en TOML. Además, `"data"` es un path relativo cuya semántica de matching (¿relativo a qué cwd?) queda indefinida para el engine de Fase 2.
**Fix:** Agregar el data dir a la protección en código — como `DEFAULT_SENSITIVE_DIRS` no puede conocer el `data_dir` configurado, hacer que el engine (Fase 2) inyecte siempre `settings.data_dir` resuelto a absoluto en el set de sensibles, de forma no removible por config. Documentar en el TOML que `"data"` del ejemplo es redundante/ilustrativo.

## Info

### IN-01: `except Exception` no cubre `BaseException` — interrupciones no quedan auditadas

**File:** `src/core/ports/agent.py:88` y `src/audit/sqlite_logger.py:102`
**Issue:** `KeyboardInterrupt`/`SystemExit` durante `_run()` o dentro de un span propagan sin registrar TASK_FAILED/SPAN_FAILED, dejando tareas con ACTION_STARTED/SPAN_STARTED huérfanos en el log ("nada relevante ocurre sin registro").
**Fix:** Capturar `BaseException` en ambos handlers (re-raise inmediato tras auditar) o documentar que los spans huérfanos significan interrupción.

### IN-02: Sobreafirmación del append-only: triggers no protegen contra `DROP TABLE` / `DROP TRIGGER`

**File:** `src/audit/schema.py:39-45`
**Issue:** El comentario "ni siquiera un bug puede reescribir o borrar historia" es más fuerte que la garantía real: cualquier código con la conexión puede `DROP TRIGGER audit_no_update` y luego `UPDATE`, o `DROP TABLE audit_events`. La protección real es contra UPDATE/DELETE accidentales.
**Fix:** Ajustar el comentario a la garantía real; opcionalmente abrir la conexión de lectura futura con `mode=ro` y considerar `PRAGMA schema_version` checks si se quiere detectar manipulación.

### IN-03: `sample_task()` es código muerto

**File:** `tests/ports/fakes.py:198-204`
**Issue:** `sample_task` no tiene ningún caller en `tests/` ni `src/` (verificado por grep). Arrastra los imports de `TaskStatus` que solo él usa.
**Fix:** Eliminarla, o usarla en un test de `FakeTaskRepository` (hoy `save`/`get` no se ejercitan más allá de la conformance estática).

### IN-04: Conexión SQLite sin cerrar en test de conformance

**File:** `tests/ports/test_conformance.py:50-53`
**Issue:** `SqliteAuditLogger(tmp_path / "audit.db")` se crea y nunca se cierra → `ResourceWarning` y dependencia del GC para liberar el handle.
**Fix:** `with SqliteAuditLogger(tmp_path / "audit.db") as logger: ...` (el adapter ya es context manager).

### IN-05: Conexión SQLite no es thread-safe y el port es sync en un futuro daemon asyncio

**File:** `src/audit/sqlite_logger.py:44`
**Issue:** `sqlite3.connect` default (`check_same_thread=True`) ata la conexión al hilo creador. El stack planifica daemon asyncio; si alguna vez `log()` se despacha a un executor/thread distinto, lanzará `ProgrammingError`. Hoy no hay concurrencia de hilos, así que es solo una mina futura.
**Fix:** Dejar el default (fail-fast correcto) y documentar la restricción en el docstring de la clase; decidir el modelo de threading al construir el daemon en Fase 4.

### IN-06: Referencias adelantadas a código inexistente

**File:** `src/core/policy/__init__.py:1` y `config/config.example.toml:44`
**Issue:** El docstring de `core/policy` describe un `CognitivePolicyEngine` que no existe, y el TOML referencia `core/policy/builtin_deny.py` (Final) que tampoco existe. Quien lea config o paquete hoy asume garantías ("denylist no removible") que aún no están implementadas en código.
**Fix:** Marcar ambos como "(Fase 2)" explícitamente para que la promesa tenga fecha.

### IN-07: El dominio permite datetimes naive fuera de `AuditEvent.new()`

**File:** `src/core/domain/task.py:27`, `src/core/domain/security.py:24`, `src/core/domain/audit.py:53`
**Issue:** Solo la factory `AuditEvent.new()` garantiza UTC tz-aware. `Task.created_at`, `Permission.granted_at` y un `AuditEvent` construido directo aceptan naive datetimes; mezclar naive/aware en `created_at` (TEXT ISO) rompe el orden lexicográfico del log y las comparaciones (`TypeError` al comparar naive vs aware).
**Fix:** Patrón factory `new()` también para `Task`/`Permission`, o `__post_init__` que rechace `tzinfo is None` en los frozen dataclasses con timestamps.

---

_Reviewed: 2026-06-11T13:42:23Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
