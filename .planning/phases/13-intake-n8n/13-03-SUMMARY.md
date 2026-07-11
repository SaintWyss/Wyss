---
phase: 13-intake-n8n
plan: 03
status: complete
completed: 2026-07-11
requirements: [INTAKE-01, INTAKE-02, INTAKE-03]
---
# 13-03 Summary — Checkpoint: smoke curl-como-n8n (APROBADO por el owner)

## Qué se probó (bridge real, 2026-07-11)
1. Bearer válido + instruction NL → `intake.propose` → plan file.read (base A) **floored a B** → pending en bandeja: fuente externa jamás ejecuta directo (INTAKE-02 en vivo).
2. Sin bearer / inválido → 401 sin loguear token (INTAKE-01/03).
3. Rate limit verificado empírico: 5 pasan → 429 (INTAKE-03).
4. Exención quirúrgica: otros paths siguen exigiendo cookie.
5. Bug cazado y arreglado en el smoke (`6a48641`): error JSON-RPC del daemon → 502 legible.

## Sign-off
Owner aprobó 2026-07-11. Fase 13 completa (3/3). [intake] enabled=true quedó en config local (max 5/min). Conexión n8n: POST /api/intake + Bearer de data/intake_token.
