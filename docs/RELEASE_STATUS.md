# Estado real de Wyss

Última revisión documental: 2026-07-20.

## Resumen

El código de `main` contiene el alcance funcional del milestone interno **v1.0 — app móvil + asistente diario**:

- **alcance implementado:** fases 1–16, incluidos el cliente Android y el Home Authority Core;
- **versión activa:** `1.0.0` en package, web y cliente Android.

La preparación de release está completa: changelog, matriz de gates desde un commit exacto,
artefactos, upgrade y rollback. Ver [`../CHANGELOG.md`](../CHANGELOG.md),
[`releases/WYSS_v1.0.0.md`](releases/WYSS_v1.0.0.md) y [`UPGRADE.md`](UPGRADE.md).
El tag y la publicación quedan sujetos a la autorización explícita del owner.

## Matriz de capacidades

| Área | Estado | Evidencia principal | Observaciones |
|---|---|---|---|
| Política A–D, confirmaciones y denylist no removible | Implementada | `src/core/policy/`, daemon y tests de seguridad | Nivel D no es confirmable; la política se reevalúa al confirmar |
| Ejecución real y verificación | Implementada | `src/execution/`, `PlanExecutor`, daemon | FileSystem, Shell y Git; fail-closed |
| Undo | Parcial | `src/execution/undo.py`, CLI `wyss undo` | Solo inversas `file.*`; shell/git no tienen undo |
| Auditoría SQLite | Implementada | `src/audit/`, CLI y RPC `audit` | Lectura acotada por port; payload omitido por defecto |
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

El CI raíz actual ejecuta en jobs bloqueantes:

```bash
uv run pytest -q
uv run mypy src tests
uv run ruff check src tests
uv run lint-imports
cd web && npm run test && npm run lint && npm run build
cd mobile && npx cap sync android && bash android/gradlew -p android testDebugUnitTest assembleDebug
```

Yo exijo los tres jobs verdes antes de integrar. Ver [`TESTING.md`](TESTING.md).

## Contradicciones resueltas

### “LLM real verificado” frente a “pendiente”

El modo LLM está implementado y hubo un smoke manual en el entorno del owner usando Qwen a través de LiteLLM local. La redacción correcta es:

> El flujo LLM fue validado en esa configuración concreta. Cada provider, modelo o gateway alternativo requiere su propia prueba de conectividad, calidad y límites.

No debe volver a describirse como “pendiente de toda verificación”, pero tampoco como garantía universal para cualquier proveedor.

### v0.1.0 frente a milestone v1.0

`v0.1.0` es una release histórica cerrada el 10 de julio. La integración v1 usó `1.0.0.dev0`; el
sufijo se retiró al preparar esta release. `1.0.0` identifica el paquete, la web y el cliente
Android desde el mismo commit.

### `.planning/ROADMAP.md` y `.planning/STATE.md`

Los artefactos de planificación acumularon casillas y métricas contradictorias durante la ejecución. El estado canónico se determina por código, pruebas, summaries de fase y este documento.

## Riesgos y límites vigentes

- Undo no cubre shell ni Git.
- El modo deterministic sigue siendo el default de la plantilla.
- El gateway LLM depende de infraestructura y secretos externos.
- El bridge LAN usa TLS local; certificados self-signed requieren confianza TOFU.
- Los permisos `0600` pueden no aplicarse en NTFS/FUSE.
- Los datos SQLite que requieren WAL deben vivir en un filesystem compatible.
- El APK se distribuye con firma debug del owner; no hay firma release ni canal de actualización.

## Gates de la release v1.0.0

| # | Gate | Estado |
|---|---|---|
| 1 | Retirar el sufijo `.dev0` desde el commit aprobado | Completo — package, web y Android en `1.0.0` |
| 2 | Changelog consolidado desde v0.1.0 | Completo — `CHANGELOG.md` |
| 3 | Artefactos reproducibles y firmados | Parcial — sdist/wheel reproducibles desde el tag con `uv.lock`; APK con firma **debug**, sin firma release |
| 4 | Cadena Python, web y Android desde un commit exacto | Completo — evidencia en `releases/WYSS_v1.0.0.md` |
| 5 | Smoke de daemon, bridge, LLM, Notion, intake y APK | Completo por fase, aprobado por el owner; sin repetición consolidada sobre este commit |
| 6 | Upgrade y rollback documentados | Completo — `UPGRADE.md` |
| 7 | Stubs operativos resueltos o marcados | Completo — el RPC `audit` dejó de ser stub (PR #5); `undo` limitado a `file.*` queda declarado |
| 8 | Checksums y evidencia de aceptación | Los checksums se generan al construir y se publican como asset de la release, no dentro del repositorio |

Pendiente de decisión del owner: firma release del APK y canal de distribución, tag y publicación.
