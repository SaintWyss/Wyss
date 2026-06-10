# Wyss — Requerimientos Funcionales

**Versión:** 0.1

---

## Grupo 1 — Interacción

**RF-001 — Comandos en lenguaje natural.** El owner debe poder dar instrucciones al orquestador en lenguaje natural (CLI/chat en v0.1).

**RF-002 — Clasificación de intención.** El orquestador debe clasificar cada instrucción en una categoría operativa (consulta de conocimiento, tarea operativa, automatización, administración de agentes, etc.).

**RF-003 — Aclaración de ambigüedad.** Ante instrucciones ambiguas, el sistema debe pedir aclaración en lugar de asumir.

## Grupo 2 — Orquestación

**RF-004 — Generación de plan.** Toda tarea modificadora debe traducirse en un plan explícito y legible antes de ejecutarse.

**RF-005 — Delegación a agentes.** El orquestador debe seleccionar el agente especializado adecuado según el dominio de la tarea.

**RF-006 — Rutinas programadas.** El orquestador debe poder ejecutar rutinas periódicas definidas por el owner (resúmenes, replanificación, seguimientos).

**RF-007 — Selección de modelo.** Para cada subtarea con IA, el sistema debe elegir el modelo según costo, complejidad, riesgo y privacidad (lógica local → modelo económico → modelo fuerte).

## Grupo 3 — Agentes

**RF-008 — Instanciación de agentes.** El owner debe poder crear agentes a partir del modelo base, definiendo identidad, dominio, herramientas y contexto habilitado.

**RF-009 — Aislamiento de dominio.** Un agente solo debe poder operar dentro de su dominio y con las BC habilitadas.

**RF-010 — Reporte al orquestador.** Todo agente debe reportar resultados, estado y errores al orquestador.

**RF-011 — Prohibición de dirección horizontal.** Ningún agente debe poder dar instrucciones a otro agente; solo el orquestador delega.

## Grupo 4 — Conocimiento

**RF-012 — Ingesta de fuentes.** El sistema debe poder incorporar fuentes de conocimiento: carpetas locales, documentos, bases existentes (RAGcorp, proyectos externos).

**RF-013 — Indexación.** Toda fuente ingresada debe quedar indexada (metadatos + texto + semántica) para recuperación inmediata.

**RF-014 — Recuperación instantánea.** Ante una consulta, el sistema debe localizar la información relevante sin recorrer los archivos uno por uno.

**RF-015 — Habilitación dinámica de BC.** El orquestador debe poder habilitar o revocar el acceso de cada agente/trabajador a cada BC, por orden del owner.

## Grupo 5 — Ejecución

**RF-016 — Ejecución local.** Los agentes deben poder ejecutar acciones sobre el entorno: archivos, aplicaciones, repositorios, comandos permitidos.

**RF-017 — Verificación posterior.** Toda acción modificadora debe verificarse después de ejecutada (conteos, hashes, estados).

## Grupo 6 — Seguridad cognitiva

**RF-018 — Evaluación de política.** Todo plan debe pasar por la política cognitiva antes de ejecutarse.

**RF-019 — Confirmación por nivel.** Las acciones de nivel B y C deben requerir confirmación del owner (simple o fuerte).

**RF-020 — Rechazo absoluto.** Las acciones de nivel D deben rechazarse con explicación, aunque el owner insista.

**RF-021 — Contexto mínimo.** El sistema debe filtrar y minimizar el contexto enviado a modelos externos, ocultando secretos.

## Grupo 7 — Auditoría y administración

**RF-022 — Auditoría completa.** Toda acción, decisión, confirmación y error debe registrarse de forma trazable.

**RF-023 — Consulta de auditoría.** El owner debe poder consultar el historial de acciones del sistema.

**RF-024 — Replicación de instancia.** El sistema debe poder replicarse para un nuevo contexto/cliente conectando sus BC y configurando sus agentes, sin reescribir el núcleo.
