---
phase: 05-orquestador-daemon
plan: 04
type: execute
status: complete
wave: 2
executor: codex (codex-gsd-exec, reasoning=high)
verified_by: opus (cadena verde re-corrida + review fail-closed/socket)
---

---
phase: 05-orquestador-daemon
plan: 04
subsystem: orchestrator
tags: [asyncio, unix-socket, json-rpc, policy, audit, cli]
requirements-completed: [ORCH-01, ORCH-02, ORCH-05, ORCH-06, AUD-02]
completed: 2026-06-13
---

# Phase 05-04: Orquestador Daemon Summary

**Daemon asyncio con JSON-RPC, dispatcher A/B/C/D fail-closed, confirmaciones pending y CLI start/ask/confirm/audit.**

## Accomplishments
- Created `src/orchestrator/daemon.py` with stale socket cleanup, `asyncio.start_unix_server`, chmod `0600`, JSON-RPC handlers, background TTL reaper, and fail-closed degraded health handling.
- Created `src/orchestrator/dispatcher.py` with deterministic branching by `PolicyDecision.outcome`: A queued, B/C pending, D rejected and audited.
- Extended `src/bootstrap/cli.py` with `start`, `ask`, `confirm`, and `audit`, plus direct SQLite audit query support.
- Replaced orchestrator stubs with real tests for daemon dispatch, pending persistence, D rejection, corrupt outcome fail-closed behavior, and audit listing.

## Files Created/Modified
- `src/orchestrator/daemon.py` - daemon server, JSON-RPC dispatch, stale socket cleanup, confirm flow.
- `src/orchestrator/dispatcher.py` - policy outcome branching and audit events.
- `src/orchestrator/__init__.py` - daemon/dispatcher exports.
- `src/bootstrap/cli.py` - four daemon/audit CLI commands and 05-04 fake orchestrator.
- `tests/orchestrator/conftest.py` - fake orchestrator and audit fixtures.
- `tests/orchestrator/test_daemon.py` - real daemon/dispatcher tests.
- `tests/orchestrator/test_audit_query.py` - real audit query test.

## Deviations
- No commits and no `.planning/` summary file were written because the user explicitly required: “NO commitees, NO toques .planning/”.
- The sandbox blocks real `AF_UNIX bind` with `EPERM`; production code still uses `asyncio.start_unix_server`, while tests cover stale cleanup via monkeypatch and JSON-RPC handling with in-memory streams.

## Systemd User Unit Reference
```ini
[Unit]
Description=Wyss Daemon
After=default.target

[Service]
Type=simple
ExecStart=/mnt/hdd/Data/10_Workspace/projects/wyss/.venv/bin/wyss start --config %h/.config/wyss/config.toml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

## Green Chain Final
```bash
UV_CACHE_DIR=/tmp/uvcache uv run pytest tests/ -q && UV_CACHE_DIR=/tmp/uvcache uv run mypy && UV_CACHE_DIR=/tmp/uvcache uv run ruff check src tests && UV_CACHE_DIR=/tmp/uvcache uv run lint-imports
```

Result: PASS  
`327 passed, 3 skipped`; mypy clean; ruff clean; import-linter contracts kept.