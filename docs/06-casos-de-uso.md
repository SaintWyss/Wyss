# Wyss — Casos de Uso

**Versión:** 0.1

---

## UC-001 — Consultar conocimiento personal

**Actor:** Owner
**Descripción:** El owner busca información perdida en sus terabytes de archivos.

1. Owner pregunta: "¿Dónde está el informe de seguridad de la pyme X?"
2. El orquestador consulta el índice semántico.
3. El índice devuelve ubicación exacta, contexto y resumen.
4. El orquestador responde con la ruta y un extracto.
5. Se registra la consulta.

**Confirmación:** No. **Riesgo:** Bajo.

---

## UC-002 — Delegar tarea a un agente especializado

**Actor:** Owner
**Descripción:** El owner pide una tarea de un dominio específico.

1. Owner instruye: "Organizame el material de estudio del parcial".
2. El orquestador clasifica el dominio (estudio) y delega al agente correspondiente.
3. El agente consulta su BC habilitada y genera un plan.
4. La política cognitiva evalúa el plan (nivel B → confirmación simple).
5. Owner confirma. El agente ejecuta y verifica.
6. El agente reporta al orquestador; se audita todo.

**Confirmación:** Simple. **Riesgo:** Medio.

---

## UC-003 — Habilitar una base de conocimiento

**Actor:** Owner
**Descripción:** El owner habilita el acceso de un agente (o trabajador) a una BC.

1. Owner: "Dale acceso al agente de finanzas a la BC de RAGcorp".
2. El orquestador valida la orden contra la política.
3. Se crea la habilitación con alcance y vigencia.
4. El agente queda con acceso de lectura a esa BC.
5. Se audita la habilitación.

**Confirmación:** Simple. **Riesgo:** Medio (acceso a información).

---

## UC-004 — Crear un nuevo agente

**Actor:** Owner
**Descripción:** Instanciar un agente del modelo base para un dominio nuevo.

1. Owner define: nombre, dominio, herramientas, BC habilitadas, presupuesto.
2. El orquestador instancia el agente a partir del modelo base.
3. El agente queda registrado y operativo.
4. Se audita la creación.

**Confirmación:** Simple. **Riesgo:** Medio.

---

## UC-005 — Rutina programada (resumen ejecutivo)

**Actor:** Orquestador (programado por el owner)
**Descripción:** Rutina semanal de estado general.

1. El orquestador se activa según calendario (ej.: lunes 8:00).
2. Consulta el estado de tareas, proyectos y agentes.
3. Detecta atrasos y propone replanificación.
4. Genera un resumen ejecutivo y lo entrega al owner.
5. Las replanificaciones propuestas esperan confirmación.

**Confirmación:** Solo para cambios. **Riesgo:** Bajo.

---

## UC-006 — Automatizar una tarea repetitiva

**Actor:** Owner
**Descripción:** Convertir un proceso manual en una rutina.

1. Owner describe el proceso repetitivo.
2. El orquestador propone una rutina (disparador, pasos, agente responsable).
3. Owner ajusta y aprueba.
4. La rutina queda activa y auditada en cada ejecución.

**Confirmación:** Fuerte al crearla; según nivel en cada ejecución. **Riesgo:** Medio.

---

## UC-007 — Seguimiento a trabajadores

**Actor:** Agente de seguimiento / Trabajador
**Descripción:** Un agente consulta el avance del equipo (patrón "Fama").

1. El agente contacta al trabajador por el canal definido.
2. El trabajador responde en texto o voz.
3. El agente extrae estado e intención y actualiza el tablero/estado de tareas.
4. Reporta novedades al orquestador.

**Confirmación:** No para lectura/actualización de estado. **Riesgo:** Bajo.

---

## UC-008 — Ingesta de una nueva fuente de conocimiento

**Actor:** Owner
**Descripción:** Incorporar una carpeta, proyecto o base externa.

1. Owner indica la fuente (ej.: carpeta de 2 TB, RAGcorp, proyecto de la beca).
2. El sistema escanea, extrae metadatos y contenido.
3. Indexa de forma incremental (solo lo nuevo o cambiado).
4. La BC queda disponible para habilitaciones.

**Confirmación:** Simple (volumen y sensibilidad). **Riesgo:** Medio.

---

## UC-009 — Rechazo de acción inválida

**Actor:** Owner o trabajador
**Descripción:** Se solicita una acción de nivel D.

1. Se solicita, por ejemplo, borrar una BC completa sin backup o exfiltrar credenciales.
2. La política cognitiva clasifica nivel D.
3. El sistema rechaza, explica el motivo y ofrece alternativa segura si existe.
4. El intento queda auditado.

**Confirmación:** No aplica. **Resultado:** Rechazo absoluto.

---

## UC-010 — Replicar Wyss para un cliente

**Actor:** Administrador técnico / Cliente
**Descripción:** Montar una nueva instancia del producto.

1. Se despliega el núcleo (modelo base) en el entorno del cliente.
2. El cliente (nuevo owner) conecta sus fuentes de conocimiento.
3. Se configuran agentes según sus áreas.
4. Se definen políticas, presupuestos y habilitaciones.
5. La instancia queda operativa, aislada de cualquier otra.

**Confirmación:** Proceso guiado. **Riesgo:** Medio.
