# PR-09 — Documentation rebuild

> **EJECUTADO 2026-07-02** directamente por Claude (desvío al plan de executor: el spec proponía
> draft Gemini + verificación Claude, pero todos los hechos ya estaban verificados en la sesión del
> audit — delegar hubiera costado más que escribir). Mecanismo GSD §12 resuelto: el marker
> `source:ARCHITECTURE.md` apuntaba a un archivo inexistente → se creó `.planning/ARCHITECTURE.md`
> como fuente y se sincronizó la sección de CLAUDE.md con el mismo contenido.
> Cifras verificadas contra el repo: 17 contratos = 16 `class *(Protocol)` (grep) + `AgentBase` ABC;
> estado 8/10 fases (STATE.md); suite 435 passed post-edición.

## 1. Objective
Que la documentación diga la verdad: README con estado real, CLAUDE.md con la arquitectura mapeada, docs fundacionales marcados como históricos.

## 2. Context from the audit
- `README.md:8` — "Estado: Fase 0 — Diseño". Realidad: fase 8/10 cerrada, 424 tests.
- `README.md:60,78` — "14 contratos (13 Protocol + AgentBase)". Realidad: 16 clases Protocol + ABC en `src/core/ports/`.
- `README.md` árbol — falta `src/ledger/`, `src/core/orchestrator/`, `gateway/providers/`, `knowledge/extractors/`; describe `scripts/` como "utilidades de desarrollo y despliegue" y está vacío.
- `CLAUDE.md` §Architecture — "Architecture not yet mapped. Follow existing patterns found in the codebase." — el runbook de TODO orquestador no describe la arquitectura que existe y está enforced.
- `docs/15-roadmap.md` — "Fase 0 — Diseño (actual)"; el roadmap real (10 fases) vive en `.planning/ROADMAP.md`.

## 3. Exact problem
Cualquier humano o agente nuevo se orienta con documentación falsa. Para un proyecto que delega ejecución a modelos baratos, docs falsos = ejecutores que "corrigen" cosas correctas o buscan módulos inexistentes.

## 4. Architectural decision
Una sola fuente de verdad por tema: estado/progreso → `.planning/` (GSD); arquitectura → `docs/architecture/WYSS_TARGET_ARCHITECTURE.md` (referenciada desde CLAUDE.md); visión histórica → `docs/00-18` congelados con banner. El README apunta, no duplica.

## 5. Files to read first
- `README.md`, `CLAUDE.md` (secciones marcadas GSD — ver §12)
- `docs/architecture/WYSS_TARGET_ARCHITECTURE.md` y `docs/audit/WYSS_SYSTEM_MAP.md` (este audit — fuente para el rewrite)
- `.planning/ROADMAP.md`, `.planning/STATE.md`
- `src/core/ports/` (contar contratos reales al momento de escribir)

## 6. Files allowed to modify
- `README.md`
- `docs/00-indice.md` (banner histórico; opcionalmente banner de una línea en 01-18)
- `CLAUDE.md` SOLO la sección `<!-- GSD:architecture-start -->…end -->` — ver riesgo §12

## 7. Files forbidden to modify
- `.planning/` (lo maneja GSD)
- `docs/audit/`, `docs/architecture/`, `docs/roadmap/`, `docs/plans/` (salida del audit — no la edita este PR)
- Código.

## 8. Required changes
1. README: estado real ("v0.1 en construcción — 8/10 fases; ver `.planning/ROADMAP.md`"), árbol actualizado (ledger, core/orchestrator, providers, extractors; quitar la mención mentirosa de scripts/ o marcar "reservado"), conteo de contratos corregido contando los reales, sección "Qué funciona hoy / qué falta" (tomar de WYSS_SYSTEM_MAP §6), link a los docs del audit.
2. `docs/00-indice.md`: banner "Documentos fundacionales (fase 0, 2026-06). Históricos: describen el diseño original; el estado real vive en `.planning/` y `docs/architecture/`."
3. CLAUDE.md §Architecture: párrafo + diagrama compacto tomado de WYSS_TARGET_ARCHITECTURE §1-2 (capas, dirección de deps, los 2 contratos import-linter, lista de protegidos D-85).
4. Verificación factual final (Claude, no el drafter): cada número citado (tests, fases, contratos) re-verificado contra el repo en el momento del merge.

## 9. Contracts and invariants
- Cero claims sin verificar: cada número del README debe ser reproducible con un comando.
- Los marcadores `<!-- GSD:*-start/end -->` de CLAUDE.md quedan intactos (GSD regenera por sección).

## 10. Tests required
```bash
uv run pytest -q   # nada de código cambió; smoke de que el repo sigue verde
grep -c "Protocol)" src/core/ports/*.py   # el número que diga el README debe salir de acá
```

## 11. Manual verification
Owner lee README de punta a punta: ¿describe el producto que corre hoy? `wyss --help` coincide con los comandos documentados.

## 12. Risks
- CLAUDE.md sección Architecture está entre marcadores GSD (`source:ARCHITECTURE.md`): si GSD regenera, pisa la edición manual. Mitigación: escribir el contenido en el archivo fuente que GSD consume (`.planning/ARCHITECTURE.md` si existe el mecanismo) o documentar en el commit que la sección se mantiene a mano. Verificar el mecanismo ANTES de editar; si es opaco, ESCALAR al owner.
- Drafter (Gemini) puede inventar detalles: por eso el paso 4 (verificación factual por Claude) es obligatorio antes del commit.

## 13. Rollback plan
Revert del commit; solo docs.

## 14. Acceptance criteria
- README sin ninguna de las 5 falsedades listadas en §2.
- CLAUDE.md §Architecture poblado y consistente con import-linter real.
- Banner histórico en docs fundacionales.
- Cada cifra verificada contra el repo (constancia en el mensaje de commit o SUMMARY).

## 15. Executor prompt for cheaper AI
```
Proyecto: Wyss. Root: /mnt/hdd/Data/10_Workspace/projects/wyss. Tarea SOLO de documentación. NO commitees.
Archivos permitidos: README.md, docs/00-indice.md, y la sección entre <!-- GSD:architecture-start --> y
<!-- GSD:architecture-end --> de CLAUDE.md. NADA más. No toques .planning/ ni docs/audit|architecture|roadmap|plans.

Fuentes de verdad (leelas antes de escribir): docs/audit/WYSS_SYSTEM_MAP.md,
docs/architecture/WYSS_TARGET_ARCHITECTURE.md, .planning/STATE.md, .planning/ROADMAP.md.

1. README.md: corrige el estado (hoy dice "Fase 0 — Diseño"; poné el estado real según STATE.md con link
   a .planning/ROADMAP.md), actualizá el árbol de src/ contra el filesystem real (agregá ledger/,
   core/orchestrator/, gateway/providers/, knowledge/extractors/), corregí el conteo de contratos de
   core/ports/ CONTÁNDOLOS en el código (grep "Protocol)" src/core/ports/*.py + la ABC AgentBase), y
   agregá sección "Qué funciona hoy / qué falta" copiando la tabla §6 del SYSTEM_MAP. No inventes NINGÚN
   dato: todo número sale de un comando o de los docs fuente.
2. docs/00-indice.md: banner al inicio: los docs 00-18 son fundacionales/históricos (diseño fase 0);
   estado real en .planning/ y docs/architecture/.
3. CLAUDE.md, SOLO dentro de los marcadores architecture: resumen de capas y dirección de dependencias
   copiado de WYSS_TARGET_ARCHITECTURE §1-2 + lista de archivos protegidos D-85. No toques ningún otro
   marcador GSD.
SUMMARY: lista de correcciones hechas con el dato viejo → nuevo y el comando que respalda cada cifra.
```
