# Wyss

> El empleado que siempre necesitaste y nunca pudiste contratar.

Sistema de asistencia operativa multi-agente, humano primero.

**Autor:** Santiago Wyss  
**Estado:** Fase 0 — Diseño  
**Versión:** 0.1

---

## Qué es Wyss

Wyss es una plataforma de asistencia operativa personal y empresarial basada en arquitectura multi-agente. Centraliza el conocimiento del owner, automatiza tareas operativas y coordina agentes especializados — todo con jerarquía estricta, política cognitiva y auditoría obligatoria.

No es un chatbot. No es un wrapper de IA. Es un operador con criterio.

## Arquitectura

```
OWNER
  └─► NÚCLEO (Orquestador · Planificador · Política Cognitiva)
        ├─► AGENTES ESPECIALIZADOS (instancias del modelo base)
        ├─► CAPA DE CONOCIMIENTO (BC indexadas · Retrieval Engine)
        ├─► GATEWAY DE MODELOS (contexto mínimo · control de costos)
        └─► CAPA DE EJECUCIÓN (adaptadores desacoplados)
```

## Niveles de acción

| Nivel | Tipo | Comportamiento |
|-------|------|----------------|
| A | Lectura / diagnóstico | Ejecución directa |
| B | Modificación normal | Confirmación simple del owner |
| C | Alto impacto | Confirmación fuerte del owner |
| D | Destructivo / inválido | Rechazo absoluto |

## Roadmap

| Fase | Entregable |
|------|-----------|
| 0 | Diseño completo (actual) |
| 1 | El Índice — BC Personal indexada, consulta en segundos |
| 2 | El Orquestador — núcleo funcional con política A–D |
| 3 | El Primer Agente — modelo base instanciable |
| 4 | Multi-agente + Rutinas |
| 5 | Modo Equipo (trabajadores) |
| 6 | Producto Replicable |
| 7 | Expansión (móvil, modelos locales, marketplace) |

## Estructura del repositorio

```
wyss/
├── docs/              Documentación fundacional (18 documentos)
├── src/
│   ├── core/          Núcleo hexagonal puro (stdlib only, mypy strict)
│   │   ├── domain/    Entidades frozen (Task, Plan, Action, RiskLevel, AuditEvent…) — sin infra
│   │   ├── ports/     Los 14 contratos (13 typing.Protocol + AgentBase ABC) — D-11
│   │   └── policy/    CognitivePolicyEngine puro + denylist built-in no removible
│   ├── orchestrator/  Intent Router, Task Planner, Confirmation Manager
│   ├── agents/        Modelo base y runtime de agentes
│   ├── knowledge/     Pipeline de ingesta, índice semántico, Retrieval Engine
│   ├── gateway/       Model Router, Context Minimizer, Cost Tracker
│   ├── execution/     Adaptadores (FileSystem, Shell, Git, etc.)
│   ├── audit/         Audit Logger (SQLite append-only, DB separada)
│   └── bootstrap/     Composition root (DI manual) + frontera Pydantic→dominio
├── tests/             Pruebas por módulo
├── config/            Configuración del sistema en TOML (sin secretos)
└── scripts/           Utilidades de desarrollo y despliegue
```

Las carpetas `core/domain/`, `core/ports/`, `core/policy/` y `bootstrap/` son nuevas
de la Fase 1 (Fundaciones):

- **`core/domain/`** — entidades de dominio como `frozen` dataclasses, stdlib only. Todo lo demás las importa; ellas no importan nada del sistema.
- **`core/ports/`** — los 14 contratos hexagonales (Protocols + la ABC `AgentBase`). Se definen y commitean antes que cualquier implementación (D-11); los módulos vecinos importan de aquí, nunca de las impls.
- **`core/policy/`** — el `CognitivePolicyEngine` puro (`Plan -> PolicyDecision`). La denylist de nivel D vive aquí en código como invariante `Final`; la config solo puede AGREGAR reglas, jamás quitarlas.
- **`bootstrap/`** — composition root con DI manual (D-10) y la única frontera donde vive Pydantic: valida `config.toml` al boot (fail-fast) y entrega frozen dataclasses al núcleo. Pydantic nunca entra a `core/`.

### Verificación

El proyecto se instala con `uv` (gestor de deps + venv) y usa paquetes top-level genéricos
(`core`, `audit`, `bootstrap`…) bajo un venv dedicado — tradeoff aceptado en D-01 a cambio
de imports flat (`from core.ports import ...`). La cadena de verificación completa, que todo
plan posterior debe dejar verde, es:

```bash
uv sync                                 # instala deps + proyecto editable
uv run pytest && uv run mypy && uv run ruff check src tests && uv run lint-imports
```

`mypy` corre en modo strict sobre `src` y `tests`; `import-linter` (`lint-imports`) verifica
los contratos hexagonales (núcleo puro stdlib-only, capas independientes entre sí).

## Principios

1. **Jerarquía estricta:** owner → orquestador → agentes → herramientas.
2. **Juicio antes que ejecución:** toda acción pasa por la política cognitiva.
3. **Contexto mínimo hacia afuera:** los modelos externos reciben solo lo necesario.
4. **Auditoría transversal:** nada relevante ocurre sin registro.
5. **Núcleo replicable:** la lógica es genérica; la personalización vive en configuración.

## Herencia de Jarvis

Wyss absorbe de Jarvis PC v0.1:
- Política Cognitiva (evaluación de finalidad, impacto, reversibilidad, riesgo).
- Niveles de acción A–D con confirmación y rechazo absoluto.
- Contexto mínimo hacia modelos externos.
- Auditoría obligatoria y adaptadores desacoplados.

---

*Filosofía rectora: humano primero, IA cuando corresponde.*
