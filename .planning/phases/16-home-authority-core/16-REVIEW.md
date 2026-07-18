---
phase: 16-home-authority-core
reviewed: 2026-07-18T00:00:00-03:00
depth: deep
files_reviewed: 12
files_reviewed_list:
  - src/adapters/sqlite_idempotency.py
  - src/bootstrap/cli.py
  - src/core/domain/home.py
  - src/core/domain/__init__.py
  - src/core/ports/home.py
  - src/core/ports/__init__.py
  - src/orchestrator/daemon.py
  - src/orchestrator/pending_store.py
  - tests/orchestrator/test_daemon.py
  - tests/orchestrator/test_daemon_execution.py
  - tests/orchestrator/test_idempotency_store.py
  - tests/orchestrator/test_pending_store.py
findings:
  critical: 1
  warning: 8
  info: 3
  total: 12
status: issues_found
---

# Phase 16: Code Review Report

## Resumen

Yo revisé el límite Home a profundidad, siguiendo los call chains hasta `PlanExecutor`,
`FileSystemAdapter`, `ShellAdapter`, `GitAdapter`, `dispatch` y `SqliteAuditLogger` cuando era
necesario para validar las garantías declaradas. El corte mejora de forma real el baseline:
persiste el claim antes de procesar, hace replay durable, rechaza payloads conflictivos, conserva
B/C, exige `CONFIRMAR` para C, reevalúa la política y usa un `UPDATE ... WHERE status='pending'`
para que una sola respuesta resuelva el plan.

El merge todavía no es seguro. La segunda muralla sólo existe para filesystem; Git y cualquier
shell habilitado llegan al I/O sin una reevaluación determinista en el adapter. Además, el nuevo
store crea en `0644` una base que puede contener instrucciones y outputs, y el socket que se
presenta como límite Home también expone operaciones administrativas y auditoría sin separar la
capacidad del proceso Edge.

Verificación ejecutada durante esta revisión:

```text
uv run pytest -q tests/orchestrator/test_daemon.py \
  tests/orchestrator/test_daemon_execution.py \
  tests/orchestrator/test_idempotency_store.py \
  tests/orchestrator/test_pending_store.py
42 passed in 0.45s
```

## Critical Issues

### CR-01: Git y shell carecen de segunda muralla inmediatamente antes del I/O

**Archivos:** `src/orchestrator/daemon.py:523-527`, `src/bootstrap/cli.py:492-496`

**Problema:** `_confirm_pending()` reevalúa el plan antes de resolver el pending, pero después
`_execute_plan()` entrega el plan al runner sin una guarda de política común. El adapter de
filesystem sí vuelve a resolver paths y ejecutar `engine.evaluate()` dentro de `execute()`, justo
antes del I/O. `GitAdapter` y `ShellAdapter` sólo aplican allowlists; no vuelven a ejecutar la
política determinista. En producción shell está cerrado por una allowlist vacía, pero Git permite
por defecto `add` y `commit`; ambos clasifican C por fail-closed y, una vez confirmados, llegan a
`create_subprocess_exec()` sin la segunda muralla requerida. Si luego se habilita un binario shell,
aparece el mismo hueco.

Esto incumple la garantía estructural «la segunda muralla se ejecuta inmediatamente antes del I/O
real». La reevaluación de confirmación no la reemplaza: puede haber varios pasos y awaits antes de
un paso posterior, y una allowlist responde una pregunta distinta a la política A-D.

**Corrección:** introducir un port/guard de autorización de ejecución reutilizable e inyectarlo en
todos los adapters con I/O. Cada `execute()` debe reconstruir el plan/acción efectivo, normalizar
los datos relevantes y reevaluar inmediatamente antes de spawn/mutación. El adapter debe bloquear
D/REJECT y cualquier nivel por encima de `max_risk`, auditar el bloqueo y tener contract tests para
filesystem, Git y shell. No alcanza con agregar otra evaluación en `DaemonServer`.

## Warnings

### WR-01: Una composición sin runner confirma y publica `verified` aunque no ejecutó nada

**Archivo:** `src/orchestrator/daemon.py:513-521`, `src/orchestrator/daemon.py:915-927`

`runner` es opcional en `DaemonServer`, `start_daemon` y `run_daemon`. Cuando falta, el código
resuelve durablemente el pending como `confirmed`, devuelve `accepted=True` y fabrica un
`execution_id`. El mapper Home interpreta ausencia de `success=False` como `status="verified"`.
El test `test_without_runner_keeps_legacy_shape` fija explícitamente este comportamiento. Una mala
composición o un test adapter puede, por tanto, decirle a todos los clientes que una acción B/C
quedó verificada sin I/O ni verificación.

**Corrección:** para los métodos Home, exigir `PlanRunner` en construcción o fallar cerrado antes
de resolver el pending. Si se conserva compatibilidad legacy para `confirm`, su resultado debe ser
`accepted`/`authorized` pero nunca `verified`; sólo una ejecución con evidencia puede producir ese
estado.

### WR-02: `client_requests.db` nace con permisos `0644` y puede guardar datos sensibles

**Archivo:** `src/adapters/sqlite_idempotency.py:37-40`

El adapter deja que `sqlite3.connect()` cree el archivo bajo el umask normal. Lo comprobé en esta
máquina: el modo resultante es `0o644`. Las respuestas idempotentes pueden contener texto de
instrucciones, pending IDs y outputs visibles de herramientas. Esto contradice los permisos
mínimos del sistema y es más débil que los helpers existentes de `gateway/db.py` y
`knowledge/db.py`, que precrean con `os.open(..., 0o600)` para evitar incluso la ventana temporal.

**Corrección:** reutilizar el patrón seguro de precreación `0600`, validar/corregir el modo de un
archivo existente y probarlo. Considerar también `-wal`/`-shm` y exigir un directorio privado.

### WR-03: El socket Home comparte toda la autoridad administrativa y confía en `source`

**Archivo:** `src/orchestrator/daemon.py:104-121`, `src/orchestrator/daemon.py:220-240`

El mismo socket `0600` que consumirá Home Edge registra `home.*`, pero también `ask`, `confirm`,
`audit` (incluyendo payload opt-in), administración de rutinas, edición/borrado de memoria y digest.
No hay una capacidad por método ni una identidad de peer; `source` es texto elegido por el caller y
también forma la clave idempotente y el actor de auditoría. Un Edge comprometido bajo el mismo UID
puede invocar métodos fuera del contrato Home, leer historia de auditoría o hacerse pasar por otro
cliente. El modo `0600` autentica al usuario Unix, no al proceso ni al dispositivo.

**Corrección:** exponer un socket/adapter Home dedicado con allowlist cerrada de métodos, derivar la
identidad del peer autenticado y no del payload, y mantener las operaciones owner/admin en otro
límite. Hasta que exista esa separación, no documentar este socket como capacidad estable de Edge.

### WR-04: Un plan que reevalúa a D no queda terminalmente rechazado

**Archivo:** `src/orchestrator/daemon.py:458-472`

Cuando la reevaluación produce D/REJECT, `dispatch()` audita el rechazo pero el pending original
permanece `status='pending'`. El test sólo comprueba que esa llamada no ejecuta; no verifica el
estado terminal. Se puede volver a responder hasta el TTL y, si reglas/config cambian después, una
reevaluación posterior podría degradar el resultado y confirmar el mismo plan. D debe ser absoluto,
no una respuesta transitoria.

**Corrección:** resolver atómicamente el pending como `rejected` por política antes de responder y
probar que respuestas posteriores producen `already_resolved`, aun si un engine posterior devuelve
un nivel inferior.

### WR-05: El TTL no forma parte del `UPDATE` atómico de resolución

**Archivo:** `src/orchestrator/pending_store.py:146-162`

El daemon hace un check previo con `_is_expired()`, pero `PendingStore.resolve()` sólo condiciona
por `status='pending'`. El invariante «no confirmar vencidos» no vive en la transacción que decide al
ganador. Hoy el event loop único reduce la ventana, pero otro proceso ya abre la misma DB para las
vistas/CLI y el método público permite confirmar directamente una fila cuyo timestamp venció si el
reaper aún no la marcó.

**Corrección:** incluir `expires_at >= now` en el `UPDATE`, dentro de `BEGIN IMMEDIATE` si se
necesita distinguir `expired` de `already_resolved`, y agregar una prueba que llame `resolve()` sobre
una fila vencida sin ejecutar antes `expire_old()`.

### WR-06: El store idempotente puede crecer sin límite durante la vida del daemon

**Archivo:** `src/adapters/sqlite_idempotency.py:52-53`, `src/adapters/sqlite_idempotency.py:99-107`

Los completados se podan sólo una vez, al construir el adapter. Los `in_progress` se conservan para
cerrar en ambiguo, pero tampoco tienen estado de revisión/reconciliación ni cuota. Un proceso local
que envíe IDs únicos puede amplificar cada request a una fila y cada respuesta a JSON durable hasta
llenar disco. La validación de longitud no limita cantidad o tasa.

**Corrección:** mantenimiento periódico acotado, límites/cuotas observables y rate limiting en el
adapter Home. Los claims ambiguos no deben borrarse automáticamente: necesitan un estado y flujo de
reconciliación explícitos para preservar fail-closed.

### WR-07: La CLI no puede completar una escalada B→C detectada al confirmar

**Archivo:** `src/bootstrap/cli.py:655-676`

La CLI elige `s` o `CONFIRMAR` usando el nivel guardado antes de llamar al daemon. Si el pending
guardado era B y la reevaluación actual sube a C, el servidor rechaza correctamente `s`, pero repetir
`wyss confirm` vuelve a leer B y vuelve a enviar `s`. El test de escalada llama el RPC directamente y
no cubre el cliente operativo.

**Corrección:** hacer que el daemon devuelva el nivel fresco requerido sin resolver y que la CLI
vuelva a presentar el gate fuerte, o separar preview de confirmación conservando la decisión final
exclusivamente en Wyss.

### WR-08: `expected_revision` está cableado a 1 y no protege una revisión real

**Archivo:** `src/orchestrator/daemon.py:278-315`

Se valida el entero, pero luego cualquier valor distinto de 1 es conflicto y el pending no almacena
revisión. Esto da apariencia de optimistic concurrency sin comparar contra una fuente de verdad.
Cuando el agregado avance a revisión 2, ninguna respuesta será válida; mientras tanto no detecta un
cliente que contestó sobre una representación diferente con la misma constante.

**Corrección:** persistir una revisión monotónica por plan/agregado y comparar el expected contra la
revisión actual en la misma transacción de resolución. Incluir la revisión real en `plan.proposed` y
en `already_resolved`.

## Info

### IF-01: La idempotencia de intención cubre replay/conflicto, pero falta el crash test de proceso

Los tests prueban cerrar/reabrir después de `complete()` y repetir un claim `in_progress` en la misma
instancia. No matan/reabren entre `claim()` y `complete()`, que es exactamente la evidencia de crash
safety declarada. El diseño autocommit + `synchronous=FULL` parece correcto; agregaría ese test y un
test con dos conexiones para fijarlo.

### IF-02: Los tests de «carrera» actuales son secuenciales

`test_double_resolve_is_atomic` y `test_home_intent_is_idempotent...` hacen dos llamadas una detrás
de otra. No ejercitan dos conexiones SQLite, `asyncio.gather`, approve-vs-reject ni confirmación-vs-
TTL. El SQL de resolución es razonable, pero la condición multicliente exigida necesita pruebas
concurrentes reales y verificación de una sola auditoría/ejecución.

### IF-03: Los ports Home están bien ubicados, pero todavía no gobiernan el caso de uso

Los protocolos y DTO viven en `core` sin frameworks, lo cual respeta port-before-adapter. Sin
embargo, salvo `IdempotencyPort`, los nuevos ports no tienen consumidores y toda la aplicación Home
(validación de transporte, política, resolución y shape JSON) vive dentro de `DaemonServer`. Conviene
extraer un servicio de aplicación que dependa de los ports; JSON-RPC debería limitarse a decodificar,
invocar el caso de uso y codificar. Eso permitirá reutilizar la misma autoridad desde web/Android/
Edge sin duplicar reglas.

## Veredicto

**Bloqueado para merge** hasta corregir CR-01. Recomiendo corregir también WR-01 a WR-05 en este
corte porque afectan directamente autoridad, veracidad, confidencialidad y resolución segura. Los
límites de crecimiento, revisiones y extracción hexagonal pueden dividirse en commits pequeños,
pero deben quedar cerrados antes de conectar Home Edge como servicio persistente.
