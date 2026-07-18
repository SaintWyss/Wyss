# Wyss

> El empleado que siempre necesitaste y nunca pudiste contratar.

Asistente operativo humano-primero con política A–D, ejecución verificable, auditoría, conocimiento local, agentes especializados, web y cliente Android.

**Autor:** Santiago Wyss  
**Estado funcional:** alcance del milestone v1.0 implementado en el código  
**Versión del paquete:** `1.0.0.dev0` — línea v1 en desarrollo; no es una release final

- [Estado real y evidencia](docs/RELEASE_STATUS.md)
- [Guía del operador](docs/OPERATOR.md)
- [Índice documental](docs/README.md)

## Qué es

Wyss recibe una instrucción, construye un plan, lo evalúa mediante una política determinista, solicita confirmación cuando corresponde, ejecuta mediante adapters y audita el resultado.

```text
OWNER
  └─► ORQUESTADOR
        ├─► PLAN
        ├─► POLÍTICA A–D
        ├─► CONFIRMACIÓN B/C
        ├─► EXECUTION ADAPTERS
        └─► VERIFICACIÓN + AUDITORÍA
```

Los modelos ayudan a interpretar y proponer. No asignan el nivel de riesgo ni pueden evitar el gate del owner.

## Estado actual

| Área | Estado |
|---|---|
| Loop ask → plan → política → confirmación → ejecución → auditoría | Implementado y verificado E2E |
| Política A–D y denylist built-in no removible | Implementadas y testeadas |
| FileSystem, Shell y Git adapters | Implementados, con segunda muralla y verificación |
| Undo | Implementado para `file.*`; shell/git pendientes |
| Auditoría | Funciona por CLI y RPC acotado sobre el socket local |
| Indexación FTS5 + vectores + RRF | Implementada |
| Gateway de modelos, presupuesto y minimización | Implementados |
| Orquestador deterministic | Implementado y default de la plantilla |
| Orquestador LLM | Implementado; smoke manual con Qwen vía LiteLLM local |
| Agentes configurables y Pellegrini | Implementados |
| Bridge web/PWA LAN | Implementado y smokeado en teléfono real |
| Routine Scheduler | Implementado |
| Notion Adapter | Implementado |
| Owner Memory | Implementada |
| Daily Assistant | Implementado |
| Intake n8n | Implementado, opt-in y con bearer dedicado |
| Web PC | Implementada |
| APK Android | Implementado y pairing QR aprobado en dispositivo real |
| Modo Equipo | Fuera del alcance actual |

`v0.1.0` sigue siendo una release histórica válida. Después se implementaron las fases 9–15. Yo
uso `1.0.0.dev0` para identificar la línea v1 activa sin declarar una release v1.0 publicada.

## Niveles de acción

| Nivel | Tipo | Comportamiento |
|---|---|---|
| A | Lectura / diagnóstico | Ejecución directa |
| B | Modificación normal | Confirmación simple |
| C | Alto impacto | Exige escribir `CONFIRMAR` |
| D | Destructivo / inválido | Rechazo absoluto |

La política se reevalúa al confirmar. Un plan que escala a D no se ejecuta aunque la propuesta original hubiera sido confirmable.

## Inicio rápido

Requisitos:

- Python 3.12+;
- `uv`;
- `libmagic` en Linux;
- Node.js/npm para trabajar sobre la SPA;
- Android SDK/Gradle para compilar el cliente móvil.

```bash
uv sync
cp config/config.example.toml config/config.toml
cp config/.env.example config/.env
chmod 600 config/.env
```

Arrancar daemon:

```bash
uv run wyss start
```

En otra terminal:

```bash
uv run wyss ask "leé /tmp/ejemplo.txt"
uv run wyss audit
```

Interfaz local o móvil:

```bash
uv run wyss web
uv run wyss web --lan --tls
```

## Uso diario

```bash
uv run wyss ask "leé tal archivo"
uv run wyss ask "mové tal archivo"
uv run wyss confirm <pending_id>
uv run wyss undo <task_id> --dry-run
uv run wyss digest
uv run wyss routine list
uv run wyss memory list
uv run wyss fin ver
```

La referencia completa está en [`docs/OPERATOR.md`](docs/OPERATOR.md).

## LLM real

La plantilla usa modo determinista:

```toml
[orchestrator]
mode = "deterministic"
```

Para usar el gateway:

```toml
[orchestrator]
mode = "llm"
tier = "economico"
```

El modo LLM fue probado manualmente en el entorno del owner con Qwen a través de LiteLLM local. Esta evidencia no garantiza cualquier provider o modelo; cada combinación requiere smoke propio.

## Capacidades v1

### Rutinas

```bash
uv run wyss routine list
uv run wyss routine pause <id>
uv run wyss routine resume <id>
uv run wyss routine rm <id>
```

Las rutinas reutilizan la misma política y bandeja. No existe un segundo camino de ejecución.

### Memoria

```bash
uv run wyss ask "recordá que prefiero respuestas breves"
uv run wyss memory list
uv run wyss memory edit <fact_id> "nuevo valor"
uv run wyss memory rm <fact_id>
```

La memoria diferencia hechos del owner y contenido externo para reducir prompt injection.

### Digest

```bash
uv run wyss digest
```

Puede programarse con `[digest]` y combina pendientes, Pellegrini, rutinas y memoria sin ejecutar escrituras.

### Notion

El adapter soporta lectura de páginas, consulta de databases y escrituras gateadas. Requiere `NOTION_TOKEN` y compartir los recursos con la integración.

### Intake

`/api/intake` se habilita explícitamente mediante `[intake]`. Usa un bearer separado del pairing y eleva toda propuesta externa a un mínimo B.

### Android

El proyecto nativo vive en `mobile/`. El checkpoint final registró instalación, pairing QR y carga del bridge con pinning TOFU en un teléfono real.

## Arquitectura

```text
src/
├── core/          dominio, ports, política e invariantes
├── orchestrator/  daemon, dispatcher, pending, rutinas y digest
├── agents/        agentes configurables
├── knowledge/     ingesta, FTS5, vectores y retrieval
├── gateway/       providers, minimizer, costos y traces
├── execution/     filesystem, shell, git, executor y undo
├── audit/         auditoría SQLite append-only
├── ledger/        finanzas deterministas
├── memory/        memoria durable del owner
├── notion/        adapter Notion
└── bootstrap/     config, DI, CLI y bridge web

web/               SPA React
mobile/            cliente Android Capacitor
```

Reglas de capas:

- `core` es stdlib-only;
- las capas importan de `core`, no entre sí;
- `bootstrap` es el composition root;
- Pydantic muere en la frontera de configuración;
- el LLM propone, la política decide;
- nivel D no tiene bypass.

## Configuración

- TOML no sensible: `config/config.toml`;
- secretos: `config/.env`;
- plantilla: `config/config.example.toml`;
- referencia: [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

La configuración falla ante claves desconocidas o tipos incorrectos. Las reglas TOML solo agregan restricciones; nunca eliminan la denylist built-in.

## Verificación

Python y arquitectura:

```bash
uv run pytest -q
uv run mypy
uv run ruff check src tests
uv run lint-imports
```

SPA:

```bash
cd web
npm ci
npm run test
npm run lint
npm run build
```

Android:

```bash
cd mobile/android
./gradlew testDebugUnitTest
./gradlew assembleDebug
```

El workflow raíz automatiza Python, web y Android como gates independientes y bloqueantes. Ver
[`docs/TESTING.md`](docs/TESTING.md).

## Límites conocidos

- undo limitado a archivos;
- dependencias externas para LLM y Notion;
- TLS local y pairing basados en confianza TOFU;
- NTFS/FUSE puede ignorar permisos POSIX o impedir WAL;
- la publicación v1 final sigue bloqueada hasta completar integración, evidencia física y rollback.

## Documentación

La fuente canónica es [`docs/README.md`](docs/README.md). `.planning/` conserva requisitos, decisiones y evidencia histórica, pero no tiene precedencia sobre código, pruebas o `docs/RELEASE_STATUS.md`.

---

*Filosofía rectora: humano primero, IA cuando corresponde.*
