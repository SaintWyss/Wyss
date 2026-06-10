# Wyss — Arquitectura Conceptual

**Versión:** 0.1

---

## 1. Vista general

```text
┌─────────────────────────────────────────────────────────────────┐
│                            OWNER                                 │
│                 CLI / chat (v0.1) · móvil / voz (futuro)         │
└───────────────────────────────┬─────────────────────────────────┘
                                │ (acceso exclusivo)
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                       NÚCLEO WYSS (Raíz)                         │
│  ┌───────────────┐ ┌──────────────┐ ┌─────────────────────────┐ │
│  │ Orquestador    │ │ Planificador │ │ Política Cognitiva       │ │
│  │ (intención,    │ │ (planes      │ │ (finalidad, impacto,     │ │
│  │  delegación)   │ │  explícitos) │ │  riesgo, niveles A–D)    │ │
│  └───────────────┘ └──────────────┘ └─────────────────────────┘ │
│  ┌───────────────┐ ┌──────────────┐ ┌─────────────────────────┐ │
│  │ Gestor de      │ │ Gestor de    │ │ Confirmaciones +         │ │
│  │ Habilitaciones │ │ Rutinas      │ │ Auditoría (transversal)  │ │
│  └───────────────┘ └──────────────┘ └─────────────────────────┘ │
└───────┬───────────────────┬───────────────────────┬─────────────┘
        │                   │                       │
        ▼                   ▼                       ▼
┌──────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ CAPA DE       │  │ CAPA DE CONOCIMIENTO │  │ GATEWAY DE MODELOS    │
│ AGENTES       │  │  · Ingesta           │  │  · Modelos económicos │
│  Agente A     │  │  · Índice semántico  │  │  · Modelos fuertes    │
│  Agente B     │  │  · Recuperación      │  │  · Contexto mínimo    │
│  Agente N     │  │  · BC por contexto   │  │  · Control de costos  │
└──────┬───────┘  └──────────────────────┘  └──────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CAPA DE EJECUCIÓN                           │
│   Adaptadores: FileSystem · Shell · Git · Calendario ·           │
│   Mensajería · Apps · APIs externas                              │
└─────────────────────────────────────────────────────────────────┘

   TRABAJADORES ──► interactúan solo con agentes habilitados
```

## 2. Los cinco bloques

### Bloque 1 — Núcleo (Raíz)
Propiedad exclusiva del owner. Contiene el orquestador, el planificador, la política cognitiva, el gestor de habilitaciones, el gestor de rutinas y la configuración maestra. **Es la parte que se construye una vez y se replica como producto.**

### Bloque 2 — Capa de Agentes
Instancias del modelo base. Cada agente tiene: identidad (nombre), dominio, herramientas permitidas, BC habilitadas, modelo de IA asignado y presupuesto. Ejecutan y reportan. Jerarquía estricta: nunca dirigen.

### Bloque 3 — Capa de Conocimiento
Independiente de los agentes. Pipeline de ingesta → índice semántico → recuperación instantánea. Las BC se organizan por contexto (personal, RAGcorp, beca, cliente X) y se habilitan dinámicamente.

### Bloque 4 — Gateway de Modelos
Punto único de salida hacia IA externa. Enruta según costo/complejidad/privacidad, aplica contexto mínimo y registra costos. Permite cambiar de proveedor sin tocar el núcleo.

### Bloque 5 — Capa de Ejecución
Adaptadores desacoplados hacia el mundo real: archivos, terminal, repositorios, calendario, mensajería, aplicaciones.

## 3. Principios arquitectónicos

1. **Jerarquía estricta:** owner → orquestador → agentes → herramientas. Nunca al revés, nunca horizontal.
2. **Conocimiento separado de los agentes:** un agente no "tiene" conocimiento; tiene *habilitaciones* sobre BC que existen aparte.
3. **Juicio antes que ejecución:** toda acción pasa por la política cognitiva (herencia directa de Jarvis).
4. **Contexto mínimo hacia afuera:** Wyss puede saberlo todo; los modelos externos solo reciben lo necesario.
5. **Auditoría transversal:** cruza todas las capas; nada relevante ocurre sin registro.
6. **Núcleo replicable:** la lógica es genérica; la personalización vive en configuración, BC y agentes.

## 4. Correspondencia con el sistema de referencia (Nate Gentile)

| Wyss | Referencia | Diferencia clave |
|---|---|---|
| Núcleo | Orion | Wyss incluye política cognitiva y habilitaciones por diseño |
| Orquestador | Janus | Replicable como producto, no a medida |
| Agentes especializados | Fama / Somnus / Moneta | Instancias de un modelo base común |
| Capa de conocimiento | BD semántica local | API-first en v0.1; sin hardware dedicado |
