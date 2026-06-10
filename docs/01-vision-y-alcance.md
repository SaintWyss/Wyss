# Wyss — Documento de Visión y Alcance

**Versión:** 0.1
**Estado:** Fundacional
**Autor:** Santiago Wyss

---

## 1. Visión

Wyss es un sistema de asistencia operativa personal y empresarial basado en una arquitectura multi-agente, diseñado para automatizar tareas, centralizar el conocimiento y operar como un empleado digital real.

El sistema se organiza en torno a un orquestador central — accesible únicamente por el owner — que coordina agentes especializados, cada uno con un dominio propio y acceso controlado a las bases de conocimiento habilitadas. Los agentes no piensan por el usuario: ejecutan lo que el usuario ya decidió, de forma precisa, trazable y auditable.

**Filosofía rectora: humano primero, IA cuando corresponde.**

> Wyss es el empleado que siempre necesitaste y nunca pudiste contratar.

## 2. Problema que resuelve

Las personas y empresas pequeñas tienen:

- Tareas repetitivas y procesos manuales que consumen tiempo valioso.
- Conocimiento disperso en archivos, carpetas, proyectos y herramientas distintas, imposible de recuperar rápido.
- Necesidades de automatización que requerirían contratar personal técnico que no pueden pagar, y cuyo retorno no pueden medir.

Hoy no existe una forma accesible de tener un trabajador digital que conozca el contexto propio, ejecute tareas operativas, use IA solo cuando corresponde y se adapte a cualquier dominio sin reprogramarse desde cero.

## 3. Solución

Wyss resuelve el problema siendo **el empleado técnico que antes no se podía tener**:

1. **Indexa el conocimiento del usuario** (archivos, proyectos, notas, bases existentes) y lo hace recuperable en instantes.
2. **Ejecuta tareas operativas** sobre el entorno real: archivos, aplicaciones, repositorios, calendarios, comunicaciones.
3. **Automatiza lo repetitivo** mediante rutinas y agentes especializados.
4. **Mantiene el control en el humano**: el owner dirige, los agentes ejecutan, todo queda auditado.

## 4. A quién está dirigido

| Perfil | Necesidad |
|---|---|
| Profesional independiente | Automatizar su operación personal y organizar su conocimiento |
| Pyme / empresa pequeña | Tener capacidad técnica de automatización sin contratar un equipo |
| Owner de múltiples proyectos | Coordinar contextos distintos (empresa, estudio, proyectos) desde un solo punto |

## 5. Diferenciadores

- **Humano primero:** la dirección estratégica y creativa es 100% humana. La IA no decide; ejecuta.
- **Jerarquía real:** solo el owner posee el orquestador. Los agentes son instancias subordinadas con acceso controlado.
- **Control de contexto por rol:** el orquestador decide qué base de conocimiento ve cada agente, igual que en una empresa real.
- **Juicio cognitivo (herencia de Jarvis):** toda acción pasa por evaluación de finalidad, impacto, reversibilidad y riesgo. Wyss puede rechazar acciones destructivas aunque se le pidan.
- **Modelo base replicable:** el núcleo se construye una vez; cada cliente nuevo solo conecta su contexto y habilita sus agentes.
- **Identidad propia:** nombres, diseño y filosofía con sello argentino.

## 6. Qué NO es Wyss

- No es un chatbot.
- No es un wrapper de un solo modelo de IA.
- No es una IA autónoma sin supervisión.
- No reemplaza el criterio humano ni la dirección creativa.
- No requiere hardware de servidor dedicado en su versión inicial (estrategia API-first).

## 7. Alcance inicial (Wyss v0.1)

- Núcleo orquestador funcional para un solo owner.
- Índice de conocimiento personal sobre los archivos del owner.
- Al menos un agente especializado operativo.
- Sistema de habilitaciones de conocimiento.
- Confirmaciones por nivel de impacto y rechazo de acciones inválidas.
- Auditoría de todas las acciones.
- Interfaz inicial por CLI/chat.

## 8. Fuera de alcance v0.1

- Multiusuario y multiempresa.
- Interfaz móvil y voz.
- Modelos locales pesados (se usan APIs externas).
- Marketplace de agentes.
- Integraciones de domótica.

## 9. Evolución prevista

```text
v0.1  Núcleo personal + índice + primer agente
v0.2  Multi-agente + rutinas programadas
v0.3  Habilitaciones por trabajador (modo empresa)
v1.0  Producto replicable para clientes
```
