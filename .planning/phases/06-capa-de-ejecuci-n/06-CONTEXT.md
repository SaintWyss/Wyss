# Phase 6: Capa de Ejecución - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Adaptadores de ejecución reales (FileSystem, Shell, Git) detrás del `Tool` port — la
capa que **ejecuta** los Planes que el daemon de Fase 5 despacha tras confirmación.
Cubre EXEC-01..04: adapters desacoplados con allowlist (EXEC-01), verificación
post-ejecución (EXEC-02), undo vía papelera + journal reversible (EXEC-03), y la
**segunda muralla** de re-verificación de riesgo antes de ejecutar (EXEC-04).

**En scope:** rellenar `src/execution/` con FileSystemAdapter, ShellAdapter, GitAdapter
implementando el `Tool` port existente; mecanismo de papelera + journal; re-evaluación de
riesgo con resolución real de paths; honrar `Action.on_error` (rollback vía journal).

**Fuera de scope (otras fases):** CalendarAdapter/MessagingAdapter/AppAdapter (adapters de
integración externa, fases posteriores); el cerebro Hermes (05-05, bloqueado); el modelo de
agentes (Fase 7). No se reestructura el layout hexagonal.
</domain>

<decisions>
## Implementation Decisions

### EXEC-03 — Undo / papelera + journal reversible
- **D-64:** Borrado-a-papelera vía **`send2trash`** (XDG FreeDesktop trash spec) — maneja
  NTFS y cross-FS, evita reinventar el trash. Empírico a validar en research/Wave 0:
  comportamiento de send2trash sobre el mount NTFS de `~/Data` (`/mnt/hdd`).
- **D-65:** **Journal SQLite (WAL)** reusando el patrón de `PendingStore`/`SqliteAuditLogger`:
  registra origen→destino + operación inversa por acción modificadora; `restore(id)` aplica
  la inversa. Consistente con el codebase (no JSONL ad-hoc).

### EXEC-01 — Shell allowlist
- **D-66:** Allowlist de **binarios** en config TOML (ej. `git`, `ls`, `rg`); ejecución por
  **exec directo (argv), NUNCA `shell=True`** → sin inyección de shell. Args validados por el
  adapter. **Fail-closed:** binario fuera de la lista = rechazo + audit. (No patrones de args
  por ahora; no denylist/sandbox — contradeciría D-absoluto.)

### EXEC-02 — Verificación post-ejecución
- **D-67:** Verificación **por tipo de acción**: `file.write`→size + sha256; `file.move`→
  destino existe & origen ausente; `file.delete`→ausente & presente en papelera; `git`→
  exit code + estado esperado. `Verification.passed` gobierna: si falla, NO se marca success
  y se audita. (No hash completo siempre — caro sobre 2 TB; no solo exit-code — débil.)

### EXEC-04 — Segunda muralla (re-verificación de riesgo)
- **D-68:** El adapter **resuelve paths reales** (normaliza `~`/`..`, resuelve symlinks) antes
  de ejecutar, reconstruye la `Action` resuelta y **re-corre `CognitivePolicyEngine.evaluate`**.
  Si el nivel resuelto supera el `max_risk` del Tool o cambió respecto a la decisión original
  → **bloquea + audita** (plan adulterado post-política). Cierra el threat de path-tricks
  registrado en Fase 1 (01-RESEARCH §794).

### Comportamiento transversal (derivado del dominio ya construido)
- **D-69:** El executor de Fase 6 **honra `Action.on_error`** (`ABORT`/`RETRY`/`ESCALATE`,
  ya en `src/core/domain/plan.py` desde 05-02; su enforcement estaba diferido a esta fase).
  Ante fallo de un paso: `ABORT` → detiene y revierte los pasos ya aplicados vía journal (D-65);
  `RETRY` → reintenta según `RetryParams`; `ESCALATE` → audita y escala al owner.

### Claude's Discretion
- Estructura interna de `src/execution/` (un módulo por adapter vs archivo único), nombres de
  tablas del journal, firma exacta de `restore()` — decisión del planner/executor.
- **Directiva del owner (vigente):** piloto automático para decisiones menores; consultar solo
  ante cambios de arquitectura/seguridad/scope. Las 4 decisiones de seguridad (D-66, D-68)
  fueron confirmadas explícitamente.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Contratos existentes a implementar (NO redefinir)
- `src/core/ports/execution.py` — `Tool` port: `name`, `max_risk: RiskLevel`, `describe()` sync,
  `execute()`/`verify()` async. Los adapters lo implementan.
- `src/core/domain/execution.py` — `ToolResult(success, detail, payload)`, `Verification(passed, detail)`.
- `src/core/domain/plan.py` — `Action(type, target, parameters, on_error, retry_params)`,
  `ErrorPolicy`, `RetryParams` (de 05-02). EXEC-04/D-69 dependen de esto.
- `src/core/policy/engine.py` — `CognitivePolicyEngine.evaluate(plan)` único método público;
  la segunda muralla (D-68) lo re-usa, NO crea un evaluador paralelo.

### Patrones a reusar
- `src/orchestrator/pending_store.py` + `src/audit/sqlite_logger.py` — patrón SQLite WAL para
  el journal de undo (D-65).
- `.planning/phases/01-RESEARCH.md` §316 (tabla `Tool`), §794 (threat path-tricks → EXEC-04).
- `.planning/phases/05-orquestador-daemon/05-CONTEXT.md` — D-50..D-63 (daemon despacha, engine
  dispone; la capa de ejecución es lo que el dispatcher invoca tras confirmar).

### Specs del owner
- `docs/18-prompt-implementacion.md` — hexagonal/SOLID/plugin, reglas inviolables 1-9, D absoluto.
- `docs/11-*` (ejecución) — `Tool` execute pareado con verify (citado en ports/execution.py).

### Constraints del entorno
- `~/Data` → symlink a `/mnt/hdd/Data` (NTFS automount). Afecta D-64 (send2trash cross-FS) y
  D-67 (move/verify). Validar empíricamente antes de implementar.
</canonical_refs>

<deferred>
## Noted for Later
- Adapters de integración externa (Calendar/Messaging/App) — fases posteriores, ya listados como
  stubs en `src/execution/__init__.py`.
- Undo multi-nivel / time-travel del journal — más allá de restore-por-id; futura mejora.
</deferred>
