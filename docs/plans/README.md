# Planes de reparación (PR-SPECs)

> Generados por auditoría C-Level 2026-07-02. Formato: 15 secciones, ejecutables por modelos baratos.
> Orden de ejecución: ver `docs/roadmap/WYSS_REPAIR_ROADMAP.md`.

## Incluidos

| Spec | Título | Executor |
|---|---|---|
| `00-baseline-stabilization.md` | Baseline: higiene data/, gitignore, tag | Claude Code |
| `01-build-test-lint-fix.md` | CI: GitHub Actions con la cadena existente | Codex |
| `03-configuration-cleanup.md` | Config: podar deps muertas, .env, provider docs | Codex |
| `06-ai-layer-boundaries.md` | LLMOrchestrator sobre OrchestratorPort vía gateway | Codex (plan Fable) |
| `07-ux-product-pass.md` | UX de CLI: errores, empty states, consistencia | Codex + criterio Claude |
| `08-security-safety-audit.md` | Re-audit seguridad fases 6-8 | Fable 5 |
| `09-documentation-rebuild.md` | README/CLAUDE.md/docs reales | Gemini draft + Claude verifica |
| `10-release-candidate.md` | Corte y tag v0.1.0-rc1 | Owner + Fable 5 |

## Omitidos (con razón — evidencia en `docs/audit/WYSS_C_LEVEL_AUDIT.md`)

- **02-project-structure-normalization** — la estructura ya está normalizada y ENFORCED: import-linter
  2/2 contratos kept (core stdlib-only + independencia de capas), layout por capa consistente, tests
  espejando src. Reestructurar sería churn sin defecto que reparar.
- **04-core-architecture-repair** — el core no está roto: mypy strict 0 issues sobre src+tests, dominio
  frozen puro, ports-first (D-11), 424 tests verdes. Nada que reparar.
- **05-agent-policy-engine** — ya existe y es la parte más fuerte del repo: `CognitivePolicyEngine` +
  `BUILTIN_DENY` Final + agregados anti-bypass + segunda muralla en adapters + fail-closed D por
  valor+isinstance (fix CR-01, plan 01-04). Se documenta en la auditoría; no hay PR que hacer.
