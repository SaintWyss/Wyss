# Phase 6: Capa de Ejecución — Research

**Researched:** 2026-06-13
**Domain:** Execution adapters — FileSystem, Shell, Git — behind the `Tool` port; undo journal; second-wall risk re-evaluation
**Confidence:** HIGH (core findings empirically verified on this machine)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-64:** Borrado-a-papelera vía `send2trash` (XDG FreeDesktop trash spec).
- **D-65:** Journal SQLite (WAL) reusando el patrón de `PendingStore`/`SqliteAuditLogger`; registra origen→destino + operación inversa por acción modificadora; `restore(id)` aplica la inversa.
- **D-66:** Allowlist de binarios en config TOML; ejecución por exec directo (argv), NUNCA `shell=True`. Fail-closed: binario fuera de lista = rechazo + audit.
- **D-67:** Verificación por tipo de acción: `file.write`→size+sha256; `file.move`→destino existe & origen ausente; `file.delete`→ausente & en papelera; `git`→exit code + estado esperado.
- **D-68:** El adapter resuelve paths reales (expanduser + resolve symlinks), reconstruye la `Action` resuelta y re-corre `CognitivePolicyEngine.evaluate`. Si nivel resuelto > `max_risk` del Tool o cambió → bloquea + audita.
- **D-69:** El executor honra `Action.on_error`: ABORT→detiene y revierte vía journal; RETRY→reintenta según `RetryParams`; ESCALATE→audita y escala.

### Claude's Discretion
- Estructura interna de `src/execution/` (un módulo por adapter vs archivo único), nombres de tablas del journal, firma exacta de `restore()`.
- Piloto automático para decisiones menores; consultar solo ante cambios de arquitectura/seguridad/scope.

### Deferred Ideas (OUT OF SCOPE)
- CalendarAdapter/MessagingAdapter/AppAdapter (fases posteriores).
- Undo multi-nivel / time-travel del journal.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXEC-01 | Adaptadores de ejecución desacoplados (FileSystem, Shell, Git) con allowlist de comandos | D-66 + asyncio.create_subprocess_exec verified; TOML allowlist via stdlib tomllib; shutil.which for binary resolution |
| EXEC-02 | Toda acción modificadora se verifica después de ejecutada (conteos, hashes, estados) | D-67 patterns verified empirically: sha256 via hashlib, stat() for size, NTFS move+hash verified |
| EXEC-03 | Operaciones de archivos con undo: papelera en vez de borrado, journal origen→destino con operación inversa | D-64 send2trash empirically verified on NTFS/fuseblk; D-65 SQLite WAL verified on /mnt/hdd |
| EXEC-04 | El adapter de ejecución re-verifica el nivel de riesgo antes de ejecutar (segunda muralla tras la política) | D-68 path resolution verified; CognitivePolicyEngine.evaluate is pure/reusable without modification |
</phase_requirements>

---

## Summary

Phase 6 fills `src/execution/` with three concrete `Tool` port adapters (FileSystemAdapter, ShellAdapter, GitAdapter) plus a SQLite-backed undo journal. All four decisions (D-64..D-69) are mutually consistent and leverage patterns already proven in the codebase: the WAL SQLite pattern from `PendingStore`/`SqliteAuditLogger`, the pure `CognitivePolicyEngine` for the second wall, and `asyncio.create_subprocess_exec` for shell/git operations.

The single empirical risk flagged in CONTEXT.md (D-64: `send2trash` behavior on the NTFS/fuseblk mount of `~/Data`) has been **verified in this session**: `send2trash` 2.1.0 on Linux uses the FreeDesktop spec — it moves files to `.Trash-1000/{files,info}/` on the same volume when the source is on an external filesystem (`fuseblk`), rather than copying across to `~/.local/share/Trash`. This avoids cross-device EXDEV errors. The `.trashinfo` metadata is correctly created alongside the file. Files on `~` (ext4) go to `~/.local/share/Trash/`. Both paths work.

The SQLite WAL pattern used in `PendingStore` and `SqliteAuditLogger` **works on the NTFS/fuseblk mount** (`/mnt/hdd/data/`). The project already has a `@pytest.mark.ntfs` / `WYSS_TEST_NTFS=1` opt-in marker for NTFS-specific tests; the same pattern must be replicated for the execution journal.

**Primary recommendation:** Implement one file per adapter plus a shared `journal.py` module, all under `src/execution/`. The second wall (D-68) is implemented inside each adapter's `execute()` — resolve paths, reconstruct `Action`, call `engine.evaluate()` — before any real I/O. No parallel evaluator. No new domain types needed.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| File create/write/move/delete | Execution adapter | Audit | I/O adapter owns the physical operation; audit owns the record |
| Shell command execution | Execution adapter (ShellAdapter) | — | argv exec, no shell; adapter owns binary resolution + timeout |
| Git operations | Execution adapter (GitAdapter) | — | Git adapter wraps git CLI via subprocess; exit code = verification signal |
| Post-execution verification | Execution adapter (verify()) | — | `Tool` protocol requires paired verify(); adapter type-dispatches by action.type |
| Undo journal (write) | Execution adapter | Journal (SQLite) | Each adapter records to journal before mutating; journal owns SQLite WAL |
| Undo journal (restore) | Journal (SQLite) | Execution adapter | `restore(id)` reads inverse op from journal, delegates to adapter to apply |
| Second-wall risk re-eval | Execution adapter (pre-execute) | CognitivePolicyEngine (reused) | Adapter resolves paths, calls existing engine; never a parallel evaluator |
| on_error enforcement | Executor / dispatcher | Audit | Dispatcher (or adapter loop) reads Action.on_error; journal provides rollback data |
| Audit | Audit port (existing) | — | Transversal — adapter logs via injected AuditPort |

---

## Standard Stack

### Core (no new dependencies for most of Phase 6)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `send2trash` | 2.1.0 | Trash-spec-compliant file deletion | [VERIFIED: PyPI + empirical] Handles fuseblk/NTFS cross-device trash via `.Trash-1000` — no EXDEV. slopcheck: OK. |
| `asyncio` (stdlib) | 3.12+ | Subprocess execution without shell=True | [VERIFIED: codebase, docs] `create_subprocess_exec` is already used in daemon; argv split prevents shell injection |
| `hashlib` (stdlib) | 3.12+ | sha256 for post-write verification | [VERIFIED: empirical] 65536-byte chunked read handles large files |
| `shutil` (stdlib) | 3.12+ | File move operations (same or cross-FS) | [VERIFIED: empirical] `shutil.move` on NTFS works; hash equality verified before/after |
| `tomllib` (stdlib) | 3.11+ | Parse TOML allowlist config | [VERIFIED: codebase] Already used for config; `allowed_binaries` list in TOML is natural |
| `sqlite3` (stdlib) | 3.12+ | Undo journal (WAL pattern) | [VERIFIED: empirical] WAL works on `/mnt/hdd` (fuseblk). Mirror of PendingStore pattern |
| `pathlib.Path` (stdlib) | 3.12+ | Path normalization + symlink resolution | [VERIFIED: empirical] `Path(os.path.expanduser(target)).resolve()` resolves `~/Data` → `/mnt/hdd/Data` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `shutil.which` (stdlib) | 3.12+ | Binary path resolution for allowlist | ShellAdapter: resolve binary name → absolute path before exec |
| `os.path.expanduser` + `Path.resolve()` | stdlib | D-68 path normalization | Every adapter, pre-execute: catches `~/../root` tricks |

**Installation (only `send2trash` is new):**
```bash
uv add send2trash>=2.1.0
```

All other dependencies are stdlib (Python 3.12+).

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `send2trash` | PyPI | ~12 yrs (1.0.0 first release) | High (JupyterLab dependency) | github.com/arsenetar/send2trash | [OK] | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

Note: `send2trash` is a well-known JupyterLab/Jupyter dependency with millions of weekly downloads. Registry source: github.com/arsenetar/send2trash (BSD license). [VERIFIED: PyPI + slopcheck OK + empirical test this session]

---

## Architecture Patterns

### System Architecture Diagram

```
Daemon/Dispatcher
      |
      | confirmed action (plan step)
      v
[Execution Layer — src/execution/]
      |
      +---> D-68: resolve paths (expanduser + resolve symlinks)
      |           reconstruct Action with resolved target
      |           CognitivePolicyEngine.evaluate(resolved_plan)
      |           if level > Tool.max_risk or changed -> BLOCK + audit
      |
      +---> dispatch by action.type prefix:
      |           "file.*"   -> FileSystemAdapter
      |           "shell.*"  -> ShellAdapter
      |           "git.*"    -> GitAdapter
      |
 [Adapter.execute(action)]
      |
      +---> [UndoJournal.record(action_id, origin, dest, inverse_op)]  <-- before mutating
      |
      +---> real I/O: shutil.move / Path.write_text / send2trash / subprocess_exec
      |
      +---> [Adapter.verify(action, result)]  -- D-67 type dispatch
      |           file.write  -> stat().st_size == expected AND sha256 match
      |           file.move   -> dest.exists() AND NOT src.exists()
      |           file.delete -> NOT path.exists() AND in .Trash-*/files/
      |           git.*       -> returncode == 0 AND expected state
      |
      +---> [AuditPort.log(EXEC_COMPLETED | EXEC_FAILED | EXEC_BLOCKED)]
      |
      v
  ToolResult(success, detail, payload) + Verification(passed, detail)
      |
 [on_error enforcement — D-69]
      +-- ABORT   -> UndoJournal.restore(all applied steps in reverse)
      +-- RETRY   -> RetryParams backoff loop (max_attempts, backoff_base_s)
      +-- ESCALATE -> audit ESCALATE event, propagate to owner
```

### Recommended Project Structure

```
src/execution/
├── __init__.py          # stubs already exist; add adapter exports
├── filesystem.py        # FileSystemAdapter implements Tool
├── shell.py             # ShellAdapter implements Tool
├── git.py               # GitAdapter implements Tool
├── journal.py           # UndoJournal (SQLite WAL), schema, restore()
└── executor.py          # PlanExecutor: step loop + on_error enforcement (D-69)

tests/execution/
├── __init__.py
├── conftest.py          # tmp_path fixtures, FakeEngine stub
├── test_filesystem.py   # unit + NTFS opt-in marker
├── test_shell.py        # allowlist enforcement, timeout, argv safety
├── test_git.py          # git operations + verification
├── test_journal.py      # WAL, record, restore, NTFS opt-in
├── test_executor.py     # on_error loop: ABORT rollback, RETRY backoff, ESCALATE
└── test_second_wall.py  # D-68: resolved path > max_risk -> block
```

### Pattern 1: Second Wall (D-68) — Path Resolution Before Execute

**What:** Every adapter's `execute()` begins with path normalization before any real I/O.
**When to use:** Always, for every action with a `target` field.

```python
# Source: empirical — verified this session
import os
from pathlib import Path
from core.domain.plan import Action
from core.domain.policy import PolicyDecision
from core.policy.engine import CognitivePolicyEngine

def _resolve_target(target: str) -> str:
    """Expand ~ and resolve symlinks. ~/Data -> /mnt/hdd/Data on this machine."""
    return str(Path(os.path.expanduser(target)).resolve())

class FileSystemAdapter:
    def __init__(self, engine: CognitivePolicyEngine, audit: ...) -> None:
        self._engine = engine
        self._audit = audit

    async def execute(self, action: Action) -> ToolResult:
        # D-68: resolve real path, reconstruct Action, re-evaluate
        resolved_target = _resolve_target(action.target)
        resolved_action = Action(
            type=action.type,
            target=resolved_target,
            parameters=action.parameters,
            on_error=action.on_error,
            retry_params=action.retry_params,
        )
        # Wrap in a single-step plan to reuse evaluate()
        resolved_plan = Plan(
            task_id=action_id,
            summary="second-wall check",
            steps=(resolved_action,),
            rationale="path-resolution re-eval",
        )
        decision = self._engine.evaluate(resolved_plan)
        if decision.risk_level > self.max_risk or resolved_target != action.target:
            # Log and block — do not execute
            self._audit.log(...)
            return ToolResult(success=False, detail="blocked: second wall", payload={})
        # Proceed with real I/O using resolved_target
        ...
```

**Critical:** `CognitivePolicyEngine` is pure (no I/O, no state) — safe to call again. It already calls `os.path.expanduser` internally for denylist matching, but that does NOT resolve symlinks. The second wall adds `Path.resolve()` which follows symlinks. This closes the path-trick threat from 01-RESEARCH §794.

### Pattern 2: Undo Journal (D-65) — SQLite WAL, mirror of PendingStore

**What:** Record origin→dest + inverse op before mutating. `restore(entry_id)` applies inverse.
**When to use:** Every modifying action (file.write, file.move, file.delete, file.create).

```python
# Source: mirror of src/orchestrator/pending_store.py and src/audit/schema.py

JOURNAL_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",  # NORMAL (not FULL) — journal is operational, not audit
    "PRAGMA busy_timeout=5000",
)

CREATE_JOURNAL = """
CREATE TABLE IF NOT EXISTS undo_entries (
  id           TEXT PRIMARY KEY,
  task_id      TEXT NOT NULL,
  step_index   INTEGER NOT NULL,
  action_type  TEXT NOT NULL,
  origin       TEXT NOT NULL,
  destination  TEXT,
  inverse_op   TEXT NOT NULL,  -- JSON: {"type": "file.move", "target": ..., "parameters": {...}}
  status       TEXT NOT NULL DEFAULT 'pending',  -- pending | applied | rolled_back
  created_at   TEXT NOT NULL,
  resolved_at  TEXT
)
"""
```

**inverse_op mapping per action type:**
| Action type | Inverse op |
|---|---|
| `file.write` (new file) | `file.delete` on the written path |
| `file.write` (overwrite) | `file.write` with original content (store in payload before overwrite) |
| `file.move` origin→dest | `file.move` dest→origin |
| `file.delete` (now in trash) | `file.restore_trash` with `.trashinfo` path |
| `file.create` | `file.delete` |

**Note on `file.delete` restore:** `send2trash` does not provide a programmatic `restore()` API. The journal must store the `.trashinfo` path (from `.Trash-1000/info/name.trashinfo` or `~/.local/share/Trash/info/name.trashinfo`) to reconstruct the origin for manual or code-driven restore. The inverse op for `file.delete` is: read the `.trashinfo` file, extract `Path=` field, move file from `files/name` back to origin. [ASSUMED: the exact trashinfo path discovery method; needs implementation verification]

### Pattern 3: send2trash on NTFS — Empirical Findings

**Behavior on fuseblk (`/mnt/hdd`, `/dev/sda3`):**
- Files on NTFS volume go to `/mnt/hdd/.Trash-1000/files/` (per-volume trash)
- `.trashinfo` metadata is written to `/mnt/hdd/.Trash-1000/info/filename.trashinfo`
- `Path=` field in `.trashinfo` is relative to the volume root when file is within the volume
- NO cross-device copy — same-volume rename (fast, no data transfer)
- Files on `~/` (ext4, same device as `~/.local/share`) go to `~/.local/share/Trash/`

**D-67 verification of delete:** `NOT path.exists()` is sufficient to confirm the file was moved. For "in trash" confirmation, check `Path('/mnt/hdd/.Trash-1000/files/') / filename` OR `Path.home() / '.local/share/Trash/files/' / filename`. Adapter must track which trash was used (journal stores it).

```python
# Source: empirical — send2trash 2.1.0 tested this session on /mnt/hdd (fuseblk)
from send2trash import send2trash

# Verification after delete:
def _verify_delete(original_path: Path, trash_path: Path) -> bool:
    return (not original_path.exists()) and trash_path.exists()
```

### Pattern 4: ShellAdapter argv exec (D-66)

**What:** Binary allowlist in TOML; resolved via `shutil.which`; exec via `asyncio.create_subprocess_exec`.
**Security invariant:** `shell=False` (default for `create_subprocess_exec`) — no shell expansion, no injection.

```python
# Source: asyncio stdlib docs + empirical test this session
import asyncio
import shutil

async def _exec_allowed(binary: str, args: list[str], cwd: str, timeout_s: float) -> tuple[int, str, str]:
    """Execute binary from allowlist. Raises if binary not in list or not found."""
    resolved = shutil.which(binary)
    if resolved is None:
        raise FileNotFoundError(f"binary not found: {binary!r}")
    
    proc = await asyncio.create_subprocess_exec(
        resolved, *args,           # argv, NOT shell string
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()  # drain
        raise
    return proc.returncode, stdout.decode(), stderr.decode()
```

**NEVER:** `asyncio.create_subprocess_shell` or `subprocess.run(..., shell=True)`.

### Pattern 5: sha256 Verification (D-67 file.write)

```python
# Source: empirical — verified this session (hashlib stdlib)
import hashlib
from pathlib import Path

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
```

Hash only on files that were written/moved. Do NOT hash on every verify call for large files — restrict to the specific file written. For `file.move`, hash the destination only (same content, different location).

### Anti-Patterns to Avoid

- **`shell=True` in subprocess:** Opens shell injection. Always `create_subprocess_exec` with argv list.
- **Building a parallel policy evaluator:** D-68 explicitly says re-use `CognitivePolicyEngine.evaluate`. Creating a second evaluator introduces divergence. Wrap the resolved action in a `Plan` and call the existing engine.
- **Hashing entire 2 TB on verify:** Only hash the specific file that was written/moved. Size check first; hash only if size matches (early exit for obvious mismatches).
- **Storing file content in the journal for overwrite-undo:** Store only a path reference or snapshot. Never store raw file content in SQLite — 2 TB files would break the DB.
- **Cross-FS `os.rename` for move:** `shutil.move` handles EXDEV automatically; `os.rename` raises on cross-device moves.
- **Calling `evaluate_action()` in the second wall:** This method does not exist on `CognitivePolicyEngine` by design (anti-bypass via composition, per engine.py docstring). Use `evaluate(plan)` with a single-step plan.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Trash-spec-compliant delete | Custom trash implementation | `send2trash` | Handles per-volume `.Trash-N` creation, `.trashinfo` metadata, EXDEV fallback to HOMETRASH |
| Shell injection prevention | Custom arg sanitizer | `asyncio.create_subprocess_exec` with `shell=False` | OS-level guarantee — no sanitizer regex can cover all cases |
| Binary lookup | Manual PATH scan | `shutil.which` | Handles PATH, executable bits, symlinks correctly |
| Cross-device file move | `os.rename` with try/except | `shutil.move` | EXDEV handling built-in |
| WAL SQLite pattern | New DB class | Mirror `PendingStore` | Already proven on this NTFS mount; WAL verified |

**Key insight:** Every "simple" custom implementation in this domain has a known failure mode that the standard library or `send2trash` already handles. The allowlist + `create_subprocess_exec` pattern is the canonical Python secure subprocess pattern.

---

## Common Pitfalls

### Pitfall 1: Policy Engine Re-evaluation — Single-step Plan Wrapping

**What goes wrong:** Caller tries to call `engine.evaluate_action(action)` (doesn't exist) or evaluates per-action in a loop, missing aggregate checks.
**Why it happens:** `CognitivePolicyEngine` has no public `evaluate_action()` by design (prevents bypass-by-composition).
**How to avoid:** Wrap the resolved single action in a `Plan(task_id=..., steps=(action,), ...)` and call `engine.evaluate(plan)`. The aggregate checks are trivially satisfied for a 1-step plan.
**Warning signs:** `AttributeError: 'CognitivePolicyEngine' object has no attribute 'evaluate_action'`

### Pitfall 2: send2trash TrashPermissionError on /tmp

**What goes wrong:** Calling `send2trash` on files in `/tmp` raises `TrashPermissionError` — `/tmp` is world-writable, send2trash cannot create a `.Trash-uid` directory there with proper permissions.
**Why it happens:** FreeDesktop spec: the trash dir must be owned exclusively by the user; `/tmp` sticky-bit prevents this.
**How to avoid:** FileSystemAdapter should not allow `file.delete` on `/tmp` paths (add to BUILTIN_DENY or adapter validation). Tests must not use `/tmp` for delete-to-trash tests — use `tmp_path` (pytest, ext4) or `/mnt/hdd` with the `@pytest.mark.ntfs` marker.
**Warning signs:** `send2trash.exceptions.TrashPermissionError: [Errno 13] Permission denied: ''`

### Pitfall 3: SQLite WAL Journal on NTFS — Must Use data/ not /tmp

**What goes wrong:** Execution journal placed on a tmpfs/ext4 path works fine in tests but the production journal in `data/` fails WAL if the filesystem changes.
**Why it happens:** Existing pattern: `data/` is on `/mnt/hdd` (NTFS/fuseblk). WAL is verified to work there (tested this session), but the fail-fast check must still run (as in `PendingStore` and `SqliteAuditLogger`).
**How to avoid:** Journal constructor must apply `JOURNAL_PRAGMAS` and verify `journal_mode == "wal"` fail-fast, raising `AuditIntegrityError` (reusing the existing pattern). Tests use `tmp_path` for unit; opt-in `@pytest.mark.ntfs` for NTFS integration.
**Warning signs:** Journal silently degrades to DELETE mode if the check is omitted.

### Pitfall 4: Path Resolution and the Policy Engine — Symlink Expansion

**What goes wrong:** `CognitivePolicyEngine._normalize()` calls `os.path.expanduser()` but NOT `Path.resolve()`. A target like `~/Data/secret.txt` is expanded to `/home/user/Data/secret.txt`, which does NOT match denylist patterns for `/mnt/hdd/**` (the real path after symlink resolution).
**Why it happens:** The engine's `_normalize` was designed for denylist matching with the original target as declared; it does not resolve symlinks.
**How to avoid:** D-68 is correct: the adapter must call `Path(os.path.expanduser(target)).resolve()` and then reconstruct the Action with the fully-resolved path BEFORE calling `engine.evaluate()`. This way the engine sees `/mnt/hdd/Data/secret.txt` and any rules targeting that path will match.
**Warning signs:** A file in `~/Data` bypassing a denylist rule that targets `/mnt/hdd/**`.

### Pitfall 5: Overwrite-undo Requires Pre-capture

**What goes wrong:** Journal records that `file.write` happened on `~/notes.md`, but to restore the original you need the original content — which the journal didn't store.
**Why it happens:** Journal records metadata, not content.
**How to avoid:** For `file.write` on an EXISTING file, the adapter must capture the original content (or create a backup copy to `data/undo_backups/`) before writing. Journal stores the backup path as the `inverse_op` destination. For new files (path didn't exist), inverse is simply `file.delete`.
**Warning signs:** `restore(id)` for an overwrite does nothing useful because original content is gone.

### Pitfall 6: asyncio Subprocess Timeout — Must Kill and Drain

**What goes wrong:** `asyncio.wait_for(proc.communicate(), timeout=T)` raises `TimeoutError` but the process is still running, consuming resources and holding file handles.
**Why it happens:** `wait_for` cancels the coroutine but does not terminate the child process.
**How to avoid:** On `asyncio.TimeoutError`: call `proc.kill()` then `await proc.communicate()` to drain remaining output. See Pattern 4 above.
**Warning signs:** Zombie processes after timeout; shell adapter tests hanging.

---

## Runtime State Inventory

> Not a rename/refactor phase. Omit.

Phase 6 creates new tables (`undo_entries`) and new files (`data/journal.db`, `data/undo_backups/`). No runtime state needs migrating.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12+ | All adapters | ✓ | 3.14.5 | — |
| `/mnt/hdd` NTFS mount | D-64, D-65, D-67 | ✓ | fuseblk (NTFS3) | — (must be mounted) |
| `git` binary | GitAdapter | ✓ | 2.54.0 | — |
| `ls`, `rg` binaries | ShellAdapter allowlist | ✓ | system | — |
| `send2trash` 2.1.0 | D-64 | needs `uv add` | 2.1.0 | — |
| SQLite WAL on /mnt/hdd | D-65 journal | ✓ | verified empirically | — |
| `.Trash-1000/` on /mnt/hdd | D-64 | ✓ auto-created by send2trash | verified | — |

**Missing dependencies with no fallback:** `send2trash` must be added via `uv add send2trash`.
**Missing dependencies with fallback:** none.

**Empirically verified this session:**
- `send2trash` on fuseblk: OK — uses `.Trash-1000/`, writes `.trashinfo`, no EXDEV
- SQLite WAL on `/mnt/hdd`: OK — `PRAGMA journal_mode=WAL` returns `"wal"`
- `asyncio.create_subprocess_exec('git', ...)`: OK on this machine
- `Path('~/Data/...').expanduser().resolve()` correctly resolves `~/Data` → `/mnt/hdd/Data`
- `shutil.move` on NTFS with sha256 before/after: hashes match

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9+ with pytest-asyncio 1.4.0 |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`) |
| Quick run command | `uv run pytest tests/execution/ -x -q` |
| Full suite command | `uv run pytest -q && uv run mypy src tests && uv run ruff check src tests && uv run lint-imports` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXEC-01 | FileSystemAdapter implements `Tool` protocol | unit | `uv run pytest tests/execution/test_filesystem.py -x` | ❌ Wave 0 |
| EXEC-01 | ShellAdapter rejects binary not in allowlist (fail-closed) | unit | `uv run pytest tests/execution/test_shell.py::test_binary_not_in_allowlist_rejected` | ❌ Wave 0 |
| EXEC-01 | ShellAdapter exec uses argv not shell string (no injection) | unit | `uv run pytest tests/execution/test_shell.py::test_no_shell_injection` | ❌ Wave 0 |
| EXEC-01 | GitAdapter executes allowed git subcommands | unit | `uv run pytest tests/execution/test_git.py -x` | ❌ Wave 0 |
| EXEC-02 | file.write verified: size + sha256 match | unit | `uv run pytest tests/execution/test_filesystem.py::test_verify_write_sha256` | ❌ Wave 0 |
| EXEC-02 | file.move verified: dest exists, src absent | unit | `uv run pytest tests/execution/test_filesystem.py::test_verify_move` | ❌ Wave 0 |
| EXEC-02 | file.delete verified: path absent, in trash | unit | `uv run pytest tests/execution/test_filesystem.py::test_verify_delete` | ❌ Wave 0 |
| EXEC-02 | verify() returns Verification(passed=False) on mismatch | unit | `uv run pytest tests/execution/test_filesystem.py::test_verify_failure_case` | ❌ Wave 0 |
| EXEC-03 | send2trash on tmp_path (ext4) succeeds | unit | `uv run pytest tests/execution/test_filesystem.py::test_delete_to_trash_ext4` | ❌ Wave 0 |
| EXEC-03 | send2trash on NTFS mount (opt-in) | ntfs/integration | `WYSS_TEST_NTFS=1 uv run pytest tests/execution/ -m ntfs` | ❌ Wave 0 |
| EXEC-03 | journal records entry before mutation | unit | `uv run pytest tests/execution/test_journal.py::test_journal_records_before_io` | ❌ Wave 0 |
| EXEC-03 | restore(id) applies inverse op (move: dest→origin) | unit | `uv run pytest tests/execution/test_journal.py::test_restore_move` | ❌ Wave 0 |
| EXEC-03 | ABORT on_error rolls back applied steps via journal | unit | `uv run pytest tests/execution/test_executor.py::test_abort_rolls_back` | ❌ Wave 0 |
| EXEC-04 | D-68: resolved path > max_risk → blocked | unit | `uv run pytest tests/execution/test_second_wall.py::test_resolved_path_above_max_risk` | ❌ Wave 0 |
| EXEC-04 | D-68: symlink path resolves to real path before eval | unit | `uv run pytest tests/execution/test_second_wall.py::test_symlink_resolved` | ❌ Wave 0 |
| EXEC-04 | D-69: RETRY respects RetryParams.max_attempts | unit | `uv run pytest tests/execution/test_executor.py::test_retry_respects_max_attempts` | ❌ Wave 0 |
| EXEC-04 | D-69: ESCALATE audits and escalates (no rollback) | unit | `uv run pytest tests/execution/test_executor.py::test_escalate_audits` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/execution/ -x -q`
- **Per wave merge:** `uv run pytest -q && uv run mypy src tests && uv run ruff check src tests && uv run lint-imports`
- **Phase gate:** Full suite green (327 + Phase 6 tests) before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/execution/__init__.py` — package marker
- [ ] `tests/execution/conftest.py` — `tmp_path`-based fixtures, `FakeEngine` stub wrapping real `CognitivePolicyEngine`, fake `AuditPort`
- [ ] `tests/execution/test_filesystem.py` — EXEC-01, EXEC-02, EXEC-03 (ext4 paths)
- [ ] `tests/execution/test_shell.py` — EXEC-01 allowlist enforcement
- [ ] `tests/execution/test_git.py` — EXEC-01 git operations
- [ ] `tests/execution/test_journal.py` — EXEC-03 WAL, record, restore
- [ ] `tests/execution/test_executor.py` — EXEC-04 (D-69) on_error loop
- [ ] `tests/execution/test_second_wall.py` — EXEC-04 (D-68) path resolution + block
- [ ] `uv add send2trash>=2.1.0` — adds to pyproject.toml

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | yes | `Tool.max_risk` + second wall (D-68); allowlist (D-66) |
| V5 Input Validation | yes | Path resolution (D-68); binary resolution via `shutil.which` |
| V6 Cryptography | no | sha256 is integrity verification, not encryption |
| V13 API/Web | no | — |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal (`../../etc/passwd`) | Tampering | `Path(expanduser(target)).resolve()` before any I/O + re-eval (D-68) |
| Shell injection | Tampering | `asyncio.create_subprocess_exec` with `shell=False`; args are a list, never a string |
| Symlink attack (`~/Data` → `/mnt/hdd`) | Elevation of Privilege | `Path.resolve()` expands symlinks; resolved path re-evaluated against policy |
| Allowlist bypass (binary not in list) | Tampering | Fail-closed: `shutil.which(binary) not in allowed_set` → reject + audit |
| Stale plan adulterado post-política | Tampering | Second wall re-evaluates resolved action; if level changed → block + audit |
| Overwrite without backup | Tampering / DoS | Journal captures original content path before write; restore applies it |
| Timeout starvation (long-running shell cmd) | DoS | `asyncio.wait_for` + `proc.kill()` on timeout |

**Security invariant (from docs/18 rules):** Nivel D is absolute and has no path through any adapter. `CognitivePolicyEngine` enforces this; adapters must not check `outcome == REJECT` themselves and proceed anyway — they must propagate the block. The second wall adds a second call to the same engine (not a weaker check).

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `subprocess.run(shell=True)` | `asyncio.create_subprocess_exec` | Python 3.5+ | Shell injection impossible by construction |
| `os.remove()` for delete | `send2trash.send2trash()` | FreeDesktop trash spec adoption | Recoverable deletes; `.trashinfo` metadata for audit |
| `os.rename` for move | `shutil.move` | Python stdlib | EXDEV cross-device handled transparently |
| Custom WAL SQLite class | Mirror `PendingStore` pattern | Established in Phase 1 | Consistent pattern, fail-fast WAL check, reuse |

**Deprecated/outdated:**
- `GitPython` library: not in project stack, adds unnecessary dependency. Direct subprocess to `git` binary is cleaner and already available.
- `pyfakefs`: explicitly NOT used in this project (CONVENTIONS). Tests use real `tmp_path` (ext4/tmpfs).

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `.trashinfo` path on NTFS uses relative path for in-volume files and absolute for cross-volume | Common Pitfalls / send2trash pattern | `restore()` would reconstruct wrong origin path; verified in `.trashinfo` content this session but only 2 samples |
| A2 | `GitAdapter` uses direct `git` CLI subprocess (not GitPython) consistent with existing "subprocess for external tools" pattern | Standard Stack | If GitPython were preferred, tests and API differ |
| A3 | `synchronous=NORMAL` (not FULL) is appropriate for the undo journal (vs FULL for audit) | Pattern 2 / Journal schema | If journal needs crash guarantees equal to audit, use FULL; NORMAL is faster and loses at most last committed WAL frame on crash |
| A4 | Overwrite-undo stores a backup file to `data/undo_backups/`, not the content inline in SQLite | Pattern 2 / Pitfall 5 | If files are always small, inline BLOB would work; for 2 TB files this assumption is critical |

**If table is not empty:** Items A1 and A3 are low-risk (verified patterns or tunable); A2 and A4 are implementation decisions left to Claude's Discretion per CONTEXT.md.

---

## Open Questions

1. **Overwrite-undo backup storage path**
   - What we know: The journal needs original content to undo a `file.write` overwrite.
   - What's unclear: Should backup go to `data/undo_backups/{entry_id}` (simple) or to `data/undo_backups/{task_id}/{step_index}` (grouped by task for easier full rollback)?
   - Recommendation: `data/undo_backups/{entry_id}` — simple, journal entry points directly to it, no directory structure to manage.

2. **`restore()` API for `file.delete` — trashinfo discovery**
   - What we know: `send2trash` does not provide a restore API. `.trashinfo` files tell us where the file came from.
   - What's unclear: How to reliably find the `.trashinfo` file after the fact (filename collision handling: send2trash appends ` 1`, ` 2`, etc. to `dest_name`).
   - Recommendation: Journal records the exact `.trashinfo` path at delete time (before the delete, pre-compute the trash destination using the same logic as `send2trash`). This requires reading send2trash internals at delete-record time, or recording post-delete by scanning for the newest `.trashinfo`.

3. **Executor location — adapter-level or separate `executor.py`?**
   - What we know: D-69 enforcement (on_error loop + journal rollback) spans multiple adapters.
   - What's unclear: Whether the dispatcher in `src/orchestrator/` already handles this or if a new `PlanExecutor` class in `src/execution/executor.py` is cleaner.
   - Recommendation: New `PlanExecutor` in `src/execution/executor.py` — it owns the step loop, dispatches to the correct adapter by `action.type` prefix, and handles the on_error policy. This keeps orchestrator code clean and makes the enforcement testable in isolation.

---

## Sources

### Primary (HIGH confidence — empirical, this session)
- `send2trash` 2.1.0 source (`plat_other.py`) — FreeDesktop trash spec implementation, EXDEV handling, `.Trash-uid` creation
- Live test: `send2trash` on `/mnt/hdd` (fuseblk) → files land in `/mnt/hdd/.Trash-1000/files/` with `.trashinfo` metadata
- Live test: SQLite WAL on `/mnt/hdd` (fuseblk) → `PRAGMA journal_mode=WAL` returns `"wal"`
- Live test: `Path('~/Data/...').expanduser().resolve()` → `/mnt/hdd/Data/...`
- Live test: `shutil.move` on NTFS + sha256 before/after → hashes match
- Live test: `asyncio.create_subprocess_exec('git', '--version', ...)` → exit 0

### Primary (HIGH confidence — codebase)
- `src/orchestrator/pending_store.py` — WAL pattern, `PENDING_PRAGMAS`, fail-fast check
- `src/audit/sqlite_logger.py` + `src/audit/schema.py` — WAL pragmas, append-only triggers
- `src/core/policy/engine.py` — `CognitivePolicyEngine.evaluate(plan)` is pure; `_normalize` uses `expanduser` not `resolve`
- `src/core/ports/execution.py` — `Tool` protocol contract
- `src/core/domain/plan.py` — `Action`, `ErrorPolicy`, `RetryParams`
- `src/core/domain/execution.py` — `ToolResult`, `Verification`
- `src/core/domain/errors.py` — `AuditIntegrityError` to reuse for journal WAL failure
- `tests/ports/fakes.py` — `FakeTool` pattern for test conformance
- `pyproject.toml` — import-linter contract: `execution` is independent of `orchestrator`, `audit`, etc. (can only import `core`)

### Secondary (MEDIUM confidence)
- PyPI metadata for `send2trash` — github.com/arsenetar/send2trash, BSD license, ~12 year old package, JupyterLab dependency
- slopcheck 0.6.1 verdict: `send2trash` = [OK]

---

## Metadata

**Confidence breakdown:**
- send2trash on NTFS: HIGH — verified empirically this session with source code review
- SQLite WAL on NTFS: HIGH — verified empirically this session
- asyncio subprocess pattern: HIGH — existing codebase, stdlib docs
- Second wall (D-68) implementation: HIGH — engine is pure, `Path.resolve()` is stdlib
- Journal schema: HIGH — direct mirror of existing `PendingStore` pattern
- overwrite-undo backup strategy: MEDIUM — A4 assumption, reasonable but not tested

**Research date:** 2026-06-13
**Valid until:** 2026-07-13 (send2trash is stable; WAL behavior is filesystem-determined, not library version)
