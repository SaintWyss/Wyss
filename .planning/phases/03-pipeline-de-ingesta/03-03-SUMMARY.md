---
plan: 03-03
status: complete
---

# Plan 03-03 Summary

**One-liner:** Se construyó el `SecretFilter` puro de 3 capas para excluir secretos antes de indexar, con patrones built-in inyectados.

## What was built
Task 1: `SecretFilter` implementa capa 1 por path/nombre/extensión sin abrir archivos, capa 2 por regex inyectados, y capa 3 por tokens de alta entropía con Shannon para base64 y hex. La allowlist por glob desactiva solo la capa de entropía; los patrones conocidos y la denylist de paths siguen activos. Los retornos son únicamente `(pattern_name, layer)`, sin exponer valores crudos de secretos.

Se agregaron tests unitarios para denylist de path, detección de patrón `anthropic_key` inyectado, detección por entropía base64 y hex, prosa normal sin falsos positivos, allowlist limitada a capa 3, y garantía de que el valor del secreto no aparece en el retorno.

## Key files
### Created
- `src/knowledge/secret_filter.py` — clase pura `SecretFilter`, constantes default de denylist, tokenización por regex y cálculo Shannon sin IO ni imports de gateway.
- `tests/knowledge/test_secret_filter.py` — cobertura de las tres capas, allowlist D-30 y no filtración del valor secreto.

### Modified
- None.

## Decisions
- Se mantuvo el reuso de `BUILTIN_SECRET_PATTERNS` por inyección de constructor para respetar `lint-imports`; `knowledge.secret_filter` no importa `gateway`.
- Se agregó un patrón default `^\.env(?:\.|$)` en `FILENAME_PATTERNS` para cubrir `.env*` de forma conservadora además de los nombres exactos de `PATH_DENYLIST`.
- La capa 3 retorna el nombre genérico `high_entropy`, sin distinguir ni exponer el token detectado.

## Self-Check
- pytest: 214 passed / 2 skipped
- mypy: Success: no issues found in 95 source files
- ruff: All checks passed
- lint-imports: 2 kept, 0 broken
