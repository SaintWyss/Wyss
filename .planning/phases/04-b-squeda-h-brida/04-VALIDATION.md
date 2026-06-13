---
phase: 04
slug: b-squeda-h-brida
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-12
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=9 + pytest-asyncio >=1.4.0 |
| **Config file** | `pyproject.toml` → `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| **Quick run command** | `uv run pytest tests/knowledge/test_rrf.py tests/knowledge/test_retrieval.py -x` |
| **Full suite command** | `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports` |
| **Estimated runtime** | ~30 seconds (quick), ~90 seconds (full) |

**Baseline:** 263 passed, 3 skipped (confirmed 2026-06-12). Full green chain (`mypy`, `ruff`, `lint-imports`).

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/knowledge/ tests/cli/test_search_command.py -x`
- **After every plan wave:** `uv run pytest -x`
- **Before `/gsd:verify-work`:** Full suite must be green

---

## Per-Task Verification Map

| Task ID | Req | Behavior | Test Type | Automated Command | File Exists | Status |
|---------|-----|----------|-----------|-------------------|-------------|--------|
| 04-RRF | KNOW-04 | `rrf_merge()` returns best-ranked Hit from two lists | unit | `uv run pytest tests/knowledge/test_rrf.py -x` | ❌ Wave 0 | ⬜ pending |
| 04-HYBRID | KNOW-04 | `HybridRetrieval.search()` returns merged results | unit | `uv run pytest tests/knowledge/test_retrieval.py::test_hybrid_returns_merged -x` | ❌ Wave 0 | ⬜ pending |
| 04-PERF | KNOW-04 | Smoke test: search completes in <5s over populated index | integration | `uv run pytest tests/knowledge/test_retrieval.py -m integration` | ❌ Wave 0 | ⬜ pending |
| 04-DEGRADED | KNOW-04 | Ollama down → FTS5-only + degraded flag in result | unit | `uv run pytest tests/knowledge/test_retrieval.py::test_degraded_mode -x` | ❌ Wave 0 | ⬜ pending |
| 04-FIELDS | KNOW-05 | Hit contains source_path, snippet, date (D-47 mtime) | unit | `uv run pytest tests/knowledge/test_retrieval.py::test_hit_fields -x` | ❌ Wave 0 | ⬜ pending |
| 04-FRESHNESS | KNOW-10 | `freshness_by_kb()` returns correct indexed_at per BC | unit | `uv run pytest tests/knowledge/test_retrieval.py::test_freshness -x` | ❌ Wave 0 | ⬜ pending |
| 04-GOLDEN | AUD-03 | N=20 golden queries hit@1 >= 0.80 in CI | integration | `uv run pytest tests/knowledge/test_golden_queries.py -x` | ❌ Wave 0 | ⬜ pending |
| 04-AUDIT | D-44 | Degraded search produces AuditEvent with degraded=true | unit | `uv run pytest tests/knowledge/test_retrieval.py::test_degraded_audit -x` | ❌ Wave 0 | ⬜ pending |
| 04-CLI-JSON | D-43 | `wyss search --json` outputs valid JSON array | CLI | `uv run pytest tests/cli/test_search_command.py::test_json_output -x` | ❌ Wave 0 | ⬜ pending |
| 04-CLI-RICH | D-43 | `wyss search` renders Rich Panels (at least 1 result) | CLI | `uv run pytest tests/cli/test_search_command.py::test_rich_output -x` | ❌ Wave 0 | ⬜ pending |
| 04-STATUS | D-47 | `wyss status` shows per-BC freshness date and file counts | CLI | `uv run pytest tests/cli/test_search_command.py::test_status_command -x` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/knowledge/test_rrf.py` — stubs/structure for RRF unit tests (KNOW-04)
- [ ] `tests/knowledge/test_retrieval.py` — stubs for KNOW-04, KNOW-05, KNOW-10, D-44, AUD-03 integration
- [ ] `tests/knowledge/test_golden_queries.py` — golden eval set gate (AUD-03); hit@1 >= 0.80 hard gate
- [ ] `tests/knowledge/golden/corpus.py` — synthetic fixture corpus (FakeEmbedding-compatible)
- [ ] `tests/knowledge/golden/queries.json` — N=20 golden queries → expected filepath mapping
- [ ] `tests/cli/test_search_command.py` — CLI behavior: D-43 Rich/JSON + D-47 status command
