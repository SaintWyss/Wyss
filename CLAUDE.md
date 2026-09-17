<!-- Fuente única de instrucciones: AGENTS.md (Codex la lee directo, Claude la importa). Acá va SOLO lo exclusivo de Claude. -->
@AGENTS.md

## GSD Workflow Enforcement (solo Claude)

Esta sección no va en AGENTS.md: Codex ejecuta tareas ya planificadas por wrapper y no abre GSD.

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.

## Orchestration Runbook (directiva del owner — 2026-06-12)

Escrito por Fable 5. Cualquier modelo orquestador (sonnet incluido) DEBE seguir esto literalmente.
El owner pidió piloto automático: tomar las decisiones recomendadas, consultar solo ante cambios
de arquitectura, seguridad o scope ("algo serio serio").
El piloto automático arranca con **un** OK de presupuesto al iniciar la fase (estimación de la cadena
completa de abajo); con ese OK la cadena corre sin volver a preguntar. Verificación = una pasada: si el
review o el verifier marcan blockers, se informa al owner antes de re-iterar.

### División de modelos (no negociable)

| Trabajo | Quién |
|---|---|
| Planes de fase, mejoras, fixes, juicio de calidad, resolución de desvíos | Fable 5 (escalar si no estás corriendo en Fable) |
| Escritura de código pesada (ejecución de planes) | Codex via `codex-gsd-exec` (reasoning high) |
| Code review de fin de fase: leer el diff y listar findings (acarreo) | Gemini via `~/.local/bin/gemini-review` (lee API key de opencode.jsonc en runtime) |
| Gate del review: qué findings bloquean y qué se arregla | Fable 5 |
| Cierre mecánico por plan | Sonnet (subagente) |
| Verifier de fase (`gsd-verifier`, juicio) | Fable 5 u opus con `model=` explícito — nunca sonnet |
| Security audit (`/gsd-secure-phase`) | Fable 5 (Mythos no disponible; opus solo como fallback) |

### Loop de ejecución de fase (cross-AI)

Por cada plan, en orden de waves, SECUENCIAL (worktree isolation falla con cwd=~; no usar `isolation`):

1. **Prompt**: header estándar (proyecto, root absoluto `/mnt/hdd/Data/10_Workspace/projects/wyss`,
   reglas, formato SUMMARY con frontmatter `plan:`/`status:`, marcador `=== PLAN FOLLOWS ===`) + PLAN.md completo.
2. **Ejecutar**: `cd <root> && BASE=$(git rev-parse HEAD) && timeout 3600s codex-gsd-exec < prompt > summary 2> err.log`
   en background. Guardar `BASE` (el HEAD previo) junto al summary.
   Codex NO commitea: deja los cambios sin commitear. Si `git rev-parse HEAD` ya no es `BASE`, Codex commiteó
   (uno o varios): `git reset --soft $BASE` deja todo su trabajo en el index y se re-verifica antes de commitear,
   porque el gate va antes del commit.
3. **Cierre (subagente sonnet)**: cadena verde `uv run pytest && uv run mypy && uv run ruff check src tests
   && uv run lint-imports` (si falla: NO commitear, escalar a Fable) → commits atómicos por task → SUMMARY.md al dir de fase → `gsd-sdk query roadmap.update-plan-progress 03 <plan> complete`
   → commit docs. Trailer siempre: `Co-Authored-By:` del modelo orquestador.
4. Heartbeat `[checkpoint] phase X wave N/M plan <id> <status> (P/Q plans done)` entre pasos.

Fin de fase: review Gemini (diff completo de la fase → findings → REVIEW.md; gate y fixes los decide Fable) →
verifier Fable/opus (`gsd-verifier`) → `gsd-sdk query phase.complete` → push.

### Gotchas verificados (no redescubrir)

- gsd-sdk: `state.record-metric/record-session/update-progress/add-decision` devuelven `updated:false` (ignorar);
  `state.advance-plan` cuenta mal "Plan: N of M" (corregir a mano); `state.patch`, `roadmap.update-plan-progress`,
  `requirements.mark-complete`, `phase.complete` funcionan.
- Cross-AI: aunque ningún plan tenga `cross_ai: true`, TODOS los planes van por Codex (directiva owner).
