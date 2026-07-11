---
phase: 13-intake-n8n
plan: 02
status: complete
completed: 2026-07-11
requirements: [INTAKE-01, INTAKE-03]
builder: codex (codex-gsd-exec) — verificado y commiteado por Claude
---
# 13-02 Summary — Token dedicado + POST /api/intake
- `_load_or_create_intake_token` (espejo web_token: urlsafe 32, data/intake_token 0600, estable, rotable borrándolo; jamás se imprime).
- `POST /api/intake` en el bridge: bearer con `compare_digest`; exención de cookie QUIRÚRGICA (match exacto del path, después de Host/Origin — allowlists intactas); 401 auditado sin el valor del token; 429 rate limit en memoria (deque por minuto, max_per_minute); 404 legible con enabled=false; body cap 2000 chars (422). Llama al RPC intake.propose.
- Tests: bearer válido/inválido/ausente, 429, 404 disabled, exención acotada (otros paths siguen exigiendo cookie), token nunca en caplog.
