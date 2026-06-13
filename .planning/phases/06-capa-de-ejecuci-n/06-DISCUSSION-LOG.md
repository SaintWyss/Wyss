# Phase 6: Capa de Ejecución — Discussion Log

**Date:** 2026-06-13 · Mode: advisor (research swarm omitido — decisiones arch internas)

Owner aceptó las 4 recomendaciones presentadas (perfil: delegator + auto-pilot decisiones menores).

| # | Gray area | Opciones presentadas | Elección |
|---|-----------|----------------------|----------|
| 1 | EXEC-03 undo/papelera | send2trash+SQLite (rec) / trash propia+JSONL / gio trash+SQLite | **send2trash + journal SQLite** (D-64/D-65) |
| 2 | EXEC-01 shell allowlist | allowlist binarios sin shell=True (rec) / +patrones args / denylist+sandbox | **allowlist binarios, exec argv, fail-closed** (D-66) |
| 3 | EXEC-02 verificación post | por tipo existencia+hash/conteo (rec) / hash completo / solo exit+existencia | **por tipo de acción** (D-67) |
| 4 | EXEC-04 2da muralla | resolver symlinks+re-evaluate (rec) / comparar nivel vs max_risk / re-evaluate sin resolver | **resolver paths reales + re-evaluate engine** (D-68) |

**Capturado sin preguntar (deriva del dominio):** D-69 — executor honra `Action.on_error` (enforcement diferido desde 05-02), rollback vía journal.

**Deferred:** adapters Calendar/Messaging/App (fases posteriores); undo multi-nivel.
