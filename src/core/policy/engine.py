"""CognitivePolicyEngine puro: `Plan -> PolicyDecision`. Sin IO, sin LLM.

El módulo más testeado del sistema. Algoritmo de 5 pasos (RESEARCH §Pattern 3):

1. Hit de denylist (`self._rules.deny`) → D incondicional, `outcome=REJECT`.
2. `per_action = max(_base_level(a) for a in plan.steps)` — desconocido → C (fail-closed).
3. `aggregate = _aggregate_level(plan)` — POL-05, evalúa el plan ENTERO (anti-bypass).
4. `final = max(per_action, aggregate, estimated or A)` — POL-04: estimated solo SUBE.
5. `outcome = outcome_for(final)`.

`RiskLevel` es `IntEnum`, así que `max()` implementa "subir sí, bajar jamás" sin lógica
especial. NO se expone un `evaluate_action()` público: invitaría al bypass por composición
(evaluar pasos uno a uno saltea los agregados). Solo stdlib (`fnmatch`, `os.path`) + core.domain.
"""

import os.path
from fnmatch import fnmatch

from core.domain.plan import Action, Plan
from core.domain.policy import DenyRule, PolicyDecision, PolicyRules
from core.domain.risk import RiskLevel, outcome_for

# action_types tratados como escritura/borrado para agregación y dirs sensibles.
_WRITE_TYPES: frozenset[str] = frozenset(
    {"file.write", "file.create", "file.delete", "file.move", "file.rename"}
)


def _normalize(target: str) -> str:
    """Expande `~` para que los patterns fnmatch (`~/.ssh`, `**/.env*`) matcheen rutas reales."""
    return os.path.expanduser(target)


class CognitivePolicyEngine:
    """Pura: `Plan -> PolicyDecision`. `rules.deny` = BUILTIN_DENY + reglas de config (aditivas)."""

    def __init__(self, rules: PolicyRules) -> None:
        self._rules = rules

    def evaluate(self, plan: Plan) -> PolicyDecision:
        deny_hits = tuple(
            rule.id
            for rule in self._rules.deny
            if any(self._matches(rule, a) for a in plan.steps)
            or self._matches_aggregate(rule, plan)
        )
        if deny_hits:
            return PolicyDecision(
                task_id=plan.task_id,
                risk_level=RiskLevel.D,
                outcome=outcome_for(RiskLevel.D),
                matched_rules=deny_hits,
                reasons=tuple(f"denylist: {rule_id}" for rule_id in deny_hits),
            )

        per_action = max(
            (self._base_level(a) for a in plan.steps),
            default=RiskLevel.A,
        )
        aggregate = self._aggregate_level(plan)
        estimated = plan.estimated_risk or RiskLevel.A
        final = max(per_action, aggregate, estimated)

        reasons: list[str] = [f"per_action={per_action.name}", f"aggregate={aggregate.name}"]
        if plan.estimated_risk is not None:
            reasons.append(f"estimated={plan.estimated_risk.name}")
        return PolicyDecision(
            task_id=plan.task_id,
            risk_level=final,
            outcome=outcome_for(final),
            matched_rules=(),
            reasons=tuple(reasons),
        )

    # -- helpers privados (sin API pública por-acción a propósito) --------------------

    def _base_level(self, action: Action) -> RiskLevel:
        """Fail-closed: un `action.type` desconocido nunca es A (default C)."""
        return self._rules.base_levels.get(action.type, self._rules.unknown_action_level)

    def _matches(self, rule: DenyRule, action: Action) -> bool:
        if not fnmatch(action.type, rule.action_type):
            return False
        if rule.target_patterns and not any(
            fnmatch(_normalize(action.target), p) for p in rule.target_patterns
        ):
            return False
        return all(action.parameters.get(k) == v for k, v in rule.params_equal.items())

    def _matches_aggregate(self, rule: DenyRule, plan: Plan) -> bool:
        """Regla `mass-delete`: el plan agrega > `delete_count_d` borrados → hit D."""
        if rule.id != "mass-delete":
            return False
        delete_count = sum(1 for a in plan.steps if a.type == "file.delete")
        return delete_count > self._rules.thresholds.delete_count_d

    def _aggregate_level(self, plan: Plan) -> RiskLevel:
        """POL-05: evalúa el plan ENTERO (conteos), no por-acción. Devuelve el nivel agregado."""
        thresholds = self._rules.thresholds
        writes: list[Action] = [a for a in plan.steps if a.type in _WRITE_TYPES]

        distinct_targets = {a.target for a in writes}
        distinct_dirs = {os.path.dirname(_normalize(a.target)) for a in writes}
        has_delete = any(a.type == "file.delete" for a in plan.steps)
        touches_sensitive = any(
            self._under_sensitive(a.target) for a in writes if a.type != "file.read"
        )

        level = RiskLevel.A
        if len(distinct_targets) > thresholds.file_count_b:
            level = max(level, RiskLevel.B)
        if len(distinct_targets) > thresholds.file_count_c:
            level = max(level, RiskLevel.C)
        if len(distinct_dirs) > thresholds.dir_count_c:
            level = max(level, RiskLevel.C)
        if has_delete:  # docs/13: cualquier borrado es mínimo C
            level = max(level, RiskLevel.C)
        if touches_sensitive:
            level = max(level, RiskLevel.C)
        return level

    def _under_sensitive(self, target: str) -> bool:
        norm = _normalize(target)
        return any(
            fnmatch(norm, _sensitive_glob(p)) for p in self._rules.thresholds.sensitive_dirs
        )


def _sensitive_glob(pattern: str) -> str:
    """Un dir sensible (`~/.ssh`, `/etc`) matchea su contenido; un glob (`**/.env*`) va tal cual."""
    expanded = _normalize(pattern)
    if any(ch in expanded for ch in ("*", "?", "[")):
        return expanded
    return f"{expanded.rstrip('/')}/**"
