---
phase: 12-daily-assistant
plan: 03
status: complete
completed: 2026-07-11
requirements: [DAILY-01, DAILY-03]
builder: codex (codex-gsd-exec) — verificado y commiteado por Claude
---
# 12-03 Summary — CLI wyss digest + composition root
- `wyss digest`: thin RPC client (digest.today), render legible, daemon caído → panel accionable. Jamás abre DBs.
- Composition root: SqliteLedgerStore inyectado a run_daemon (satisface LedgerPort); job del digest registrado si [digest].enabled.
- Extra benigno: PermissionError tratado como daemon caído en ask/digest (mismo panel).
