# Phase 9: Routine Scheduler - Research

**Researched:** 2026-07-10
**Domain:** asyncio background scheduling inside an existing single-process daemon; cron/interval routines that produce `Plan`s gated by the existing `CognitivePolicyEngine` + `dispatch()`
**Confidence:** HIGH (architecture/pitfalls grounded in direct reads of `daemon.py`, `dispatcher.py`, `pending_store.py`, `ttl_reaper.py`, `core/domain/*`, `bootstrap/cli.py`, `bootstrap/web.py`, `bootstrap/config.py`); MEDIUM on APScheduler API specifics (Context7 unavailable in this environment — fell back to official docs via WebSearch, cross-checked against GitHub issues)

## Summary

Phase 9 does not need a new architectural layer — it needs one new asyncio background task inside the existing daemon, one new small SQLite-backed store (sibling to `PendingStore`, not an ORM), and zero new `action.type`s or `base_levels`. The daemon already has the exact shape this feature reuses: `start_daemon()` creates `reaper_task` via `asyncio.create_task(...)` and hands back a closeable `RunningDaemon`; the Routine Scheduler is a second task of the same shape, added to the same dataclass, closed the same way. `dispatch(plan, decision, pending_store=, audit=)` is already the single gate everything in this daemon goes through — A executes (via the injected `PlanRunner`), B/C land in `PendingStore` exactly like an interactive `ask()`, D rejects. The scheduler must never call anything except `engine.evaluate()` + `dispatch()`; it must never call `_execute_plan` directly and must never touch the `PlanRunner` on its own.

The one real design decision this phase must make and that the milestone research correctly flagged as open is **catch-up policy** and **timezone correctness** — both are pure logic bugs waiting to happen if copied from the existing `ttl_reaper`'s `while True: sleep(fixed)` pattern, which drifts and cannot express "at 08:00" or survive a multi-hour daemon outage without either silently skipping the routine or double-firing it. APScheduler 3.11.3 (confirmed on PyPI registry, `slopcheck` clean) solves drift and misfire computation, but it does **not** solve the "daemon was completely offline, not just busy" case — that is domain logic this phase must write explicitly (Pitfall 7/8 below), independent of which scheduling library is used.

**Primary recommendation:** Use `APScheduler` 3.11.3's `AsyncIOScheduler` purely as an **in-process trigger/next-fire-time computer**, wired into the daemon's existing event loop exactly like `ttl_reaper`. Do **not** use APScheduler's persistent jobstore (`SQLAlchemyJobStore` etc.) — persist routines in a hand-rolled SQLite `RoutineStore` (mirroring `PendingStore`'s style exactly: raw `sqlite3`, WAL, no ORM), and re-register jobs with APScheduler from that store on every daemon boot. Each routine fires by building a `Plan` directly (no LLM call, no `classify_intent`/`draft_plan`) and calling `engine.evaluate()` + `dispatch()` — this keeps routines reliable even if the gateway/LiteLLM is down at 08:00, and keeps testing deterministic.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCHED-01 | Owner puede crear una rutina programada (cron u hora fija) desde CLI o web, con preview legible del schedule antes de guardar | `CronTrigger.from_crontab` + next-N-fire-times preview (Code Examples); no croniter/humanize dependency needed (Alternatives Considered) |
| SCHED-02 | Una rutina que dispara genera un Plan que pasa por la política: A ejecuta directo, B/C caen a la bandeja — jamás auto-ejecución (cierra MULTI-02) | Reuse verbatim of `engine.evaluate()` + `dispatch()` (Architecture Patterns, System Architecture Diagram); zero new action types or base_levels needed |
| SCHED-03 | Owner puede listar, pausar, reanudar y borrar rutinas, y ver el último resultado de cada una | `RoutineStore` (SQLite, mirrors `PendingStore` style) + new JSON-RPC methods `routine.add/list/pause/resume/delete` (Recommended Project Structure, Code Examples) |
| SCHED-04 | Tras downtime del daemon, las rutinas perdidas se manejan con política de catch-up explícita (coalesce; jamás doble-fire) | Pattern 3 (Catch-up-on-boot is domain logic, not an APScheduler feature) + Pitfall 2 and Pitfall 3 (double-fire guards, atomic `last_fired_at` persistence) |
| SCHED-05 | Toda ejecución de rutina queda auditada: trigger, plan, decisión de política, resultado | New `AuditEventType.ROUTINE_TRIGGERED` enum member (Pitfall 5, Code Examples) + Pattern 2 (explicit try/except around every fire so failures are audited too, not just successes) |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Cron/interval trigger computation (next fire time, drift-free) | Orchestrator (daemon process) | — | Must share the daemon's single asyncio event loop; a separate process/timer would open a second writer to `pending_store.db` (WAL is single-writer-safe within one process, not designed for multi-process coordination here) |
| Routine definition storage (CRUD, pause/resume, last-result) | Orchestrator (daemon process, SQLite) | — | Runtime-created by the owner (not boot-time config like `config.toml`); needs the same durability model as `PendingStore` |
| Routine → Plan construction | Orchestrator (`scheduler.py`, deterministic) | — | Must not depend on LLM/gateway being reachable at fire time (reliability requirement, not just style) |
| Policy gate (A executes / B,C to bandeja / D rejects) | Core (`CognitivePolicyEngine`) + Orchestrator (`dispatch()`) | — | Zero new code path: reuse verbatim, this is the whole point of SCHED-02/MULTI-02 |
| CLI surface (`wyss routine add/list/pause/resume/rm`) | Bootstrap (Typer CLI) | Orchestrator (new JSON-RPC methods) | Same pattern as `wyss ask`/`wyss confirm` — CLI is a thin RPC client, never touches SQLite directly |
| Web surface (list/pause/resume rutinas) | Bootstrap (`bootstrap/web.py` FastAPI) | Orchestrator (same new RPC methods) | Bridge stays a "never decides risk" composition root; it proxies to the daemon via `_json_rpc_call`, exactly like `/api/ask` and `/api/confirm` today |
| Audit of every fire (trigger, plan, decision, resultado) | Audit (`audit/sqlite_logger.py`, append-only) | — | Existing `AuditPort`/`AuditEvent` taxonomy; needs one new `AuditEventType` member (see Don't Hand-Roll / Code Examples) |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|---------------|
| `APScheduler` | 3.11.3 `[VERIFIED: PyPI registry via uv resolve, slopcheck OK]` | `AsyncIOScheduler` + `CronTrigger`/`IntervalTrigger`: drift-free next-fire computation inside the daemon's own event loop | Mature (2011+), API-stable 3.x line, explicitly integrates with an existing asyncio loop (no threads spawned); avoids hand-rolling cron parsing and misfire/coalesce logic from scratch |

No other new runtime dependency is required for this phase. `zoneinfo` (stdlib, Python 3.12+) is already sufficient for Argentina-timezone-aware scheduling — verified working on this machine without a separate `tzdata` package (`ZoneInfo("America/Argentina/Buenos_Aires")` resolved correctly via system tz database).

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none new) | — | — | — |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| APScheduler `AsyncIOScheduler` | Hand-rolled `while True: sleep(align_to_next(schedule))` loop (like `ttl_reaper` but wall-clock-anchored) | Zero new dependency, matches project's stdlib-first bias — but re-derives cron parsing, misfire handling, and DST-safety from scratch with no test coverage from an upstream project. APScheduler 3.11.3 is boring/mature enough (`[VERIFIED]` on registry) that hand-rolling isn't justified here; reserve hand-rolling only if the owner explicitly wants zero new deps. |
| `AsyncIOScheduler` + APScheduler's own `SQLAlchemyJobStore`/`MemoryJobStore` persistence | Custom `RoutineStore` (raw `sqlite3`, own table, jobs re-added to an in-memory APScheduler at every boot) | `SQLAlchemyJobStore` drags in `sqlalchemy` — an ORM this project's own STACK.md explicitly lists under "What NOT to Use" (`SQLAlchemy ORM... SQL directo con sqlite3 stdlib es más simple y auditable`). A custom store also gives full control over the catch-up/coalesce policy (Pitfall 7/8), which APScheduler's built-in misfire handling does **not** solve for a fully-stopped process (see Common Pitfalls). |
| Building `Plan` directly from a stored action template (deterministic) | Storing an NL instruction per routine, replayed through `classify_intent`→`draft_plan` (LLM) at fire time | NL is more flexible (owner types "recordame X todos los días") but makes every routine's reliability depend on the gateway/LiteLLM being reachable at the exact fire time — directly conflicts with SCHED-04's reliability requirement and the project's own "aburrido a propósito" philosophy. Recommend deterministic `Plan` templates for v1.0; NL-authored routines can be added later as a thin layer that resolves to a template ONCE at creation time (still shown as a preview before saving, per SCHED-01), never re-resolved through the LLM at fire time. |
| Preview via `croniter` + a humanization library ("todos los días a las 08:00") | Preview via APScheduler's own trigger `get_next_fire_time()` called N times ("próximas 5 ejecuciones: ...") | Humanized cron strings are a well-known source of subtly wrong translations for complex expressions (`0 8 * * 1-5` vs "every day"). Showing the next 3-5 concrete fire timestamps (already timezone-converted) is simpler, honest, and needs no extra dependency — APScheduler's trigger objects already expose this computation. |

**Installation:**
```bash
uv add apscheduler
```

**Version verification:** `uv add apscheduler --dry-run` resolved `apscheduler==3.11.3` + its sole transitive dependency `tzlocal==5.4.4` against the live PyPI index during this research session `[VERIFIED: PyPI registry]`. `tzlocal` is only used by APScheduler to detect the *host's* local timezone as a fallback when no explicit `timezone=` is passed to `AsyncIOScheduler` — this phase must always pass `timezone=ZoneInfo("America/Argentina/Buenos_Aires")` explicitly (never rely on `tzlocal`'s host-detection), so `tzlocal` becomes dead weight in practice but is an unavoidable transitive dependency of the library.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|--------------|-----------|-------------|
| `apscheduler` | PyPI | 14+ yrs (first released 2011) `[ASSUMED: training knowledge, not re-verified this session]` | High (millions/month, widely depended-on; exact figure not queried this session) `[ASSUMED]` | `github.com/agronholm/apscheduler` `[CITED: pypi.org/project/APScheduler shows this repo link]` | `[OK]` (scanned via `slopcheck install apscheduler`, this session) | Approved |
| `tzlocal` | PyPI | transitive dep of apscheduler, not directly installed by this project | — | — | Not scanned directly (transitive) | Approved by association — pinned indirectly via apscheduler's own dependency constraint |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

Note on package-name provenance rule: `apscheduler` was already named in this project's own prior milestone research (`.planning/research/SUMMARY.md`, `.planning/research/ARCHITECTURE.md`) and in `docs/architecture/WYSS_TARGET_ARCHITECTURE.md` before this research session — its identity as "the standard Python job-scheduling library" is training-knowledge-consistent and now additionally confirmed present on the live PyPI registry via `uv add --dry-run` and clean via `slopcheck`. Per the provenance rule this is still tagged `[ASSUMED]` for anything beyond "it exists on the registry and scans clean" (e.g. exact download counts, exact age) since those specific figures were not independently re-verified this session.

## Architecture Patterns

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ CLI (wyss routine add/list/pause/resume/rm)   Web SPA (rutinas)     │
└───────────────────────┬───────────────────────────┬─────────────────┘
                         │ JSON-RPC over Unix socket │ HTTP (bridge proxies to RPC)
                         ▼                           ▼
┌───────────────────────────────────────────────────────────────────────┐
│ orchestrator/daemon.py :: DaemonServer._handlers                      │
│   NUEVO: "routine.add" / "routine.list" / "routine.pause" /           │
│          "routine.resume" / "routine.delete"                          │
└───────────────────────┬─────────────────────────────────────────────┘
                         │ direct call (same process)
                         ▼
┌───────────────────────────────────────────────────────────────────────┐
│ orchestrator/routine_store.py :: RoutineStore (SQLite, WAL, own table) │
│   CRUD + last_fired_at / last_result — mirrors pending_store.py style  │
└───────────────────────┬─────────────────────────────────────────────┘
                         │ read at boot + on CRUD
                         ▼
┌───────────────────────────────────────────────────────────────────────┐
│ orchestrator/scheduler.py :: RoutineScheduler                          │
│   AsyncIOScheduler (APScheduler), one job per active Routine          │
│   ┌─ on boot: diff "should have fired since last_fired_at" per        │
│   │   routine → apply catch_up policy (coalesce, single fire)        │
│   └─ on each natural/catch-up fire:                                   │
│        plan = build_plan_from_routine(routine)   [deterministic,      │
│                                                    no LLM call]        │
│        decision = engine.evaluate(plan)          [SAME engine]        │
│        await dispatch(plan, decision,                                 │
│                        pending_store=..., audit=...)  [SAME dispatch] │
│        routine_store.mark_fired(routine.id, result_summary)           │
└───────────────────────┬─────────────────────────────────────────────┘
                         │ B/C                              │ A
                         ▼                                   ▼
              PendingStore.save()                  PlanRunner.run() (existing)
              → aparece en Bandeja                  → executed directo
              → owner confirma (flujo YA EXISTENTE,
                sin cambios)
```

A reader can trace the primary use case end-to-end: CLI/web creates a Routine → stored in `RoutineStore` → `RoutineScheduler` computes next fire → at fire time builds a `Plan` → the SAME `CognitivePolicyEngine.evaluate()` + `dispatch()` used by interactive `ask()` decides A/B/C/D → B/C become a normal pending confirmation the owner already knows how to handle; A executes through the existing `PlanRunner`. No new execution path exists anywhere in this diagram.

### Recommended Project Structure

```
src/
├── orchestrator/
│   ├── routine_store.py     # NUEVO: Routine (frozen dataclass) + RoutineStore (SQLite, WAL)
│   │                          #   mirrors pending_store.py's PendingProposal/PendingStore style
│   ├── scheduler.py         # NUEVO: RoutineScheduler wrapping AsyncIOScheduler;
│   │                          #   build_plan_from_routine(); catch-up-on-boot logic
│   ├── daemon.py            # MODIFICADO: += scheduler_task field on RunningDaemon,
│   │                          #   += 5 RPC handlers (routine.add/list/pause/resume/delete)
│   ├── dispatcher.py        # SIN CAMBIOS — reused verbatim
│   ├── pending_store.py     # SIN CAMBIOS — reused verbatim
│   └── ttl_reaper.py        # SIN CAMBIOS — NOT the template to copy (see Pitfall 6)
├── core/domain/
│   └── audit.py             # MODIFICADO: += AuditEventType.ROUTINE_TRIGGERED (or reuse
│                               #   existing types — see Code Examples)
└── bootstrap/
    ├── cli.py               # MODIFICADO: += `wyss routine add|list|pause|resume|rm` subcommands
    └── web.py                # MODIFICADO: += /api/routines (GET/POST), /api/routines/{id}/pause,
                                 #   /api/routines/{id}/resume, DELETE /api/routines/{id}
```

### Structure Rationale

- **`routine_store.py` and `scheduler.py` inside `orchestrator/`, not a new top-level package:** matches the milestone architecture research's explicit rationale — the scheduler already needs `core.policy`, `core.domain`, `PendingStore`, `dispatch()`, exactly the imports `orchestrator/` already legitimately has. A separate `scheduler/` package would need to import from `orchestrator/` anyway (for `dispatch`), which the import-linter's independence contract (`orchestrator, agents, knowledge, gateway, execution, audit, ledger` don't import each other) would then either force into a weird re-export or violate. Keeping it inside `orchestrator/` sidesteps that entirely.
- **`Routine`/`RoutineStore` as a concrete class in `orchestrator/`, not a new `core/ports/routine.py` Protocol:** mirrors the existing precedent exactly — `PendingProposal`/`PendingStore` are defined directly in `orchestrator/pending_store.py`, not abstracted behind a `core/ports/` Protocol, because there is exactly one implementation (SQLite) and no adapter-swapping requirement. Doing the same for `Routine`/`RoutineStore` is consistent, not a shortcut.
- **No new `action.type`, no new `base_levels` entries:** routines in this phase build `Plan`s out of ALREADY-classified action types (`file.*`, `git.*`, `finance.*`, `shell.run`, or future `notion.*`/`memory.*` once those phases land) — a routine is a *producer* of a `Plan`, not a new kind of `Action`. This is why SCHED-02 is satisfiable with zero policy-engine changes.

### Pattern 1: Scheduler task lives inside `RunningDaemon`, started/stopped exactly like `reaper_task`

**What:** Add a `scheduler: AsyncIOScheduler` (or a thin wrapper holding it) field to the `RunningDaemon` dataclass, started in `start_daemon()` right after `reaper_task` is created, and shut down in `aclose()`.

**When to use:** Any periodic work that must share the daemon's single SQLite writer connection to `pending_store.db`/`routines.db` (WAL is not designed for multi-process coordination in this codebase — see `busy_timeout=5000` comment in `pending_store.py`).

**Example:**
```python
# Source: pattern mirrors existing orchestrator/daemon.py:292-317 (start_daemon),
# APScheduler AsyncIOScheduler usage per official docs
# https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html [CITED]
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from zoneinfo import ZoneInfo

ARG_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

@dataclass(slots=True)
class RunningDaemon:
    server: asyncio.AbstractServer
    socket_path: Path
    reaper_task: asyncio.Task[None]
    scheduler: AsyncIOScheduler  # NUEVO

    async def aclose(self) -> None:
        self.server.close()
        await self.server.wait_closed()
        self.reaper_task.cancel()
        with suppress(asyncio.CancelledError):
            await self.reaper_task
        self.scheduler.shutdown(wait=False)  # NUEVO — no bloquea el cierre
        self.socket_path.unlink(missing_ok=True)


async def start_daemon(...) -> RunningDaemon:
    ...
    reaper_task = asyncio.create_task(ttl_reaper(pending_store, audit, interval_s=reaper_interval_s))
    scheduler = AsyncIOScheduler(timezone=ARG_TZ)
    await register_routines(scheduler, routine_store, engine=engine, pending_store=pending_store, audit=audit)
    scheduler.start()  # no-op de retorno inmediato; agenda su propio trabajo en el loop
    return RunningDaemon(server=server, socket_path=socket_path, reaper_task=reaper_task, scheduler=scheduler)
```

**Trade-offs:** `AsyncIOScheduler.start()` must be called from within a running event loop (it schedules its own wakeups via `call_later`) — calling it before `asyncio.start_unix_server`'s loop is running will not work; calling it inside `start_daemon()` (already `async`) is correct and matches where `reaper_task` is created today.

### Pattern 2: A job function's exception must never crash the scheduler — but it also must not vanish

**What:** APScheduler's job executor catches all exceptions raised inside a scheduled job and fires an internal `EVENT_JOB_ERROR` — it does **not** propagate the exception up into `AsyncIOScheduler` itself, so a single misbehaving routine cannot kill the scheduler loop `[CITED: APScheduler docs, job execution/error events]`. However, relying on APScheduler's own (log-only, no owner-visible surface) error event is not enough for SCHED-05 ("toda ejecución queda auditada"): wrap the routine's fire logic in an explicit `try/except` that writes a `TASK_FAILED`-style `AuditEvent` on any exception, so a Notion timeout or a bad Plan template shows up in `wyss audit`/the bandeja, not just in process logs.

**When to use:** Every routine fire, unconditionally — this is not optional hardening, it's what makes SCHED-05 true for the failure path, not just the happy path.

**Example:**
```python
# Source: pattern combines APScheduler's documented exception isolation
# (https://apscheduler.readthedocs.io/en/3.x/userguide.html#missed-job-executions) [CITED]
# with this project's existing audit-on-every-outcome convention (dispatcher.py:101-128)
async def _fire_routine(routine: Routine, *, engine, pending_store, audit, routine_store) -> None:
    try:
        plan = build_plan_from_routine(routine)
        decision = engine.evaluate(plan)
        result = await dispatch(plan, decision, pending_store=pending_store, audit=audit)
        routine_store.mark_fired(routine.id, outcome=result.get("outcome", "unknown"))
    except Exception as exc:  # noqa: BLE001 — intencional: nunca dejar que un fallo mate el scheduler
        audit.log(
            AuditEvent.new(
                task_id=f"routine-{routine.id}",
                actor_type=ActorType.SYSTEM,
                actor_id="scheduler",
                event_type=AuditEventType.TASK_FAILED,
                message=f"rutina {routine.name!r} falló al disparar: {exc}",
                payload={"routine_id": routine.id},
            )
        )
```

### Pattern 3: Catch-up-on-boot is domain logic, not an APScheduler feature

**What:** APScheduler's `misfire_grace_time`/`coalesce` only help when the *scheduler process itself* is running but delayed (e.g. event loop busy for a few seconds) — they do **not** know about fire times missed while the daemon was completely stopped, because a fresh `AsyncIOScheduler` on restart just computes the *next future* fire time from its trigger, with no memory of the past `[CITED: APScheduler misfire docs describe in-process delay handling, not cross-restart gap detection]`. This phase must implement its own boot-time diff: for each routine, compare `last_fired_at` (persisted in `RoutineStore`) against "what fire times should have occurred since then" and apply a **per-routine `catch_up: bool`** policy:
- `catch_up=True` (default for most routines): if one or more fires were missed, run the routine **once** immediately on boot (coalesced — never once per missed occurrence), then resume normal schedule.
- `catch_up=False`: skip all missed fires silently, resume from the next natural future fire time — appropriate for routines where a stale catch-up run would be actively wrong (e.g. "daily digest" for a day that already passed).

**When to use:** Every routine, at every daemon boot, before `scheduler.start()`.

**Trade-off:** This directly closes SCHED-04's "jamás doble-fire" requirement (Pitfall 7/8 below) — a routine's `last_fired_at` must be persisted **atomically with** the act of firing (same transaction as marking it fired in `RoutineStore`), not as a separate step, or a crash between "fired" and "persisted" re-triggers on next boot.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Cron expression parsing / next-fire-time computation | Regex-based cron parser, manual "next Tuesday at 08:00" date math | `APScheduler`'s `CronTrigger`/`IntervalTrigger` | Cron edge cases (month-end, day-of-week combinations, leap years) are exactly the kind of thing a 14-year-old maintained library has already debugged; hand-rolling reintroduces bugs this project doesn't need to pay for |
| Wall-clock-anchored sleep loop that doesn't drift | Copy-pasting `ttl_reaper`'s `while True: work(); sleep(interval)` pattern for calendar-anchored routines | `AsyncIOScheduler` (or, if zero-dependency is mandated, an explicit `next_run = align_to(now, schedule); sleep(max(0, (next_run-now).total_seconds()))` — never `sleep(fixed_interval)` for anything calendar-anchored | The reaper pattern is correct for *its own* purpose (approximate periodic sweeping) and actively wrong for "daily at 08:00" — see Pitfall 6 |
| Cross-restart missed-run detection | Nothing off-the-shelf solves this — it is inherently this project's own domain logic (needs `last_fired_at` + a `catch_up` policy owned by the Routine entity) | Custom boot-time diff in `RoutineScheduler` (Pattern 3 above) | No scheduling library's misfire/coalesce feature spans a full process restart the way this project needs; this is not a library gap, it is a different problem than what those features solve |

**Key insight:** The scheduling *library* problem (drift, cron parsing, single-process concurrency) is well-solved by APScheduler and should not be hand-rolled. The *catch-up-across-a-fully-stopped-daemon* problem is unique to this project's "daemon isn't always-on" deployment model and has no off-the-shelf solution — it must be designed explicitly (Pattern 3), not assumed to come free with whichever library is chosen.

## Common Pitfalls

### Pitfall 1: Naive `while True: sleep(fixed_interval)` scheduler drifts and can't do absolute-time routines

**What goes wrong:** Copying `ttl_reaper.py`'s exact pattern for "run daily at 08:00" computes each sleep duration relative to *now*, not to the next absolute fire time — accumulated execution time shifts the actual fire time later every cycle, and it cannot express calendar-anchored schedules at all (only "N seconds from whenever the loop last woke up").
**Why it happens:** The reaper pattern is the obvious template already in the codebase for "another background asyncio task" — it works for its own purpose (approximate TTL sweeping) but that purpose is different from calendar-anchored routines.
**How to avoid:** Use `AsyncIOScheduler` with `CronTrigger`/`IntervalTrigger`, which computes next-fire-time from wall-clock, not from an accumulated sleep. Set `misfire_grace_time` and `coalesce=True` explicitly per job rather than relying on defaults.
**Warning signs:** A routine documented as "daily at 08:00" observably fires a few minutes later each day.

### Pitfall 2: Daemon isn't always-on — missed routines during downtime silently vanish OR look like they "ran" when they didn't

**What goes wrong:** `wyss start` is a manual, not-always-on process (matches this project's existing Docker `restart=no` pattern on other machines per project memory). A routine scheduled for 08:00 while the daemon is down simply never fires with a naive scheduler — no error, nothing in audit. Worse: if the scheduler's fire produces a B/C `PendingProposal` the moment the daemon *does* restart, and the owner doesn't open the UI before the existing TTL reaper's window closes, the reaper auto-expires it as `CONFIRMATION_ANSWERED` with "propuesta expirada por TTL - auto-rechazada" — audit then shows a full `command.received → plan.created → confirmation.answered` trail that looks like the system "handled" the routine, when actually nothing executed and the owner never saw it.
**Why it happens:** MULTI-02's correct requirement (routines never auto-execute B/C) interacts badly with an intermittently-running daemon and a TTL-reaper built for interactive confirm-or-expire flows, not unattended multi-hour-gap catch-up.
**How to avoid:** Implement Pattern 3 (boot-time catch-up diff per routine, `catch_up: bool`). Additionally: give routine-originated `PendingProposal`s either a longer TTL than interactive `ask()` proposals, or surface "N routines missed since you were last online" as a first-class, hard-to-miss status on daemon/SPA connect — not buried in the audit feed.
**Warning signs:** Audit log shows `confirmation.answered` / "expirada por TTL" for a routine-originated proposal the owner never saw a notification for.
**Phase to address:** This phase, at design time — decide the catch-up policy shape before shipping the first routine type, not as a bug fix later.

### Pitfall 3: Double-fire from restart-time recompute and overlapping runs

**What goes wrong:** Two distinct risks: (1) recomputing "next run" from `last_fired_at` on every restart with an off-by-one (`>=` vs `>`, or not persisting `last_fired_at` in the SAME transaction as the fire itself) can re-trigger a routine that just fired, immediately after a restart; (2) if a routine's own execution takes longer than its own interval and nothing guards against overlap, two copies of the same routine can run concurrently, producing duplicate `PendingProposal` rows for the same logical action.
**Why it happens:** Persisting fire-state atomically and guarding against concurrent execution are both easy to skip when the first implementation is "make it fire once and call it done."
**How to avoid:** Persist `last_fired_at` atomically with the act of dispatching (same DB write/transaction as recording the routine fired — mirror `PendingStore.resolve()`'s pattern of a single `UPDATE ... WHERE status='pending'` with `rowcount` check). Set `max_instances=1` on every APScheduler job (built-in overlap guard) as defense in depth even though the daemon is single-process.
**Warning signs:** Two `PendingProposal` rows with the same routine origin and near-identical `created_at`.

### Pitfall 4: Timezone — Argentina has no DST, but "no DST" is not the same as "no timezone bugs"

**What goes wrong:** `America/Argentina/Buenos_Aires` has been fixed UTC-3 with no DST transitions since 2009, so the classic "spring-forward missed job" class mostly doesn't apply — but two other bugs remain real: (a) using naive `datetime.now()` instead of an explicit `ZoneInfo("America/Argentina/Buenos_Aires")`-aware datetime means the schedule silently follows the **host machine's** system timezone, a real risk given this project already runs across multiple independently-configured machines (Santiago-PC, Acer — per project memory, "Ops de sistema... NO sincronizan"); (b) SQLite stores timestamps as text — comparing a naive-UTC stored timestamp against a tz-aware "now" without normalizing both to the same reference silently miscomputes "is this routine due."
**Why it happens:** "Argentina has no DST" correctly rules out one bug class but is often (incorrectly) generalized to "no timezone bugs here at all."
**How to avoid:** Always construct `AsyncIOScheduler(timezone=ZoneInfo("America/Argentina/Buenos_Aires"))` explicitly — never rely on `tzlocal`'s host-detection fallback. Persist all `RoutineStore` timestamps in UTC ISO-8601 (matching the existing `datetime.now(UTC).isoformat()` convention already used throughout `pending_store.py`/`core/domain/audit.py`), convert to Argentina time only at the schedule-evaluation and display boundary.
**Warning signs:** A routine's actual fire time differs from its configured time by a fixed offset (not drifting, just wrong) — that pattern points to a naive/aware or UTC/local mismatch, not drift.

### Pitfall 5: `AuditEventType` is a closed `StrEnum` — adding `ROUTINE_TRIGGERED` needs a one-line domain change, and it's easy to skip

**What goes wrong:** `core/domain/audit.py`'s `AuditEventType` is documented as "taxonomía cerrada" (closed taxonomy). It would be tempting to reuse an existing type like `COMMAND_RECEIVED` for a routine firing to avoid touching `core/domain/`, but that would make routine-originated events indistinguishable from owner-typed `ask()` events in the audit trail — directly working against SCHED-05's "trigger, plan, decisión, resultado" auditability requirement and this milestone's own convention (Pattern (e) in the milestone architecture research: "auditar `actor_type=SYSTEM, actor_id=...`... para que la traza distinga claramente" for other new producers).
**Why it happens:** The taxonomy being "closed" reads as "don't add to it" when it actually means "don't let arbitrary strings in — but adding a new named member through the enum is exactly the sanctioned extension point."
**How to avoid:** Add `ROUTINE_TRIGGERED = "routine.triggered"` (or similar) as a new `AuditEventType` member. Verified this is safe at the storage layer: `audit/schema.py`'s `audit_events` table stores `event_type` as plain `TEXT NOT NULL` with **no `CHECK` constraint** enforcing the enum's closed set — so this is a pure Python/domain-layer change, no migration needed `[VERIFIED: read audit/schema.py directly, this session]`.
**Warning signs:** Routine fires show up in `wyss audit` labeled `command.received` / `plan.created` indistinguishable from a manual `wyss ask`.

## Code Examples

### Adding the new `AuditEventType` member (Pitfall 5)

```python
# Source: core/domain/audit.py (existing file, this session) — extend the StrEnum
class AuditEventType(StrEnum):
    COMMAND_RECEIVED = "command.received"
    PLAN_CREATED = "plan.created"
    POLICY_DECISION = "policy.decision"
    CONFIRMATION_REQUESTED = "confirmation.requested"
    CONFIRMATION_ANSWERED = "confirmation.answered"
    ACTION_STARTED = "action.started"
    ACTION_COMPLETED = "action.completed"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    COST_RECORDED = "cost.recorded"
    SPAN_STARTED = "span.started"
    SPAN_COMPLETED = "span.completed"
    SPAN_FAILED = "span.failed"
    ROUTINE_TRIGGERED = "routine.triggered"  # NUEVO — SCHED-05
```

### RoutineStore mirrors PendingStore's exact style (raw sqlite3, WAL, frozen row dataclass)

```python
# Source: pattern taken directly from orchestrator/pending_store.py (this session, verbatim style)
PENDING_PRAGMAS: tuple[str, ...] = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA busy_timeout=5000",
)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS routines (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  schedule_kind TEXT NOT NULL,   -- 'cron' | 'interval'
  schedule_expr TEXT NOT NULL,   -- cron string or interval seconds
  plan_json     TEXT NOT NULL,   -- serialized Action steps + summary/rationale template
  catch_up      INTEGER NOT NULL DEFAULT 1,
  status        TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'paused'
  created_at    TEXT NOT NULL,
  last_fired_at TEXT,
  last_outcome  TEXT
)
"""
# Same fail-closed WAL check as PendingStore.__init__ (raise AuditIntegrityError if
# journal_mode != 'wal') — this is the NTFS-safety guard already proven in this repo.
```

### Preview via next-N-fire-times (no croniter/humanize dependency needed)

```python
# Source: APScheduler CronTrigger public API pattern
# https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html [CITED]
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

def preview_next_fires(cron_expr: str, tz: ZoneInfo, count: int = 5) -> list[datetime]:
    """SCHED-01: preview legible antes de guardar — próximas N ejecuciones concretas,
    no un string humanizado que puede mentir sobre expresiones cron complejas."""
    trigger = CronTrigger.from_crontab(cron_expr, timezone=tz)
    fires: list[datetime] = []
    now = datetime.now(tz)
    for _ in range(count):
        now = trigger.get_next_fire_time(None, now)
        if now is None:
            break
        fires.append(now)
    return fires
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|--------------------|---------------|--------|
| `docs/architecture/WYSS_TARGET_ARCHITECTURE.md` §5 assumed APScheduler was "ya en stack" | Confirmed NOT in `pyproject.toml` `[project].dependencies` `[VERIFIED: read pyproject.toml directly]` | This phase | This phase must actually add the dependency (`uv add apscheduler`), not assume it's already wired |

**Deprecated/outdated:** APScheduler 4.x remains alpha/pre-release as of this project's prior milestone research (2026-07-10) and this session did not find evidence of a stable 4.x release — 3.11.3 remains the correct choice, matching the milestone `STACK.md`'s own note ("verificar estado de la 4.x al llegar a Fase 4" — verified now, still not stable) `[ASSUMED: based on milestone research + training knowledge; re-check `pip index versions apscheduler` immediately before implementation if a long gap occurs between this research and execution]`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|-----------------|
| A1 | `apscheduler`'s exact download count / GitHub star count / maintainer reputation beyond "exists on PyPI, slopcheck OK, repo linked from PyPI page" | Package Legitimacy Audit | Low — this is a training-data-consistent, multi-year-established library independently corroborated by this project's own prior milestone research; even if exact figures are stale, the qualitative "standard, mature, boring" characterization is very unlikely to be wrong |
| A2 | APScheduler 4.x is still alpha/not-stable-released as of 2026-07 | State of the Art | Low-Medium — if 4.x has since stabilized, the recommendation to pin 3.11.3 would need revisiting; the fix is cheap (re-run `uv add apscheduler --dry-run` and check the resolved major version before implementation) |
| A3 | The deterministic (no-LLM) `Plan`-template approach for routines is the right default for v1.0, vs. an NL-instruction-per-routine approach | Alternatives Considered / Architecture Patterns | Medium — this is a genuine product trade-off (flexibility vs. reliability), not a pure technical fact; the owner should confirm this default during planning/discuss-phase rather than treat it as settled, since it constrains what a routine "can express" in v1.0 (fixed action templates only, no free-text "recordame algo distinto cada vez") |
| A4 | Per-routine `catch_up: bool` (single coalesced catch-up fire vs. skip-to-next) is a sufficient policy shape for SCHED-04, vs. e.g. a per-routine max-catch-up-age or a richer catch-up strategy enum | Pattern 3 / Pitfall 2 | Low-Medium — a boolean is the simplest thing that satisfies "coalesce; jamás doble-fire" from the requirement text; if the owner wants finer control (e.g. "catch up only if missed by less than 2 hours") this would need a small follow-up, not a redesign |

**If this table is empty:** N/A — see rows above.

## Open Questions

1. **Should routine-authored `Plan`s ever call through `classify_intent`/`draft_plan` (LLM) instead of a fixed template, even as an opt-in?**
   - What we know: The deterministic path (Pattern in Architecture) is strictly more reliable and matches the "aburrido a propósito" philosophy; the milestone architecture research's own skeleton (`plan_builder: Callable[[Routine], Plan]`) already assumes a deterministic builder, not an LLM round-trip.
   - What's unclear: Whether the owner wants any routine to be "free text, resolved fresh every fire" (more flexible, less reliable) vs. this phase's recommended "free text resolved ONCE at creation time into a fixed template, re-fired identically every time."
   - Recommendation: Ship deterministic-template-only for v1.0 (Assumption A3); revisit if the owner explicitly asks for NL-per-fire flexibility later — that would be a genuinely separate feature, not a variant of this one.

2. **Exact TTL for routine-originated `PendingProposal`s vs. interactive `ask()` proposals.**
   - What we know: The existing `DEFAULT_TTL_BY_LEVEL` (`B: 3600s`, `C: 900s`) was tuned for an owner actively watching for a response right after typing a command; a routine fires unattended, possibly while the owner is asleep or away for hours.
   - What's unclear: Whether routine-originated proposals need a distinct (longer) TTL, or whether the "N routines missed" surfacing (Pitfall 2) is a sufficient mitigation on its own without touching the shared `ttl_for` mechanism.
   - Recommendation: Planner should decide during task breakdown whether `dispatch()`'s `ttl_for` callable needs an origin-aware variant, or whether a separate, longer-lived visibility mechanism (dashboard badge) is enough without touching the existing TTL constants (lower blast radius, since `ttl_for_risk`/`DEFAULT_TTL_BY_LEVEL` are shared with every other proposal type).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|---------|----------|
| `apscheduler` (PyPI) | Cron/interval trigger computation | ✗ (not yet installed in this project's venv — confirmed via `uv run python -c "import apscheduler"` failing this session) | Resolves to 3.11.3 via `uv add --dry-run` | Hand-rolled wall-clock-anchored sleep loop (Don't Hand-Roll table) if the owner explicitly wants zero new deps |
| `zoneinfo` (stdlib) + system tz database | Timezone-aware scheduling (`America/Argentina/Buenos_Aires`) | ✓ (verified working this session: `ZoneInfo("America/Argentina/Buenos_Aires")` resolved correctly without a separate `tzdata` package) | Python 3.12+ stdlib, project already requires `>=3.12` | — |
| SQLite WAL support on the target filesystem | `RoutineStore` (mirrors `PendingStore`'s WAL requirement) | ✓ (already proven — `PendingStore.__init__` already enforces and this pattern is copied verbatim) | — | — |

**Missing dependencies with no fallback:** none — `apscheduler` has a documented fallback if the owner rejects the new dependency.
**Missing dependencies with fallback:** `apscheduler` (see above).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` 9.x + `pytest-asyncio` 1.4.x (`asyncio_mode = "auto"` in `pyproject.toml`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/orchestrator/ -x -q` |
| Full suite command | `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports` (project's own mandated gate chain per `CLAUDE.md`) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|---------------------|--------------|
| SCHED-01 | Create cron/fixed-time routine from CLI/web with legible preview before saving | unit | `pytest tests/orchestrator/test_scheduler.py::test_preview_next_fires -x` | ❌ Wave 0 |
| SCHED-02 | Routine fire → Plan → policy gate: A executes direct, B/C → bandeja, never auto-exec | unit + integration | `pytest tests/orchestrator/test_scheduler.py::test_routine_fire_respects_policy_gate -x` | ❌ Wave 0 |
| SCHED-03 | List/pause/resume/delete routines + last result | unit | `pytest tests/orchestrator/test_routine_store.py -x` | ❌ Wave 0 |
| SCHED-04 | Post-downtime catch-up: coalesce, never double-fire | unit | `pytest tests/orchestrator/test_scheduler.py::test_catchup_on_boot_coalesces -x` and `::test_no_double_fire_on_restart` | ❌ Wave 0 |
| SCHED-05 | Every fire audited (trigger, plan, decision, result) | unit | `pytest tests/orchestrator/test_scheduler.py::test_fire_is_audited` and `::test_fire_failure_is_audited` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/orchestrator/ -x -q`
- **Per wave merge:** `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/orchestrator/test_routine_store.py` — covers SCHED-03 (CRUD, pause/resume/delete, last-result read-back), mirrors the style of existing `tests/orchestrator/test_daemon.py` fixtures (in-memory/tmp_path SQLite, no mocks needed since `RoutineStore` has no external I/O)
- [ ] `tests/orchestrator/test_scheduler.py` — covers SCHED-01/02/04/05: needs a fake/frozen clock or a way to inject "now" into `RoutineScheduler` so drift/catch-up tests don't require real sleeping (mirror however `tests/orchestrator/test_daemon.py`/existing tests already fake time for `ttl_reaper`, if they do — check `tests/orchestrator/` for an existing time-injection fixture before inventing a new one)
- [ ] Framework install: `uv add apscheduler` (dev + runtime dependency — this is a runtime feature, not test-only)
- [ ] A regression test asserting a routine that resolves to a B/C plan appears in `PendingStore.load_pending()` and is NEVER auto-executed even when `runner` is provided to the daemon — this is the direct automated verification of MULTI-02/SCHED-02's "jamás auto-ejecución" for this specific new producer

*(Wave 0 gaps are non-trivial for this phase: this is a new subsystem, not an extension of an existing one, so all test files are new.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|-----------------|---------|---------------------|
| V2 Authentication | No | Routines are owner-created via the ALREADY-authenticated CLI/web surface (same cookie/pairing model as every other command); this phase adds no new auth boundary |
| V3 Session Management | No | Same as above — reuses existing bridge session model unchanged |
| V4 Access Control | Yes | New JSON-RPC methods (`routine.add/list/pause/resume/delete`) must be reachable ONLY through the existing daemon Unix socket (`0o600` permissions, already enforced in `start_daemon`) — no new network-facing surface |
| V5 Input Validation | Yes | Cron expression strings from CLI/web input must be validated (`CronTrigger.from_crontab` raises on malformed input — catch and surface as a user-facing `ConfigError`-style message, never a raw traceback); routine `name`/`plan_json` must go through the same `Action`/`Plan` construction validation already used elsewhere (no new bespoke parser) |
| V6 Cryptography | No | No new secrets/crypto introduced by this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|------------------------|
| A malformed/malicious cron expression causing a crash or resource exhaustion (e.g. a pathological expression that fires extremely frequently) | Denial of Service | Validate cron/interval input at creation time (`CronTrigger.from_crontab` + a minimum-interval floor, e.g. reject intervals under some sane threshold like 60s, mirroring the spirit of existing aggregate thresholds in `core/domain/policy.py`) |
| A routine's `Plan` template referencing a since-revoked or since-escalated-risk action (e.g. a routine created when `file.write` to a path was B, later reclassified) | Tampering / Elevation of Privilege | None needed beyond what already exists: `dispatch()` always calls `engine.evaluate()` FRESH at fire time (never trusts a stored risk level) — this is the exact same "re-evaluate before trusting" discipline `daemon._confirm()` already applies to stored pending proposals, and it composes for free here since routines go through the same `evaluate()`+`dispatch()` call, not a cached decision |
| A paused routine silently resuming due to a state-management bug (owner believes it's off, it fires anyway) | Tampering (of intent) | `RoutineStore.status` must be checked by the scheduler's own fire-eligibility logic (not just at job-registration time) — i.e. `_fire_routine` should re-check `status == 'active'` immediately before dispatching, not only when jobs were registered at boot, so a pause taking effect mid-session is honored without requiring a daemon restart |

## Sources

### Primary (HIGH confidence)
- Direct reads this session: `src/orchestrator/daemon.py`, `dispatcher.py`, `pending_store.py`, `ttl_reaper.py`, `plan_renderer.py`; `src/core/domain/audit.py`, `plan.py`, `risk.py`, `policy.py`; `src/core/ports/orchestrator.py`; `src/orchestrator/llm_orchestrator.py`; `src/bootstrap/cli.py` (lines 400-520, incl. `_DeterministicOrchestrator`), `config.py` (full), `web.py` (endpoint list); `src/audit/schema.py`; `pyproject.toml`; `.planning/config.json`
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md`, `.planning/research/SUMMARY.md`, `.planning/research/ARCHITECTURE.md`, `.planning/research/PITFALLS.md` (this project's own prior milestone-level research, HIGH confidence — grounded in the same codebase)
- `uv add apscheduler --dry-run` — live PyPI resolution this session (`apscheduler==3.11.3`, `tzlocal==5.4.4`) `[VERIFIED: PyPI registry]`
- `slopcheck install apscheduler` — clean `[OK]` verdict this session

### Secondary (MEDIUM confidence)
- [APScheduler AsyncIOScheduler docs](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html) — official docs, WebSearch-retrieved this session (Context7 MCP was not reachable in this environment for a fresh fetch; content cross-checked against this project's own prior milestone `ARCHITECTURE.md` which cites the same URL from an earlier Context7-backed session)
- [APScheduler user guide — misfire/coalesce](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — official docs
- [APScheduler CronTrigger module docs](https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html) — official docs
- WebSearch: "APScheduler 3.11 latest version PyPI release date changelog" — confirms 3.11.x is the current stable line, no evidence of a stable 4.x as of this session

### Tertiary (LOW confidence)
- None used for load-bearing claims in this document; all APScheduler behavioral claims were either verified against official docs or against this project's own prior HIGH-confidence milestone research.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — APScheduler 3.11.3 existence/version verified live against PyPI this session; architectural placement (orchestrator/, not a new package) directly derived from reading the actual import-linter contracts in `pyproject.toml`
- Architecture: HIGH — every pattern here is a direct extension of code read this session (`daemon.py`'s `RunningDaemon`/`start_daemon`, `dispatcher.py`'s `dispatch()`, `pending_store.py`'s style)
- Pitfalls: HIGH — catch-up/double-fire/timezone pitfalls are logical consequences of the daemon's actual (verified) always-off-by-default deployment model and the actual (verified) `ttl_reaper` pattern, not generic scheduling folklore
- APScheduler-specific API surface (exact exception-isolation behavior, `get_next_fire_time` signature) — MEDIUM: could not re-fetch via Context7 in this environment; relied on official docs URLs already vetted in this project's own prior research plus WebSearch this session

**Research date:** 2026-07-10
**Valid until:** 30 days for the architectural recommendations (stable, codebase-grounded); re-verify the exact `apscheduler` version via `uv add apscheduler --dry-run` immediately before implementation if more than a few weeks pass, since a 4.x stable release would change the Alternatives Considered trade-off

---
*Research for: Phase 9 — Routine Scheduler (Wyss v1.0)*
