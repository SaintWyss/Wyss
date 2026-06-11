---
phase: 2
slug: gateway-de-modelos
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-11
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing, green at 69 passed) |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/gateway -q` |
| **Full suite command** | `uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports` |
| **Estimated runtime** | ~10 seconds (full chain) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/gateway -q`
- **After every plan wave:** Run full chain (`uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports`)
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Filled by the planner — each task maps to its requirement, test type, and command.
> Success criteria anchors (from ROADMAP Phase 2):

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (planner fills) | — | — | GATE-01 | — | Dos providers intercambiables vía config, FakeProvider en tests | unit | `uv run pytest tests/gateway -q` | ❌ W0 | ⬜ pending |
| (planner fills) | — | — | GATE-02 | — | Tier→provider+modelo determinístico desde config | unit | `uv run pytest tests/gateway -q` | ❌ W0 | ⬜ pending |
| (planner fills) | — | — | GATE-03 | T-secret-egress | Fixture "secreto trampa" NUNCA en payload saliente; llamada bloqueada | unit (security) | `uv run pytest tests/gateway -q` | ❌ W0 | ⬜ pending |
| (planner fills) | — | — | GATE-04 | T-budget-bypass | Presupuesto agotado → llamada bloqueada ANTES de salir (gate, no reporte) | unit (security) | `uv run pytest tests/gateway -q` | ❌ W0 | ⬜ pending |
| (planner fills) | — | — | GATE-05 | — | Cada llamada deja trace: prompt, output, latencia, tokens, costo | unit | `uv run pytest tests/gateway -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/gateway/__init__.py` + `tests/gateway/conftest.py` — shared fixtures (FakeProvider, secreto trampa, config gateway de prueba)
- [ ] Test stubs for GATE-01..05 per plan breakdown

*Framework already installed — no Wave 0 install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| LiteLLMProvider contra proxy real localhost:4000 | GATE-01 | Requiere Docker litellm levantado + LITELLM_MASTER_KEY; opt-in env var | `WYSS_TEST_LITELLM=1 uv run pytest tests/gateway -m integration` |
| OllamaEmbeddingProvider real | GATE-01 (criterio 5) | Ollama NO instalado — decisión usuario: skipif opt-in (patrón NTFS Fase 1) | Instalar Ollama + `ollama pull nomic-embed-text`, luego `WYSS_TEST_OLLAMA=1 uv run pytest tests/gateway -m integration` |
| AnthropicProvider real | GATE-01 | Sin ANTHROPIC_API_KEY (decisión usuario: mock respx; real gated) | Cargar key en .env, luego `WYSS_TEST_ANTHROPIC=1 uv run pytest tests/gateway -m integration` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
