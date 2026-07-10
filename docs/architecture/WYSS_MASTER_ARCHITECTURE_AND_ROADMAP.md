# Wyss — Master Architecture & Roadmap

**Fecha:** 2026-07-09 · **Estado del repo:** post RC2 + Mobile Bridge MVP (`e687e92`),
PR-08 Security Re-Audit en curso. Documento de arquitectura y plan de ejecución.

> Veredicto: **preservar arquitectura**. La hexagonal con policy determinística en el
> centro es la correcta; falta completar capacidades dentro del molde, no cambiar molde.

---

## 1. Diagnóstico ejecutivo

Wyss es un **operador local supervisado que funciona**: el loop ask → plan (LLM real)
→ política A/B/C/D → confirmación → ejecución → verificación → auditoría → evidencia de
undo corre E2E desde escritorio y teléfono. 488 tests, mypy strict, hexágono enforced.

**Sólido (no tocar):** hexágono + 2 contratos import-linter; `CognitivePolicyEngine` +
`BUILTIN_DENY`; flujo confirm B/C con re-evaluación; journal-antes-de-mutar; gateway
(cost gate, minimizer, traces); auth del bridge.

**Frágil:** executor no lee/lista (**cerrado en PR-11**); undo es evidencia, no comando
(**cerrado en PR-09**); móvil sin TLS; deuda F3 de la segunda muralla (**cerrada en
PR-08**); RPC `audit` del daemon fake.

**Para v0.1 estable:** PR-08 ✅ + PR-09 ✅ + PR-11 ✅ + PR-10 (TLS).
**Para v0.2+:** memoria, n8n, scheduler, Notion. **Arquitectura: se preserva.**

---

## 2. Mapa del sistema (resumen)

| Módulo | Madurez | Acción |
|---|---|---|
| bootstrap (CLI+config+web) | Alta | Partir `cli.py` (imán); no urgente |
| daemon/orchestrator | Alta | RPC audit real; prompt paths absolutos |
| dispatcher | Alta (D-85) | No tocar |
| policy engine + denylist | Alta | Solo AGREGAR reglas |
| execution (executor/fs/shell/git/journal) | Alta en lo que hace | read/list/stat; `wyss undo`; F3 (hecho) |
| gateway (cost/gateway protegidos) | Alta | Solo curar aliases |
| knowledge | Alta (2TB probado) | Mantener wrapping anti-injection |
| agents/ledger | Media/Alta | Calibrar advisory (v0.2); ledger intocable |
| web + bridge móvil | Alta | mkcert (PR-10) |

Detalle por archivo: `docs/audit/WYSS_SYSTEM_MAP.md`.

---

## 3. Arquitectura objetivo

```
owner ── teléfono/web/CLI ── wyss web (bridge, NUNCA decide riesgo)
                                   │
                            daemon (Unix socket JSON-RPC)
                                   │ intake → audit
                            LLMOrchestrator (classify → draft Plan)  ←→ gateway ←→ LiteLLM/Anthropic
                                   │ el LLM SOLO propone
                            CognitivePolicyEngine (A/B/C/D determinístico + denylist Final)
                                   │
          A: ejecuta directo    B/C: PendingStore+TTL → confirmación (re-evalúa política)
                                   │
                            PlanExecutor → 2ª muralla → UndoJournal (antes de mutar)
                               fs / shell(allowlist) / git
                                   │
                            verify → audit (task.completed/failed) → wyss undo <task_id>

   Knowledge (documentos, 2TB) · Memory (v0.2: hechos/preferencias) · State (pending/ledger/journal) · Audit (forever)
```

**Roles:** PC = única autoridad y executor. Teléfono/web/CLI = clientes del mismo bridge.
LiteLLM = modelos baratos; Anthropic = tier fuerte. Notion = espejo curado (adapter futuro).
mem0/tabla propia = capa Memory v0.2. n8n = productor de tareas, jamás executor.
Aburrido a propósito: cero LangGraph/CrewAI.

---

## 4. Límites de producto

**ES:** operador personal local-first · capa de ejecución segura con criterio · router de
modelos con presupuesto · asistente con contexto · planificador supervisado · audit-first.

**NO ES:** clon de AutoGPT · agente cloud/público · shell bot sin límites · app nativa
first · plataforma smart-home (aún) · producto multi-usuario (aún) · agente autónomo sin
supervisión (nunca).

---

## 5. Arquitectura de seguridad

Consolidada en **`docs/security/SECURITY_MODEL.md`** (capas, niveles, denylist, tabla de
prompts peligrosos, modelo LAN, huecos conocidos). PR-08 la produjo y la blindó con tests.

---

## 6. Undo/rollback (PR-09)

Base: `undo_entries` con `inverse_op` + backups + restore inverso en ABORT.
`wyss undo <task_id>`: lista entradas `applied` en orden inverso → **dry-run** → clasifica
reversibilidad → confirma al nivel de riesgo de la inversa (pasa por el MISMO engine, no es
bypass) → ejecuta → audita. Por tipo: create/write-nuevo → delete a papelera; write-overwrite
→ restaurar backup; move → move inverso con check de colisión; delete → restaurar de papelera;
shell → **irreversible** (evidencia); git → apoyar en git (fuera de v0.1). PR mínimo: CLI +
inversas file.* + dry-run + confirmación + audit. Sin UI web, sin shell/git undo.

---

## 7. Memoria y conocimiento

| Capa | Qué | Dónde | Estado |
|---|---|---|---|
| Knowledge | Documentos/notas/proyectos indexados | FTS5+Chroma | ✅ |
| Memory | Preferencias, hechos estables, reglas | `memory.db` propio (v0.2); escritura SOLO con confirmación owner | 🔜 |
| State | pending/ledger/journal/traces | SQLite por dominio | ✅ |
| Audit | Lo que pasó | audit.db forever | ✅ |

Regla anti-duplicación: **cada dato tiene UNA capa dueña**. Notion = espejo curado, no
fuente de verdad. mem0 = candidato de motor; empezar con tabla propia (el valor está en el
schema + gate de escritura, no en el vendor).

---

## 8. Automatización (n8n)

**n8n produce tareas, jamás las ejecuta.** Entrante: n8n → POST `/api/ask` con token de
servicio solo-ask → el plan pasa por policy igual → B/C quedan en Bandeja esperando al owner.
**La automatización nunca confirma** (confirmar es humano por diseño). Saliente: notificaciones
desde eventos de audit. Rutinas: scheduler propio v0.2 (APScheduler ya en stack). Recordatorio
≠ ejecución autónoma.

---

## 9. Móvil

Suficiente hoy: flujo completo, auth correcta, LAN opt-in. Endurecer (PR-10): HTTPS mkcert
(cifra token + destraba voz del browser), cookie Secure, opcional QR/PWA. Esperar: app nativa
(browser cubre todo), push (polling alcanza). Voz bloqueada hasta HTTPS; mientras, dictado del
teclado del teléfono (es texto). Pairing v0.2: tokens por dispositivo con revocación.

---

## 10. Modelos/gateway

Barato (LiteLLM): classify, draft de planes, resúmenes, advisory. Fuerte (Anthropic):
razonamiento largo, redacción final, bajo demanda. Sin LLM jamás: números del ledger,
clasificación de riesgo, denylist, decisión de ejecución. Si todo LLM falla: degradación
fail-closed (`OrchestratorUnavailable`), nada se ejecuta, comandos determinísticos siguen
vivos. Sin fallback automático entre tiers (D-17). Mejora pendiente: mensaje diferenciado
429 vs negativa vs JSON inválido.

---

## 11. Roadmap por PRs

| PR | Objetivo | Estado |
|---|---|---|
| **PR-08 Security Re-Audit** | Auditar superficie de ejecución + cerrar gaps denylist + suite prompts peligrosos + fix F3/TTL | **CERRADO** |
| **PR-09 `wyss undo`** | Undo user-facing (§6) | **CERRADO** |
| **PR-11 Operator Read Tools** | `file.read/list/stat` + `git.status/log/diff` | **CERRADO** |
| **PR-10 HTTPS local + voz** | `--tls` self-signed auto (mkcert opcional), cookie Secure, voz destrabada | **CERRADO** (PWA entregada en PR-14) |
| **PR-14 v0.1.0 Stable** | Cierre, docs, smoke físico, app web (PWA + login persistente), tag | **CERRADO** — smoke en teléfono real aprobado 2026-07-10 (`docs/releases/WYSS_v0.1.0.md`) |
| PR-15 Scheduler · PR-16 Notion adapter · PR-17 Daily Assistant · PR-12 Memory · PR-13 Intake n8n | | v0.2 |

Reordenado vs la sugerencia: PR-11 (lectura) antes que PR-10 — un operador que no puede
mirar es más grave que un token en LAN propia. Voz fusionada en PR-10 (es subproducto del
secure context). Cada PR: chico, con acceptance + rollback (revert del commit; reglas
denylist son aditivas).

---

## 12. Release

Hoy = RC2. **v0.1.0 estable:** PR-08+09+11+10 verdes + suite prompts peligrosos en CI +
smoke manual en teléfono físico + `wyss undo` demostrado + docs al día + tag `v0.1.0`.
**v0.2.0:** memoria + intake n8n + scheduler + Notion. **v0.3.0:** multi-agente (Belgrano),
calibración advisory, rutinas ricas. Gate por release: cadena completa + dangerous suite +
smoke E2E real (LLM vivo).

---

## 13. Testing

Existente: 488 unit/integración espejo de `src/`, gate dorado hit@1, AST anti-`shell=True`,
NTFS opt-in. Nuevo (PR-08): `tests/security/test_dangerous_prompts.py`. Pendiente: tests
de undo (PR-09), scope de tokens (PR-13), TLS (PR-10). Canónico:
`uv run pytest -q && uv run mypy && uv run ruff check src tests && uv run lint-imports`;
frontend `cd web && npm run test && npx oxlint && npm run build`.

---

## 14. Documentación

Al día: specs 00-18, target architecture, system map, release RC, mobile MVP, **security
model** (PR-08), **este roadmap**. Faltan: `docs/OPERATOR.md` (uso diario, troubleshooting).
Regla: un doc por audiencia, sin duplicar.

---

## 15. Riesgos

| Riesgo | Sev | Prob | Mitigación | PR |
|---|---|---|---|---|
| Token LAN en HTTP plano | Alta | Media | mkcert TLS | PR-10 |
| Shell allowlist poblada sin reglas de args | Alta | Media | arg_substrings + reglas D (base hecha PR-08) | PR-08+ |
| Prompt injection desde archivos indexados | Alta | Media | Wrapping D-70 + test dorado | PR-08 verifica |
| Comandos alucinados por LLM | Media | Alta | Types cerrados, C fail-closed, denylist | mitigado |
| Path traversal/symlink | Alta | Baja | 2ª muralla + F3 fix | **hecho PR-08** |
| Undo sobre estado cambiado | Media | Media | Check de colisión + dry-run | PR-09 |
| Sobre-automatización (n8n confirmando) | Alta | Baja | Token solo-ask | PR-13 |
| Duplicación memoria/Notion | Media | Alta | "una capa dueña" | PR-12 |
| Providers inestables (429) | Baja | Alta | Degradación + aliases | menor |
| Costo | Media | Baja | Cost gate + budgets | ✅ existe |

---

## 16. Qué NO construir todavía

App nativa (browser LAN cubre todo) · TV/luces/IoT/USB (dominio nuevo = riesgo nuevo) ·
agente autónomo de fondo con permisos amplios (contradice el invariante) · acceso remoto
público/túneles (rompe local-first; VPN personal si algún día) · cloud sync de secretos
(jamás) · multi-usuario (modelo single-owner a propósito) · marketplace/plugins (ejecución
de código ajeno = peor riesgo) · rewrite LangGraph/AutoGPT (tirar un policy engine probado) ·
dashboards fancy (datos antes que vidrio).

---

## 17. Próxima acción

PR-08, PR-09, PR-11 y PR-10 cerrados — todo lo técnico de v0.1 está. Siguiente:
**PR-14 v0.1.0 estable**: smoke en el teléfono físico del owner (`wyss web --lan --tls`,
aceptar cert, probar voz), docs al día (`docs/OPERATOR.md`) y tag `v0.1.0`.
