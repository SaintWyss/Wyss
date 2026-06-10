# Wyss — Arquitectura de Agentes

**Versión:** 0.1

---

## 1. Anatomía de un agente

Todo agente de Wyss es una **instancia del modelo base** con esta estructura:

```text
Agente
├── Identidad
│   ├── Nombre propio (identidad argentina)
│   ├── Dominio de responsabilidad
│   └── Descripción de rol ("contrato" del agente)
├── Capacidades
│   ├── Herramientas permitidas (subconjunto de adaptadores)
│   ├── Modelo de IA asignado (alias en el gateway)
│   └── Presupuesto (tokens / dinero / período)
├── Contexto
│   ├── BC habilitadas (vía Permission)
│   ├── Memoria operativa propia (preferencias y patrones del dominio)
│   └── Instrucciones permanentes del owner
└── Restricciones
    ├── Niveles de acción permitidos (A–C; D siempre prohibido)
    ├── No puede dirigir a otros agentes
    └── No puede modificar sus propias habilitaciones
```

## 2. El modelo base

El modelo base es **el producto**. Define lo común a todos los agentes:

- Protocolo de comunicación con el orquestador (recibir tarea → planificar → ejecutar → reportar).
- Integración con la política cognitiva (ningún agente la puede saltear).
- Acceso al conocimiento solo vía Retrieval Engine + habilitaciones.
- Acceso a IA solo vía Model Gateway.
- Auditoría automática de todo lo que hace.

Crear un agente nuevo = modelo base + configuración. **Cero código nuevo.**

## 3. Ciclo de vida

```text
Definición ──► Instanciación ──► Habilitación ──► Operación ──► Suspensión/Retiro
   (owner        (registro en      (Permission      (tareas y      (estado, no
    define)       Agent Registry)   sobre BC)        rutinas)       borrado: auditoría)
```

## 4. Jerarquía y comunicación

```text
                    OWNER
                      │  instrucciones
                      ▼
                 ORQUESTADOR
              │       │       │   delega / consolida
              ▼       ▼       ▼
          Agente A  Agente B  Agente C
              │       │       │   ejecutan / reportan
              ▼       ▼       ▼
          Herramientas + BC habilitadas
```

Reglas de comunicación:

1. **Vertical descendente:** solo el orquestador asigna tareas a agentes.
2. **Vertical ascendente:** los agentes reportan exclusivamente al orquestador.
3. **Horizontal: prohibida.** Si una tarea necesita dos dominios, el orquestador la divide y consolida los resultados.
4. **Trabajadores:** interactúan con agentes asignados solo dentro del alcance de su rol (consultar, reportar avance); nunca pueden reconfigurarlos.

## 5. Convención de nombres

Los agentes llevan **nombres con identidad argentina**, definidos por el owner. Ejemplos de la visión inicial:

| Dominio | Nombre candidato |
|---|---|
| Estudio | Belgrano |
| Organización general | Sarmiento |
| (a definir por dominio) | — |

Criterios: evitar marcas y personas vivas con derechos de imagen; preferir próceres, geografía y conceptos culturales. El nombre es configuración, no código: cada cliente puede renombrar sus agentes.

## 6. Asignación de inteligencia

Cada agente declara la complejidad típica de su dominio y el Model Router resuelve:

```text
Tarea determinística         → lógica local, sin IA
Clasificar / resumir simple  → modelo económico
Razonamiento profundo        → modelo fuerte (con control de costo)
Información sensible         → contexto mínimo o procesamiento local
```

Un mismo agente puede usar distintos modelos según la tarea; el agente es el rol, no el modelo.

## 7. Lo que un agente nunca puede hacer

- Acceder a una BC sin habilitación vigente.
- Ejecutar acciones de nivel D.
- Dirigir, crear o modificar otros agentes.
- Modificar sus propias habilitaciones, presupuesto o restricciones.
- Comunicarse con el owner salteando al orquestador (salvo canal de emergencia definido por política).
- Enviar secretos o contexto no autorizado a modelos externos.
