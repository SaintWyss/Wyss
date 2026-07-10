# Phase 10: Notion Adapter - Research

**Researched:** 2026-07-10
**Domain:** External read/write integration (Notion API) as a policy-gated `Tool` adapter in an existing hexagonal Python daemon
**Confidence:** HIGH (composition-root wiring, policy engine, executor dispatch, config loading — all read directly from `src/`); HIGH (notion-client 3.1.0 API — verified against the exact tagged source on GitHub + official Notion docs, not training-data guesswork); MEDIUM (preview/UX shape for NOTION-02 — a design proposal, not a verified existing pattern)

## Summary

Notion becomes the first genuinely external (`net.*`-class) capability in Wyss — `SECURITY_MODEL.md` explicitly flags this gap ("No existe tipo de acción de red... Formalizar en v0.2 si se agrega capacidad de red"). This phase is that formalization. The milestone-level research (`SUMMARY.md`/`ARCHITECTURE.md`/`PITFALLS.md`) already established the right shape — new `notion.*` Action types dispatched through a `Tool`-protocol adapter, gated by the same `CognitivePolicyEngine` as `file.*`/`shell.*`/`git.*` — but this phase-level research found one materially important correction and one materially important simplification versus that milestone research:

**Correction:** `execution/executor.py::PlanExecutor` does **not** have a generic adapter registry today. `_adapter_for()` is a hardcoded `if/elif` over three concrete adapter types passed as named constructor kwargs (`filesystem`, `shell`, `git`). The milestone ARCHITECTURE.md's "mapa de adapters += {'notion': NotionTool}" describes the *aspiration*, not the *current code*. Adding Notion means extending this exact hardcoded pattern (new kwarg + new `if` branch + new union member), mirroring precisely how `git` was added alongside `file`/`shell` — not writing to a dict-based registry that doesn't exist yet. A full registry refactor is possible but is out of scope for "surgical" (CLAUDE.md) — flagged as an open question, not a requirement.

**Simplification:** notion-client 3.1.0 (released 2026-05-12, confirmed via GitHub tag `v3.1.0`, PyPI `pypi.org/project/notion-client` = 3.1.0) targets Notion API version `2025-09-03`, which shipped two endpoints the milestone research did not know about: `pages.retrieve_markdown(page_id)` and `pages.update_markdown(page_id, ...)`. These convert a page's full block tree to/from a markdown string **server-side**. This eliminates the recursive `blocks.children.list` walk, the depth-cap engineering, and most of the pagination-vs-confirmation-gate tension that `PITFALLS.md` (Pitfalls 10-11) worried about for the *page read/write* path. Database/data-source queries still need real pagination (see below) — that part of the milestone research stands.

**Primary recommendation:** Four action types — `notion.read_page` (A), `notion.query_database` (A), `notion.write_page` (C), `notion.append_block` (C) — implemented by a `NotionTool` in a new top-level `notion/` package, added to `PlanExecutor`'s existing hardcoded dispatch, with `notion.*` base levels hardcoded into `src/bootstrap/config.py::_BASE_LEVELS` (this dict is **not** TOML-configurable — it is a Python constant, contrary to what a TOML-driven mental model might suggest) and mirrored into the 5 conftest fixtures that copy that dict for tests.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NOTION-01 | Leer página/DB en lenguaje natural, nivel A con base_levels explícito | `notion.read_page` via `pages.retrieve_markdown`; `notion.query_database` via `databases.retrieve` + `data_sources.query` (paginated). Both added to `_BASE_LEVELS` as `RiskLevel.A`. See Code Examples + Pitfall N1 (fail-closed-to-C gap). |
| NOTION-02 | Create/edit cae como propuesta B/C con preview del cambio | `notion.write_page`/`notion.append_block` = `RiskLevel.C` (mirrors `file.write`/`file.create`). Preview = the plan's rendered `parameters` (markdown diff or new content), no live Notion fetch needed at preview time — see Pattern 3. |
| NOTION-03 | Rate limits retry/backoff en 429 + paginación completa | notion-client's built-in `RetryOptions` (default `max_retries=2`, exponential backoff, honors `Retry-After`) handles the 429 case automatically — don't hand-roll. Pagination for `data_sources.query`/`blocks.children.list` must be hand-rolled (cursor loop) because it must complete **before** the confirmation gate (Pitfall N2, inherited from milestone Pitfall 10). |
| NOTION-04 | Token en config/.env, jamás repo, todo auditado | `NOTION_TOKEN` via existing `_load_dotenv`/`.env` mechanism; add to `_GATEWAY_ENV_KEYS`-equivalent so the gateway minimizer blocks it from leaking into LLM prompts by substring; never put in `payload` passed to `AuditPort.log`. See Security Domain. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Notion API auth (token) | Bootstrap (composition root) | — | `.env` loading is Pydantic-boundary-adjacent, already centralized in `bootstrap/config.py`; core/execution never see raw secrets |
| Notion read (page/DB) | Execution (`notion/` new package) | — | Same tier as `file.read`/`git.status`: a `Tool` adapter invoked by `PlanExecutor`, gated by policy before it runs |
| Notion write (page/block) | Execution (`notion/` new package) | Policy (`core/policy`) | Adapter performs the call; policy engine decides A/B/C/D before the adapter is ever invoked — write risk is a policy-tier decision, not an execution-tier one |
| Risk classification (`notion.*` base levels) | Policy / Bootstrap (`_BASE_LEVELS` constant) | — | Hardcoded in `bootstrap/config.py`, not TOML — matches how `file.*`/`git.*`/`finance.*` levels are set today (no owner-facing config surface for this) |
| Preview of a pending write | Orchestrator (`plan_renderer.py`) | Bootstrap (bridge `/api/pending`) | Preview is the plan's rendered steps, exactly like every other B/C proposal — no new preview subsystem needed |
| Anti-injection wrapping of read content | Agents (`_format_hits_safe`-style wrapper) or Orchestrator prompt assembly | — | Content read from Notion is external, untrusted data; must be delimited as data before touching any LLM prompt (same discipline as knowledge-base hits) |
| Rate limit / retry | notion-client SDK (external, HIGH confidence) | — | Client-level `RetryOptions` handles 429/5xx automatically; Wyss code should configure, not reimplement |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `notion-client` | 3.1.0 (PyPI, released 2026-05-12) `[VERIFIED: PyPI registry + GitHub tag v3.1.0]` | Official-community Python SDK for the Notion REST API (sync + async), maintained by ramnes/notion-sdk-py | Only actively maintained Python Notion SDK; `AsyncClient` fits the codebase's `asyncio`-native `Tool.execute()` contract directly; depends only on `httpx>=0.23.0`, already a first-class dependency of this repo (`httpx>=0.28.1` in `pyproject.toml`) |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `httpx` | already `>=0.28.1` in `pyproject.toml` | Transport notion-client sits on; can be injected as a shared `httpx.AsyncClient` for testability (same pattern as `tests/gateway/conftest.py::http_client` + `respx_mock`) | Always — inject rather than let notion-client construct its own client, to keep tests network-free |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `notion-client` (official SDK) | Raw `httpx` calls against `api.notion.com/v1` directly | Loses built-in `RetryOptions` (429/5xx backoff), request signing helpers, and the new `retrieve_markdown`/`update_markdown` convenience — would have to hand-roll all of it. Not worth it; the SDK is thin and MIT-licensed. |
| `pages.retrieve_markdown`/`update_markdown` (2025-09-03 API) | Manual `blocks.children.list` recursion + custom block→markdown renderer | The manual path is exactly what `PITFALLS.md` (Pitfalls 10-11) warned about: recursion depth, linked-page scope creep, pagination-vs-confirmation-gate races. The markdown endpoints solve all three server-side (with a documented 20k-block cap + `truncated` flag). Recommend the markdown endpoints as primary; keep raw block access only if a future need requires structured (non-text) block data. |

**Installation:**
```bash
uv add notion-client
```

**Version verification:** Confirmed directly — `curl -s https://pypi.org/pypi/notion-client/json` → `version: "3.1.0"`, `requires_dist: ["httpx>=0.23.0", ...]`. Cross-checked against `github.com/ramnes/notion-sdk-py` tag `v3.1.0` (commit `4569053d`, released per GitHub Releases API `2026-05-12T08:58:08Z`). The milestone-level `ARCHITECTURE.md` had already named `notion-client 3.1` at MEDIUM confidence (no Context7 match found for the Python package at that time) — this phase-level research upgrades that to HIGH by reading the actual tagged source.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| notion-client | PyPI | active since 2021 (v1.0.0), v3.1.0 released 2026-05-12 | large (well-established Notion community SDK) | github.com/ramnes/notion-sdk-py | `[OK]` — flagged the `-client` suffix as "classic LLM naming pattern" but confirmed "package is established" | Approved |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none — slopcheck ran successfully (`uvx slopcheck install notion-client`) and returned `[OK]` for the sole new dependency this phase introduces.

## Architecture Patterns

### System Architecture Diagram

```
Owner instruction ("leeme la página de reuniones de hoy" / "creá una página con X")
    │
    ▼
LLMOrchestrator.draft_plan()  ── _ACTION_TYPES tuple MUST include notion.* entries
    │                             (PR-11 regression: an omitted type here makes the
    │                             LLM fall back to shell.run/C even for a plain read)
    ▼
Plan{ steps=[ Action(type="notion.read_page", target="<page_id_or_url>", ...) ] }
    │
    ▼
CognitivePolicyEngine.evaluate(plan)   ── _BASE_LEVELS["notion.read_page"]=A,
    │                                      ["notion.query_database"]=A,
    │                                      ["notion.write_page"]=C,
    │                                      ["notion.append_block"]=C
    │                                      (unregistered type → C fail-closed, docs/13)
    ▼
dispatch(plan, decision, pending_store, audit)
    ├─ A (read)  → PlanExecutor.run(plan) directo
    └─ B/C (write) → PendingStore.save() → Bandeja (SPA/CLI/APK) → owner confirma
                       → daemon._confirm() re-evalúa → PlanExecutor.run(plan)
    │
    ▼
PlanExecutor._adapter_for(action)   ── prefix "notion" → self._notion (NUEVO kwarg)
    │
    ▼
NotionTool.execute(action)  (notion/tool.py, implements core.ports.execution.Tool)
    │  read_page   → client.pages.retrieve_markdown(page_id)
    │  query_db    → client.databases.retrieve(db_id) → data_source_id(s)
    │                 → client.data_sources.query(data_source_id, start_cursor=...) loop
    │  write_page  → client.pages.update_markdown(page_id, type="update_content", ...)
    │                 or client.pages.create(parent=..., properties=..., markdown=...)
    │  append_block→ client.blocks.children.append(block_id, children=[...])
    ▼
notion-client AsyncClient (RetryOptions handles 429/5xx automatically)
    │
    ▼
ToolResult(success, detail, payload={"output": <markdown or rendered rows>, ...})
    │
    ▼
PlanExecutor._visible_output()  ── same generic "output" key convention as file.read
    │
    ▼
Owner sees the content (CLI/web/APK) — external content wrapped as DATA, never
concatenated raw into a future LLM prompt (mirrors agents/configured_agent.py::_format_hits_safe)
```

### Recommended Project Structure

```
src/
├── notion/                        # NUEVO paquete top-level (import-linter independence)
│   ├── __init__.py
│   ├── client.py                  # wrapper delgado: construye AsyncClient con token+httpx.AsyncClient inyectado
│   ├── tool.py                    # NotionTool(Tool): name/max_risk/describe/execute/verify
│   ├── markdown.py                # helpers: cap-check del truncated flag, formato de preview
│   └── pagination.py              # cursor loop explícito para data_sources.query / blocks.children.list
├── execution/
│   └── executor.py                # MODIFICADO: PlanExecutor.__init__ += notion kwarg,
│                                   #             _adapter_for += "notion" branch,
│                                   #             union type += NotionTool
├── bootstrap/
│   ├── config.py                  # MODIFICADO: _BASE_LEVELS += 4 notion.* entries,
│                                   #             _GATEWAY_ENV_KEYS-equivalent += NOTION_TOKEN,
│                                   #             _load_dotenv ya lo carga sin cambios
│   └── cli.py                     # MODIFICADO: _build_plan_runner construye NotionTool,
│                                   #             lo pasa a PlanExecutor(notion=...)
└── orchestrator/
    └── llm_orchestrator.py        # MODIFICADO: _ACTION_TYPES += notion.* + guía de uso en _draft_prompt

tests/
├── notion/                        # NUEVO — espejo de tests/execution/ para el nuevo package
│   ├── conftest.py                 # respx_mock + httpx.AsyncClient fixture (mismo patrón que tests/gateway/conftest.py)
│   ├── test_tool.py                # execute()/verify()/describe() por action type
│   ├── test_pagination.py          # cursor loop: has_more=True dos veces, luego False
│   └── test_rate_limit.py          # 429 → RetryOptions reintenta (mock respx con secuencia de respuestas)
├── policy/conftest.py              # MODIFICADO: DEFAULT_BASE_LEVELS += notion.* (mirror 1/5)
├── execution/conftest.py           # MODIFICADO: DEFAULT_BASE_LEVELS += notion.* (mirror 2/5)
├── orchestrator/conftest.py        # MODIFICADO: mirror 3/5
├── security/conftest.py            # MODIFICADO: mirror 4/5
└── agents/conftest.py              # MODIFICADO: mirror 5/5 (NOTE: milestone research said "4 conftests
                                     #             espejo" — this phase-level research found FIVE:
                                     #             agents/, execution/, orchestrator/, policy/, security/,
                                     #             all matching `_BASE_LEVELS`/`BASE_LEVELS` — grep-verified)
```

### Pattern 1: `NotionTool` as a fifth `Tool` adapter, wired through the executor's existing hardcoded dispatch (not a new registry)

**What:** `PlanExecutor.__init__` currently takes `filesystem: FileSystemAdapter, shell: ShellAdapter, git: GitAdapter` as required named kwargs, and `_adapter_for()` is a 3-branch `if/elif/raise ValueError` on `action.type.split(".")[0]`. Add `notion: NotionTool` as a fourth required kwarg (or `NotionTool | None` if the phase wants Notion to be optional-by-config), extend the return-type union, and add one `if prefix == "notion": return self._notion` branch. This is a two-line diff mirroring exactly how `git` sits next to `file`/`shell` today — not a refactor to a `dict[str, Tool]` registry (which doesn't exist yet; `ARCHITECTURE.md`'s "mapa de adapters" phrasing describes the target shape, not the current file).

**When to use:** Any time a new `Tool` is added to this executor, until/unless a future phase deliberately refactors to a real registry (bigger diff, not required for this phase's 4 action types).

**Example:**
```python
# src/execution/executor.py (diff sketch)
class PlanExecutor:
    def __init__(
        self,
        *,
        filesystem: FileSystemAdapter,
        shell: ShellAdapter,
        git: GitAdapter,
        notion: "NotionTool",          # NUEVO
        journal: UndoJournal,
        audit: object,
    ) -> None:
        ...
        self._notion = notion          # NUEVO

    def _adapter_for(
        self, action: Action
    ) -> FileSystemAdapter | ShellAdapter | GitAdapter | "NotionTool":
        prefix = action.type.split(".")[0]
        if prefix == "file":
            return self._filesystem
        if prefix == "shell":
            return self._shell
        if prefix == "git":
            return self._git
        if prefix == "notion":         # NUEVO
            return self._notion
        raise ValueError(f"no adapter for action type: {action.type!r}")
```

### Pattern 2: Read path uses the 2025-09-03 markdown endpoints, not manual block recursion

**What:** `client.pages.retrieve_markdown(page_id, include_transcript=False)` returns the page's full content pre-rendered as markdown, server-side, with a documented cap (~20,000 blocks; response includes `truncated: true` + `unknown_block_ids` beyond that). This directly satisfies NOTION-01's "ver el contenido" without hand-rolling recursive `blocks.children.list` calls or a custom block-type-to-text renderer.

**When to use:** `notion.read_page` — always prefer `retrieve_markdown` over manual block walking, unless a future requirement needs structured (non-text) block metadata (e.g., checkbox state, specific property types) that markdown flattens away.

**Example:**
```python
# notion/tool.py (sketch) — Source: github.com/ramnes/notion-sdk-py (tag v3.1.0),
# developers.notion.com/reference/retrieve-page-markdown
async def _read_page(client: AsyncClient, page_id: str) -> ToolResult:
    response = await client.pages.retrieve_markdown(page_id, include_transcript=False)
    text = response["markdown"]  # exact key per official docs
    if response.get("truncated"):
        text += "\n\n[NOTA: contenido truncado — página excede ~20k bloques]"
    return ToolResult(success=True, detail=f"leída página {page_id}", payload={"output": text})
```

### Pattern 3: Write preview is the rendered plan, not a live diff fetch

**What:** NOTION-02 requires "preview del cambio antes de confirmar." The simplest, most honest option — consistent with how every other B/C proposal in this codebase already previews (`orchestrator/plan_renderer.py::plan_to_text`, already used for SCHED-01's schedule preview) — is to render the `Action.parameters` the LLM proposed (the markdown to insert/replace, or the new page's title+content) as the preview text. This requires **zero** additional Notion API calls at plan-creation time.

A live "fetch current state, compute diff" preview (showing exactly what changes in context) is more accurate for `update_content`/`replace_content_range` edits (where the owner might want to see the *surrounding* text, not just the replacement), but costs an extra `pages.retrieve_markdown` call at draft time and reintroduces a version of Pitfall 10 (state may have changed between preview-fetch and confirm-execute — a bounded, minor race, not the pagination-cursor-expiry problem, since `retrieve_markdown` isn't cursor-based).

**Recommendation:** Ship the rendered-plan preview (Option A) for v1 — it is simple, honest, and consistent with SCHED-01's existing UX. Flag the live-diff option as a documented `Open Question` for the owner/planner to explicitly accept or reject, not a silent scope decision.

**When to use:** Any `notion.write_page`/`notion.append_block` action reaching B/C.

### Pattern 4: Pagination completes fully before the policy gate, never split across it

**What:** Inherited directly from milestone `PITFALLS.md` Pitfall 10 — Notion's `next_cursor` is meant to be consumed in the immediately-following request, and Wyss's B/C flow can pause for minutes (TTL up to 900s for C). For `notion.query_database`, this only matters at the **read** side (level A, no confirmation gate at all — so the tension doesn't actually apply to `notion.query_database` itself). It matters if a *future* action ever needs "read N rows, then write based on them" as a single gated plan: the read-and-paginate must complete fully (as a level-A pre-step) before the write half is evaluated/confirmed, never interleaved.

**When to use:** Any Notion action design where a write depends on prior paginated reads.

**Example (cursor loop, hand-rolled — deliberately not using the SDK's generic `async_collect_paginated_api` helper, which expects a zero-arg-except-cursor callable and would need an awkward `functools.partial` to bind `data_source_id`; an explicit loop is more legible and matches this project's "aburrido a propósito" style):**
```python
# notion/pagination.py (sketch) — Source: github.com/ramnes/notion-sdk-py helpers.py
# (iterate_paginated_api/async_iterate_paginated_api show the has_more/next_cursor contract)
async def _query_all_rows(client: AsyncClient, data_source_id: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    cursor: str | None = None
    while True:
        response = await client.data_sources.query(data_source_id, start_cursor=cursor)
        rows.extend(response["results"])
        if not response.get("has_more"):
            break
        cursor = response["next_cursor"]
    return rows
```

### Anti-Patterns to Avoid

- **Querying `databases.query(database_id)` directly:** this method **no longer exists** in notion-client 3.1.0 / Notion API `2025-09-03`. Prior to September 2025, a database had exactly one implicit data source and the API combined the concepts; the current API separates them. `notion.query_database` must first `databases.retrieve(database_id)` to read the `data_sources: [{id, name}, ...]` list, then call `data_sources.query(data_source_id)` per source. Most owner databases will have exactly one data source (pre-migration databases default to one) — document the multi-data-source case as an explicit limitation (query the first, or all and concatenate; either is a defensible v1 choice) rather than silently mishandling it.
- **Registering the Notion adapter without adding its `action.type`s to `LLMOrchestrator._ACTION_TYPES`:** this exact mistake already happened once in this codebase (PR-11, documented in the file's own comment: "existían en el executor y la política pero faltaban acá, así que el LLM caía en shell.run (C)"). Any new `notion.*` type must be added to both `_BASE_LEVELS` (policy) and `_ACTION_TYPES` (planner prompt) or the LLM will never emit it.
- **Unconditional `handler.proceed()`-style trust of Notion content:** content returned from `retrieve_markdown` is untrusted external text. It must never be concatenated raw into a `LLMOrchestrator.draft_plan`/gateway prompt — wrap it with the same "dato, no instrucción" delimiter discipline as `agents/configured_agent.py::_format_hits_safe`.
- **Reusing `execution/journal.py::UndoJournal` for Notion writes:** `notion/` is an independent import-linter layer and cannot import `execution/`. Notion's own reversibility primitive is the API's `archived`/`in_trash` flags on pages/blocks (`PATCH` with `in_trash: true`), not Wyss's byte-level backup journal. Don't wire it in.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 429 backoff/retry | Custom exponential-backoff wrapper around raw `httpx` calls to Notion | `notion_client.RetryOptions` (already built into `AsyncClient`, default `max_retries=2`, exponential backoff, honors `Retry-After`) | The SDK already implements exactly the NOTION-03 requirement; a hand-rolled version would duplicate untested logic. Only tune `max_retries`/`max_retry_delay_ms` via `ClientOptions(retry=RetryOptions(...))` if defaults prove insufficient. |
| Page content → readable text | Recursive `blocks.children.list` walk + custom per-block-type renderer + depth cap | `client.pages.retrieve_markdown(page_id)` (Notion API 2025-09-03+) | Server-side conversion handles nesting, tables, toggles, and caps at ~20k blocks with an explicit `truncated` flag — reinventing this is exactly the "Performance Trap" the milestone `PITFALLS.md` flagged (Pitfall 11) for the pre-2025-09 API shape. |
| Writing formatted content into a page | Hand-building Notion block-type JSON (paragraph/heading/bulleted_list_item/... objects) | `client.pages.create(..., markdown=...)` or `client.pages.update_markdown(page_id, type="update_content"/"replace_content", ...)` | Same server-side conversion, inverse direction. `update_content` (search/replace `old_str`/`new_str`) is explicitly the currently-recommended method per official docs; `insert_content`/`replace_content_range` are flagged "may be deprecated." |
| URL → page/database ID extraction | Regex parsing of `notion.so/...` URLs | `notion_client.helpers.extract_page_id(url)` / `extract_database_id(url)` / `extract_notion_id(url_or_id)` | Already implemented and tested in the SDK; owner will likely paste full Notion URLs as targets, not bare UUIDs. |

**Key insight:** notion-client 3.1.0 is unusually "batteries-included" for exactly the two hardest parts of this phase (rate-limit retry, block-tree rendering) — the temptation to write custom versions of either is a direct regression versus what already ships in the dependency this phase is adding anyway.

## Common Pitfalls

### Pitfall N1: `notion.*` unregistered in `_BASE_LEVELS` makes even reads pedir confirmación fuerte

**What goes wrong:** `CognitivePolicyEngine._base_level()` (src/core/policy/engine.py:77-79) returns `self._rules.unknown_action_level` (fail-closed, effectively C) for any `action.type` not present in `base_levels`. If `notion.read_page`/`notion.query_database` are not added to `_BASE_LEVELS` in `src/bootstrap/config.py`, a plain read pays the level-C confirmation cost — directly contradicts NOTION-01's "nivel A."

**Why it happens:** `_BASE_LEVELS` is a hardcoded Python dict, not something that shows up in `config.toml` — easy to forget it exists as a *second* place (beyond writing the adapter) that needs editing.

**How to avoid:** Add all four `notion.*` entries to `_BASE_LEVELS` (line ~55-75 of `bootstrap/config.py`) in the SAME commit/task that adds the `NotionTool`. Also update all 5 conftest mirrors (see Recommended Project Structure) or policy tests for other phases will silently diverge from production config.

**Warning signs:** A manual `wyss ask "leeme la página X de Notion"` prompts CONFIRMAR when it should execute directly.

**Phase to address:** This phase, first task (config before adapter, so tests can assert A immediately).

---

### Pitfall N2: `databases.query()` does not exist in notion-client 3.1.0 — must go through `data_sources`

**What goes wrong:** Any code written from training-data familiarity with the "old" Notion API (pre-September 2025) will call `client.databases.query(database_id, ...)`. This method was **removed**; `DatabasesEndpoint` in 3.1.0 only has `retrieve`, `update`, `create` — querying moved to `DataSourcesEndpoint.query(data_source_id, ...)`.

**Why it happens:** Training data / muscle memory from the older, single-data-source-per-database API shape; the September 2025 restructuring ("data sources" as a layer between databases and pages) is recent enough that most existing tutorials/blog posts still show the old shape.

**How to avoid:** Always `databases.retrieve(database_id)` first, read the `data_sources` array from the response, then `data_sources.query(data_source_id, ...)`. Verified directly against the tagged `v3.1.0` source (`api_endpoints.py`) and `developers.notion.com/reference/database`.

**Warning signs:** `AttributeError: 'DatabasesEndpoint' object has no attribute 'query'` at runtime, or (if guessed instead of verified) a plan that silently never queries anything.

**Phase to address:** This phase — verify with an integration smoke test against a real database before considering NOTION-01 done for the database-read case.

---

### Pitfall N3 (inherited, confirmed still applicable): Recursive/linked-page scope creep for anything NOT going through `retrieve_markdown`

**What goes wrong:** If a future action needs raw block access (not markdown) — e.g., to read a checkbox's checked-state — recursing into `has_children` blocks can silently follow links into sibling pages the action was never scoped to, and/or blow past the 3 req/s average rate limit combinatorially. (Milestone `PITFALLS.md` Pitfall 11, still valid for anything outside the markdown-endpoint happy path.)

**How to avoid:** For this phase's four action types, this risk is avoided entirely by relying on `retrieve_markdown`'s server-side 20k-block cap. If a later phase adds raw block access, re-apply Pitfall 11's mitigations (depth/count caps, treat linked child pages as a fresh authorization boundary).

**Phase to address:** N/A for this phase's scope (avoided by design); re-flag if raw block access is ever added.

---

### Pitfall N4: A page/database not shared with the integration returns as if it doesn't exist

**What goes wrong:** Notion's permission model requires a page/database to be explicitly shared with the integration (the token's owner). An unshared target returns 404/403, which can look like a bug rather than a permissions gap — especially confusing for the owner who can see the page fine in their own Notion client.

**Why it happens:** Confirmed as already-known operational behavior from the owner's own separate Notion integration in this same environment (per milestone `ARCHITECTURE.md`, "gotcha operativo conocido").

**How to avoid:** `NotionTool.execute()` must translate the notion-client `APIResponseError` (with `code` matching `object_not_found`/`restricted_resource`) into a `ToolResult(success=False, detail="página no compartida con la integración Wyss, o no existe")` — a legible result, not a raw exception. `Tool.execute()` errors are ALWAYS results per this codebase's convention (`ToolResult(success=False)`, never a propagated exception) — this is an existing hard rule (`CLAUDE.md`: "errores de adapters son resultados... no excepciones propagadas"), directly applicable here.

**Warning signs:** Owner reports "it says the page doesn't exist but I can open it in my browser."

**Phase to address:** This phase, in `NotionTool.execute()`'s error handling.

---

### Pitfall N5: `NOTION_TOKEN` leaking into LLM context/audit payload

**What goes wrong:** The token itself must never appear in an `AuditEvent.payload`, a gateway prompt, or a trace. This codebase already has a mechanism for exactly this class of problem (`_GATEWAY_ENV_KEYS` → `_gateway_env_values()` → `ContextMinimizer` substring-blocks any `.env` value ≥8 chars from outbound LLM traffic) — but that list is currently scoped to LLM provider keys (`ANTHROPIC_API_KEY`, `LITELLM_MASTER_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`). `NOTION_TOKEN` is a *different* kind of secret (not an LLM provider key) but the same minimizer mechanism is the right reuse target — a token value long enough (Notion integration tokens are ~50 chars) would never legitimately need to appear in an LLM prompt.

**How to avoid:** Add `NOTION_TOKEN` to the `_GATEWAY_ENV_KEYS` tuple (or an equivalently-named superset, if the phase renames it to reflect "secrets the minimizer must block," not just "gateway provider keys") so its value is swept into `env_values` and blocked by substring the same way. Never pass the raw token into `ToolResult.payload` or `AuditEvent.payload` — only pass the page/database ID and outcome.

**Phase to address:** This phase, alongside adding `NOTION_TOKEN` to `.env`/`config/.env.example`.

## Code Examples

### Constructing the AsyncClient with an injectable httpx transport (testability)

```python
# notion/client.py (sketch) — Source: github.com/ramnes/notion-sdk-py client.py (tag v3.1.0)
import httpx
from notion_client import AsyncClient, ClientOptions, RetryOptions


def build_notion_client(token: str, *, http_client: httpx.AsyncClient | None = None) -> AsyncClient:
    """Construye el AsyncClient; inyectar http_client en tests para usar respx (sin red)."""
    options = ClientOptions(
        auth=token,
        retry=RetryOptions(max_retries=3),  # NOTION-03: default es 2, subir un poco es aceptable
    )
    if http_client is not None:
        return AsyncClient(options=options, client=http_client)
    return AsyncClient(options=options)
```

### Test pattern for 429 handling (mirrors `tests/gateway/conftest.py`'s `respx_mock`/`http_client` fixtures)

```python
# tests/notion/test_rate_limit.py (sketch) — mirrors tests/gateway/test_retry.py's structure
import httpx
import respx


async def test_query_retries_on_429(respx_mock: respx.MockRouter, http_client: httpx.AsyncClient) -> None:
    route = respx_mock.get("https://api.notion.com/v1/pages/abc123").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}, json={"code": "rate_limited"}),
            httpx.Response(200, json={"object": "page", "id": "abc123", "properties": {}}),
        ]
    )
    client = build_notion_client("secret_fake", http_client=http_client)
    result = await client.pages.retrieve("abc123")
    assert result["id"] == "abc123"
    assert route.call_count == 2  # 1 fallo 429 + 1 reintento exitoso
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `databases.query(database_id)` — one implicit data source per database | `databases.retrieve(database_id)` → `data_sources` list → `data_sources.query(data_source_id)` | Notion API version `2025-09-03` (per notion-client `ClientOptions.notion_version` default) | Any NOTION-01 database-read code must resolve the data source ID first; the old single-call shape 404s or is simply absent from the SDK |
| Manual `blocks.children.list` recursion + custom markdown renderer | `pages.retrieve_markdown(page_id)` / `pages.update_markdown(page_id, ...)` | Same `2025-09-03` API version | Eliminates most of milestone `PITFALLS.md`'s Pitfall 10/11 engineering burden for the page read/write path specifically |

**Deprecated/outdated:**
- `insert_content`/`replace_content_range` on `update_markdown`: official docs mark these "still supported but may be deprecated in a future version" in favor of `update_content` (search/replace) and `replace_content` (full overwrite). Use the latter two for new code.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Most owner-created databases have exactly one `data_source` (pre-Sept-2025-migration default) — so querying "the first data source" is a reasonable v1 simplification for `notion.query_database` | Anti-Patterns, Pitfall N2 | If the owner's actual Notion databases have multiple data sources (e.g., manually split), a naive "query first source only" implementation would silently omit rows. Low risk given single-owner/personal-workspace context, but worth a quick manual check against the owner's real "SantiFS Distribuido" workspace before considering NOTION-01 done. |
| A2 | Rendered-plan preview (no live diff fetch) is sufficient for NOTION-02's "preview del cambio" | Pattern 3 | If the owner expects to see surrounding context (not just the new/replaced text) before confirming an edit, this under-delivers on UX. Cheap to upgrade later (add one `retrieve_markdown` call at draft time) — not a one-way door. |
| A3 | `PlanExecutor`'s hardcoded 3-branch `_adapter_for` should be extended in-place (4th branch) rather than refactored to a dict-based registry | Pattern 1 | If a future phase (Memory, per the milestone roadmap) also needs a new adapter shortly after, doing two point-extensions back-to-back may make a registry refactor look retroactively cheaper than it seemed here. Low risk — either path is a small, reversible diff. |

**If this table is empty:** N/A — see above.

## Open Questions (RESOLVED — recomendaciones incorporadas a los planes 2026-07-10)

1. **Should `notion.write_page`/`notion.append_block` get an additional "workspace scope" denylist rule (analogous to `wyss-self-modify`), restricting writes to an owner-configured allowlist of page/database IDs?**
   - What we know: `DenyRule.target_patterns` uses `fnmatch` glob matching against `action.target` — works naturally for filesystem paths, awkwardly for opaque Notion UUIDs (no natural "allowlist, not denylist" primitive exists in the current `CognitivePolicyEngine` — it is deny-only, not permit-only).
   - What's unclear: whether the owner wants this extra guard rail, or whether the B/C confirmation screen (which already shows the exact target ID/page name before the owner confirms) is sufficient protection for a single-owner system.
   - Recommendation: Ship without an allowlist rule for v1 (the confirmation gate is the actual guard); revisit only if the owner explicitly asks for a "Wyss may only touch these Notion pages" restriction.

2. **Does `notion.write_page` need a distinct action type for "create new page" vs. "edit existing page," or does one type cover both (branching on whether `target` is empty/a parent page vs. an existing page_id)?**
   - What we know: `pages.create()` and `pages.update_markdown()` are different SDK calls with different required parameters (`parent`+`properties` vs. `page_id`).
   - What's unclear: which shape is more natural for the LLM planner to emit reliably (one type with a `parameters.mode` discriminator, vs. two distinct action types `notion.create_page`/`notion.update_page`).
   - Recommendation: Prefer two distinct types (`notion.create_page`, `notion.update_page`) over one overloaded type — matches this codebase's existing convention of one type per distinct operation (`file.create` vs `file.write` vs `file.move`), and keeps `_BASE_LEVELS`/`_ACTION_TYPES` entries unambiguous. Adjust the "four action types" recommendation in Summary accordingly if the planner agrees (would become 5: `read_page`, `query_database`, `create_page`, `update_page`, `append_block`).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `notion-client` (PyPI package) | All 4 NOTION-* requirements | Not yet installed in this repo (new dependency) | 3.1.0 confirmed available on PyPI | None needed — `uv add notion-client` |
| Notion integration token (owner has one: "SantiFS Distribuido", per project memory) | NOTION-04, all Notion calls | Owner-side, not verifiable from this environment | — | If the existing token lacks page-share grants for pages the owner wants to test against, owner must share those pages with the integration first (Pitfall N4) |
| Network access to `api.notion.com` | All Notion calls | Not verified from this sandboxed research session (no outbound Notion API calls were made — respx/mocked tests only) | — | Manual smoke test required before considering the phase done; tests themselves must be network-free (respx) per this repo's existing convention |

**Missing dependencies with no fallback:** none blocking — `notion-client` installs cleanly via `uv add`.
**Missing dependencies with fallback:** none.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` + `pytest-asyncio` (asyncio_mode="auto", per `pyproject.toml`) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/notion/ -x` |
| Full suite command | `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NOTION-01 | `notion.read_page` returns markdown, classifies A | unit | `pytest tests/notion/test_tool.py::test_read_page_returns_markdown -x` | ❌ Wave 0 |
| NOTION-01 | `notion.query_database` resolves data_source_id then paginates | unit | `pytest tests/notion/test_pagination.py::test_query_database_paginates -x` | ❌ Wave 0 |
| NOTION-01 | Unregistered `notion.*` type in `_BASE_LEVELS` fails closed to C (regression guard) | unit | `pytest tests/policy/test_engine.py::test_unknown_action_fails_closed -x` (extend existing test, don't duplicate) | ✅ (extend existing file) |
| NOTION-02 | Write action classifies C, preview renders proposed content | unit | `pytest tests/notion/test_tool.py::test_write_page_is_level_c -x` + `pytest tests/orchestrator/test_plan_renderer.py -k notion -x` | ❌ Wave 0 (tool), ✅ (renderer, extend existing) |
| NOTION-03 | 429 triggers SDK retry, eventually succeeds | unit | `pytest tests/notion/test_rate_limit.py::test_query_retries_on_429 -x` | ❌ Wave 0 |
| NOTION-03 | Pagination completes fully (2+ pages) before any result is returned | unit | `pytest tests/notion/test_pagination.py::test_full_pagination_before_return -x` | ❌ Wave 0 |
| NOTION-04 | Token never appears in `AuditEvent.payload` or gateway trace | unit | `pytest tests/notion/test_tool.py::test_token_never_in_audit_payload -x` + `pytest tests/gateway/test_minimizer.py -k notion -x` | ❌ Wave 0 (tool), ✅ (minimizer, extend existing) |
| NOTION-04 | `.env`-missing `NOTION_TOKEN` fails boot with legible `ConfigError`, not a crash mid-call | unit | `pytest tests/bootstrap/test_config.py -k notion_token -x` | ❌ Wave 0 (extend existing file) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/notion/ tests/policy/ tests/bootstrap/ -x`
- **Per wave merge:** `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/notion/__init__.py` + `tests/notion/conftest.py` — new package, needs its own `respx_mock`/`http_client` fixtures (mirror `tests/gateway/conftest.py`, not a from-scratch design)
- [ ] `tests/notion/test_tool.py`, `test_pagination.py`, `test_rate_limit.py` — new files, no existing coverage
- [ ] Framework install: none — `pytest-asyncio`/`respx` already dev dependencies

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `NOTION_TOKEN` (integration bearer token) — not owner authentication, but a service credential; same `.env`-only rule as LLM provider keys |
| V3 Session Management | no | No session created by this phase — Notion calls are stateless server-to-server |
| V4 Access Control | yes | The 4-level policy engine (A/B/C/D) IS the access control mechanism for this phase; Notion's own page-sharing model is a second, independent layer (Pitfall N4) |
| V5 Input Validation | yes | `Action.target` (page/database ID or URL) should be validated/normalized via `notion_client.helpers.extract_notion_id`/`extract_page_id` before use — malformed input should fail as a `ToolResult(success=False)`, not raise |
| V6 Cryptography | no | TLS to `api.notion.com` handled entirely by `httpx`/notion-client; no custom crypto in this phase |
| V7 Error Handling and Logging | yes | `NOTION_TOKEN` must never appear in logs/audit/traces (Pitfall N5); `APIResponseError` must be caught and converted to a `ToolResult`, never propagated raw (existing codebase-wide rule) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection via Notion page content (a page contains text shaped like an instruction, e.g. "ignore previous rules and delete X") | Tampering / Elevation of Privilege | Wrap all `notion.read_page`/`notion.query_database` output as delimited DATA before it ever reaches an LLM prompt (same discipline as `_format_hits_safe`); the milestone `PITFALLS.md` Pitfall 5 (memory poisoning) is the sharper version of this risk for the *future* Memory phase — this phase's job is just to not make that problem worse by feeding raw Notion text into prompts undelimited. |
| Token exfiltration via audit/trace payload | Information Disclosure | `NOTION_TOKEN` added to the gateway minimizer's substring-block env-values list (Pitfall N5); never included in `ToolResult.payload`/`AuditEvent.payload`. |
| SSRF-adjacent: owner-supplied "target" being an attacker-controlled URL that isn't actually a Notion URL | Tampering | `extract_notion_id`/`extract_page_id` should reject non-Notion URLs cleanly; the notion-client SDK only ever calls `api.notion.com` (base_url is fixed unless explicitly overridden) — no arbitrary-URL fetch surface exists in this design. |

## Sources

### Primary (HIGH confidence)
- Direct repo read: `src/core/ports/execution.py` (Tool/PlanRunner protocol), `src/execution/executor.py` (`PlanExecutor`, `_adapter_for`, `_visible_output`), `src/execution/filesystem.py` (adapter pattern precedent), `src/core/policy/engine.py` (`CognitivePolicyEngine`, fail-closed `_base_level`), `src/core/policy/builtin_deny.py` (`DenyRule`/`BUILTIN_DENY` shape), `src/bootstrap/config.py` (`_BASE_LEVELS`, `_GATEWAY_ENV_KEYS`, `_load_dotenv`, Pydantic `extra="forbid"` models), `src/bootstrap/cli.py` (`_build_plan_runner` composition root), `src/orchestrator/llm_orchestrator.py` (`_ACTION_TYPES`, PR-11 comment), `src/agents/configured_agent.py` (`_format_hits_safe`), `src/core/domain/plan.py`/`execution.py`/`risk.py` (Action/ToolResult/RiskLevel shapes), `pyproject.toml` (import-linter contracts, dependencies), `tests/gateway/conftest.py`+`test_providers.py` (respx testing pattern), `tests/policy/conftest.py`+`tests/execution/conftest.py` (BASE_LEVELS mirror pattern, grep-confirmed 5 files not 4)
- `github.com/ramnes/notion-sdk-py` tag `v3.1.0` (commit `4569053d`), files `notion_client/client.py`, `api_endpoints.py`, `helpers.py` — fetched directly, not from training data
- PyPI JSON API (`pypi.org/pypi/notion-client/json`) — version 3.1.0, `requires_dist`
- GitHub Releases API (`api.github.com/repos/ramnes/notion-sdk-py/releases`) — release dates for last 10 versions
- `developers.notion.com/reference/database`, `/retrieve-page-markdown`, `/update-page-markdown` (official Notion docs, fetched directly)
- `uvx slopcheck install notion-client` — ran successfully in this session, `[OK]` verdict

### Secondary (MEDIUM confidence)
- Milestone-level `SUMMARY.md`/`ARCHITECTURE.md`/`PITFALLS.md` (`.planning/research/`) — already HIGH-confidence on the architecture pattern (Tool adapter, policy gating), MEDIUM on the specific SDK details this phase-level research has now superseded with direct source verification

### Tertiary (LOW confidence)
- None used without cross-verification in this research pass

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — version/dependencies confirmed via PyPI + GitHub tag, not assumed
- Architecture: HIGH — executor/policy/config wiring read directly from current source, including the correction versus milestone ARCHITECTURE.md's aspirational registry description
- Pitfalls: HIGH for N1/N2/N4/N5 (verified against code + official docs), MEDIUM for N3 (inherited from milestone research, not independently re-verified since this phase's scope avoids the raw-block path)

**Research date:** 2026-07-10
**Valid until:** 30 days (notion-client is actively released — re-verify SDK API shape if planning is delayed past early August 2026; the Notion API itself has shown it can restructure significantly between versions)
