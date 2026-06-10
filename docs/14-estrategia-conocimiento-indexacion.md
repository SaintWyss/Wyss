# Wyss — Estrategia de Conocimiento e Indexación

**Versión:** 0.1

---

## 1. Objetivo

Que el owner pueda encontrar **cualquier información perdida en terabytes de archivos en un instante**, y que los agentes operen sobre ese conocimiento con acceso controlado — sin hardware de servidor dedicado.

## 2. Restricción de diseño: API-first, sin hierro

A diferencia del sistema de referencia (servidor con GPU de 96 GB para modelos locales), Wyss v0.1 corre en una PC estándar:

| Necesidad | Solución sin hardware dedicado |
|---|---|
| Embeddings | API de embeddings externa (lotes, costo bajo) o modelo liviano local en CPU |
| Búsqueda full-text | SQLite FTS5 (patrón validado en Hermes Agent) — gratis, local, rapidísimo |
| Índice vectorial | Base vectorial embebida local (Chroma/Qdrant embebido/sqlite-vec) |
| LLM de razonamiento | APIs externas vía gateway, con contexto mínimo |
| Procesamiento de media pesada | Diferido / por lotes / opcional en v0.1 |

**Principio:** la inteligencia se alquila por consulta; el conocimiento y el índice son 100% locales y propios.

## 3. Pipeline de ingesta

```text
1. Registro de fuente      → carpeta, base externa, documento
2. Escaneo                 → inventario de archivos + metadatos (ruta, tipo, fecha, tamaño)
3. Diff incremental        → solo nuevos o modificados (hash + fecha)
4. Extracción              → texto según tipo (docs, código, PDF, notas)
5. Chunking                → fragmentos con referencia exacta a origen
6. Resumen persistente     → descripción breve por archivo/fragmento
7. Doble indexación        → FTS5 (palabras exactas) + vectores (semántica)
8. Catalogación            → asignación a su Base de Conocimiento
```

**Reglas:**
- Incremental siempre: 2 TB se indexan una vez; después solo cambios.
- Los archivos nunca se mueven ni modifican: el índice apunta, no copia (salvo caché de extractos).
- Lo binario pesado (video, imágenes) se indexa por metadatos y resumen, no por contenido completo, en v0.1.

## 4. Recuperación híbrida

Una consulta se resuelve combinando tres vías, en paralelo:

```text
Consulta del owner/agente
  ├── Metadatos     → nombre, fecha, tipo, ubicación ("el PDF de marzo en la carpeta de la beca")
  ├── FTS5          → coincidencia exacta de términos ("informe seguridad pyme")
  └── Semántica     → significado ("eso que escribí sobre vulnerabilidades de sistemas chicos")
        ↓
  Fusión y ranking de resultados
        ↓
  Filtro de habilitaciones (qué BC puede ver quien pregunta)
        ↓
  Respuesta: ubicación exacta + extracto + resumen
```

La combinación es lo que da la sensación de "instantáneo e infalible": si una vía falla, las otras encuentran.

## 5. Organización por Bases de Conocimiento

```text
BC Personal        → archivos propios del owner (los 2 TB iniciales)
BC RAGcorp         → base documental de la empresa
BC Beca Ciber #1   → proyecto de análisis de seguridad de pymes
BC Beca Ciber #2   → proyecto de análisis de sistemas
BC Cliente X       → (futuro, instancias replicadas)
```

Cada BC es independiente: índice propio, sensibilidad propia, habilitaciones propias. El orquestador decide quién ve cuál.

## 6. Memoria de los agentes vs. conocimiento

No confundir:

| | Conocimiento (BC) | Memoria operativa |
|---|---|---|
| Qué es | Información del owner | Lo que el agente aprende usándose |
| Ejemplos | Documentos, código, notas | Preferencias, rutas frecuentes, decisiones repetidas |
| Dónde vive | Índice semántico | Memoria propia del agente (patrón MEMORY.md / skills de Hermes) |
| Quién la controla | Owner vía habilitaciones | El sistema, auditada y revisable por el owner |

## 7. Evolución futura

- v0.x: embeddings locales en CPU para independencia total de APIs.
- Futuro: si el volumen y el negocio lo justifican, migración a servidor local con GPU — la arquitectura no cambia, solo el despliegue del gateway.
