# Phase 1: Fundaciones - Research

**Researched:** 2026-06-10
**Domain:** Núcleo hexagonal Python 3.12+ — dominio puro, Protocols, política cognitiva determinística, auditoría SQLite, config TOML+Pydantic
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Fuente:** el owner entregó la spec completa en `docs/18-prompt-implementacion.md` en lugar de discusión por áreas. Las decisiones de abajo se extraen de ese documento; es la referencia canónica ante cualquier duda.

#### Estructura de paquete
- **D-01:** Mantener el layout del prompt: `src/core/ports/` + `src/core/` (lógica pura) + módulos por capa (`orchestrator/`, `agents/`, `knowledge/`, `gateway/`, `execution/`, `audit/`). Los stubs existentes se conservan y se rellenan — NO se reestructura a un `adapters/` top-level. Las implementaciones concretas de ports viven dentro de su módulo de capa.
- **D-02:** Carpetas nuevas se documentan en el README.

#### Política cognitiva (núcleo de la fase)
- **D-03:** Semántica de niveles exacta del prompt: A ejecuta directo · B muestra plan y pide `[s/N]` · C muestra plan con advertencia y exige escribir `"CONFIRMAR"` · D rechaza siempre, sin path de ejecución, rechazo auditado.
- **D-04:** Clasificación D determinística por denylist (decisión de research ya commiteada en ROADMAP/STATE): el LLM puede subir el riesgo estimado, nunca bajarlo.
- **D-05:** La política evalúa el plan completo + agregados — sin bypass por composición (POL-05).

#### Auditoría
- **D-06:** Audit store en **SQLite separado de los datos de usuario** (índice/BC van en otra DB). Decisión fija del prompt.
- **D-07:** Registro mínimo por evento: actor, instrucción, plan, decisión de política, confirmación, acciones, resultado, costo.
- **D-08:** AuditLogger se inyecta por constructor a todo componente posterior — regla #1: si no está auditado, no está terminado.

#### Config y DI
- **D-09:** `config.toml` (TOML) para configuración; `.env` solo para secretos/keys de proveedores. Validación Pydantic al boot, fail-fast con error legible.
- **D-10:** DI por constructores explícitos — sin framework DI. Composition root manual.
- **D-11:** Interfaces primero: los Protocols de `core/ports/` se definen y commitean antes que cualquier implementación. Módulos vecinos importan de `core/ports/`, nunca de implementaciones.

#### Tests
- **D-12:** Tests de seguridad explícitos obligatorios en esta fase: acción nivel D → rechazada y nunca ejecutada; plan compuesto que agrega a D → clasificado D. Foco en bordes críticos, no coverage.
- **D-13:** mypy strict en `core/`; `ruff` lint+format; pytest.

### Claude's Discretion
- **Contenido inicial de la denylist D** — el owner no enumeró operaciones. Arrancar conservador: borrado masivo/recursivo fuera de papelera, modificación de config/permisos/presupuesto de Wyss por un agente (regla #6), exfiltración de secretos, escritura en `~/.ssh`/system files, `git push --force` a main, formateo/particionado. Ampliable por config (la denylist es datos, no código).
- **Umbrales de agregación A→B→C** (cuántos archivos/qué directorios escalan nivel) — proponer defaults sensatos, configurables en `config.toml`.
- **Esquema exacto de tablas SQLite de auditoría** — respetando D-07 como campos mínimos.

### Deferred Ideas (OUT OF SCOPE)
- **Conflicto pdfplumber (prompt) vs pymupdf (research)** — decidir en Fase 3 (Pipeline de Ingesta) con benchmark real sobre archivos del owner. No afecta Fundaciones.
- **Watchdog para re-indexación automática** — el prompt lo marca opcional; REQUIREMENTS lo tiene en v2. Fase 3 decide si entra.
- **`agents.toml` separado de `config.toml`** — detalle de Fase 7; el prompt lo menciona, registrarlo ahí.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| POL-01 | Todo plan pasa por la política cognitiva antes de ejecutarse | `CognitivePolicyEngine.evaluate(plan) -> PolicyDecision` como función pura; el contrato del sistema es que nada ejecuta sin un `PolicyDecision` con outcome ≠ REJECT (ver Architecture Patterns §3 y AgentBase belt-and-suspenders) |
| POL-02 | A ejecuta directo; B pide [s/N]; C exige "CONFIRMAR" | Enum `RiskLevel(IntEnum)` + `Outcome` + mapeo exhaustivo con `match`/`assert_never` (Patterns §3); semántica de docs/13 §2 codificada como `base_levels` por action_type |
| POL-03 | Nivel D se rechaza con explicación, auditado, sin path de ejecución | Denylist built-in en código (no removible por config) + `PolicyDecision(outcome=REJECT, matched_rules=...)`; el rechazo emite `AuditEvent` con prioridad; tests de ausencia (Validation Architecture) |
| POL-04 | Clasificación D determinística; el LLM solo puede subir riesgo | `Plan.estimated_risk` separado del nivel final: `final = max(deterministic, estimated)` — `IntEnum` hace el `max()` trivial y verificable por property test de monotonía |
| POL-05 | Evaluación del plan completo + agregados — sin bypass por composición | Agregados sobre el `Plan` entero: conteo de targets modificados, directorios distintos, directorios sensibles, conteo de deletes — umbrales configurables (Patterns §3.2) |
| AUD-01 | Registro: actor, instrucción, plan, decisión, confirmación, acciones, resultado, costo — en SQLite | Esquema `audit_events` con taxonomía de `event_type` que cubre los 8 campos D-07, correlación por `task_id`, WAL + synchronous=FULL, trigger append-only (Patterns §4) |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

Directivas accionables de `./CLAUDE.md` que el plan DEBE cumplir:

1. **Arquitectura hexagonal** — el núcleo no importa infraestructura directamente (verificable con import-linter, ver Patterns §6).
2. **Nivel D absoluto** — sin excepciones en ningún path de código.
3. **Contexto mínimo hacia afuera** — no aplica IO externo en esta fase (no hay llamadas a modelos).
4. **Auditoría transversal** — nada relevante sin registro; AuditLogger es la primera pieza después del dominio.
5. **API-first, sin servidor dedicado** — esta fase es 100% local, sin dependencias de red.
6. **Extensibilidad sin ruptura** — agregar extractor/proveedor/agente nunca modifica código existente (regla #9 del owner).
7. **What NOT to Use** (de STACK.md embebido en CLAUDE.md): LangChain/LlamaIndex, PyPDF2, Celery/Redis, FastAPI para IPC, python-daemon, SQLAlchemy ORM — el audit store usa `sqlite3` stdlib con SQL directo.
8. **Workflow GSD** — el trabajo se hace vía `/gsd-execute-phase`, no con edits directos.

## Summary

La Fase 1 construye el núcleo hexagonal puro: ~20 entidades de dominio como frozen dataclasses (stdlib only), los 14 contratos de `core/ports/` (13 `typing.Protocol` + 1 ABC `AgentBase`), el `CognitivePolicyEngine` como función pura `Plan -> PolicyDecision` con denylist determinística y agregación anti-bypass, el `SqliteAuditLogger` en DB separada con esquema append-only, y la carga de `config.toml` validada con Pydantic v2 (fail-fast al boot). No hay IO de negocio, ni LLM, ni daemon: todo lo que se escribe acá es testeable sin mocks de red.

Los tres riesgos reales de la fase no son de librerías sino de diseño: (1) el layout flat multi-paquete bajo `src/` que fija D-01 requiere configuración explícita de hatchling/mypy/import-linter (no es el default de ningún tool); (2) los Protocols no se verifican solos — sin un módulo de "conformance assignments" tipado, una implementación que no cumple el contrato pasa silenciosa hasta runtime; (3) la denylist debe ser datos *aditivos*: los invariantes D viven en código como tupla inmutable y la config solo puede agregar reglas, nunca quitarlas — si la config pudiera vaciar la denylist, la regla #2 del owner sería violable editando un TOML.

Stack mínimo y verificado: `pydantic 2.13.4` como única dependencia runtime; `pytest 9`, `mypy 2.1`, `ruff 0.15`, `import-linter 2.11` como dev deps. Todo pasa slopcheck `[OK]`. El entorno local (Python 3.14.5, uv 0.11.18, SQLite 3.53.2 con FTS5) cumple sobradamente. Un hallazgo de entorno importante: el repo vive en NTFS (fuseblk) — WAL de SQLite funciona pero debe verificarse con smoke test al boot (ver Pitfall 6).

**Primary recommendation:** dominio frozen + 14 ports primero (commit propio, D-11), después AuditLogger, después PolicyEngine con golden plans, después config+bootstrap — exactamente el build order 0→4 de research/ARCHITECTURE.md.

## Architectural Responsibility Map

Esta fase no tiene tiers web; el mapa usa las capas hexagonales del proyecto.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Entidades de dominio (Task, Plan, Action, RiskLevel, AuditEvent…) | `core/domain` (dominio) | — | Stdlib only, frozen; todo lo demás las importa |
| 14 ports (Protocols + AgentBase) | `core/ports` (dominio) | — | Contratos puros; D-11 exige commitearlos antes que cualquier impl |
| CognitivePolicyEngine | `core/policy` (dominio) | — | Función pura sin IO — el módulo más testeado del sistema |
| Reglas de política (denylist, umbrales) | `core/policy` (invariantes en código) | `bootstrap/config` (reglas adicionales por TOML) | Config solo AGREGA reglas; invariantes D no removibles |
| AuditLogger (SQLite) | `src/audit/` (adapter de capa) | `core/ports/audit.py` (contrato) | Implementación concreta vive en su módulo de capa per D-01 |
| Carga y validación de config | `src/bootstrap/` (composition root) | `core/domain/config.py` (dataclass de destino) | Pydantic NO entra a `core/`; bootstrap convierte a frozen dataclass |
| Composition root (DI manual) | `src/bootstrap/` | — | Único módulo que importa todo (D-10) |
| AgentBase (template method) | `core/ports/agent.py` | — | ABC puro (solo domain + ports); audit/D-check no salteables |

**Nota:** `src/bootstrap/` es carpeta nueva → documentar en README (D-02).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python (CPython) | 3.14.5 local, `requires-python = ">=3.12"` | Runtime | Fija por owner spec; 3.14.5 ya instalado [VERIFIED: python3 --version] |
| pydantic | 2.13.4 | Validación de config al boot | Decisión de STACK.md; 2.12+ soporta Python 3.14 [VERIFIED: npm-equivalent PyPI + pydantic.dev release notes] |
| uv | 0.11.18 | Gestor de deps + venv | Fija por owner spec; instalado [VERIFIED: uv --version] |
| hatchling | latest (uv default) | Build backend | Default de `uv init --package`; soporta multi-package src layout [CITED: hatch.pypa.io/latest/config/build/#packages] |

### Supporting (dev)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | 9.0.3 | Test runner | Decisión D-13 [VERIFIED: PyPI] |
| mypy | 2.1.0 | Types, strict en core | D-13; ver State of the Art — mypy 2.x cambió defaults [VERIFIED: PyPI + mypy.readthedocs.io] |
| ruff | 0.15.16 | Lint + format | D-13 [VERIFIED: PyPI] |
| import-linter | 2.11 | Enforcement de capas hexagonales | Verifica D-11 ("vecinos importan de core/ports, nunca de impls") en CI [VERIFIED: PyPI + slopcheck OK] |
| hypothesis | 6.155.2 | Property test de monotonía de la política (opcional) | Solo si el planner incluye el property test de POL-04/05; los golden plans no lo requieren [VERIFIED: PyPI] |

**Stdlib que hace trabajo pesado (cero deps):** `tomllib` (parse TOML), `sqlite3` (audit store), `dataclasses`, `enum`, `typing.Protocol`, `contextlib`, `fnmatch` (matching de denylist), `uuid`, `datetime` (con `timezone.utc`).

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tomllib + `model_validate` | pydantic-settings (`TomlConfigSettingsSource`) | pydantic-settings agrega merging de env vars que D-09 no quiere para config.toml; útil recién en Fase 2 para `.env` de proveedores. En Fase 1: tomllib manual = explícito, sin magia |
| import-linter | Test propio con AST scan | No hand-rollear: import-linter es el estándar, declara contratos en pyproject.toml y corre en CI con un comando |
| `IntEnum` para RiskLevel | `StrEnum` | StrEnum no ordena; "el LLM sube pero nunca baja" y los agregados necesitan `max()` — IntEnum lo da gratis. Serializar con `.name` |
| sqlite3 stdlib | SQLAlchemy | Prohibido por STACK.md/CLAUDE.md — SQL directo es más auditable para ~3 queries estables |

**Installation:**
```bash
cd /mnt/hdd/Data/10_Workspace/projects/wyss
uv add "pydantic>=2.13"
uv add --dev "pytest>=9" "mypy>=2.1" "ruff>=0.15" "import-linter>=2.11"
# hypothesis solo si se adopta el property test:
# uv add --dev "hypothesis>=6.155"
```

**Version verification:** todas las versiones confirmadas contra PyPI el 2026-06-10 con `pip index versions` (ver Package Legitimacy Audit).

## Package Legitimacy Audit

slopcheck 0.6.1 ejecutado el 2026-06-10 sobre PyPI (ecosistema correcto para fase Python).

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| pydantic | PyPI | ~9 yrs | masivo | github.com/pydantic/pydantic | [OK] | Approved |
| pytest | PyPI | ~15 yrs | masivo | github.com/pytest-dev/pytest | [OK] | Approved |
| mypy | PyPI | ~12 yrs | masivo | github.com/python/mypy | [OK] | Approved |
| ruff | PyPI | ~3.5 yrs | masivo | github.com/astral-sh/ruff | [OK] | Approved |
| import-linter | PyPI | ~7 yrs | alto | github.com/seddonym/import-linter (metadata PyPI no lo linkea — verificado manualmente que el proyecto es el conocido) | [OK] (nota: "no source repository linked") | Approved |
| hypothesis | PyPI | ~12 yrs | masivo | github.com/HypothesisWorks/hypothesis | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

Flujo principal de la fase (evaluación de un plan + auditoría):

```
config/config.toml ──tomllib──▶ [bootstrap/config.py: WyssConfigModel (Pydantic)]
                                       │ ValidationError → stderr legible + exit(1)  (fail-fast)
                                       ▼
                              WyssSettings (frozen dataclass, core/domain)
                                       │
                 ┌─────────────────────┼──────────────────────┐
                 ▼                     ▼                      ▼
        PolicyRules (frozen)   audit_db_path           (resto de settings)
                 │                     │
                 ▼                     ▼
   CognitivePolicyEngine      SqliteAuditLogger ──▶ data/audit.db (WAL, append-only)
   (core/policy, puro)        (src/audit, implementa AuditPort)
                 │                     ▲
   Plan ────────▶│ evaluate()          │ log(AuditEvent) / span()
                 ▼                     │
        PolicyDecision ────────────────┘  (toda decisión, incluida REJECT, se audita)
          │
          ├─ A → EXECUTE            (fases futuras)
          ├─ B → CONFIRM_SIMPLE     (fases futuras)
          ├─ C → CONFIRM_STRONG     (fases futuras)
          └─ D → REJECT — sin path de ejecución; AgentBase además raisea PolicyViolation
```

### Recommended Project Structure

Respeta D-01 (stubs conservados, sin `adapters/` top-level). Carpetas nuevas marcadas con (+):

```
src/
├── core/
│   ├── __init__.py            # existente (stub)
│   ├── domain/             (+)# entidades frozen, stdlib only
│   │   ├── __init__.py        # re-exporta el vocabulario público
│   │   ├── risk.py            # RiskLevel, Outcome
│   │   ├── plan.py            # Action, Plan
│   │   ├── policy.py          # PolicyDecision, DenyRule, PolicyRules
│   │   ├── audit.py           # AuditEvent, ActorType, AuditEventType, Span
│   │   ├── task.py            # Task, TaskStatus (mínimo viable para ports)
│   │   ├── knowledge.py       # SourceFile, ExtractedContent, Chunk, IndexEntry, Hit, Query, Vector (mínimos)
│   │   ├── gateway.py         # ModelRequest, ModelResponse, AgentModelRequest (mínimos)
│   │   ├── execution.py       # ToolResult, Verification (mínimos)
│   │   ├── security.py        # Subject, Permission (mínimos)
│   │   ├── agent.py           # AgentDefinition, Report (mínimos)
│   │   └── config.py          # WyssSettings (frozen) — destino de la validación Pydantic
│   ├── ports/              (+)# los 14 contratos — commit propio ANTES de impls (D-11)
│   │   ├── __init__.py        # re-exporta los 14
│   │   ├── audit.py           # AuditPort
│   │   ├── config.py          # ConfigStore
│   │   ├── knowledge.py       # Extractor, Chunker, EmbeddingProvider, FullTextIndex, VectorIndex, Retrieval
│   │   ├── security.py        # PermissionStore
│   │   ├── gateway.py         # ModelProvider, ModelGatewayPort
│   │   ├── execution.py       # Tool
│   │   ├── persistence.py     # TaskRepository
│   │   └── agent.py           # AgentBase (la única ABC — template method)
│   └── policy/             (+)# CognitivePolicyEngine (puro)
│       ├── __init__.py
│       ├── engine.py
│       └── builtin_deny.py    # invariantes D en código — NO removibles por config
├── audit/
│   ├── __init__.py            # existente (stub)
│   ├── schema.py           (+)# DDL + PRAGMAs
│   └── sqlite_logger.py    (+)# SqliteAuditLogger (implementa AuditPort)
├── bootstrap/              (+)# composition root + frontera Pydantic — documentar en README (D-02)
│   ├── __init__.py
│   ├── config.py              # WyssConfigModel (Pydantic) + load_settings() → WyssSettings
│   └── wiring.py              # build_*() — crece con las fases
├── orchestrator/ agents/ knowledge/ gateway/ execution/   # stubs existentes, intactos esta fase
tests/
├── conftest.py             (+)
├── domain/test_entities.py (+)
├── ports/test_conformance.py (+)
├── policy/
│   ├── golden/             (+)# *.toml — planes dorados
│   ├── test_golden_plans.py(+)
│   └── test_aggregation.py (+)# bypass por composición (D-12)
├── audit/test_sqlite_logger.py (+)
└── config/test_load_settings.py (+)
config/
├── config.example.toml     (+)# reemplaza config.example.yaml (CONTEXT: obsoleto)
└── .env.example               # se mantiene
pyproject.toml              (+)
```

**Acción requerida sobre `src/__init__.py`:** eliminarlo. Es artefacto del init original que convierte a `src` en paquete y rompe el esquema de imports flat (`from core.ports import ...`). No forma parte del árbol del owner en docs/18 (que muestra `src/` como contenedor, no como paquete). CONTEXT.md lista como stubs a conservar solo los `__init__.py` de los 7 módulos de capa.

### Pattern 1: pyproject.toml para layout flat multi-paquete

**What:** D-01 fija paquetes top-level genéricos (`core`, `audit`, …) bajo `src/`. Ningún tool lo asume por default — hay que configurarlo explícito en hatchling, mypy y pytest.

```toml
# Source: hatch.pypa.io build config + mypy.readthedocs.io config_file + verificado contra layout local
[project]
name = "wyss"
version = "0.1.0"
description = "Asistente operativo personal multi-agente — humano primero"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.13"]

[dependency-groups]
dev = ["pytest>=9", "mypy>=2.1", "ruff>=0.15", "import-linter>=2.11"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = [
  "src/core", "src/orchestrator", "src/agents", "src/knowledge",
  "src/gateway", "src/execution", "src/audit", "src/bootstrap",
]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.mypy]
python_version = "3.12"
mypy_path = "src"
strict = true
files = ["src", "tests"]

[tool.ruff]
target-version = "py312"
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]
```

`uv sync` + `uv pip install -e .` (o `uv run`, que instala el proyecto editable) hacen que `import core`, `import audit` funcionen en tests y en import-linter. [VERIFIED: hatchling docs — `packages` acepta múltiples rutas y el nombre importable es el basename]

**Tradeoff conocido (aceptado por D-01):** nombres top-level genéricos (`core`, `agents`, `audit`) pueden colisionar con paquetes de PyPI instalados en el mismo venv. Mitigación: el venv del proyecto es dedicado y las deps son mínimas; documentar en README.

### Pattern 2: Protocols para ports, una sola ABC

**What:** 13 ports como `typing.Protocol` (structural typing — los adapters no heredan nada de core) + `AgentBase` como ABC con template method (audit y rechazo D no salteables).

**Decisiones de firma (cerradas en research/ARCHITECTURE.md §Interface Contracts — el planner las copia, no las rediseña):**

| # | Port | Archivo | Sync/Async | Nota |
|---|------|---------|-----------|------|
| 1 | `AuditPort` | ports/audit.py | sync | `log()` + `span()` → `AbstractContextManager[Span]` |
| 2 | `ConfigStore` | ports/config.py | sync | retorna `WyssSettings` (dataclass de dominio, NO el modelo Pydantic) |
| 3 | `Extractor` | ports/knowledge.py | sync | `media_types` como `@property` (ver Pitfall 4) |
| 4 | `Chunker` | ports/knowledge.py | sync | |
| 5 | `EmbeddingProvider` | ports/knowledge.py | **async** | cruza red |
| 6 | `FullTextIndex` | ports/knowledge.py | sync | SQLite local |
| 7 | `VectorIndex` | ports/knowledge.py | sync | `kb_ids` es parámetro del port — el adapter no puede "olvidar" filtrar |
| 8 | `Retrieval` | ports/knowledge.py | **async** | fan-out paralelo |
| 9 | `PermissionStore` | ports/security.py | sync | persistencia; la lógica de reglas vive en core |
| 10 | `ModelProvider` | ports/gateway.py | **async** | |
| 11 | `ModelGatewayPort` | ports/gateway.py | **async** | lo único que ven los agentes |
| 12 | `Tool` | ports/execution.py | **async** execute/verify | `max_risk: RiskLevel` declarado por el adapter; `describe()` sync |
| 13 | `TaskRepository` | ports/persistence.py | sync | |
| 14 | `AgentBase` (ABC) | ports/agent.py | — | template method `execute()`; hook abstracto `_run()` |

**`runtime_checkable`: NO usarlo por default.** `isinstance` con Protocols solo chequea presencia de métodos, no firmas — da falsa confianza. La verificación real es mypy strict + el módulo de conformance (Pattern 5). [CITED: docs.python.org/3/library/typing.html#typing.runtime_checkable — "runtime check only verifies presence of methods"]

**Implicación de planificación:** definir los 14 ports obliga a definir ~20 tipos de dominio que sus firmas referencian (`Chunk`, `Hit`, `ModelRequest`, `ToolResult`, `Subject`, …). Se definen como frozen dataclasses *mínimas* (campos de docs/09 donde existen; mínimos donde no) — expandirlas después es aditivo, no breaking. mypy strict en `core/` no pasa si falta alguno.

### Pattern 3: CognitivePolicyEngine — denylist aditiva + agregados

**3.1 — Separación estimado/final (POL-04):** el `Plan` lleva `estimated_risk: RiskLevel | None` (lo que el LLM/planner cree); el nivel final lo decide solo el engine: `final = max(per_action, aggregate, estimated or A)`, y si hay hit de denylist → D incondicional. Con `IntEnum`, `max()` implementa "subir sí, bajar jamás" sin lógica especial.

**3.2 — Agregación anti-bypass (POL-05, D-05) — defaults propuestos (Claude's Discretion, configurables en `config.toml`):**

| Agregado | Umbral default | Efecto |
|----------|---------------|--------|
| Targets modificados distintos | > 10 | mínimo B |
| Targets modificados distintos | > 100 | mínimo C |
| Directorios distintos tocados por escritura | > 5 | mínimo C |
| Cualquier acción `file.delete` | ≥ 1 | mínimo C (docs/13: borrado es C) |
| Acciones `file.delete` | > 50 o `recursive=true` fuera de papelera | **D** (denylist agregada built-in) |
| Target bajo directorio sensible (write) | ≥ 1 | mínimo C |

Directorios sensibles default: `~/.ssh`, `/etc`, `/boot`, el data dir de Wyss, `**/.env*`, `**/*.key`, `**/id_rsa*`.

**3.3 — Denylist inicial (Claude's Discretion, conservadora):** built-ins en `core/policy/builtin_deny.py` como `Final[tuple[DenyRule, ...]]`:

| Rule id | Match |
|---------|-------|
| `mass-delete` | `file.delete` con `recursive=true` y `to_trash=false`, o conteo agregado > 50 |
| `wyss-self-modify` | cualquier write/delete con target bajo el config/data dir de Wyss (regla #6) |
| `audit-tamper` | write/delete sobre `data/audit.db*` o desactivación de auditoría |
| `secret-exfiltration` | `file.read`+envío externo o cualquier acción con target matching `**/.env*`, `**/*.key`, `**/id_rsa*`, `**/.ssh/**` hacia destino externo; write en `~/.ssh/**` |
| `system-files-write` | write/delete bajo `/etc/**`, `/boot/**`, `/usr/**` |
| `git-force-push-main` | `git.push` con `force=true` y branch `main|master` |
| `disk-format` | `shell.run` con comando matching `mkfs*`, `fdisk`, `parted`, `dd if=` |

**Regla estructural clave:** la config TOML solo puede **agregar** `[[policy.deny]]` — `PolicyRules.deny = BUILTIN_DENY + tuple(config_rules)`. No existe mecanismo para remover built-ins. Si la config pudiera vaciar la denylist, D dejaría de ser absoluto editando un archivo (violación de regla #2).

**3.4 — Action types fail-closed:** `Action.type` usa taxonomía con prefijo (`file.read`, `file.create`, `file.move`, `file.write`, `file.delete`, `shell.run`, `git.push`, `system.config`, `agent.admin`, …). El mapa `base_levels` (action_type → nivel) viene de config con defaults en código según docs/13 §2 (lecturas → A; mover/renombrar → B; borrar/sobrescribir/instalar → C). **Un action_type desconocido clasifica C, nunca A** — fail-closed.

**3.5 — Match exhaustivo:** `Outcome` → paso siguiente con `match` + `typing.assert_never` para que mypy detecte variantes nuevas (Pattern 7 de ARCHITECTURE.md).

### Pattern 4: SqliteAuditLogger — esquema y garantías

DB separada (`data/audit.db`) de datos de usuario (D-06). Esquema (Claude's Discretion, respeta D-07):

```sql
-- src/audit/schema.py
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;     -- audit: pérdida-en-crash inaceptable; FULL fsyncea cada commit
PRAGMA busy_timeout=5000;

CREATE TABLE IF NOT EXISTS audit_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id    TEXT NOT NULL UNIQUE,          -- uuid4 hex
  task_id     TEXT,                          -- correlación; reconstruye la traza completa
  actor_type  TEXT NOT NULL,                 -- owner|orchestrator|agent|worker|system
  actor_id    TEXT NOT NULL,
  event_type  TEXT NOT NULL,                 -- taxonomía cerrada (abajo)
  message     TEXT NOT NULL,
  payload     TEXT NOT NULL DEFAULT '{}',    -- JSON (plan serializado, decisión, costo…)
  created_at  TEXT NOT NULL                  -- ISO-8601 UTC
);
CREATE INDEX IF NOT EXISTS idx_audit_task ON audit_events(task_id);
CREATE INDEX IF NOT EXISTS idx_audit_type_time ON audit_events(event_type, created_at);

-- Append-only estructural: ni siquiera un bug puede reescribir historia
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
```

**Cobertura D-07 vía taxonomía de `event_type`** (enum `AuditEventType` en dominio): `command.received` (instrucción), `plan.created` (plan), `policy.decision` (decisión — los REJECT con prioridad en payload), `confirmation.requested` / `confirmation.answered` (confirmación), `action.started` / `action.completed` (acciones + verificación), `task.completed` / `task.failed` (resultado), `cost.recorded` (costo). Los 8 campos D-07 quedan cubiertos por eventos correlacionados por `task_id`, no por 8 columnas — esquema estable cuando los payloads evolucionen.

**API:** sync (`log()` rápido con fsync; el daemon de Fase 5 lo envuelve en `asyncio.to_thread` si hace falta). `span()` con `@contextlib.contextmanager`: loggea start, end con duración, y excepción automáticamente. Inyección por constructor a todo componente posterior (D-08) — los tests verifican la firma (Validation Architecture, criterio 4).

### Pattern 5: Conformance assignments — Protocols verificados por mypy

**What:** un Protocol no se verifica hasta que alguien lo usa. Módulo de tests donde cada implementación (real o fake) se asigna a una variable tipada con el port — si la firma no cumple, **mypy strict falla**, no un test en runtime.

```python
# tests/ports/test_conformance.py  (verificado por mypy, no solo por pytest)
from core.ports.audit import AuditPort
from audit.sqlite_logger import SqliteAuditLogger

def test_sqlite_logger_conforms(tmp_path: Path) -> None:
    logger: AuditPort = SqliteAuditLogger(tmp_path / "audit.db")  # mypy verifica el contrato
    assert logger is not None
```

Como `files = ["src", "tests"]` en mypy, el criterio de éxito 1 ("mypy strict pasa") cubre también la conformidad.

### Pattern 6: import-linter — la arquitectura hexagonal como contrato de CI

```toml
# pyproject.toml
[tool.importlinter]
root_packages = ["core", "orchestrator", "agents", "knowledge", "gateway", "execution", "audit", "bootstrap"]

[[tool.importlinter.contracts]]
name = "core es puro: stdlib only"
type = "forbidden"
source_modules = ["core"]
forbidden_modules = ["pydantic", "orchestrator", "agents", "knowledge", "gateway", "execution", "audit", "bootstrap"]

[[tool.importlinter.contracts]]
name = "las capas importan de core, nunca entre sí"
type = "independence"
modules = ["orchestrator", "agents", "knowledge", "gateway", "execution", "audit"]
```

`lint-imports` corre en CI junto a mypy/ruff/pytest. Esto convierte D-11 y la regla "core sin imports de infra" de convención a verificación automática. [VERIFIED: import-linter 2.11 PyPI; tipos de contrato `forbidden`/`independence` — import-linter.readthedocs.io]

### Anti-Patterns to Avoid
- **Pydantic en `core/`** — los modelos Pydantic viven en `bootstrap/`; core recibe frozen dataclasses. import-linter lo hace imposible de violar silenciosamente.
- **`runtime_checkable` + isinstance como "verificación"** — no chequea firmas; usar conformance assignments.
- **Denylist 100% en config** — los invariantes D van en código; config solo agrega.
- **Action type desconocido → A** — siempre fail-closed (C).
- **Evaluar pasos individuales del plan** — el engine recibe el `Plan` entero; no exponer API `evaluate_action()` pública que invite al bypass.
- **Crear `BelgranoAgent` u otras subclases de AgentBase ahora** — en v0.1 los agentes son configuración (`ConfiguredAgent` llega en Fase 7); la ABC se define, no se puebla.
- **Sobre-modelar entidades que esta fase no usa** — `Chunk`, `ModelRequest`, etc. se definen mínimas solo para que los ports tipen; Fases 2-4 las expanden.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parse de TOML | parser propio | `tomllib` (stdlib 3.11+) | Cero deps, spec completa |
| Validación de config con errores legibles | if/raise manual por campo | Pydantic v2 `model_validate` + `extra="forbid"` | Errores con `loc` por campo; typos en denylist detectados (fail-closed) |
| Enforcement de capas | test propio con AST/`sys.modules` | import-linter | Contratos declarativos en pyproject, mantenido, salida clara |
| Matching de patterns en denylist | regex engine propio o mini-DSL | `fnmatch.fnmatch` sobre paths normalizados | Stdlib, determinístico; un DSL de reglas es scope creep |
| Lint + format + import sort | black+isort+flake8 | ruff | Decisión D-13; un solo tool |
| IDs y timestamps | contadores propios | `uuid.uuid4().hex`, `datetime.now(timezone.utc)` | Stdlib |
| DI | framework (dependency-injector, dishka) | composition root manual en `bootstrap/wiring.py` | D-10 lo fija; a esta escala el framework solo agrega magia |

**Key insight:** esta fase tiene exactamente UNA dependencia runtime (pydantic). Todo lo demás es stdlib — esa es la garantía de que `core/` es portable y testeable para siempre.

## Common Pitfalls

### Pitfall 1: Protocol que nadie verifica
**What goes wrong:** una implementación con firma incorrecta (param renombrado, sync vs async) pasa silenciosa hasta que explota en runtime en Fase 5.
**Why it happens:** los Protocols son estructurales; sin asignación tipada no hay chequeo.
**How to avoid:** conformance assignments (Pattern 5) + mypy sobre `tests/`.
**Warning signs:** un adapter nuevo sin entrada en `test_conformance.py`.

### Pitfall 2: Inmutabilidad superficial de frozen dataclasses
**What goes wrong:** `Plan` es frozen pero `Action.parameters` es un dict mutable — un agente podría mutar parámetros DESPUÉS de la evaluación de política (superficie de ataque real señalada en ARCHITECTURE.md).
**How to avoid:** tipar como `Mapping[str, object]` (la interfaz no expone mutación y mypy strict rechaza `params["x"] = y`); `steps` como `tuple[Action, ...]`, nunca list. No depender de hashing de `Action` (dict no hashea — no definir `unsafe_hash`). Test explícito: mutar un plan evaluado debe fallar (`FrozenInstanceError` para campos; mypy error para el Mapping).
**Warning signs:** `dict[str, object]` en firmas de dominio; `list[Action]` en `Plan.steps`.

### Pitfall 3: La config puede "apagar" la denylist
**What goes wrong:** si `PolicyRules.deny` viene 100% de config.toml, un TOML vacío (o un agente que edite config — regla #6) desactiva D.
**How to avoid:** `BUILTIN_DENY` como `Final` en código; el loader solo concatena. Test: engine construido con config vacía sigue clasificando D los golden plans de denylist.
**Warning signs:** ausencia de `builtin_deny.py`; un test que construye el engine "sin reglas".

### Pitfall 4: Atributos de Protocol vs properties en mypy strict
**What goes wrong:** declarar `media_types: frozenset[str]` como atributo mutable del Protocol hace que mypy rechace implementaciones con `@property` (read-only no satisface miembro mutable).
**How to avoid:** declarar miembros de solo lectura como `@property` en el Protocol (`@property def media_types(self) -> frozenset[str]: ...`). Aplica a `Extractor.media_types`, `ModelProvider.name`, `Tool.name`, `Tool.max_risk`.
**Warning signs:** errores mypy `"X is read-only in protocol"` al escribir el primer adapter.
[CITED: mypy docs — protocol members / read-only properties semantics]

### Pitfall 5: `datetime.utcnow()` y typing deprecado
**What goes wrong:** `utcnow()` está deprecado (naive datetime) y `typing.ContextManager` también.
**How to avoid:** `datetime.now(timezone.utc)` siempre; `contextlib.AbstractContextManager[Span]` para la firma de `AuditPort.span`. ruff `UP` lo detecta.

### Pitfall 6: SQLite WAL sobre NTFS (fuseblk)
**What goes wrong:** el repo vive en `/mnt/hdd` (NTFS vía FUSE — verificado: `df -T` reporta `fuseblk`). WAL usa un archivo `-shm` mapeado en memoria; sobre FUSE el locking/mmap puede degradar o fallar según versión del driver.
**How to avoid:** smoke test al inicializar el logger: ejecutar `PRAGMA journal_mode=WAL` y verificar que retorna `"wal"`; si retorna otra cosa, fail-fast con mensaje claro (no degradar silencioso a journal sin fsync para un audit log). Incluir test de concurrencia básica (2 conexiones, write+read) en `test_sqlite_logger.py` corriendo sobre `tmp_path` (ext4/tmpfs) Y un test opcional marcado `@pytest.mark.ntfs` sobre el data dir real.
**Warning signs:** `database is locked` intermitente; `journal_mode` que retorna `delete`.
**Confidence:** MEDIUM — el riesgo es conocido para filesystems no estándar; el comportamiento exacto de ntfs-3g actual con WAL no se verificó en esta sesión. El smoke test convierte la incertidumbre en fail-fast.

### Pitfall 7: mypy 2.x cambió defaults respecto a 1.x
**What goes wrong:** recetas de training/blogs asumen mypy 1.x; mypy 2.0 (actual: 2.1.0) activa `--local-partial-types` y `--strict-bytes` por default.
**How to avoid:** greenfield = ningún costo de migración; escribir directo contra mypy ≥ 2.1 y pinear `mypy>=2.1` en dev deps. No copiar configs viejas que desactiven esos flags.
[VERIFIED: mypy.readthedocs.io changelog — 2.0 flips local-partial-types y strict-bytes]

### Pitfall 8: Golden plans que solo prueban el happy path
**What goes wrong:** tests de política que verifican "A es A" pero no la dirección catastrófica (falso-A) ni los bordes (composición, target sensible con path relativo/`~`).
**How to avoid:** el set dorado DEBE incluir: ≥1 plan por nivel; ≥2 planes de bypass por composición (N deletes pequeños; N writes en directorios distintos); planes con targets `~/.ssh/config`, paths relativos y `..`; un plan con `estimated_risk=A` que el engine sube a C (POL-04). Normalizar targets (`expanduser` + `abspath` sintáctico) ANTES del matching — sin tocar el filesystem (el engine es puro; la resolución real de symlinks es la segunda muralla del adapter en Fase 6, EXEC-04).

## Code Examples

Patrones concretos para el planner (fuente: research/ARCHITECTURE.md §Patterns, validados contra Python 3.12+ stdlib).

### Dominio: RiskLevel ordenable + Plan inmutable

```python
# src/core/domain/risk.py
from enum import IntEnum
from typing import assert_never

class RiskLevel(IntEnum):
    """Orden total: A < B < C < D. max() implementa 'subir sí, bajar jamás' (POL-04)."""
    A = 1
    B = 2
    C = 3
    D = 4

class Outcome(IntEnum):
    EXECUTE = 1
    CONFIRM_SIMPLE = 2
    CONFIRM_STRONG = 3
    REJECT = 4

def outcome_for(level: RiskLevel) -> Outcome:
    match level:
        case RiskLevel.A: return Outcome.EXECUTE
        case RiskLevel.B: return Outcome.CONFIRM_SIMPLE
        case RiskLevel.C: return Outcome.CONFIRM_STRONG
        case RiskLevel.D: return Outcome.REJECT
    assert_never(level)
```

```python
# src/core/domain/plan.py
from collections.abc import Mapping
from dataclasses import dataclass, field
from core.domain.risk import RiskLevel

@dataclass(frozen=True, slots=True)
class Action:
    type: str                                   # taxonomía "file.delete" — desconocido = C
    target: str                                 # path/identificador (normalizado por el engine)
    parameters: Mapping[str, object] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class Plan:
    task_id: str
    summary: str
    steps: tuple[Action, ...]
    rationale: str
    estimated_risk: RiskLevel | None = None     # estimación del LLM — solo puede SUBIR el final
```

### Política: evaluación del plan completo

```python
# src/core/policy/engine.py (esqueleto)
class CognitivePolicyEngine:
    """Pura: Plan -> PolicyDecision. Sin IO, sin LLM. El módulo más testeado del sistema."""

    def __init__(self, rules: PolicyRules) -> None:
        self._rules = rules                     # BUILTIN_DENY + reglas de config (solo aditivas)

    def evaluate(self, plan: Plan) -> PolicyDecision:
        deny_hits = tuple(
            rule.id for rule in self._rules.deny
            if any(self._matches(rule, a) for a in plan.steps) or self._matches_aggregate(rule, plan)
        )
        if deny_hits:
            return self._decision(plan, RiskLevel.D, deny_hits)   # outcome=REJECT, auditable

        per_action = max(
            (self._base_level(a) for a in plan.steps),
            default=RiskLevel.A,
        )
        aggregate = self._aggregate_level(plan)                   # POL-05: plan entero
        final = max(per_action, aggregate, plan.estimated_risk or RiskLevel.A)  # POL-04
        return self._decision(plan, final, ())

    def _base_level(self, action: Action) -> RiskLevel:
        # fail-closed: action_type desconocido nunca es A
        return self._rules.base_levels.get(action.type, self._rules.unknown_action_level)  # default C
```

### AuditLogger: span con context manager

```python
# src/audit/sqlite_logger.py (esqueleto del span)
from contextlib import contextmanager
from collections.abc import Iterator

class SqliteAuditLogger:
    """Implementa AuditPort. DB separada de datos de usuario (D-06). Append-only."""

    @contextmanager
    def _span_impl(self, task_id: str, actor: str, event: str) -> Iterator[Span]:
        span = Span(task_id=task_id, actor=actor, event=event, started_at=_utcnow())
        self.log(AuditEvent.span_started(span))
        try:
            yield span
        except Exception as exc:
            self.log(AuditEvent.span_failed(span, exc))
            raise
        self.log(AuditEvent.span_completed(span))
```

(La firma pública `span(...) -> AbstractContextManager[Span]` satisface el Protocol; `@contextmanager` produce exactamente ese tipo.)

### Config: tomllib + Pydantic fail-fast

```python
# src/bootstrap/config.py
import sys, tomllib
from pathlib import Path
from pydantic import BaseModel, ConfigDict, ValidationError

class PolicyConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")   # typo en una deny rule = boot abortado (fail-closed)
    file_count_b: int = 10
    file_count_c: int = 100
    deny: list["DenyRuleModel"] = []
    # ...

class WyssConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    data_dir: Path
    audit_db: Path
    policy: PolicyConfigModel = PolicyConfigModel()

def load_settings(path: Path) -> WyssSettings:        # retorna el frozen dataclass de core/domain
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
        model = WyssConfigModel.model_validate(raw)
    except FileNotFoundError:
        sys.exit(f"wyss: no existe el archivo de configuración: {path}")
    except tomllib.TOMLDecodeError as e:
        sys.exit(f"wyss: TOML inválido en {path}: {e}")
    except ValidationError as e:
        lines = [f"  {'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()]
        sys.exit(f"wyss: configuración inválida en {path}:\n" + "\n".join(lines))
    return _to_settings(model)                         # Pydantic muere acá; core recibe dataclass
```

### Golden plans: fixtures TOML + parametrize

```toml
# tests/policy/golden/composition_mass_delete.toml
name = "bypass por composición — 200 deletes individuales"
expected_level = "D"
description = "Cada paso individual sería B/C; el agregado es D (POL-05, D-12)"

[[steps]]
type = "file.delete"
target = "~/Documents/old/file_001.txt"
# ... (generado: 200 steps en el fixture o construido programáticamente en el test)
```

```python
# tests/policy/test_golden_plans.py
GOLDEN_DIR = Path(__file__).parent / "golden"

@pytest.mark.parametrize("fixture", sorted(GOLDEN_DIR.glob("*.toml")), ids=lambda p: p.stem)
def test_golden_plan(fixture: Path, engine: CognitivePolicyEngine) -> None:
    case = load_golden(fixture)
    decision = engine.evaluate(case.plan)
    assert decision.risk_level == case.expected_level, (
        f"{case.name}: esperado {case.expected_level.name}, obtuvo {decision.risk_level.name}"
        + (" — FALSO-A: el sistema ejecutaría algo que debía confirmar/rechazar"
           if decision.risk_level < case.expected_level else "")
    )

def test_no_false_a_direction(all_golden_cases, engine) -> None:
    """La dirección catastrófica: nada esperado >A puede clasificar A."""
    for case in all_golden_cases:
        if case.expected_level > RiskLevel.A:
            assert engine.evaluate(case.plan).risk_level > RiskLevel.A

def test_monotonia_estimated_risk(engine) -> None:
    """POL-04: estimated_risk solo sube el nivel, jamás lo baja."""
    plan_c = make_plan(steps=[delete_action()])                      # base C
    lowered = replace(plan_c, estimated_risk=RiskLevel.A)
    assert engine.evaluate(lowered).risk_level >= RiskLevel.C
```

Set dorado mínimo recomendado (~12-15 fixtures): 2×A (read, search), 2×B (move, rename), 3×C (delete simple, overwrite, write en dir sensible), 3×D por denylist (write `~/.ssh`, self-modify config Wyss, git push --force main), 2× composición (mass delete, multi-dir spread), 1× estimated_risk que sube, 1× action type desconocido → C.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| mypy 1.x defaults | mypy 2.x: `local-partial-types` y `strict-bytes` default ON (actual 2.1.0) | mypy 2.0 (2026) | Greenfield: pinear `>=2.1`, no copiar configs 1.x [VERIFIED: mypy changelog] |
| pytest 8.x | pytest 9.0.3 | 2025-2026 | Sin impacto para esta fase; pinear `>=9` |
| pydantic sin soporte 3.14 | pydantic 2.12+ soporta Python 3.14 (PEP 649/749 lazy annotations) | 2.12 (oct 2025) | El entorno local es 3.14.5 — usar `>=2.13` [VERIFIED: pydantic.dev release notes] |
| `typing.ContextManager`, `datetime.utcnow()` | `contextlib.AbstractContextManager[T]`, `datetime.now(timezone.utc)` | deprecados hace varias versiones | ruff UP los detecta |
| `TypeVar` manual | PEP 695 (`class Registry[T]:`) | Python 3.12 | Usar sintaxis nueva en el registry genérico (Fase 3 lo necesita; el patrón ya está fijado en ARCHITECTURE.md) |

**Deprecated/outdated:** nada del stack elegido está deprecado. `config/config.example.yaml` del repo queda obsoleto (la spec fija TOML) — esta fase lo reemplaza por `config.example.toml`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | WAL de SQLite funciona correctamente sobre el mount NTFS fuseblk del owner | Pitfall 6 | Bajo — el smoke test al boot lo convierte en fail-fast; alternativa: mover `data/` a un path ext4 y symlinkear |
| A2 | Umbrales de agregación propuestos (10/100 archivos, 5 dirs, 50 deletes) son razonables para el uso del owner | Pattern 3.2 | Bajo — son configurables en config.toml por diseño; discreción delegada explícitamente |
| A3 | La denylist inicial de 7 reglas cubre lo que el owner espera de "conservador" | Pattern 3.3 | Bajo — discreción delegada; ampliable por config; los built-ins requieren code review para cambiar (deliberado) |
| A4 | Los "14 ports" del criterio de éxito = 13 Protocols + AgentBase ABC (conteo de ARCHITECTURE.md §Interface Contracts) | Pattern 2 | Medio — si el owner contaba distinto, falta/sobra un port; el planner debe listar los 14 explícitos en el plan para que verify-work lo confirme |
| A5 | Eliminar `src/__init__.py` no viola D-01 (es artefacto del init, no parte del árbol del owner) | Project Structure | Bajo — sin eliminarlo el esquema de imports flat no funciona; alternativa sería imports `src.core.*` (peor) |

## Open Questions

1. **¿Dónde vive exactamente `AgentBase`?**
   - What we know: el criterio de éxito dice "los 14 ports existen como Protocols en core/ports/"; ARCHITECTURE.md ubica AgentBase en `core/agents/base.py` y lo define como ABC (no Protocol).
   - What's unclear: si "14 en core/ports/" es literal.
   - Recommendation: ponerlo en `core/ports/agent.py` — satisface el criterio literalmente, es puro (solo importa domain + ports) y mantiene la regla "vecinos importan de core/ports". El planner lo fija así salvo objeción.

2. **Nivel de detalle de las entidades "mínimas" para Fases 2-4** (`ModelRequest`, `Chunk`, `Hit`…)
   - What we know: los ports las referencian; mypy strict exige que existan.
   - Recommendation: definir solo los campos que las firmas de los ports necesitan + los de docs/09 cuando la entidad aparece ahí. Expandir en su fase es aditivo.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | todo | ✓ | 3.14.5 | — |
| uv | gestión deps, venv | ✓ | 0.11.18 | — |
| SQLite + FTS5 + WAL | AuditLogger | ✓ | 3.53.2, FTS5 compilado | — |
| git | commits por fase | ✓ | repo confirmado | — |
| Filesystem del repo | data/audit.db | ⚠ | NTFS (fuseblk) en /mnt/hdd | Smoke test WAL al boot; si falla, `data/` en path ext4 + symlink |

**Missing dependencies with no fallback:** ninguna.
**Missing dependencies with fallback:** ninguna faltante; el ⚠ de NTFS tiene mitigación documentada (Pitfall 6).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | ninguno aún — `[tool.pytest.ini_options]` en pyproject.toml es Wave 0 |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| POL-01 | Todo plan produce PolicyDecision; engine sin path de ejecución | unit | `uv run pytest tests/policy/ -x` | ❌ Wave 0 |
| POL-02 | Mapeo nivel→outcome exhaustivo (A/B/C/D) | unit + mypy (`assert_never`) | `uv run pytest tests/policy/test_golden_plans.py -x` + `uv run mypy` | ❌ Wave 0 |
| POL-03 | Plan D → REJECT, auditado, ninguna API ejecuta; AgentBase raisea ante D | unit (test de ausencia) | `uv run pytest tests/policy/test_level_d.py tests/ports/test_agent_base.py -x` | ❌ Wave 0 |
| POL-04 | `estimated_risk` sube, nunca baja; D por denylist sin LLM | unit (monotonía) | `uv run pytest tests/policy/test_golden_plans.py::test_monotonia_estimated_risk -x` | ❌ Wave 0 |
| POL-05 | Plan compuesto de pasos menores que agrega a D → D | unit | `uv run pytest tests/policy/test_aggregation.py -x` | ❌ Wave 0 |
| AUD-01 | Eventos en SQLite separado; esquema cubre D-07; append-only; WAL activo | integration (tmp_path) | `uv run pytest tests/audit/test_sqlite_logger.py -x` | ❌ Wave 0 |

### Success Criteria → Validation Strategy
| # | Criterio | Estrategia concreta |
|---|----------|---------------------|
| 1 | 14 ports como Protocols en core/ports/, mypy strict pasa | `uv run mypy` (strict, files=src+tests) verde + `tests/ports/test_conformance.py` con asignaciones tipadas (Pattern 5) + `uv run lint-imports` (core stdlib-only) |
| 2 | Golden plans clasificados A/B/C/D; D por denylist sin LLM | `tests/policy/golden/*.toml` parametrizados (~12-15 casos); test direccional `test_no_false_a_direction`; test con config vacía donde los built-ins siguen dando D (Pitfall 3) |
| 3 | Bypass por composición → D | `tests/policy/test_aggregation.py`: 200 deletes individuales → D; N writes multi-dir → escala; fixture dorado `composition_mass_delete.toml` |
| 4 | AuditLogger escribe a SQLite; inyección verificada por firma | `tests/audit/test_sqlite_logger.py` (tmp_path: WAL=`"wal"`, trigger append-only aborta UPDATE/DELETE, span loggea start/end/exception); `tests/ports/test_agent_base.py`: `inspect.signature(AgentBase.__init__)` contiene parámetro `audit` y construir sin él falla |
| 5 | Config TOML validada al boot, fail-fast legible | `tests/config/test_load_settings.py`: TOML válido → `WyssSettings`; campo extra → exit con mensaje que nombra el campo (`extra="forbid"`); tipo inválido → mensaje con `loc`; archivo ausente → mensaje claro; ningún traceback crudo |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q && uv run mypy`
- **Per wave merge:** full suite (pytest + mypy + ruff + lint-imports)
- **Phase gate:** full suite verde antes de `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `pyproject.toml` — proyecto uv completo (deps, mypy, ruff, pytest, importlinter, hatchling packages)
- [ ] `tests/conftest.py` — fixtures: engine con reglas default, engine con config vacía, factory de planes/acciones, logger sobre tmp_path
- [ ] `tests/policy/golden/` — set dorado inicial
- [ ] Framework install: `uv sync` (crea venv + instala dependency-groups)
- [ ] Eliminar `src/__init__.py` y `config/config.example.yaml` (reemplazo por `.toml`)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (single-owner local, sin red en esta fase) | — |
| V3 Session Management | no | — |
| V4 Access Control | **yes — es el corazón de la fase** | CognitivePolicyEngine determinístico, fail-closed (desconocido=C), denylist no removible, evaluación de plan completo |
| V5 Input Validation | yes | Pydantic `extra="forbid"` en config; normalización de targets (`expanduser`+abspath sintáctico) antes del matching de denylist |
| V6 Cryptography | no en esta fase | — |
| V8 Logging & Auditing (V7/V8 según versión) | yes | Audit append-only (triggers SQLite), `synchronous=FULL`, REJECT siempre registrado, correlación por task_id |

### Known Threat Patterns for este stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Mutación del plan post-evaluación | Tampering | Frozen dataclasses + `tuple` steps + `Mapping` params; test de inmutabilidad |
| Bypass por composición de pasos menores | Elevation of Privilege | Agregados sobre el plan entero (POL-05); umbrales acumulativos; golden test dedicado |
| LLM persuadido baja el riesgo (prompt injection futuro) | Elevation of Privilege | `max(deterministic, estimated)` — estructuralmente imposible bajar (POL-04) |
| Denylist desactivada por config | Tampering | Built-ins `Final` en código; config solo aditiva; test con config vacía |
| Reescritura de historia de auditoría | Repudiation | Triggers `RAISE(ABORT)` en UPDATE/DELETE; API sin métodos de mutación |
| Path tricks en targets (`~`, `..`, relativos) | Tampering | Normalización sintáctica en el engine; resolución real de symlinks en el adapter de ejecución (Fase 6, EXEC-04 — segunda muralla) |
| Pérdida de eventos de auditoría en crash | Repudiation | `PRAGMA synchronous=FULL` (fsync por commit) — barato a esta escala |

## Sources

### Primary (HIGH confidence)
- Docs canónicos del proyecto: `docs/18-prompt-implementacion.md`, `docs/13-politica-acceso-seguridad.md`, `docs/09-modelo-de-datos.md`, `.planning/phases/01-fundaciones/01-CONTEXT.md` — decisiones fijas
- `.planning/research/ARCHITECTURE.md` — los 14 ports, patrones 1-8, build order (research previo del proyecto)
- PyPI vía `pip index versions` (2026-06-10): pydantic 2.13.4, pytest 9.0.3, mypy 2.1.0, ruff 0.15.16, import-linter 2.11, hypothesis 6.155.2
- slopcheck 0.6.1: 6/6 paquetes `[OK]`
- Entorno local verificado: Python 3.14.5, uv 0.11.18, SQLite 3.53.2 con FTS5, repo git, filesystem fuseblk (NTFS)
- Python stdlib 3.12+ (`tomllib`, `Protocol`, `IntEnum`, `assert_never`, `AbstractContextManager`)

### Secondary (MEDIUM confidence)
- [mypy changelog/release planning — defaults 2.0](https://mypy.readthedocs.io/en/stable/changelog.html) (WebSearch verificado con docs oficiales)
- [Pydantic v2.12 release — soporte Python 3.14](https://pydantic.dev/articles/pydantic-v2-12-release) (WebSearch verificado con anuncio oficial)
- hatchling `packages` para multi-package wheel — hatch.pypa.io (training + estructura confirmada localmente)

### Tertiary (LOW confidence)
- Comportamiento exacto de SQLite WAL sobre ntfs-3g/fuseblk — no verificado empíricamente en esta sesión; mitigado con smoke test fail-fast (Assumption A1)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versiones verificadas contra PyPI + slopcheck, una sola dep runtime
- Architecture: HIGH — patrones ya decididos en research previo del proyecto; esta fase los aterriza a archivos/firmas
- Pitfalls: HIGH para los de diseño (1-5, 7-8); MEDIUM para WAL-sobre-NTFS (6, mitigado)

**Research date:** 2026-06-10
**Valid until:** 2026-07-10 (stack estable; re-verificar versiones con `uv add` al ejecutar)
