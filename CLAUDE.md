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

## Recommended Stack (with versions)
### Core runtime
| Componente | Elección | Versión mínima | Rationale | Confianza |
|---|---|---|---|---|
| Python | CPython | 3.12+ (3.13 si estable en CachyOS) | `tomllib` nativo, type params PEP 695, perf | HIGH |
| Gestor deps | `uv` | latest | Lockfile robusto, 10-100x más rápido que pip, estándar de facto 2025 | HIGH |
| Build backend | `hatchling` | latest | Default de `uv init --package`, simple, sin magia | HIGH |
### Conocimiento e indexación
| Componente | Elección | Rationale | Confianza |
|---|---|---|---|
| Vector store | **ChromaDB** (modo persistente embebido) | Sin servidor, API simple, colecciones por BC → mapea natural a habilitaciones | HIGH |
| Full-text | **SQLite FTS5** (stdlib `sqlite3`) | Cero deps, tokenizer unicode61, BM25 built-in | HIGH |
| PDF | **pymupdf** (fitz) | Mucho más rápido y robusto que pypdf/pdfplumber para volumen 2TB; AGPL — uso interno OK | HIGH |
| PDF fallback | `pdfplumber` | Para tablas complejas donde pymupdf falla | MEDIUM |
| DOCX | `python-docx` | Estándar, estable | HIGH |
| XLSX/CSV | `openpyxl` (read-only mode) + stdlib `csv` | read-only mode crítico para archivos grandes | HIGH |
| Imágenes (metadatos) | `Pillow` + `exifread` | Solo metadatos en v0.1 | HIGH |
| Video/audio (metadatos) | `pymediainfo` o `ffprobe` via subprocess | Solo metadatos en v0.1; ffprobe ya está en el sistema | MEDIUM |
| Detección de tipo | `python-magic` (libmagic) | No confiar en extensión; necesario para 2TB heterogéneos | HIGH |
| Detección de secretos | `detect-secrets` (Yelp) + reglas propias | Plugins de entropía + regex; complementar con denylist de rutas (.env, *.key, id_rsa) | HIGH |
### Embeddings (intercambiables vía port)
| Proveedor | Cliente | Nota |
|---|---|---|
| OpenAI | `openai` SDK | `text-embedding-3-small` — mejor costo/calidad para arranque |
| Voyage | `voyageai` | Mejor calidad para retrieval puro |
| Google | `google-genai` | Alternativa económica |
### Daemon + IPC
| Componente | Elección | Rationale | Confianza |
|---|---|---|---|
| IPC | Unix socket + JSON-RPC 2.0 | stdlib `socket` + `json`; spec JSON-RPC es trivial de implementar (~100 líneas); evita dependencia de framework HTTP | HIGH |
| Event loop | `asyncio` (stdlib) | `asyncio.start_unix_server` hace el 90% del trabajo | HIGH |
| Supervisión | systemd user unit (`~/.config/systemd/user/wyss.service`) | Ya es el patrón del sistema del owner; restart automático, journal logging | HIGH |
| Scheduler | `APScheduler` 4.x (o 3.x estable si 4 sigue beta) | Cron triggers + persistencia de jobs; verificar estado de la 4.x al llegar a Fase 4 | MEDIUM |
### CLI
| Componente | Elección | Rationale | Confianza |
|---|---|---|---|
| Framework | **Typer** | Type-hints driven, subcomandos limpios (`wyss index`, `wyss search`, `wyss ask`), built sobre Click | HIGH |
| Output | **Rich** | Tablas de resultados, progreso de indexación, paneles de confirmación B/C | HIGH |
### Config y validación
| Componente | Elección | Rationale | Confianza |
|---|---|---|---|
| Formato | TOML (`tomllib` stdlib para leer) | Decisión tomada; stdlib desde 3.11 | HIGH |
| Validación | **Pydantic v2** | Validar config al boot (fail-fast), modelos de dominio serializables, `pydantic-settings` para .env | HIGH |
### Testing
| Componente | Elección | Rationale |
|---|---|---|
| Runner | `pytest` | Decisión tomada |
| Async | `pytest-asyncio` | Tests del daemon/orquestador |
| Fixtures FS | `tmp_path` built-in + factories propias | No usar pyfakefs — tests de integración reales sobre tmp |
| Mocks de API | `respx` (si httpx) o fixtures con adapters fake | El patrón hexagonal hace esto natural: inyectar `FakeEmbeddingProvider` |
| Lint/format | `ruff` (lint + format) | Único tool, reemplaza black+isort+flake8 |
| Types | `mypy` strict en `core/` | El núcleo hexagonal debe pasar strict; adapters pueden relajar |
## Validated Decisions
- **ChromaDB embebido** ✓ — correcto para single-owner local. Colección por BC = aislamiento natural para PermissionManager.
- **SQLite FTS5** ✓ — cero fricción, BM25 nativo. Híbrido FTS5+vector con fusión RRF (Reciprocal Rank Fusion) es el patrón estándar.
- **TOML** ✓ — `tomllib` stdlib.
- **uv** ✓ — estándar 2025.
- **Unix socket + JSON-RPC** ✓ — correcto. Evitar FastAPI/HTTP para IPC local: superficie innecesaria.
- **API-first embeddings** ✓ — correcto para v0.1 sin GPU dedicada al proyecto.
## Recommended Changes
## Missing Pieces
- **`python-magic`** — detección de tipo real de archivo (no extensión). Crítico para 2TB heterogéneos.
- **`detect-secrets`** — base del filtro de secretos del pipeline (regla inviolable #8).
- **`watchdog`** — re-indexación incremental por eventos FS (opcional Fase 1, mencionado en prompt).
- **`tenacity`** — retry con backoff para llamadas a APIs de embeddings/LLM en el gateway.
- **`structlog`** — logging estructurado; el AuditLogger escribe a SQLite pero el log operativo necesita estructura.
## What NOT to Use
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

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Generated by GSD from questionnaire. Run `/gsd-profile-user --refresh` to update.

| Dimension | Rating | Confidence |
|-----------|--------|------------|
| Communication | detailed-structured | MEDIUM |
| Decisions | delegator | MEDIUM |
| Explanations | concise | MEDIUM |
| Debugging | diagnostic | MEDIUM |
| UX Philosophy | design-conscious | MEDIUM |
| Vendor Choices | pragmatic-fast | MEDIUM |
| Frustrations | verbosity | MEDIUM |
| Learning | guided | MEDIUM |

**Directives:**
- **Communication:** Match this developer's structured communication: use headers for sections, numbered lists for steps, and acknowledge provided context before responding.
- **Decisions:** Make clear recommendations with confidence. Explain your reasoning briefly, but own the suggestion.
- **Explanations:** Pair code with a brief explanation (1-2 sentences) of the approach. Keep prose minimal.
- **Debugging:** Diagnose the root cause before presenting the fix. Explain what went wrong and why the fix addresses it.
- **UX Philosophy:** Invest in UX quality: thoughtful spacing, smooth transitions, responsive layouts. Treat design as a first-class concern.
- **Vendor Choices:** Suggest libraries quickly based on popularity and reliability. Don't over-analyze choices for non-critical dependencies.
- **Frustrations:** Be concise. Lead with code, follow with brief explanation only if needed. Avoid restating the problem or unnecessary context.
- **Learning:** Explain concepts in context of the developer's codebase. Use their actual code as examples when teaching.
<!-- GSD:profile-end -->

## Orchestration Runbook (directiva del owner — 2026-06-12)

Escrito por Fable 5. Cualquier modelo orquestador (sonnet incluido) DEBE seguir esto literalmente.
El owner pidió piloto automático: tomar las decisiones recomendadas, consultar solo ante cambios
de arquitectura, seguridad o scope ("algo serio serio").

### División de modelos (no negociable)

| Trabajo | Quién |
|---|---|
| Planes de fase, mejoras, fixes, juicio de calidad, resolución de desvíos | Fable 5 (escalar si no estás corriendo en Fable) |
| Escritura de código pesada (ejecución de planes) | Codex via `codex-gsd-exec` (reasoning high) |
| Code review (gate de fin de fase) | Gemini via `~/.local/bin/gemini-review` (lee API key de opencode.jsonc en runtime) |
| Cierre mecánico por plan + verifier de fase | Sonnet (subagente) |
| Security audit (`/gsd-secure-phase`) | Fable 5 (Mythos no disponible; opus solo como fallback) |

### Loop de ejecución de fase (cross-AI)

Por cada plan, en orden de waves, SECUENCIAL (worktree isolation falla con cwd=~; no usar `isolation`):

1. **Prompt**: header estándar (proyecto, root absoluto `/mnt/hdd/Data/10_Workspace/projects/wyss`,
   reglas, formato SUMMARY con frontmatter `plan:`/`status:`, marcador `=== PLAN FOLLOWS ===`) + PLAN.md completo.
2. **Ejecutar**: `cd <root> && timeout 3600s codex-gsd-exec < prompt > summary 2> err.log` en background.
   Codex a veces commitea él mismo (bien formateado) y a veces deja todo untracked — ambos OK.
3. **Cierre (subagente sonnet)**: cadena verde `uv run pytest && uv run mypy && uv run ruff check src tests
   && uv run lint-imports` (si falla: NO commitear, escalar a Fable) → commits atómicos por task si Codex
   no commiteó → SUMMARY.md al dir de fase → `gsd-sdk query roadmap.update-plan-progress 03 <plan> complete`
   → commit docs. Trailer siempre: `Co-Authored-By:` del modelo orquestador.
4. Heartbeat `[checkpoint] phase X wave N/M plan <id> <status> (P/Q plans done)` entre pasos.

Fin de fase: review Gemini (diff completo de la fase → findings → REVIEW.md; fixes los decide Fable) →
verifier sonnet (`gsd-verifier`) → `gsd-sdk query phase.complete` → push.

### Gotchas verificados (no redescubrir)

- `~/Data` → `/mnt/hdd/Data` (NTFS): verificar `mountpoint /mnt/hdd` antes de escribir; `core.filemode false` ya seteado.
- `uv sync` warning de hardlink (cache SSD→NTFS): no bloqueante. Codex sandbox: `UV_CACHE_DIR` ro → usa /tmp solo.
- gsd-sdk: `state.record-metric/record-session/update-progress/add-decision` devuelven `updated:false` (ignorar);
  `state.advance-plan` cuenta mal "Plan: N of M" (corregir a mano); `state.patch`, `roadmap.update-plan-progress`,
  `requirements.mark-complete`, `phase.complete` funcionan.
- Spawnear agentes GSD SIEMPRE con `model=` explícito — sin él heredan el modelo del orquestador (caro).
- Cross-AI: aunque ningún plan tenga `cross_ai: true`, TODOS los planes van por Codex (directiva owner).
