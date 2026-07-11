---
phase: 13-intake-n8n
plan: 01
status: complete
completed: 2026-07-11
requirements: [INTAKE-02]
builder: codex (codex-gsd-exec) — verificado y commiteado por Claude
---
# 13-01 Summary — Config [intake] + RPC intake.propose con floor B
- `IntakeConfigModel` (extra=forbid: enabled=False default opt-in, max_per_minute) + config.example.toml.
- RPC `intake.propose` en el daemon: reusa el pipeline de ask PERO fuerza `max(risk, B)` + `outcome_for()` ANTES del dispatch — un plan A de fuente externa cae a bandeja como pending B, jamás ejecuta directo. D/REJECT intacto (el floor solo sube). Audita COMMAND_RECEIVED con actor SYSTEM/"intake". Jamás toca memory_store.
- **dispatcher.py y pending_store.py: diff = 0 bytes** (protegidos D-85 intactos, verificado).
