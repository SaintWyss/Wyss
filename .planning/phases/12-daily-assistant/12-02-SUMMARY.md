---
phase: 12-daily-assistant
plan: 02
status: complete
completed: 2026-07-11
requirements: [DAILY-01, DAILY-03]
builder: codex (codex-gsd-exec) — verificado y commiteado por Claude
---
# 12-02 Summary — RPC digest.today + job interno
- RPC `digest.today` (LedgerPort inyectado por daemon; ventana = 1° del mes → hoy, ART; devuelve {markdown, generated_at}; audita DIGEST_GENERATED; solo-lectura).
- `schedule_digest(hour, minute, callback)` con job_id `internal:digest` DIRECTO sobre APScheduler — sin RoutineStore/dispatch (cero superficie de política nueva). Callback materializa `data/digests/YYYY-MM-DD.md` (`write_digest_file`), misma ventana que el RPC. digest_enabled=False → no registra.
