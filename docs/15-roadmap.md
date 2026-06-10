# Wyss — Roadmap

**Versión:** 0.1

---

## Fase 0 — Diseño (actual)

- Documentos fundacionales (este conjunto).
- Validación de la arquitectura conceptual.
- Definición de los primeros agentes y sus dominios.
- Decisiones técnicas base (lenguaje, almacenamiento, gateway).

**Sale de esta fase:** diseño completo aprobado por el owner. **Sin código.**

## Fase 1 — El Índice (primer valor real)

- Pipeline de ingesta sobre la BC Personal (los 2 TB).
- Índice híbrido: metadatos + FTS5 + vectores.
- Consulta por CLI: encontrar cualquier cosa en segundos.
- Auditoría básica de consultas.

**Criterio de éxito:** "le pregunto dónde está algo que no encuentro hace meses y me lo da al instante".

## Fase 2 — El Orquestador

- Núcleo como proceso persistente.
- Intent Router + Task Planner.
- Política cognitiva con niveles A–D.
- Confirmaciones y rechazo absoluto funcionando.
- Model Gateway con al menos dos proveedores (económico + fuerte).

## Fase 3 — El Primer Agente

- Modelo base de agente (plantilla instanciable).
- Primer agente especializado operativo en un dominio real del owner.
- Permission Manager: habilitaciones agente ↔ BC.
- Memoria operativa del agente.

## Fase 4 — Multi-agente y Rutinas

- Varios agentes conviviendo bajo el orquestador.
- Routine Scheduler: rutinas programadas (resumen semanal, seguimientos).
- División y consolidación de tareas multi-dominio.
- Conexión de las BC restantes (RAGcorp, proyectos de la beca).

## Fase 5 — Modo Equipo

- Trabajadores interactuando con agentes asignados.
- Patrón de seguimiento (estado de tareas por mensajería, texto/voz).
- Auditoría con vistas para el owner.

## Fase 6 — Producto Replicable

- Instalación de instancia nueva por configuración.
- Onboarding guiado: conectar fuentes, crear agentes, definir políticas.
- Aislamiento total entre instancias.
- Documentación de cliente.
- Primer cliente real (pyme o profesional).

## Fase 7 — Expansión

- Interfaz móvil / voz.
- Embeddings y modelos locales opcionales.
- Marketplace o catálogo de agentes preconfigurados por industria.
- Integraciones adicionales según demanda de clientes.

---

## Regla del roadmap

Cada fase entrega **valor usable por el owner** antes de pasar a la siguiente. No se avanza con fases a medias: lo define el documento de Criterios de Aceptación.
