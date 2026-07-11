---
phase: 12-daily-assistant
plan: 01
status: complete
completed: 2026-07-11
requirements: [DAILY-01, DAILY-02]
builder: codex (codex-gsd-exec) — verificado y commiteado por Claude
---
# 12-01 Summary — compose_digest() puro + config [digest]
- `src/orchestrator/digest.py`: `compose_digest()` PURO (sin IO/LLM/dispatch/reloj; grep estructural de ejecución = 0 — DAILY-02 por construcción). Secciones fijas: encabezado (+memoria como dato), Pendientes de bandeja, Finanzas Pellegrini (vía LedgerPort de core YA existente, inyectado — orchestrator jamás importa src/ledger), Rutinas (fallas=failed; resto últimas corridas; orden last_fired_at DESC, id).
- `DigestConfigModel` (extra=forbid: enabled/hour/minute) + config.example.toml + `AuditEventType.DIGEST_GENERATED`.
- Tests: 20 (digest + config).
