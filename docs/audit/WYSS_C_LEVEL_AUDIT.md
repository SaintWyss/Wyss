# Wyss — Auditoría C-Level

> 2026-07-02 · commit `fef3ab8` · Auditor: Fable 5 (rol: Chief Systems Engineer / Architect / Release Auditor)
> Toda afirmación está respaldada por evidencia del repo o por la cadena de verificación corrida en vivo.

## Resumen ejecutivo

La premisa de "repo fragmentado por agentic coding" es **falsa**. Wyss es de los repos generados-con-IA
más disciplinados que se pueden auditar: arquitectura hexagonal **enforced por herramienta** (import-linter,
2/2 contratos kept), mypy strict sobre src+tests (0 issues), 424 tests verdes, política cognitiva con
denylist inamovible en código, doble muralla de riesgo, undo journal, auditoría append-only, cero
`shell=True`, secretos fail-closed en ingesta y gateway.

El problema de Wyss no es calidad ni arquitectura. Es **brecha de producto**: el loop central prometido
("hablarle a Wyss y que ejecute con juicio") no funciona con un LLM real. El daemon existe, la política
existe, los adapters existen — pero el orquestador conversacional es un fake determinístico porque el plan
05-05 (Hermes) está bloqueado por infraestructura externa (sin imagen Docker publicada, UFW, toolsets).
Segundo problema: **cero CI** — toda la disciplina de gates vive en la convención del orquestador humano/IA,
no en un pipeline. Tercero: **documentación pública mentirosa** — README dice "Fase 0 — Diseño" con 8/10
fases cerradas.

## Verdict: **PARTIAL-GO**

Se puede seguir con feature work (fase 9) **solo después** de: (1) PR-00/PR-01 (baseline + CI — barato,
inmediato), y (2) decisión del owner sobre PR-06 (orquestador LLM vía gateway vs. esperar Hermes). Sin (2),
cada fase nueva construye sobre un core loop no probado con LLM real y agranda la deuda de calibración.
NO-GO no se justifica: build verde, arquitectura sana, nada podrido que reparar antes de continuar.
GO pleno tampoco: el gap conversacional es estructural al producto, no cosmético.

## Scores por dimensión

| Area | Score 0-10 | Status | Evidence | Risk | Priority |
|---|---:|---|---|---|---|
| Arquitectura de software | 9 | OK | import-linter 2/2 KEPT; core stdlib-only; DI manual en bootstrap; ports antes que impls (D-11) | Bajo — riesgo de erosión sin CI | P2 Medium |
| Calidad de código | 8 | OK | mypy strict 0 issues en src+tests; ruff limpio; decisiones D-XX documentadas por fase | `bootstrap/cli.py` 35.6K concentra CLI+composition (cohesión) | P3 Low |
| Configuración y entorno | 6 | Weak | TOML sin secretos + Pydantic fail-fast OK; pero `config/.env` NO existe, LiteLLM down, deps muertas `fastmcp`/`mcp` en pyproject | Providers reales inutilizables hoy; deps muertas confunden a ejecutores | P1 High |
| Build, test y release | 5 | Weak | Cadena verde verificada en vivo (424 passed) pero **no existe `.github/`** — cero CI; sin versionado de release; sin systemd unit pese a STACK.md | Regresión silenciosa el día que un ejecutor barato no corra la cadena | P0 Critical |
| UX / Producto | 6 | Weak | CLI coherente (index/search/ask/confirm/fin/status, Rich); pero el flujo estrella (`ask` conversacional) responde con orquestador fake; producto se siente "índice + ledger", no "empleado" | Expectativa vs realidad; el pitch del README no es lo que corre | P1 High |
| Sistemas de IA | 5 | Weak | Gateway ejemplar (cost gate pre-llamada, minimizer, traces 0600); PERO: orquestador LLM no cableado (05-05 BLOCKED), advisory de Pellegrini jamás calibrada (rúbrica determinística de respaldo), Ollama/embeddings dependen de servicios locales caídos | El corazón AI del producto está sin probar end-to-end | P0 Critical |
| Seguridad y safety | 9 | OK | BUILTIN_DENY `Final` no vaciable; 2da muralla en adapters (D-68); allowlist argv sin shell=True (verificado por grep y por test AST); SecretFilter fail-closed; audit append-only DB separada; anti-injection con fixture dorado | Residual: symlink/path-traversal merece re-audit dedicado (PR-08) | P2 Medium |
| Documentación | 4 | Broken | README = "Fase 0 — Diseño" (realidad: fase 8/10); "14 contratos" (hay 16 Protocols+ABC); `scripts/` documentado y vacío; CLAUDE.md sección Architecture = "not yet mapped"; docs/15-roadmap.md stale vs .planning/ROADMAP.md (10 fases) | Cualquier agente/humano nuevo se orienta con docs falsos | P1 High |
| Finishabilidad | 6 | Weak | 40/41 planes ejecutados; fases 9-10 definidas con criterios medibles; blocker único bien documentado (05-EMPIRICAL.md) | Riesgo de scope: fase 10 (Modo Equipo) es otro producto; sin definición de v0.1-release | P1 High |

## Top 10 problemas críticos

1. **Orquestador conversacional fake** — `orchestrator/daemon.py` opera con `_DeterministicOrchestrator`; Hermes (05-05) bloqueado por A2 (sin imagen publicada), A3 (disabled_toolsets), A4 (UFW). El producto no cumple su propia definición. → PR-06.
2. **Cero CI** — no hay `.github/`; la cadena `pytest+mypy+ruff+lint-imports` es convención, no gate. Con ejecutores baratos (Codex/Qwen/GLM) esto es la única muralla real contra regresión. → PR-01.
3. **Advisory sin calibrar** — `judge_advisory_quality` corre rúbrica determinística de respaldo, nunca LLM real (STATE.md, deuda diferida 08-04). La calidad de la prosa de Pellegrini es desconocida. → PR-06/PR-10.
4. **`config/.env` inexistente + LiteLLM :4000 down** — providers reales inoperables; toda evidencia E2E con LLM es de fakes. → PR-03.
5. **README y docs fundacionales mentirosos** — "Fase 0 — Diseño", "14 contratos", `scripts/` fantasma. → PR-09.
6. **Deps muertas `fastmcp`/`mcp`** en pyproject (0 imports) — instalan superficie MCP que nadie usa. → PR-03.
7. **Residuos de test en `data/` real** — `trash_journal_test.db`, `trash_test_sentinel.txt` sin cleanup (deliberado por pitfall /tmp, pero acumula basura junto a datos reales del owner). → PR-00.
8. **CLAUDE.md §Architecture vacío** ("not yet mapped") — el runbook que todo orquestador debe leer no describe la arquitectura que sí existe. → PR-09.
9. **Sin definición de release v0.1** — no hay criterio de "esto se puede usar todos los días"; fases 9-10 podrían empezar sin cerrar el gap conversacional. → PR-10.
10. **Naming confuso `core/orchestrator` vs `orchestrator`** — mismo nombre, capas distintas (intent puro vs daemon). No es bug; es costo cognitivo para ejecutores baratos. → documentado en PR-09 (NO renombrar: el churn no paga).

## Top 10 fixes de mayor impacto (orden de ejecución)

1. PR-00 — baseline: cleanup data/, `.import_linter_cache` a .gitignore, tag del estado verde.
2. PR-01 — GitHub Actions con la cadena existente (el fix más barato con mayor retorno).
3. PR-03 — podar fastmcp/mcp; crear `config/.env` desde example; documentar dependencia LiteLLM.
4. **Decisión owner**: Hermes vs adapter API para el orquestador (bloquea PR-06).
5. PR-06 — `LLMOrchestrator` adapter sobre `OrchestratorPort` usando el gateway existente (provider litellm/anthropic ya escritos). Hermes queda como adapter alternativo futuro.
6. Calibración advisory Pellegrini con LiteLLM arriba (script throwaway ya descrito en STATE.md).
7. PR-09 — README real + ARCHITECTURE.md + banner "histórico" en docs/00-18.
8. PR-08 — re-audit seguridad fases 6-8 (path traversal/symlinks en FileSystemAdapter).
9. PR-07 — pass UX de CLI (errores, empty states, `--help` en español consistente).
10. PR-10 — definición y corte de v0.1 RC (fase 9 adentro solo si 05/06 cerrados; fase 10 afuera).

## Qué NO tocar

- `src/gateway/cost.py`, `src/gateway/gateway.py`, `src/orchestrator/dispatcher.py`, `src/agents/configured_agent.py`, `src/agents/registry.py` — protegidos por decisión (D-85, STATE 08-04: "INTACTOS"). Cualquier cambio requiere decisión explícita del owner, no un ejecutor barato.
- `src/core/policy/builtin_deny.py` — la denylist es invariante de seguridad; jamás en scope de un PR de limpieza.
- `.planning/` — estado GSD; solo lo tocan los comandos GSD.
- No renombrar `core/orchestrator` ni reestructurar paquetes: import-linter y 424 tests dependen del layout; el beneficio no paga el churn.

## Qué estabilizar primero

CI (PR-01) antes que cualquier PR que toque código. Sin CI, delegar a ejecutores baratos multiplica el
riesgo de regresión inadvertida — hoy el único gate es la disciplina del orquestador.

## Clasificación de acciones (mapeo al modelo A-D existente)

El repo YA implementa el modelo exigido; se documenta, no se inventa:

| Categoría auditoría | Nivel Wyss | Confirmación | Rollback | Audit log | Review modelo fuerte | Rechazo |
|---|---|---|---|---|---|---|
| Read-only | A | No | No | Sí (AuditLogger) | No | No |
| Low-risk write | B | Simple (`wyss confirm`, TTL) | Sí (UndoJournal) | Sí | No | No |
| Medium/High-risk write | C | Fuerte (frase de confirmación) | Sí (UndoJournal + verify) | Sí | Sí (los gates quedan en Claude, runbook CLAUDE.md) | No |
| Destructivo/inválido | D | — | — | Sí (rechazo auditado) | — | **Absoluto** (BUILTIN_DENY, fail-closed por valor+isinstance) |
| Forbidden (meta) | — | — | — | — | — | Vaciar denylist, shell=True, tocar protegidos D-85: prohibido por código/decisión |

## Tabla de riesgos

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Regresión introducida por ejecutor barato sin correr la cadena | Alta | Alto | PR-01 (CI) + regla existente "Claude re-verifica antes de commit" |
| Hermes nunca se desbloquea y el producto queda sin conversación | Media | Crítico | PR-06: adapter API sobre OrchestratorPort; Hermes pasa a opcional |
| Prosa advisory mala en producción (nunca calibrada) | Media | Medio | Calibración con LiteLLM + rúbrica LLM-judge (marker `llm_judge` ya existe) |
| Docs falsos desorientan a agentes ejecutores | Alta | Medio | PR-09 |
| data/ del owner contaminado por tests NTFS | Baja | Bajo | PR-00 (cleanup + subdir dedicado) |
| Scope creep fase 10 (Modo Equipo) antes de cerrar v0.1 | Media | Alto | PR-10 (corte explícito) |
