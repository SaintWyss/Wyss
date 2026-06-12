# Phase 3: Pipeline de Ingesta — Discussion Log

**Date:** 2026-06-12
**Mode:** default (interactivo), con cambio a piloto automático a mitad del área 3 por pedido del owner.

## Áreas seleccionadas

El owner seleccionó las 4 áreas propuestas: Granularidad de exclusión de secretos · Vectores f3/f4 · UX del CLI · Política de archivos problemáticos.

## Área 1 — Granularidad de exclusión de secretos

1. **Archivo con una key adentro:** opciones excluir entero / redactar / excluir chunk → eligió **Excluir archivo entero** (recomendada). → D-27
2. **Reporte al owner:** resumen final + SQLite + audit / inline / silencioso → eligió **Resumen al final + estado SQLite + AuditEvent** (recomendada). → D-28
3. **Capas de detección:** 3 capas (ruta+gateway+entropía) / sin entropía / patrones propios → eligió **3 capas con reuso de secrets_patterns del gateway** (recomendada). → D-29
4. **Falsos positivos de entropía:** allowlist por ruta / sin válvula / umbral global → eligió **Allowlist por ruta en config.toml, solo apaga capa entropía** (recomendada). → D-30

## Área 2 — Vectores: ¿fase 3 o fase 4?

1. **Dónde van los embeddings:** pipeline completo en f3 / solo FTS5 en f3 / opt-in por flag → eligió **Pipeline completo en f3 con vectores** (recomendada). → D-31
2. **Ollama caído al indexar:** degradar / fail-fast / esperar → eligió **Degradar: FTS5 sigue, embeddings pendientes a re-run** (recomendada). → D-32
3. **Chunking:** researcher decide con defaults en config / fijo 512-50 / por tipo desde día 1 → eligió **Researcher/planner deciden** (recomendada). → D-33
4. **Qué muestra --estimate:** completo con costo $0 explícito / mínimo / Claude decide → eligió **Archivos/chunks/tiempo + costo $0 explícito** (recomendada). → D-34

## Área 3 — UX del CLI

1. **Progreso:** barra rich / líneas simples / silencioso+verbose → eligió **Barra rich con etapa+archivo+ETA, degrada en no-interactiva** (recomendada). → D-35
2. **Archivo que falla al extraer:** en esta pregunta el owner respondió (Other): **"toma todas las decisiones recomendadas y solo preguntame cuando haya algo serio serio"** → se activó piloto automático; se aplicó la recomendada (acumular y seguir, resumen final). → D-36

### Resto del área 3 y área 4 — resueltas en piloto automático (opción recomendada)

- Re-run muestra skipped; --dry-run lista con razones. → D-37
- Exit codes 0/≠0 por completitud de corrida. → D-38
- Retry automático de failed, máx 3, luego --retry-failed. → D-39
- Encriptados/no soportados → skipped_unsupported, sin passwords. → D-40
- Límite de tamaño configurable; exceso → solo metadatos. → D-41
- Symlinks no se siguen; denylist de dirs ocultos/ruido. → D-42

## Directiva persistente del owner

"Tomá todas las decisiones recomendadas y solo preguntame cuando haya algo serio serio" — registrada en Claude's Discretion de CONTEXT.md: ante decisiones menores, opción recomendada sin preguntar; consultar solo ante cambios de arquitectura, seguridad o scope.

## Deferred Ideas

Ninguna — la discusión se mantuvo dentro del scope de la fase.
