---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: Producto final — app móvil + asistente diario
status: active
last_updated: 2026-07-20T15:30:00-03:00
last_activity: 2026-07-20 -- Preparacion de release v1.0.0 (version unificada, changelog, upgrade, matriz verde)
progress:
  total_phases: 8
  completed_phases: 8
  total_plans: 32
  completed_plans: 32
  percent: 100
stopped_at: Release v1.0.0 preparada en rama release/v1.0.0; pendiente OK del owner para tag y firma release del APK
---

# Wyss — State

> Este archivo resume el milestone de planificación. El estado operativo canónico vive en `docs/RELEASE_STATUS.md` y tiene precedencia ante cualquier checklist histórico contradictorio.

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-10).

**Core value:** Encontrar cualquier cosa en 2 TB en segundos, delegar tareas a agentes con control total y auditar todo.

**Current focus:** integrar Wyss, Home Edge y ESP32 con Wyss como única autoridad.

## Current Position

- Phase: 16 — Home Authority Core
- Plan: incremental PR #3–#7, #10, #11 (todas mergeadas en `main`)
- Status: complete
- Last activity: 2026-07-20
- Evidence: `main` en `b93ca2b`, `.planning/phases/16-home-authority-core/16-REVIEW.md`
  (WR-01..WR-05 cerrados, matriz de invariantes toda "Cumple"), suite local
  `754 passed, 7 skipped` el 2026-07-20

## v1.0 Roadmap — Phases 9–16

Orden por dependencia. Regla inviolable: nada B/C se autoejecuta.

| Phase | Goal | Estado | Evidencia |
|---|---|---|---|
| 9. Routine Scheduler | Rutinas programadas → gate de política | Complete | `src/orchestrator/scheduler.py`, summaries de fase |
| 10. Notion Adapter | Leer/escribir Notion como acciones gateadas | Complete | `src/notion/`, summaries de fase |
| 11. Owner Memory | Memoria persistente y trust-tiered | Complete | `src/memory/`, summaries de fase |
| 12. Daily Assistant | Digest diario proactivo, solo lectura | Complete | `src/orchestrator/digest.py`, summaries de fase |
| 13. Intake n8n | Webhook externo → propuesta con floor B | Complete | daemon/web, summaries de fase |
| 14. Web PC Polish | Superficies de rutinas, digest y memoria | Complete | `web/`, summaries de fase |
| 15. Mobile APK | Capacitor, QR y pinning TOFU | Complete | `mobile/`, checkpoint físico aprobado |
| 16. Home Authority Core | Ports, RPC Unix idempotente, política y auditoría | Complete | `16-REVIEW.md`, PR #7/#10/#11 en `main` |

**Coverage:** 25/25 requirements mapeados a una fase del milestone.

## Decisions Log

| Date | Decision | Context |
|---|---|---|
| 2026-07-10 | Roadmap v1.0 con siete fases verticales y sin segundo camino de ejecución | Todo productor de Plan reutiliza dispatch o un Tool adapter gateado |
| 2026-07-10 | Memory debe preceder a Intake | Trust-tiering reduce laundering de prompt injection |
| 2026-07-10 | Viejas fases Multi-agente/Rutinas y Modo Equipo quedan superadas | Rutinas se absorbieron en Phase 9; Modo Equipo queda post-v1.0 |
| 2026-07-10 | APK como fase final propia | Requería spike de pinning y schema QR |
| 2026-07-11 | Phase 15 cerrada por checkpoint del owner | Instalación, QR, TOFU y carga del bridge aprobados en teléfono real |
| 2026-07-20 | Phase 16 cerrada | Cortes incrementales mergeados en `main`; review sin deuda y suite verde localmente |

_Decisiones v0.1: ver `phases/*-DECISIONS.md` y git history._

## Blockers

Ningún blocker para el alcance funcional del milestone.

Preparacion de release v1.0.0 completa (rama `release/v1.0.0`): versionado unificado en
`1.0.0`, changelog consolidado, `docs/UPGRADE.md`, `docs/releases/WYSS_v1.0.0.md` y matriz
Python/web/Android verde desde el mismo commit.

Pendiente de decision del owner:

- tag `v1.0.0` y publicacion;
- firma release del APK y canal de distribucion (hoy firma debug).

## Notes

- Modo LLM validado en el entorno del owner con Qwen vía LiteLLM local.
- El modo deterministic sigue siendo el default de la plantilla.
- `pyproject.toml` declara `1.0.0`; el tag y la publicación siguen sujetos al OK del owner.
- `.planning/ROADMAP.md` conserva detalle histórico y puede contener checkboxes desactualizados. Usar este State y `docs/RELEASE_STATUS.md` para estado vigente.
