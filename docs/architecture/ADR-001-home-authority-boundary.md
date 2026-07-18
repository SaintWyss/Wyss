# ADR-001 — Yo mantengo la autoridad Home dentro de Wyss

**Estado:** aceptada  
**Fecha:** 2026-07-18

## Contexto

Yo necesito que PC, Android y ESP32 compartan conversación, confirmaciones y estado doméstico sin
crear un segundo orquestador. Home Edge debe poder cambiar de transporte o proveedor sin conocer
el executor, las bases de datos ni frameworks internos de Wyss.

## Decisión

Yo defino primero `HomePort`, `ProjectionPort`, `ClientEventPort`, `MediaPort`, `CalendarPort`,
`ReminderPort`, `TimerPort`, `NotificationPort`, `SpeechPort` y `CameraPort` dentro de `core`.
Los tipos cruzados son objetos inmutables de standard library y expresan correlación,
idempotencia, revisión por agregado, orden global y estado verificado.

Wyss conserva identidad, conversación, planes, política A–D, confirmación, ejecución y auditoría.
Home Edge sólo adapta capacidades y distribuye proyecciones; firmware, web y Android sólo consumen
la proyección y envían intenciones o respuestas. Ningún adapter puede importar internals del
executor ni abrir las bases de datos de Wyss.

## Consecuencias

- Yo mantengo una única fuente de verdad y puedo reemplazar HTTP, WSS o IPC sin tocar dominio.
- Yo mantengo el socket owner `0600` y asigno el socket Home `0660` a una cuenta Edge de UID
  separado, verifico `SO_PEERCRED` y no abro otro puerto de red entre Edge y Wyss.
- Yo persisto claims idempotentes antes de procesar intenciones o respuestas de planes; un estado
  ambiguo cierra sin repetir I/O.
- Yo debo mapear explícitamente los DTO del protocolo en los composition roots.
- Yo acepto más contratos pequeños a cambio de pruebas aisladas y fronteras auditables.
- Yo mantengo el camino rápido de luces limitado a acciones A allowlisted; el resultado verificado
  vuelve a Wyss como evento y prevalece sobre el optimista.

## Alternativas descartadas

- Yo descarto que Home Edge llame al executor o SQLite porque crea un bypass de política.
- Yo descarto guardar OAuth o credenciales de proveedores en firmware porque amplía el impacto de
  una extracción física.
- Yo descarto un segundo historial en ESP32 porque rompe convergencia y recuperabilidad.

## Rollback

Mientras no existan adapters productivos, yo puedo retirar estos ports con un revert. Después de
publicar Protocol v2, el rollback operativo es activar temporalmente el feature flag v1, nunca
transferir autoridad a Home Edge.
