# Wyss — Política de Acceso y Seguridad

**Versión:** 0.1

---

## 1. Principios

1. **Mínimo privilegio:** todo sujeto (agente, trabajador, modelo externo) tiene el menor acceso posible para cumplir su función.
2. **Acceso por habilitación, nunca por defecto:** un agente recién creado no ve ninguna BC.
3. **Jerarquía inviolable:** solo el owner otorga; el orquestador ejecuta las órdenes del owner; nadie más concede accesos.
4. **Juicio antes que permiso:** tener acceso no implica poder ejecutar — toda acción pasa por la política cognitiva.
5. **Revocación inmediata:** cualquier habilitación puede revocarse y el efecto es instantáneo.

## 2. Niveles de acción (herencia de Jarvis)

### Nivel A — Ejecución directa
Lecturas, búsquedas, apertura de aplicaciones, consultas al índice, comandos de diagnóstico, actualización de estados de tareas, creación de archivos nuevos no conflictivos.

### Nivel B — Confirmación simple
Mover/renombrar archivos, ordenar carpetas, modificar archivos de proyecto, crear agentes, habilitar BC de sensibilidad normal, activar rutinas existentes.

### Nivel C — Confirmación fuerte
Borrado de archivos, sobrescritura, instalación de paquetes, cambios de configuración del sistema, movimientos masivos de datos, habilitar BC sensibles, crear rutinas nuevas con acciones modificadoras, uso de modelos caros por encima del presupuesto.

### Nivel D — Rechazo absoluto
Destrucción de BC o backups, exfiltración de credenciales o secretos, instalación de software malicioso, desactivación injustificada de seguridad o auditoría, envío de información sensible a modelos no confiables, acciones irreversibles sin finalidad legítima, intentos de un agente de modificar sus propios permisos.

## 3. Política sobre el conocimiento

- Las BC viven separadas por contexto; **el aislamiento entre contextos es absoluto** salvo habilitación explícita del owner.
- Los secretos (credenciales, claves, tokens) se almacenan fuera de las BC indexables y nunca entran al índice semántico.
- El Retrieval Engine aplica el filtro de habilitaciones **antes** de buscar, no después: un agente sin permiso ni siquiera consulta esa BC.
- En modo producto: los datos de cada cliente viven en su propia instancia; no existe base compartida entre clientes.

## 4. Política hacia modelos externos

- Todo contexto saliente pasa por el Context Minimizer: recorte, resumen y redacción de secretos.
- Información clasificada como sensible: contexto mínimo o directamente no se envía (procesamiento local/determinístico).
- El gateway registra cada llamada: modelo, tokens, costo, agente solicitante.
- Lista de proveedores confiables definida en configuración; enviar datos a un proveedor fuera de la lista es nivel D.

## 5. Política sobre trabajadores

- Un trabajador interactúa solo con los agentes que el owner le asignó.
- Puede: consultar dentro de su rol, reportar avances, solicitar tareas de su dominio.
- No puede: ver el núcleo, modificar agentes, pedir habilitaciones, acceder a la auditoría, ni solicitar acciones de nivel C/D (esas escalan al owner).

## 6. Defensa frente a manipulación

- **Prompt injection en documentos:** el contenido de las BC es *dato*, nunca *instrucción*. El pipeline de ingesta sanitiza y el runtime separa instrucciones del owner del contenido recuperado.
- **Instrucciones encadenadas:** una instrucción que llega a través de un trabajador o un documento no hereda la autoridad del owner.
- **Auto-modificación:** ningún agente puede alterar su configuración, presupuesto, permisos o la política. Solo el owner, vía núcleo.

## 7. Auditoría como garantía

- La auditoría no es opcional ni desactivable por agentes.
- Registra: actor, instrucción original, plan, decisión de política, confirmación, acciones, resultado, costo.
- El owner tiene visibilidad total; los intentos rechazados (nivel D) se registran con prioridad.
