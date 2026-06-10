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
├── docs/           Documentación fundacional (17 documentos)
├── src/
│   ├── core/       Núcleo: orquestador, planificador, política cognitiva
│   ├── orchestrator/  Intent Router, Task Planner, Confirmation Manager
│   ├── agents/     Modelo base y runtime de agentes
│   ├── knowledge/  Pipeline de ingesta, índice semántico, Retrieval Engine
│   ├── gateway/    Model Router, Context Minimizer, Cost Tracker
│   ├── execution/  Adaptadores (FileSystem, Shell, Git, etc.)
│   └── audit/      Audit Logger
├── tests/          Pruebas por módulo
├── config/         Configuración del sistema (sin secretos)
└── scripts/        Utilidades de desarrollo y despliegue
```

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
