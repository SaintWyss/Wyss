---
phase: 02-gateway-de-modelos
audited: 2026-06-12
status: secured
threats_total: 24
threats_closed: 24
threats_open: 0
---

# SECURITY — Phase 02: Gateway de Modelos

**Audited:** 2026-06-12
**Auditor:** gsd-security-auditor (adversarial verification, FORCE stance)
**ASVS Level:** default
**Status:** SECURED — 24/24 threats resolved (20 mitigate CLOSED, 4 accept logged)
**Code review baseline:** 02-REVIEW.md (CR-01 + WR-01..10 all `fixed`, commits ae59b10..13e29cd) — factored as mitigation evidence.

Implementation files are READ-ONLY for this audit. No implementation was modified.

---

## Mitigated Threats (verified present in code)

| Threat ID | Category | Evidence (file:line / test) |
|-----------|----------|------------------------------|
| T-02-01 | Info Disclosure | `.gitignore:34-36` (`.env`, `.env.*`, `!.env.example`); `config/.env.example` holds placeholders only (`sk-ant-...`, `...`) |
| T-02-02 | Tampering | `core/domain/errors.py:40-42` `SecretDetected.__init__` takes only `pattern_name`; `tests/gateway/test_minimizer.py:105` `test_el_secreto_nunca_aparece_en_la_excepcion` |
| T-02-SC | Tampering (supply chain) | `uv.lock:193/517/530` pin httpx/pytest-asyncio/respx; 308 `sha256` hashes in `uv.lock` |
| T-02-secret-egress | Info Disclosure | `gateway/minimizer.py:45-57` fail-closed, 3 sources (env_values, builtins, config); `tests/gateway/test_minimizer.py:93` multi-format trap |
| T-02-secret-log | Info Disclosure | `gateway/minimizer.py:53,56` raises `SecretDetected(name)` only; gateway audits `pattern` only (`gateway.py:102-106`) |
| T-02-patterns-tamper | Tampering | `gateway/secrets_patterns.py:21` `Final[tuple]`; merge additive `minimizer.py:41-43`; `test_minimizer.py:126` `test_builtins_no_vaciables_por_config` |
| T-02-tier-fallback | Tampering/Repudiation | `gateway/router.py:20-25` `UnknownTier`, no fallback; `gateway.py:91-95` propagates + audits |
| T-02-double-retry | DoS | providers call `resp.raise_for_status()` with no internal retry (`anthropic.py:47`, `litellm.py:42`); `test_retry.py:91` `test_4xx_fail_fast_no_retry` (1 call) |
| T-02-key-in-log | Info Disclosure | keys from `os.environ` to headers (`bootstrap/gateway.py:80-84`); `cost_usd=0.0` in ModelResponse; never logged |
| T-02-sdk-type-leak | Tampering | `anthropic.py:49-53`, `litellm.py:43-50` JSON dict dies in adapter, only `ModelResponse` exits |
| T-02-budget-bypass | DoS | `cost.py:75-91` `authorize()` raises `BudgetExceeded` pre-call; re-passed each retry `gateway.py:217`; `test_cost_gate.py:71` |
| T-02-budget-advisory | DoS | `cost.py:65-73,132` local cost always (D-24); provider cost stored comparative only, never gates; `test_cost_gate.py:113` |
| T-02-budget-override | Tampering/Repudiation | `cost.py` exposes no limit setters; limits fixed at construct (`__init__:40-54`); change only via config + reload |
| T-02-trace-wal | Tampering | `gateway/db.py:47-59` WAL smoke fail-fast raises `TraceIntegrityError`; `test_cost_gate.py:141` standalone fail-fast |
| T-02-e2e-secret-egress | Info Disclosure | `test_e2e_security.py:68` `test_format_secret_never_egresses` (5 formats incl. `sk-proj-`/`AIza`), provider 0 calls |
| T-02-e2e-secret-log | Info Disclosure | `test_e2e_security.py` asserts secret absent from TASK_FAILED payload/message; only `pattern` |
| T-02-budget-bypass(e2e) | DoS (denial-of-wallet) | `gateway.py:214-217` authorize inside retry loop; inflight reservation `cost.py:93-115` (WR-06); `test_cost_gate.py:164` |
| T-02-double-retry(e2e) | DoS | `gateway.py:54-61,231-238` 4xx fail-fast / transient retry; `test_retry.py:126` `test_transient_exhausts_retries` (3 calls) |
| T-02-tier-fallback(e2e) | Tampering | `test_e2e_security.py` `test_unknown_tier_propagates_without_fallback`, provider 0 calls |
| T-02-key-in-trace | Info Disclosure | `bootstrap/gateway.py:80-84` keys only environ→headers; trace `write()` stores POST-min prompt only |
| T-02-trace-file-perms | Info Disclosure | `gateway/db.py:37-46` pre-create `os.open(...,0o600)` + chmod, failures logged; `test_e2e_security.py:398` + `test_cost_gate.py:153` 0600 verified |
| T-02-audit-independence | Tampering | `gateway.py:32-46` imports only `core.ports.audit`/`core.domain.audit`; `test_gateway.py:342` scans for `import audit`; lint-imports `independence` contract KEPT |

## Accepted Risks (logged here per accept disposition)

| Threat ID | Category | Rationale | Code anchor |
|-----------|----------|-----------|-------------|
| T-02-false-negative | Info Disclosure | Regex/substring coverage cannot catch every secret format; env_value substring net + builtin patterns are best-effort. Accepted; high-precision env_value layer covers the owner's actual keys. | `gateway/minimizer.py:51-56` |
| T-02-embed-egress | Info Disclosure | `OllamaEmbeddingProvider` egresses content to localhost:11434 (trusted local Ollama, D-15). Accepted. | `gateway/providers/ollama.py:1-8,30-36` |
| T-02-trace-pii | Info Disclosure | `traces.db` stores POST-minimizer prompts/outputs; local file, 0600 perms, 90d retention purge. Residual PII accepted. | `gateway/traces.py:55-119`, `bootstrap/gateway.py:68` |
| T-02-config-regex-dos | DoS | Config-supplied secret regex could be catastrophic; config is authored by the trusted owner and compiled fail-fast at boot. Accepted. | `bootstrap/config.py:233-240` |

## Unregistered Flags

None. No `## Threat Flags` section is present in any 02-0*-SUMMARY.md. 02-05-SUMMARY.md `## Threat Model Coverage` maps only to registered IDs. No new attack surface appeared during implementation without a threat mapping.

## Notes

- WR-09 fix relocated 0600 + WAL handling into the shared `open_gateway_db` helper (`src/gateway/db.py`) — both `TraceStore` and `CostTracker` now obtain identical perms/durability guarantees regardless of construction order.
- WR-10 fix added a stdlib `.env` loader in bootstrap (`src/bootstrap/config.py:97-122`, `load_settings:293`) so the minimizer's env-value layer is actually populated; CR-01 fix added `GOOGLE_API_KEY`/`OPENAI_API_KEY` to `_GATEWAY_ENV_KEYS` and `google_api`/`openai_proj` builtin patterns.
