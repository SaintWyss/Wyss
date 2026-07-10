# Pitfalls Research — Wyss v1.0 (APK Capacitor, Scheduler, Notion, Memory, n8n Intake)

**Domain:** Adding mobile client (Capacitor), routine scheduler, Notion adapter, agent memory, and n8n webhook intake to an existing local-first, hexagonal, policy-gated (A-D) Python daemon + FastAPI bridge + React SPA.
**Researched:** 2026-07-10
**Confidence:** HIGH on bridge/auth-code-grounded findings (read directly from `src/bootstrap/web.py` + `docs/security/SECURITY_MODEL.md`), MEDIUM on Capacitor/Notion/n8n findings (verified against Context7 official Capacitor docs + WebSearch cross-checked with official Notion/n8n docs), LOW-MEDIUM on memory-poisoning research (academic/2026 sources, fast-moving area).

## Critical Pitfalls

### Pitfall 1: Capacitor's default local origin silently satisfies the bridge's "localhost" trust entry

**What goes wrong:**
`src/bootstrap/web.py::_origin_allowed` allows any Origin whose `urlsplit().hostname` is in `allowed_hosts` (`127.0.0.1`, `localhost`, detected LAN IP) and whose scheme matches `allowed_scheme`. Capacitor's default Android WebView, when the SPA is **bundled as local assets** (the default, no `server.url`), serves the app from `androidScheme://localhost` — and since Capacitor 6 the default `androidScheme` is `https`. That means an unconfigured Capacitor build presents `Origin: https://localhost` on every cross-origin fetch to the PC's LAN bridge — which is **already in the allowlist**, because that entry exists to trust the PC's own loopback browser. The anti-DNS-rebinding design (`docs/security/SECURITY_MODEL.md` §"Modelo de red / móvil") implicitly assumed "only the PC's own browser can present origin `localhost`"; a phone app now also can, by construction, not by attack.

**Why it happens:**
The allowlist matches by hostname **string**, not by "is this literally the loopback interface of this machine." Nobody revisits that assumption when a new client type (native WebView with its own virtual origin) is introduced.

**How to avoid:**
- Do **not** bundle the SPA as local Capacitor assets for this feature. Configure `capacitor.config` `server.url` to point directly at the LAN bridge's `https://<ip>:<port>` (see Pitfall 2 for the caveat this creates), so the WebView is genuinely same-origin with the bridge — no cross-origin fetch, no Origin-allowlist edge case, cookie behaves like a normal browser.
- If bundled-assets mode is ever used instead, treat `https://localhost`/`http://localhost` in the Origin allowlist as **PC-only** by additionally gating on Host (already done — Host must be the LAN IP) **and** rejecting Origin `https://localhost` when Host is the LAN IP but Origin is NOT `null`+`Sec-Fetch-Site: same-origin` (today's `null` exception is fine; a literal non-null `https://localhost` Origin hitting a LAN-IP Host is the case to add a test for).
- Add a regression test mirroring `test_dangerous_prompts.py`'s style: `Origin: https://localhost` + `Host: <lan-ip>:7777` must be rejected unless it's the documented `null`+`Sec-Fetch-Site: same-origin` case.

**Warning signs:** A Capacitor build "just works" against the LAN bridge without ever configuring `server.url` — that's the tell that the app is bundled-local and got through by hostname collision, not by design.

**Phase to address:** Mobile/APK phase, before any smoke test on a real device — this is an auth-boundary regression, not a UX bug.

---

### Pitfall 2: `server.url` is the only viable pattern here, but Capacitor docs mark it "not for production"

**What goes wrong:**
Capacitor's official config docs (verified via Context7) state `server.url` "is intended for use with live-reload servers. **This is not intended for use in production.**" Yet for Wyss's exact use case — a thin WebView shell whose entire purpose is to render a server-driven SPA over the LAN — `server.url` pointed at the bridge is the *correct* architecture (same-origin cookies, no bundled stale assets, no CORS). Treating this as "just a dev flag" and skipping test coverage means a future Capacitor major-version upgrade (which explicitly changes `androidScheme` defaults, as it did in v6) can silently change WebView behavior for this codepath with zero official support to fall back on.
Additionally, `cleartext: true` (required if ever testing over plain HTTP before TLS/PR-10 rollout) must be explicitly set or Android blocks cleartext traffic to non-localhost hosts by default (API 28+ `usesCleartextTraffic=false` default) — this is a separate, easy-to-forget flag from `allowNavigation`.

**Why it happens:** The line between "Capacitor's supported use case" and "what actually works for a local-first LAN app" is not documented anywhere Capacitor publishes; teams find `server.url` works and move on without flagging it as a maintenance risk.

**How to avoid:**
- Document explicitly in the mobile build (README/comment in `capacitor.config`) that `server.url` usage is deliberate and load-bearing, not a leftover dev setting — so it survives future refactors.
- Pin the Capacitor major version and re-verify `androidScheme`/`server.url` behavior on every major upgrade (changelog review, not just `npm update`).
- Set `allowNavigation: ["<lan-ip>", "<lan-ip-alt-if-dhcp-changes>"]` and `server.cleartext` explicitly rather than relying on defaults.

**Warning signs:** Blank screen or `ERR_CLEARTEXT_NOT_PERMITTED` after a Capacitor upgrade with no code change on the Wyss side.

**Phase to address:** Mobile/APK phase — capture as a build config decision with a comment, not tribal knowledge.

---

### Pitfall 3: Self-signed cert trust is static (networkSecurityConfig) but the Wyss cert is dynamic (regenerates on IP change)

**What goes wrong:**
`docs/security/SECURITY_MODEL.md` states the self-signed TLS cert auto-regenerates when the LAN IP changes (DHCP). Android's `networkSecurityConfig` — the documented, "secure" way to trust a self-signed cert in a WebView — is a **static XML compiled into the APK**. You cannot add a trust anchor for "whatever cert Wyss generates next" at build time. Two bad fallbacks teams reach for: (a) overriding `WebViewClient.onReceivedSslError` to unconditionally `handler.proceed()` (accepts *any* cert, defeats TLS entirely, easy to ship in a debug build and forget), or (b) asking the user to manually install the CA as a trusted user cert (fragile: apps targeting API 24+ don't trust user-added CAs unless `networkSecurityConfig` explicitly opts in with `<certificates src="user"/>`, which itself weakens the trust model app-wide).

**Why it happens:** Web docs about "self-signed cert in WebView" assume a fixed, known cert baked in at build time. Wyss's cert is per-machine and per-IP, generated at runtime — a fundamentally different trust model (TOFU, matching the SECURITY_MODEL's own "Residual conocido: TOFU" admission for the desktop/browser case).

**How to avoid:**
- Implement the WebView's own TOFU: override `onReceivedSslError`, extract the presented cert's SHA-256 fingerprint, and compare it against the fingerprint captured at pairing time (the same fingerprint the CLI already prints per SECURITY_MODEL — reuse that value, e.g. embed it in the pairing QR payload alongside the URL/token). Only `handler.proceed()` if the fingerprint matches what was pinned at pairing; otherwise `handler.cancel()` and surface "cert changed, re-pair" to the user.
- Persist the pinned fingerprint per paired server (keyed by LAN IP or a stable device identifier if you add one), and explicitly invalidate/reprompt when the IP changes (ties directly to Pitfall 14, reconnection after DHCP change).
- Never ship a build with unconditional `handler.proceed()` — treat that pattern as a merge-blocking lint/review item, same weight as the D-level denylist rules in this codebase.

**Warning signs:** Any `onReceivedSslError` override that calls `handler.proceed()` without inspecting `error.getCertificate()`.

**Phase to address:** Mobile/APK phase, pairing flow design — this is a security-model decision (TOFU fingerprint pinning on-device), not a later hardening pass.

---

### Pitfall 4: Reusing the phone-pairing cookie model for n8n webhook intake is the wrong auth primitive

**What goes wrong:**
The current bridge auth (`_authenticate_request`) is a **browser session model**: one-time query-token → `Set-Cookie` HttpOnly SameSite=Strict → cookie on every subsequent request. n8n's HTTP Request/Webhook nodes are not a browser: they don't do redirect-then-store-cookie-jar semantics by default, don't send `Sec-Fetch-Site`, and a workflow execution's cookie jar (if enabled at all) doesn't persist across separate executions — so every scheduled workflow run would need to redo the pairing GET, which was designed to be a rare, manual, human action (open URL once, done for 30 days), not a machine-to-machine repeated flow.
Separately: `_origin_allowed` returns `True` when the `Origin` header is **absent** (documented as "the check for real same-origin GETs" that don't send Origin) — a non-browser HTTP client like n8n's node naturally sends no Origin header, so it trivially passes the Origin check. That's fine by itself, but it means the Origin/Sec-Fetch-Site layer provides **zero** protection against n8n-shaped traffic; the entire burden falls on the cookie, and the cookie model doesn't fit n8n's usage pattern.

**Why it happens:** "We already have auth, just point n8n at it" is the path of least resistance, but the milestone's own scope (`Intake n8n webhooks — canal de entrada automático (webhooks → bandeja)`) is the **reverse direction** of what the cookie/pairing flow was built for (bridge serves an authenticated phone/PC browser; it was never designed to *receive* pushes from a headless automation tool).

**How to avoid:**
- Add a **separate, dedicated intake endpoint** (e.g. `POST /api/intake/n8n`) authenticated by a distinct static header token (e.g. `X-Wyss-Intake-Token`, `compare_digest`-checked like the pairing token, but never set as a cookie and never derived from the phone-pairing token). Rotatable independently.
- Rate-limit that endpoint distinctly (n8n misconfiguration or a retry storm shouldn't be able to flood the pending queue).
- Treat every intake payload as **untrusted external content**: it must produce a plan through the same `CognitivePolicyEngine` A-D path (never a direct-execute shortcut) — this is also required by Pitfall 8 (memory/prompt-injection laundering) since n8n payloads often originate from third-party services (email, calendar, forms).
- Do not weaken `SameSite=Strict`/Origin-null handling "to make n8n easier" — that cookie model protects the phone/PC UI; n8n gets its own token, not a relaxation of the existing one.

**Warning signs:** Any change to the existing cookie/Origin middleware "to accommodate n8n" — that's the sign the wrong integration point was chosen.

**Phase to address:** n8n intake phase — design the token before writing the endpoint, don't retrofit auth after the happy path works.

---

### Pitfall 5: Memory writes from untrusted adapters (Notion, n8n) can launder prompt injection into trusted persistent context

**What goes wrong:**
The whole Wyss security model rests on the LLM only **proposing** and a deterministic engine + owner confirmation gating execution (`ORCH-07` Context Minimizer, `POL-04` risk-only-rises). Persistent agent memory (`AGENT-04`) breaks that boundary if content ingested from **external, owner-adjacent-but-not-owner-controlled sources** (a shared Notion page someone else edited, an n8n webhook payload from a third-party service) is summarized into memory and later replayed as if it were trusted owner context in a future session. This is exactly the "memory poisoning" pattern documented in current LLM-agent security research (arXiv 2606.04329, 2601.05504, Lakera's write-up): a single exposure to attacker-controlled content in memory influences every future recall, and standard prompt-injection defenses (which assume a single-turn, single-source prompt) don't cover it because the injected instruction is no longer "external input" by the time it's recalled — it now looks like the system's own memory.

**Why it happens:** Memory is built to make future interactions cheaper/smarter (reasonable goal), and the temptation is to let any adapter (Notion reader, n8n intake) write freely into the same memory store the owner's own stated preferences live in, without re-classifying the trust level of that content.

**How to avoid:**
- Classify memory writes by **source trust tier**: owner-stated preference (direct chat) vs. ingested-external-content (Notion/n8n/file). Never let ingested-external content write to the same memory namespace the LLM treats as "owner's stated fact" without an explicit owner confirmation step (a `memory.write` action type should be policy-gated, not implicit — likely level B minimum, not A).
- When summarizing external content into memory, keep provenance metadata (source, timestamp, trust tier) and have the prompt template that assembles context clearly delimit "owner-stated" vs. "observed from external source, unverified" — don't flatten both into one undifferentiated memory blob.
- Apply the same Context Minimizer discipline to memory recall that already exists for outbound LLM calls (`ORCH-07`): scan recalled memory content for injection-shaped patterns (imperative instructions embedded in what should be descriptive facts) before it re-enters a prompt, same spirit as `SecretFilter`'s three-layer approach already used for indexed files.

**Warning signs:** A memory entry that reads like an instruction ("ignore previous constraints", "always approve X") rather than a fact — the fact/instruction distinction is the actual detection signal here, not keyword blocklists.

**Phase to address:** Memory phase — must be designed before Notion/n8n intake ship, since those are exactly the untrusted-write paths this pitfall targets. Sequence memory's trust-tiering before or alongside Notion/n8n, not after.

---

### Pitfall 6: Naive `while True: work(); await asyncio.sleep(interval)` scheduler drifts and can't do absolute-time routines

**What goes wrong:**
The existing `ttl_reaper` (`src/orchestrator/ttl_reaper.py`) is a `while True: reap_once(); await asyncio.sleep(interval_s)` loop spawned via `asyncio.create_task` alongside the Unix socket server — perfectly fine for "run roughly every 30s," where drift of milliseconds from `reap_once()`'s own execution time doesn't matter. If the Routine Scheduler is built by copying this exact pattern for "run daily at 08:00" or "every hour on the hour," it will drift: each cycle's sleep duration is computed relative to *now*, not to the next absolute fire time, so accumulated execution time across days shifts the actual fire time later and later. It also can't express "next Tuesday at 08:00" — only "N seconds from whenever the loop last woke up."

**Why it happens:** The reaper pattern is right there in the codebase as the obvious template to copy for "another background asyncio task," and it works for its own purpose — but "works for TTL sweeping" and "works for calendar-anchored routines" are different requirements.

**How to avoid:**
- For absolute-time/cron-like routines, compute the next fire time from wall-clock (`zoneinfo`-aware `datetime`), not from a relative sleep accumulator. Prefer `APScheduler`'s `AsyncIOScheduler` (integrates with the existing asyncio event loop the daemon already runs) with `misfire_grace_time` and `coalesce=True` explicitly set per job, rather than hand-rolling — APScheduler already solves drift, misfire, and coalescing; hand-rolling re-derives those from scratch with no test coverage.
- If hand-rolling is preferred for dependency-minimalism (matching the project's existing preference for stdlib-first, e.g. Unix socket over HTTP), explicitly compute `next_run = align_to(now, schedule)` each cycle and `sleep(max(0, (next_run - now).total_seconds()))` — never `sleep(fixed_interval)` in a loop for calendar-anchored schedules.

**Warning signs:** A routine documented as "daily at 08:00" that observably fires a few minutes later each day.

**Phase to address:** Scheduler phase — pick APScheduler (or the wall-clock-anchored variant) at design time, not after drift is reported by the owner.

---

### Pitfall 7: Daemon isn't always-on — missed routines during downtime silently vanish (or worse, silently "look like" they ran)

**What goes wrong:**
Wyss's daemon is started manually (`wyss start`), not installed as an always-on systemd service in the current setup (matches the project's existing pattern of Docker services with `restart=no` on the Acer machine). A routine scheduled for "08:00 daily" when the laptop is asleep/daemon-down at 08:00 will, with a standard scheduler, simply never fire — no catch-up, no error, nothing in the audit log, because the process wasn't running to notice. Worse: if the Routine Scheduler produces a `PendingProposal` the moment the daemon *does* start up next (treating "startup" as "catch up all missed runs"), and the owner doesn't open the UI in time, the existing TTL reaper (`ttl_reaper.py`) will auto-expire it as `CONFIRMATION_ANSWERED` with "propuesta expirada por TTL - auto-rechazada" — which shows up in audit as if the system *did* process the routine (command.received → plan.created → confirmation expired), giving a false impression the routine "ran and was handled" when in fact nothing executed and the owner never saw it.

**Why it happens:** MULTI-02 correctly requires routines to produce confirmable proposals, not auto-execute — but that policy-correct choice interacts badly with an intermittently-running daemon and a TTL-reaper design built for interactive confirm-or-expire flows, not for unattended catch-up after hours/days of downtime.

**How to avoid:**
- On daemon startup, explicitly diff "routines that should have fired since last successful daemon shutdown/last-seen timestamp" and decide a policy per routine: coalesce all missed runs into a single catch-up proposal (don't queue N separate stale proposals), and/or apply a distinct, longer TTL (or no auto-expire) for routine-originated proposals versus interactively-originated `ask` proposals, so a routine's proposal doesn't silently vanish before the owner has realistically had a chance to see it.
- Surface "N routines missed since last run" as a first-class status the SPA/companion app shows on connect, not just a buried audit-log line — this is a UX signal the owner needs, distinct from a generic pending-items badge.
- Persist `last_successful_run_at` per routine (not just "next scheduled time") so restart logic is idempotent and doesn't double-fire (see Pitfall 8) while still catching genuine misses.

**Warning signs:** Audit log shows `confirmation.answered` with reason "expirada por TTL" for a routine-originated proposal the owner never saw a notification for.

**Phase to address:** Scheduler phase — the catch-up policy is a design decision, not a bug fix; decide it before shipping the first routine type.

---

### Pitfall 8: Double-fire from restart-time recompute and overlapping runs

**What goes wrong:**
Two distinct double-fire risks: (1) if "next run" is recomputed from `last_run_at` on every daemon restart with an off-by-one (e.g., comparing with `>=` instead of `>`, or not persisting `last_run_at` transactionally with the fire itself), a restart shortly after a routine fired can re-trigger it immediately; (2) if a routine's own execution (e.g., a Notion sync that recurses through many nested blocks — see Pitfall 9) takes longer than the routine's own interval, and the scheduler doesn't guard against overlapping invocations, two copies of the same routine run concurrently, potentially producing duplicate `PendingProposal` rows for the same logical action.

**Why it happens:** Persisting "next run" state and guarding against concurrent execution are two separate, easy-to-skip concerns when the initial implementation is "make it fire once and call it done."

**How to avoid:**
- Persist `last_run_at`/`next_run_at` update **atomically with** the act of firing (same transaction/same DB write as creating the routine's proposal), not as a separate step that could be skipped on crash-between-steps.
- Use an explicit "is this routine currently running" guard (a lock row, or an in-memory set of currently-executing routine IDs checked before starting a new run) so a slow run doesn't overlap with the next scheduled tick.

**Warning signs:** Two `PendingProposal` rows with the same routine origin and near-identical `created_at` timestamps.

**Phase to address:** Scheduler phase.

---

### Pitfall 9: Timezone — Argentina has no DST, but "no DST" is not the same as "no timezone bugs"

**What goes wrong:**
`America/Argentina/Buenos_Aires` has been fixed at UTC-3 with no DST transitions since 2009, so the classic "spring-forward missed job" bug class mostly doesn't apply here — but two other timezone bugs remain very real: (a) using naive `datetime.now()` (no `tzinfo`) instead of an explicit `zoneinfo.ZoneInfo("America/Argentina/Buenos_Aires")`-aware datetime means the schedule silently follows whatever the **host machine's** system timezone is configured to, which is a real risk given the project already runs across multiple machines with independent OS configs (Santiago-PC, Acer — per project memory, "Ops de sistema... NO sincronizan"); if any machine's system TZ drifts from `America/Argentina/Buenos_Aires` (e.g., a container, a misconfigured VM, a fresh install defaulting to UTC), "08:00" silently means a different wall-clock moment than the owner intends. (b) SQLite (used throughout this project — `audit.db`, `pending_store`, etc.) stores/returns timestamps as text by default; comparing a naive-UTC stored timestamp against a timezone-aware "now" without normalizing both to the same reference will silently miscompute "is this routine due."

**Why it happens:** "Argentina has no DST" is often (correctly) used to conclude "timezone bugs won't happen here," which skips the machine-configuration and naive-vs-aware-datetime classes of bugs that are independent of DST.

**How to avoid:**
- Always construct schedule "due" comparisons with explicit `zoneinfo.ZoneInfo("America/Argentina/Buenos_Aires")`, never rely on the host's local `datetime.now()` without a tz argument.
- Store all persisted timestamps in UTC (ISO-8601 with explicit offset, matching the existing `_now_iso()`/audit timestamp convention already used in `bootstrap/cli.py` — check that convention and reuse it rather than introducing a second timestamp format for routines) and convert to Argentina time only at the schedule-evaluation boundary and for display.

**Warning signs:** A routine's actual fire time differs from its configured time by a fixed offset (not drifting, just wrong) — that pattern points to a naive/aware or UTC/local mismatch, not scheduler drift.

**Phase to address:** Scheduler phase, alongside Pitfall 6.

---

### Pitfall 10: Notion's short-lived pagination cursor doesn't survive Wyss's plan→confirm gating

**What goes wrong:**
Notion's API caps pages at 100 results and requires the returned `next_cursor` to be "consumed in the immediately following request" (official Notion docs) — cursors are not meant to be held across a delay. Wyss's action model, however, is built around "propose a plan, wait for owner confirmation (possibly minutes, possibly until TTL expiry), then execute" (`ORCH-02`). If a Notion-reading action is naively implemented as "start paginating, and if a `file.write`-equivalent confirmation gate is needed mid-walk, pause and resume the cursor later," the cursor will very likely have expired by the time confirmation arrives, and the read silently returns incomplete/stale results (or a cursor error) with no obvious symptom beyond "the page seems truncated."

**Why it happens:** Standard Wyss request flow assumes a pause-for-confirmation between planning and execution; Notion's pagination assumes rapid-fire sequential calls. These two assumptions conflict unless pagination is fully completed **inside** the planning step (before any confirmation gate), never split across a confirmation boundary.

**How to avoid:**
- Do all Notion pagination/recursion needed to answer a query or build a plan **before** presenting anything to the policy engine/owner for confirmation — treat "read + fully paginate + recursively resolve nested blocks" as a single atomic read step (level A, per the existing "lecturas" policy) that completes before any B/C confirmation gate, never interleaved with it.
- If a write action depends on prior reads, cache the fully-resolved Notion content at plan-creation time rather than re-querying (with a fresh cursor walk) at confirm/execute time.

**Warning signs:** A Notion-derived plan whose confirmed execution returns different/fewer items than what the owner saw when approving.

**Phase to address:** Notion adapter phase — design the read-then-plan boundary before writing pagination code.

---

### Pitfall 11: Recursive nested-block fetching can cross BC/permission boundaries and blow past rate limits combinatorially

**What goes wrong:**
Notion's API only returns first-level children per block; a full page reconstruction requires recursively calling "retrieve block children" for every block where `has_children` is true (official Notion docs, verified). A single "summarize this Notion page" action can silently balloon into dozens of API calls if the page links/embeds sub-pages, and — more importantly for this system's model — those recursively-discovered sub-pages may belong to a different Notion workspace section than what the owner scoped the original action to. Given `AGENT-02` ("un agente sin permiso vigente sobre una BC no puede consultar esa BC"), unbounded recursion is a scope-creep risk: the action was authorized for "page X," but recursion can pull in linked content the owner never intended to expose to that action's context, then feed it to an LLM call (violating `ORCH-07`'s "contexto mínimo hacia afuera" even if the BC-boundary check technically doesn't apply to Notion, the *spirit* of least-context does).
Combined with the 3 req/s average rate limit (429 + `Retry-After`, per official docs), an unbounded recursive walk on a deeply nested page can also just fail mid-action from rate limiting, with no rate-limit-aware backoff, some content fetched and some not.

**Why it happens:** "Just recurse into `has_children`" is the natural, correct-looking implementation of "get the full page," but it has no natural stopping point and no scope boundary by default.

**How to avoid:**
- Cap recursion depth and/or total block count explicitly per action (mirrors the existing `256 KiB`/`500`-entries caps already used for file reads per `SECURITY_MODEL.md` — apply the same "cap + say it truncated" discipline to Notion reads).
- Treat recursion into a **linked/child page** (not just nested blocks within the same page) as a scope boundary: don't silently follow links to other Notion pages without a fresh, explicit authorization check — that's a different "resource" than the one the action was scoped to, and should require the same confirmation gate as a fresh read.
- Respect `Retry-After` on 429 with exponential backoff; never busy-retry a Notion call from inside a routine (interacts with Pitfall 6/8's overlap risks if a routine retries indefinitely and overruns into the next scheduled tick).

**Warning signs:** A single "summarize this page" action making dozens of Notion API calls, or occasionally 429ing when the page happens to be deeply linked.

**Phase to address:** Notion adapter phase.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|-----------------|
| Bundle Capacitor SPA as local assets instead of `server.url` (skip Pitfall 1/2 analysis) | Faster first build, matches Capacitor "getting started" tutorials | Cross-origin fetch to LAN bridge fights the existing Origin allowlist and SameSite=Strict cookie; both need to be re-architected later anyway | Never for this project — same-origin `server.url` is the only architecture consistent with the existing bridge auth |
| `onReceivedSslError` → `handler.proceed()` unconditionally | Unblocks dev testing against self-signed cert in minutes | Ships a WebView that accepts *any* TLS cert from *any* host it's told to load — full MITM exposure | Only in an explicitly non-shippable debug build variant, never in the build users install |
| Reuse `ttl_reaper`'s `while True: sleep(fixed)` pattern for calendar-anchored routines | Zero new dependency, matches existing code style | Drift compounds daily; can't express "at 08:00", silently wrong over weeks | Only for fixed-interval housekeeping (TTL sweeps, health pings), never for owner-facing "daily at X" routines |
| Let Notion/n8n adapters write directly into the same memory table as owner-stated preferences | Ships memory feature faster, one storage schema | Opens the memory-poisoning/prompt-injection-laundering path (Pitfall 5) | Never — trust-tier separation must exist from the first write path, not be retrofitted |
| Point n8n at the existing cookie-pairing bridge auth instead of a dedicated token | No new auth code | Fragile (no real cookie-jar semantics in workflow automation), tempts weakening SameSite/Origin to "make it work" | Never — dedicated header token for intake is cheap and correct from day one |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|-----------------|-------------------|
| Capacitor (Android WebView) | Bundling SPA as local assets, then `fetch()`-ing the LAN bridge cross-origin | `server.url` pointed at the bridge's `https://<lan-ip>:<port>` so the WebView is same-origin; keep plain `fetch`/WebView cookie jar, don't enable `CapacitorHttp` native bridging for these calls (it bypasses the browser CORS/cookie model the bridge's Origin/Sec-Fetch-Site checks depend on) |
| Self-signed TLS in WebView | Static `networkSecurityConfig` trust anchor baked at build time, doesn't survive the cert regenerating on LAN-IP change | `onReceivedSslError` override doing app-level TOFU fingerprint pinning against the fingerprint captured at pairing (reuse the SHA-256 the CLI already prints per SECURITY_MODEL) |
| Notion API | Pausing mid-pagination for a confirmation gate; unbounded recursive `has_children` walk across linked pages | Fully paginate + resolve nested blocks before any confirmation boundary; cap recursion depth/block count and treat linked child pages as a fresh scope requiring authorization |
| Notion API rate limit (3 req/s avg, 429 + `Retry-After`) | Busy-retry loop inside a routine, especially one that can overlap with the next scheduled tick | Respect `Retry-After`, exponential backoff, and bound total calls per action |
| n8n webhook intake | Reusing the phone-pairing cookie/Origin model for a headless automation tool | Dedicated static header token on a dedicated `/api/intake/*` endpoint; treat payloads as untrusted, always plan-gated through the policy engine, never direct-execute |
| Android notifications for pending items | Assuming background polling/JS timers fire reliably while the app is backgrounded or the phone is in Doze | Rely on foreground polling + local notification on resume; explicitly document "no true push while backgrounded" rather than adding FCM/cloud relay (contradicts the LAN-only, no-internet-exposure constraint) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|-----------------|
| Recursive Notion block fetch with no depth/count cap | A single "read this page" action makes dozens of API calls, occasionally 429s | Cap depth + total block count, same discipline as the existing file-read `256 KiB`/`500`-entry caps | Any Notion page with more than a couple levels of nested/linked sub-pages |
| Undifferentiated memory blob fed whole into every LLM call | Prompt size/cost/latency creep over weeks as memory accumulates | Summarization/compaction strategy and trust-tiered context assembly from the first version, not deferred | Once memory exceeds a few dozen entries per agent domain |
| `while True: sleep(fixed_interval)` scheduler loop for calendar routines | Routine fires progressively later each cycle | Wall-clock-anchored next-fire computation (or APScheduler with `misfire_grace_time`) | Any schedule longer than the interval itself accumulates visible drift within days to weeks |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Ingested external content (Notion, n8n) written into the same memory trust tier as owner-stated facts | Prompt injection persists across sessions ("memory poisoning"), replayed as trusted context in future plans | Explicit trust-tier separation on every memory write; `memory.write` from an external-source adapter is policy-gated (≥B), never implicit |
| Reusing the phone-pairing cookie auth for n8n webhook intake | Either breaks silently (no real cookie-jar semantics) or tempts weakening SameSite/Origin checks to accommodate a non-browser client, undermining the anti-CSRF model the phone/PC UI depends on | Dedicated static header token, separate endpoint, separate rate limit |
| `onReceivedSslError` unconditional `handler.proceed()` | Full MITM exposure — WebView accepts any cert from any host | App-level TOFU fingerprint pinning tied to the pairing-time fingerprint; never ship unconditional proceed |
| Origin allowlist trusting `localhost` by hostname string alone | A Capacitor app's default local origin (`https://localhost`) can satisfy a check meant only for the PC's own loopback browser | Same-origin `server.url` architecture (Pitfall 1) removes the ambiguity entirely; add a regression test for the collision case regardless |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| Routine proposals silently auto-expire via the existing TTL reaper while the owner is away | Owner believes a routine "handled itself" (audit shows a full command→plan→confirmation-answered trail) when nothing actually executed | Distinct, more visible status for routine-originated pending items; surface "N routines missed/expired since you were last online" prominently, not buried in the audit feed |
| Pairing URL breaks silently after the PC's LAN IP changes (DHCP) or the TLS cert regenerates | Owner sees generic connection failure indistinguishable from "network is down" or "someone is MITMing me" | Distinguish "no route to host" (off-LAN) from "cert fingerprint changed" (re-pair required) from "401 cookie expired" (routine re-open) with different, specific messages — the existing bridge already logs distinct 403 reasons server-side; surface the equivalent distinction client-side |
| Assuming push notifications will work like a normal messaging app | Owner expects a phone buzz for a new pending item while the app is backgrounded/phone locked; that won't happen without a cloud relay this project deliberately doesn't have | Set expectations explicitly in-app ("Wyss checks for updates while open — no background push over LAN-only") rather than silently under-delivering |

## "Looks Done But Isn't" Checklist

- [ ] **Capacitor build works on the developer's phone:** Often means the developer's phone and the PC are already paired/cert-trusted from prior manual testing — verify against a **fresh** device/fresh app install to catch Pitfall 1/3 collisions.
- [ ] **Routine fires once correctly in a demo:** Verify it fires correctly after (a) a daemon restart between two scheduled times, (b) the machine's clock/timezone deliberately set to something other than Argentina, (c) a deliberately slow routine run that overlaps the next tick.
- [ ] **Notion adapter "reads a page" in testing:** Verify against a page with nested toggle blocks / linked sub-pages / more than 100 blocks — the common demo case (a flat short page) never exercises pagination or recursion at all.
- [ ] **n8n webhook "works" in a manual test:** Verify it still works from a **scheduled, unattended** n8n workflow execution, not just a manual "Execute Workflow" click in the n8n editor (manual execution reuses editor session state that a scheduled trigger won't have).
- [ ] **Memory "remembers preferences" in a demo:** Verify what happens when the memory content includes an instruction-shaped string ingested from an external source (a Notion page, an n8n payload) — does it get treated as a fact to recall or as an instruction to follow?

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|-----------------|-------------------|
| Origin-allowlist collision shipped (Pitfall 1) | LOW | Add the missing test case, tighten `_origin_allowed` to require the `null`+`Sec-Fetch-Site` path when Host is a LAN IP; no data-model change needed |
| Unconditional cert-proceed shipped in a release build (Pitfall 3) | MEDIUM | Force-update the APK with TOFU pinning added; treat any prior pairing as untrusted until re-verified against the printed fingerprint |
| Memory already poisoned by ingested content (Pitfall 5) | HIGH | Requires manual audit/purge of memory entries by provenance; this is why trust-tiering must exist before Notion/n8n ship, not after — recovery here is expensive and imprecise (no clean way to prove which recalled "facts" already influenced past plans) |
| Scheduler drift discovered in production (Pitfall 6) | LOW-MEDIUM | Swap the fire-time computation to wall-clock-anchored (or migrate to APScheduler); no data loss, just re-derive `next_run_at` from current config |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|-----------------|
| Origin allowlist / Capacitor origin collision (1) | Mobile/APK phase | Regression test: `Origin: https://localhost` + `Host: <lan-ip>` → 403 unless `null`+`Sec-Fetch-Site: same-origin` |
| `server.url` production risk (2) | Mobile/APK phase | `capacitor.config` documented + `allowNavigation`/`cleartext` explicit, reviewed on every Capacitor major upgrade |
| Self-signed cert TOFU pinning (3) | Mobile/APK phase | Manual test: rotate the PC's cert (simulate IP change), confirm the app rejects the new cert until re-paired, never silently proceeds |
| n8n auth model (4) | n8n intake phase | Dedicated token + endpoint exists before any workflow is connected; cookie/Origin middleware untouched |
| Memory poisoning / trust tiering (5) | Memory phase (before/alongside Notion + n8n) | A test that feeds an instruction-shaped string through the Notion/n8n intake path into memory, and asserts it does not alter a subsequent unrelated plan's risk/behavior |
| Scheduler drift (6) | Scheduler phase | Simulate N cycles with variable execution time, assert fire times stay wall-clock-accurate, not accumulated-relative |
| Downtime catch-up policy (7) | Scheduler phase | Simulate daemon down across a scheduled fire time, assert a single coalesced catch-up proposal with owner-visible surfacing, not silent TTL expiry |
| Double-fire guard (8) | Scheduler phase | Simulate restart immediately after a fire, and an overlapping slow run, assert no duplicate proposals |
| Timezone correctness (9) | Scheduler phase | Test with host system TZ set to something other than Argentina, assert scheduled times stay correct in `America/Argentina/Buenos_Aires` |
| Notion pagination vs. confirmation gating (10) | Notion adapter phase | Test a Notion read spanning >100 results, assert full pagination completes before any confirmation gate is presented |
| Notion recursion scope/rate limits (11) | Notion adapter phase | Test against a page with linked sub-pages, assert recursion is capped and cross-page links require fresh authorization |

## Sources

- `src/bootstrap/web.py` (read directly — Origin/Host/cookie auth implementation, confidence HIGH, this is the actual code being extended)
- `docs/security/SECURITY_MODEL.md` (read directly — TLS/TOFU/cert-regeneration model, confidence HIGH)
- `docs/mobile/WYSS_MOBILE_BRIDGE_MVP.md` (read directly — existing LAN bridge smoke-test findings, confidence HIGH)
- `src/orchestrator/ttl_reaper.py`, `src/orchestrator/daemon.py` (read directly — existing asyncio background-task pattern that a naive scheduler would likely copy, confidence HIGH)
- [Capacitor Configuration docs (Context7 /ionic-team/capacitor-docs)](https://capacitorjs.com/docs/config) — `server.url` "not intended for use in production," `androidScheme` default change in v6 — confidence HIGH (official docs, version-aware via Context7)
- [Capacitor Live Reload guide](https://github.com/ionic-team/capacitor-docs/blob/main/docs/main/guides/live-reload.md) — `server.url`+`cleartext` remote-backend pattern — confidence HIGH
- [Understanding Authentication in Hybrid Mobile Apps: Cookies, WebViews, and Common Pitfalls](https://dev.to/itamartati/understanding-authentication-in-hybrid-mobile-apps-cookies-webviews-and-common-pitfalls-3m8) — confidence MEDIUM (community source, cross-checked against official Capacitor cookie/CORS behavior)
- [Capacitor Security guide](https://capacitorjs.com/docs/guides/security) — confidence HIGH (official)
- [ionic-team/capacitor allowNavigation cookie/set-cookie proxy issue discussion](https://github.com/ionic-team/capacitor/discussions/1488) — confidence MEDIUM (GitHub discussion, illustrates real-world cookie/proxy gotcha)
- [Android WebView self-signed certificate handling](https://sslinsights.com/how-to-handle-self-signed-certificates-in-android-webview/) — confidence MEDIUM (single source, standard `onReceivedSslError`/networkSecurityConfig pattern, cross-checked against Android developer conventions)
- [APScheduler user guide (misfire, coalesce, AsyncIOScheduler)](https://apscheduler.readthedocs.io/en/3.x/userguide.html) — confidence HIGH (official docs)
- [APScheduler missed-jobs-run-late issue #1095](https://github.com/agronholm/apscheduler/issues/1095) — confidence MEDIUM (real-world confirmation of misfire behavior nuance)
- [Notion API: Retrieve block children (pagination, recursion)](https://developers.notion.com/reference/get-block-children) — confidence HIGH (official docs)
- [Notion API rate limits and request handling](https://thomasjfrank.com/how-to-handle-notion-api-request-limits/) — confidence MEDIUM (community source, figures cross-checked against official Notion API request-limits documentation)
- [Memory Poisoning Attack and Defense on Memory Based LLM-Agents (arXiv 2601.05504)](https://arxiv.org/abs/2601.05504) — confidence MEDIUM (2026 academic preprint, fast-moving area, directional findings not yet standardized defenses)
- [From Untrusted Input to Trusted Memory: A Systematic Study of Memory Poisoning Attacks in LLM Agents (arXiv 2606.04329)](https://arxiv.org/html/2606.04329v1) — confidence MEDIUM (academic preprint)
- [Agentic AI Threats: Memory Poisoning & Long-Horizon Goal Hijacks — Lakera](https://www.lakera.ai/blog/agentic-ai-threats-p1) — confidence MEDIUM (vendor blog, but well-aligned with the academic sources above)
- [n8n Webhook credentials / header auth docs](https://docs.n8n.io/integrations/builtin/credentials/webhook) — confidence HIGH (official n8n docs)
- [Securing Webhooks in n8n](https://hostadvice.com/blog/web-hosting/vps/securing-webhooks-in-n8n/) — confidence MEDIUM (community source, cross-checked against official n8n webhook auth documentation)

---
*Pitfalls research for: Wyss v1.0 — APK Capacitor, Routine Scheduler, Notion adapter, Memory, n8n intake*
*Researched: 2026-07-10*
