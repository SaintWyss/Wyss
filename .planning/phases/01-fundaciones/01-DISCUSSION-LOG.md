# Phase 1: Fundaciones — Discussion Log

**Date:** 2026-06-10
**Mode:** Spec-driven (sin discusión por áreas)

## Cómo se capturó el contexto

Se presentaron 4 áreas grises (Denylist nivel D · Calibración A/B/C · Esquema de auditoría · Estructura de paquete). El owner interrumpió la selección y entregó la spec de implementación completa (`docs/18-prompt-implementacion.md`) como respuesta integral.

## Resolución de las áreas grises

| Área gris | Resolución | Fuente |
|---|---|---|
| Estructura de paquete | Layout del prompt: `src/core/ports/` + módulos por capa; stubs se conservan | Spec §Estructura |
| Esquema de auditoría | SQLite separado de datos de usuario; campos mínimos definidos | Spec §Decisiones fijas + §Fase 2 |
| Calibración A/B/C | Semántica exacta definida (A directo, B [s/N], C "CONFIRMAR"); umbrales de agregación a discreción de Claude | Spec §Fase 2 |
| Denylist nivel D | No enumerada por el owner — discreción de Claude con defaults conservadores, denylist como datos configurables | Inferido (regla #6 + research) |

## Deferred

- pdfplumber vs pymupdf → Fase 3 (benchmark)
- Watchdog → Fase 3
- agents.toml → Fase 7
