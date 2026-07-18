# 03 — Arquitectura y decisiones de ingeniería

## Explicación simple

Yo construí Wyss con arquitectura hexagonal. El núcleo define tareas, planes, riesgos, política y contratos. Los detalles externos —LLM, archivos, Git, Notion, SQLite, web— se conectan mediante adaptadores.

La regla más importante es:

```text
El LLM propone. La política decide. El owner confirma. Las herramientas ejecutan.
```

## Capas

| Capa | Responsabilidad |
|---|---|
| `core/domain` | entidades y vocabulario inmutable |
| `core/ports` | contratos para orquestación, ejecución, memoria, ledger y auditoría |
| `core/policy` | clasificación A–D y denylist no removible |
| `orchestrator` | daemon, dispatch, pendientes, scheduler y digest |
| `gateway` | providers, router, costos, minimización y traces |
| `knowledge` | scanner, extracción, FTS5, vectores y retrieval |
| `execution` | archivos, shell, Git, verificación y undo |
| `agents` | agentes config-driven |
| `memory` | memoria persistente y herramienta gateada |
| `notion` | adaptador de Notion |
| `ledger` | finanzas deterministas |
| `audit` | evidencia append-only lógica |
| `bootstrap` | config, DI, CLI, web y composición |

## Por qué la arquitectura es adecuada

### Seguridad estructural

Yo no dependo solo de prompts. La denylist nivel D vive en código y la configuración solo puede agregar reglas.

### Sustitución de proveedores

El orquestador usa un port. Puedo conectar deterministic, LiteLLM, Anthropic u otro provider sin permitir que el provider conozca la ejecución concreta.

### Pruebas sin recursos reales

Los ports permiten usar fakes para LLM, filesystem, memoria, auditoría o ledger.

### Un único camino de ejecución

Rutinas, intake, CLI y web producen planes que terminan en el mismo `dispatch()` y `PlanExecutor`.

## Decisiones principales

### D-01 — Hexagonal y core puro

**Yo elegí:** `core` solo con standard library.

**Porque:** el significado de riesgo, plan y política no debe depender de Pydantic, FastAPI o SQLite.

**Costo:** más mapeos en bootstrap.

### D-02 — Daemon local por Unix socket

**Yo elegí:** JSON-RPC sobre socket Unix.

**Porque:** reduce exposición de red y ofrece IPC simple para CLI.

**Diferencia:** la web no reemplaza el daemon; actúa como bridge controlado.

### D-03 — Política determinista A–D

**Yo elegí:** niveles y reglas evaluados fuera del LLM.

**Porque:** la seguridad no puede depender de una salida probabilística.

### D-04 — Denylist built-in aditiva

**Yo elegí:** reglas D inmutables en código; TOML solo agrega.

**Porque:** editar configuración no debe desactivar la protección.

### D-05 — Re-evaluación al confirmar

**Yo elegí:** volver a evaluar el plan antes de aceptar la palabra.

**Porque:** archivos, symlinks, reglas o contexto pueden cambiar entre propuesta y confirmación.

### D-06 — Segunda muralla en adaptadores

**Yo elegí:** cada herramienta valida nuevamente rutas, flags y efectos.

**Porque:** la política y el planner no deben ser el único punto de defensa.

### D-07 — Gateway único de modelos

**Yo elegí:** toda salida a IA pasa por minimización, presupuesto, routing y tracing.

**Porque:** evita providers ocultos y controla costos/contexto.

### D-08 — FTS5 + vectores + RRF

**Yo elegí:** búsqueda híbrida.

**Porque:** FTS5 encuentra términos exactos y embeddings aportan semántica; RRF combina rankings sin calibrar scores incompatibles.

### D-09 — SQLite separado por responsabilidad

**Yo elegí:** bases distintas para auditoría, pendientes, rutinas, memoria, ledger, índice y journal.

**Porque:** reduce acoplamiento, facilita backups selectivos y evita que un esquema gigante mezcle dominios.

**Costo:** operación y consistencia entre DBs requieren cuidado.

### D-10 — Rutinas como productores de planes

**Yo elegí:** guardar un plan serializado y reconstruirlo al disparar.

**Porque:** una rutina no debe ejecutar por un camino privilegiado.

### D-11 — Memoria trust-tiered

**Yo elegí:** distinguir owner de contenido externo.

**Porque:** evita convertir una instrucción maliciosa ingerida en una preferencia confiable.

### D-12 — Digest fuera de acciones mutables

**Yo elegí:** composición de solo lectura.

**Porque:** un resumen proactivo no debe crear escrituras por sí mismo.

### D-13 — Notion como Tool

**Yo elegí:** leer/escribir Notion mediante acciones tipadas y política.

**Porque:** una integración externa debe tener los mismos gates que filesystem.

### D-14 — Intake con bearer propio y piso B

**Yo elegí:** separar automatizaciones externas de pairing y forzar confirmación.

**Porque:** n8n no representa al owner autenticado en persona.

### D-15 — Bridge LAN opt-in

**Yo elegí:** localhost por defecto y `--lan --tls` explícito.

**Porque:** no quiero exponer la interfaz accidentalmente.

### D-16 — APK con pinning TOFU

**Yo elegí:** confiar la primera huella y bloquear cambios posteriores.

**Porque:** el certificado local self-signed necesita una identidad verificable sin CA pública.

**Límite:** el primer pairing debe hacerse en una red y pantalla confiables.

### D-17 — Wyss como única autoridad Home

**Yo elegí:** exponer capacidades y proyecciones mediante ports públicos de `core`.

**Porque:** Home Edge, web, Android y ESP32 no deben acceder al executor ni a bases internas, y no
deben convertirse en autoridades alternativas.

**Detalle:** [ADR-001 — límite de autoridad Home](../architecture/ADR-001-home-authority-boundary.md).

### D-18 — Capacidad RPC dedicada para Home Edge

**Yo elegí:** separar `wyss-home.sock` de `wyss.sock`, aplicar una allowlist cerrada de métodos y
resolver confirmaciones con revisión y TTL dentro del mismo compare-and-swap.

**Porque:** un permiso de archivo autentica al usuario Unix, pero no debe conceder por transitividad
las operaciones owner/administrativas al canal legítimo de Home Edge.

**Detalle:** [ADR-003 — capacidad RPC Home](../architecture/ADR-003-home-rpc-capability-boundary.md).

## Alternativas descartadas

| Alternativa | Ventaja | Por qué la descarté |
|---|---|---|
| dar shell libre al LLM | flexibilidad | rompe control y auditabilidad |
| HTTP público para daemon | acceso fácil | mayor superficie de ataque |
| una sola DB | menos archivos | acopla dominios y backups |
| LangChain/LlamaIndex | componentes listos | arquitectura y abstracciones impuestas |
| Redis/Celery desde el inicio | distribución | sobreingeniería para un owner local |
| autoejecutar rutinas | comodidad | contradice humano primero |
| aceptar cualquier certificado | menos fricción | permite MITM/reemplazo silencioso |

## Atributos priorizados

1. seguridad y control humano;
2. auditabilidad;
3. corrección;
4. privacidad/contexto mínimo;
5. recuperabilidad;
6. extensibilidad;
7. experiencia;
8. rendimiento.

## Deuda reconocida

- RPC `audit` stub;
- undo limitado;
- release/versionado formal desalineado con alcance v1;
- CI raíz no ejecuta toda la matriz web/Android;
- operación single-owner/local;
- dependencia de WAL y filesystem POSIX;
- service worker limitado con certificados self-signed;
- path advisory de agentes externos en evolución.

## Regla de evolución

Yo rechazo cualquier feature que introduzca un segundo camino de ejecución o permita que un productor de planes asigne el riesgo definitivo.
