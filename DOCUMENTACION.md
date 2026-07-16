# Documentación de Wyss

Yo organicé la documentación de Wyss para que una persona sin experiencia en agentes, LLM, daemons o arquitectura hexagonal pueda entender el sistema antes de darle permisos sobre su computadora.

## Recorrido recomendado

1. [Producto y primeros pasos](docs/manual/01_PRODUCTO_Y_PRIMEROS_PASOS.md)
2. [Uso funcional](docs/manual/02_USO_FUNCIONAL.md)
3. [Arquitectura y decisiones](docs/manual/03_ARQUITECTURA_Y_DECISIONES.md)
4. [Diagramas UML](docs/manual/04_UML.md)
5. [Configuración, datos y APIs](docs/manual/05_CONFIGURACION_DATOS_Y_API.md)
6. [Seguridad, pruebas y calidad](docs/manual/06_SEGURIDAD_PRUEBAS_Y_CALIDAD.md)
7. [Operación, despliegue y recuperación](docs/manual/07_OPERACION_DESPLIEGUE_Y_RECUPERACION.md)
8. [Estado, limitaciones, roadmap y glosario](docs/manual/08_ESTADO_LIMITACIONES_Y_GLOSARIO.md)

## Criterio editorial

- Escribí el manual en español y en primera persona.
- Explico primero con ejemplos simples y después con precisión técnica.
- Diferencio el núcleo de seguridad, los productores de planes y los adaptadores que ejecutan.
- No presento al LLM como autoridad de riesgo.
- Separo funciones implementadas, pruebas automatizadas, smoke físico y release formal.

## Fuente de verdad

1. código, configuración y pruebas;
2. este manual normalizado;
3. documentación vigente de `docs/`;
4. release notes históricas;
5. `.planning/` como evidencia de construcción y planes.

Los secretos de proveedores, tokens de pairing, bearer de intake y archivos de datos reales nunca se incluyen en esta documentación.