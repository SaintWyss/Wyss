---
phase: 13
slug: intake-n8n
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-11
updated: 2026-07-11
---

# Phase 13 — Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (asyncio strict) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/bootstrap/test_web.py tests/orchestrator/test_daemon.py -q` |
| **Full suite command** | `uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports` |
| **Estimated runtime** | ~15 s (quick) / ~70 s (full) |

## Sampling Rate

- After every task commit: quick command
- After every plan wave: full suite
- Before verify-work: full suite green
- Max feedback latency: 70 seconds

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-01-T1 | 13-01 | 1 | INTAKE-02 | (config fail-closed) | [intake] extra=forbid, enabled=false default, opt-in | unit (tdd) | `uv run pytest tests/bootstrap/test_config.py -q` | ✅ | ⬜ pending |
| 13-01-T2 | 13-01 | 1 | INTAKE-02 | T-13-01, T-13-02, T-13-03, T-13-04 | intake.propose fuerza floor B antes de dispatch; nunca ejecuta directo; origen SYSTEM/intake auditado; dispatcher.py intacto | unit (tdd) | `uv run pytest tests/orchestrator/test_daemon.py -q` | ✅ | ⬜ pending |
| 13-02-T1 | 13-02 | 2 | INTAKE-01 | T-13-06 | intake_token dedicado 0600, jamás la cookie; no se imprime | unit | `uv run pytest tests/bootstrap/test_cli.py -q` | ✅ | ⬜ pending |
| 13-02-T2 | 13-02 | 2 | INTAKE-01, INTAKE-03 | T-13-05..T-13-10 | bearer compare_digest; 401 sin loguear token; 429 rate limit; 404 si disabled; exención de cookie solo /api/intake | unit (tdd) | `uv run pytest tests/bootstrap/test_web.py -q` | ✅ | ⬜ pending |
| 13-03-T1 | 13-03 | 3 | INTAKE-01, INTAKE-02, INTAKE-03 | T-13-11, T-13-12 | smoke real curl-como-n8n: bearer→bandeja, sin bearer→401, flood→429, cero auto-ejecución | manual | checkpoint human-verify | — | ⬜ pending |

## Wave 0 Requirements

- [x] Framework ya instalado (pytest asyncio)
- [ ] Tests de config `[intake]` fail-closed — creados en 13-01 Task 1 (test_config.py)
- [ ] Tests del RPC intake.propose (floor B, no auto-exec, actor SYSTEM/intake) — creados en 13-01 Task 2 (test_daemon.py)
- [ ] Tests del endpoint /api/intake (bearer válido/inválido/ausente, 429, 404 disabled, exención acotada, body cap) — creados en 13-02 Task 2 (test_web.py)

Nota Nyquist: sin `<automated>MISSING</automated>`. Cada task de código crea/extiende su propio
test file en la misma pasada (test_config.py, test_daemon.py, test_cli.py, test_web.py ya existen).
El único manual-only es el checkpoint final (daemon + bridge vivos + curl real).

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Intake real curl-como-n8n end-to-end | INTAKE-01/02/03 | requiere daemon + bridge LAN vivos, cert self-signed, y opcionalmente n8n | Plan 13-03: `[intake].enabled=true` + `wyss start` + `wyss web --lan`; curl con bearer de data/intake_token → pending en bandeja; sin bearer → 401; 6+ requests → 429; confirmar cero auto-ejecución |

## Key Decisions (documentadas en los planes)

1. **Floor B vía RPC nuevo `intake.propose`, SIN tocar dispatcher.py** (Plan 13-01): el handler reusa el
   pipeline de ask y aplica `max(decision.risk_level, RiskLevel.B)` con `outcome_for()` ANTES de llamar
   `dispatch()`. El dispatcher (D-85 protegido) queda intacto; la rama runner/_execute_plan de `_ask`
   NO se replica → intake nunca alcanza outcome "queued". POL-04 preservado (el floor solo sube: D/REJECT
   sigue rechazado).
2. **Origen externo auditado como SYSTEM/"intake"** (Plan 13-01): distinguible del OWNER; la instruction se
   rotula como dato externo no confiable en el message. El rótulo + floor B/C + preview en bandeja = defensa
   final contra prompt-injection laundering.
3. **Invariante: intake JAMÁS escribe a memoria** (Plan 13-01): previene memory-poisoning (Pitfall 5/8).
4. **Bearer token dedicado ESTÁTICO `data/intake_token`** (Plan 13-02): espeja `_load_or_create_web_token`
   (token_urlsafe(32), 0600, estable entre reinicios, borrar = rotar). Nunca la cookie del pairing; nunca
   seteado como cookie; rotable independientemente.
5. **Exención de cookie QUIRÚRGICA solo para `/api/intake`** (Plan 13-02): el middleware mantiene host+origin
   en todo path; solo ese path exacto salta `_authenticate_request` y valida bearer vía `_authenticate_intake`.
   Ningún otro path pierde protección de cookie.
6. **401/429 auditados vía `_LOG.warning` sin el valor del token** (Plan 13-02): mismo patrón que el
   middleware existente (log del hecho, jamás el secreto). El intake ACEPTADO se audita a audit.db vía
   COMMAND_RECEIVED (SYSTEM/intake) en el daemon.
7. **Rate limit propio en memoria** (Plan 13-02): token bucket / ventana de 60 s por proceso, N configurable
   en `[intake].max_per_minute`; excedido → 429. Body cap: instruction max_length 2000 (anti-DoS).
8. **`[intake].enabled=false` por default** (Plan 13-01/13-02): opt-in explícito; deshabilitado → endpoint 404.
