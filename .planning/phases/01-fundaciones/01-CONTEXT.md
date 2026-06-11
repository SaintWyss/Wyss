# Phase 1: Fundaciones - Context

**Gathered:** 2026-06-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Núcleo hexagonal puro: entidades de dominio, los 14 ports como Protocols, AuditLogger funcional, CognitivePolicyEngine determinístico y config TOML validada con fail-fast. Sin IO de negocio, sin LLM, sin daemon — solo la fundación que todo lo demás recibe inyectada. (POL-01..05, AUD-01 esquema.)

</domain>

<decisions>
## Implementation Decisions

**Fuente:** el owner entregó la spec completa en `docs/18-prompt-implementacion.md` en lugar de discusión por áreas. Las decisiones de abajo se extraen de ese documento; es la referencia canónica ante cualquier duda.

### Estructura de paquete
- **D-01:** Mantener el layout del prompt: `src/core/ports/` + `src/core/` (lógica pura) + módulos por capa (`orchestrator/`, `agents/`, `knowledge/`, `gateway/`, `execution/`, `audit/`). Los stubs existentes se conservan y se rellenan — NO se reestructura a un `adapters/` top-level. Las implementaciones concretas de ports viven dentro de su módulo de capa.
- **D-02:** Carpetas nuevas se documentan en el README.

### Política cognitiva (núcleo de la fase)
- **D-03:** Semántica de niveles exacta del prompt: A ejecuta directo · B muestra plan y pide `[s/N]` · C muestra plan con advertencia y exige escribir `"CONFIRMAR"` · D rechaza siempre, sin path de ejecución, rechazo auditado.
- **D-04:** Clasificación D determinística por denylist (decisión de research ya commiteada en ROADMAP/STATE): el LLM puede subir el riesgo estimado, nunca bajarlo.
- **D-05:** La política evalúa el plan completo + agregados — sin bypass por composición (POL-05).

### Auditoría
- **D-06:** Audit store en **SQLite separado de los datos de usuario** (índice/BC van en otra DB). Decisión fija del prompt.
- **D-07:** Registro mínimo por evento: actor, instrucción, plan, decisión de política, confirmación, acciones, resultado, costo.
- **D-08:** AuditLogger se inyecta por constructor a todo componente posterior — regla #1: si no está auditado, no está terminado.

### Config y DI
- **D-09:** `config.toml` (TOML) para configuración; `.env` solo para secretos/keys de proveedores. Validación Pydantic al boot, fail-fast con error legible.
- **D-10:** DI por constructores explícitos — sin framework DI. Composition root manual.
- **D-11:** Interfaces primero: los Protocols de `core/ports/` se definen y commitean antes que cualquier implementación. Módulos vecinos importan de `core/ports/`, nunca de implementaciones.

### Tests
- **D-12:** Tests de seguridad explícitos obligatorios en esta fase: acción nivel D → rechazada y nunca ejecutada; plan compuesto que agrega a D → clasificado D. Foco en bordes críticos, no coverage.
- **D-13:** mypy strict en `core/`; `ruff` lint+format; pytest.

### Claude's Discretion
- **Contenido inicial de la denylist D** — el owner no enumeró operaciones. Arrancar conservador: borrado masivo/recursivo fuera de papelera, modificación de config/permisos/presupuesto de Wyss por un agente (regla #6), exfiltración de secretos, escritura en `~/.ssh`/system files, `git push --force` a main, formateo/particionado. Ampliable por config (la denylist es datos, no código).
- **Umbrales de agregación A→B→C** (cuántos archivos/qué directorios escalan nivel) — proponer defaults sensatos, configurables en `config.toml`.
- **Esquema exacto de tablas SQLite de auditoría** — respetando D-07 como campos mínimos.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Spec de implementación (la más importante — entregada por el owner)
- `docs/18-prompt-implementacion.md` — decisiones técnicas fijas, principios de arquitectura (hexagonal/SOLID/plugin/DI), reglas inviolables 1-9, criterios de tests. Ante conflicto: seguridad cognitiva primero.

### Diseño fundacional
- `docs/07-arquitectura-conceptual.md` — los 5 bloques y principios arquitectónicos
- `docs/08-diagrama-componentes.md` — componentes y comunicación
- `docs/09-modelo-de-datos.md` — entidades de dominio
- `docs/11-diagramas-uml.md` — secuencias (flujo de comando con política)
- `docs/13-politica-acceso-seguridad.md` — política cognitiva y niveles A-D
- `docs/16-criterios-de-aceptacion.md` — criterio transversal: nada se acepta con vía para ejecutar D, acción sin auditar, o secreto enviado afuera

### Research (decisiones técnicas ya tomadas)
- `.planning/research/ARCHITECTURE.md` — los 14 ports (§Interface Contracts), build order, patrones Python concretos (Protocols vs ABCs, frozen dataclasses, composition root manual, enums + exhaustive matching para la política)
- `.planning/research/PITFALLS.md` — D determinística, bypass por composición, auditoría primero
- `.planning/research/STACK.md` — Pydantic v2, ruff, mypy strict, WAL mode

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/{core,orchestrator,agents,knowledge,gateway,execution,audit}/__init__.py` — stubs vacíos del init; el layout coincide con la spec del owner. Se conservan y rellenan.
- `config/config.example.yaml` — queda obsoleto: la spec fija TOML. Reemplazar por `config.example.toml` en esta fase.
- `config/.env.example` — se mantiene (secretos de proveedores).

### Established Patterns
- Ninguno aún — esta fase los establece. Todo lo que se escriba acá ES el patrón para las 9 fases siguientes.

### Integration Points
- `pyproject.toml` no existe — crearlo con `uv init` es parte de esta fase.
- `data/` gitignoreado para DBs runtime.

</code_context>

<specifics>
## Specific Ideas

- "No es prototipo. No es MVP. Cada fase se implementa completa." — estándar de calidad explícito del owner.
- Regla #9 del owner: si agregar una feature obliga a modificar código existente, es defecto de diseño. Los tests de extensibilidad lo verifican.
- Filosofía rectora en todo diseño de API: humano primero — Wyss ejecuta lo que Santiago decidió, no decide por él.

</specifics>

<deferred>
## Deferred Ideas

- **Conflicto pdfplumber (prompt) vs pymupdf (research)** — decidir en Fase 3 (Pipeline de Ingesta) con benchmark real sobre archivos del owner. No afecta Fundaciones.
- **Watchdog para re-indexación automática** — el prompt lo marca opcional; REQUIREMENTS lo tiene en v2. Fase 3 decide si entra.
- **`agents.toml` separado de `config.toml`** — detalle de Fase 7; el prompt lo menciona, registrarlo ahí.

</deferred>

---

*Phase: 1-Fundaciones*
*Context gathered: 2026-06-10*
