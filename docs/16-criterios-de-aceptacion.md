# Wyss — Criterios de Aceptación por Fase

**Versión:** 0.1

---

## Fase 0 — Diseño

Aceptada cuando:
- Los 17 documentos fundacionales existen y están aprobados por el owner.
- La arquitectura responde todos los casos de uso definidos.
- Las decisiones técnicas base están tomadas y justificadas por escrito.

## Fase 1 — El Índice

Aceptada cuando:
- La BC Personal completa está indexada (escaneo inicial terminado).
- Una consulta cualquiera se resuelve en menos de 5 segundos.
- La re-indexación es incremental: un cambio de 10 archivos no re-procesa 2 TB.
- La respuesta incluye ubicación exacta, extracto y fuente.
- Toda consulta queda auditada.
- Los secretos no aparecen en el índice (verificado con prueba dirigida).

## Fase 2 — El Orquestador

Aceptada cuando:
- Clasifica al menos 5 tipos de intención correctamente.
- Genera planes legibles antes de cualquier acción modificadora.
- Aplica los 4 niveles: ejecuta A directo, pide confirmación en B y C, rechaza D.
- Rechaza al menos una clase de acción destructiva con explicación (probado).
- El gateway enruta a 2+ proveedores y registra costo por llamada.
- Corre como proceso persistente sin intervención.

## Fase 3 — El Primer Agente

Aceptada cuando:
- El agente se crea por configuración a partir del modelo base, sin código nuevo.
- Solo accede a las BC habilitadas (probado con intento de acceso no habilitado → bloqueado y auditado).
- Completa de punta a punta al menos 3 tareas reales de su dominio.
- Reporta resultados al orquestador y todo queda auditado.
- Respeta su presupuesto de modelos.

## Fase 4 — Multi-agente y Rutinas

Aceptada cuando:
- Dos o más agentes operan en simultáneo sin interferirse.
- Una tarea multi-dominio se divide, ejecuta y consolida correctamente.
- Una rutina semanal corre 4 semanas seguidas sin intervención y entrega su resumen.
- Las acciones B/C generadas por rutinas quedan como propuestas, nunca se auto-ejecutan.
- Las 4 BC del owner están conectadas y habilitadas selectivamente.

## Fase 5 — Modo Equipo

Aceptada cuando:
- Un trabajador real interactúa con su agente asignado sin acceso al núcleo.
- El estado de tareas se actualiza a partir de reportes en texto o voz.
- Un intento del trabajador de exceder su rol escala al owner (probado).

## Fase 6 — Producto Replicable

Aceptada cuando:
- Una instancia nueva se monta solo con configuración, en menos de un día de trabajo.
- Las instancias están totalmente aisladas (probado).
- Un cliente externo completa el onboarding y opera el sistema sin asistencia diaria.

---

## Criterio transversal (todas las fases)

Ninguna fase se acepta si:
- Existe una acción modificadora sin auditoría.
- Existe una vía para que un agente acceda a una BC sin habilitación.
- Existe una vía para ejecutar nivel D.
- El sistema envió secretos a un modelo externo durante las pruebas.
