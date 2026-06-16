# Phase 8: Primer Agente de Dominio (Finanzas) - Research

**Researched:** 2026-06-16
**Domain:** Domain advisory agent (config-driven, wyss-native) + new SQLite-backed ledger capability, hexagonal ports/adapters
**Confidence:** HIGH

## Summary

This phase is unusually well pre-specified: `08-AI-SPEC.md` (design contract) and `08-PATTERNS.md` (analog map) already resolve framework selection, evaluation dimensions, prompt design, and file-by-file code patterns against the real source tree. This research does **not** re-derive that work. It verifies the load-bearing claims directly against `src/` (all confirmed accurate), surfaces three concrete planning gaps PATTERNS.md flagged but left open, and produces the Validation Architecture / Nyquist sampling section the planner needs but AI-SPEC's `## 5. Evaluation Strategy` doesn't fully translate into pytest-runnable commands.

Three gaps verified as real (not hypothetical) by direct inspection of the repo:
1. **No `config.toml` exists yet in the repo** — only test fixtures (`_VALID_AGENT_TOML` in `tests/bootstrap/test_agent_config.py`) reference the shape. The planner must create it as part of this phase, not "edit" it.
2. **No `pytest -m llm_judge` marker exists** — `pyproject.toml`'s `[tool.pytest.ini_options].markers` currently lists only `ntfs`, `integration`, `gateway`. Adding `llm_judge` is in-scope plumbing for D3.
3. **Two distinct `budget_usd` locations exist and are NOT auto-synced** — `[[agents]].budget_usd` (informational, flows into `AgentDefinition`) and `[gateway].agent_budgets` (the dict `CostTracker.authorize()` actually reads, confirmed at `src/gateway/cost.py:87`). The plan must populate `[gateway.agent_budgets].pellegrini = 5.0` explicitly — setting only `[[agents]].budget_usd` does **not** wire the gate.

**Primary recommendation:** Follow AI-SPEC §3/§4 and PATTERNS.md file-by-file verbatim (every pattern there was independently re-verified against `src/` in this research and found accurate). Spend planning effort on the three gaps above, the `finance.record`/`finance.query` action-type contract (no precedent in repo — greenfield), and the Validation Architecture section below, which maps AI-SPEC's 6 eval dimensions onto concrete `pytest` commands and a Wave 0 test-file checklist.

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-80:** Nombre **Pellegrini**. `agent_id = "pellegrini"`, `domain = "finanzas"`.
- **D-81:** Modelo `economico` + `budget_usd = 5.0` (tope chico a propósito para agotar el gate en test).
- **D-82:** Ledger SQLite tras un port nuevo (mismo patrón que `src/audit/sqlite_logger.py` y `src/orchestrator/pending_store.py`). Dominio: transacción con tipo (ingreso/gasto), monto, fecha, y para ingreso `fuente` / para gasto `categoria`.
- **D-83:** Categorías **free-text** en v0.1 (no enum fijo).
- **D-84:** Carga **híbrida (CLI + conversacional)**. CLI determinístico sin IA. Conversacional vía acción `finance.record` owner-instruida que DEBE pasar por el policy engine (segunda muralla) — no es escritura libre desde contenido de BC (respeta D-71).
- **D-85:** El primitivo de enforcement de presupuesto **ya existe** en `src/gateway/cost.py`. El trabajo de fase es cablear `agent_budgets` desde `[[agents]].budget_usd` (o sección equivalente) en el composition root y verificar E2E el bloqueo. NO re-implementar el gate.
- **D-86:** Pellegrini reporta vía el **daemon dispatcher** existente con **FakeOrchestrator** — Hermes real diferido (05-05 bloqueado).
- **D-87:** Las 3 tareas E2E de aceptación: (1) "¿Dónde se me va la plata?" → gastos por categoría; (2) "Armá mi presupuesto mensual" → propuesta desde ingresos vs. gastos históricos; (3) "¿Cuánto puedo ahorrar?" → superávit/déficit + sugerencia.

### Claude's Discretion

- Esquema exacto de la tabla SQLite del ledger, nombres de columnas, índices.
- Diseño del/los action type(s) (`finance.record`, `finance.query`) y su clasificación de riesgo en la denylist.
- Forma de los subcomandos CLI (`wyss fin ...`) y su salida Rich.
- Cómo Pellegrini "lee" el ledger: tool inyectado vs. retrieval adaptado.

### Deferred Ideas (OUT OF SCOPE)

- Belgrano (dominio estudio) — agente posterior, mismo molde.
- OCR de fotos de recibos / ingesta automática de extractos bancarios.
- Hermes orquestador real (05-05 bloqueado).
- Multi-agente y rutinas (Fase 9).
- Categorización inteligente de gastos (vs. free-text).

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AGENT-07 | Cada agente respeta su presupuesto de modelos configurado | `src/gateway/cost.py:75-91` confirmed: `authorize(agent_id, ...)` already checks `_agent_budgets[agent_id]` and raises `BudgetExceeded`. Wiring chain confirmed end-to-end: `bootstrap/config.py:182` (`GatewayConfigModel.agent_budgets`) → `bootstrap/config.py:300` (`_to_gateway_settings`) → `bootstrap/gateway.py:73` (`CostTracker(agent_budgets=...)`) → `cost.py:87` (`authorize` reads it). Phase work = populate `[gateway.agent_budgets]` in `config.toml` (which does not exist yet) + E2E test. See Validation Architecture D4. |
| AGENT-09 | Belgrano/Pellegrini completa ≥3 tareas reales E2E reportando al orquestador | `src/orchestrator/dispatcher.py` + `FakeOrchestrator` fixture confirmed at `tests/orchestrator/conftest.py`. The 3 tasks are D-87. See Validation Architecture D2/D3 and Reference Dataset below. |

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Ledger persistence (transacciones) | Database/Storage (SQLite, own file `ledger.db`) | Core/domain (port `LedgerPort`) | Owner's financial data is domain state, not audit trail — separate file from `audit.db`/`pending.db` (confirmed pattern: each store gets its own SQLite file with its own WAL settings). |
| Ledger CRUD adapter | API/Backend equivalent — `src/ledger/sqlite_store.py` (new infra package) | — | Mirrors `orchestrator/pending_store.py` exactly; infra layer, never imported by `core`. |
| Ledger aggregation (SUM/GROUP BY) | Database/Storage (SQL layer inside adapter) | — | Failure mode #1 mitigation: arithmetic must happen in SQL, not in the LLM. Confirmed precedent: `cost.py:173` `month_spend_agent()` does exactly this windowed-SUM pattern. |
| CLI ingestion (`wyss fin add-*`) | API/Backend (Typer command in composition root) | — | Deterministic, no LLM in the loop; same tier as existing `wyss index`. |
| Conversational ingestion (`finance.record`) | API/Backend (action routed through policy engine before execution) | Agent runtime (ConfiguredAgent generates the plan step) | Must pass through `AgentBase.execute()` template method (`core/ports/agent.py:49-121`) — confirmed this is the ONLY path that enforces the second-wall rejection structurally. |
| Pellegrini agent reasoning | Agent runtime (`ConfiguredAgent`, gateway-mediated) | — | Zero new agent code (D-73) — config entry only. |
| Budget enforcement | Gateway (`cost.py::CostTracker.authorize`) | Bootstrap (composition root wires config → gate) | Gate code already exists and is correct; phase only wires config. Putting enforcement anywhere else would duplicate an already-correct primitive. |
| Orchestrator reporting | Orchestrator (daemon dispatcher + FakeOrchestrator) | — | Hermes real is deferred; this phase's E2E is genuine over the daemon+audit path, not a mock of the whole system. |

## Standard Stack

No new external dependencies. This phase is 100% in-repo runtime extension — confirmed against `pyproject.toml` and `uv.lock` (no `uv add` required).

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sqlite3` (stdlib) | Python 3.12+ runtime | Ledger store, WAL mode | Already the pattern for `audit.db`/`pending.db`; CLAUDE.md forbids SQLAlchemy ORM for this kind of schema |
| `tomllib` (stdlib) | Python 3.12+ runtime | Read `config.toml` | Already in use, confirmed `bootstrap/config.py` |
| `pydantic` v2 | already in lockfile | Validate `[[agents]]` / new ledger config models at the bootstrap boundary only | Confirmed pattern: `AgentConfigModel(BaseModel)` with `extra="forbid"`, `bootstrap/config.py:217-231` |
| `typer` + `rich` | already in lockfile | `wyss fin ...` subcommands | Confirmed existing pattern in `bootstrap/cli.py` |
| `pytest` | 9.0.3 (verified via `uv run pytest --version`) | Test suite — backbone of D1/D2/D4/D5 | Already the project's only test runner |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| none | — | — | No new supporting libraries identified for this phase |

### Alternatives Considered

(Per AI-SPEC §2 — re-confirmed, not re-litigated)

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| wyss-native ConfiguredAgent | LangChain/LangGraph | Forbidden in CLAUDE.md "What NOT to Use" — imposes its own ports against the hexagon |
| wyss-native ledger reasoning | LlamaIndex RAG | Wrong problem shape — no documents exist to index; data lives in a structured ledger, not a corpus |
| Protocol port for ledger | ABC | Repo convention reserves ABC for template-method cases (`AgentBase`); simple persistence ports are `Protocol` (confirmed `core/ports/persistence.py`) |

**Installation:**
```bash
# No new packages. Confirm lockfile is current:
uv sync
```

## Package Legitimacy Audit

**Not applicable** — this phase installs zero new external packages. All dependencies (`sqlite3`, `tomllib`, `pydantic`, `typer`, `rich`, `pytest`) are stdlib or already present in the project's `uv.lock`, confirmed by direct inspection. No slopcheck run needed.

## Architecture Patterns

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────────┐
                    │  Owner input                                  │
                    └───────────────┬───────────────────────────────┘
                                     │
              ┌──────────────────────┴──────────────────────┐
              │                                               │
     CLI path (deterministic)                     Conversational path
   `wyss fin add-gasto 5000 super`              "gasté 5000 en super hoy"
              │                                               │
              ▼                                               ▼
   bootstrap/cli.py (Typer cmd)                  ConfiguredAgent._run()
              │                                  generates Plan with
              │                                  Action(type="finance.record")
              │                                               │
              │                                               ▼
              │                                  CognitivePolicyEngine.evaluate()
              │                                  (segunda muralla — risk classification)
              │                                               │
              │                                  ┌────────────┴────────────┐
              │                                  │ REJECT/D → audit + raise │
              │                                  │ A/B/C → proceed          │
              │                                  └────────────┬────────────┘
              │                                               │
              └──────────────────────┬────────────────────────┘
                                      ▼
                          LedgerPort.record(Transaccion)
                                      │
                                      ▼
                   SqliteLedgerStore (WAL, own ledger.db file)
                                      │
                          ┌───────────┴───────────┐
                          │   transacciones table   │
                          └───────────┬───────────┘
                                      │
                     (separately, on advisory query)
                                      ▼
                  LedgerPort.query_by_category() / balance()
                  — SQL SUM/GROUP BY, pre-aggregated, windowed
                                      │
                                      ▼
              ConfiguredAgent._build_prompt() injects result as
              "## Hechos verificados del ledger (NO recalcular)"
              — explicitly OUTSIDE <untrusted_content>
                                      │
                                      ▼
                    gateway.ask(AgentModelRequest(agent_id="pellegrini"))
                                      │
                                      ▼
                  CostTracker.authorize("pellegrini", ...)
                  checks agent_budgets["pellegrini"] (5.0)
                          │                    │
                  under budget          over budget
                          │                    │
                          ▼                    ▼
                  provider call          raise BudgetExceeded
                  → cost.record()        (blocked, audited,
                  → trace → audit         never reaches provider)
                          │
                          ▼
                  Report → daemon dispatcher → FakeOrchestrator
                  (D-86 — genuine E2E over daemon+audit path)
```

### Recommended Project Structure
```
src/
├── core/
│   ├── domain/
│   │   └── ledger.py          # NEW: Transaccion (frozen dataclass, stdlib-only)
│   └── ports/
│       └── ledger.py          # NEW: LedgerPort (Protocol) — record/query_by_category/balance
├── ledger/                     # NEW infra package (mirrors audit/, orchestrator/)
│   ├── sqlite_store.py        # SqliteLedgerStore impl — WAL fail-fast, own ledger.db
│   └── schema.py               # DDL: CREATE TABLE transacciones + indexes
├── agents/                     # NO code changes — Pellegrini is config-only
├── bootstrap/
│   ├── config.py               # EDIT: _BASE_LEVELS additions, possible LedgerConfigModel
│   └── cli.py                   # EDIT: `wyss fin` sub-Typer app
├── core/policy/
│   └── builtin_deny.py          # NO changes — finance.* risk goes in _BASE_LEVELS, not BUILTIN_DENY
└── config/
    └── config.toml              # NEW FILE — does not exist yet in repo (verified)
```

### Pattern 1: WAL Fail-Fast SQLite Store
**What:** Connection opens with `PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`; if WAL mode is not actually achieved, close the connection and raise `AuditIntegrityError` immediately rather than silently degrading durability.
**When to use:** Any new SQLite-backed store in this codebase (confirmed at both `audit/sqlite_logger.py` and `orchestrator/pending_store.py`).
**Example:**
```python
# Source: src/orchestrator/pending_store.py (verified in-repo, lines 68-85 per PATTERNS.md)
PENDING_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",   # ledger uses NORMAL, not FULL (not an audit log)
    "PRAGMA busy_timeout=5000",
)

class SqliteLedgerStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        journal_mode: str | None = None
        for pragma in PENDING_PRAGMAS:
            row = self._conn.execute(pragma).fetchone()
            if pragma.endswith("WAL") and row is not None:
                journal_mode = str(row[0]).lower()
        if journal_mode != "wal":
            self._conn.close()
            raise AuditIntegrityError(f"ledger en {db_path}: WAL no disponible.")
        self._apply_schema()
```

### Pattern 2: Pre-Aggregated SQL, Never Raw Rows to the LLM
**What:** All arithmetic (totals, balances, surplus) happens via `SUM`/`GROUP BY` with an explicit date-window filter in the adapter; the LLM only ever receives the already-reduced numeric result.
**When to use:** Any ledger query that feeds Pellegrini's prompt — this is the structural fix for AI-SPEC failure mode #1 (hallucinated arithmetic).
**Example:**
```python
# Source: src/gateway/cost.py:173-180 (verified in-repo) — the exact windowed-SUM precedent to mirror
def month_spend_agent(self, agent_id: str) -> float:
    (total,) = self._conn.execute(
        "SELECT COALESCE(SUM(cost_usd_local), 0.0) FROM spend_ledger "
        "WHERE agent_id = ? AND created_at >= ?",
        (agent_id, self._month_start_iso()),
    ).fetchone()
    return float(total)
```

### Pattern 3: Second-Wall Enforcement via Template Method (not a runtime check you write)
**What:** `AgentBase.execute()` (`core/ports/agent.py:49-121`, full method read and confirmed in this research) rejects any `Plan` with `Outcome.REJECT` or `risk_level >= RiskLevel.D` **before** calling `_run()`. This is structural, not optional — there is no code path that can skip it because `_run()` is only reachable from inside `execute()`.
**When to use:** Every `finance.record` step must arrive as part of a `Plan` evaluated through `CognitivePolicyEngine.evaluate()` and passed to `execute()`. Do not invoke ledger writes directly from parsed LLM output.
**Example:**
```python
# Source: src/core/ports/agent.py (verified in-repo, full method read)
def execute(self, plan: Plan, decision: PolicyDecision) -> Report:
    risk = decision.risk_level
    outcome = decision.outcome
    if (
        not isinstance(risk, RiskLevel)
        or not isinstance(outcome, Outcome)
        or outcome == Outcome.REJECT
        or risk >= RiskLevel.D
    ):
        self._audit.log(AuditEvent.new(...))  # rejection is audited
        raise PolicyViolation(f"plan {plan.task_id} rechazado: nivel {level}")
    # only reachable here if approved:
    report = self._run(plan)
```

### Anti-Patterns to Avoid
- **Re-implementing the cost gate:** `cost.py::CostTracker.authorize/reserve/release/record` already enforces per-agent budget (confirmed lines 75-91, 108, 117, 173). Touching `cost.py` is scope creep for AGENT-07 and risks breaking the "no runtime setters for limits" invariant (D-19, referenced in AI-SPEC).
- **Writing to the ledger outside the policy engine:** A `finance.record` executed directly from LLM-parsed text without going through `engine.evaluate()` violates D-70/D-84 and breaks the structural guarantee in Pattern 3 above.
- **Letting the LLM compute totals:** The prompt must never ask the model to sum amounts — confirmed as AI-SPEC failure mode #1 and explicitly called out in `configured_agent.py`'s existing `_format_hits_safe()` precedent for treating retrieved content as data, not as something to "process" mathematically.
- **Putting the SQLite adapter inside `core/`:** `core/ports/ledger.py` is a `Protocol`; the concrete `SqliteLedgerStore` belongs in the new `ledger/` infra package. Confirmed: `pyproject.toml`'s `import-linter` contract `"core es puro: stdlib only"` forbids `core` importing infra packages — and currently does **not** list `ledger` as a root_package, so it must be added or the contract silently fails to protect the new code (see Common Pitfalls #4).
- **Validating ledger config with Pydantic inside `core`:** Pydantic must die at the `bootstrap/config.py` boundary; `core.domain.ledger.Transaccion` must be a stdlib `@dataclass(frozen=True, slots=True)`, confirmed pattern at `core/domain/agent.py`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Per-agent budget enforcement | A new budget-check function in the agent or ledger code | `CostTracker.authorize(agent_id, ...)` — already implemented, confirmed at `cost.py:75-91` | Re-implementing duplicates an already-correct, already-tested primitive and risks divergent semantics from the global budget check |
| Risk classification of mutating actions | A bespoke "is this safe" check inside the ledger adapter | `CognitivePolicyEngine.evaluate()` + `_BASE_LEVELS` dict entries for `finance.record`/`finance.query` | The denylist-as-data + aggregate-threshold engine is the sole authority on risk; a parallel check would create two sources of truth |
| SQLite durability handling | Custom retry/backoff around `sqlite3.OperationalError` | The existing WAL fail-fast pattern (`busy_timeout=5000`, explicit `journal_mode` verification at connect time) | Already solved twice in this codebase (audit, pending_store); a third bespoke implementation is inconsistency risk, not a feature |
| Action-type → risk mapping config | A new config mechanism (e.g. separate YAML/JSON for ledger risk) | `_BASE_LEVELS: dict[str, RiskLevel]` in `bootstrap/config.py` (same dict that already holds `file.*`/`shell.run`) | One mapping table, one place to audit; splitting it defeats the purpose of having a single classification surface |

**Key insight:** Every piece of "new" infrastructure logic this phase appears to need (budget gate, risk classification, durable storage primitives) already exists in the codebase in a form designed to be extended by adding entries, not by adding code. The actual net-new code is narrow: the `Transaccion` domain type, the `LedgerPort` protocol, the `SqliteLedgerStore` adapter, the CLI subcommands, and the prompt-injection block for ledger facts.

## Common Pitfalls

### Pitfall 1: Setting `[[agents]].budget_usd` without also setting `[gateway.agent_budgets]`
**What goes wrong:** The cost gate silently does not enforce — `cost.py:87` reads `self._agent_budgets.get(agent_id)`, which is populated exclusively from `[gateway].agent_budgets` (confirmed chain: `bootstrap/config.py:182,300` → `bootstrap/gateway.py:73`). `AgentDefinition.budget_usd` (from `[[agents]]`) is a separate, currently-unconsumed field.
**Why it happens:** Two fields with the same name (`budget_usd`) exist in two unrelated config sections, and only one feeds the actual enforcement path. This is exactly the gap PATTERNS.md flags ("Hallazgo crítico").
**How to avoid:** The plan must explicitly populate both `[[agents]].budget_usd = 5.0` (informational/future) AND `[gateway.agent_budgets] pellegrini = 5.0` (the one that matters) in the new `config.toml`. Consider whether `_to_agent_definition` should derive the second from the first — flagged in PATTERNS.md as a design gap to resolve in planning, not assume.
**Warning signs:** AGENT-07's E2E test passes for the wrong reason (e.g. a global budget cap triggers first) or doesn't trigger at all even after many calls.

### Pitfall 2: `config.toml` does not exist yet
**What goes wrong:** PATTERNS.md and AI-SPEC both refer to "editing" `config.toml`, but `find . -maxdepth 2 -iname "config*"` in the actual repo returns nothing — only `tests/bootstrap/test_agent_config.py`'s `_VALID_AGENT_TOML` string constant shows the expected shape.
**Why it happens:** Phases 1-7 built the parsing logic and tested it against in-memory TOML strings; no phase has yet shipped a real runtime config file.
**How to avoid:** Treat "create `config/config.toml` with a real `[[agents]]` Pellegrini entry + `[gateway.agent_budgets]`" as an explicit task, not an edit. Verify the exact section name/path the loader expects (`load_settings(config_path)` signature in `bootstrap/cli.py`) before assuming `config/config.toml` is the right location.
**Warning signs:** Tests pass (they use in-memory TOML) but `wyss fin add-gasto` fails at runtime with `ConfigError` or `FileNotFoundError` because there's no file for it to load.

### Pitfall 3: `import-linter` doesn't yet know about the new `ledger` package
**What goes wrong:** `pyproject.toml`'s `[tool.importlinter]` currently lists `root_packages = ["core", "orchestrator", "agents", "knowledge", "gateway", "execution", "audit", "bootstrap"]` — `ledger` is absent. Until added, `lint-imports` will not catch a `core` → `ledger` import violation, silently leaving a hexagon hole.
**Why it happens:** The contract is additive/explicit — new packages must be registered, they aren't auto-discovered.
**How to avoid:** Add `"ledger"` to `root_packages`, to the `forbidden_modules` list of the `"core es puro"` contract, and to the `modules` list of the `"las capas importan de core, nunca entre sí"` independence contract. Confirm whether `bootstrap` should also join that second contract (currently it does not, consistent with being the composition root).
**Warning signs:** `lint-imports` passes locally even though `core/ports/ledger.py`'s implementation accidentally imports `sqlite3` directly, or `agents/` imports `ledger/sqlite_store.py` directly instead of going through the port.

### Pitfall 4: No `pytest -m llm_judge` marker registered
**What goes wrong:** A test decorated `@pytest.mark.llm_judge` runs anyway (or pytest warns `PytestUnknownMarkWarning`) because `pyproject.toml`'s `markers` list (currently `ntfs`, `integration`, `gateway`) doesn't include it.
**Why it happens:** D3's LLM-judge eval is genuinely new — no existing test in the suite uses this pattern (confirmed: zero matches for `llm_judge` in the repo).
**How to avoid:** Add `"llm_judge: low-ceremony LLM-judge eval, opt-in only (consumes agent budget)"` to the markers list as part of this phase's bootstrap work, alongside the actual judge test.
**Warning signs:** CI accidentally runs (and pays for) the LLM-judge test on every push instead of on-demand only.

### Pitfall 5: `finance.record` and `finance.query` have no action-type precedent to copy
**What goes wrong:** Every existing `Action.type` in the codebase is a generic execution primitive (`file.*`, `shell.run`, `git.push`) — there is no existing example of a *domain-specific* business action with its own `parameters` contract. Inventing the shape ad hoc risks an awkward fit with `CognitivePolicyEngine`'s pattern-matching (`target_patterns` via fnmatch, `params_equal` via dict equality).
**Why it happens:** This is genuinely greenfield — confirmed by PATTERNS.md's "Sin Analog Encontrado" table and independently verified by reading `builtin_deny.py` and `plan.py` in full (all 7 built-in rules target generic file/shell/git operations).
**How to avoid:** Design `finance.record`'s `parameters: Mapping[str, object]` deliberately (e.g. `{"tipo": "gasto", "monto": 5000.0, "categoria": "super", "fecha": "2026-06-16"}`) before writing the policy classification, since the denylist/risk engine matches on this shape. Decide explicitly whether negative amounts or future dates warrant a `DenyRule`, or whether `RiskLevel.B` confirmation is sufficient (per AI-SPEC's suggested levels: `finance.query` → A, `finance.record` → B).
**Warning signs:** The policy engine accepts a `finance.record` action with nonsensical parameters (e.g. negative amount) because no rule was written to catch it, and this is only discovered by the owner manually.

## Code Examples

### Cost gate authorize/record/release contract (verified, do not modify)
```python
# Source: src/gateway/cost.py (verified in-repo, lines 75-117)
def authorize(self, agent_id: str, ..., est: float) -> None:
    """Veta con BudgetExceeded si gasto + en-vuelo + estimado excede global o cap."""
    if <global check fails>:
        raise BudgetExceeded("presupuesto global mensual agotado")
    cap = self._agent_budgets.get(agent_id)
    if cap is not None and self.month_spend_agent(agent_id) + inflight_agent + est > cap:
        raise BudgetExceeded(f"presupuesto del agente {agent_id} agotado")

def release(self, agent_id: str, amount: float) -> None: ...
def record(self, ...) -> None: ...
def month_spend_agent(self, agent_id: str) -> float: ...
```

### AgentConfigModel — the Pydantic boundary pattern to mirror for any ledger config
```python
# Source: src/bootstrap/config.py:217-231 (verified in-repo per PATTERNS.md cross-check)
class AgentConfigModel(BaseModel):
    """Entrada [[agents]]: extra='forbid' fail-closed — un typo aborta el boot."""
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    name: str
    domain: str
    knowledge_bases: list[str] = []
    model_tier: str = "economico"
    budget_usd: float = 0.0   # informational only — does NOT feed CostTracker directly
```

### Test fixture for FakeOrchestrator (E2E reporting path, D-86)
```python
# Source: tests/orchestrator/conftest.py (confirmed present; consumed by tests/orchestrator/test_daemon.py)
# Reuse directly — do not reimplement.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Phase 8 originally scoped as "agent over a document KB" (Belgrano-style) | Re-scoped during discuss-phase to "coach + ledger" MVP vertical (CONTEXT.md, D-82 through D-87) | 2026-06-16 (this phase's discussion) | The agent has no `Retrieval`/document KB to query at all — `knowledge_bases = []` in the `[[agents]]` entry is itself a decision that needs verification against `ConfiguredAgent._run()`'s behavior with an empty `kb_ids: frozenset()` (flagged open question below) |

**Deprecated/outdated:** None within this phase's scope — this is a forward extension of existing patterns, not a replacement of anything.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ConfiguredAgent._run()` tolerates `kb_ids=frozenset()` (empty knowledge bases) without error, since Pellegrini has no document KB | Standard Stack / State of the Art | If `_run()` assumes at least one KB and errors or behaves unexpectedly on empty `kb_ids`, the planner needs a small guard clause or a different wiring approach (e.g. treat ledger access as a `Tool` instead of `Retrieval`, sidestepping `kb_ids` entirely) — PATTERNS.md flags this exact question as unresolved. Recommend the planner verify this with a 5-minute code read of `ConfiguredAgent._run()` before committing to the Retrieval-adapter design over the Tool-injection design. |
| A2 | `config/config.toml` (vs. some other path) is where `load_settings()` expects the real runtime config | Common Pitfalls #2 | If the actual default path differs, the `wyss fin` CLI commands and the bootstrap composition root will silently look in the wrong place. Low risk — confirm by reading `bootstrap/cli.py`'s `--config` default value (PATTERNS.md cites `Path("config/config.toml")` as the existing default for the `index` command, which is a reasonable basis for this assumption, but it was not independently re-verified character-for-character in this research pass). |
| A3 | `RiskLevel.A` for `finance.query` / `RiskLevel.B` for `finance.record` (AI-SPEC's suggested levels) are correct per `docs/10-arquitectura-de-agentes.md` §7 | Don't Hand-Roll / Common Pitfalls #5 | AI-SPEC explicitly flags this as needing verification against §7 before fixing the final level — this research did not re-read that doc section. If `finance.record` should actually require RiskLevel.C (strong confirmation) because it's a financial-data mutation, the CLI/conversational UX changes meaningfully (confirmation prompt vs. simple y/N). |

## Open Questions

1. **Does `ConfiguredAgent._run()` work correctly with `kb_ids=frozenset()`?**
   - What we know: Pellegrini's `[[agents]]` entry per PATTERNS.md example sets `knowledge_bases = []`. The existing `Retrieval.search()` call path was designed for document-KB agents.
   - What's unclear: Whether an empty KB set short-circuits gracefully or whether `Retrieval` needs at least one `kb_id` to function, which would force the "Tool-injected ledger" design over the "Retrieval-adapter" design (AI-SPEC leaves this as planner's discretion).
   - Recommendation: Spend 10 minutes reading `ConfiguredAgent._run()` and `Retrieval.search()` signatures before the planner locks the ledger-read pattern. This is a small, bounded investigation, not a re-research task.

2. **Should `_to_agent_definition` derive `[gateway.agent_budgets][agent_id]` automatically from `[[agents]].budget_usd`, closing the two-field gap (Pitfall 1)?**
   - What we know: Both fields currently exist independently; only one is consumed by the gate.
   - What's unclear: Whether fixing this divergence in `bootstrap/config.py` is in scope for Phase 8 (it would benefit every future agent, not just Pellegrini) or whether it's deferred as "config duplication, acceptable for now."
   - Recommendation: Planner should decide explicitly — either (a) populate both fields manually in `config.toml` for Pellegrini (zero code change, accepted duplication) or (b) add the derivation in `_to_gateway_settings`/`_to_agent_definition` (small code change, fixes the gap for all agents going forward, very low risk given `agent_budgets: dict[str, float] = {}` already exists as a settable field). Option (b) is recommended given it's a ~3-line change and removes a footgun for every future `[[agents]]` entry (Belgrano next).

3. **Exact final RiskLevel for `finance.record`.**
   - What we know: AI-SPEC suggests B; PATTERNS.md repeats B as a starting point but flags "confirm against docs/10 §7 before fixing."
   - What's unclear: This research did not re-read `docs/10-arquitectura-de-agentes.md` §7 in full to independently confirm B is correct.
   - Recommendation: Planner reads §7 directly (short doc section) before finalizing `_BASE_LEVELS["finance.record"]`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 9.0.3 (verified via `uv run pytest --version`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `testpaths = ["tests"]`, `asyncio_mode = "auto"`, `markers = ["ntfs", "integration", "gateway"]` (verified; `llm_judge` marker NOT yet present — Wave 0 gap) |
| Quick run command | `uv run pytest tests/ -k "ledger or finance or budget" -q` |
| Full suite command | `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports` (the project's standard 4-tool gate per CLAUDE.md's orchestration runbook) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|-------------|
| AGENT-07 | Cost gate blocks Pellegrini's calls once `agent_budgets["pellegrini"]` (5.0) is exhausted, BEFORE the provider is touched | integration/E2E | `pytest tests/gateway/test_cost_agent_budget_e2e.py -x` | ❌ Wave 0 |
| AGENT-07 | `[gateway.agent_budgets].pellegrini` is correctly parsed from `config.toml` into `CostTracker` at boot | unit | `pytest tests/bootstrap/test_agent_budget_wiring.py -x` | ❌ Wave 0 |
| AGENT-09 | Ledger aggregation (`query_by_category`, `balance`, `surplus`) matches hand-computed fixture totals exactly | unit | `pytest tests/ledger/test_sqlite_store.py -x` | ❌ Wave 0 |
| AGENT-09 | `finance.record` action only executes after passing `CognitivePolicyEngine.evaluate()`; a non-owner-instructed write is rejected | integration | `pytest tests/agents/test_pellegrini_second_wall.py -x` | ❌ Wave 0 |
| AGENT-09 | All numerals in Pellegrini's advisory response trace back to the injected "Hechos verificados del ledger" block (no fabricated figures) | integration (regex assertion) | `pytest tests/agents/test_pellegrini_no_fabrication.py -x` | ❌ Wave 0 |
| AGENT-09 | 3 E2E advisory tasks (D-87) produce sensible, actionable advice and report via daemon dispatcher + FakeOrchestrator | E2E + LLM-judge (opt-in) | `pytest tests/agents/test_pellegrini_e2e.py -x` (deterministic parts) + `pytest -m llm_judge -k pellegrini` (advisory quality, on-demand) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -k "ledger or finance or budget" -q` — fast, deterministic, zero IA spend (D1, D2, D4, D5 dimensions from AI-SPEC §5).
- **Per wave merge:** Full suite: `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports` — the existing project-wide 4-tool gate (per CLAUDE.md orchestration runbook); this is non-negotiable per the project's existing close-out convention, not new to this phase.
- **Phase gate:** Full suite green + `pytest -m llm_judge -k pellegrini` run at least once manually by the owner (D3 calibration — AI-SPEC explicitly assigns the owner as final calibrator, judge as assistant only) before `/gsd:verify-work`.

### Wave 0 Gaps
- [ ] `tests/ledger/test_sqlite_store.py` — covers AGENT-09 aggregation correctness (D1/D2 from AI-SPEC §5); needs fixtures with hand-precomputed totals
- [ ] `tests/ledger/conftest.py` — fixtures: known transaction sets with manually-verified category totals, balance, surplus (mirrors `tests/orchestrator/conftest.py` style)
- [ ] `tests/gateway/test_cost_agent_budget_e2e.py` — covers AGENT-07 (D4); needs a fake/stub provider that counts invocations so the test can assert zero provider calls after `BudgetExceeded`
- [ ] `tests/bootstrap/test_agent_budget_wiring.py` — covers the config→gate wiring chain itself (distinct from the E2E behavioral test above); catches Pitfall 1 (two budget_usd fields) at the unit level
- [ ] `tests/agents/test_pellegrini_second_wall.py` — covers D5 (policy engine gate on `finance.record`); reuse `RecordingEngine`/`FakePlanRunner` fixtures already in `tests/agents/conftest.py`
- [ ] `tests/agents/test_pellegrini_no_fabrication.py` — covers D2; regex-extracts dollar amounts from Pellegrini's response and asserts each appears in the injected ledger-facts block
- [ ] `tests/agents/test_pellegrini_e2e.py` — covers AGENT-09's 3 D-87 tasks at the deterministic-assertion layer (reuses `tests/orchestrator/conftest.py`'s `FakeOrchestrator`)
- [ ] Pytest marker registration: add `"llm_judge: low-ceremony LLM-judge eval, opt-in only (consumes agent budget)"` to `pyproject.toml`'s `[tool.pytest.ini_options].markers` (currently absent — confirmed)
- [ ] `config/config.toml` itself does not exist yet — needs creation as part of this phase's bootstrap work (not test infra, but blocks any E2E test that loads real config rather than in-memory TOML strings)

*(All gaps above were independently verified absent by directory listing and grep — none are speculative.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | Single-owner local tool, no auth surface introduced by this phase |
| V3 Session Management | No | No session concept in scope |
| V4 Access Control | Yes | The second-wall policy engine (`CognitivePolicyEngine.evaluate`) is wyss's access-control primitive for mutating actions; `finance.record` must route through it (D-70/D-84) — already covered structurally by `AgentBase.execute()` |
| V5 Input Validation | Yes | `AgentConfigModel`/new ledger config models at the Pydantic boundary (`extra="forbid"`, fail-closed); `finance.record` action `parameters` shape needs explicit validation before it reaches SQL (parameterized queries only, never string-interpolated SQL — confirmed existing pattern uses `?` placeholders throughout `pending_store.py`/`cost.py`) |
| V6 Cryptography | No | No new cryptographic surface; ledger data is local SQLite, same trust model as `audit.db` |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| SQL injection via free-text category (D-83) | Tampering | Parameterized queries (`?` placeholders) exclusively — confirmed existing pattern in every SQLite store in this codebase; never f-string/format SQL with user-supplied `categoria` |
| Policy-engine bypass for ledger writes (executing `finance.record` directly from parsed LLM output, skipping `engine.evaluate()`) | Tampering / Elevation of Privilege | Structural enforcement via `AgentBase.execute()` template method (confirmed — no code path reaches `_run()` without passing the REJECT/D check first) |
| Non-owner-instructed ledger mutation (a `finance.record` derived from retrieved BC content rather than the owner's own words) | Tampering | D-71 invariant: only owner-instructed writes are permitted; this is a design/prompt-level guarantee, not a runtime type check — the planner should consider whether to add an explicit provenance flag on the action (e.g. `parameters["source"] = "owner_instructed"`) that a `DenyRule` could verify, since AI-SPEC currently treats this as a design invariant rather than a checked one |
| Budget-gate bypass via reentrant/concurrent calls (race between `authorize()` check and `record()`) | Denial of Service (of the budget itself — overspend) | Existing `reserve`/`release`/`record` three-phase pattern in `cost.py` (confirmed methods exist) is designed to close this race; phase work should not introduce a second call path that skips `reserve()` |

## Sources

### Primary (HIGH confidence — verified directly against repo source in this research session)
- `src/gateway/cost.py` (read in full relevant sections) — `authorize`/`release`/`record`/`month_spend_agent` signatures and budget-gate logic
- `src/bootstrap/config.py` (grepped + cross-checked) — `agent_budgets` field, `_BASE_LEVELS` dict, `AgentConfigModel`
- `src/bootstrap/gateway.py` (grepped) — `CostTracker` instantiation wiring
- `src/core/ports/agent.py` (read in full) — `AgentBase.execute()` template method, second-wall structural enforcement
- `src/core/domain/plan.py` (read in full) — `Action`/`Plan` dataclass shapes
- `src/core/policy/builtin_deny.py` (read in full) — all 7 `BUILTIN_DENY` rules, confirmed no domain-specific action-type precedent exists
- `pyproject.toml` (grepped) — `[tool.pytest.ini_options]` markers list (confirmed `llm_judge` absent), `[tool.importlinter]` (confirmed `ledger` absent from root_packages)
- Repo filesystem (via `find`/`ls`) — confirmed no `config.toml` exists anywhere in the repo; confirmed `tests/ledger/` directory does not exist
- `uv run pytest --version` — confirmed pytest 9.0.3 available and working

### Secondary (MEDIUM confidence — sourced from this phase's own upstream artifacts, cross-verified against source where load-bearing)
- `.planning/phases/08-primer-agente-de-dominio-finanzas/08-AI-SPEC.md` — design contract; all code-pattern claims independently re-verified against `src/` above and found accurate
- `.planning/phases/08-primer-agente-de-dominio-finanzas/08-PATTERNS.md` — file-by-file analog map; the "Hallazgo crítico" (two budget_usd fields) and "Sin Analog Encontrado" sections independently re-verified above and found accurate
- `.planning/phases/08-primer-agente-de-dominio-finanzas/08-CONTEXT.md` — locked decisions D-80 through D-87
- `.planning/REQUIREMENTS.md` — AGENT-07, AGENT-09 definitions
- `.planning/STATE.md` — phase history, confirms 05-05 (Hermes) blocker status feeding D-86

### Tertiary (LOW confidence)
- None — no WebSearch/external-ecosystem research was needed for this phase, since it is 100% in-repo extension of existing wyss-native patterns with zero new external dependencies.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, all existing libraries confirmed already in lockfile
- Architecture: HIGH — every pattern claim in AI-SPEC/PATTERNS.md cross-checked against actual `src/` files in this session, no discrepancies found
- Pitfalls: HIGH — all 5 pitfalls confirmed by direct repo inspection (grep/find), not inferred
- Validation Architecture: HIGH for test mapping structure (derived directly from AI-SPEC §5's 6 dimensions, which are themselves already grounded in a domain rubric); MEDIUM for exact file paths proposed (these are recommendations, not yet-existing files, so "correctness" will only be confirmed at planning/execution time)

**Research date:** 2026-06-16
**Valid until:** 30 days (stable in-repo architecture; revisit if Phase 7 patterns change before Phase 8 executes, or if `config.toml` is created by another phase first)
