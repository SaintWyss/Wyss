# Wyss — Stakeholders y Roles

**Versión:** 0.1

---

## 1. Actores humanos

### Owner
- Único poseedor del orquestador (Núcleo/Raíz).
- Define instrucciones, políticas, rutinas y habilitaciones.
- Aprueba o rechaza acciones que requieren confirmación.
- Es el único que puede crear, modificar o eliminar agentes.

### Trabajador / Operador
- Interactúa con agentes especializados asignados a su rol.
- No tiene acceso al orquestador.
- Solo ve las bases de conocimiento que el owner le habilitó.
- Reporta avances a través de los agentes (texto, voz, etc.).

### Cliente (fase producto)
- Empresa o persona que adquiere una instancia de Wyss.
- Se convierte en owner de su propia instancia.
- Conecta su contexto y configura sus agentes.

### Administrador técnico (fase producto)
- Realiza el despliegue, mantenimiento e integración inicial.
- No tiene acceso al contenido del conocimiento del cliente.

## 2. Actores de sistema

### Orquestador (Núcleo)
- Agente raíz. Coordina, planifica, delega y controla.
- Único punto con visión completa del sistema.

### Agentes Especializados
- Instancias del modelo base configuradas para un dominio.
- Ejecutan tareas dentro de su dominio y reportan al orquestador.
- No pueden dirigir a otros agentes.

### Sistemas externos
- Proveedores de modelos de IA (Claude, Gemini, modelos económicos vía gateway).
- Bases de conocimiento existentes (RAGcorp, proyectos de la beca, archivos locales).
- Herramientas del entorno: sistema de archivos, Git, calendario, mensajería, aplicaciones.

## 3. Matriz de permisos

| Capacidad | Owner | Trabajador | Orquestador | Agente |
|---|:---:|:---:|:---:|:---:|
| Acceder al orquestador | ✅ | ❌ | — | ❌ |
| Crear/eliminar agentes | ✅ | ❌ | ⚙ propone | ❌ |
| Habilitar bases de conocimiento | ✅ | ❌ | ⚙ ejecuta | ❌ |
| Dar instrucciones a agentes | ✅ | ⚙ limitado a su rol | ✅ | ❌ |
| Ejecutar tareas operativas | — | — | ⚙ delega | ✅ |
| Ver auditoría completa | ✅ | ❌ | ✅ | ❌ |
| Confirmar acciones de alto impacto | ✅ | ❌ | ❌ | ❌ |

⚙ = con restricciones definidas por política.

## 4. Regla jerárquica central

```text
Solo el owner dirige.
El orquestador coordina en nombre del owner.
Los agentes ejecutan en su dominio.
Nadie por debajo del orquestador puede dirigir a otros.
```
