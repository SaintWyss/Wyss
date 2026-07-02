# Wyss — System Map

> Auditoría C-Level, 2026-07-02. Fuente: inspección directa del repo en commit `fef3ab8` (main, sincronizado con origin).
> Cadena de verificación corrida en vivo: **424 passed / 6 skipped · mypy 0 issues · ruff limpio · import-linter 2/2 contratos kept**.

## 1. Qué es esto (forma real del producto)

Sistema operativo personal multi-agente en Python 3.12, local-first, CLI-first. Un solo entrypoint
instalable (`wyss = bootstrap.cli:app`, pyproject `[project.scripts]`). Hoy el producto usable es:

- `wyss index` — ingesta de archivos (2 TB heterogéneos) a índice híbrido FTS5 + ChromaDB.
- `wyss search` / `wyss status` — búsqueda híbrida RRF con degradación.
- `wyss start` / `wyss ask` / `wyss confirm` — daemon asyncio sobre Unix socket JSON-RPC con bandeja de confirmaciones B/C.
- `wyss fin add-ingreso / add-gasto / ver` — ledger de finanzas determinístico (agente Pellegrini).
- `wyss audit` — consulta del audit trail.

**Lo que NO funciona todavía**: el path conversacional con LLM real (`ask` → orquestador LLM → plan).
El daemon usa un orquestador determinístico interno; el adapter Hermes (plan 05-05) está BLOQUEADO.

## 2. Estructura por capas (real, enforced)

```
src/
├── core/               NÚCLEO PURO — stdlib only (contrato import-linter "core es puro: KEPT")
│   ├── domain/         frozen dataclasses: Task, Plan, Action, RiskLevel, AuditEvent, Transaccion, errors…
│   ├── ports/          16 typing.Protocol + AgentBase ABC (README dice "14" — stale)
│   ├── policy/         CognitivePolicyEngine (engine.py) + BUILTIN_DENY Final no removible (builtin_deny.py)
│   └── orchestrator/   intent.py — clasificación de intención PURA (no confundir con src/orchestrator/)
├── orchestrator/       daemon asyncio (daemon.py: DaemonServer, Unix socket JSON-RPC),
│                       dispatcher fail-closed, PendingStore SQLite, plan_renderer B/C, ttl_reaper
├── agents/             ConfiguredAgent (ciclo _run, anti-injection), AgentRegistry config-driven,
│                       AgentMemory, SQLitePermissionStore, ScopedRetrieval, pellegrini.py, ledger_retrieval.py
├── knowledge/          pipeline de ingesta (scanner→extractors→secret_filter→chunker→FTS5+Chroma),
│                       retrieval híbrido RRF, state_store incremental, extractors/ (9 plugins)
├── gateway/            gateway.py (fail-closed), cost.py (budget gate per-agente), minimizer, router,
│                       secrets_patterns, traces (0600/90d), providers/ (anthropic, litellm, ollama, fakes)
├── execution/          executor.py (PlanExecutor ABORT/RETRY/ESCALATE), filesystem.py (2da muralla + verify),
│                       shell.py + git.py (allowlist argv, jamás shell=True), journal.py (UndoJournal WAL)
├── audit/              SqliteAuditLogger append-only, DB separada (data/audit.db)
├── ledger/             Transaccion + SqliteLedgerStore (WAL, agregaciones SQL deterministas)
└── bootstrap/          composition root: cli.py (Typer, 35.6K), config.py (Pydantic→frozen, fail-fast),
                        gateway.py (armado del gateway)
```

Dirección de dependencias **verificada por import-linter** (pyproject `[tool.importlinter]`):
1. `core` no importa nada del sistema ni pydantic (contrato "forbidden").
2. Las 7 capas (`orchestrator, agents, knowledge, gateway, execution, audit, ledger`) son independientes entre sí (contrato "independence"); solo importan de `core`.
3. `bootstrap` es el único lugar donde vive Pydantic y donde se cablea todo (DI manual, D-10).

## 3. Flujos

### Flujo de comando (acción sobre el entorno)
```
owner → wyss ask (CLI) → Unix socket JSON-RPC → DaemonServer (orchestrator/daemon.py)
  → dispatcher.dispatch() [fail-closed]
  → CognitivePolicyEngine.evaluate(Plan) → PolicyDecision {A|B|C|D}
      A → ejecución directa · B/C → PendingStore + plan_renderer + wyss confirm · D → rechazo absoluto
  → PlanExecutor (execution/executor.py) → adapter (FileSystem/Shell/Git)
      · adapter re-verifica riesgo ANTES de ejecutar ("segunda muralla", D-68)
      · toda mutación → UndoJournal (inverse op) + verify posterior (conteos/hashes)
  → SqliteAuditLogger (todo el camino queda auditado)
```

### Flujo de conocimiento
```
wyss index → scanner (python-magic, no extensión) → ExtractorRegistry (9 extractores plugin)
  → SecretFilter 3 capas fail-closed (chunk con secreto NUNCA entra al índice, KNOW-07)
  → TokenChunker → FTS5 (external content, BM25) + ChromaDB (colección por BC)
  → StateStore (data/index.db, WAL, incremental/reanudable)
wyss search → HybridRetrieval → fusión RRF + degradación D-44 → Rich/JSON
```

### Flujo AI/modelos
```
agente → gateway.gateway (fail-closed) → CostTracker.veta PRE-llamada (budget per-agente desde [[agents]].budget_usd)
  → ContextMinimizer (contexto mínimo hacia afuera) + secrets_patterns (SecretDetected sin exponer valor)
  → router por tier → providers/{anthropic|litellm|ollama} (httpx directo, sin SDK) → traces.db (0600, 90 días)
Agentes: AgentRegistry lee [[agents]] de config.toml → ConfiguredAgent (cero código por agente nuevo, D-73)
  → ScopedRetrieval (permisos estructurales pre-retrieval) → contenido marcado untrusted (anti-injection, POL-07)
```

### Flujo de configuración
```
config/config.toml (TOML, sin secretos) + config/.env (gitignored; HOY NO EXISTE)
  → bootstrap/config.py: Pydantic v2 valida al boot (fail-fast, extra=forbid en agentes)
  → frontera única: entrega frozen dataclasses al núcleo (Pydantic jamás entra a core/)
  → la config solo puede AGREGAR reglas a la denylist D, jamás quitarlas (BUILTIN_DENY Final)
```

## 4. Archivos importantes

| Archivo | Rol |
|---|---|
| `src/core/policy/builtin_deny.py` | Denylist nivel D en código, `Final`, no vaciable por config |
| `src/core/policy/engine.py` | Plan → PolicyDecision, agregados anti-bypass nivel-plan |
| `src/execution/filesystem.py` | Adapter más grande (18.7K): 2da muralla + verify por tipo + send2trash/journal |
| `src/gateway/cost.py` | Gate de presupuesto per-agente (protegido D-85: no tocar sin decisión) |
| `src/bootstrap/cli.py` | Composition root + TODOS los comandos (35.6K — ver hallazgos) |
| `.planning/ROADMAP.md`, `STATE.md` | Estado GSD real (fuente de verdad de progreso, no el README) |
| `pyproject.toml` | Contratos import-linter + mypy strict src+tests + gates |

## 5. Archivos muertos / sospechosos

| Ítem | Evidencia | Diagnóstico |
|---|---|---|
| deps `fastmcp>=2.14`, `mcp>=1.27` | 0 imports en src/tests/scripts (grep) | **Muertas** — huérfanas del plan 05-05 bloqueado |
| `scripts/` | solo `.gitkeep`; README lo describe como "utilidades de desarrollo y despliegue" | Vacío; doc miente |
| `data/trash_journal_test.db`, `data/trash_test_sentinel.txt` | residuos de `tests/execution/test_wave0_ntfs.py` y `test_filesystem.py:404` (opt-in `WYSS_TEST_NTFS=1`) | Deliberado (pitfall sticky-bit /tmp) pero **sin cleanup** — basura acumulándose en data/ real |
| `data/index.db` 57 MB | gitignored, runtime | OK (índice real del owner) |
| `.import_linter_cache/` | en raíz, no listado en .gitignore | menor: agregar a .gitignore |
| `config/.env` | no existe; `.env.example` sí | Bloquea providers reales (advisory sin calibrar) |

## 6. Estado del producto (qué es real, qué es demo)

| Capacidad | Estado |
|---|---|
| Índice + búsqueda híbrida 2 TB | **REAL** (fases 3-4 cerradas; index.db 57 MB poblado) |
| Policy A-D + auditoría + undo + allowlists | **REAL y testeado** (424 tests; golden tests de política) |
| Ledger finanzas + CLI `fin` | **REAL** (checkpoint owner aprobado con evidencia en vivo) |
| Agente Pellegrini conversacional (asesoría con prosa LLM) | **PARCIAL/FAKE**: E2E pasa con FakeOrchestrator + rúbrica determinística; prosa real jamás calibrada (LiteLLM down, sin .env) |
| Daemon `ask` → orquestador LLM real | **NO CABLEADO** (05-05 BLOCKED: Hermes sin imagen publicada; requiere docker build + UFW + disabled_toolsets) |
| Multi-agente + rutinas (fase 9), Modo Equipo (fase 10) | **NO EMPEZADAS** |

## 7. Unknowns / requieren confirmación humana

1. ¿Hermes sigue siendo el plan para el orquestador conversacional, o se acepta un adapter API (LiteLLM/Anthropic) sobre `OrchestratorPort`? (El gateway ya tiene provider LiteLLM — `src/gateway/providers/litellm.py`.)
2. ¿LiteLLM :4000 se re-levanta en esta máquina (quedó down por perf-tuning en Santiago-PC; este repo corre también en la Acer)?
3. ¿Las 4 BC (Personal, RAGcorp, Beca #1, Beca #2) existen como colecciones reales o solo Personal está poblada?
4. ¿v0.1 "release" significa uso propio del owner en ambas PCs, o algo distribuible (fase 6 del README viejo: "Producto Replicable")?
