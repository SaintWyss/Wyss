# Wyss

## What This Is

Wyss es un sistema de asistencia operativa personal y empresarial basado en arquitectura multi-agente. Un orquestador central coordina agentes especializados con dominios propios y acceso controlado a bases de conocimiento. Los agentes no deciden por el owner — ejecutan lo que el owner ya decidió, de forma precisa, trazable y auditable.

**Filosofía rectora: humano primero, IA cuando corresponde.**

## Core Value

Santiago puede encontrar cualquier cosa en sus 2 TB en segundos, delegar tareas operativas a agentes especializados y mantener control total sobre lo que el sistema ejecuta — con auditoría de todo.

## Current Milestone: v1.0 Producto final — app móvil + asistente diario

**Goal:** Wyss deja de ser demo técnica: app Android instalable (APK) + web PC pulida + asistente diario real (rutinas programadas, Notion, memoria, intake automático).

**Target features:**
- APK Android — Capacitor envolviendo la SPA existente; pairing por QR; cert self-signed manejado en WebView; build Gradle local
- Scheduler / rutinas — tareas programadas que caen a la bandeja de confirmación (absorbe la vieja fase 9 sin multi-agente pleno)
- Notion adapter — leer/escribir páginas Notion como acciones con política
- Daily Assistant — resumen diario proactivo (agenda, finanzas Pellegrini, pendientes)
- Memory — memoria persistente del owner entre sesiones
- Intake n8n — canal de entrada automático (webhooks → bandeja)
- Web PC pulida — glow-up de la SPA para escritorio

**Key context:** v0.1.0 taggeado 2026-07-10 (bridge móvil smoke-aprobado en teléfono real; PRs 07-14 ejecutados fuera de GSD — ver `docs/architecture/WYSS_MASTER_ARCHITECTURE_AND_ROADMAP.md` y `docs/releases/WYSS_v0.1.0.md`). Modo LLM activo (qwen vía LiteLLM local). Fase 10 vieja (modo equipo) queda fuera de este corte.

## Requirements

### Validated

- [x] **ORCH-06**: El Model Gateway enruta a ≥ 2 proveedores configurables, registra tokens y costo por llamada — Validated in Phase 2: Gateway de Modelos
- [x] **ORCH-07**: El Context Minimizer filtra secretos y contexto innecesario antes de toda llamada externa — Validated in Phase 2: Gateway de Modelos (gap conocido CR-01 en 02-REVIEW.md: cobertura de patrones a ampliar antes de producción)

- [x] **KNOW-01**: El sistema indexa carpetas/archivos del owner con metadatos + FTS5 + vectores semánticos — Validated in Phases 3-4
- [x] **KNOW-03**: La re-indexación es incremental (hash + fecha — solo procesa cambios) — Validated in Phase 3
- [x] **KNOW-04**: Los secretos (.env, *.key, tokens) se detectan y excluyen antes de indexar — Validated in Phase 3 (SecretFilter 3 capas)
- [x] **KNOW-05**: Toda consulta queda auditada en SQLite — Validated in Phases 3-4
- [x] **KNOW-06**: Soporte para PDF, DOCX, TXT, MD, PY, JS, TS, CSV, XLSX, imágenes y video/audio (metadatos) — Validated in Phase 3
- [x] **ORCH-02**: Toda tarea modificadora genera un plan explícito y legible antes de ejecutarse — Validated in Phase 5 + v0.1.0 smoke físico
- [x] **ORCH-03**: La política cognitiva aplica los 4 niveles (A/B/C/D) — Validated in Phase 1 + PR-08 re-audit (13 deny rules)
- [x] **ORCH-04**: Nivel D se rechaza con explicación aunque el owner insista — Validated in Phase 1 (BUILTIN_DENY Final) + PR-08
- [x] **ORCH-05**: El orquestador corre como daemon persistente (Unix socket + JSON-RPC) — Validated in Phase 5 + v0.1.0
- [x] **AGENT-01**: Los agentes se crean por configuración, sin código nuevo — Validated in Phases 7-8 (Pellegrini config-only)
- [x] **AGENT-02**: Un agente sin permiso vigente sobre una BC no puede consultar esa BC — Validated in Phase 7 (scoped facades)
- [x] **AUDIT-01**: Toda acción relevante queda auditada — Validated in Phases 1-8 + PR-08

### Active

- [ ] **KNOW-02**: Una consulta en lenguaje natural resuelve en < 5 segundos sobre cualquier volumen (falta corpus real 2 TB indexado)
- [ ] **ORCH-01**: El orquestador clasifica intención en ≥ 9 categorías operativas (LLM mode recién activado; calibración pendiente)
- [ ] **AGENT-03**: Los agentes no se comunican horizontalmente — solo el orquestador divide y consolida
- [ ] **AGENT-04**: Cada agente persiste preferencias del owner en su dominio (MEMORY.md)
- [ ] **AGENT-05**: Belgrano (dominio estudio) opera con al menos 3 tareas reales de punta a punta
- [ ] **MULTI-01**: Múltiples agentes conviven sin interferencia bajo el orquestador
- [ ] **MULTI-02**: Routine Scheduler ejecuta rutinas programadas; acciones B/C quedan como propuestas, nunca auto-ejecutadas
- [ ] **MULTI-03**: Las 4 BC del owner (Personal, RAGcorp, Beca Ciber #1, Beca Ciber #2) están conectadas con habilitaciones selectivas

### Out of Scope

- Multiusuario / multiempresa (TEAM-01/02, modo equipo — vieja fase 10) — post-v1.0
- Modelos locales pesados — API-first
- Marketplace de agentes — futuro
- Integraciones de domótica — futuro
- ~~Interfaz móvil o por voz — v0.3+~~ **SUPERADO**: bridge móvil + voz shippearon en v0.1.0; APK es target de v1.0

## Context

- **Owner:** Santiago Wyss, Argentina
- **Volumen de datos:** ~2 TB de archivos personales en `~/Data/`
- **4 Bases de Conocimiento:** Personal, RAGcorp (empresa), Beca Ciberseguridad #1, Beca Ciberseguridad #2
- **Stack:** Python 3.12+, ChromaDB embebido, SQLite FTS5, TOML config, uv, pytest
- **Entorno:** CachyOS KDE, ruta `~/Data/10_Workspace/projects/wyss`
- **Primer agente operativo:** Belgrano (dominio: estudio)
- **Sistema de referencia:** hereda política cognitiva de Jarvis (niveles A–D, juicio antes de ejecución)
- **Arquitectura:** Hexagonal (Ports & Adapters) + SOLID + Plugin Pattern — nueva feature = nueva clase, nunca modificar código existente
- **Fase 0 completa:** 18 documentos fundacionales aprobados por el owner en `docs/`

## Constraints

- **Arquitectura**: Hexagonal con ports/adapters — el núcleo no importa infraestructura directamente
- **Seguridad cognitiva**: Nivel D es absoluto y no tiene excepciones en ningún path de código
- **Contexto**: Contexto mínimo hacia afuera — los modelos externos solo reciben lo necesario
- **Auditoría**: Nada relevante ocurre sin registro — es requisito transversal a todas las fases
- **Hardware**: Sin servidor dedicado en v0.1 — estrategia API-first
- **Extensibilidad**: Agregar extractor/proveedor/agente nunca modifica código existente

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python 3.12+ | Ecosistema IA maduro, type hints avanzados, uv para deps | — Pending |
| ChromaDB embebido | Sin servidor dedicado, mejor embedded local 2025, API simple | — Pending |
| SQLite FTS5 | Built-in, sin deps extra, búsqueda híbrida junto a vectores | — Pending |
| TOML config | Más legible que YAML, menos ambiguo, nativo Python 3.11+ | — Pending |
| Unix socket + JSON-RPC para daemon | Simple, sin dep HTTP, bajo overhead, seguro (solo procesos locales) | — Pending |
| uv para deps | Más rápido que pip/poetry, lockfile robusto, estándar 2025 | — Pending |
| Hexagonal + Plugin Pattern | Extensibilidad sin ruptura — nueva feature = nueva clase | — Pending |
| Hermes Agent (NousResearch) como cerebro de orquestación — modo híbrido | Evita construir orquestador NL/planes/rutinas de cero (solapa Fases 5 y 9). Hermes corre en container aislado, tools built-in deshabilitadas; toda acción real pasa por MCP server de Wyss → CognitivePolicyEngine + audit gatean cada call fail-closed. Hermes = adapter detrás de OrchestratorPort; reglas inviolables 1-9 se mantienen como garantía determinística. Decidido 2026-06-11 | — Pending |
| Ruteo de modelos en el desarrollo: **Claude = juicio, Codex = construcción, Gemini = acarreo** | Optimización de tokens Claude. Claude (orquestador/subagentes GSD): discusión, planning, verificación, security, decisiones D-XX — todos los gates de juicio. Codex high (`codex-gsd-exec`): ejecución de planes, debugging profundo, refactors grandes. Gemini (`gemini-gsd-exec`): acarreo — research crudo, docs mecánicos, lecturas masivas (ventana 1M); nunca juicio ni gates. Claude siempre re-verifica la cadena antes de commit (los wrappers no commitean). Decidido 2026-06-13 | — Active |

---

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-10 — Milestone v1.0 iniciado (producto final: APK + asistente diario); v0.1.0 taggeado; requirements re-auditados contra lo shippeado (fases 1-8 + PRs 07-14)*
