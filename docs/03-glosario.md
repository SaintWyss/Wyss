# Wyss — Glosario del Proyecto

**Versión:** 0.1

---

| Término | Definición |
|---|---|
| **Wyss** | Nombre del sistema completo. Plataforma de asistencia operativa multi-agente, humano primero. |
| **Núcleo / Raíz** | Componente central del sistema. Contiene el orquestador, las políticas y la configuración maestra. Solo el owner lo posee. |
| **Orquestador** | Agente principal del núcleo. Interpreta las instrucciones del owner, planifica, delega a los agentes y controla las habilitaciones. Equivalente conceptual a "Janus" en el sistema de referencia de Nate Gentile. |
| **Agente Especializado** | Instancia del modelo base configurada para un dominio específico (estudio, finanzas, organización, etc.). Ejecuta y reporta; no dirige. |
| **Modelo Base** | Plantilla replicable a partir de la cual se instancian todos los agentes. Es el producto central de Wyss. |
| **Instancia** | Copia operativa del modelo base con identidad, dominio, herramientas y contexto propios. |
| **Dominio** | Área de responsabilidad de un agente (ej.: estudio, organización, finanzas, seguimiento). |
| **Base de Conocimiento (BC)** | Conjunto de información indexada perteneciente a un contexto: archivos personales, RAGcorp, proyectos de la beca, documentación de un cliente. |
| **Habilitación** | Permiso dinámico otorgado por el orquestador (por orden del owner) para que un agente o trabajador acceda a una BC determinada. |
| **Índice Semántico** | Estructura que permite recuperar cualquier información de las BC en instantes, combinando metadatos, búsqueda full-text y embeddings. |
| **Ingesta** | Proceso de incorporar nueva información a una BC: extracción, limpieza, indexación. |
| **Política Cognitiva** | Capa de juicio heredada de Jarvis: evalúa finalidad, impacto, reversibilidad y riesgo de toda acción antes de ejecutarla. |
| **Nivel de Acción** | Clasificación de impacto: A (ejecución directa), B (confirmación simple), C (confirmación fuerte), D (rechazo absoluto). |
| **Rutina** | Tarea programada que el orquestador ejecuta periódicamente sin intervención del owner (ej.: resumen ejecutivo semanal). |
| **Confirmación** | Aprobación explícita del owner requerida antes de acciones modificadoras o de alto impacto. |
| **Auditoría** | Registro trazable de toda acción, decisión, confirmación y resultado del sistema. |
| **Owner** | Persona dueña de la instancia de Wyss. Único humano con acceso al núcleo. |
| **Trabajador** | Humano que interactúa con agentes asignados, sin acceso al núcleo. |
| **Contexto** | Conjunto de información, herramientas y BC asociadas a una organización o área de la vida del owner. |
| **Gateway de Modelos** | Punto único de acceso a proveedores de IA externos (vía LiteLLM o equivalente), con control de costos y enrutamiento. |
| **Contexto Mínimo** | Principio de privacidad: a cada modelo externo se le envía solo la información estrictamente necesaria. |
| **Humano Primero** | Filosofía rectora: la dirección estratégica, creativa y de diseño es 100% humana; la IA ejecuta lo operativo. |
