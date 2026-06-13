# Phase 5: Orquestador Daemon — Pattern Map

**Mapped:** 2026-06-13
**Files analyzed:** 14 new/modified files
**Analogs found:** 13 / 14 (1 net-new: MCP server has no codebase analog)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/core/domain/plan.py` | model | transform | self (extend) | exact — modify in place |
| `src/core/ports/orchestrator.py` | port/protocol | request-response | `src/core/ports/gateway.py` | role-match |
| `src/orchestrator/daemon.py` | service | event-driven | `src/bootstrap/cli.py` (asyncio.run pattern) | partial |
| `src/orchestrator/dispatcher.py` | service | request-response | `src/core/ports/agent.py` (branch by outcome) | role-match |
| `src/orchestrator/intent_router.py` | service | request-response | `src/core/ports/agent.py` + gateway.py | partial |
| `src/orchestrator/mcp_server.py` | middleware | request-response | no analog — net-new | none |
| `src/orchestrator/pending_store.py` | service | CRUD | `src/audit/sqlite_logger.py` | role-match |
| `src/orchestrator/plan_renderer.py` | utility | transform | `src/bootstrap/cli.py` (_print_search_panels) | role-match |
| `src/orchestrator/ttl_reaper.py` | utility | event-driven | `src/audit/sqlite_logger.py` + asyncio pattern | partial |
| `src/adapters/hermes/hermes_adapter.py` | adapter | request-response | `src/gateway/gateway.py` (httpx async adapter) | role-match |
| `src/bootstrap/cli.py` | utility | request-response | self (extend existing) | exact — modify in place |
| `tests/orchestrator/conftest.py` | test | — | `tests/policy/conftest.py` | exact |
| `tests/orchestrator/test_pending_store.py` | test | — | `tests/audit/test_sqlite_logger.py` | exact |
| `tests/policy/test_golden_nl_plans.py` | test | — | `tests/policy/test_golden_plans.py` | exact |

---

## Pattern Assignments

### `src/core/domain/plan.py` (model — extend in place)

**Analog:** self (already read above)

**Current structure** (lines 1-36 of existing file — add after existing `Action` fields):
```python
# Existing Action — copy existing imports + dataclass decorator exactly:
from collections.abc import Mapping
from dataclasses import dataclass, field
from core.domain.risk import RiskLevel

@dataclass(frozen=True, slots=True)
class Action:
    type: str
    target: str
    parameters: Mapping[str, object] = field(default_factory=dict)
    # ADD at end (keyword-only with defaults — retro-compatible with positional tests):
    on_error: "ErrorPolicy" = field(default_factory=lambda: ErrorPolicy.ABORT)
    retry_params: "RetryParams | None" = None
```

**New types to add before `Action`** (StrEnum + frozen dataclass = pure domain, no Pydantic):
```python
from enum import StrEnum

class ErrorPolicy(StrEnum):
    RETRY    = "retry"
    ESCALATE = "escalate"
    ABORT    = "abort"

@dataclass(frozen=True, slots=True)
class RetryParams:
    max_attempts: int = 3
    backoff_base_s: float = 1.0
    backoff_max_s: float = 60.0
```

**Critical pitfall (Pitfall 3 from RESEARCH.md):** Before modifying, grep all existing `Action(...)` call sites:
```bash
grep -rn "Action(" /mnt/hdd/Data/10_Workspace/projects/wyss/tests/ \
  /mnt/hdd/Data/10_Workspace/projects/wyss/src/
```
Confirm no positional arg at position 4+ exists. Fields with defaults appended at end are retro-compatible.

---

### `src/core/ports/orchestrator.py` (port/protocol, request-response)

**Analog:** `src/core/ports/gateway.py` (lines 1-21)

**Imports pattern** (copy from gateway.py line 1-5, adapt):
```python
from typing import Protocol
from core.domain.plan import Plan
# IntentClassification lives in src/core/orchestrator/intent.py (new module)
```

**Core Protocol pattern** (mirror `ModelGatewayPort` structure — async methods, no implementations):
```python
class OrchestratorPort(Protocol):
    """Adapter del cerebro de orquestación. Hermes es la implementación concreta.
    Solo se invoca desde el daemon — NO desde agentes (vertical only, docs/10).
    """
    async def classify_intent(self, instruction: str) -> "IntentClassification": ...
    async def draft_plan(self, instruction: str, intent: "IntentClassification") -> Plan: ...
    async def health_check(self) -> bool: ...
```

**Pattern rule:** Every port in `src/core/ports/` uses `Protocol` (structural subtyping), never ABC. Compare with `gateway.py` line 17 (`class ModelGatewayPort(Protocol)`) and `audit.py` line 9 (`class AuditPort(Protocol)`). No imports from `adapters/` or infrastructure — pure domain + other ports only.

---

### `src/orchestrator/daemon.py` (service, event-driven asyncio)

**Analog:** `src/bootstrap/cli.py` (asyncio.run pattern, lines 235-281) + RESEARCH.md Pattern 1 & 2

**Imports pattern** (copy from cli.py lines 1-11, reduce to daemon needs):
```python
import asyncio
import json
import os
from pathlib import Path
from rich.console import Console
from audit.sqlite_logger import SqliteAuditLogger
from bootstrap.config import load_settings
from core.domain.errors import AuditIntegrityError, ConfigError
```

**Stale socket cleanup** (RESEARCH.md Pattern 1 — no codebase analog, use research pattern verbatim):
```python
async def _cleanup_stale_socket(path: Path) -> None:
    if not path.exists():
        return
    try:
        _r, w = await asyncio.open_unix_connection(str(path))
        w.close()
        await w.wait_closed()
        raise RuntimeError(f"Daemon ya corriendo en {path}")
    except (ConnectionRefusedError, FileNotFoundError):
        path.unlink(missing_ok=True)
```

**Socket permissions pattern** (security — D-59 invariant, set immediately after bind):
```python
os.chmod(socket_path, 0o600)  # Unix socket accesible solo por el owner
```

**Error handling pattern** — copy from cli.py lines 269-274 (same exception taxonomy):
```python
except (ConfigError, AuditIntegrityError) as exc:
    console.print(f"Error: {exc}", style="red")
    raise SystemExit(1) from exc
except (OSError, sqlite3.Error) as exc:
    console.print(f"Error sistémico: {exc}", style="red")
    raise SystemExit(1) from exc
```

**Cleanup pattern** (copy from cli.py `finally` block structure lines 275-281):
```python
finally:
    socket_path.unlink(missing_ok=True)
    if audit is not None and hasattr(audit, "close"):
        audit.close()
```

---

### `src/orchestrator/dispatcher.py` (service, request-response — branches by PolicyDecision.outcome)

**Analog:** `src/core/ports/agent.py` (lines 49-121 — outcome branching + audit pattern)

**Core branching pattern** (copy from agent.py lines 60-88, adapt to async + daemon context):
```python
# agent.py uses: if outcome == Outcome.REJECT or risk >= RiskLevel.D → audit + raise
# dispatcher.py: same branch, but returns dict instead of raising (daemon never crashes a client)

from core.domain.risk import Outcome, RiskLevel
from core.domain import AuditEvent, AuditEventType, ActorType

async def dispatch(plan: Plan, decision: PolicyDecision, ...) -> dict:
    if decision.outcome == Outcome.REJECT or decision.risk_level >= RiskLevel.D:
        audit.log(AuditEvent.new(
            task_id=plan.task_id,
            actor_type=ActorType.SYSTEM,
            actor_id="daemon",
            event_type=AuditEventType.POLICY_DECISION,
            message="plan rechazado por política",
            payload={"risk_level": decision.risk_level.name,
                     "reasons": list(decision.reasons)},
        ))
        return {"outcome": "rejected", "reasons": list(decision.reasons)}
    if decision.outcome in (Outcome.CONFIRM_SIMPLE, Outcome.CONFIRM_STRONG):
        pending_id = pending_store.save(plan, decision)
        return {"outcome": "pending", "pending_id": pending_id, "plan": render(plan)}
    # EXECUTE (A — direct dispatch queue)
    execution_id = _enqueue(plan)
    return {"outcome": "queued", "execution_id": execution_id}
```

**Audit pattern** — copy from agent.py lines 90-120: log ACTION_STARTED before, TASK_FAILED/TASK_COMPLETED in try/except/else. Same three-event structure.

---

### `src/orchestrator/intent_router.py` (service, request-response)

**Analog:** `src/gateway/gateway.py` lines 64-80 (constructor with injected dependencies)

**Imports pattern:**
```python
from dataclasses import dataclass
from enum import StrEnum
from core.ports.orchestrator import OrchestratorPort
```

**IntentClassification domain object** (pure dataclass, no Pydantic — follows plan.py pattern):
```python
class IntentCategory(StrEnum):
    KNOWLEDGE_QUERY    = "knowledge_query"
    FILE_OPERATION     = "file_operation"
    SYSTEM_OPERATION   = "system_operation"
    CONFIGURATION      = "configuration"
    DANGEROUS_OPERATION = "dangerous_operation"
    AMBIGUOUS_REQUEST  = "ambiguous_request"
    STATUS_QUERY       = "status_query"
    ROUTINE_TRIGGER    = "routine_trigger"
    UNKNOWN            = "unknown"

@dataclass(frozen=True, slots=True)
class IntentClassification:
    category: IntentCategory
    confidence: float
    clarification_needed: bool
```

**Degradation pattern** (D-60) — mirror the cli.py degraded banner pattern (line 488):
```python
# If OrchestratorPort.health_check() returns False:
return {
    "outcome": "degraded",
    "message": "Orquestador Hermes no disponible. Consultas de conocimiento siguen activas.",
}
```

---

### `src/orchestrator/mcp_server.py` (middleware, request-response — net-new, NO codebase analog)

**Analog:** none — use RESEARCH.md Pattern 3 verbatim

**Key invariant (Pitfall 2 from RESEARCH.md):** Every `@mcp.tool()` handler MUST:
1. Construct a single-`Action` `Plan` from the tool call parameters
2. Call `engine.evaluate(plan)` — never skip this
3. Branch by `outcome` (REJECT → return error string; CONFIRM → return PENDING:id; EXECUTE → enqueue)

```python
from fastmcp import FastMCP
from core.policy import CognitivePolicyEngine
from core.domain.plan import Plan, Action

mcp = FastMCP("wyss-tools")

@mcp.tool()
async def execute_plan(plan_json: str) -> str:
    """Hermes submits a Plan JSON (D-51). Engine evaluates — Hermes never sets the level (D-50)."""
    plan = Plan(**json.loads(plan_json))
    decision = engine.evaluate(plan)          # ALWAYS — no shortcut
    audit.log(AuditEvent.new(...))
    match decision.outcome:
        case Outcome.REJECT:
            return f"REJECTED: {decision.reasons}"
        case Outcome.CONFIRM_SIMPLE | Outcome.CONFIRM_STRONG:
            pending_id = pending_store.save(plan, decision)
            return f"PENDING:{pending_id}"
        case _:
            execution_id = dispatch_queue.enqueue(plan)
            return f"QUEUED:{execution_id}"
```

**Startup pattern** (run in daemon background task — not blocking the Unix socket loop):
```python
def start_mcp_server(host: str = "127.0.0.1", port: int = 7420) -> None:
    mcp.run(transport="http", host=host, port=port)
```

---

### `src/orchestrator/pending_store.py` (service, CRUD)

**Analog:** `src/audit/sqlite_logger.py` (lines 1-146) + `src/audit/schema.py` (lines 1-55)

**Imports pattern** (copy from sqlite_logger.py lines 9-18):
```python
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from core.domain.errors import AuditIntegrityError  # reuse existing error type
```

**WAL verification pattern** (copy from sqlite_logger.py lines 43-57 verbatim — same fail-fast logic):
```python
def __init__(self, db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    self._conn = sqlite3.connect(db_path)
    journal_mode: str | None = None
    for pragma in PENDING_PRAGMAS:
        row = self._conn.execute(pragma).fetchone()
        if pragma.endswith("WAL") and row is not None:
            journal_mode = str(row[0]).lower()
    if journal_mode != "wal":
        self._conn.close()
        raise AuditIntegrityError(
            f"pending_store en {db_path}: WAL no disponible sobre este filesystem."
        )
    _apply_schema(self._conn)
```

**PRAGMAs** (from RESEARCH.md Pattern 4 — NORMAL not FULL because pending is not audit-critical):
```python
PENDING_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
)
```

**Schema** (from RESEARCH.md Pattern 4 — copy SQL exactly):
```sql
CREATE TABLE IF NOT EXISTS pending_proposals (
    id           TEXT PRIMARY KEY,
    task_id      TEXT NOT NULL,
    plan_json    TEXT NOT NULL,
    risk_level   TEXT NOT NULL,
    outcome      TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL,
    resolved_at  TEXT,
    resolved_by  TEXT
);
CREATE INDEX IF NOT EXISTS idx_pending_status ON pending_proposals(status, expires_at);
```

**Insert pattern** (copy from sqlite_logger.py lines 61-79 — parameterized, commit per write):
```python
def save(self, plan: Plan, decision: PolicyDecision, ttl_seconds: int) -> str:
    pending_id = uuid.uuid4().hex
    now = datetime.now(UTC).isoformat()
    expires_at = datetime.fromtimestamp(
        datetime.now(UTC).timestamp() + ttl_seconds, UTC
    ).isoformat()
    self._conn.execute(
        "INSERT INTO pending_proposals (id, task_id, plan_json, risk_level, outcome, "
        "created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (pending_id, plan.task_id, json.dumps(_plan_to_dict(plan)),
         decision.risk_level.name, decision.outcome.name, now, expires_at),
    )
    self._conn.commit()
    return pending_id
```

**context manager pattern** (copy from sqlite_logger.py lines 136-145 — `__enter__`/`__exit__` closing `self._conn`).

---

### `src/orchestrator/plan_renderer.py` (utility, transform)

**Analog:** `src/bootstrap/cli.py` lines 491-506 (`_print_search_panels`) and lines 447-456 (`_print_estimate`)

**Imports pattern** (copy from cli.py lines 14-17):
```python
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
```

**Rich Panel pattern** (copy from cli.py lines 498-506 — same structure for B/C confirmation display):
```python
def render_plan(plan: Plan, decision: PolicyDecision, console: Console) -> None:
    body = (
        f"Resumen: {plan.summary}\n"
        f"Nivel: {decision.risk_level.name}\n"
        f"Pasos: {len(plan.steps)}\n\n"
        + "\n".join(f"  {i+1}. [{a.type}] {a.target}" for i, a in enumerate(plan.steps))
    )
    console.print(Panel(body, title=f"Plan propuesto — nivel {decision.risk_level.name}", expand=False))
```

**Confirmation prompt pattern** (B = `[s/N]`, C = requires typing `CONFIRMAR` — from CONTEXT.md D-54):
```python
def prompt_confirmation(decision: PolicyDecision, console: Console) -> bool:
    if decision.risk_level == RiskLevel.B:
        resp = console.input("[bold yellow]Confirmar? [s/N]: [/]").strip().lower()
        return resp == "s"
    # Level C: require explicit string
    resp = console.input("[bold red]Escribí CONFIRMAR para continuar: [/]").strip()
    return resp == "CONFIRMAR"
```

---

### `src/orchestrator/ttl_reaper.py` (utility, event-driven asyncio)

**Analog:** `src/audit/sqlite_logger.py` (audit logging pattern) + RESEARCH.md Pattern 4 TTL Reaper

**Imports pattern:**
```python
import asyncio
from core.domain import AuditEvent, AuditEventType, ActorType
from core.ports.audit import AuditPort
```

**Background task pattern** (from RESEARCH.md — asyncio loop with sleep):
```python
async def ttl_reaper(pending_store: "PendingStore", audit: AuditPort,
                     interval_s: float = 30.0) -> None:
    while True:
        expired = pending_store.expire_old()
        for proposal in expired:
            audit.log(AuditEvent.new(
                task_id=proposal.task_id,
                actor_type=ActorType.SYSTEM,
                actor_id="ttl_reaper",
                event_type=AuditEventType.POLICY_DECISION,
                message="propuesta expirada por TTL — auto-rechazada",
                payload={"pending_id": proposal.id, "risk_level": proposal.risk_level},
            ))
        await asyncio.sleep(interval_s)
```

**Audit pattern** (copy AuditEvent.new call signature from sqlite_logger.py lines 96-109 — same 5 keyword args: task_id, actor_type, actor_id, event_type, message, optional payload).

---

### `src/adapters/hermes/hermes_adapter.py` (adapter, request-response)

**Analog:** `src/gateway/gateway.py` lines 64-80 (httpx async client + constructor injection)

**Imports pattern** (copy from gateway.py lines 25-46, reduce to adapter needs):
```python
import httpx
import json
from core.domain.plan import Plan
from core.ports.orchestrator import OrchestratorPort
# OrchestratorUnavailable: new domain error to add to core.domain.errors
```

**Constructor pattern** (copy from gateway.py lines 67-80 — keyword-only args, httpx.AsyncClient):
```python
class HermesOrchestrator:
    def __init__(self, *, base_url: str, api_key: str, model: str) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=60.0)
        self._api_key = api_key
        self._model = model
```

**HTTP call pattern** (copy from gateway.py lines 80+ — headers, json body, raise_for_status):
```python
async def classify_intent(self, instruction: str) -> IntentClassification:
    try:
        resp = await self._client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self._model, "messages": [...], "response_format": {"type": "json_object"}},
        )
        resp.raise_for_status()
        # parse response
    except (httpx.HTTPError, KeyError, json.JSONDecodeError) as exc:
        raise OrchestratorUnavailable(f"Hermes no disponible: {exc}") from exc
```

**Degradation pattern** (D-60 — mirror cli.py degraded banner at line 488, but as exception):
- Raise `OrchestratorUnavailable` (new error in `core.domain.errors`) from ALL httpx exceptions.
- Caller (dispatcher) catches it and returns degraded response dict — never propagates to client.

**health_check pattern** (short timeout, returns bool — no exception propagation):
```python
async def health_check(self) -> bool:
    try:
        resp = await self._client.get("/v1/models", timeout=2.0)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False
```

---

### `src/bootstrap/cli.py` (utility — extend existing, add 4 subcommands)

**Analog:** self (lines 213-375 — existing `index`, `search`, `status` commands)

**New command pattern** (copy from existing `search` command lines 284-351 — same structure):
```python
@app.command()
def start(
    config: Annotated[Path, typer.Option("--config")] = Path("config/config.toml"),
) -> None:
    """Levanta el daemon Wyss (ORCH-01)."""
    # Same: load_settings → try/except (ConfigError, AuditIntegrityError, OSError) → Exit(1)
    # asyncio.run(run_daemon(socket_path)) — blocking until shutdown
```

**`wyss ask` CLI client pattern** (from RESEARCH.md Code Examples — asyncio Unix socket client):
```python
@app.command()
def ask(instruction: str, config: ...) -> None:
    async def _ask() -> dict:
        try:
            reader, writer = await asyncio.open_unix_connection(str(socket_path))
        except FileNotFoundError:
            console.print("Daemon no está corriendo. Usar: wyss start", style="red")
            raise typer.Exit(1)
        try:
            req = json.dumps({"jsonrpc": "2.0", "method": "ask",
                              "params": {"instruction": instruction}, "id": 1})
            writer.write(req.encode() + b"\n")
            await writer.drain()
            resp = json.loads(await reader.readline())
            return resp.get("result", {})
        finally:
            writer.close()
            await writer.wait_closed()
    result = asyncio.run(_ask())
    _render_ask_result(result)  # uses Rich Panel pattern from plan_renderer
```

**Error handling** (copy from cli.py lines 339-344 — same exception types, same `stderr_console`):
```python
except (ConfigError, AuditIntegrityError) as exc:
    stderr_console.print(f"Error: {exc}", style="red")
    raise typer.Exit(code=1) from exc
```

---

### `tests/orchestrator/conftest.py` (test fixtures)

**Analog:** `tests/policy/conftest.py` (lines 1-44) — exact pattern

**Structure to copy** (policy conftest pattern verbatim):
```python
import pytest
from core.domain.policy import AggregateThresholds, PolicyRules
from core.domain.risk import RiskLevel
from core.policy import BUILTIN_DENY, CognitivePolicyEngine

@pytest.fixture
def engine() -> CognitivePolicyEngine:
    return CognitivePolicyEngine(PolicyRules(
        deny=BUILTIN_DENY,
        base_levels={...},  # same DEFAULT_BASE_LEVELS as policy conftest
        thresholds=AggregateThresholds(),
    ))
```

**Additional fixtures needed** (not in policy conftest — add here):
```python
@pytest.fixture
def pending_store(tmp_path: Path) -> Iterator["PendingStore"]:
    """PendingStore over tmp_path (ext4 — WAL works). Mirror of audit conftest logger fixture."""
    store = PendingStore(tmp_path / "pending.db")
    try:
        yield store
    finally:
        store.close()

@pytest.fixture
def fake_orchestrator() -> "FakeOrchestrator":
    """Deterministic stub implementing OrchestratorPort — Hermes is DOWN in unit tests."""
    # Returns preset IntentClassification and Plan without HTTP call
    ...
```

**Import path pattern** — copy from audit conftest lines 7-8: `from audit import SqliteAuditLogger` → adapt to `from orchestrator.pending_store import PendingStore`.

---

### `tests/orchestrator/test_pending_store.py` (test, CRUD)

**Analog:** `tests/audit/test_sqlite_logger.py` (lines 1-60) — exact pattern

**Structure to copy** (sqlite_logger test pattern):
```python
def test_wal_active(pending_store: "PendingStore", tmp_path: Path) -> None:
    """WAL active over tmp_path — mirror of test_sqlite_logger.test_wal_active."""
    conn = sqlite3.connect(tmp_path / "pending.db")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        conn.close()

def test_save_and_load_roundtrip(...) -> None: ...
def test_expire_old_sets_status_expired(...) -> None: ...
def test_confirm_rejects_expired_proposal(...) -> None: ...  # D-56 guard
def test_pending_survives_reopen(tmp_path: Path) -> None: ...  # ORCH-06 — key test
```

**Isolation pattern** (copy from sqlite_logger test line 16 `_read_conn`):
```python
def _read_conn(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)  # independent connection for verification
```

---

### `tests/policy/test_golden_nl_plans.py` (test, golden gate)

**Analog:** `tests/policy/test_golden_plans.py` (lines 1-155) — exact pattern + gate extension

**Structure to copy verbatim** (from golden_plans.py lines 6-28):
```python
from dataclasses import dataclass
import pytest
from core.domain.plan import Action, Plan
from core.domain.risk import RiskLevel
from core.policy import CognitivePolicyEngine

def _plan(*steps: Action, estimated: RiskLevel | None = None, task_id: str = "t") -> Plan:
    return Plan(task_id=task_id, summary="golden-nl", steps=tuple(steps),
                rationale="test", estimated_risk=estimated)
```

**Golden dataclass** (extend existing `Golden` with `instruction` and `intent` fields):
```python
@dataclass(frozen=True)
class NLGolden:
    instruction: str          # human-readable NL (for test id and error messages)
    intent: str               # IntentCategory value
    plan: Plan                # deterministic fixture — Hermes is DOWN, built manually
    expected: RiskLevel
```

**Parametrize pattern** (copy from golden_plans.py lines 121-128 verbatim — only the assert changes):
```python
@pytest.mark.parametrize("case", NL_GOLDEN_CASES, ids=lambda c: c.instruction[:40])
def test_nl_golden_plan_level(case: NLGolden, engine: CognitivePolicyEngine) -> None:
    decision = engine.evaluate(case.plan)
    falso_a = " — FALSO-A CATASTROFICO: ejecutaria sin confirmar"
    assert decision.risk_level == case.expected, (
        f"{case.instruction!r}: esperado {case.expected.name}, "
        f"obtuvo {decision.risk_level.name}"
        + (falso_a if decision.risk_level < case.expected else "")
    )
```

**Minimum fixture count:** 20 cases covering: A (read/query, ≥3), B (move/rename, ≥3), C (write/delete/sensitive, ≥5), D (denylist hits: mass-delete, audit-tamper, secret-exfiltration, system-files-write, git-force-push-main, disk-format — ≥6), ambiguous (≥2 that return clarification_needed without a Plan/D level).

---

## Shared Patterns

### Audit logging (AuditPort)
**Source:** `src/audit/sqlite_logger.py` lines 60-79 + `src/core/ports/agent.py` lines 71-88
**Apply to:** `daemon.py`, `dispatcher.py`, `mcp_server.py`, `ttl_reaper.py`, `hermes_adapter.py`

```python
# Pattern: always use AuditEvent.new() — never construct AuditEvent directly
audit.log(AuditEvent.new(
    task_id=plan.task_id,
    actor_type=ActorType.SYSTEM,   # or AGENT/OWNER/ORCHESTRATOR
    actor_id="daemon",             # component identifier string
    event_type=AuditEventType.POLICY_DECISION,
    message="human-readable description",
    payload={"key": "value"},      # optional Mapping[str, object]
))
```

### Fail-closed error handling
**Source:** `src/core/policy/engine.py` line 79 (`unknown_action_level` = C) + `src/core/ports/agent.py` lines 60-70
**Apply to:** `dispatcher.py`, `mcp_server.py`, `intent_router.py`

```python
# Unknown action type → C (never A). Unknown outcome → treat as REJECT.
# Corrupt types (non-enum, int casts from JSON) → REJECT (agent.py lines 64-70 pattern).
if not isinstance(risk, RiskLevel) or not isinstance(outcome, Outcome):
    # treat as REJECT — fail-closed
```

### SQLite connection management
**Source:** `src/audit/sqlite_logger.py` lines 35-58 (WAL verification) + lines 136-145 (context manager)
**Apply to:** `pending_store.py`

```python
# 1. mkdir parents, exist_ok
# 2. sqlite3.connect(db_path)
# 3. Run PRAGMAs; verify WAL result; raise AuditIntegrityError if not "wal"
# 4. apply_schema(conn) — idempotent IF NOT EXISTS DDL
# 5. Implement __enter__/__exit__ closing self._conn
```

### Rich CLI output
**Source:** `src/bootstrap/cli.py` lines 60-63 (console setup) + lines 491-506 (Panel pattern)
**Apply to:** `plan_renderer.py`, `cli.py` new commands

```python
console = Console()
stderr_console = Console(stderr=True)
# Errors → stderr_console.print(..., style="red")
# Info → console.print(Panel(body, title=..., expand=False))
```

### httpx async adapter
**Source:** `src/gateway/gateway.py` lines 64-80
**Apply to:** `hermes_adapter.py`

```python
# Constructor: keyword-only args, self._client = httpx.AsyncClient(base_url=..., timeout=60.0)
# Every method: try/except (httpx.HTTPError, KeyError, json.JSONDecodeError) → domain exception
# health_check: separate short timeout (2.0), return bool, never raise
```

### Typer subcommand
**Source:** `src/bootstrap/cli.py` lines 284-351 (`search` command — most similar to `ask`)
**Apply to:** New `start`, `ask`, `confirm`, `audit` commands in `cli.py`

```python
@app.command()
def command_name(
    param: str,
    config: Annotated[Path, typer.Option("--config")] = Path("config/config.toml"),
) -> None:
    try:
        settings = load_settings(config)
        # ... logic ...
    except (ConfigError, AuditIntegrityError) as exc:
        stderr_console.print(f"Error: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    except (OSError, sqlite3.Error) as exc:
        stderr_console.print(f"Error sistémico: {exc}", style="red")
        raise typer.Exit(code=1) from exc
    finally:
        # close resources
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `src/orchestrator/mcp_server.py` | middleware | request-response | No MCP server exists in codebase. Use RESEARCH.md Pattern 3 (FastMCP `@mcp.tool()` + `mcp.run(transport="http")`) as the reference. The invariant (every tool → engine.evaluate) must be enforced via tests. |

---

## New Domain Errors (add to `src/core/domain/errors.py`)

No analog file read for errors.py — but the pattern is established: every new error type is a plain `Exception` subclass with no extra behavior. Check existing errors for naming convention before adding:
```bash
grep -n "class.*Error" /mnt/hdd/Data/10_Workspace/projects/wyss/src/core/domain/errors.py
```
Add:
- `OrchestratorUnavailable` — raised by `HermesOrchestrator` on httpx failure (D-60)

---

## Metadata

**Analog search scope:** `src/core/`, `src/audit/`, `src/gateway/`, `src/bootstrap/`, `src/orchestrator/`, `tests/`
**Files read:** 14 source files
**Pattern extraction date:** 2026-06-13
