# Wyss — Flujos de Trabajo Principales

**Versión:** 0.1

---

## Flujo 1 — Consulta de conocimiento (el más frecuente)

```text
Owner pregunta
  → Intent Router: knowledge_query
  → Retrieval Engine: búsqueda híbrida (metadatos + FTS + semántica)
  → Filtro de habilitaciones (si pregunta un agente/trabajador)
  → Respuesta con fuente, ubicación exacta y extracto
  → Auditoría
```

**Meta de rendimiento:** segundos, sin importar el volumen indexado.

## Flujo 2 — Tarea operativa delegada

```text
Owner instruye
  → Clasificación de intención y dominio
  → Orquestador delega al agente del dominio
  → Agente consulta su BC habilitada y arma plan
  → Policy Engine: nivel A/B/C/D
      A → ejecuta directo
      B → confirmación simple del owner
      C → confirmación fuerte del owner
      D → rechazo explicado
  → Ejecución vía adaptadores
  → Verificación posterior (conteos, estados, hashes)
  → Reporte al orquestador → respuesta al owner
  → Auditoría de todo el flujo
```

## Flujo 3 — Rutina programada

```text
Scheduler dispara (cron/evento)
  → Orquestador carga definición de la rutina
  → Ejecuta pasos (consultas, análisis, generación de resumen)
  → Acciones de nivel A: ejecuta
  → Acciones B/C detectadas: quedan como propuestas pendientes
  → Entrega resultado al owner (resumen + propuestas a confirmar)
  → Auditoría
```

Ejemplo: lunes 8:00 — estado de proyectos, atrasos detectados, replanificación propuesta.

## Flujo 4 — Ingesta de conocimiento

```text
Owner registra fuente (carpeta, base externa, documento)
  → Scanner releva archivos y metadatos
  → Diff incremental: solo lo nuevo/modificado
  → Extracción de contenido por tipo (texto, docs, código, media)
  → Chunking + resumen + embedding + entrada FTS
  → Alta en el Índice Semántico
  → BC disponible para habilitaciones
  → Auditoría
```

**Regla:** la ingesta nunca re-procesa todo; es incremental por diseño (clave para volúmenes de TB).

## Flujo 5 — Habilitación de acceso

```text
Owner ordena habilitar BC a un agente/trabajador
  → Permission Manager valida contra política
  → Crea Permission (alcance, nivel, vigencia)
  → Efecto inmediato en Retrieval Engine
  → Auditoría
Revocación: misma cadena, efecto inmediato.
```

## Flujo 6 — Seguimiento de equipo (patrón Fama)

```text
Agente de seguimiento contacta al trabajador (canal definido)
  → Trabajador responde (texto/voz)
  → Agente extrae estado e intención
  → Actualiza estado de tareas (nivel A: actualización de estado)
  → Detecta bloqueos → reporta al orquestador
  → Orquestador incluye novedades en el próximo resumen al owner
```

## Flujo 7 — Salida hacia IA externa (transversal)

Todo uso de IA externa pasa por esta cadena, sin excepciones:

```text
Agente necesita IA
  → Model Router: ¿hace falta IA? ¿qué nivel?
  → Context Minimizer: recorte de contexto + redacción de secretos
  → Cost Tracker: ¿hay presupuesto?
  → Llamada al proveedor vía gateway
  → Registro de tokens y costo
```
