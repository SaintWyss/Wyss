# Documentación canónica de Wyss

Este índice separa documentación vigente, evidencia de release, planificación e historia. Su objetivo es evitar que un plan antiguo o una release previa se interpreten como estado actual del producto.

## Regla de precedencia

Cuando dos fuentes discrepan, se usa este orden:

1. código, configuración, pruebas y artefactos ejecutables;
2. [`RELEASE_STATUS.md`](RELEASE_STATUS.md);
3. [`OPERATOR.md`](OPERATOR.md) y documentación operativa;
4. arquitectura y seguridad vigentes;
5. release notes históricas;
6. `.planning/`, auditorías y planes de implementación.

Una casilla marcada en `.planning/` no reemplaza evidencia ejecutable. Del mismo modo, una casilla desactualizada no invalida código y validaciones posteriores.

## Estado y operación

- [Estado real del producto](RELEASE_STATUS.md)
- [Guía diaria del operador](OPERATOR.md)
- [Configuración](CONFIGURATION.md)
- [Testing y gates](TESTING.md)
- [Release histórica v0.1.0](releases/WYSS_v0.1.0.md)

## Arquitectura y seguridad

- [Arquitectura objetivo y reglas de capas](architecture/WYSS_TARGET_ARCHITECTURE.md)
- [Mapa del sistema](audit/WYSS_SYSTEM_MAP.md)
- [Modelo de seguridad](security/SECURITY_MODEL.md)
- [Auditorías](audit/)

## Interfaces y clientes

- El bridge web, pairing, intake y superficies del operador viven en `src/bootstrap/web.py`.
- La app Android nativa vive en `mobile/`.
- La validación del APK y los checkpoints de dispositivo están en `.planning/phases/15-mobile-apk/`.

## Planificación e historia

`.planning/` conserva requisitos, investigación, planes, decisiones y summaries. Es evidencia útil para entender por qué se construyó algo, pero no es la fuente principal del estado actual.

Los documentos numerados y planes antiguos de `docs/` pueden describir arquitectura objetivo, propuestas descartadas o etapas anteriores. Cuando no estén enlazados desde este índice deben tratarse como históricos o de contexto.

## Mantenimiento

Todo PR que cambie capacidades, comandos, variables, riesgos, superficies HTTP, persistencia, cliente móvil o gates debe actualizar en el mismo cambio:

- `README.md` si afecta onboarding;
- `docs/RELEASE_STATUS.md` si cambia estado funcional;
- `docs/OPERATOR.md` si cambia operación diaria;
- `docs/CONFIGURATION.md` si cambia configuración;
- `docs/TESTING.md` si cambia validación o CI.
