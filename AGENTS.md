<!-- GSD:project-start source:PROJECT.md -->
## Project

**Wyss**

Wyss es un sistema de asistencia operativa personal y empresarial basado en arquitectura multi-agente. Un orquestador central coordina agentes especializados con dominios propios y acceso controlado a bases de conocimiento. Los agentes no deciden por el owner — ejecutan lo que el owner ya decidió, de forma precisa, trazable y auditable.

**Filosofía rectora: humano primero, IA cuando corresponde.**

**Core Value:** Santiago puede encontrar cualquier cosa en sus 2 TB en segundos, delegar tareas operativas a agentes especializados y mantener control total sobre lo que el sistema ejecuta — con auditoría de todo.

### Constraints

- **Arquitectura**: Hexagonal con ports/adapters — el núcleo no importa infraestructura directamente
- **Seguridad cognitiva**: Nivel D es absoluto y no tiene excepciones en ningún path de código
- **Contexto**: Contexto mínimo hacia afuera — los modelos externos solo reciben lo necesario
- **Auditoría**: Nada relevante ocurre sin registro — es requisito transversal a todas las fases
- **Hardware**: Sin servidor dedicado en v0.1 — estrategia API-first
- **Extensibilidad**: Agregar extractor/proveedor/agente nunca modifica código existente
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

Detalle y rationale en `.planning/research/STACK.md` y `pyproject.toml` (leer on-demand).
Python 3.12+ con `uv`, ChromaDB embebido + SQLite FTS5 (fusión RRF), IPC por Unix socket + JSON-RPC 2.0,
CLI Typer + Rich, config TOML validada con Pydantic v2, pytest + ruff + mypy strict en `core/`.

**No usar:**
- **LangChain / LlamaIndex** — abstracción pesada que pelea contra la arquitectura hexagonal propia. Wyss define sus propios ports; estos frameworks imponen los suyos.
- **PyPDF2** — deprecado.
- **Celery / Redis** — overkill absoluto para daemon single-owner local.
- **FastAPI para IPC** — HTTP innecesario; superficie de ataque y dependencia extra.
- **python-daemon (PEP 3143)** — obsoleto; systemd user units hacen esto mejor en el entorno del owner.
- **SQLAlchemy ORM** — para el esquema de auditoría e índice, SQL directo con `sqlite3` stdlib es más simple y auditable. (Core queries son pocas y estables.)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

**Ruteo de modelos (convención oficial, 2026-06-13):**
- **Claude = juicio**: discusión, planning, verificación, security review, decisiones D-XX. Todos los gates quedan en Claude.
- **Codex = construcción**: ejecución de planes GSD, debugging profundo, refactors grandes — vía `codex-gsd-exec` (stdin prompt → stdout SUMMARY; no commitea, el orquestador commitea).
- **Gemini = acarreo**: research crudo, drafts de docs, lecturas masivas, ediciones mecánicas — vía `gemini-gsd-exec` (mismo contrato stdin/stdout; `GEMINI_GSD_MODEL` para override). Nunca juicio ni gates.
- Regla fija: lo que un wrapper externo produce lo re-verifica Claude con la cadena completa (`pytest && mypy && ruff && lint-imports`) antes de commit.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Hexagonal enforced por `import-linter` (2 contratos en pyproject, la cadena de verificación los corre):

1. **`core` es puro** — stdlib only; no importa pydantic ni ninguna capa.
2. **Las capas son independientes** — `orchestrator, agents, knowledge, gateway, execution, audit, ledger`
   solo importan de `core`, jamás entre sí. Todo cableado cruzado se inyecta por constructor desde
   `bootstrap` (composition root, única frontera Pydantic).

```
bootstrap (CLI Typer + config Pydantic→frozen + DI manual)
   └─ orchestrator (daemon Unix-socket JSON-RPC, dispatcher fail-closed, PendingStore B/C,
                    LLMOrchestrator — adapter de OrchestratorPort que recibe ModelGatewayPort inyectado)
        └─ core/policy (CognitivePolicyEngine: Plan → PolicyDecision A/B/C/D; BUILTIN_DENY Final,
                        la config solo AGREGA reglas) → execution (PlanExecutor → FileSystem/Shell/Git,
                        segunda muralla D-68, UndoJournal, verify post-acción)
   agents (ConfiguredAgent config-driven [[agents]], ScopedRetrieval, anti-injection)
   knowledge (ingesta secret-gated → FTS5+Chroma → retrieval RRF)
   gateway (única salida a modelos: cost gate PRE-llamada, minimizer, providers, traces)
   audit (append-only, DB separada) — transversal: todo el camino queda registrado
   ledger (finanzas: agregaciones SQL deterministas, nunca LLM para números)
```

Detalle completo: `docs/architecture/WYSS_TARGET_ARCHITECTURE.md` (capas, flujos, anti-patterns)
y `docs/audit/WYSS_SYSTEM_MAP.md` (mapa por archivo).

**Protegidos D-85** — no tocar sin decisión explícita del owner: `src/gateway/cost.py`,
`src/gateway/gateway.py`, `src/orchestrator/dispatcher.py`, `src/agents/configured_agent.py`,
`src/agents/registry.py`. Tampoco vaciar/perforar `src/core/policy/builtin_deny.py`.

Reglas duras que ningún cambio puede violar: el LLM solo propone (el nivel A-D lo asigna el engine
determinístico; `estimated_risk` solo puede subir — POL-04); jamás `shell=True` (test AST lo enforcea);
`shutil.move` y no `os.rename` (EXDEV cross-FS NTFS↔ext4); errores de adapters son resultados
(`ToolResult(success=False)`), no excepciones propagadas.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:profile-start -->
## Developer Profile

> Perfil global en `~/.claude/rules/perfil.md` (generado por `/gsd-profile-user`); aplica acá sin cambios.
<!-- GSD:profile-end -->

## Gotchas de entorno (verificados)

- `~/Data` → `/mnt/hdd/Data` (NTFS): verificar `mountpoint /mnt/hdd` antes de escribir; `core.filemode false` ya seteado.
- `uv sync` warning de hardlink (cache SSD→NTFS): no bloqueante. Codex sandbox: `UV_CACHE_DIR` ro → usa /tmp solo.
