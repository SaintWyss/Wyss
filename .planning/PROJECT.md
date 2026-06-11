# Wyss

## What This Is

Wyss es un sistema de asistencia operativa personal y empresarial basado en arquitectura multi-agente. Un orquestador central coordina agentes especializados con dominios propios y acceso controlado a bases de conocimiento. Los agentes no deciden por el owner — ejecutan lo que el owner ya decidió, de forma precisa, trazable y auditable.

**Filosofía rectora: humano primero, IA cuando corresponde.**

## Core Value

Santiago puede encontrar cualquier cosa en sus 2 TB en segundos, delegar tareas operativas a agentes especializados y mantener control total sobre lo que el sistema ejecuta — con auditoría de todo.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] **KNOW-01**: El sistema indexa carpetas/archivos del owner con metadatos + FTS5 + vectores semánticos
- [ ] **KNOW-02**: Una consulta en lenguaje natural resuelve en < 5 segundos sobre cualquier volumen
- [ ] **KNOW-03**: La re-indexación es incremental (hash + fecha — solo procesa cambios)
- [ ] **KNOW-04**: Los secretos (.env, *.key, tokens) se detectan y excluyen antes de indexar
- [ ] **KNOW-05**: Toda consulta queda auditada en SQLite
- [ ] **KNOW-06**: Soporte para PDF, DOCX, TXT, MD, PY, JS, TS, CSV, XLSX, imágenes y video/audio (metadatos v0.1)
- [ ] **ORCH-01**: El orquestador clasifica intención en ≥ 9 categorías operativas
- [ ] **ORCH-02**: Toda tarea modificadora genera un plan explícito y legible antes de ejecutarse
- [ ] **ORCH-03**: La política cognitiva aplica los 4 niveles (A ejecuta / B confirma simple / C confirma fuerte / D rechaza absoluto)
- [ ] **ORCH-04**: Nivel D se rechaza con explicación aunque el owner insista — sin excepciones en código
- [ ] **ORCH-05**: El orquestador corre como daemon persistente (Unix socket + JSON-RPC)
- [ ] **ORCH-06**: El Model Gateway enruta a ≥ 2 proveedores configurables, registra tokens y costo por llamada
- [ ] **ORCH-07**: El Context Minimizer filtra secretos y contexto innecesario antes de toda llamada externa
- [ ] **AGENT-01**: Los agentes se crean por configuración a partir del modelo base, sin código nuevo
- [ ] **AGENT-02**: Un agente sin permiso vigente sobre una BC no puede consultar esa BC
- [ ] **AGENT-03**: Los agentes no se comunican horizontalmente — solo el orquestador divide y consolida
- [ ] **AGENT-04**: Cada agente persiste preferencias del owner en su dominio (MEMORY.md)
- [ ] **AGENT-05**: Belgrano (dominio estudio) opera con al menos 3 tareas reales de punta a punta
- [ ] **MULTI-01**: Múltiples agentes conviven sin interferencia bajo el orquestador
- [ ] **MULTI-02**: Routine Scheduler ejecuta rutinas programadas; acciones B/C quedan como propuestas, nunca auto-ejecutadas
- [ ] **MULTI-03**: Las 4 BC del owner (Personal, RAGcorp, Beca Ciber #1, Beca Ciber #2) están conectadas con habilitaciones selectivas
- [ ] **TEAM-01**: Trabajadores interactúan con agentes asignados sin acceso al núcleo
- [ ] **TEAM-02**: Intento de exceder rol por trabajador escala al owner (probado explícitamente)
- [ ] **AUDIT-01**: Toda acción relevante queda auditada: actor, instrucción, plan, decisión de política, confirmación, resultado, costo

### Out of Scope

- Multiusuario / multiempresa — v1.0+
- Interfaz móvil o por voz — v0.3+
- Modelos locales pesados — API-first en v0.1
- Marketplace de agentes — futuro
- Integraciones de domótica — futuro

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
*Last updated: 2026-06-10 after initialization*
