# `.planning/` — planificación e historia de ejecución

Este directorio conserva requisitos, research, planes, decisions, summaries y validaciones generadas durante la construcción de Wyss.

No es la fuente principal del estado operativo.

## Precedencia

Ante contradicciones:

1. código, configuración y pruebas;
2. `docs/RELEASE_STATUS.md`;
3. `docs/OPERATOR.md`;
4. este directorio.

`STATE.md` resume el cierre del milestone. `ROADMAP.md` conserva detalle acumulado y puede contener checkboxes históricos que no se actualizaron después de una ejecución posterior.

## Cómo interpretar archivos

- `*-PLAN.md`: intención previa a implementar;
- `*-SUMMARY.md`: resultado declarado de una ejecución;
- `*-VALIDATION.md`: mapa o evidencia de validación;
- `*-RESEARCH.md`: investigación y decisiones consideradas;
- `ROADMAP.md`: orden y alcance planeados;
- `STATE.md`: resumen reconciliado del milestone.

Una capacidad se considera vigente únicamente cuando además existe evidencia en código, pruebas y `docs/RELEASE_STATUS.md`.
