"""Política cognitiva: denylist built-in (Final) + engine puro Plan -> PolicyDecision."""

from core.policy.builtin_deny import BUILTIN_DENY
from core.policy.engine import CognitivePolicyEngine

__all__ = ["BUILTIN_DENY", "CognitivePolicyEngine"]
