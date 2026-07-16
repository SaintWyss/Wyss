# Manual normalizado de Wyss

Yo diseñé este manual como una ruta de confianza progresiva. Antes de usar lenguaje natural para modificar archivos o ejecutar acciones, la persona debe comprender qué decide el LLM, qué decide la política y qué confirma el owner.

## Capítulos

| Capítulo | Resultado esperado |
|---|---|
| 01 | entender Wyss y levantarlo en modo seguro |
| 02 | usar CLI, web, APK, rutinas, memoria, digest, Notion e intake |
| 03 | comprender arquitectura, límites y decisiones |
| 04 | recorrer las vistas UML |
| 05 | configurar providers, datos y contratos |
| 06 | conocer política A–D, pruebas y controles |
| 07 | operar, respaldar, recuperar y responder a incidentes |
| 08 | conocer estado, deuda, roadmap y términos |

## Estados

- **Implementado:** código conectado al composition root.
- **Probado:** suite automatizada o smoke reproducible.
- **Validado físicamente:** comprobado en PC/teléfono real.
- **Opt-in:** existe, pero no se activa sin configuración explícita.
- **Parcial:** falta cobertura o integración.
- **Histórico:** describe una release anterior.

## Documentación avanzada

- `docs/OPERATOR.md`;
- `docs/CONFIGURATION.md`;
- `docs/TESTING.md`;
- `docs/RELEASE_STATUS.md`;
- `docs/security/`;
- `docs/architecture/`;
- `docs/audit/`;
- `docs/releases/`;
- `.planning/`.

## Regla de mantenimiento

Cuando cambia una acción, nivel de riesgo, proveedor, flujo de confirmación, DB, API, UI o dispositivo, yo actualizo el capítulo canónico, la prueba y el documento avanzado relacionado en el mismo pull request.