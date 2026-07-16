# Estado real de Wyss

Última revisión documental: 2026-07-16.

## Resumen

El código de `main` contiene el alcance funcional del milestone interno **v1.0 — app móvil + asistente diario**. Sin embargo, el paquete Python, el README histórico y varias release notes todavía usan `0.1.0`. Por eso deben separarse dos conceptos:

- **alcance implementado:** fases 1–15, incluido el cliente Android;
- **versión distribuida/formal:** el metadata de `pyproject.toml` continúa en `0.1.0` y no prueba por sí solo una release pública v1.0.

No declarar una release v1.0 distribuible hasta unificar versionado, artefactos, changelog y gates de publicación.

## Matriz de capacidades

| Área | Estado | Evidencia principal | Observaciones |
|---|---|---|---|
| Política A–D, confirmaciones y denylist no removible | Implementada | `src/core/policy/`, daemon y tests de seguridad | Nivel D no es confirmable; la política se reevalúa al confirmar |
| Ejecución real y verificación | Implementada | `src/execution/`, `PlanExecutor`, daemon | FileSystem, Shell y Git; fail-closed |
| Undo | Parcial | `src/execution/undo.py`, CLI `wyss undo` | Solo inversas `file.*`; shell/git no tienen undo |
| Auditoría SQLite | Implementada con gap RPC | `src/audit/`, CLI `wyss audit` | El método JSON-RPC `audit` todavía devuelve lista vacía |
| Indexación y búsqueda híbrida | Implementada | `src/knowledge/` | FTS5 + vectores + RRF |
| Gateway de modelos | Implementado | `src/gateway/` | Presupuesto, minimización, providers y trazas |
| Orquestador deterministic | Implementado | `src/bootstrap/cli.py` | Es el default de `config/config.example.toml` |
| Orquestador LLM | Implementado y smokeado en entorno del owner | `LLMOrchestrator`, `.planning/STATE.md` | Validado con Qwen vía LiteLLM local; otros providers requieren su propia aceptación |
| Agentes configurables | Implementados | `src/agents/` y `[[agents]]` | Agregar definición no debe requerir cambiar el núcleo |
| Pellegrini / ledger | Implementado | `src/ledger/`, CLI `wyss fin` | Cálculos deterministas, no delegados al LLM |
| Bridge web/PWA LAN | Implementado y validado en teléfono | `src/bootstrap/web.py`, release v0.1.0 | Pairing, cookie, HTTPS local, voz y confirmaciones |
| Routine Scheduler | Implementado | `src/orchestrator/scheduler.py`, `routine_store.py` | Cron/interval, catch-up coalescente, pause/resume/delete |
| Notion Adapter | Implementado | `src/notion/` | Lecturas A y escrituras gateadas; requiere token y páginas compartidas |
| Owner Memory | Implementada | `src/memory/`, domain/ports y CLI | Persistente, editable y con tiers owner/external |
| Daily Assistant | Implementado | `src/orchestrator/digest.py`, RPC `digest.today` | Solo lectura; puede programarse desde `[digest]` |
| Intake n8n | Implementado opt-in | daemon `intake.propose`, web `/api/intake` | Bearer dedicado y floor B; nunca usa cookie de pairing |
| Web PC polish | Implementado | SPA embebida y superficies de rutinas/memoria/digest | Debe mantenerse sincronizada con la API interna |
| Android APK | Implementado y checkpoint físico aprobado | `mobile/`, Phase 15 summary/validation | Instalación, pairing QR, TOFU y carga del bridge aprobados en dispositivo real |
| Modo Equipo | Fuera de alcance actual | decisión de roadmap | No debe presentarse como implementado |
| Multi-agente autónomo pleno | No es el modelo actual | arquitectura vigente | Hay agentes especializados, pero no autonomía sin gate del owner |

## Validaciones confirmadas

La release v0.1.0 registró 539 pruebas, mypy strict, Ruff e import-linter verdes, además de un smoke físico del bridge web.

Después de esa release se agregaron rutinas, Notion, memoria, digest, intake, web y APK. Las fases contienen summaries y validaciones específicas, incluida la aprobación E2E del APK en un teléfono real el 11 de julio de 2026.

El CI raíz actual ejecuta:

```bash
uv run pytest -q
uv run mypy
uv run ruff check src tests
uv run lint-imports
```

La existencia de CI verde para Python no implica automáticamente que web y Android estén validados en cada PR. Ver [`TESTING.md`](TESTING.md).

## Contradicciones resueltas

### “LLM real verificado” frente a “pendiente”

El modo LLM está implementado y hubo un smoke manual en el entorno del owner usando Qwen a través de LiteLLM local. La redacción correcta es:

> El flujo LLM fue validado en esa configuración concreta. Cada provider, modelo o gateway alternativo requiere su propia prueba de conectividad, calidad y límites.

No debe volver a describirse como “pendiente de toda verificación”, pero tampoco como garantía universal para cualquier proveedor.

### v0.1.0 frente a milestone v1.0

`v0.1.0` es una release histórica cerrada el 10 de julio. El código posterior implementó el milestone v1.0, pero el metadata del paquete sigue en `0.1.0`. Hasta unificarlo, la documentación debe decir **“alcance v1.0 implementado”**, no “release v1.0 publicada”.

### `.planning/ROADMAP.md` y `.planning/STATE.md`

Los artefactos de planificación acumularon casillas y métricas contradictorias durante la ejecución. El estado canónico se determina por código, pruebas, summaries de fase y este documento.

## Riesgos y límites vigentes

- `audit` por JSON-RPC sigue siendo stub; el CLI directo funciona.
- Undo no cubre shell ni Git.
- El modo deterministic sigue siendo el default de la plantilla.
- El gateway LLM depende de infraestructura y secretos externos.
- El bridge LAN usa TLS local; certificados self-signed requieren confianza TOFU.
- Los permisos `0600` pueden no aplicarse en NTFS/FUSE.
- Los datos SQLite que requieren WAL deben vivir en un filesystem compatible.
- El APK validado usa el flujo local del owner; distribución, firma release y actualización segura deben documentarse antes de publicar.
- CI no ejecuta actualmente toda la matriz web/Android en el workflow raíz.
- El versionado del package y la narrativa de release están desalineados.

## Gates para declarar una release v1.0 formal

1. actualizar `pyproject.toml`, cliente móvil y cualquier superficie que muestre versión;
2. crear changelog consolidado desde v0.1.0;
3. producir artefactos reproducibles y firmados;
4. ejecutar la cadena Python, web y Android desde un commit exacto;
5. repetir smoke de daemon, bridge, LLM, Notion, intake y APK;
6. documentar upgrade y rollback;
7. eliminar o marcar stubs operativos, especialmente audit RPC;
8. publicar checksums y evidencia de aceptación.
