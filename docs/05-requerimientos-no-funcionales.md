# Wyss — Requerimientos No Funcionales

**Versión:** 0.1

---

**RNF-001 — Seguridad cognitiva.** Ninguna acción modificadora se ejecuta sin pasar por evaluación de intención, impacto, reversibilidad y riesgo.

**RNF-002 — Privacidad.** El conocimiento del owner nunca sale del sistema completo: a los modelos externos solo se envía contexto mínimo, filtrado y sin secretos. Los datos de un cliente jamás se mezclan con los de otro.

**RNF-003 — Trazabilidad.** Toda acción relevante es auditable: quién la pidió, qué se planificó, qué se ejecutó, qué resultó.

**RNF-004 — Modularidad.** Cada integración (herramienta, modelo, fuente de conocimiento) se implementa como adaptador desacoplado del núcleo.

**RNF-005 — Replicabilidad.** Una nueva instancia de Wyss para un cliente debe poder montarse por configuración, sin modificar código del núcleo.

**RNF-006 — Costo controlado.** El sistema prefiere lógica determinística o modelos económicos cuando alcanzan; los modelos fuertes se usan solo cuando la tarea lo justifica. Debe existir control de presupuesto por agente y por período.

**RNF-007 — Escalabilidad de conocimiento.** El índice debe soportar volúmenes del orden de terabytes de archivos sin degradar la velocidad de recuperación (indexación incremental, no re-procesar todo).

**RNF-008 — Rendimiento de recuperación.** Una consulta sobre la BC debe resolverse en segundos, independientemente del volumen total indexado.

**RNF-009 — Robustez.** Toda acción modificadora debe verificar su resultado y manejar errores sin dejar el entorno en estado inconsistente.

**RNF-010 — Reversibilidad.** Cuando sea posible, las acciones modificadoras deben tener backup, papelera o plan de rollback.

**RNF-011 — Independencia de proveedor.** El cambio de proveedor de IA no debe requerir cambios en el núcleo (gateway con alias de modelos).

**RNF-012 — Operación sin hardware dedicado.** La v0.1 debe funcionar en una computadora personal estándar, usando APIs externas para los modelos pesados. La arquitectura debe permitir migrar a modelos locales en el futuro sin rediseño.

**RNF-013 — Observabilidad.** El sistema debe exponer logs, métricas de uso y costos, y reportes de ejecución.

**RNF-014 — Disponibilidad del núcleo.** El orquestador debe poder correr como proceso persistente (daemon) para rutinas programadas.

**RNF-015 — Usabilidad.** El owner no necesita conocimientos técnicos para operar el sistema una vez configurado; la complejidad vive en el diseño, no en el uso.
