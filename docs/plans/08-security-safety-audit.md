# PR-08 — Security & safety re-audit (fases 6-8 + path LLM)

## 1. Objective
Verificar con evidencia que las mitigaciones de seguridad prometidas por las fases 6-8 existen en el código, y extender el análisis al path LLM nuevo (PR-06). Entregable: `SECURITY.md` de hallazgos, no código.

## 2. Context from the audit
La postura de seguridad es la fortaleza del repo (score 9): denylist Final, 2da muralla, allowlist argv, SecretFilter fail-closed, anti-injection con fixture dorado, audit append-only. Pero: (a) el audit C-level verificó por muestreo, no exhaustivo; (b) PR-06 agrega la superficie más peligrosa posible (LLM generando planes de ejecución); (c) fases 1-2 tienen DECISIONS de seguridad documentadas — fases 6-8 merecen la verificación retroactiva equivalente (`/gsd-secure-phase` existe para esto y no consta corrido para 6-8).

## 3. Exact problem
Sin verificación retroactiva dedicada, afirmaciones como "el adapter re-verifica riesgo antes de ejecutar" o "path traversal contenido" son claims de SUMMARYs de ejecución, no hallazgos auditados.

## 4. Architectural decision
La seguridad se audita con juicio (Fable 5/Claude), jamás se delega a ejecutores baratos. Los fixes que surjan van en PRs separados con spec propio.

## 5. Files to read first
- `src/execution/filesystem.py` (18.7K — traversal, symlinks, verify, 2da muralla)
- `src/execution/shell.py` + `git.py` (allowlist, argv, env del subproceso)
- `src/execution/journal.py` (integridad del undo: ¿el journal mismo es escribible por un plan?)
- `src/core/policy/builtin_deny.py` + `engine.py` (¿cubre la denylist los targets vía symlink/ruta relativa?)
- `src/agents/configured_agent.py` + `scoped_retrieval.py` (anti-injection, permisos)
- `src/knowledge/secret_filter.py` + `src/gateway/secrets_patterns.py` (cobertura de patrones)
- `tests/execution/`, `tests/policy/`, `tests/agents/` (qué está y qué NO está testeado)

## 6. Files allowed to modify
- `docs/audit/SECURITY-REAUDIT.md` (crear — único entregable)

## 7. Files forbidden to modify
- TODO el código. Este PR no arregla: encuentra y clasifica.

## 8. Required changes
Checklist mínimo a verificar con evidencia file:line:
1. **Path traversal**: ¿FileSystemAdapter resuelve/normaliza rutas antes de la 2da muralla? ¿`../` y rutas absolutas fuera de scope se bloquean? ¿Hay test?
2. **Symlinks**: ¿un symlink dentro de un directorio permitido que apunta a `/etc` se sigue? ¿send2trash sobre symlink borra el target? ¿Hay test?
3. **Denylist por alias**: ¿`BUILTIN_DENY` matchea sobre ruta canónica o literal? ¿Un plan con target `data/../../../etc/passwd` evalúa contra qué string?
4. **Journal como target**: ¿un plan puede modificar/borrar `undo_backups`/journal DB, neutralizando el rollback? ¿La denylist wyss-self-modify (gotcha conocido: bloquea file.* sobre `<repo>/data` y `/config`) lo cubre en ambas rutas (relativa/absoluta)?
5. **Shell env**: ¿los subprocesos heredan env completo (con secretos de .env)? ¿Debería pasarse env mínimo?
6. **Inyección vía retrieval**: re-correr mentalmente el fixture dorado contra el prompt del PR-06 (superficie nueva).
7. **Secretos**: ¿`secrets_patterns` y `SecretFilter` comparten patrones o divergen? ¿Gap entre ambos?
8. **Permisos de archivos**: traces.db 0600 verificado; ¿audit.db, ledger.db, index.db tienen modo restrictivo también?
Cada ítem: CONFIRMADO (evidencia) / GAP (riesgo + fix propuesto como PR futuro) / N-A.

## 9. Contracts and invariants
El re-audit no cambia comportamiento. Todo GAP encontrado se clasifica por nivel A-D de impacto.

## 10. Tests required
Ninguno nuevo aquí (los tests faltantes detectados se listan como GAPs con spec sugerido).

## 11. Manual verification
Owner lee SECURITY-REAUDIT.md; cada CONFIRMADO tiene file:line abrible; cada GAP tiene reproducción conceptual.

## 12. Risks
Falsa sensación de seguridad si el auditor muestrea en vez de leer los archivos listados completos. Mitigación: checklist §8 es exhaustivo y cada ítem exige evidencia.

## 13. Rollback plan
N/A (documento).

## 14. Acceptance criteria
- Los 8 ítems del checklist con verdict + evidencia.
- GAPs priorizados P0-P3 con fix propuesto.
- Ejecutado por Fable 5 u Opus (constancia en el doc) — no por ejecutor barato.

## 15. Executor prompt for cheaper AI
NO APLICA. Este plan se ejecuta con `/gsd-secure-phase` o manualmente por Fable 5/Claude (juicio).
Regla del runbook: los gates de seguridad quedan en Claude. Si un modelo barato recibe este spec por
error: detenerse y devolverlo.
