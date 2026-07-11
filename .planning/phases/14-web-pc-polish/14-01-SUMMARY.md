---
phase: 14-web-pc-polish
plan: 01
status: complete
completed: 2026-07-11
requirements: [WEB-01, WEB-02, WEB-03]
builder: codex — verificado y commiteado por Claude
---
# 14-01 Summary — Endpoints + api.ts + format.ts
8 endpoints thin-proxy cookie-auth (routines list/pause/resume/delete, digest/today, memory list/edit/forget) con 503/502 legibles, middleware intacto; api.ts con types Routine/MemoryFact/DigestToday + 8 métodos (encodeURIComponent en path params); format.ts helpers puros + vitest. Tests backend 200/401/503/502 por ruta. 692 tests, cadena completa verde.
