---
plan: 07-04
status: complete
---

Implemented `ConfiguredAgent` in `src/agents/configured_agent.py`: prompt construction wraps retrieved BC hits in `<untrusted_content>` with explicit data-not-instructions warnings, `_run` performs the AGENT-01 retrieval -> prompt -> gateway -> deterministic `engine.evaluate` -> `PlanRunner.run` cycle, and the second wall audits and raises `PolicyViolation` for D/REJECT plans before execution. The module delegates only to the injected runner and the AST gate confirms no `self.execute(...)` recursion.

Updated `tests/agents/test_configured_agent.py` to use the current `Hit(entry_id=...)` domain shape. Reworked `tests/agents/test_golden_injection.py` to exercise the real ConfiguredAgent path with the malicious fixture as retrieval data, a dangerous generated plan, `RecordingEngine`, D/REJECT assertions, blocked runner, and `POLICY_DECISION` audit assertion.

Verification:
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/agents/test_configured_agent.py tests/agents/test_golden_injection.py -q` -> 6 passed.
- AST no-recursion gate -> `no-recursion ok`.
- `UV_CACHE_DIR=/tmp/uv-cache uv run mypy src/agents` -> success.
- `UV_CACHE_DIR=/tmp/uv-cache uv run lint-imports` -> 2 contracts kept, 0 broken.
