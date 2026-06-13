# Decisions — Fase 1 (fundaciones)

Movidas desde STATE.md al cierre de fase (compactación del Decisions Log).

| Date | Decision | Context |
|------|----------|---------|
| 2026-06-11 | `include_external_packages=true` en import-linter | El contrato `forbidden` de `core` lista `pydantic` (externo); sin esa opción `lint-imports` aborta (01-01) |
| 2026-06-11 | `uv.lock` commiteado; `src/__init__.py` eliminado | Instalaciones reproducibles; el `__init__.py` raíz rompía los imports flat `from core...` (Assumption A5) (01-01) |
| 2026-06-11 | `AgentBase` en `core/ports/agent.py` (Open Question 1) | Satisface "14 ports en core/ports/" y es puro (solo domain + ports); import-linter verde (01-02) |
| 2026-06-11 | `execute(plan, decision)` recibe ambos | `Plan` es frozen y solo lleva `estimated_risk`; el nivel FINAL viaja en `PolicyDecision` (01-02) |
| 2026-06-11 | `SqliteAuditLogger.span()` usa `AuditEvent.new` directo | El dominio frozen solo expone `new()`; el adapter compone los SPAN_* sin inventar API en el núcleo puro (01-03) |
| 2026-06-11 | Smoke test WAL fail-fast al construir el logger | `journal_mode≠wal` → `AuditIntegrityError`; nunca degradar silencioso un audit log sobre NTFS/fuseblk (Pitfall 6/T4) (01-03) |
| 2026-06-11 | Test ntfs opt-in vía `skipif` por `WYSS_TEST_NTFS` | No alterar `addopts` globales; el test de integración sobre el mount real corre solo on-demand (01-03) |
| 2026-06-11 | deny rules de config: `match_action`→`action_type`, `match_target`→`target_patterns` | Mapeo del TOML canónico al `DenyRule` de dominio; `match_target` ausente = tupla vacía (matchea cualquier target) (01-06) |
| 2026-06-11 | Guarda de rechazo D por valor/orden + `isinstance` fail-closed (no `is`) | CR-01: `risk_level is RiskLevel.D` era no-op ante ints crudos de deserialización JSON-RPC; ahora `risk >= RiskLevel.D` tras isinstance guard rechaza fail-closed (POL-03, 01-04) |
| 2026-06-11 | `CognitivePolicyEngine` sin `evaluate_action()` público; agregados a nivel-plan | Evaluar pasos uno a uno saltearía los umbrales agregados (bypass por composición); 200 deletes → D solo si se evalúa el plan entero (POL-05, 01-05) |
| 2026-06-11 | `BUILTIN_DENY` como `Final[tuple[DenyRule,...]]` en código, no en TOML | La config solo agrega reglas (`deny = BUILTIN_DENY + config`); nunca puede vaciarlas — D sigue absoluto sin importar el TOML (regla #2; POL-04, 01-05) |
| 2026-06-11 | `load_settings` levanta `ConfigError` (dominio) en vez de `sys.exit` | Fail-fast testeable con `pytest.raises`; el caller CLI de Fase 5 decide el exit. Pydantic muere en bootstrap — core nunca ve un BaseModel (import-linter; SC5, 01-06) |
