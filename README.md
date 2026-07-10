# Wyss

> El empleado que siempre necesitaste y nunca pudiste contratar.

Sistema de asistencia operativa multi-agente, humano primero.

**Autor:** Santiago Wyss  
**Estado:** v0.1.0 — loop ask→plan→política→confirmar→ejecutar→auditar verificado E2E con LLM real y smoke físico del bridge móvil aprobado (ver `docs/releases/WYSS_v0.1.0.md`)  
**Versión:** 0.1.0

**Uso diario:** ver `docs/OPERATOR.md` (arranque, teléfono, troubleshooting).

---

## Qué es Wyss

Wyss es una plataforma de asistencia operativa personal y empresarial basada en arquitectura multi-agente. Centraliza el conocimiento del owner, automatiza tareas operativas y coordina agentes especializados — todo con jerarquía estricta, política cognitiva y auditoría obligatoria.

No es un chatbot. No es un wrapper de IA. Es un operador con criterio.

## Arquitectura

```
OWNER
  └─► NÚCLEO (Orquestador · Planificador · Política Cognitiva)
        ├─► AGENTES ESPECIALIZADOS (instancias del modelo base)
        ├─► CAPA DE CONOCIMIENTO (BC indexadas · Retrieval Engine)
        ├─► GATEWAY DE MODELOS (contexto mínimo · control de costos)
        └─► CAPA DE EJECUCIÓN (adaptadores desacoplados)
```

## Niveles de acción

| Nivel | Tipo | Comportamiento |
|-------|------|----------------|
| A | Lectura / diagnóstico | Ejecución directa |
| B | Modificación normal | Confirmación simple del owner |
| C | Alto impacto | Confirmación fuerte del owner |
| D | Destructivo / inválido | Rechazo absoluto |

## Qué funciona hoy / qué falta

| Capacidad | Estado |
|---|---|
| Índice + búsqueda híbrida (FTS5 + vectores, fusión RRF) — `wyss index` / `wyss search` | **Funciona** (fases 3-4) |
| Política A-D + auditoría + undo journal + allowlists de ejecución | **Funciona y testeado** (fases 1, 6) |
| Daemon con bandeja de confirmaciones B/C — `wyss start` / `ask` / `confirm` | **Funciona** (fase 5) |
| Agentes config-driven + ledger de finanzas (Pellegrini) — `wyss fin` | **Funciona** (fases 7-8) |
| Deshacer lo aplicado — `wyss undo` (dry-run + confirmación por política, sin bypass) | **Funciona** (PR-09) |
| Lecturas del operador — `file.read/list/stat`, `git status/log/diff` (salidas capadas, secretos bloqueados) | **Funciona** (PR-11) |
| UI web + bridge móvil — `wyss web --lan --tls` (HTTPS self-signed, cookie 30 días, PWA instalable, voz) | **Funciona, smoke físico aprobado** (PR-10/14/15) |
| Conversación con LLM real (`[orchestrator] mode = "llm"`) | **Cableado, opt-in** — pendiente verificación manual con proveedor real |
| Multi-agente + rutinas (fase 9) · Modo Equipo (fase 10) | **No empezadas** |

El roadmap vigente (10 fases por build order técnico) vive en `.planning/ROADMAP.md`.
La auditoría C-Level 2026-07-02, la arquitectura objetivo y los planes de reparación viven en
`docs/audit/`, `docs/architecture/` y `docs/plans/`.

## Estructura del repositorio

```
wyss/
├── docs/                  Documentación: fundacional (00-18, histórica) + audit/ + architecture/ + plans/
├── src/
│   ├── core/              Núcleo hexagonal puro (stdlib only, mypy strict)
│   │   ├── domain/        Entidades frozen (Task, Plan, Action, RiskLevel, AuditEvent, Transaccion…)
│   │   ├── ports/         Los 17 contratos (16 typing.Protocol + AgentBase ABC) — D-11
│   │   ├── policy/        CognitivePolicyEngine puro + denylist built-in no removible
│   │   └── orchestrator/  Modelo puro de intención (IntentCategory / IntentClassification)
│   ├── orchestrator/      Daemon asyncio (Unix socket JSON-RPC), dispatcher fail-closed,
│   │                      PendingStore B/C, LLMOrchestrator (adapter del port vía gateway)
│   ├── agents/            ConfiguredAgent config-driven, registry, permisos, memoria, Pellegrini
│   ├── knowledge/         Pipeline de ingesta (extractors/ plugin), índice FTS5+Chroma, retrieval RRF
│   ├── gateway/           Router por tiers, Context Minimizer, Cost Tracker, providers/ (anthropic,
│   │                      litellm, ollama), traces
│   ├── execution/         Adaptadores FileSystem/Shell/Git + PlanExecutor + UndoJournal
│   ├── audit/             Audit Logger (SQLite append-only, DB separada)
│   ├── ledger/            Dominio de finanzas: Transaccion + SqliteLedgerStore (agregaciones SQL)
│   └── bootstrap/         Composition root (DI manual) + CLI Typer + frontera Pydantic→dominio
├── tests/                 Pruebas espejando src/ por capa
├── config/                Configuración TOML (sin secretos) + .env.example
└── scripts/               Reservado (systemd unit y utilidades llegan con el release candidate)
```

Notas de capas:

- **`core/domain/`** — entidades de dominio como `frozen` dataclasses, stdlib only. Todo lo demás las importa; ellas no importan nada del sistema.
- **`core/ports/`** — los 17 contratos hexagonales (16 Protocols + la ABC `AgentBase`). Se definen y commitean antes que cualquier implementación (D-11); los módulos vecinos importan de aquí, nunca de las impls.
- **`core/policy/`** — el `CognitivePolicyEngine` puro (`Plan -> PolicyDecision`). La denylist de nivel D vive aquí en código como invariante `Final`; la config solo puede AGREGAR reglas, jamás quitarlas.
- **`bootstrap/`** — composition root con DI manual (D-10) y la única frontera donde vive Pydantic: valida `config.toml` al boot (fail-fast) y entrega frozen dataclasses al núcleo. Pydantic nunca entra a `core/`.
- Ojo con el nombre repetido: `core/orchestrator/` es el modelo **puro** de intención; `orchestrator/` (top-level) es la capa del **daemon**. Son capas distintas del hexágono.

### Verificación

El proyecto se instala con `uv` (gestor de deps + venv) y usa paquetes top-level genéricos
(`core`, `audit`, `bootstrap`…) bajo un venv dedicado — tradeoff aceptado en D-01 a cambio
de imports flat (`from core.ports import ...`). La cadena de verificación completa, que todo
plan posterior debe dejar verde, es:

```bash
uv sync                                 # instala deps + proyecto editable
uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports
```

`mypy` corre en modo strict sobre `src` y `tests`; `import-linter` (`lint-imports`) verifica
los contratos hexagonales (núcleo puro stdlib-only, capas independientes entre sí).
Esta cadena corre automáticamente en CI (GitHub Actions) en cada push a `main` y en cada PR.

## Principios

1. **Jerarquía estricta:** owner → orquestador → agentes → herramientas.
2. **Juicio antes que ejecución:** toda acción pasa por la política cognitiva.
3. **Contexto mínimo hacia afuera:** los modelos externos reciben solo lo necesario.
4. **Auditoría transversal:** nada relevante ocurre sin registro.
5. **Núcleo replicable:** la lógica es genérica; la personalización vive en configuración.

## Herencia de Jarvis

Wyss absorbe de Jarvis PC v0.1:
- Política Cognitiva (evaluación de finalidad, impacto, reversibilidad, riesgo).
- Niveles de acción A–D con confirmación y rechazo absoluto.
- Contexto mínimo hacia modelos externos.
- Auditoría obligatoria y adaptadores desacoplados.

---

*Filosofía rectora: humano primero, IA cuando corresponde.*
