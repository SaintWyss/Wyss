# Architecture Research

**Domain:** Multi-agent AI system, local-first, hexagonal (Ports & Adapters), Python 3.13+
**Project:** Wyss
**Researched:** 2026-06-10
**Confidence:** HIGH (docs 07/08/09/10/11/14 + verified current Python ecosystem patterns)

---

## Component Map (what talks to what)

### Hexagonal mapping of the five Wyss blocks

The conceptual docs (07, 08) map cleanly onto hexagonal layers. The key reframing: **the "Núcleo" is not one layer — it splits into domain core + application services.**

```
┌──────────────────────────── DRIVING ADAPTERS ────────────────────────────┐
│  CLI / chat (v0.1)   ·   RoutineScheduler (time-driven)   ·   future UI  │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼  (calls inbound ports)
┌──────────────────────────── APPLICATION LAYER ───────────────────────────┐
│  Orchestrator · IntentRouter · TaskPlanner · ConfirmationManager         │
│  AgentRuntime · IngestionPipeline · RetrievalEngine · ModelRouter        │
│  (use cases — orchestrate domain objects, depend ONLY on ports)          │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▼  (uses)
┌──────────────────────────────── DOMAIN CORE ─────────────────────────────┐
│  Entities/VOs: Task, Plan, Action, PolicyDecision, Permission, Agent     │
│               (definition), KnowledgeBase, RiskLevel, Intent, Report     │
│  Pure logic:  CognitivePolicyEngine · PermissionManager (rules)          │
│  Ports:       ALL Protocols/ABCs live here (wyss.core.ports)             │
│  ZERO imports of anything outside stdlib                                 │
└──────────────────────────────────┬───────────────────────────────────────┘
                                   ▲  (implemented by — dependency points inward)
┌──────────────────────────── DRIVEN ADAPTERS ─────────────────────────────┐
│  Execution:   FileSystemAdapter · ShellAdapter · GitAdapter · ...        │
│  Models:      AnthropicProvider · OpenAIProvider · LiteLLMProvider · ... │
│  Knowledge:   SqliteFtsIndex · SqliteVecIndex/Chroma · PdfExtractor ...  │
│  Persistence: SqliteTaskRepo · SqlitePermissionRepo · SqliteAuditSink    │
│  Config:      TomlConfigStore                                            │
└───────────────────────────────────────────────────────────────────────────┘
```

### Dependency rule table

| Component | Layer | May import | Must NOT import |
|---|---|---|---|
| `core/domain` (entities, enums) | Domain | stdlib only | everything else |
| `core/ports` (Protocols/ABCs) | Domain | `core/domain` | application, adapters |
| `core/policy` (CognitivePolicyEngine) | Domain | `core/domain` | ports impls, IO |
| `core/permissions` (rule logic) | Domain | `core/domain` | IO (repo via port) |
| `orchestration/` (Orchestrator, IntentRouter, TaskPlanner, ConfirmationManager) | Application | `core/*` | adapters, `agents/` internals |
| `agents/` (AgentBase, AgentRegistry, AgentRuntime) | Application | `core/*` | adapters directly (only via ToolPort) |
| `knowledge/` (IngestionPipeline, ExtractorRegistry, RetrievalEngine) | Application | `core/*` | concrete index/extractor impls |
| `gateway/` (ModelRouter, ContextMinimizer, CostTracker) | Application | `core/*` | concrete provider SDKs |
| `adapters/` (everything concrete) | Infrastructure | `core/ports`, `core/domain`, 3rd-party SDKs | application layer |
| `audit/` | Port in core + sinks in adapters | — | — |
| `bootstrap/` (composition root) | Wiring | EVERYTHING | n/a — only place allowed to |

### Communication edges (from doc 08, made hexagonal)

- **CLI → Orchestrator** via inbound port `CommandHandler` (the only entry point; RoutineScheduler calls the same port — a routine is just a pre-recorded command).
- **Orchestrator → IntentRouter → TaskPlanner → CognitivePolicyEngine → ConfirmationManager**: synchronous in-process calls within the application layer.
- **Orchestrator → AgentRuntime**: the ONLY component that assigns work to agents. Agents never see each other (enforced structurally: `AgentBase` has no reference to `AgentRegistry`).
- **AgentRuntime → RetrievalEngine** (knowledge), **→ ModelRouter** (AI), **→ ToolPort** (execution). These three ports are the agent's entire world.
- **RetrievalEngine → PermissionManager**: permission filtering happens INSIDE retrieval, not in the agent (per class diagram in doc 11 — agents physically cannot query unauthorized KBs).
- **ModelRouter → ContextMinimizer → ModelProviderPort**, with **CostTracker** observing every call.
- **AuditPort**: injected into Orchestrator, AgentRuntime, ConfirmationManager, ModelRouter, ToolExecutor. Cross-cutting via injection, not via magic (see Patterns).

---

## Data Flow (how information moves through the system)

### Flow 1 — Command flow (the main loop, from doc 11 sequence diagram)

```
Owner text
  → CLI adapter parses → Command (frozen dataclass)
  → Orchestrator.handle(command)
      → IntentRouter.classify(command) → Intent (query | task | admin | ambiguous)
      → if query: RetrievalEngine.search(...) → answer, done
      → if task:  select Agent by domain (AgentRegistry)
                  AgentRuntime.plan(agent, task)
                      agent queries RetrievalEngine (permission-filtered)
                      agent calls ModelRouter (context-minimized) → Plan
      → CognitivePolicyEngine.evaluate(plan) → PolicyDecision (A|B|C|D)
          D → reject + audit + explain, STOP
          B/C → ConfirmationManager.request(...) → owner confirms or cancels
          A or confirmed → AgentRuntime.execute(agent, plan)
              each Action → ToolPort.execute() → ToolResult + verification
      → Orchestrator consolidates Report → AuditPort.log(full trace) → Owner
```

Every state transition matches the task state machine in doc 11 §4 (`Recibida → Clasificada → Delegada → Planificada → Evaluada → ...`). **Model that state machine as a `TaskStatus` enum on the `Task` entity and make illegal transitions raise** — it is the backbone of auditability.

### Flow 2 — Ingestion flow (doc 14 §3, write path of knowledge)

```
Source registered (KB + path)
  → Scanner: inventory files + metadata
  → Diff: hash + mtime → only new/changed
  → ExtractorRegistry.for_media_type(mt) → ExtractorPort.extract() → text
  → ChunkerPort.chunk(text) → chunks with exact source refs
  → SummarizerPort (cheap model via gateway) → per-file/chunk summary
  → DOUBLE index:  FullTextIndexPort.upsert (FTS5)
                   EmbeddingPort.embed → VectorIndexPort.upsert
  → catalog into KnowledgeBase (IndexEntry rows)
```

Pure pipeline: each stage a port, data flows as immutable dataclasses (`SourceFile → ExtractedContent → list[Chunk] → list[IndexEntry]`). Never mutates source files (doc 14 rule).

### Flow 3 — Retrieval flow (doc 14 §4, read path)

```
Query (from owner or agent, carries subject identity)
  → fan-out in parallel:  metadata filter | FTS5 match | vector similarity
  → fusion + ranking (RRF — reciprocal rank fusion, standard for hybrid)
  → PermissionManager.filter(subject, results)   ← security boundary
  → Hits: exact location + excerpt + summary
```

**Boundary decision:** permission filtering AFTER fusion but BEFORE results leave the RetrievalEngine. Better: pass `allowed_kbs` INTO the index queries (pre-filter) so unauthorized content never enters memory of the calling context. Do both: pre-filter by KB id at query time, post-check before returning.

### Flow 4 — Model call flow (every external AI interaction)

```
ModelRequest (task_kind, sensitivity, agent_id, payload)
  → ModelRouter: deterministic? → no model. cheap? strong? sensitive? → choose alias
  → ContextMinimizer: strip secrets, trim to minimum, redact per sensitivity
  → ModelProviderPort.complete(request)
  → CostTracker.record(agent_id, tokens, cost) → budget check (can VETO before send)
  → ModelResponse → audit
```

CostTracker must check budget **before** the call (pre-authorization) and record after — otherwise budgets are advisory, not enforced.

### Flow 5 — Audit flow (transversal)

Every component receives `AuditPort` by constructor injection. Events are append-only `AuditEvent` dataclasses with `task_id` correlation. One write path (SQLite table + optional JSONL sink), never blocking the main flow (write-behind queue acceptable; loss-on-crash is not — fsync per event in v0.1, it's cheap at this scale).

---

## Python Patterns for Implementation (ABCs, Protocols, concrete examples)

### Pattern 1 — Protocols for ports, ABCs for shared enforced behavior

Current consensus (verified): **`typing.Protocol` for ports** (structural typing — adapters don't import core base classes, perfect for plugins), **ABC where you need shared implementation + behavior that subclasses must not skip** (template method). Wyss needs both:

```python
# core/ports/knowledge.py — Protocol: pure contract, no inheritance needed
from typing import Protocol
from wyss.core.domain import Chunk, ExtractedContent, SourceFile

class Extractor(Protocol):
    """Port: turns a source file into text. New file type = new class."""
    @property
    def media_types(self) -> frozenset[str]: ...
    def extract(self, source: SourceFile) -> ExtractedContent: ...
```

```python
# core/agents/base.py — ABC with template method: policy/audit CANNOT be skipped
from abc import ABC, abstractmethod

class AgentBase(ABC):
    """Doc 10 §2: 'ningún agente la puede saltear' — enforced structurally."""
    def __init__(self, definition: AgentDefinition, retrieval: Retrieval,
                 gateway: ModelGateway, tools: ToolBelt, audit: AuditPort):
        self._def = definition
        self._retrieval = retrieval   # already permission-scoped to this agent
        self._gateway = gateway       # already budget-scoped to this agent
        self._tools = tools           # only the adapters this agent is allowed
        self._audit = audit

    def execute(self, plan: Plan) -> Report:        # NOT overridable in spirit
        if plan.risk_level is RiskLevel.D:
            raise PolicyViolation(plan)              # belt-and-suspenders
        self._audit.log(AuditEvent.plan_started(self._def.id, plan))
        try:
            report = self._run(plan)                 # subclass hook
        except Exception as exc:
            self._audit.log(AuditEvent.plan_failed(self._def.id, plan, exc))
            raise
        self._audit.log(AuditEvent.plan_completed(self._def.id, report))
        return report

    @abstractmethod
    def _run(self, plan: Plan) -> Report: ...
```

**Critical nuance from doc 10:** "Crear un agente nuevo = modelo base + configuración. Cero código nuevo." That means in v0.1 there is likely only ONE concrete agent class — `ConfiguredAgent(AgentBase)` — whose behavior comes entirely from `AgentDefinition` (domain, tools, model alias, system prompt). The ABC subclass-hook exists for FUTURE specialized agents, not for v0.1. Don't create `BelgranoAgent` classes; create agent TOML/YAML configs.

### Pattern 2 — Frozen dataclasses in the domain, Pydantic only at the boundary

```python
# core/domain/plan.py — stdlib only, immutable, hashable
from dataclasses import dataclass, field
from enum import Enum

class RiskLevel(Enum):
    A = "a"   # auto-execute
    B = "b"   # simple confirmation
    C = "c"   # strong confirmation
    D = "d"   # absolute rejection

@dataclass(frozen=True, slots=True)
class Action:
    type: str
    target: str
    parameters: dict[str, object] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class Plan:
    task_id: str
    summary: str
    steps: tuple[Action, ...]
    risk_level: RiskLevel
    rationale: str
```

- Domain: `@dataclass(frozen=True, slots=True)` — zero dependencies, immutability prevents agents mutating plans after policy evaluation (a real attack surface here).
- Boundaries (config files, model API payloads, persistence rows): **Pydantic v2** models in `adapters/`, converted to/from domain dataclasses at the adapter edge. Never let Pydantic models leak into `core/`.

### Pattern 3 — Generic decorator registry + entry points for plugins

```python
# core/registry.py — one generic registry, reused everywhere (PEP 695, Py 3.12+)
class Registry[T]:
    def __init__(self, kind: str) -> None:
        self._kind = kind
        self._items: dict[str, type[T]] = {}

    def register(self, name: str):
        def deco(cls: type[T]) -> type[T]:
            if name in self._items:
                raise DuplicateRegistration(self._kind, name)
            self._items[name] = cls
            return cls
        return deco

    def create(self, name: str, **kwargs) -> T:
        try:
            return self._items[name](**kwargs)
        except KeyError:
            raise UnknownPlugin(self._kind, name, available=list(self._items))

# adapters/extractors/pdf.py — plugging in = existing, never editing core
@extractors.register("pdf")
class PdfExtractor:
    media_types = frozenset({"application/pdf"})
    def extract(self, source: SourceFile) -> ExtractedContent: ...
```

Registration triggers on import — the composition root imports `wyss.adapters.extractors` (a package whose `__init__` imports all modules). For **third-party** plugins later, discover via `importlib.metadata.entry_points(group="wyss.extractors")` — same registry, second discovery source. This is the standard 2025 pattern (used by pytest/pluggy, AiiDA, etc.). Don't adopt `pluggy` itself in v0.1 — its hook model (many subscribers per hook) doesn't match Wyss's model (one selected implementation per request); the registry above is enough.

Registries needed: `extractors`, `tools` (execution adapters), `model_providers`, `chunkers`, `interfaces` (CLI/chat), `audit_sinks`. Agents are NOT a class registry — they are a **data** registry (rows/configs), per doc 10.

### Pattern 4 — Manual composition root, no DI framework

Verified recommendation: at this scale, a hand-written composition root beats `dependency-injector`/`dishka` (frameworks earn their keep with request-scoped lifetimes in web apps; Wyss is a long-lived daemon with one object graph).

```python
# bootstrap/wiring.py — the ONLY module that imports adapters AND application
def build_wyss(config: WyssConfig) -> Orchestrator:
    audit = SqliteAuditSink(config.db_path)
    fts = SqliteFtsIndex(config.db_path)
    vectors = SqliteVecIndex(config.db_path)          # or Chroma embedded
    permissions = PermissionManager(SqlitePermissionRepo(config.db_path), audit)
    retrieval = RetrievalEngine(fts, vectors, MetadataIndex(...), permissions)
    cost = CostTracker(SqliteCostRepo(config.db_path), config.budgets)
    gateway = ModelGateway(
        router=ModelRouter(config.model_aliases),
        minimizer=ContextMinimizer(config.redaction_rules),
        providers={"anthropic": AnthropicProvider(...), "litellm": LiteLLMProvider(...)},
        cost=cost, audit=audit,
    )
    runtime = AgentRuntime(AgentRegistry(SqliteAgentRepo(...)),
                           retrieval, gateway, build_toolbelt(config), audit)
    return Orchestrator(
        intent=IntentRouter(gateway),
        planner=TaskPlanner(gateway),
        policy=CognitivePolicyEngine(config.policy_rules),
        confirm=ConfirmationManager(audit),
        runtime=runtime, audit=audit,
    )
```

Everything is **constructor injection**, all dependencies typed as ports. Tests inject fakes; no monkeypatching needed.

### Pattern 5 — Scoped facades enforce restrictions structurally

Doc 10 §7 lists what an agent "nunca puede hacer". Don't enforce these with runtime checks scattered around — enforce by **construction**: when AgentRuntime instantiates an agent, it hands it pre-scoped capability objects:

- `ScopedRetrieval(retrieval, subject=agent_id)` — bakes the agent identity into every query; the agent cannot ask as someone else.
- `ScopedGateway(gateway, agent_id, budget)` — every model call pre-tagged and budget-checked.
- `ToolBelt(allowed: dict[str, Tool])` — agent only ever receives the adapters in its definition; the others don't exist from its perspective.

This is the capability-security pattern and it's the single most important structural decision in this system: an agent without a reference cannot misuse it.

### Pattern 6 — Audit as injected port + context manager, not AOP

Avoid decorators-with-globals or aspect libraries. Two explicit mechanisms:

```python
class AuditPort(Protocol):
    def log(self, event: AuditEvent) -> None: ...

# convenience for spans:
with audit.span(task_id, actor="agent:belgrano", event="execute_plan") as span:
    ...   # span logs start, end/duration, and exception automatically
```

`AuditEvent` is a frozen dataclass mirroring the `AuditLog` entity of doc 09 (actor_type, actor_id, event_type, task_id, metadata). Correlation by `task_id` reconstructs the full trace of any task.

### Pattern 7 — Enums + exhaustive matching for the policy engine

```python
def next_step(decision: PolicyDecision) -> Step:
    match decision.outcome:
        case Outcome.ALLOW:            return Step.EXECUTE
        case Outcome.CONFIRM_SIMPLE | Outcome.CONFIRM_STRONG:
            return Step.AWAIT_CONFIRMATION
        case Outcome.REJECT:           return Step.REJECT
    assert_never(decision.outcome)   # typing.assert_never → mypy catches new variants
```

`CognitivePolicyEngine` should be a **pure function over Plan → PolicyDecision** (rules from config + hard-coded invariants like "delete without backup = D"). Pure = trivially testable = the most-tested module in the system.

### Pattern 8 — Async where IO fans out, sync core

Model calls, hybrid retrieval fan-out (3 parallel queries), and ingestion batches benefit from `asyncio`. The domain core stays sync (pure functions). Practical split: define ports as `async def` for anything that crosses a network or disk boundary (`ModelProviderPort`, index ports, tool ports); keep `CognitivePolicyEngine`, `PermissionManager` rule-checks, and entity logic synchronous. Don't dual-maintain sync+async versions.

---

## Build Order (dependencies between components — what must be built first)

Dependency-driven order, each step testable in isolation, with vertical-slice milestones:

| # | Build | Depends on | Why this position |
|---|---|---|---|
| 0 | `core/domain` — entities, enums (`Task`, `Plan`, `Action`, `RiskLevel`, `TaskStatus` state machine, `AgentDefinition`, `Permission`, `AuditEvent`) | nothing | Everything imports these. Pure stdlib, fully unit-tested first. |
| 1 | `core/ports` — ALL Protocols (see Interface Contracts) | 0 | Interfaces-first mandate. Cheap to write, forces design decisions early. |
| 2 | `audit/` — AuditPort + SQLite/JSONL sink | 0,1 | Transversal: every later component takes it in its constructor. Building it late means retrofitting every signature. |
| 3 | `core/policy` — CognitivePolicyEngine (pure) + `core/permissions` rule logic | 0 | Zero IO, highest-value tests, defines the A–D semantics everything else honors. |
| 4 | Config: `WyssConfig` (Pydantic at boundary) + `bootstrap/` skeleton | 0–3 | Composition root grows with the system; start it now. |
| 5 | `gateway/` — ModelRouter, ContextMinimizer, CostTracker + ONE provider adapter (LiteLLM gives many models for one adapter) | 1,2,4 | Needed by planner, summarizer, agents. Testable with a `FakeProvider`. |
| 6 | `knowledge/` — ExtractorRegistry + 2–3 extractors (txt/md, pdf), Chunker, FTS5 index, vector index, IngestionPipeline, RetrievalEngine (hybrid fusion + permission filter) | 1,2,3,5(summaries) | **Milestone A: instant search over the owner's files — standalone value before any agent exists.** This de-risks the hardest subsystem early. |
| 7 | `orchestration/` — IntentRouter, TaskPlanner, ConfirmationManager, Orchestrator | 3,5,6 | The conductor. With knowledge done, "query" intent works end-to-end. |
| 8 | `agents/` — AgentBase, ConfiguredAgent, AgentRegistry, AgentRuntime, scoped facades | 3,5,6,7 | Needs everything an agent touches to already exist. |
| 9 | Execution adapters — FileSystemAdapter first (with dry-run + verify), then ShellAdapter, GitAdapter | 1,2 (buildable earlier; integrate here) | **Milestone B: one agent executes a real plan with confirmation flow.** FileSystem first: most useful, easiest to verify/rollback. |
| 10 | CLI interface loop (full REPL with confirmations) | 7 | Thin; a basic version should exist from step 7 for dogfooding. |
| 11 | RoutineScheduler | 7 | Trivial once Orchestrator exists (it just submits commands on a cron). |
| 12 | Workers, MessagingAdapter, CalendarAdapter, multi-context replication | all | Explicitly post-v0.1 per docs. |

**Anti-pattern to avoid in ordering:** building the agent layer before knowledge + gateway. Agents are thin coordinators; their value is entirely in what they can reach. Build the reachable things first.

---

## Interface Contracts (key ABCs/Protocols to define first)

All in `wyss/core/ports/`, all consuming/returning domain dataclasses only. The 14 that matter, in definition order:

```python
# --- transversal -----------------------------------------------------------
class AuditPort(Protocol):
    def log(self, event: AuditEvent) -> None: ...
    def span(self, task_id: str, actor: str, event: str) -> ContextManager[Span]: ...

class ConfigStore(Protocol):
    def load(self) -> WyssConfig: ...

# --- knowledge -------------------------------------------------------------
class Extractor(Protocol):
    media_types: frozenset[str]
    def extract(self, source: SourceFile) -> ExtractedContent: ...

class Chunker(Protocol):
    def chunk(self, content: ExtractedContent) -> Sequence[Chunk]: ...

class EmbeddingProvider(Protocol):
    async def embed(self, texts: Sequence[str]) -> Sequence[Vector]: ...

class FullTextIndex(Protocol):
    def upsert(self, entries: Sequence[IndexEntry]) -> None: ...
    def search(self, query: str, kb_ids: frozenset[str], limit: int) -> Sequence[Hit]: ...

class VectorIndex(Protocol):
    def upsert(self, entries: Sequence[tuple[IndexEntry, Vector]]) -> None: ...
    def search(self, vector: Vector, kb_ids: frozenset[str], limit: int) -> Sequence[Hit]: ...

class Retrieval(Protocol):          # what agents/orchestrator see (already fused+filtered)
    async def search(self, query: Query, subject: Subject) -> Sequence[Hit]: ...

# --- security --------------------------------------------------------------
class PermissionStore(Protocol):    # persistence port; rule logic lives in core
    def grants_for(self, subject: Subject) -> Sequence[Permission]: ...
    def save(self, permission: Permission) -> None: ...
    def revoke(self, permission_id: str) -> None: ...

# --- gateway ---------------------------------------------------------------
class ModelProvider(Protocol):
    name: str
    async def complete(self, request: ModelRequest) -> ModelResponse: ...

class ModelGatewayPort(Protocol):   # what agents see (routing+minimizing+cost inside)
    async def ask(self, request: AgentModelRequest) -> ModelResponse: ...

# --- execution -------------------------------------------------------------
class Tool(Protocol):
    name: str
    max_risk: RiskLevel                       # adapter declares its ceiling
    def describe(self, action: Action) -> str            # for confirmation prompts
    async def execute(self, action: Action) -> ToolResult: ...
    async def verify(self, action: Action, result: ToolResult) -> Verification: ...

# --- persistence -----------------------------------------------------------
class TaskRepository(Protocol):
    def save(self, task: Task) -> None: ...
    def get(self, task_id: str) -> Task: ...
```

Plus the **one ABC**: `AgentBase` (template method shown above — ABC, not Protocol, precisely because audit/policy hooks must be inherited, not merely conformed to).

Contract rules:
1. Ports accept/return only `core/domain` types — never SDK types, never Pydantic, never ORM rows.
2. Every `Tool.execute` is paired with `verify` (doc 11: "resultado + verificación") — verification is part of the contract, not an afterthought.
3. `kb_ids` permission scoping is a parameter of the index ports themselves — adapters cannot "forget" to filter.

---

## Extensibility Points (where the plugin pattern applies)

| Extension point | Mechanism | Adding one means | Open/Closed status |
|---|---|---|---|
| **File-type extractor** | `Extractor` Protocol + `extractors` registry (`@extractors.register("epub")`) | New class in `adapters/extractors/`, zero edits elsewhere | Fully closed to modification |
| **Model provider** | `ModelProvider` Protocol + registry; selected by alias in config | New class + config alias entry | Closed; ModelRouter logic untouched |
| **Execution tool/adapter** | `Tool` Protocol + `tools` registry; agent definitions reference tool names | New class + grant in agent config | Closed; PermissionManager untouched |
| **Agent** | **Configuration, not code** (doc 10): TOML/YAML → `AgentDefinition` row → `ConfiguredAgent` instance | New config file. Zero code | The product's core promise |
| **Specialized agent behavior** (future) | Subclass `AgentBase`, override `_run` | New class; policy/audit inherited, unskippable | Closed via template method |
| **Audit sink** | `AuditPort` impl + fan-out `CompositeAuditSink` | New sink class (e.g., remote SIEM later) | Closed |
| **Interface** (CLI → chat → voice → mobile) | Driving adapters all call the same `Orchestrator.handle(Command)` inbound port | New adapter package | Closed; core never knows the UI |
| **Vector/FTS backend** | `VectorIndex`/`FullTextIndex` Protocols (sqlite-vec → Chroma → Qdrant server) | Swap in bootstrap; doc 14 §7 "la arquitectura no cambia, solo el despliegue" holds automatically | Closed |
| **Embedding source** | `EmbeddingProvider` Protocol (API now, local CPU model later per doc 14 §7) | New adapter | Closed |
| **Policy rules** | Data-driven rules (config) evaluated by the engine; hard invariants (level-D list) stay in code | Edit config for tunables; code change ONLY for new invariant categories | Partially open by design — safety invariants SHOULD require code review |
| **Intent classification** | `IntentClassifier` Protocol (regex/heuristic v0.1 → cheap model later) | Swap adapter | Closed |
| **Third-party plugins** (post-v0.1) | `importlib.metadata.entry_points(group="wyss.*")` feeding the same registries | `pip install wyss-extractor-foo` | Closed; discovery is additive |

**Where NOT to make it pluggable:** Orchestrator, CognitivePolicyEngine invariants, PermissionManager, AgentBase template method, ContextMinimizer. These are the security/governance spine — making them swappable would let a plugin bypass the rules the whole design exists to enforce. Hard-code the spine; plug in the limbs.

---

## Sources

- Wyss design docs (authoritative for requirements): `docs/07-arquitectura-conceptual.md`, `08-diagrama-componentes.md`, `09-modelo-de-datos.md`, `10-arquitectura-de-agentes.md`, `11-diagramas-uml.md`, `14-estrategia-conocimiento-indexacion.md` — HIGH
- Protocol vs ABC for hexagonal ports: [Modern Python Interfaces: ABC, Protocol, or Both?](https://tconsta.medium.com/python-interfaces-abc-protocol-or-both-3c5871ea6642), [Hexagonal Architecture in Python (van der Meij)](https://douwevandermeij.medium.com/hexagonal-architecture-in-python-7468c2606b63), [Hexagonal architecture in Python (Miks)](https://blog.szymonmiks.pl/p/hexagonal-architecture-in-python/) — MEDIUM (multiple credible sources agree; matches PEP 544 official semantics)
- Plugin/registry/entry-points patterns: [Dependency Inversion and Entry Points](https://johndanielraines.medium.com/level-up-in-python-with-dependency-inversion-and-entry-points-c648a1b087ee), [How to Build Plugin Systems in Python](https://oneuptime.com/blog/post/2026-01-30-python-plugin-systems/view), [Registry Pattern with Decorators](https://medium.com/@tihomir.manushev/implementing-the-registry-pattern-with-decorators-in-python-de8daf4a452a), [class-registry (entry-points integration)](https://github.com/todofixthis/class-registry) — MEDIUM
- `dataclasses(frozen=True, slots=True)`, `typing.Protocol`, `match`/`assert_never`, PEP 695 generics, `importlib.metadata.entry_points`: Python stdlib (3.12+; local env is 3.14.5) — HIGH
