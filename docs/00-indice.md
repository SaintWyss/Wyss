# Wyss — Índice de Documentación Fundacional

> ⚠️ **Documentos históricos (fase 0 de diseño, 2026-06).** Describen el diseño original y se
> conservan como referencia; NO reflejan el estado actual. El estado real vive en
> `.planning/ROADMAP.md` / `.planning/STATE.md`; la arquitectura vigente en
> `docs/architecture/WYSS_TARGET_ARCHITECTURE.md`; el mapa del sistema en
> `docs/audit/WYSS_SYSTEM_MAP.md`.

**Proyecto:** Wyss — Sistema de asistencia operativa multi-agente, humano primero
**Autor:** Santiago Wyss
**Estado:** Fase 0 — Diseño (histórico)

> Wyss es el empleado que siempre necesitaste y nunca pudiste contratar.

---

## Fase 1 — Fundamentos
1. [Visión y Alcance](01-vision-y-alcance.md)
2. [Stakeholders y Roles](02-stakeholders-y-roles.md)
3. [Glosario](03-glosario.md)

## Fase 2 — Requerimientos
4. [Requerimientos Funcionales](04-requerimientos-funcionales.md)
5. [Requerimientos No Funcionales](05-requerimientos-no-funcionales.md)
6. [Casos de Uso](06-casos-de-uso.md)

## Fase 3 — Arquitectura
7. [Arquitectura Conceptual](07-arquitectura-conceptual.md)
8. [Diagrama de Componentes](08-diagrama-componentes.md)
9. [Modelo de Datos](09-modelo-de-datos.md)
10. [Arquitectura de Agentes](10-arquitectura-de-agentes.md)

## Fase 4 — Diseño
11. [Diagramas UML](11-diagramas-uml.md)
12. [Flujos de Trabajo](12-flujos-de-trabajo.md)
13. [Política de Acceso y Seguridad](13-politica-acceso-seguridad.md)
14. [Estrategia de Conocimiento e Indexación](14-estrategia-conocimiento-indexacion.md)

## Fase 5 — Producto
15. [Roadmap](15-roadmap.md)
16. [Criterios de Aceptación](16-criterios-de-aceptacion.md)
17. [Definición de Hecho](17-definicion-de-hecho.md)

---

## Herencia del proyecto Jarvis

Wyss hereda y absorbe del diseño de Jarvis PC v0.1:
- La **Política Cognitiva** (evaluación de finalidad, impacto, reversibilidad, riesgo).
- Los **niveles de acción A–D** con confirmación y rechazo absoluto.
- El principio de **contexto mínimo** hacia modelos externos.
- La **auditoría obligatoria** y los adaptadores desacoplados.

Y agrega lo que Jarvis no tenía:
- Jerarquía owner → orquestador → agentes especializados.
- Bases de conocimiento separadas con habilitaciones dinámicas.
- Índice semántico para recuperación instantánea sobre terabytes.
- Modelo base replicable como producto comercial.
