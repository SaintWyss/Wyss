---
phase: 16-home-authority-core
reviewed: 2026-07-18T14:51:11-03:00
depth: deep
base_commit: 809bc98866a332146df3e5939421b5dc9968e80c
head_commit: 45c8a28d464ea3f97eafab81c378ba1fd75d4fde
workspace_fixes_reviewed: true
files_reviewed: 22
files_reviewed_list:
  - src/adapters/sqlite_idempotency.py
  - src/bootstrap/cli.py
  - src/core/domain/home.py
  - src/core/ports/home.py
  - src/core/policy/builtin_deny.py
  - src/execution/guard.py
  - src/execution/filesystem.py
  - src/execution/shell.py
  - src/execution/git.py
  - src/execution/executor.py
  - src/orchestrator/daemon.py
  - src/orchestrator/pending_store.py
  - src/orchestrator/dispatcher.py
  - tests/bootstrap/test_cli.py
  - tests/orchestrator/test_daemon.py
  - tests/orchestrator/test_daemon_execution.py
  - tests/orchestrator/test_idempotency_store.py
  - tests/orchestrator/test_pending_store.py
  - tests/execution/test_second_wall.py
  - tests/execution/test_shell.py
  - tests/execution/test_git.py
  - tests/execution/test_filesystem.py
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 16: Code Review Report

## Veredicto

La revisión profunda final queda **clean**. No encontré bypasses de política A/B/C/D, repetición
idempotente conocida, acceso administrativo desde Home Edge ni defectos abiertos de severidad
crítica o warning en el corte revisado.

Yo revisé `45c8a28d464ea3f97eafab81c378ba1fd75d4fde` contra
`809bc98866a332146df3e5939421b5dc9968e80c`. Revisé también los fixes sucesivos que cerraron los
hallazgos de las pasadas anteriores. No leí ni mostré secretos y no modifiqué código fuente.

## Verificación independiente ejecutada

```text
106 passed, 2 skipped in 3.10s
  - bootstrap CLI Home
  - daemon owner/Home e IPC Unix
  - ejecución y confirmaciones
  - idempotencia y pending
  - segunda muralla filesystem, shell y Git

Ruff dirigido: PASS
Ruff format check dirigido: PASS
mypy --strict dirigido: PASS
import-linter: 2 contratos kept, 0 broken
git diff --check: PASS
```

Los dos skips dirigidos son gates opt-in/ambientales, no fallos. Como evidencia complementaria del
corte, la ejecución completa registrada por el implementador reporta `731 passed, 7 skipped`; CI
volverá a ejecutar los gates globales.

## Cierre de hallazgos anteriores

### WR-01 — contexto efectivo de la segunda muralla: cerrado

Shell fija al construir el adapter la ruta absoluta/canónica de cada binario permitido, entrega al
guard esa ruta y el argv exacto, y ejecuta exactamente la misma ruta autorizada. Git entrega al
guard el cwd resuelto, argv y binario resuelto que usa en el subprocess. Las reglas D incorporan
los patrones de rutas absolutas necesarios para conservar los bloqueos.

### WR-02 — durabilidad de pendientes: cerrado

`pending.db` usa WAL con `synchronous=FULL`. Los estados que habilitan I/O se resuelven mediante
CAS dentro de `BEGIN IMMEDIATE`, con estado, TTL y revisión en la condición.

### WR-03 — carrera D contra TTL/concurrencia: cerrado

Si el CAS de rechazo D pierde, el daemon recarga el estado real. Si la fila continúa pendiente pero
ya venció, la terminaliza como `expired` mediante otro CAS; de lo contrario responde con el estado
y la revisión observados. La regresión D-vs-TTL comprueba que no se publica un rechazo ficticio.

### WR-04 — límite durable por bytes: cerrado

El store idempotente limita las respuestas persistidas a 16 KiB medidos sobre UTF-8. Un exceso
falla cerrado y conserva el claim ambiguo como `in_progress`, por lo que el efecto no puede
reabrirse como una solicitud nueva.

### WR-05 — aislamiento de identidad y socket: cerrado

El runtime dir Home exige owner UID exacto, grupo compartido exacto y modo exacto `0750`. El socket
Home exige un UID Edge distinto mediante `SO_PEERCRED`, aplica allowlist RPC y queda separado del
socket owner `0600`. El smoke opt-in con la identidad local real verificó que Edge abre Home y que
el kernel rechaza el socket owner con `EACCES` (`errno 13`).

## Matriz final de invariantes

| Invariante | Resultado |
|---|---|
| A ejecuta sólo tras política | Cumple |
| B siempre requiere confirmación simple | Cumple |
| C exige literal `CONFIRMAR` | Cumple, incluida escalada B→C en CLI |
| D no es confirmable ni ejecutable | Cumple |
| Política se reevalúa al confirmar | Cumple |
| Segunda muralla inmediatamente antes del I/O efectivo | Cumple |
| Primera respuesta válida gana | Cumple por CAS |
| Replay no repite efectos | Cumple; crash y capacidad fallan cerrados |
| Home no accede a métodos owner/admin | Cumple por DAC, UID y allowlist |
| DB, WAL y SHM privados | Cumple con modo `0600` |

## Recomendación de merge

El corte es apto para PR y squash merge cuando los gates globales de CI estén verdes y la rama esté
actualizada/mergeable contra `main`. No queda deuda de revisión local que justifique bloquearlo.
