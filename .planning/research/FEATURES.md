# Feature Research

**Domain:** Personal operational AI agent — local-first assistant with human-gated execution (routine scheduling, proactive briefing, persistent memory, Notion adapter, mobile companion app)
**Researched:** 2026-07-10
**Confidence:** MEDIUM (patterns cross-verified across multiple 2025-2026 products; no single source is Wyss-specific since local-first + human-gate combo is uncommon in mainstream products)

## Scope Note

This research covers only the **five NEW feature areas** of the v1.0 milestone: Routine Scheduler, Notion adapter, Daily Assistant, Memory, and the Android companion app (pairing/reconnection/notifications). Existing infrastructure (bandeja B/C, CONFIRMAR gate, política A-D, daemon Unix socket + JSON-RPC, ledger Pellegrini, búsqueda híbrida) is treated as a given foundation these features build on — not re-researched. Web desktop polish is UI work, not covered here (belongs in a design pass, not ecosystem research).

**Inviolable product rule carried into every section below:** nothing classified B/C auto-executes. The scheduler, Notion adapter, Daily Assistant, and n8n intake channel all *propose* — the owner's bandeja + CONFIRMAR gate is the only path to execution. This is not a feature to build; it's a constraint every new feature must respect by construction (route everything B/C through the existing `CognitivePolicyEngine` + confirmation queue, never a parallel approval path).

## Feature Landscape

### Table Stakes (Users Expect These)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Scheduler shows next-run time and last-run result per routine | Users of any scheduler (cron UIs, Home Assistant automations, Claude Code scheduled tasks) expect visibility into "when does this fire next" and "did it work last time" | LOW | Store `next_run`, `last_run_at`, `last_run_status` per routine row; surface in bandeja/routine list UI |
| Natural-language routine creation ("todos los lunes a las 9am revisá X") converted to explicit, inspectable schedule | 2026 baseline set by Claude Cowork, Hermes Agent, ChatGPT scheduled tasks — all convert NL to cron/RRule and show the owner the resolved schedule before saving, never silently | MEDIUM | LLM parses NL → cron/RRule; **must show resolved expression + human-readable preview for owner confirmation before the routine is saved**, not just before each run |
| Routine run produces a bandeja item for any B/C step, exactly like a manual request | Owner already trusts the bandeja for ad-hoc actions; a scheduler that bypasses it would be inconsistent and is explicitly disallowed by MULTI-02 | LOW (if bandeja abstraction is already generic) | Scheduler is just another *caller* of the same `OrchestratorPort` — reuse plan generation + policy gate, don't build a second one |
| Daily briefing arrives at a predictable time with a fixed, scannable structure (not free-form prose) | ChatGPT Pulse, Gemini Daily Brief, and Claude Cowork's morning briefing all use structured cards/sections (agenda, money, pending items) rather than a wall of text — users scan, they don't read | MEDIUM | Fixed sections: agenda del día, snapshot financiero (Pellegrini), bandeja pendiente, alertas de rutinas fallidas |
| Memory the owner can see and edit in plain text, not a black box | Anthropic's 2026 Claude Memory (human-readable markdown, click-to-edit/delete) is now the credibility bar; OpenAI/Google's opaque vector memory draws consistent criticism for being unauditable | MEDIUM | Reuse the existing per-agent `MEMORY.md` pattern (AGENT-04) — already textual, already versionable in git, already fits Wyss's audit-everything philosophy |
| Deleting a memory item actually removes its influence, not just hides it from the UI | Claude's "delete conversation removes derived memory points" set the expectation that edit/delete is real, not cosmetic | LOW-MEDIUM | Since memory = flat file read into context, deletion is trivially real — advantage over vector-store competitors, worth calling out as a Wyss strength |
| Mobile app auto-discovers the LAN server on the same network without manual IP entry | Home Assistant Companion's "search for servers on this network, auto-offer to connect" is the 2025-2026 baseline; manual IP-only pairing feels dated | MEDIUM | On first launch, attempt local discovery (mDNS/broadcast or QR-provided endpoint) before falling back to manual entry |
| Push/local notification when something lands in the bandeja | A companion app that requires opening it to discover pending confirmations defeats the purpose of "mobile companion" | MEDIUM-HIGH | LAN-only server (no cloud push relay by default) means true push (FCM) needs either a cloud relay or reliance on local notification when app is foregrounded/polling — flag as an open design question, see Pitfalls research |
| Reconnection after Wi-Fi drop / app backgrounding is automatic, not a manual "reconnect" button | Any LAN client users compare this to (Home Assistant, Jellyfin, Plex, Sonos apps) auto-retries on network change; manual reconnect is a known complaint pattern for weaker apps | MEDIUM | WebView/Capacitor bridge needs connection-state detection + auto-retry with backoff against the daemon's Unix-socket-backed HTTP/WS bridge |
| Notion write actions show a diff/preview before writing (what block/page will change) | Every mature Notion integration (n8n Notion nodes, Truto-style sync engines) treats Notion writes as risky because Notion has no native undo API — the *product* must build the preview, since Notion itself won't | MEDIUM | This maps directly onto Wyss's plan-then-confirm flow already required for B/C actions — Notion write = classify B/C, generate plan (page/property diff), require CONFIRMAR |

### Differentiators (Competitive Advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Scheduler proposals carry full plan + audit trail identical to manual actions | Nobody in the human-in-the-loop scheduler space (n8n HITL, gotoHuman, Claude Cowork) unifies scheduled and manual approval into the *same* audited pipeline — most bolt approval on as a separate "wait for webhook" node with its own state | MEDIUM | Reuses ORCH-02 (explicit plan) + AUDIT-01 (total audit) for free if scheduler is built as an `OrchestratorPort` caller, not a parallel system — this is Wyss's structural advantage from the hexagonal architecture |
| Daily Assistant references the owner's own indexed knowledge base and finance ledger, not external news/calendar APIs | Pulse/Gemini Daily Brief personalize with Gmail/Calendar; Wyss's differentiator is the 2TB personal knowledge base + Pellegrini ledger already indexed — briefing quality tied to something competitors don't have (a fully local, already-searched personal corpus) | MEDIUM | Briefing composer queries hybrid search + Pellegrini agent, not a new data source — mostly orchestration, not new indexing |
| Memory is per-agent-scoped (Belgrano ≠ Pellegrini ≠ Personal), not one global blob | ChatGPT/Claude/Gemini memory is one global profile per user; Wyss's multi-agent architecture (AGENT-02 scoped facades) naturally supports separating "what Belgrano knows about my study habits" from "what Pellegrini knows about my spending" — reduces context pollution and respects the existing permission boundaries | MEDIUM-HIGH | Requires the orchestrator to route only the relevant agent's MEMORY.md into that agent's context, never all of them — this is an architecture decision, not just a feature |
| Notion adapter enforces the same A-D policy as file/shell actions (reads = A, page edits = B/C by content sensitivity, deletes = D-adjacent) | Most Notion integrations (n8n, Zapier, native API) have no concept of graduated risk — a page edit and a page delete are equally "just an API call." Wyss's cognitive policy applied to Notion is a genuine differentiator matching the project's "humano primero" philosophy | MEDIUM | Classify Notion actions through existing `CognitivePolicyEngine`; likely need new deny-rules for irreversible Notion ops (page deletion, workspace-level changes) |
| QR pairing that also transfers the daemon's self-signed cert fingerprint (not just IP:port) | Most self-hosted LAN apps (Jellyfin, Home Assistant) solve HTTPS-on-LAN with "just accept the warning" or full CA setup; encoding a cert pin in the QR payload lets the WebView auto-trust *only* that specific server without weakening security globally | MEDIUM-HIGH | Genuine UX+security differentiator versus "tap through the scary SSL warning" pattern most local-first apps still ship with in 2026 |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Auto-approve scheduler routines below a $ threshold or after N successful runs ("it's proven itself, stop asking") | Feels like natural evolution of trust, seen in some AI agent scheduler blogs recommending "approval checkpoints only above a threshold" | Directly violates MULTI-02 and the project's core "humano primero" rule — a habituated owner clicking CONFIRMAR without reading is a known failure mode of approval fatigue, but the fix is better UI/batching, not silent auto-execution | Batch same-routine repeated proposals into one bandeja card with clear diff-from-last-time, not auto-execution |
| Remote (outside-LAN) access to the mobile companion via port-forward or embedded VPN | Users of Jellyfin/Home Assistant expect "access my server from anywhere" as standard; feels like an obvious next step for the APK | v1.0 scope is explicitly LAN pairing with a self-signed cert managed by the app itself; remote access reintroduces the exact attack surface (exposed daemon, cert trust across networks) the project's security model isn't designed for yet, and Tailscale/VPN integration is a scoped-out future item, not v1.0 | Ship LAN-only in v1.0; document Tailscale/WireGuard as a manual, owner-configured escape hatch outside the app, not a built-in feature |
| Fully autonomous nightly research/web-browsing for the Daily Assistant (ChatGPT Pulse style "does research across the internet overnight") | Pulse's headline feature is proactive internet research; tempting to copy directly | Wyss's context-minimization principle (ORCH-07) and API-first/no-heavy-local-model constraint make unbounded autonomous web research expensive, hard to audit, and off-brand for a project whose value prop is *your own data*, not internet aggregation | Daily Assistant summarizes what's already inside Wyss's boundary (agenda, ledger, bandeja, indexed KB) — if external content is wanted later, it's a scoped, policy-gated fetch (A-level read), never open-ended autonomous browsing |
| One global memory blob shared across all agents, "so nothing is ever missed" | Simpler to implement than per-agent scoping; matches how ChatGPT/Claude structure memory today (single profile) | Breaks AGENT-02's scoped-facade guarantee — an agent without permission on a BC could still "know" things about it via shared memory, defeating the permission model | Per-agent MEMORY.md, explicitly routed by the orchestrator only to agents with legitimate access to that context |
| Two-way real-time Notion sync (edit in Notion, instantly reflected in Wyss, and vice versa) | "Bidirectional sync" sounds like the obvious end state and is often the first ask for any Notion integration | As of 2026, even mature Notion sync tooling (n8n, Truto-style connectors) still implements this as two separate one-directional flows with reconciliation, not true real-time bidirectional sync — Notion's API has no native "writeback" primitive and rate limits (3 req/s per integration) make aggressive polling for live sync expensive and brittle | Wyss reads Notion (with caching + periodic reconciliation) and writes Notion only via explicit, owner-confirmed actions (a proposal in the bandeja) — no live two-way loop, no polling-driven auto-writes |
| Push notifications delivered via a third-party cloud relay (Firebase Cloud Messaging) by default | It's the only well-documented Capacitor push path (Push Notifications plugin is FCM-based) and the "complete" tutorials all assume it | Routing bandeja notifications through Google's FCM means owner data (that something needs confirmation, potentially with a preview) transits a third party — inconsistent with local-first / owner-controlled philosophy | Default to local notifications while app is foregrounded/backgrounded-but-alive + WebSocket/long-poll to the daemon over LAN; treat FCM as an optional, explicitly opted-in future path for true background push when off-LAN (flagged as open question, not v1.0 default) |

## Feature Dependencies

```
Routine Scheduler
    └──requires──> Existing bandeja/CONFIRMAR gate + CognitivePolicyEngine (already built)
    └──requires──> Persistent job store (next_run/last_run) — new, small addition to daemon

Notion Adapter
    └──requires──> CognitivePolicyEngine classification rules extended for Notion actions (new deny-rules for destructive ops)
    └──requires──> Read path (Notion → cache) built before write path (cache → confirmed write)

Daily Assistant
    └──requires──> Routine Scheduler (it IS a scheduled routine — daily trigger)
    └──requires──> Hybrid search (existing) + Pellegrini ledger (existing) as data sources
    └──enhances──> Memory (uses memory to personalize what's surfaced)

Memory
    └──requires──> Per-agent scoping already present in architecture (AGENT-02 facades) — reuse, don't rebuild
    └──enhances──> Daily Assistant, Notion Adapter, Scheduler (all read memory for personalization/context)

Intake n8n (webhooks → bandeja)
    └──requires──> Bandeja abstraction accepts external-origin proposals, not just LLM-planner-origin ones
    └──conflicts (partially)──> naive auto-execution assumptions common in n8n HITL tutorials (must be re-gated through Wyss's own policy engine, not n8n's approval nodes)

Mobile Companion App (APK)
    └──requires──> Daemon exposes an HTTP/WS bridge reachable from LAN (already exists per v0.1.0 bridge)
    └──requires──> QR pairing flow (new) — encodes endpoint + cert fingerprint
    └──enhances──> Routine Scheduler, Daily Assistant, Notion Adapter, Intake n8n (all become more useful once notifications reach the phone)
```

### Dependency Notes

- **Daily Assistant requires Routine Scheduler:** the briefing is conceptually "a routine that runs once a day and composes a summary instead of proposing a single action." Building the scheduler generically enough to support both use cases avoids two parallel systems.
- **Memory enhances almost everything:** treat it as infrastructure, not a standalone feature — build it early enough that Notion adapter, Scheduler, and Daily Assistant can consume it, but it doesn't block any of them (they work with empty memory too).
- **Mobile Companion App conflicts with rushing remote-access scope:** LAN-only pairing is simpler and safer; don't let "but what if I'm not home" pull VPN/relay work into v1.0 — that's explicitly out of scope (see Anti-Features).
- **Intake n8n conflicts with copying n8n's own HITL pattern wholesale:** n8n's native "gated tool" / "wait for webhook" approval nodes are a *parallel* approval system to Wyss's bandeja. Webhooks should land as an unclassified proposal that flows into Wyss's own `CognitivePolicyEngine`, not use n8n's approval UI as the gate — otherwise there are two different approval systems with different audit trails, breaking AUDIT-01.

## MVP Definition

### Launch With (v1)

- [ ] **Routine Scheduler core** — NL-to-cron/RRule parsing, persistent job store, routine fires → generates plan → B/C lands in bandeja exactly like manual action — essential because MULTI-02 is an explicit Active requirement and everything else (Daily Assistant, some Notion flows) depends on it existing
- [ ] **Memory (per-agent MEMORY.md, owner-editable)** — essential because AGENT-04 is an explicit Active requirement and Daily Assistant/personalization needs it to not feel generic
- [ ] **Notion adapter — read + policy-gated write** — essential per milestone scope; read path alone is low-risk (level A), write path must go through existing plan+confirm flow — can ship read-only first if write proves complex, but both are milestone targets
- [ ] **Daily Assistant — structured daily summary (agenda + Pellegrini snapshot + bandeja pending + failed-routine alerts)** — essential per milestone scope; built as a special scheduled routine, so mostly a composition/prompt-design task once Scheduler + Memory exist
- [ ] **Mobile APK — QR pairing + LAN discovery + bandeja view + CONFIRMAR from phone** — essential per milestone scope (the headline v1.0 feature); notifications can be a v1.x follow-up if push infra proves too complex for the milestone window
- [ ] **Intake n8n — webhook → unclassified proposal → existing policy engine → bandeja** — essential per milestone scope; keep the n8n side dumb (just POST a payload), keep all classification/audit logic inside Wyss

### Add After Validation (v1.x)

- [ ] **Mobile push notifications (local/foreground-aware first, then evaluate FCM opt-in)** — trigger: owner reports missing bandeja items because they didn't have the app open
- [ ] **Notion write for more action types beyond simple property/page edits (e.g., database schema changes)** — trigger: real usage reveals which Notion write patterns the owner actually needs beyond the initial adapter scope
- [ ] **Daily Assistant curation ("show me more of X, less of Y")** like ChatGPT Pulse's "curate" — trigger: owner finds the fixed-section briefing too rigid or missing something recurring

### Future Consideration (v2+)

- [ ] **Remote (off-LAN) mobile access via Tailscale/VPN** — defer: explicitly out of v1.0 scope per project constraints; adds a security surface that needs its own design pass, not a bolt-on
- [ ] **Cross-agent memory synthesis / "memory of memories"** (orchestrator-level insight built from multiple agents' MEMORY.md files) — defer: needs the per-agent scoping to mature and prove useful standalone first; premature to build a meta-layer
- [ ] **Notion real-time bidirectional sync** — defer: not even solved by mature commercial Notion integrations in 2026; stick to read+confirmed-write

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Routine Scheduler core | HIGH | MEDIUM | P1 |
| Memory (per-agent, editable) | HIGH | MEDIUM | P1 |
| Mobile APK (pairing + bandeja view) | HIGH | HIGH | P1 |
| Notion adapter (read + gated write) | MEDIUM-HIGH | MEDIUM-HIGH | P1 |
| Daily Assistant | MEDIUM-HIGH | LOW-MEDIUM (once Scheduler+Memory exist) | P1 |
| Intake n8n webhooks | MEDIUM | LOW-MEDIUM | P1 |
| Mobile push notifications (true background) | MEDIUM | HIGH (LAN + off-LAN duality) | P2 |
| Daily Assistant curation/preferences | LOW-MEDIUM | LOW | P2 |
| Remote/off-LAN mobile access | LOW (for current single-owner use) | HIGH | P3 |
| Notion real-time bidirectional sync | LOW | VERY HIGH | P3 |

## Competitor Feature Analysis

| Feature | ChatGPT Pulse / Claude Cowork | n8n (HITL + Notion nodes) | Home Assistant Companion | Our Approach |
|---------|-------------------------------|----------------------------|---------------------------|--------------|
| Scheduled proactive task → approval | Pulse shows cards, no explicit human-approval gate for actions (it's read-only research); Cowork asks for review before executing recurring tasks | Gated tool nodes pause and wait for Slack/email approval, but approval state lives in n8n's own execution, separate from any broader audit system | N/A (automations run without a generic approval layer; user pre-approves scenes and automations once at authoring time) | Scheduler output is a plan through the *same* `OrchestratorPort` + policy engine as manual actions — one audit trail, not a bolted-on approval node |
| Memory transparency | Claude: human-readable, editable, deletion is real. ChatGPT: explicit list + opaque implicit recall (two-tier, less transparent) | N/A | N/A | Match Claude's transparency bar; go further with per-agent scoping instead of one global profile |
| External service write-back | N/A (Pulse/Cowork don't write to Notion) | n8n Notion nodes write directly via API calls, with no built-in graduated risk/approval concept — a page edit and a delete are equally "just a node" | N/A | Notion writes classified A-D like any other action; destructive Notion ops treated as high-risk, gated like file/shell D-level actions |
| Companion app connectivity | N/A (cloud-hosted, no local pairing concept) | N/A | Auto-discovers LAN server, manual URL fallback, FCM-based push, critical-alert support on iOS | Auto-discover + QR pairing with cert pinning (stronger security default than "tap through the SSL warning"); push notification strategy deliberately deferred pending LAN-vs-off-LAN design (see Anti-Features and Pitfalls) |

## Sources

- [AI Agent Job Scheduling: Best Patterns for 2026 | Fast.io](https://fast.io/resources/ai-agent-job-scheduling/) — MEDIUM confidence (industry blog, cross-checked against multiple similar sources)
- [Polling Agents in AI Assistants: 11 Implementation Patterns](https://www.glukhov.org/ai-systems/architecture/polling-agents-ai-assistants-implementation-patterns) — MEDIUM confidence
- [Introducing ChatGPT Pulse | OpenAI](https://openai.com/index/introducing-chatgpt-pulse/) — HIGH confidence (official announcement)
- [OpenAI launches ChatGPT Pulse to proactively write you morning briefs | TechCrunch](https://techcrunch.com/2025/09/25/openai-launches-chatgpt-pulse-to-proactively-write-you-morning-briefs/) — HIGH confidence (reputable tech press)
- [Claude Memory: 3 Layers Most Users Miss (2026 Setup)](https://www.shareuhack.com/en/posts/claude-memory-feature-guide-2026) — MEDIUM confidence
- [How to Use Claude Memory vs ChatGPT Memory: Which Is Better for Power Users? | MindStudio](https://www.mindstudio.ai/blog/claude-memory-vs-chatgpt-memory-comparison) — MEDIUM confidence, corroborates markdown vs vector-store distinction
- [Use Claude's chat search and memory to build on previous context | Claude Help Center](https://support.claude.com/en/articles/11817273-use-claude-s-chat-search-and-memory-to-build-on-previous-context) — HIGH confidence (official docs)
- [Getting Started | Home Assistant Companion Docs](https://companion.home-assistant.io/docs/getting_started/) — HIGH confidence (official docs)
- [Companion app for Android: It's been a while - Home Assistant blog](https://www.home-assistant.io/blog/2025/07/23/companion-app-for-android/) — HIGH confidence (official blog)
- [How to Access Jellyfin Remotely in 2026 - WunderTech](https://www.wundertech.net/how-to-access-jellyfin-remotely/) — MEDIUM confidence
- [Networking | Jellyfin official docs](https://jellyfin.org/docs/general/post-install/networking/) — HIGH confidence
- [Request limits - Notion Docs](https://developers.notion.com/reference/request-limits) — HIGH confidence (official docs)
- [Notion API Rate Limits Are Breaking Your Automation — Here's the Real Fix - DEV Community](https://dev.to/kanta13jp1/notion-api-rate-limits-are-breaking-your-automation-heres-the-real-fix-o5p) — MEDIUM confidence, corroborated by official rate-limit docs
- [How to Integrate with the Notion API: Architecture Guide for B2B SaaS | Truto Blog](https://truto.one/blog/how-to-integrate-with-the-notion-api-architecture-guide-for-b2b-saas/) — MEDIUM confidence
- [Human-in-the-loop for AI tool calls | n8n Docs](https://docs.n8n.io/advanced-ai/human-in-the-loop-tools/) — HIGH confidence (official docs)
- [Human in the loop automation: Build AI workflows that keep humans in control – n8n Blog](https://blog.n8n.io/human-in-the-loop-automation/) — HIGH confidence (official blog)
- [Push Notifications Capacitor Plugin API | Capacitor Documentation](https://capacitorjs.com/docs/apis/push-notifications) — HIGH confidence (official docs) — confirms FCM dependency for true push
- [Local Notifications Capacitor Plugin API | Capacitor Documentation](https://capacitorjs.com/docs/apis/local-notifications) — HIGH confidence (official docs) — confirms local-only path exists without a push server
- [Capacitor Android app do Javascript rest calls to Nginx server with self-signed certificate - Ionic Forum](https://forum.ionicframework.com/t/capacitor-android-app-do-javascript-rest-calls-to-nginx-server-with-self-signed-certificate/200959) — LOW-MEDIUM confidence (community forum, no official Capacitor guidance found for this specific case — flagged as a gap, see PITFALLS.md)
- [Run prompts on a schedule - Claude Code Docs](https://code.claude.com/docs/en/scheduled-tasks) — HIGH confidence (official docs), used for NL-to-cron pattern precedent
- [RRule vs Cron — rrule.net](https://www.rrule.net/guides/rrule-vs-cron) — MEDIUM confidence

---
*Feature research for: Wyss v1.0 — Routine Scheduler, Notion adapter, Daily Assistant, Memory, Android companion app*
*Researched: 2026-07-10*
