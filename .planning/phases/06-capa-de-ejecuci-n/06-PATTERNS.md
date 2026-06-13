# Phase 6: Capa de Ejecución - Pattern Map

**Mapped:** 2026-06-13
**Files analyzed:** 12 (7 src + 5 test infrastructure)
**Analogs found:** 12 / 12

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/execution/filesystem.py` | adapter / Tool impl | file-I/O + CRUD | `tests/ports/fakes.py` (FakeTool) + `src/audit/sqlite_logger.py` (WAL init pattern) | role-match |
| `src/execution/shell.py` | adapter / Tool impl | request-response | `tests/ports/fakes.py` (FakeTool contract) | role-match |
| `src/execution/git.py` | adapter / Tool impl | request-response | `tests/ports/fakes.py` (FakeTool contract) | role-match |
| `src/execution/journal.py` | service / SQLite store | CRUD | `src/orchestrator/pending_store.py` | exact |
| `src/execution/executor.py` | service / step loop | event-driven | `src/orchestrator/pending_store.py` (loop+state pattern) | role-match |
| `src/execution/__init__.py` | config / exports | — | `src/audit/__init__.py` | role-match |
| `tests/execution/__init__.py` | test / package marker | — | `tests/orchestrator/__init__.py` | exact |
| `tests/execution/conftest.py` | test / fixtures | — | `tests/orchestrator/conftest.py` | exact |
| `tests/execution/test_filesystem.py` | test / unit | file-I/O | `tests/audit/test_sqlite_logger.py` | role-match |
| `tests/execution/test_shell.py` | test / unit | request-response | `tests/orchestrator/test_pending_store.py` | role-match |
| `tests/execution/test_journal.py` | test / unit | CRUD | `tests/orchestrator/test_pending_store.py` | exact |
| `tests/execution/test_executor.py` | test / unit | event-driven | `tests/orchestrator/test_pending_store.py` | role-match |
| `tests/execution/test_second_wall.py` | test / unit | request-response | `tests/policy/test_golden_plans.py` (engine usage) | role-match |
| `tests/execution/test_git.py` | test / unit | request-response | `tests/orchestrator/test_pending_store.py` | role-match |

---

## Pattern Assignments

### `src/execution/filesystem.py` (adapter, file-I/O)

**Analog:** `tests/ports/fakes.py` lines 145-161 (FakeTool — the contract to mirror) + `src/audit/sqlite_logger.py` lines 35-58 (constructor/WAL-fail-fast pattern)

**Imports pattern** — mirror FakeTool's domain imports plus stdlib I/O:
```python
import hashlib
import os
import shutil
from pathlib import Path

from send2trash import send2trash

from core.domain.execution import ToolResult, Verification
from core.domain.plan import Action
from core.domain.risk import RiskLevel
from core.policy.engine import CognitivePolicyEngine
```

**Tool protocol contract** (from `src/core/ports/execution.py` lines 8-21 — implement ALL five members):
```python
class FileSystemAdapter:
    @property
    def name(self) -> str: ...          # "filesystem"

    @property
    def max_risk(self) -> RiskLevel: ...  # RiskLevel.C (handles file.delete)

    def describe(self, action: Action) -> str: ...

    async def execute(self, action: Action) -> ToolResult: ...

    async def verify(self, action: Action, result: ToolResult) -> Verification: ...
```

**Second-wall pattern (D-68)** — prepend to every `execute()` before any real I/O:
```python
# Source: src/core/policy/engine.py lines 29-31 + RESEARCH.md Pattern 1
import os
from pathlib import Path
from core.domain.plan import Plan

def _resolve_target(target: str) -> str:
    """Expand ~ and resolve symlinks. ~/Data -> /mnt/hdd/Data on this machine."""
    return str(Path(os.path.expanduser(target)).resolve())

# Inside execute():
resolved_target = _resolve_target(action.target)
resolved_action = Action(
    type=action.type,
    target=resolved_target,
    parameters=action.parameters,
    on_error=action.on_error,
    retry_params=action.retry_params,
)
resolved_plan = Plan(
    task_id="second-wall",
    summary="second-wall check",
    steps=(resolved_action,),
    rationale="path-resolution re-eval",
)
decision = self._engine.evaluate(resolved_plan)   # engine.py line 40 — pure, safe to call again
if decision.risk_level > self.max_risk or resolved_target != action.target:
    # self._audit.log(...)   <- AuditPort.log with EXEC_BLOCKED event
    return ToolResult(success=False, detail="blocked: second wall", payload={})
```

**Critical:** `CognitivePolicyEngine._normalize()` (engine.py line 29-31) calls `expanduser` only — NOT `resolve()`. The adapter MUST call `Path.resolve()` additionally. This is the whole point of the second wall.

**sha256 verification pattern (D-67 file.write)** — from RESEARCH.md Pattern 5:
```python
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
```

**verify() type-dispatch (D-67)**:
```python
async def verify(self, action: Action, result: ToolResult) -> Verification:
    if not result.success:
        return Verification(passed=False, detail="execute failed")
    resolved = Path(str(result.payload.get("resolved_target", action.target)))
    if action.type == "file.write":
        expected_hash = str(result.payload.get("sha256", ""))
        actual_hash = _sha256(resolved)
        passed = resolved.stat().st_size == result.payload.get("size") and actual_hash == expected_hash
        return Verification(passed=passed, detail=f"sha256={'ok' if passed else 'mismatch'}")
    if action.type == "file.move":
        src = Path(os.path.expanduser(action.target))
        passed = resolved.exists() and not src.exists()
        return Verification(passed=passed, detail="dest exists & src absent" if passed else "move verify failed")
    if action.type == "file.delete":
        trash_path = Path(str(result.payload.get("trash_path", "")))
        passed = not resolved.exists() and trash_path.exists()
        return Verification(passed=passed, detail="absent & in trash" if passed else "delete verify failed")
    return Verification(passed=result.success, detail="no type-specific verify")
```

**send2trash call + journal record order** — record to journal BEFORE mutation:
```python
# 1. journal.record(...)   <- before any I/O
# 2. send2trash(str(resolved_target))
# 3. verify(...)
```

**send2trash on NTFS** (from RESEARCH.md Pattern 3):
```python
from send2trash import send2trash

# Files on /mnt/hdd go to /mnt/hdd/.Trash-1000/files/ (per-volume, no EXDEV)
# Files on ~ go to ~/.local/share/Trash/files/
# Journal must store the exact trash_path so restore() can find the file
```

---

### `src/execution/shell.py` (adapter, request-response)

**Analog:** `tests/ports/fakes.py` lines 145-161 (FakeTool protocol), RESEARCH.md Pattern 4

**Imports pattern**:
```python
import asyncio
import shutil

from core.domain.execution import ToolResult, Verification
from core.domain.plan import Action
from core.domain.risk import RiskLevel
from core.policy.engine import CognitivePolicyEngine
```

**Allowlist enforcement (D-66) + argv exec pattern** — from RESEARCH.md Pattern 4:
```python
async def _exec_allowed(
    self, binary: str, args: list[str], cwd: str, timeout_s: float
) -> tuple[int, str, str]:
    """Execute binary from allowlist. shell=False always (D-66)."""
    if binary not in self._allowed_binaries:   # set[str] loaded from TOML at init
        # self._audit.log(EXEC_BLOCKED)
        raise ValueError(f"binary not in allowlist: {binary!r}")
    resolved = shutil.which(binary)
    if resolved is None:
        raise FileNotFoundError(f"binary not found: {binary!r}")

    proc = await asyncio.create_subprocess_exec(
        resolved, *args,           # argv list — NEVER shell string
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()   # drain to avoid zombie
        raise
    return proc.returncode, stdout.decode(), stderr.decode()
```

**TOML allowlist loading** — stdlib `tomllib`, mirror of config loading in `src/bootstrap/`:
```python
import tomllib

with open(config_path, "rb") as f:
    cfg = tomllib.load(f)
allowed_binaries: set[str] = set(cfg.get("allowed_binaries", []))
```

**Shell verify()** — exit code is the primary signal:
```python
async def verify(self, action: Action, result: ToolResult) -> Verification:
    returncode = result.payload.get("returncode")
    passed = result.success and returncode == 0
    return Verification(passed=passed, detail=f"returncode={returncode}")
```

**ShellAdapter has no journal entry** — shell commands are not reversible; no undo entry recorded. Shell is read-only or side-effect-only (not file mutations). If a shell command writes files, those files should go through FileSystemAdapter instead.

---

### `src/execution/git.py` (adapter, request-response)

**Analog:** `tests/ports/fakes.py` lines 145-161 (FakeTool protocol) + shell.py pattern (subprocess)

**Same `asyncio.create_subprocess_exec` pattern as ShellAdapter**, specialized for `git`:
```python
# GitAdapter wraps the git CLI binary directly (no GitPython — not in stack)
# Allowed git subcommands declared in TOML: ["status", "diff", "add", "commit", "log"]
# execute() calls _exec_allowed("git", [subcommand, *args], cwd=repo_path, timeout_s=30)
```

**Git verify()** — exit code + optional state check:
```python
async def verify(self, action: Action, result: ToolResult) -> Verification:
    returncode = result.payload.get("returncode")
    passed = result.success and returncode == 0
    # For git.commit: could additionally verify HEAD moved
    return Verification(passed=passed, detail=f"git returncode={returncode}")
```

---

### `src/execution/journal.py` (service, CRUD — SQLite WAL)

**Analog:** `src/orchestrator/pending_store.py` — **exact structural mirror**

**Imports pattern** (mirror pending_store.py lines 1-14):
```python
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from core.domain.errors import AuditIntegrityError
```

**WAL PRAGMAs** (mirror pending_store.py lines 16-20, using NORMAL not FULL — journal is operational not audit):
```python
JOURNAL_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",   # NORMAL (not FULL): journal is operational, not audit log
    "PRAGMA busy_timeout=5000",
)
```

**WAL fail-fast constructor** (mirror pending_store.py lines 68-85 exactly):
```python
def __init__(self, db_path: Path) -> None:
    self._db_path = db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    self._conn = sqlite3.connect(db_path)
    self._conn.row_factory = sqlite3.Row
    journal_mode: str | None = None
    for pragma in JOURNAL_PRAGMAS:
        row = self._conn.execute(pragma).fetchone()
        if pragma.endswith("WAL") and row is not None:
            journal_mode = str(row[0]).lower()
    if journal_mode != "wal":
        self._conn.close()
        raise AuditIntegrityError(
            f"undo journal en {db_path}: PRAGMA journal_mode retorno "
            f"{journal_mode!r}, se esperaba 'wal'. WAL no esta disponible "
            "sobre este filesystem."
        )
    self._apply_schema()
```

**Schema** (from RESEARCH.md Pattern 2):
```python
CREATE_JOURNAL = """
CREATE TABLE IF NOT EXISTS undo_entries (
  id           TEXT PRIMARY KEY,
  task_id      TEXT NOT NULL,
  step_index   INTEGER NOT NULL,
  action_type  TEXT NOT NULL,
  origin       TEXT NOT NULL,
  destination  TEXT,
  inverse_op   TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending',
  created_at   TEXT NOT NULL,
  resolved_at  TEXT
)
"""
# inverse_op is JSON: {"type": "file.move", "target": "...", "parameters": {...}}
# For file.write overwrite: inverse_op points to backup in data/undo_backups/{entry_id}
# For file.delete: inverse_op includes trash_path for recovery
```

**record() and restore() signatures** (mirror save()/resolve() in pending_store.py lines 87-159):
```python
def record(
    self,
    task_id: str,
    step_index: int,
    action: Action,
    origin: str,
    destination: str | None,
    inverse_op: dict[str, object],
) -> str:
    """Persist undo entry; return entry_id. Call BEFORE mutating."""
    entry_id = uuid.uuid4().hex
    now = datetime.now(UTC)
    self._conn.execute(_INSERT, (entry_id, task_id, step_index, ...))
    self._conn.commit()
    return entry_id

def restore(self, entry_id: str) -> bool:
    """Apply the inverse operation for a single entry. Returns True if rolled back."""
    ...

def mark_applied(self, entry_id: str) -> None:
    """After successful execution, mark entry status='applied'."""
    ...

def mark_rolled_back(self, entry_id: str) -> None:
    """After restore(), mark entry status='rolled_back'."""
    ...
```

**Context manager** (mirror pending_store.py lines 165-178):
```python
def __enter__(self) -> "UndoJournal": return self
def __exit__(self, exc_type, exc, tb) -> None: self.close()
def close(self) -> None: self._conn.close()
```

---

### `src/execution/executor.py` (service, step-loop + on_error enforcement)

**Analog:** No direct structural analog. Closest: `src/orchestrator/pending_store.py` (state management) + the `on_error` domain from `src/core/domain/plan.py` lines 10-24.

**Domain types to import** (plan.py lines 10-24):
```python
from core.domain.execution import ToolResult, Verification
from core.domain.plan import Action, ErrorPolicy, Plan, RetryParams
from core.domain.risk import RiskLevel
```

**on_error enforcement loop (D-69)** — three branches:
```python
# ErrorPolicy.ABORT (default): stop + rollback all applied steps in reverse
# ErrorPolicy.RETRY: retry up to RetryParams.max_attempts with backoff
# ErrorPolicy.ESCALATE: audit ESCALATE event, propagate (no rollback)

import asyncio

async def _retry_with_backoff(
    adapter, action: Action, params: RetryParams
) -> ToolResult:
    attempt = 0
    delay = params.backoff_base_s
    while attempt < params.max_attempts:
        result = await adapter.execute(action)
        if result.success:
            return result
        attempt += 1
        if attempt < params.max_attempts:
            await asyncio.sleep(min(delay, params.backoff_max_s))
            delay *= 2
    return result   # last failure
```

**Step dispatch by action.type prefix**:
```python
def _adapter_for(self, action: Action):
    prefix = action.type.split(".")[0]
    if prefix == "file":
        return self._filesystem
    if prefix == "shell":
        return self._shell
    if prefix == "git":
        return self._git
    raise ValueError(f"no adapter for action type: {action.type!r}")
```

---

### `src/execution/__init__.py` (config / exports)

**Analog:** `src/audit/__init__.py` (minimal re-export pattern)

Add adapter exports once files exist:
```python
from execution.filesystem import FileSystemAdapter
from execution.shell import ShellAdapter
from execution.git import GitAdapter
from execution.journal import UndoJournal
from execution.executor import PlanExecutor

__all__ = ["FileSystemAdapter", "ShellAdapter", "GitAdapter", "UndoJournal", "PlanExecutor"]
```

---

## Test Pattern Assignments

### `tests/execution/conftest.py`

**Analog:** `tests/orchestrator/conftest.py` lines 1-113 — **direct structural mirror**

**Key fixtures to replicate**:
```python
# From tests/orchestrator/conftest.py lines 36-44: engine fixture
@pytest.fixture
def engine() -> CognitivePolicyEngine:
    return CognitivePolicyEngine(
        PolicyRules(
            deny=BUILTIN_DENY,
            base_levels=DEFAULT_BASE_LEVELS,
            thresholds=AggregateThresholds(),
        )
    )

# From tests/orchestrator/conftest.py lines 107-113: store fixture with cleanup
@pytest.fixture
def journal(tmp_path: Path) -> Iterator[UndoJournal]:
    j = UndoJournal(tmp_path / "journal.db")
    try:
        yield j
    finally:
        j.close()
```

**FakeAudit class** (from tests/orchestrator/conftest.py lines 47-67 — copy verbatim):
```python
class FakeAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def log(self, event: AuditEvent) -> None:
        self.events.append(event)

    def span(self, task_id: str, actor: str, event: str) -> AbstractContextManager[Span]:
        return self._span_impl(task_id, actor, event)

    @contextmanager
    def _span_impl(self, task_id: str, actor: str, event: str) -> Iterator[Span]:
        yield Span(task_id=task_id, actor=actor, event=event, started_at=datetime.now(UTC))
```

**FakeEngine stub** (new — wraps real engine but allows per-test override):
```python
# Thin wrapper that records calls for test assertion
class RecordingEngine:
    def __init__(self, inner: CognitivePolicyEngine) -> None:
        self._inner = inner
        self.calls: list[Plan] = []

    def evaluate(self, plan: Plan) -> PolicyDecision:
        self.calls.append(plan)
        return self._inner.evaluate(plan)
```

---

### `tests/execution/test_journal.py`

**Analog:** `tests/orchestrator/test_pending_store.py` lines 1-137 — **exact structural mirror**

**WAL test** (mirror test_pending_store.py lines 49-60):
```python
def test_wal_active(journal: UndoJournal, tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "journal.db")
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert str(mode).lower() == "wal"
    finally:
        conn.close()
```

**Survives reopen test** (mirror test_pending_store.py lines 63-76):
```python
def test_entry_survives_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "journal.db"
    journal = UndoJournal(db_path)
    entry_id = journal.record(task_id="t-1", step_index=0, ...)
    journal.close()

    reopened = UndoJournal(db_path)
    try:
        entry = reopened.load(entry_id)
    finally:
        reopened.close()
    assert entry is not None
    assert entry.status == "pending"
```

---

### `tests/execution/test_filesystem.py`

**Analog:** `tests/audit/test_sqlite_logger.py` (structure) + `tests/orchestrator/conftest.py` (fixtures)

**NTFS opt-in marker pattern** (mirror test_sqlite_logger.py lines 218-231):
```python
@pytest.mark.ntfs
@pytest.mark.skipif(
    os.environ.get("WYSS_TEST_NTFS") != "1",
    reason="requiere WYSS_TEST_NTFS=1 (corre sobre el mount NTFS/fuseblk real)",
)
def test_send2trash_on_ntfs_mount() -> None:
    """send2trash on /mnt/hdd creates .Trash-1000/files/ entry — no EXDEV."""
    repo_root = Path(__file__).resolve().parents[2]
    test_file = repo_root / "data" / "trash_test_sentinel.txt"
    ...
```

**Unit test for delete (ext4/tmp_path)** — use `tmp_path` not `/tmp` directly (avoids TrashPermissionError):
```python
def test_delete_to_trash_ext4(tmp_path: Path) -> None:
    # tmp_path is on ext4 — send2trash works correctly
    # NEVER use /tmp directly: sticky-bit raises TrashPermissionError
    test_file = tmp_path / "delete_me.txt"
    test_file.write_text("x")
    adapter = FileSystemAdapter(engine=..., audit=..., journal=...)
    # ...
```

---

### `tests/execution/test_second_wall.py`

**Analog:** `tests/policy/test_golden_plans.py` (engine usage pattern) + `tests/orchestrator/conftest.py` (engine fixture)

**Core test structure**:
```python
def test_resolved_path_above_max_risk(engine: CognitivePolicyEngine, tmp_path: Path) -> None:
    """A symlink target that resolves to a denylist-matching path is blocked."""
    # Create symlink: tmp_path/link -> ~/.ssh (if exists) or a dangerous mock
    # Action uses the symlink path (pre-resolution)
    # Adapter resolves it -> real path hits denylist or exceeds max_risk
    # Result: ToolResult(success=False, detail="blocked: second wall")
    ...

def test_symlink_resolved_before_eval(engine: CognitivePolicyEngine, tmp_path: Path) -> None:
    """Path.resolve() expands ~/Data -> /mnt/hdd/Data (symlink on this machine)."""
    target = "~/Data/test_file.txt"
    resolved = str(Path(os.path.expanduser(target)).resolve())
    assert resolved.startswith("/mnt/hdd")  # verifies symlink was followed
```

---

### `tests/execution/test_executor.py`

**Analog:** `tests/orchestrator/test_pending_store.py` (state machine test pattern)

**on_error ABORT rollback test**:
```python
async def test_abort_rolls_back(
    engine: CognitivePolicyEngine, tmp_path: Path
) -> None:
    """ABORT policy: second step fails -> first step's journal entry is restored."""
    # step 1: file.write succeeds
    # step 2: file.write fails (file locked / permission denied)
    # Action.on_error = ErrorPolicy.ABORT
    # Expect: executor rolls back step 1 via journal.restore(entry_id)
```

**RETRY respects max_attempts**:
```python
async def test_retry_respects_max_attempts() -> None:
    # Adapter always returns ToolResult(success=False)
    # RetryParams(max_attempts=3)
    # Expect: adapter.execute called exactly 3 times, then failure returned
```

---

## Shared Patterns

### Tool Protocol Contract
**Source:** `src/core/ports/execution.py` lines 8-21
**Apply to:** `filesystem.py`, `shell.py`, `git.py` — all three must implement ALL five members with exact signatures (`describe` sync, `execute`/`verify` async)
```python
from typing import Protocol
from core.domain import Action, RiskLevel, ToolResult, Verification

class Tool(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def max_risk(self) -> RiskLevel: ...
    def describe(self, action: Action) -> str: ...
    async def execute(self, action: Action) -> ToolResult: ...
    async def verify(self, action: Action, result: ToolResult) -> Verification: ...
```

### SQLite WAL Fail-Fast Constructor
**Source:** `src/orchestrator/pending_store.py` lines 68-85
**Apply to:** `journal.py` — copy this constructor verbatim, replacing `PENDING_PRAGMAS` with `JOURNAL_PRAGMAS` and the error message text
```python
journal_mode: str | None = None
for pragma in JOURNAL_PRAGMAS:
    row = self._conn.execute(pragma).fetchone()
    if pragma.endswith("WAL") and row is not None:
        journal_mode = str(row[0]).lower()
if journal_mode != "wal":
    self._conn.close()
    raise AuditIntegrityError(...)
```

### Error Hierarchy
**Source:** `src/core/domain/errors.py`
**Apply to:** All new files
- `AuditIntegrityError` — reuse for journal WAL failure (already exists, line 12)
- `WyssError` — base for any new execution-specific errors (e.g., `ExecutionBlocked`, `AllowlistViolation`)
- New subclasses go in `src/core/domain/errors.py` following existing pattern (lines 4-27)

### Import Isolation (import-linter)
**Source:** `pyproject.toml` lines 103-113
**Apply to:** ALL `src/execution/` files
- `execution` is listed in the `independence` contract alongside `orchestrator`, `agents`, `knowledge`, `gateway`, `audit`
- **Forbidden:** any import of `orchestrator`, `agents`, `knowledge`, `gateway`, or `audit` from within `src/execution/`
- **Allowed:** `core.*` only (plus stdlib and third-party)

### asyncio_mode = "auto"
**Source:** `pyproject.toml` line 54
**Apply to:** All async tests in `tests/execution/`
- All `async def test_*` functions run automatically without `@pytest.mark.asyncio`
- No need to add the decorator — it is project-wide

### NTFS Opt-In Marker
**Source:** `tests/audit/test_sqlite_logger.py` lines 218-231 + `pyproject.toml` line 56
**Apply to:** Any test touching `/mnt/hdd` or `send2trash` on NTFS
```python
@pytest.mark.ntfs
@pytest.mark.skipif(
    os.environ.get("WYSS_TEST_NTFS") != "1",
    reason="requiere WYSS_TEST_NTFS=1 (corre sobre el mount NTFS/fuseblk real)",
)
def test_*_on_ntfs_mount() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    ...
```

### FakeTool Conformance Test
**Source:** `tests/ports/test_conformance.py` lines 106-108
**Apply to:** `tests/ports/test_conformance.py` — add conformance checks for real adapters
```python
def test_filesystem_adapter_conforms(tmp_path: Path) -> None:
    adapter: Tool = FileSystemAdapter(...)
    assert adapter is not None

def test_shell_adapter_conforms(...) -> None: ...
def test_git_adapter_conforms(...) -> None: ...
```

### Context Manager Close Pattern
**Source:** `src/orchestrator/pending_store.py` lines 161-178
**Apply to:** `journal.py` (UndoJournal needs same `__enter__`/`__exit__`/`close()` triple)

### Fixture with try/finally close
**Source:** `tests/orchestrator/conftest.py` lines 107-113 + `tests/audit/conftest.py` lines 13-19
**Apply to:** `tests/execution/conftest.py` — all SQLite-backed fixtures must close in `finally`:
```python
@pytest.fixture
def journal(tmp_path: Path) -> Iterator[UndoJournal]:
    j = UndoJournal(tmp_path / "journal.db")
    try:
        yield j
    finally:
        j.close()
```

---

## No Analog Found

All files have analogs. No entries needed.

---

## Critical Anti-Patterns (from RESEARCH.md — enforce in planning)

| What | Why | Source |
|---|---|---|
| `shell=True` in subprocess | Shell injection — no analog anywhere in codebase | RESEARCH.md §Anti-Patterns |
| `engine.evaluate_action(action)` | Method does not exist by design (engine.py docstring line 13) | `src/core/policy/engine.py` line 13 |
| `os.rename` for cross-FS moves | Raises `EXDEV` — use `shutil.move` | RESEARCH.md §Anti-Patterns |
| `send2trash` on `/tmp` paths | `TrashPermissionError` — tests must use `tmp_path` | RESEARCH.md Pitfall 2 |
| Journal on tmpfs in production | Journal must live in `data/` (NTFS mount verified) | RESEARCH.md Pitfall 3 |
| Hashing entire 2 TB on every verify | Size check first, hash only the written/moved file | RESEARCH.md §Anti-Patterns |
| File content inline in SQLite | Overwrite-undo backup goes to `data/undo_backups/{entry_id}`, not SQLite BLOB | RESEARCH.md Pitfall 5 |

---

## Metadata

**Analog search scope:** `src/` (all modules), `tests/` (all suites)
**Key files read:** `src/core/ports/execution.py`, `src/core/domain/execution.py`, `src/core/domain/plan.py`, `src/core/domain/errors.py`, `src/core/policy/engine.py`, `src/orchestrator/pending_store.py`, `src/audit/sqlite_logger.py`, `src/audit/schema.py`, `src/execution/__init__.py`, `tests/ports/fakes.py`, `tests/ports/test_conformance.py`, `tests/orchestrator/conftest.py`, `tests/orchestrator/test_pending_store.py`, `tests/audit/conftest.py`, `tests/audit/test_sqlite_logger.py` (partial), `tests/conftest.py`, `pyproject.toml`
**Pattern extraction date:** 2026-06-13
